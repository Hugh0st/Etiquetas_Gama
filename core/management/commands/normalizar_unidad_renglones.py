"""Normaliza la unidad de los renglones de pedido que traen variantes viejas.

Por qué hace falta: la migración 0003 mapeó las variantes del sistema de
consola ('KGS', 'KGM', 'KGM.', 'LTR', 'LTR.') a los dos valores válidos, pero
**solo sobre Producto**. Los renglones de pedido copian la unidad del producto
al capturarse, así que los renglones creados antes de esa migración pueden
seguir con una variante sucia.

Eso importa ahora que la unidad del renglón es un selector de dos opciones: el
formulario autocura lo que encuentra al abrir un pedido (ver
RenglonPedidoForm._autocurar_unidad), pero esto lo limpia en bloque y, con
--dry-run, dice cuántos hay antes de desplegar.

Los renglones de pedidos EMITIDOS no se tocan por omisión. Aunque pasar 'KGS' a
'KGS.' parezca cosmético, la unidad va impresa en la etiqueta junto a los pesos
y en el certificado junto a la cantidad: cambiarla altera un documento que ya
se entregó a un cliente. El dry-run los cuenta aparte para que se vea cuántos
son, y --incluir-emitidos los incluye si algún día se decide que conviene.
"""
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Producto, RenglonPedido

PALABRA_CONFIRMACION = 'NORMALIZAR'
CARPETA_RESPALDOS = 'respaldos'
MUESTRA_POR_DEFECTO = 40
ANCHO = 74

# Las mismas variantes que mapeó la migración 0003 sobre el catálogo.
NORMALIZACION = {
    'KGS.': 'KGS.',
    'KGS': 'KGS.',
    'KGM': 'KGS.',
    'KGM.': 'KGS.',
    'LTR.': 'LTS.',
    'LTR': 'LTS.',
    'LTS.': 'LTS.',
}


class Command(BaseCommand):
    help = (
        'Normaliza la unidad de los renglones de pedido que traen variantes del '
        'sistema viejo. Con --dry-run solo muestra lo que haría. Al aplicar, '
        'respalda la base y pide confirmación escrita. No toca pedidos emitidos.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra lo que haría, sin cambiar nada ni generar respaldo.',
        )
        parser.add_argument(
            '--muestra',
            type=int,
            default=MUESTRA_POR_DEFECTO,
            help=f'Cuántos ejemplos mostrar (por omisión {MUESTRA_POR_DEFECTO}).',
        )
        parser.add_argument(
            '--incluir-emitidos',
            action='store_true',
            help=(
                'Normaliza también los renglones de pedidos emitidos. Ojo: eso '
                'cambia la unidad impresa en documentos ya entregados.'
            ),
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opciones):
        simulacro = opciones['dry_run']
        incluir_emitidos = opciones['incluir_emitidos']
        tamano_muestra = max(0, opciones['muestra'])

        self._titulo(
            'NORMALIZACIÓN DE UNIDAD EN RENGLONES' + (' (SIMULACRO)' if simulacro else '')
        )

        validas = set(dict(Producto.UNIDAD_CHOICES))
        sucios_en_curso, sucios_emitidos = self._clasificar(validas)

        self._estado_actual(validas, sucios_en_curso, sucios_emitidos)

        a_tocar = sucios_en_curso + (sucios_emitidos if incluir_emitidos else [])
        if not a_tocar:
            self.stdout.write('')
            if sucios_emitidos and not incluir_emitidos:
                self.stdout.write(self.style.WARNING(
                    f'Los {len(sucios_emitidos)} renglones sucios que hay están todos en '
                    f'pedidos emitidos, y por omisión no se tocan. Si de verdad quieres '
                    f'cambiarlos, corre con --incluir-emitidos.'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    'Todas las unidades ya son válidas. No hay nada que hacer.'
                ))
            return

        self._mostrar_cambios(a_tocar, tamano_muestra)
        self._mostrar_resumen(a_tocar, sucios_emitidos, incluir_emitidos)

        if simulacro:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'SIMULACRO: no se cambió nada ni se generó respaldo. '
                'Corre el comando sin --dry-run para aplicarlo.'
            ))
            return

        if not self._confirmar(len(a_tocar), incluir_emitidos):
            self.stdout.write(self.style.WARNING('\nCancelado. No se cambió nada.'))
            return

        ruta_respaldo = self._respaldar()
        self._aplicar(a_tocar)

        self._conteo_final(validas)
        self.stdout.write('')
        self.stdout.write(f'Respaldo previo guardado en: {ruta_respaldo}')

    # ------------------------------------------------------------------
    def _clasificar(self, validas):
        """Separa los renglones sucios según su pedido esté emitido o en curso.

        Devuelve dos listas de (renglon, unidad_nueva). La unidad nueva sale de
        la tabla de variantes conocidas y, si la que trae no está ahí, de la
        unidad que el catálogo tiene para ese producto.
        """
        en_curso, emitidos = [], []
        renglones = (
            RenglonPedido.objects
            .exclude(unidad__in=validas)
            .select_related('producto', 'pedido')
            .order_by('pedido_id', 'id')
        )
        for renglon in renglones:
            nueva = NORMALIZACION.get(renglon.unidad.strip().upper())
            if nueva is None:
                # Variante que la tabla no conoce (o unidad vacía): se usa la
                # del catálogo, que es de donde se copió en su momento.
                nueva = renglon.producto.unidad
            if nueva == renglon.unidad:
                continue
            (emitidos if renglon.pedido.emitido else en_curso).append((renglon, nueva))
        return en_curso, emitidos

    # ------------------------------------------------------------------
    def _estado_actual(self, validas, sucios_en_curso, sucios_emitidos):
        total = RenglonPedido.objects.count()
        self.stdout.write('')
        self.stdout.write('Estado actual:')
        self._fila('Renglones de pedido en total', total)
        self._fila('Con unidad válida', RenglonPedido.objects.filter(unidad__in=validas).count())
        self._fila('Con unidad sucia, pedido en curso', len(sucios_en_curso))
        self._fila('Con unidad sucia, pedido EMITIDO', len(sucios_emitidos))
        self.stdout.write('')
        self.stdout.write('Unidades que hay hoy en los renglones:')
        for valor, cuantos in Counter(
            RenglonPedido.objects.values_list('unidad', flat=True)
        ).most_common():
            marca = '' if valor in validas else '   <- sucia'
            self._fila(f'  {valor!r}', f'{cuantos}{marca}')

    def _mostrar_cambios(self, a_tocar, tamano_muestra):
        self.stdout.write('')
        self.stdout.write('-' * ANCHO)
        self.stdout.write(self.style.MIGRATE_HEADING('CAMBIOS QUE SE HARÍAN'))
        self.stdout.write('-' * ANCHO)
        for viejo, nuevo in sorted(Counter(
            (r.unidad, nueva) for r, nueva in a_tocar
        ).items()):
            self._fila(f'  {viejo[0]!r} -> {viejo[1]!r}', nuevo)

        if not tamano_muestra:
            return

        self.stdout.write('')
        self.stdout.write(
            f'  Muestra de {min(tamano_muestra, len(a_tocar))} (de {len(a_tocar)}):'
        )
        for renglon, nueva in a_tocar[:tamano_muestra]:
            pedido = renglon.pedido
            etiqueta = pedido.folio or f'borrador #{pedido.pk}'
            estado = 'EMITIDO' if pedido.emitido else 'en curso'
            self.stdout.write(
                f'    renglon={renglon.pk:<6} {etiqueta:<14} {estado:<9} '
                f'{renglon.producto_id:<12} {renglon.unidad!r} -> {nueva!r}'
            )

    def _mostrar_resumen(self, a_tocar, sucios_emitidos, incluir_emitidos):
        self.stdout.write('')
        self.stdout.write('=' * ANCHO)
        self.stdout.write(self.style.WARNING('SE VAN A CAMBIAR:'))
        self._fila('Renglones', len(a_tocar))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('NO SE TOCA:'))
        if sucios_emitidos and not incluir_emitidos:
            self._fila('Renglones de pedidos emitidos', len(sucios_emitidos))
            self.stdout.write(
                '    (la unidad va impresa en su etiqueta y su certificado;\n'
                '     cambiarla alteraría un documento ya entregado)'
            )
        self.stdout.write('    El catálogo, los resultados y todo lo demás del pedido.')

    # ------------------------------------------------------------------
    def _aplicar(self, a_tocar):
        with transaction.atomic():
            for renglon, nueva in a_tocar:
                renglon.unidad = nueva
            RenglonPedido.objects.bulk_update(
                [renglon for renglon, _ in a_tocar], ['unidad'], batch_size=500,
            )
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Listo. Se normalizó la unidad de {len(a_tocar)} renglones.'
        ))

    # ------------------------------------------------------------------
    def _confirmar(self, cuantos, incluir_emitidos):
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            f'Se va a cambiar la unidad de {cuantos} renglones de pedido.'
        ))
        if incluir_emitidos:
            self.stdout.write(self.style.ERROR(
                'Estás incluyendo pedidos EMITIDOS: eso cambia la unidad impresa '
                'en etiquetas y certificados que ya se entregaron.'
            ))
        self.stdout.write('')
        self.stdout.write(
            f'Para continuar escribe {PALABRA_CONFIRMACION} y presiona Enter. '
            f'Cualquier otra cosa cancela.'
        )
        try:
            respuesta = input('> ')
        except EOFError:
            return False
        return respuesta.strip().upper() == PALABRA_CONFIRMACION

    # ------------------------------------------------------------------
    def _respaldar(self):
        """Copia la base con la API de respaldo de SQLite.

        No es una copia de archivo: SQLite lee la base página por página y
        escribe una copia consistente, aunque haya algo escribiendo al mismo
        tiempo. Mismo procedimiento que limpiar_pedidos_prueba.
        """
        config = settings.DATABASES['default']
        if 'sqlite3' not in config['ENGINE']:
            raise CommandError(
                f'Este comando respalda solo SQLite, y la base configurada es '
                f'{config["ENGINE"]}. Aborto sin cambiar nada.'
            )

        origen_ruta = Path(config['NAME'])
        if not origen_ruta.exists():
            raise CommandError(f'No encuentro la base en {origen_ruta}. Aborto sin cambiar nada.')

        carpeta = Path(settings.BASE_DIR) / CARPETA_RESPALDOS
        carpeta.mkdir(exist_ok=True)
        marca = datetime.now().strftime('%Y%m%d-%H%M%S')
        destino_ruta = carpeta / f'db-antes-de-normalizar-unidad-{marca}.sqlite3'

        origen = sqlite3.connect(str(origen_ruta))
        destino = sqlite3.connect(str(destino_ruta))
        try:
            with destino:
                origen.backup(destino)
        finally:
            destino.close()
            origen.close()

        tamano = destino_ruta.stat().st_size / 1024 / 1024
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Respaldo creado: {destino_ruta}  ({tamano:.1f} MB)'
        ))
        return destino_ruta

    # ------------------------------------------------------------------
    def _conteo_final(self, validas):
        self.stdout.write('')
        self.stdout.write('Conteo final:')
        self._fila('Renglones de pedido', RenglonPedido.objects.count())
        self._fila('Con unidad válida', RenglonPedido.objects.filter(unidad__in=validas).count())
        self._fila('Con unidad sucia', RenglonPedido.objects.exclude(unidad__in=validas).count())

    # ------------------------------------------------------------------
    def _titulo(self, texto):
        self.stdout.write('')
        self.stdout.write('=' * ANCHO)
        self.stdout.write(f' {texto}')
        self.stdout.write('=' * ANCHO)

    def _fila(self, etiqueta, valor):
        self.stdout.write(f'    {etiqueta:<40} {valor:>8}')
