from django.db import migrations
from django.db.models import F


def sumar_barriles_a_paquetes(apps, schema_editor):
    RenglonPedido = apps.get_model('core', 'RenglonPedido')
    RenglonPedido.objects.update(paquetes=F('paquetes') + F('barriles'))


def revertir_suma(apps, schema_editor):
    # No se puede separar de nuevo cuánto era barriles y cuánto paquetes;
    # no hay nada que revertir aquí en sentido inverso.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_corregir_fk_renglonpedido_pedido'),
    ]

    operations = [
        migrations.RunPython(sumar_barriles_a_paquetes, revertir_suma),
        migrations.RemoveField(
            model_name='renglonpedido',
            name='barriles',
        ),
    ]
