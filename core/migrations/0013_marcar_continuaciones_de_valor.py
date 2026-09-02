import re

from django.db import migrations

# Una continuación de VALOR: arranca con una corrida de 2+ espacios, trae
# texto después, y no tiene ninguna otra corrida de 2+ espacios (si la
# tuviera, sería su propio par nombre/valor indentado, no una continuación).
PATRON_INDENTADA = re.compile(r'^ {2,}(\S.*)$')
PATRON_OTRA_CORRIDA = re.compile(r' {2,}')

# De esas, dos sub-casos leen como continuación del NOMBRE del parámetro
# (mismo caso que "A 25 C:"), no del valor: un indicador de grados sin
# número propio, o una unidad de medida sola sin número propio.
PATRON_GRADOS = re.compile(r'^[oOºÂ°]{0,2}\s*[Cc]\s*[:;.]?$')
UNIDADES_CONOCIDAS = {
    'G/ML', 'MG/G', 'MG/ML', 'MG/L', 'G/L', 'G/CM3', 'G/CM³',
    'PPM', 'CP', 'CPS', 'CENTIPOISE', 'CENTIPOISES',
    '%', 'KG/M3', 'MOL/L', 'MEQ/G', 'MEQ/KG', 'UI/G',
}


def es_continuacion_de_valor(texto):
    m = PATRON_INDENTADA.match(texto)
    if not m:
        return False
    return not PATRON_OTRA_CORRIDA.search(m.group(1))


def clasificar_tipo(contenido):
    if PATRON_GRADOS.match(contenido):
        return 'parametros'
    if not re.search(r'\d', contenido):
        limpio = contenido.rstrip(':;.').strip().upper()
        if limpio in UNIDADES_CONOCIDAS:
            return 'parametros'
    return 'especificacion'


def marcar(apps, schema_editor):
    LineaEspecificacion = apps.get_model('core', 'LineaEspecificacion')
    for linea in LineaEspecificacion.objects.filter(es_continuacion=False).iterator():
        if not es_continuacion_de_valor(linea.texto):
            continue
        contenido = linea.texto.strip()
        linea.es_continuacion = True
        linea.tipo_continuacion = clasificar_tipo(contenido)
        linea.save(update_fields=['es_continuacion', 'tipo_continuacion'])


def desmarcar(apps, schema_editor):
    LineaEspecificacion = apps.get_model('core', 'LineaEspecificacion')
    for linea in LineaEspecificacion.objects.filter(es_continuacion=True).iterator():
        if es_continuacion_de_valor(linea.texto):
            linea.es_continuacion = False
            linea.tipo_continuacion = 'parametros'
            linea.save(update_fields=['es_continuacion', 'tipo_continuacion'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_lineaespecificacion_tipo_continuacion'),
    ]

    operations = [
        migrations.RunPython(marcar, desmarcar),
    ]
