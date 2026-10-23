import hashlib
import json

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

    # ------------------------------------------------------------------
    # Especificación
    # ------------------------------------------------------------------
    def lineas_frescas(self):
        """Las líneas del catálogo leídas de la base, sin pasar por la caché.

        A propósito no se usa self.especificacion.all(): si alguien cargó el
        producto con prefetch_related('especificacion'), eso devolvería la
        copia en memoria, y el editor estaría decidiendo sobre una foto vieja
        justo mientras la reescribe.
        """
        return LineaEspecificacion.objects.filter(producto=self).order_by('orden')

    def especificacion_a_lista(self):
        """La especificación del catálogo con la misma forma que el snapshot."""
        return [
            {
                'linea_id': linea.pk,
                'orden': linea.orden,
                'texto': linea.texto,
                'es_continuacion': linea.es_continuacion,
                'tipo_continuacion': linea.tipo_continuacion,
            }
            for linea in self.lineas_frescas()
        ]

    def hash_especificacion(self):
        """Huella de la especificación tal como está ahora.

        Se manda en la pantalla de edición y se vuelve a calcular al guardar:
        si alguien más la cambió mientras esa pantalla estaba abierta, el
        guardado se rechaza en vez de pisar su trabajo sin avisar. Cualquier
        usuario puede editar, así que dos personas sobre el mismo producto no
        es hipotético.
        """
        crudo = json.dumps(self.especificacion_a_lista(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(crudo.encode('utf-8')).hexdigest()[:16]

    def analizar_cambio_especificacion(self, filas):
        """Qué resultados ya capturados se llevaría consigo este cambio.

        Solo mira pedidos en curso. Los resultados de un pedido emitido están
        desatados de su línea (linea=NULL) desde el momento de emitir, así que
        filtrar por línea los excluye solo: un cambio en el catálogo no puede
        alcanzar un documento ya entregado.

        Devuelve (destructivos, vacios):
          destructivos  líneas con resultados que tienen texto capturado; hay
                        que confirmar antes de aplicar
          vacios        líneas cuyos resultados están en blanco; se borran sin
                        preguntar, porque no se pierde nada
        """
        ids_que_quedan = {f['id'] for f in filas if f['id']}
        ids_vueltas_continuacion = {
            f['id'] for f in filas if f['id'] and f['es_continuacion']
        }

        afectadas = []
        for linea in self.lineas_frescas():
            if linea.pk not in ids_que_quedan:
                afectadas.append((linea, 'borrada'))
            elif linea.pk in ids_vueltas_continuacion and not linea.es_continuacion:
                # Una continuación no lleva resultado propio, así que marcarla
                # deja huérfano lo que ya se había capturado. Mismo trato que
                # borrarla, aunque la línea siga ahí.
                afectadas.append((linea, 'continuacion'))

        destructivos, vacios = [], []
        for linea, motivo in afectadas:
            resultados = list(
                ResultadoLaboratorio.objects
                .filter(linea=linea, renglon__pedido__emitido=False)
                .select_related('renglon__pedido')
            )
            if not resultados:
                continue

            con_texto = [r for r in resultados if r.texto.strip()]
            afectados = con_texto or resultados
            aviso = {
                'linea_id': linea.pk,
                'texto': linea.texto,
                'motivo': motivo,
                'resultados': len(afectados),
                'pedidos': sorted({
                    r.renglon.pedido.folio or f'borrador #{r.renglon.pedido_id}'
                    for r in afectados
                }),
            }
            (destructivos if con_texto else vacios).append(aviso)

        return destructivos, vacios

    def aplicar_especificacion(self, filas, usuario, pedido=None, confirmado=False, huella=None):
        """Reescribe la especificación del catálogo y deja registro.

        `filas` viene en el orden deseado, cada una con id (None si es nueva),
        texto, es_continuacion y tipo_continuacion. Las líneas se renumeran
        1..N según ese orden.

        Levanta EspecificacionCambiadaPorOtro si `huella` ya no corresponde, y
        EspecificacionDestruyeResultados si el cambio se llevaría resultados
        con texto y `confirmado` es falso.
        """
        if huella is not None and huella != self.hash_especificacion():
            raise EspecificacionCambiadaPorOtro()

        # Los "vacios" no se consultan aquí a propósito: sus resultados están
        # en blanco, así que se borran sin preguntar junto con su línea. El
        # análisis los separa para poder mostrarlos en la pantalla.
        destructivos, _ = self.analizar_cambio_especificacion(filas)
        if destructivos and not confirmado:
            raise EspecificacionDestruyeResultados(destructivos)

        with transaction.atomic():
            anterior = self.especificacion_a_lista()
            existentes = {linea.pk: linea for linea in self.lineas_frescas()}
            ids_que_quedan = {f['id'] for f in filas if f['id']}

            borradas = [linea for pk, linea in existentes.items() if pk not in ids_que_quedan]
            vueltas_continuacion = [
                existentes[f['id']] for f in filas
                if f['id'] and f['es_continuacion'] and not existentes[f['id']].es_continuacion
            ]

            # Los resultados se borran antes que su línea: el FK es PROTECT a
            # propósito, para que nada se lleve un resultado por accidente.
            a_limpiar = [l.pk for l in borradas] + [l.pk for l in vueltas_continuacion]
            eliminados, pedidos_afectados = self._borrar_resultados_de(a_limpiar)

            for linea in borradas:
                linea.delete()

            # Renumeración en dos fases. UniqueConstraint(producto, orden) hace
            # que mover una línea al lugar de otra choque, así que primero
            # todas se van a órdenes negativos, que nadie más usa, y de ahí al
            # definitivo.
            for i, linea in enumerate(existentes.values()):
                if linea.pk in ids_que_quedan:
                    LineaEspecificacion.objects.filter(pk=linea.pk).update(orden=-(i + 1))

            for posicion, fila in enumerate(filas, start=1):
                tipo = fila['tipo_continuacion'] if fila['es_continuacion'] else ''
                if fila['id']:
                    LineaEspecificacion.objects.filter(pk=fila['id']).update(
                        orden=posicion,
                        texto=fila['texto'],
                        es_continuacion=fila['es_continuacion'],
                        tipo_continuacion=tipo,
                    )
                else:
                    LineaEspecificacion.objects.create(
                        producto=self,
                        orden=posicion,
                        texto=fila['texto'],
                        es_continuacion=fila['es_continuacion'],
                        tipo_continuacion=tipo,
                    )

            # El orden de cada resultado se mantiene igual al de su línea: es
            # la copia que se congela al emitir y la que lee el certificado.
            # Los resultados de pedidos emitidos tienen linea=NULL, así que
            # este barrido no los toca.
            for linea in self.lineas_frescas():
                ResultadoLaboratorio.objects.filter(linea=linea).exclude(
                    orden=linea.orden
                ).update(orden=linea.orden)

            return CorreccionEspecificacionProducto.objects.create(
                producto=self,
                usuario=usuario,
                pedido=pedido,
                origen=(
                    CorreccionEspecificacionProducto.ORIGEN_PEDIDO if pedido
                    else CorreccionEspecificacionProducto.ORIGEN_CATALOGO
                ),
                especificacion_anterior=anterior,
                especificacion_nueva=self.especificacion_a_lista(),
                resultados_eliminados=eliminados,
                pedidos_afectados=', '.join(pedidos_afectados),
            )

    @staticmethod
    def _borrar_resultados_de(ids_linea):
        """Borra los resultados atados a esas líneas y dice a quién tocó.

        Devuelve (cuántos, lista de pedidos). Solo alcanza pedidos en curso:
        los emitidos tienen sus resultados desatados.
        """
        if not ids_linea:
            return 0, []

        resultados = list(
            ResultadoLaboratorio.objects
            .filter(linea_id__in=ids_linea)
            .select_related('renglon__pedido')
        )
        if not resultados:
            return 0, []

        pedidos = sorted({
            r.renglon.pedido.folio or f'borrador #{r.renglon.pedido_id}'
            for r in resultados
        })
        ResultadoLaboratorio.objects.filter(pk__in=[r.pk for r in resultados]).delete()
        return len(resultados), pedidos


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


class EspecificacionCambiadaPorOtro(Exception):
    """Alguien más cambió la especificación mientras esta pantalla estaba abierta."""


class EspecificacionDestruyeResultados(Exception):
    """El cambio se llevaría resultados ya capturados y falta confirmarlo.

    Lleva en `impacto` la lista de lo que se perdería, para poder mostrarla.
    """

    def __init__(self, impacto):
        self.impacto = impacto
        super().__init__('El cambio eliminaría resultados de laboratorio ya capturados.')


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
    def datos_cliente(self):
        """Los datos del cliente que le tocan a ESTE pedido.

        Un pedido emitido lee del snapshot congelado al emitirlo; uno en curso,
        del catálogo. Así una etiqueta reimpresa de un pedido ya entregado sigue
        diciendo lo mismo aunque después se corrija el cliente en Catálogos.

        Las claves pueden faltar en un snapshot viejo, así que quien lo use
        debe hacerlo con .get().
        """
        if self.cliente_snapshot is not None:
            return self.cliente_snapshot
        return self.cliente.a_snapshot()

    @property
    def nombre_cliente_impresion(self):
        """El nombre del cliente tal como va impreso, con el mismo criterio
        en el certificado y en la etiqueta."""
        datos = self.datos_cliente
        return datos.get('razon_social') or datos.get('nombre_corto') or ''

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
                        renglon.especificacion_snapshot = renglon.producto.especificacion_a_lista()
                        # La descripción también se congela aquí. Si el renglón
                        # la tiene vacía, descripcion_impresion cae al catálogo,
                        # y entonces un pedido ya entregado cambiaría de nombre
                        # si alguien corrige ese producto después. Copiarla en
                        # este instante no cambia lo que se imprime hoy: es el
                        # mismo valor al que caería el respaldo.
                        if not renglon.descripcion:
                            renglon.descripcion = renglon.producto.descripcion
                        renglon.save(update_fields=['especificacion_snapshot', 'descripcion'])

                        # Se desatan los resultados de la línea del catálogo,
                        # conservando su orden. A partir de aquí el pedido es
                        # autocontenido: el snapshot y el orden lo dicen todo,
                        # y editar o borrar una línea del catálogo ya no puede
                        # alcanzar un documento que se entregó al cliente.
                        renglon.resultados.update(linea=None)
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
    def lineas_especificacion(self):
        """Las líneas de especificación que le toca mostrar a ESTE renglón.

        Un renglón congelado lee del snapshot que se guardó al emitir; uno en
        curso, del catálogo. Así la pantalla de resultados muestra exactamente
        lo mismo que el certificado, y corregir el catálogo no altera un pedido
        que ya se entregó al cliente.

        Que el snapshot exista (aunque sea una lista vacía) es la señal de que
        el renglón está congelado: solo Pedido.emitir() lo escribe, y un pedido
        emitido ya no se puede editar. Una lista vacía significa "este producto
        no tenía especificación al emitir", no "búscala en el catálogo", igual
        que lo interpreta el certificado.

        Devuelve diccionarios con la misma forma en los dos casos, la del
        snapshot, para que quien los use no tenga que saber de dónde salieron.
        Los snapshots viejos pueden no traer todas las claves, así que se
        rellenan.
        """
        if self.especificacion_snapshot is not None:
            return [
                {
                    # Los snapshots escritos antes del FK no traen linea_id.
                    # No importa: un renglón congelado empareja por orden.
                    'id': linea.get('linea_id'),
                    'orden': linea.get('orden'),
                    'texto': linea.get('texto') or '',
                    'es_continuacion': linea.get('es_continuacion', False),
                    'tipo_continuacion': (
                        linea.get('tipo_continuacion')
                        or LineaEspecificacion.TIPO_CONTINUACION_PARAMETROS
                    ),
                }
                for linea in self.especificacion_snapshot
            ]

        return [
            {
                'id': linea.pk,
                'orden': linea.orden,
                'texto': linea.texto,
                'es_continuacion': linea.es_continuacion,
                'tipo_continuacion': linea.tipo_continuacion,
            }
            for linea in self.producto.especificacion.all()
        ]

    def filas_resultado(self):
        """Las líneas de este renglón, cada una con el resultado que le toca.

        El emparejamiento cambia según el renglón esté congelado o en curso, y
        esa es justo la razón de que viva aquí y no en la vista:

        - En curso: por la LÍNEA. Es el vínculo real, así que reordenar o
          insertar en el catálogo no desalinea nada.
        - Congelado: por el ORDEN. Al emitir, los resultados se desatan de la
          línea (linea=NULL) y lo único que los une al snapshot es el orden,
          que quedó guardado junto a él. Es el mismo criterio que usa el
          certificado.
        """
        lineas = self.lineas_especificacion
        resultados = self.resultados.all()

        if self.especificacion_snapshot is not None:
            por_clave = {r.orden: r.texto for r in resultados}
            claves = [linea['orden'] for linea in lineas]
        else:
            por_clave = {r.linea_id: r.texto for r in resultados}
            claves = [linea['id'] for linea in lineas]

        return [
            {'linea': linea, 'texto': por_clave.get(clave, '')}
            for linea, clave in zip(lineas, claves)
        ]

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

    # A qué línea de especificación corresponde este resultado.
    #
    # El vínculo es la IDENTIDAD de la línea, no su posición. Antes era el
    # campo `orden`, y con eso reordenar la especificación dejaba cada
    # resultado pegado a una posición: un valor acababa impreso bajo otro
    # parámetro, en un certificado de análisis, sin que nada avisara. Con el
    # FK, reordenar solo reescribe `orden` en las líneas y los resultados no
    # se mueven, porque nunca estuvieron atados a un lugar.
    #
    # PROTECT a propósito: borrar una línea con resultados capturados no debe
    # poder pasar de lado. El editor calcula el impacto y pide confirmación,
    # y borra los resultados explícitamente antes de la línea.
    #
    # Queda en NULL en dos casos: un pedido emitido (Pedido.emitir() los
    # desata para que el documento sea autocontenido y ningún cambio del
    # catálogo lo pueda alcanzar) y un resultado heredado al que la migración
    # 0019 no le encontró línea.
    linea = models.ForeignKey(
        LineaEspecificacion,
        on_delete=models.PROTECT,
        related_name='resultados',
        null=True,
        blank=True,
    )

    # Copia del orden de la línea, sincronizada mientras el resultado está
    # atado. Es lo que se congela al emitir y lo que empareja el certificado
    # contra especificacion_snapshot.
    orden = models.IntegerField()
    texto = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['renglon', 'orden']
        constraints = [
            # Un resultado por línea y renglón. No se usa (renglon, orden)
            # porque la renumeración de un reordenamiento lo violaría a medio
            # camino, y porque los resultados desatados comparten linea=NULL
            # (los NULL no chocan entre sí en una restricción única).
            models.UniqueConstraint(fields=['renglon', 'linea'], name='unico_renglon_linea'),
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


class CorreccionEspecificacionProducto(models.Model):
    """Bitácora de las ediciones a la especificación de un producto.

    Las líneas de especificación se importaron del sistema de consola viejo y
    la migración dejó errores: texto duplicado, continuaciones sin marcar. No
    se revisa el catálogo completo: se corrige sobre la marcha, conforme cada
    producto se usa, desde la pantalla de captura de resultados.

    Una fila por SESIÓN de edición, no por línea: lo que el usuario hizo de un
    jalón es una sola corrección, y agruparla así deja ver qué cambió junto.
    Por eso el antes y el después se guardan completos, con la misma forma que
    especificacion_snapshot, en vez de un diff línea por línea: con la foto
    entera siempre se puede reconstruir cualquier momento y comparar dos.

    Hermana de CorreccionDescripcionProducto, con las mismas convenciones para
    que las dos bitácoras se lean igual en el admin. No se edita a mano.
    """
    ORIGEN_PEDIDO = 'pedido'
    ORIGEN_CATALOGO = 'catalogo'
    ORIGEN_CHOICES = [
        (ORIGEN_PEDIDO, 'Captura de resultados'),
        (ORIGEN_CATALOGO, 'Catálogos'),
    ]

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name='correcciones_especificacion',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='correcciones_especificacion',
    )
    fecha = models.DateTimeField(auto_now_add=True)
    origen = models.CharField(max_length=10, choices=ORIGEN_CHOICES)
    # De qué pedido salió la corrección. SET_NULL y no CASCADE porque un
    # borrador sí se puede eliminar, y el registro no debe irse con él: el
    # catálogo ya quedó cambiado.
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='correcciones_especificacion',
    )

    especificacion_anterior = models.JSONField()
    especificacion_nueva = models.JSONField()

    # Cuántos resultados de laboratorio se llevó el cambio y de qué pedidos.
    # Una edición destructiva tiene que quedar rastreable: es lo único de esta
    # bitácora que no se puede reconstruir del antes y el después.
    resultados_eliminados = models.IntegerField(default=0)
    pedidos_afectados = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Corrección de especificación'
        verbose_name_plural = 'Correcciones de especificación'

    def __str__(self):
        return f'{self.producto_id}: {self.resumen}'

    @property
    def resumen(self):
        """Cuántas líneas había antes y cuántas quedaron."""
        antes = len(self.especificacion_anterior or [])
        despues = len(self.especificacion_nueva or [])
        # Con flecha ASCII y no →: __str__ usa esto, y una consola de
        # Windows en cp1252 no puede imprimir ese caracter.
        return f'{antes} líneas -> {despues} líneas'

    @property
    def procedencia(self):
        """Dónde se hizo la corrección, para leerla de un vistazo."""
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
