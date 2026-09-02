import re

from django.db import migrations

# ø (0xf8) y ¦ (0xa6) son el símbolo de grados corrupto por la codificación
# del sistema viejo; § (0xa7) también se usó con el mismo sentido en varias
# líneas. Los tres se normalizan al símbolo real de grados.
PATRON_CORRUPTOS = re.compile(r'[\xf8\xa7\xa6]')


def normalizar(apps, schema_editor):
    LineaEspecificacion = apps.get_model('core', 'LineaEspecificacion')
    for linea in LineaEspecificacion.objects.all().iterator():
        if PATRON_CORRUPTOS.search(linea.texto):
            linea.texto = PATRON_CORRUPTOS.sub('\xb0', linea.texto)
            linea.save(update_fields=['texto'])


def sin_reversa(apps, schema_editor):
    raise migrations.exceptions.IrreversibleError(
        'No se puede saber cuál de los 3 caracteres originales (ø, § o ¦) '
        'tenía cada línea una vez normalizados a °.'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_marcar_continuaciones'),
    ]

    operations = [
        migrations.RunPython(normalizar, sin_reversa),
    ]
