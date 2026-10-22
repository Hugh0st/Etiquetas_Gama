from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone


# Separadores con los que alguien pegaría el modelo al inicio de la
# descripción, imitando cómo se veía el buscador de productos ("E7000 — ...").
SEPARADORES_PREFIJO = ' -–—:'


def normalizar_descripcion(texto, modelo=None):
    """Deja una descripción de producto en el estilo del catálogo.

    Todo el catálogo viene del sistema de consola viejo y está en mayúsculas,
    y tanto la etiqueta como el certificado imprimen el texto tal cual. Sin
    normalizar, el catálogo acabaría con dos estilos de escritura según quién
    corrigió cada nombre.

    Si se pasa el modelo, además se le quita al texto ese modelo cuando viene
    pegado al inicio (ver _quitar_prefijo_modelo). El campo de descripción
    lleva solo el nombre; el modelo repetido dentro es un error que después
    habría que corregir a mano.
    """
    limpio = ' '.join((texto or '').split()).upper()
    return _quitar_prefijo_modelo(limpio, modelo)


def _quitar_prefijo_modelo(texto, modelo):
    """Quita del inicio del texto el modelo del producto y su separador.

    Red de seguridad por si alguien escribe "E7000 — BUTIRATO DE ETILO" en el
    campo de descripción. Tres cuidados:

    - No aplica a los modelos puramente numéricos (hay dos en el catálogo,
      "6" y "8"). En nomenclatura química un número al inicio es parte del
      nombre, y textos como "6-METIL CUMARINA" o "2 METHYL BUTIRIC ACID"
      perderían información real.
    - Solo mira el prefijo exacto. Los guiones y dos puntos dentro del nombre
      son legítimos ("AC.ESC. LAVANDIN CR-516") y no se tocan.
    - Tiene que haber un separador de verdad: en "E7000X ALGO" el modelo es el
      arranque de una palabra más larga, no un prefijo.

    Si el texto era solo el modelo, devuelve vacío para que el llamador caiga
    al respaldo de la descripción del catálogo.
    """
    modelo = (modelo or '').strip().upper()
    if not modelo or modelo.isdigit() or not texto.startswith(modelo):
        return texto

    resto = texto[len(modelo):]
    if not resto:
        return ''

    sin_separador = resto.lstrip(SEPARADORES_PREFIJO)
    if sin_separador == resto:
        return texto
    return sin_separador


class Cliente(models.Model):
    codigo = models.CharField(max_length=20, primary_key=True)
    nombre_corto = models.CharField(max_length=255, blank=True)
    razon_social = models.CharField(max_length=255, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    numero_exterior = models.CharField(max_length=50, blank=True)
    numero_interior = models.CharField(max_length=50, blank=True)
    colonia = models.CharField(max_length=255, blank=True)
    municipio = models.CharField(max_length=255, blank=True)
    ciudad = models.CharField(max_length=255, blank=True)
    estado = models.CharField(max_length=255, blank=True)
    pais = models.CharField(max_length=255, blank=True)
    cp = models.CharField(max_length=20, blank=True)
    rfc = models.CharField(max_length=20, blank=True)
    tel1 = models.CharField(max_length=50, blank=True)
    tel2 = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nombre_corto or self.razon_social}'

    def a_snapshot(self):
        """Datos congelados al emitir un pedido. El certificado imprime razon_social."""
        return {
            'codigo': self.codigo,
            'nombre_corto': self.nombre_corto,
            'razon_social': self.razon_social,
            'direccion': self.direccion,
            'numero_exterior': self.numero_exterior,
            'numero_interior': self.numero_interior,
            'colonia': self.colonia,
            'municipio': self.municipio,
            'ciudad': self.ciudad,
            'estado': self.estado,
            'pais': self.pais,
            'cp': self.cp,
            'rfc': self.rfc,
            'tel1': self.tel1,
            'tel2': self.tel2,
            'email': self.email,
        }


class Producto(models.Model):
    UNIDAD_KGS = 'KGS.'
    UNIDAD_LTS = 'LTS.'
    UNIDAD_CHOICES = [
        (UNIDAD_KGS, 'Kilogramos'),
        (UNIDAD_LTS, 'Litros'),
    ]

    modelo = models.CharField(max_length=20, primary_key=True)
    descripcion = models.CharField(max_length=255, blank=True)
    unidad = models.CharField(max_length=4, choices=UNIDAD_CHOICES, default=UNIDAD_KGS)
    cas = models.CharField(max_length=50, blank=True)
    onu = models.CharField(max_length=50, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['modelo']

    def __str__(self):
        return f'{self.modelo} - {self.descripcion}'

    def corregir_descripcion(self, nueva, usuario, pedido=None):
        """Corrige la descripción en el catálogo dejando registro de quién y cuándo.

        Es el único camino para cambiar la descripción con bitácora, para que
        el catálogo no se pueda actualizar sin dejar rastro. Devuelve el
        registro creado, o None si no había nada que cambiar (texto vacío o
        igual al que ya estaba).
        """
        nueva = normalizar_descripcion(nueva, self.modelo)
        if not nueva or nueva == self.descripcion:
            return None

        anterior = self.descripcion
        with transaction.atomic():
            self.descripcion = nueva
            self.save(update_fields=['descripcion'])
            return CorreccionDescripcionProducto.objects.create(
                producto=self,
                descripcion_anterior=anterior,
                descripcion_nueva=nueva,
                usuario=usuario,
                pedido=pedido,
                origen=(
                    CorreccionDescripcionProducto.ORIGEN_PEDIDO if pedido
                    else CorreccionDescripcionProducto.ORIGEN_CATALOGO
                ),
            )


class LineaEspecificacion(models.Model):
    TIPO_CONTINUACION_PARAMETROS = 'parametros'
    TIPO_CONTINUACION_ESPECIFICACION = 'especificacion'
    TIPO_CONTINUACION_CHOICES = [
        (TIPO_CONTINUACION_PARAMETROS, 'Parámetros (continúa el nombre, ej. "A 25 C:")'),
        (TIPO_CONTINUACION_ESPECIFICACION, 'Especificación (continúa el valor, ej. "ALCANFORADO")'),
    ]

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='especificacion')
    orden = models.IntegerField()
    texto = models.CharField(max_length=500)
    es_continuacion = models.BooleanField(
        default=False,
        help_text='Es continuación visual de la línea anterior (no lleva su propio resultado).',
    )
    tipo_continuacion = models.CharField(
        max_length=14,
        choices=TIPO_CONTINUACION_CHOICES,
        default=TIPO_CONTINUACION_PARAMETROS,
        blank=True,
        help_text='Solo aplica si es_continuacion está activo: en qué columna del certificado se imprime.',
    )

    class Meta:
        ordering = ['producto', 'orden']
        constraints = [
            models.UniqueConstraint(fields=['producto', 'orden'], name='unico_producto_orden'),
        ]

    def __str__(self):
        return f'{self.producto_id} [{self.orden}] {self.texto}'


class PedidoSinResultados(Exception):
    """Se intentó emitir un pedido sin ningún resultado de laboratorio capturado."""


class PedidoEmitidoNoSeElimina(Exception):
    """Se intentó borrar de la base un pedido que ya tiene folio.

    Un pedido emitido ya salió de la empresa: se cancela, nunca se borra, para
    no dejar huecos en la numeración consecutiva.
    """


class PedidoNoEmitido(Exception):
    """Se intentó cancelar un pedido que todavía no se ha emitido."""


class MotivoCancelacionRequerido(Exception):
    """Se intentó cancelar un pedido sin escribir el motivo."""


class PedidoQuerySet(models.QuerySet):
    def delete(self):
        """Última barrera: ni siquiera un borrado masivo puede llevarse un
        pedido emitido."""
        if self.filter(models.Q(emitido=True) | models.Q(folio__isnull=False)).exists():
            raise PedidoEmitidoNoSeElimina(
                'Hay pedidos emitidos en la selección. Un pedido con folio no se '
                'elimina: se cancela.'
            )
        return super().delete()


class Pedido(models.Model):
    # El folio (formato ####-AAMM) solo se asigna al emitir el certificado;
    # un borrador se identifica por su id interno. Ver Pedido.emitir().
    folio = models.CharField(max_length=9, unique=True, null=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='pedidos')
    fecha = models.DateTimeField(auto_now_add=True)
    usuario_creador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pedidos')
    emitido = models.BooleanField(default=False)
    fecha_emision = models.DateTimeField(null=True, blank=True)
    cliente_snapshot = models.JSONField(null=True, blank=True)

    # Cancelación: el pedido conserva folio, renglones, resultados y snapshots.
    cancelado = models.BooleanField(default=False)
    fecha_cancelacion = models.DateTimeField(null=True, blank=True)
    usuario_cancelacion = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pedidos_cancelados',
    )
    motivo_cancelacion = models.TextField(blank=True)

    objects = PedidoQuerySet.as_manager()

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'Pedido {self.folio or f"(borrador {self.id})"} - {self.cliente_id}'

    @property
    def tiene_resultados(self):
        return ResultadoLaboratorio.objects.filter(renglon__pedido=self).exclude(texto='').exists()

    @property
    def se_puede_eliminar(self):
        """Solo los pedidos que nunca salieron de la empresa."""
        return not self.emitido and not self.folio

    def delete(self, *args, **kwargs):
        if not self.se_puede_eliminar:
            raise PedidoEmitidoNoSeElimina(
                f'El pedido {self.folio} ya fue emitido. Un pedido con folio no se '
                f'elimina: se cancela.'
            )
        return super().delete(*args, **kwargs)

    def cancelar(self, usuario, motivo):
        """Anula un pedido emitido conservando todo su registro."""
        if not self.emitido:
            raise PedidoNoEmitido('Solo se puede cancelar un pedido ya emitido.')
        if self.cancelado:
            return

        motivo = (motivo or '').strip()
        if not motivo:
            raise MotivoCancelacionRequerido('Hay que escribir el motivo de la cancelación.')

        self.cancelado = True
        self.fecha_cancelacion = timezone.now()
        self.usuario_cancelacion = usuario
        self.motivo_cancelacion = motivo
        self.save(update_fields=[
            'cancelado', 'fecha_cancelacion', 'usuario_cancelacion', 'motivo_cancelacion',
        ])

    def emitir(self):
        """Asigna folio, congela los snapshots y marca el pedido como emitido.

        El folio se calcula con la fecha de emisión (no la fecha del pedido).
        Como SQLite no soporta bloqueo de filas real, la protección contra
        condiciones de carrera se hace reintentando ante un choque de folio
        único (dos emisiones simultáneas no pueden terminar con el mismo).
        """
        if self.emitido:
            return
        if not self.tiene_resultados:
            raise PedidoSinResultados('El pedido no tiene resultados de laboratorio capturados.')

        ahora = timezone.now()
        prefijo = ahora.strftime('%y%m')

        for _ in range(10):
            try:
                with transaction.atomic():
                    ultimo = (
                        Pedido.objects.select_for_update()
                        .filter(folio__endswith=f'-{prefijo}')
                        .order_by('-folio')
                        .first()
                    )
                    consecutivo = int(ultimo.folio[:4]) + 1 if ultimo else 1

                    self.folio = f'{consecutivo:04d}-{prefijo}'
                    self.fecha_emision = ahora
                    self.emitido = True
                    self.cliente_snapshot = self.cliente.a_snapshot()
                    self.save()

                    for renglon in self.renglones.select_related('producto'):
                        renglon.especificacion_snapshot = [
                            {
                                'orden': linea.orden,
                                'texto': linea.texto,
                                'es_continuacion': linea.es_continuacion,
                                'tipo_continuacion': linea.tipo_continuacion,
                            }
                            for linea in renglon.producto.especificacion.all()
                        ]
                        renglon.save(update_fields=['especificacion_snapshot'])
                return
            except IntegrityError:
                continue

        raise RuntimeError('No se pudo asignar folio después de varios intentos. Intenta de nuevo.')


class RenglonPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='renglones')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='renglones_pedido')
    # Descripción del producto tal como la lleva ESTE pedido. Se autollena con
    # la del catálogo al capturar el renglón y el usuario la puede corregir.
    # Vive aquí, y no se lee del catálogo al imprimir, para que un pedido ya
    # emitido no cambie si alguien corrige el catálogo después.
    descripcion = models.CharField(max_length=255, blank=True)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    unidad = models.CharField(max_length=20, blank=True)
    cas = models.CharField(max_length=50, blank=True)
    onu = models.CharField(max_length=50, blank=True)
    paquetes = models.IntegerField(default=0)
    lote = models.CharField(max_length=100, blank=True)
    salida = models.CharField(max_length=100, blank=True)
    peso_bruto = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    peso_tara = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    caducidad = models.CharField(max_length=100, blank=True)
    produccion = models.CharField(max_length=100, blank=True)
    especificacion_snapshot = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['pedido', 'id']

    @property
    def descripcion_impresion(self):
        """La descripción que llevan la etiqueta, el certificado y las pantallas.

        Siempre la del renglón. El respaldo al catálogo solo cubre el caso de
        un renglón que quedara sin descripción; los que ya existían cuando se
        agregó el campo los llenó la migración 0016.
        """
        return self.descripcion or self.producto.descripcion

    @property
    def peso_neto(self):
        if self.peso_bruto is None or self.peso_tara is None:
            return None
        return self.peso_bruto - self.peso_tara

    def __str__(self):
        return f'{self.pedido_id} - {self.producto_id}'


class ResultadoLaboratorio(models.Model):
    renglon = models.ForeignKey(RenglonPedido, on_delete=models.CASCADE, related_name='resultados')
    orden = models.IntegerField()
    texto = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['renglon', 'orden']
        constraints = [
            models.UniqueConstraint(fields=['renglon', 'orden'], name='unico_renglon_orden'),
        ]

    def __str__(self):
        return f'{self.renglon_id} [{self.orden}]'


class CorreccionDescripcionProducto(models.Model):
    """Bitácora de las correcciones a la descripción de un producto.

    Las descripciones se importaron del sistema de consola viejo y algunas
    quedaron mal (nombres invertidos, por ejemplo). No se revisa el catálogo
    completo: se corrige sobre la marcha, conforme cada producto se usa, desde
    la captura del pedido o desde Catálogos. Cada corrección queda registrada
    aquí para poder rastrear después de dónde salió un nombre.

    Se escribe solo desde Producto.corregir_descripcion() y desde el admin de
    Producto. No se edita a mano: es bitácora.
    """
    ORIGEN_PEDIDO = 'pedido'
    ORIGEN_CATALOGO = 'catalogo'
    ORIGEN_CHOICES = [
        (ORIGEN_PEDIDO, 'Captura del pedido'),
        (ORIGEN_CATALOGO, 'Catálogos'),
    ]

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name='correcciones_descripcion',
    )
    descripcion_anterior = models.CharField(max_length=255, blank=True)
    descripcion_nueva = models.CharField(max_length=255)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='correcciones_descripcion',
    )
    fecha = models.DateTimeField(auto_now_add=True)
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES)
    # De qué pedido salió la corrección. SET_NULL y no CASCADE porque un
    # borrador sí se puede eliminar, y el registro no debe irse con él: el
    # catálogo ya quedó cambiado. Por eso el origen se guarda en su propio
    # campo y no se deduce de que este quede vacío.
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='correcciones_descripcion',
    )

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Corrección de descripción'
        verbose_name_plural = 'Correcciones de descripción'

    def __str__(self):
        return f'{self.producto_id}: "{self.descripcion_anterior}" → "{self.descripcion_nueva}"'

    @property
    def procedencia(self):
        """Dónde se hizo la corrección, para leerla de un vistazo en la bitácora."""
        if self.origen == self.ORIGEN_CATALOGO:
            return 'Catálogos'
        if self.pedido_id is None:
            return 'Pedido (ya eliminado)'
        return f'Pedido {self.pedido.folio or f"borrador #{self.pedido_id}"}'


class Configuracion(models.Model):
    calib_x = models.FloatField(default=45.0)
    calib_y = models.FloatField(default=26.7)
    calib_interlineado = models.FloatField(default=4.1)
    calib_paso = models.FloatField(default=94.7)
    offset_x = models.FloatField(default=0.0)
    offset_y = models.FloatField(default=0.0)
    texto_almacenamiento = models.TextField(blank=True)
    nombre_control_calidad = models.CharField(max_length=255, default='FERNANDO CARDOSO')

    class Meta:
        verbose_name = 'Configuración'
        verbose_name_plural = 'Configuración'

    def __str__(self):
        return 'Configuración'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
