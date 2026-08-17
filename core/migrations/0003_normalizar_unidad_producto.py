from django.db import migrations

# Mapea las variantes sucias del sistema anterior a los dos valores válidos.
NORMALIZACION = {
    'KGS.': 'KGS.',
    'KGS': 'KGS.',
    'KGM': 'KGS.',
    'KGM.': 'KGS.',
    'LTR.': 'LTS.',
    'LTR': 'LTS.',
    'LTS.': 'LTS.',
}


def normalizar_y_limpiar(apps, schema_editor):
    Producto = apps.get_model('core', 'Producto')

    h87 = Producto.objects.filter(unidad='H87')
    print('\nEliminando productos con unidad H87:')
    for p in h87:
        print(f'  modelo={p.pk!r} descripcion={p.descripcion!r}')
    h87.delete()

    for origen, destino in NORMALIZACION.items():
        if origen == destino:
            continue
        Producto.objects.filter(unidad=origen).update(unidad=destino)


def sin_reversa(apps, schema_editor):
    raise migrations.exceptions.IrreversibleError(
        'Esta migración normaliza y elimina datos; no se puede revertir automáticamente.'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_producto_unidad'),
    ]

    operations = [
        migrations.RunPython(normalizar_y_limpiar, sin_reversa),
    ]
