from datetime import date

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import (
    Cliente,
    Configuracion,
    Pedido,
    Producto,
    RenglonPedido,
    normalizar_descripcion,
)

MESES = [
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
]
MES_CHOICES = [('', '---------')] + [(mes, mes) for mes in MESES]


def anio_choices():
    actual = date.today().year
    return [('', '---------')] + [(str(a), str(a)) for a in range(actual - 5, actual + 11)]


class PedidoForm(forms.ModelForm):
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.all(),
        widget=forms.HiddenInput(),
        error_messages={'required': 'Debes elegir un cliente.'},
    )

    class Meta:
        model = Pedido
        fields = ['cliente']


class RenglonPedidoForm(forms.ModelForm):
    producto = forms.ModelChoiceField(
        queryset=Producto.objects.all(),
        widget=forms.HiddenInput(),
        error_messages={'required': 'Debes elegir un producto.'},
    )
    caducidad_mes = forms.ChoiceField(choices=MES_CHOICES, required=False, label='Caducidad (mes)')
    caducidad_anio = forms.ChoiceField(choices=[], required=False, label='Caducidad (año)')
    produccion_mes = forms.ChoiceField(choices=MES_CHOICES, required=False, label='Producción (mes)')
    produccion_anio = forms.ChoiceField(choices=[], required=False, label='Producción (año)')
    # Propagar la descripción al catálogo afecta a todos los pedidos futuros y
    # a los demás usuarios, así que es una acción deliberada y no un efecto
    # secundario de escribir en el campo: nunca viene marcada de entrada.
    corregir_catalogo = forms.BooleanField(
        required=False,
        label='Corregir también en el catálogo',
    )

    class Meta:
        model = RenglonPedido
        fields = [
            'producto', 'descripcion', 'cantidad', 'unidad', 'cas', 'onu',
            'paquetes', 'lote', 'salida',
            'peso_bruto', 'peso_tara', 'caducidad', 'produccion',
        ]
        labels = {
            'cas': 'CAS',
            'onu': 'ONU',
            'descripcion': 'Descripción',
        }
        widgets = {
            'descripcion': forms.TextInput(attrs={'autocomplete': 'off'}),
            'unidad': forms.TextInput(attrs={'readonly': 'readonly'}),
            'cantidad': forms.NumberInput(attrs={'step': '0.001'}),
            'peso_bruto': forms.NumberInput(attrs={'step': '0.001'}),
            'peso_tara': forms.NumberInput(attrs={'step': '0.001'}),
            'paquetes': forms.NumberInput(attrs={'min': '1'}),
            'caducidad': forms.HiddenInput(),
            'produccion': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        opciones_anio = anio_choices()
        self.fields['caducidad_anio'].choices = opciones_anio
        self.fields['produccion_anio'].choices = opciones_anio

        if self.instance and self.instance.pk:
            mes, anio = self._separar_mes_anio(self.instance.caducidad)
            self.initial.setdefault('caducidad_mes', mes)
            self.initial.setdefault('caducidad_anio', anio)
            mes, anio = self._separar_mes_anio(self.instance.produccion)
            self.initial.setdefault('produccion_mes', mes)
            self.initial.setdefault('produccion_anio', anio)

    @staticmethod
    def _separar_mes_anio(valor):
        if not valor:
            return '', ''
        partes = valor.rsplit(' ', 1)
        if len(partes) == 2 and partes[0] in MESES and partes[1].isdigit():
            return partes[0], partes[1]
        return '', ''

    def _combinar_mes_anio(self, prefijo, cleaned):
        mes = cleaned.get(f'{prefijo}_mes')
        anio = cleaned.get(f'{prefijo}_anio')
        if mes and anio:
            return f'{mes} {anio}'
        if mes or anio:
            campo = f'{prefijo}_anio' if mes else f'{prefijo}_mes'
            self.add_error(campo, 'Debes elegir mes y año.')
        return ''

    def clean(self):
        cleaned = super().clean()
        producto = cleaned.get('producto')

        if cleaned.get('DELETE') or not producto:
            return cleaned

        # El servidor manda: si el catálogo ya trae CAS/ONU, se usa ese valor
        # sin importar lo que haya llegado del formulario.
        if producto.cas:
            cleaned['cas'] = producto.cas
        if producto.onu:
            cleaned['onu'] = producto.onu

        # La descripción funciona al revés que CAS/ONU, y es intencional: es
        # justo el dato que el usuario puede corregir, porque muchas vinieron
        # mal del sistema viejo. Lo que escribió se guarda SIEMPRE en el
        # renglón; el catálogo solo se toca si marcó la casilla, y de eso se
        # encarga la vista con Producto.corregir_descripcion().
        # Si borró el campo, se queda con la del catálogo: una etiqueta sin
        # nombre de producto es peor que un nombre mal escrito.
        # El modelo va como segundo argumento para que, si alguien escribió
        # "E7000 — BUTIRATO DE ETILO" imitando el buscador, se guarde solo el
        # nombre y el modelo no quede repetido dentro de la descripción.
        descripcion = (
            normalizar_descripcion(cleaned.get('descripcion'), producto.modelo)
            or producto.descripcion
        )
        cleaned['descripcion'] = descripcion

        # Quien decide si se toca el catálogo es el servidor, comparando
        # contra el valor de ahora: que la casilla esté oculta en la pantalla
        # no impide que llegue marcada en el POST.
        cleaned['corregir_catalogo'] = (
            bool(cleaned.get('corregir_catalogo')) and descripcion != producto.descripcion
        )

        cleaned['caducidad'] = self._combinar_mes_anio('caducidad', cleaned)
        cleaned['produccion'] = self._combinar_mes_anio('produccion', cleaned)

        paquetes = cleaned.get('paquetes') or 0
        if paquetes < 1:
            self.add_error('paquetes', 'Paquetes debe ser al menos 1.')

        peso_bruto = cleaned.get('peso_bruto')
        peso_tara = cleaned.get('peso_tara')
        if peso_bruto is not None and peso_tara is not None and peso_tara > peso_bruto:
            self.add_error(None, 'El peso tara no puede ser mayor que el peso bruto.')

        return cleaned


class BaseRenglonPedidoFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        renglones_activos = 0
        correcciones = {}
        for form in self.forms:
            if not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            producto = form.cleaned_data.get('producto')
            if not producto:
                continue
            renglones_activos += 1

            # El mismo producto puede ir en dos renglones del pedido. Si los
            # dos piden corregir el catálogo con textos distintos, en vez de
            # dejar que gane el último se rechaza el guardado: el usuario
            # tiene que decidir cuál es el nombre bueno.
            if not form.cleaned_data.get('corregir_catalogo'):
                continue
            descripcion = form.cleaned_data['descripcion']
            previa = correcciones.setdefault(producto.pk, descripcion)
            if previa != descripcion:
                raise forms.ValidationError(
                    f'Hay dos renglones del producto {producto.pk} que piden corregir el '
                    f'catálogo con descripciones distintas: «{previa}» y «{descripcion}». '
                    f'Deja marcada la casilla solo en el renglón con el nombre correcto.'
                )

        if renglones_activos < 1:
            raise forms.ValidationError('El pedido debe tener al menos un renglón.')


RenglonPedidoFormSet = inlineformset_factory(
    Pedido,
    RenglonPedido,
    form=RenglonPedidoForm,
    formset=BaseRenglonPedidoFormSet,
    extra=1,
    can_delete=True,
)


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = Configuracion
        fields = ['calib_x', 'calib_y', 'calib_interlineado', 'calib_paso', 'offset_x', 'offset_y']
        labels = {
            'calib_x': 'X',
            'calib_y': 'Y',
            'calib_interlineado': 'Interlineado',
            'calib_paso': 'Paso',
            'offset_x': 'Offset X',
            'offset_y': 'Offset Y',
        }
        help_texts = {
            'calib_x': 'Posición horizontal (mm desde el borde izquierdo de la hoja) donde empieza a escribirse cada valor.',
            'calib_y': 'Posición vertical (mm desde el borde superior de la hoja) de la primera línea (VENDIDO A) de la primera etiqueta.',
            'calib_interlineado': 'Separación vertical (mm) entre renglones consecutivos de la rejilla de una misma etiqueta.',
            'calib_paso': 'Distancia vertical (mm) de una etiqueta a la siguiente en la misma hoja.',
            'offset_x': 'Ajuste fino horizontal (mm) que se suma a X. Úsalo para corregir un desfase parejo en todas las líneas.',
            'offset_y': 'Ajuste fino vertical (mm) que se suma a Y. Úsalo para corregir un desfase parejo en todas las etiquetas.',
        }
        widgets = {
            campo: forms.NumberInput(attrs={'step': '0.1'})
            for campo in ['calib_x', 'calib_y', 'calib_interlineado', 'calib_paso', 'offset_x', 'offset_y']
        }
