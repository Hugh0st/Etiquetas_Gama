"""Marca las líneas de especificación que son continuación visual de la anterior.

Por qué hace falta un comando y no basta con las migraciones 0010 y 0013:
    esas migraciones traen exactamente esta lógica, pero corrieron antes de que
    el catálogo se importara con importar_csv, así que no tuvieron efecto sobre
    los datos actuales. Hoy no hay una sola línea marcada, y por eso el
    certificado parte 'A  25 C:' en PARAMETRO='A' / ESPECIFICACION='25 C:' y le
    pone su propia casilla de resultado.

Volver a correr una migración de datos ya aplicada no es una opción razonable,
y tampoco conviene: esto hay que poder revisarlo con --dry-run, aplicarlo con
respaldo y confirmación, y poder repetirlo si mañana se importa más catálogo.

Es idempotente y respeta el trabajo manual: solo mira las líneas que hoy NO
están marcadas, así que nunca pisa una marca puesta a mano.

No toca el texto de ninguna línea, ni los pedidos, ni los resultados. Solo los
campos es_continuacion y tipo_continuacion de LineaEspecificacion.
"""
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.continuaciones import (
    CRITERIO_NOMBRE,
    CRITERIO_VALOR,
    TIPO_ESPECIFICACION,
    TIPO_PARAMETROS,
    clasificar,
)
from core.models import LineaEspecificacion

PALABRA_CONFIRMACION = 'MARCAR'
CARPETA_RESPALDOS = 'respaldos'
MUESTRA_POR_DEFECTO = 40
ANCHO = 74

# Cómo se describe cada criterio al reportar.
CRITERIOS = [
    (
        CRITERIO_NOMBRE,
        'CRITERIO A — continuación del NOMBRE del parámetro',
        'Arranca con "A <número>" y ahí se acaba, sin valor propio: "A  25 C:".\n'
        '  Misma lógica que la migración 0010. Siempre queda como "parametros".',
    ),
    (
        CRITERIO_VALOR,
        'CRITERIO B — continuación del VALOR de la línea anterior',
        'Arranca indentada con 2+ espacios, trae texto, y no tiene otra corrida\n'
        '  de 2+ espacios. Misma lógica que la migración 0013. El tipo se deduce:\n'
        '  grados o unidad suelta van a "parametros", el resto a "especificacion".',
    ),
]


class Command(BaseCommand):
    help = (
        'Marca como continuación las líneas de especificación que lo son, '
        'deduciéndolo del texto. Con --dry-run solo muestra lo que haría. '
        'Al aplicar, respalda la base y pide confirmación escrita.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra lo que haría, sin marcar nada ni generar respaldo.',
        )
        parser.add_argument(
            '--muestra',
            type=int,
            default=MUESTRA_POR_DEFECTO,
            help=f'Cuántos ejemplos mostrar de cada criterio (por omisión {MUESTRA_POR_DEFECTO}).',
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opciones):
        simulacro = opciones['dry_run']
        tamano_muestra = max(0, opciones['muestra'])

        self._titulo(
            'MARCADO DE CONTINUACIONES DE ESPECIFICACIÓN'
            + (' (SIMULACRO)' if simulacro else '')
        )

        self._estado_actual()

        candidatas, anteriores = self._analizar()

        if not candidatas:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'No hay ninguna línea sin marcar que cumpla los criterios. '
                'No hay nada que hacer.'
            ))
            return

        for criterio, titulo, explicacion in CRITERIOS:
            self._mostrar_criterio(
                criterio, titulo, explicacion, candidatas, anteriores, tamano_muestra,
            )

        self._mostrar_resumen(candidatas)

        if simulacro:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'SIMULACRO: no se marcó nada ni se generó respaldo. '
                'Corre el comando sin --dry-run para aplicarlo.'
            ))
            return

        if not self._confirmar(len(candidatas)):
            self.stdout.write(self.style.WARNING('\nCancelado. No se marcó nada.'))
            return

        ruta_respaldo = self._respaldar()
        self._aplicar(candidatas)

        self._conteo_final()
        self.stdout.write('')
        self.stdout.write(f'Respaldo previo guardado en: {ruta_respaldo}')

    # ------------------------------------------------------------------
    def _analizar(self):
        """Clasifica las líneas no marcadas y arma el índice de la línea anterior.

        Devuelve (candidatas, anteriores):
          candidatas  lista de (linea, tipo, criterio) de las que hay que marcar
          anteriores  {id de línea: texto de la línea de arriba del mismo producto}

        Las 8146 líneas del catálogo caben de sobra en memoria, así que se
        cargan de una vez en lugar de ir a la base por cada línea anterior.
        """
        todas = list(LineaEspecificacion.objects.all().order_by('producto', 'orden'))

        por_producto = defaultdict(dict)
        for linea in todas:
            por_producto[linea.producto_id][linea.orden] = linea.texto

        candidatas = []
        anteriores = {}
        for linea in todas:
            # Solo las que hoy no están marcadas: si alguien ya corrigió a
            # mano, su marca manda y no se toca.
            if linea.es_continuacion:
                continue

            es_continuacion, tipo, criterio = clasificar(linea.texto)
            if not es_continuacion:
                continue

            candidatas.append((linea, tipo, criterio))
            hermanas = por_producto[linea.producto_id]
            previas = [o for o in hermanas if o < linea.orden]
            anteriores[linea.id] = hermanas[max(previas)] if previas else None

        return candidatas, anteriores

    # ------------------------------------------------------------------
    def _estado_actual(self):
        total = LineaEspecificacion.objects.count()
        marcadas = LineaEspecificacion.objects.filter(es_continuacion=True)
        self.stdout.write('')
        self.stdout.write('Estado actual del catálogo:')
        self._fila('Líneas de especificación', total)
        self._fila('Productos con especificación', len(
            set(LineaEspecificacion.objects.values_list('producto_id', flat=True))
        ))
        self._fila('Ya marcadas como continuación', marcadas.count())
        self._fila('  de tipo parametros', marcadas.filter(tipo_continuacion=TIPO_PARAMETROS).count())
        self._fila('  de tipo especificacion', marcadas.filter(tipo_continuacion=TIPO_ESPECIFICACION).count())

    def _mostrar_criterio(self, criterio, titulo, explicacion, candidatas, anteriores, tamano_muestra):
        propias = [(l, t) for l, t, c in candidatas if c == criterio]

        self.stdout.write('')
        self.stdout.write('-' * ANCHO)
        self.stdout.write(self.style.MIGRATE_HEADING(titulo))
        self.stdout.write(f'  {explicacion}')
        self.stdout.write('-' * ANCHO)

        if not propias:
            self.stdout.write('  Ninguna línea entra por este criterio.')
            return

        por_tipo = Counter(tipo for _, tipo in propias)
        self.stdout.write(f'  Líneas que se marcarían: {len(propias)}')
        for tipo in (TIPO_PARAMETROS, TIPO_ESPECIFICACION):
            if por_tipo.get(tipo):
                self.stdout.write(f'      tipo_continuacion = {tipo:<16} {por_tipo[tipo]:>6}')
        productos = len({linea.producto_id for linea, _ in propias})
        self.stdout.write(f'  Productos afectados: {productos}')

        if not tamano_muestra:
            return

        self.stdout.write('')
        self.stdout.write(f'  Muestra de {min(tamano_muestra, len(propias))} '
                          f'(de {len(propias)}), con repr() para ver la indentación real:')
        for linea, tipo in propias[:tamano_muestra]:
            anterior = anteriores.get(linea.id)
            self.stdout.write('')
            self.stdout.write(f'    {linea.producto_id} [orden {linea.orden}]  -> {tipo}')
            if anterior is None:
                self.stdout.write(self.style.WARNING(
                    '      anterior: (ninguna, es la primera línea del producto)'
                ))
            else:
                self.stdout.write(f'      anterior: {self._recortar(anterior)}')
            self.stdout.write(f'      ESTA:     {self._recortar(linea.texto)}')

    def _mostrar_resumen(self, candidatas):
        por_tipo = Counter(tipo for _, tipo, _ in candidatas)
        por_criterio = Counter(criterio for _, _, criterio in candidatas)
        total_lineas = LineaEspecificacion.objects.count()

        self.stdout.write('')
        self.stdout.write('=' * ANCHO)
        self.stdout.write(self.style.WARNING('SE VAN A MARCAR:'))
        self._fila('Por criterio A (nombre)', por_criterio.get(CRITERIO_NOMBRE, 0))
        self._fila('Por criterio B (valor)', por_criterio.get(CRITERIO_VALOR, 0))
        self._fila('-' * 36, '-' * 6)
        self._fila('Total', len(candidatas))
        self.stdout.write('')
        self._fila('Quedarían con tipo parametros', por_tipo.get(TIPO_PARAMETROS, 0))
        self._fila('Quedarían con tipo especificacion', por_tipo.get(TIPO_ESPECIFICACION, 0))
        self.stdout.write('')
        porcentaje = len(candidatas) * 100 // total_lineas if total_lineas else 0
        self._fila(f'Sobre un total de {total_lineas} líneas', f'{porcentaje}%')
        self._fila('Productos afectados', len({l.producto_id for l, _, _ in candidatas}))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('NO SE TOCA:'))
        self.stdout.write('    El texto de las líneas, los pedidos, los renglones, los')
        self.stdout.write('    resultados de laboratorio, ni las líneas ya marcadas a mano.')

    # ------------------------------------------------------------------
    def _aplicar(self, candidatas):
        with transaction.atomic():
            for linea, tipo, _ in candidatas:
                linea.es_continuacion = True
                linea.tipo_continuacion = tipo
            LineaEspecificacion.objects.bulk_update(
                [linea for linea, _, _ in candidatas],
                ['es_continuacion', 'tipo_continuacion'],
                batch_size=500,
            )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Listo. Se marcaron {len(candidatas)} líneas como continuación.'
        ))

    # ------------------------------------------------------------------
    def _confirmar(self, cuantas):
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            f'Se van a modificar {cuantas} líneas del catálogo. Esto cambia cómo se '
            f'imprimen los certificados de todos los pedidos que se emitan de aquí '
            f'en adelante.'
        ))
        self.stdout.write(
            'Los pedidos YA emitidos no cambian: su especificación quedó congelada '
            'en especificacion_snapshot al emitirlos.'
        )
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
                f'{config["ENGINE"]}. Aborto sin marcar nada.'
            )

        origen_ruta = Path(config['NAME'])
        if not origen_ruta.exists():
            raise CommandError(f'No encuentro la base en {origen_ruta}. Aborto sin marcar nada.')

        carpeta = Path(settings.BASE_DIR) / CARPETA_RESPALDOS
        carpeta.mkdir(exist_ok=True)
        marca = datetime.now().strftime('%Y%m%d-%H%M%S')
        destino_ruta = carpeta / f'db-antes-de-marcar-continuaciones-{marca}.sqlite3'

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
    def _conteo_final(self):
        total = LineaEspecificacion.objects.count()
        marcadas = LineaEspecificacion.objects.filter(es_continuacion=True)
        self.stdout.write('')
        self.stdout.write('Conteo final:')
        self._fila('Líneas de especificación', total)
        self._fila('Marcadas como continuación', marcadas.count())
        self._fila('  de tipo parametros', marcadas.filter(tipo_continuacion=TIPO_PARAMETROS).count())
        self._fila('  de tipo especificacion', marcadas.filter(tipo_continuacion=TIPO_ESPECIFICACION).count())
        self._fila('Sin marcar', LineaEspecificacion.objects.filter(es_continuacion=False).count())

    # ------------------------------------------------------------------
    def _titulo(self, texto):
        self.stdout.write('')
        self.stdout.write('=' * ANCHO)
        self.stdout.write(f' {texto}')
        self.stdout.write('=' * ANCHO)

    def _fila(self, etiqueta, valor):
        self.stdout.write(f'    {etiqueta:<36} {valor:>6}')

    @staticmethod
    def _recortar(texto, limite=110):
        """repr() para ver la indentación real, recortado si es larguísimo."""
        bruto = repr(texto)
        if len(bruto) <= limite:
            return bruto
        return bruto[:limite] + '…(recortado)'
