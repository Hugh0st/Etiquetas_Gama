from datetime import date

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import Cliente, Pedido, Producto, RenglonPedido

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

    class Meta:
        model = RenglonPedido
        fields = [
            'producto', 'cantidad', 'unidad', 'cas', 'onu',
            'barriles', 'paquetes', 'lote', 'salida',
            'peso_bruto', 'peso_tara', 'caducidad', 'produccion',
        ]
        labels = {
            'cas': 'CAS',
            'onu': 'ONU',
        }
        widgets = {
            'unidad': forms.TextInput(attrs={'readonly': 'readonly'}),
            'cantidad': forms.NumberInput(attrs={'step': '0.001'}),
            'peso_bruto': forms.NumberInput(attrs={'step': '0.001'}),
            'peso_tara': forms.NumberInput(attrs={'step': '0.001'}),
            'barriles': forms.NumberInput(attrs={'min': '0'}),
            'paquetes': forms.NumberInput(attrs={'min': '0'}),
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

        cleaned['caducidad'] = self._combinar_mes_anio('caducidad', cleaned)
        cleaned['produccion'] = self._combinar_mes_anio('produccion', cleaned)

        barriles = cleaned.get('barriles') or 0
        paquetes = cleaned.get('paquetes') or 0
        if barriles == 0 and paquetes == 0:
            self.add_error(None, 'Barriles y paquetes no pueden ser ambos cero.')

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
        for form in self.forms:
            if not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            if not form.cleaned_data.get('producto'):
                continue
            renglones_activos += 1

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
