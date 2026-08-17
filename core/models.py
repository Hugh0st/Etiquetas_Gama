from django.conf import settings
from django.db import models


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


class Producto(models.Model):
    modelo = models.CharField(max_length=20, primary_key=True)
    descripcion = models.CharField(max_length=255, blank=True)
    unidad = models.CharField(max_length=20, blank=True)
    cas = models.CharField(max_length=50, blank=True)
    onu = models.CharField(max_length=50, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['modelo']

    def __str__(self):
        return f'{self.modelo} - {self.descripcion}'


class LineaEspecificacion(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='especificacion')
    orden = models.IntegerField()
    texto = models.CharField(max_length=500)

    class Meta:
        ordering = ['producto', 'orden']
        constraints = [
            models.UniqueConstraint(fields=['producto', 'orden'], name='unico_producto_orden'),
        ]

    def __str__(self):
        return f'{self.producto_id} [{self.orden}] {self.texto}'


class Pedido(models.Model):
    folio = models.AutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='pedidos')
    fecha = models.DateTimeField(auto_now_add=True)
    usuario_creador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pedidos')
    emitido = models.BooleanField(default=False)
    fecha_emision = models.DateTimeField(null=True, blank=True)
    cliente_snapshot = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-folio']

    def __str__(self):
        return f'Pedido {self.folio} - {self.cliente_id}'


class RenglonPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='renglones')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='renglones_pedido')
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    unidad = models.CharField(max_length=20, blank=True)
    barriles = models.IntegerField(default=0)
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
