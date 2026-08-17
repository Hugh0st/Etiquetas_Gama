import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Cliente, LineaEspecificacion, Producto


def leer_csv(ruta):
    """Lee un CSV probando utf-8 y cayendo a latin-1 si falla."""
    for encoding in ('utf-8', 'latin-1'):
        try:
            with open(ruta, encoding=encoding, newline='') as f:
                filas = list(csv.DictReader(f))
            return filas, encoding
        except UnicodeDecodeError:
            continue
    raise CommandError(f'No se pudo leer {ruta} ni con utf-8 ni con latin-1')


class Command(BaseCommand):
    help = (
        'Importa Clientes (CXC00001.csv), Productos (INV00001.csv) y '
        'Especificaciones (ESPEC.csv) desde la carpeta indicada. Es idempotente: '
        'volver a correrlo actualiza los registros existentes en vez de duplicarlos.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'carpeta',
            type=str,
            help='Carpeta que contiene CXC00001.csv, INV00001.csv y ESPEC.csv',
        )

    def handle(self, *args, **options):
        carpeta = Path(options['carpeta'])
        ruta_clientes = carpeta / 'CXC00001.csv'
        ruta_productos = carpeta / 'INV00001.csv'
        ruta_espec = carpeta / 'ESPEC.csv'

        for ruta in (ruta_clientes, ruta_productos, ruta_espec):
            if not ruta.exists():
                raise CommandError(f'No se encontró el archivo {ruta}')

        with transaction.atomic():
            resumen_clientes = self.importar_clientes(ruta_clientes)
            resumen_productos = self.importar_productos(ruta_productos)
            resumen_espec = self.importar_especificaciones(ruta_espec)

        self.imprimir_resumen(resumen_clientes, resumen_productos, resumen_espec)

    # ------------------------------------------------------------------
    # Clientes
    # ------------------------------------------------------------------
    def importar_clientes(self, ruta):
        filas, encoding = leer_csv(ruta)

        conteo = {}
        for fila in filas:
            codigo = fila['CODIGO']
            conteo[codigo] = conteo.get(codigo, 0) + 1
        duplicados = sorted(codigo for codigo, n in conteo.items() if n > 1)

        creados = 0
        actualizados = 0
        omitidos = 0

        for fila in filas:
            codigo = fila['CODIGO']
            if codigo in duplicados:
                omitidos += 1
                continue

            valores = dict(
                nombre_corto=fila.get('NOMCTO', ''),
                razon_social=fila.get('NOMBRE', ''),
                direccion=fila.get('DIREC', ''),
                numero_exterior=fila.get('NOEXT', ''),
                numero_interior=fila.get('NOINT', ''),
                colonia=fila.get('DELEGA', ''),
                municipio=fila.get('MUNICIPIO', ''),
                ciudad=fila.get('CIUDAD', ''),
                estado=fila.get('ESTADO', ''),
                pais=fila.get('PAIS', ''),
                cp=fila.get('CP', ''),
                rfc=fila.get('RFC', ''),
                tel1=fila.get('TEL1', ''),
                tel2=fila.get('TEL2', ''),
                email=fila.get('EMAIL', ''),
            )

            obj, created = Cliente.objects.get_or_create(codigo=codigo, defaults=valores)
            if created:
                creados += 1
            else:
                for campo, valor in valores.items():
                    setattr(obj, campo, valor)
                obj.save()
                actualizados += 1

        return {
            'archivo': ruta.name,
            'encoding': encoding,
            'filas': len(filas),
            'creados': creados,
            'actualizados': actualizados,
            'omitidos_por_duplicado': omitidos,
            'duplicados': duplicados,
        }

    # ------------------------------------------------------------------
    # Productos
    # ------------------------------------------------------------------
    def importar_productos(self, ruta):
        filas, encoding = leer_csv(ruta)

        conteo = {}
        for fila in filas:
            modelo = fila['MODELO']
            conteo[modelo] = conteo.get(modelo, 0) + 1
        duplicados = sorted(modelo for modelo, n in conteo.items() if n > 1)

        creados = 0
        actualizados = 0
        omitidos = 0

        for fila in filas:
            modelo = fila['MODELO']
            if modelo in duplicados:
                omitidos += 1
                continue

            valores = dict(
                descripcion=fila.get('DESCRI', ''),
                unidad=fila.get('UNIDAD', ''),
                cas=fila.get('CAS', ''),
                onu=fila.get('ONU', ''),
            )

            obj, created = Producto.objects.get_or_create(modelo=modelo, defaults=valores)
            if created:
                creados += 1
            else:
                for campo, valor in valores.items():
                    setattr(obj, campo, valor)
                obj.save()
                actualizados += 1

        return {
            'archivo': ruta.name,
            'encoding': encoding,
            'filas': len(filas),
            'creados': creados,
            'actualizados': actualizados,
            'omitidos_por_duplicado': omitidos,
            'duplicados': duplicados,
        }

    # ------------------------------------------------------------------
    # Especificaciones
    # ------------------------------------------------------------------
    def importar_especificaciones(self, ruta):
        filas, encoding = leer_csv(ruta)

        modelos_validos = set(Producto.objects.values_list('pk', flat=True))

        lineas_por_modelo = {}
        huerfanos = set()
        lineas_huerfanas = 0

        for fila in filas:
            modelo = fila['MODELO']
            texto = fila['PASO']
            if modelo not in modelos_validos:
                huerfanos.add(modelo)
                lineas_huerfanas += 1
                continue
            lineas_por_modelo.setdefault(modelo, []).append(texto)

        lineas_importadas = 0
        for modelo, textos in lineas_por_modelo.items():
            producto = Producto.objects.get(pk=modelo)
            # Se reemplaza el bloque completo para reflejar exactamente el
            # orden y contenido actual del CSV en cada corrida.
            LineaEspecificacion.objects.filter(producto=producto).delete()
            objetos = [
                LineaEspecificacion(producto=producto, orden=i, texto=texto)
                for i, texto in enumerate(textos, start=1)
            ]
            LineaEspecificacion.objects.bulk_create(objetos)
            lineas_importadas += len(objetos)

        return {
            'archivo': ruta.name,
            'encoding': encoding,
            'filas': len(filas),
            'modelos_con_especificacion': len(lineas_por_modelo),
            'lineas_importadas': lineas_importadas,
            'huerfanos': sorted(huerfanos),
            'lineas_huerfanas': lineas_huerfanas,
        }

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------
    def imprimir_resumen(self, clientes, productos, espec):
        w = self.stdout.write

        w('')
        w(self.style.MIGRATE_HEADING('== Clientes (%s, encoding=%s) ==' % (clientes['archivo'], clientes['encoding'])))
        w(f"  Filas leídas:        {clientes['filas']}")
        w(f"  Creados:             {clientes['creados']}")
        w(f"  Actualizados:        {clientes['actualizados']}")
        w(f"  Omitidos (dup.):     {clientes['omitidos_por_duplicado']}")
        if clientes['duplicados']:
            w(self.style.WARNING(f"  CODIGO duplicado ({len(clientes['duplicados'])}): {', '.join(clientes['duplicados'])}"))
        else:
            w('  Sin CODIGO duplicados.')

        w('')
        w(self.style.MIGRATE_HEADING('== Productos (%s, encoding=%s) ==' % (productos['archivo'], productos['encoding'])))
        w(f"  Filas leídas:        {productos['filas']}")
        w(f"  Creados:             {productos['creados']}")
        w(f"  Actualizados:        {productos['actualizados']}")
        w(f"  Omitidos (dup.):     {productos['omitidos_por_duplicado']}")
        if productos['duplicados']:
            w(self.style.WARNING(f"  MODELO duplicado ({len(productos['duplicados'])}): {', '.join(productos['duplicados'])}"))
        else:
            w('  Sin MODELO duplicados.')

        w('')
        w(self.style.MIGRATE_HEADING('== Especificaciones (%s, encoding=%s) ==' % (espec['archivo'], espec['encoding'])))
        w(f"  Filas leídas:            {espec['filas']}")
        w(f"  Líneas importadas:       {espec['lineas_importadas']}")
        w(f"  Modelos con especif.:    {espec['modelos_con_especificacion']}")
        w(f"  Líneas huérfanas:        {espec['lineas_huerfanas']}")
        if espec['huerfanos']:
            w(self.style.WARNING(f"  MODELO sin producto ({len(espec['huerfanos'])}): {', '.join(espec['huerfanos'])}"))
        else:
            w('  Sin modelos huérfanos.')

        w('')
        w(self.style.SUCCESS('Importación terminada.'))
