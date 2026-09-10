"""Respalda la base de datos y conserva solo los respaldos más recientes.

Se ejecuta solo, todos los días, desde el Programador de tareas de Windows.

Por qué no es una copia normal del archivo:
    Si alguien está usando el sistema en ese momento, SQLite puede tener
    cambios a medio escribir. Copiar el archivo tal cual (copy, xcopy,
    Ctrl+C/Ctrl+V) puede dejar un respaldo corrupto que solo se descubre el
    día que lo necesitas. Aquí se usa la API de respaldo de SQLite, que lee la
    base página por página y produce una copia consistente aunque haya alguien
    trabajando.

Además, al terminar se verifica el respaldo recién hecho (integrity_check),
para no guardar un archivo que no sirva.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PREFIJO = 'respaldo-'
EXTENSION = '.db'
CONSERVAR_POR_DEFECTO = 30
ESPERA_SEGUNDOS = 60


class Command(BaseCommand):
    help = (
        'Copia la base de datos a la carpeta de respaldos con la fecha en el '
        'nombre, verifica que la copia sirva, y borra los respaldos más viejos.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--carpeta',
            default=None,
            help='Carpeta donde guardar. Por omisión, la de settings.CARPETA_RESPALDOS.',
        )
        parser.add_argument(
            '--conservar',
            type=int,
            default=CONSERVAR_POR_DEFECTO,
            help=f'Cuántos respaldos conservar (por omisión {CONSERVAR_POR_DEFECTO}).',
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opciones):
        inicio = datetime.now()
        origen = self._ruta_base_de_datos()
        carpeta = self._carpeta_destino(opciones['carpeta'])
        conservar = max(1, opciones['conservar'])

        destino = carpeta / f'{PREFIJO}{inicio.strftime("%Y-%m-%d")}{EXTENSION}'

        self.stdout.write(f'[{inicio:%Y-%m-%d %H:%M:%S}] Respaldando {origen}')

        self._respaldar(origen, destino)
        self._verificar(destino)

        tamano = destino.stat().st_size / 1024 / 1024
        self.stdout.write(self.style.SUCCESS(
            f'  OK  {destino.name}  ({tamano:.2f} MB)  ->  {carpeta}'
        ))

        self._rotar(carpeta, conservar)

    # ------------------------------------------------------------------
    def _ruta_base_de_datos(self):
        config = settings.DATABASES['default']
        if 'sqlite3' not in config['ENGINE']:
            raise CommandError(f'Este comando respalda solo SQLite (encontré {config["ENGINE"]}).')
        origen = Path(config['NAME'])
        if not origen.exists():
            raise CommandError(f'No encuentro la base de datos en {origen}.')
        return origen

    def _carpeta_destino(self, indicada):
        carpeta = Path(indicada) if indicada else Path(
            getattr(settings, 'CARPETA_RESPALDOS', settings.BASE_DIR / 'respaldos')
        )
        # Si la carpeta está en un disco/USB que no está conectado, avisamos
        # claro en vez de fallar con un error críptico.
        raiz = Path(carpeta.anchor)
        if raiz.parts and not raiz.exists():
            raise CommandError(
                f'La unidad {carpeta.anchor} no está disponible. '
                f'¿Está conectado el disco donde van los respaldos?'
            )
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise CommandError(f'No pude crear la carpeta {carpeta}: {error}')
        return carpeta

    def _respaldar(self, origen, destino):
        """Copia con la API de respaldo de SQLite (no es una copia de archivo).

        ESPERA_SEGUNDOS: si justo en ese instante alguien está guardando un
        pedido, SQLite tiene la base bloqueada un momento. En vez de rendirse
        al primer intento, esperamos: para un respaldo desatendido de
        madrugada es preferible tardar unos segundos a no tener respaldo.
        """
        conexion_origen = sqlite3.connect(str(origen), timeout=ESPERA_SEGUNDOS)
        conexion_destino = sqlite3.connect(str(destino), timeout=ESPERA_SEGUNDOS)
        try:
            with conexion_destino:
                conexion_origen.backup(conexion_destino)
        except sqlite3.OperationalError as error:
            raise CommandError(
                f'No pude respaldar porque la base estuvo ocupada más de '
                f'{ESPERA_SEGUNDOS} segundos ({error}). Vuelve a correr el '
                f'comando cuando nadie esté capturando, o programa el respaldo '
                f'a una hora sin gente.'
            )
        except sqlite3.Error as error:
            raise CommandError(f'Falló el respaldo: {error}')
        finally:
            conexion_destino.close()
            conexion_origen.close()

    def _verificar(self, destino):
        """Abre el respaldo recién hecho y confirma que no está corrupto."""
        conexion = sqlite3.connect(str(destino))
        try:
            resultado = conexion.execute('PRAGMA integrity_check').fetchone()[0]
            pedidos = conexion.execute('SELECT COUNT(*) FROM core_pedido').fetchone()[0]
            clientes = conexion.execute('SELECT COUNT(*) FROM core_cliente').fetchone()[0]
        except sqlite3.Error as error:
            raise CommandError(f'El respaldo quedó ilegible: {error}')
        finally:
            conexion.close()

        if resultado != 'ok':
            raise CommandError(f'El respaldo quedó corrupto (integrity_check = {resultado}).')

        self.stdout.write(f'  Verificado: integridad ok, {pedidos} pedidos, {clientes} clientes.')

    def _rotar(self, carpeta, conservar):
        """Deja solo los N respaldos más recientes."""
        respaldos = sorted(
            carpeta.glob(f'{PREFIJO}*{EXTENSION}'),
            key=lambda p: p.name,
            reverse=True,
        )
        sobrantes = respaldos[conservar:]
        for viejo in sobrantes:
            try:
                viejo.unlink()
                self.stdout.write(f'  Borrado por antigüedad: {viejo.name}')
            except OSError as error:
                self.stderr.write(f'  No pude borrar {viejo.name}: {error}')

        self.stdout.write(
            f'  Se conservan {min(len(respaldos), conservar)} respaldos '
            f'(máximo {conservar}).'
        )
