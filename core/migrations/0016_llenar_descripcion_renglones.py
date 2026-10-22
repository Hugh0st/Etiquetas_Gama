"""Llena la descripción de los renglones que ya existían.

RenglonPedido.descripcion se agregó cuando el sistema ya estaba en uso, así
que todos los renglones existentes quedaron en blanco. Se les copia la
descripción del catálogo.

Para un pedido ya emitido esto copia el valor ACTUAL del catálogo, aunque sea
un nombre mal importado del sistema viejo: es exactamente lo que ese pedido
imprimió en su momento, así que es lo fiel. De aquí en adelante cada renglón
lleva su propia descripción y un pedido emitido ya no cambia si alguien
corrige el catálogo después.
"""
from django.db import migrations


def llenar_descripcion(apps, schema_editor):
    RenglonPedido = apps.get_model('core', 'RenglonPedido')
    pendientes = []
    for renglon in RenglonPedido.objects.filter(descripcion='').select_related('producto').iterator():
        renglon.descripcion = renglon.producto.descripcion
        pendientes.append(renglon)
    RenglonPedido.objects.bulk_update(pendientes, ['descripcion'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_renglonpedido_descripcion_y_bitacora_correcciones'),
    ]

    operations = [
        # Sin reversa: vaciar el campo se llevaría también las descripciones
        # que los usuarios hayan corregido a mano después de esta migración.
        # Si hay que deshacer todo, 0015 elimina la columna completa.
        migrations.RunPython(llenar_descripcion, migrations.RunPython.noop),
    ]
