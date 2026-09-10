"""Borra los pedidos de prueba previos al arranque con datos reales.

Es una excepción de una sola vez: la interfaz nunca permite borrar un pedido
emitido (ver Pedido.delete y PedidoQuerySet.delete), y esa regla no cambia.
Esta limpieza se hace desde aquí, a mano, con respaldo previo y confirmación
escrita, porque es una tarea de mantenimiento y no una acción de uso diario.

Solo toca Pedido y lo que cuelga de él. Los catálogos (Cliente, Producto,
LineaEspecificacion), la Configuracion, los usuarios y los grupos no se tocan.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import models as django_models
from django.db import transaction

from core.models import (
    Cliente,
    Configuracion,
    LineaEspecificacion,
    Pedido,
    Producto,
    RenglonPedido,
    ResultadoLaboratorio,
)

PALABRA_CONFIRMACION = 'BORRAR'
CARPETA_RESPALDOS = 'respaldos'


class Command(BaseCommand):
    help = (
        'Borra todos los pedidos de prueba (Pedido, RenglonPedido y '
        'ResultadoLaboratorio), respaldando antes la base de datos. '
        'No toca catálogos, configuración, usuarios ni grupos.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra lo que haría, sin borrar nada ni generar respaldo.',
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opciones):
        simulacro = opciones['dry_run']

        conteos = {
            'Pedido': Pedido.objects.count(),
            'RenglonPedido': RenglonPedido.objects.count(),
            'ResultadoLaboratorio': ResultadoLaboratorio.objects.count(),
        }

        self._titulo('LIMPIEZA DE PEDIDOS DE PRUEBA' + (' (SIMULACRO)' if simulacro else ''))

        if conteos['Pedido'] == 0:
            self.stdout.write(self.style.WARNING('No hay pedidos que borrar. No se hizo nada.'))
            self._conteo_final()
            return

        self._mostrar_pedidos()
        self._mostrar_a_borrar(conteos)
        self._mostrar_intocables()

        if simulacro:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'SIMULACRO: no se borró nada ni se generó respaldo. '
                'Corre el comando sin --dry-run para hacerlo de verdad.'
            ))
            return

        if not self._confirmar():
            self.stdout.write(self.style.WARNING('\nCancelado. No se borró nada.'))
            return

        ruta_respaldo = self._respaldar()

        with transaction.atomic():
            # El delete() de PedidoQuerySet bloquea a propósito el borrado de
            # pedidos emitidos. Aquí se llama al delete() base de Django para
            # saltar esa protección: es la excepción documentada de esta
            # limpieza. El borrado en cascada se lleva RenglonPedido y
            # ResultadoLaboratorio.
            total, por_modelo = django_models.QuerySet.delete(Pedido.objects.all())

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Listo. Se borraron {total} registros:'))
        for etiqueta, cantidad in sorted(por_modelo.items()):
            self.stdout.write(f'    {etiqueta:<32} {cantidad:>6}')

        self._conteo_final()
        self.stdout.write('')
        self.stdout.write(f'Respaldo previo guardado en: {ruta_respaldo}')
        self.stdout.write(
            'El siguiente certificado que emitas arrancará en 0001 del mes en curso.'
        )

    # ------------------------------------------------------------------
    def _titulo(self, texto):
        self.stdout.write('')
        self.stdout.write('=' * 62)
        self.stdout.write(f' {texto}')
        self.stdout.write('=' * 62)

    def _mostrar_pedidos(self):
        self.stdout.write('')
        self.stdout.write('Pedidos que se van a borrar:')
        pedidos = (
            Pedido.objects.select_related('cliente')
            .annotate(
                n_renglones=django_models.Count('renglones', distinct=True),
                n_resultados=django_models.Count('renglones__resultados', distinct=True),
            )
            .order_by('id')
        )
        for p in pedidos:
            folio = p.folio or '(sin folio)'
            estado = 'cancelado' if p.cancelado else ('emitido' if p.emitido else 'borrador')
            cliente = p.cliente.razon_social or p.cliente.nombre_corto
            self.stdout.write(
                f'    id={p.id:<5} {folio:<12} {estado:<10} {cliente[:34]:<34} '
                f'{p.n_renglones} rengl. / {p.n_resultados} result.'
            )

    def _mostrar_a_borrar(self, conteos):
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('SE VAN A BORRAR:'))
        for etiqueta, cantidad in conteos.items():
            self.stdout.write(f'    {etiqueta:<32} {cantidad:>6}')
        self.stdout.write(f'    {"-" * 32} {"-" * 6}')
        self.stdout.write(f'    {"Total":<32} {sum(conteos.values()):>6}')

    def _mostrar_intocables(self):
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('NO SE TOCAN:'))
        for etiqueta, cantidad in self._conteos_intocables().items():
            self.stdout.write(f'    {etiqueta:<32} {cantidad:>6}')

    def _conteos_intocables(self):
        return {
            'Cliente': Cliente.objects.count(),
            'Producto': Producto.objects.count(),
            'LineaEspecificacion': LineaEspecificacion.objects.count(),
            '  de ellas, continuaciones': LineaEspecificacion.objects.filter(
                es_continuacion=True
            ).count(),
            'Configuracion': Configuracion.objects.count(),
            'Usuarios': User.objects.count(),
            'Grupos': Group.objects.count(),
        }

    # ------------------------------------------------------------------
    def _confirmar(self):
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Esta acción no se puede deshacer (queda el respaldo, eso sí).'
        ))
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
        tiempo.
        """
        config = settings.DATABASES['default']
        if 'sqlite3' not in config['ENGINE']:
            raise CommandError(
                f'Este comando respalda solo SQLite, y la base configurada es '
                f'{config["ENGINE"]}. Aborto sin borrar nada.'
            )

        origen_ruta = Path(config['NAME'])
        if not origen_ruta.exists():
            raise CommandError(f'No encuentro la base en {origen_ruta}. Aborto sin borrar nada.')

        carpeta = Path(settings.BASE_DIR) / CARPETA_RESPALDOS
        carpeta.mkdir(exist_ok=True)
        marca = datetime.now().strftime('%Y%m%d-%H%M%S')
        destino_ruta = carpeta / f'db-antes-de-limpiar-{marca}.sqlite3'

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
        self.stdout.write('')
        self.stdout.write('Conteo final de todas las tablas:')
        finales = {
            'Pedido': Pedido.objects.count(),
            'RenglonPedido': RenglonPedido.objects.count(),
            'ResultadoLaboratorio': ResultadoLaboratorio.objects.count(),
        }
        finales.update(self._conteos_intocables())
        for etiqueta, cantidad in finales.items():
            self.stdout.write(f'    {etiqueta:<32} {cantidad:>6}')
