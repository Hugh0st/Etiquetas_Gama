from django.db import migrations


def corregir_fk_pedido(apps, schema_editor):
    """
    La migración 0006 cambió la primary key de Pedido de 'folio' a 'id', pero
    SQLite no reescribe por sí sola la restricción FOREIGN KEY de tablas que
    ya referenciaban la columna vieja: core_renglonpedido seguía apuntando a
    core_pedido(folio) en vez de core_pedido(id), lo que rompía la creación
    de cualquier pedido nuevo (IntegrityError al hacer commit).

    Un AlterField normal no lo corrige: el "remake" de tabla de SQLite se
    hace sobre el modelo tal como lo reconstruye el estado histórico de la
    migración, y esa reconstrucción aislada no vuelve a resolver bien la
    referencia contra la Pedido ya migrada. Para forzar la referencia
    correcta usamos el modelo real de la app (ya con su FK bien resuelta a
    Pedido.id) y le pedimos al editor de esquema que reconstruya la tabla.
    """
    from core.models import RenglonPedido
    schema_editor._remake_table(RenglonPedido)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_alter_pedido_options_pedido_id_alter_pedido_folio'),
    ]

    operations = [
        migrations.RunPython(corregir_fk_pedido, migrations.RunPython.noop),
    ]
