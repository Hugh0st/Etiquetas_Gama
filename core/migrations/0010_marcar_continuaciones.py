import re

from django.db import migrations

# Continuaciones de temperatura tipo "A 25 C:" o "A 20øC" que no traen su
# propio valor (si trajeran valor, serían su propia característica).
PATRON_ARRANQUE = re.compile(r'^A\s+\d+')
PATRON_PURA = re.compile(r'^A\s+\d+O?\s*[^\dA-Za-z\s]{0,2}\s*[Cc]\s*[:;]?\s*$')


def marcar_continuaciones(apps, schema_editor):
    LineaEspecificacion = apps.get_model('core', 'LineaEspecificacion')
    for linea in LineaEspecificacion.objects.all().iterator():
        s = linea.texto.strip()
        if PATRON_ARRANQUE.match(s) and PATRON_PURA.match(s):
            linea.es_continuacion = True
            linea.save(update_fields=['es_continuacion'])


def desmarcar_continuaciones(apps, schema_editor):
    LineaEspecificacion = apps.get_model('core', 'LineaEspecificacion')
    for linea in LineaEspecificacion.objects.all().iterator():
        s = linea.texto.strip()
        if PATRON_ARRANQUE.match(s) and PATRON_PURA.match(s):
            linea.es_continuacion = False
            linea.save(update_fields=['es_continuacion'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_lineaespecificacion_es_continuacion'),
    ]

    operations = [
        migrations.RunPython(marcar_continuaciones, desmarcar_continuaciones),
    ]
