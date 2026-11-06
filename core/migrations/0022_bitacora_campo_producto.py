"""Generaliza la bitácora de descripciones a cualquier dato del producto.

CorreccionDescripcionProducto pasa a CorreccionCampoProducto, con un campo
`campo` que dice cuál se corrigió. La forma (un antes, un después) era idéntica
para la descripción y lo es para la unidad, y lo será para CAS y ONU si algún
día se corrigen igual. Mejor una tabla con tres filas ahora que dos tablas con
trescientas después.

Escrita a mano y no con makemigrations a propósito: el autodetector pregunta
"¿renombraste X?" de forma interactiva, y si se le contesta que no (o se corre
con --no-input) genera un borrar-y-crear que se llevaría las filas que ya hay.
RenameModel y RenameField conservan los datos.

Las filas existentes son todas de descripción, porque hasta ahora era lo único
que esta tabla registraba: se les pone campo='descripcion'.
"""
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_configuracion_rfc_empresa'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name='CorreccionDescripcionProducto',
            new_name='CorreccionCampoProducto',
        ),
        migrations.RenameField(
            model_name='correccioncampoproducto',
            old_name='descripcion_anterior',
            new_name='valor_anterior',
        ),
        migrations.RenameField(
            model_name='correccioncampoproducto',
            old_name='descripcion_nueva',
            new_name='valor_nuevo',
        ),
        # Las filas que ya existen son todas de descripción. preserve_default
        # en False para que el valor sea solo para ellas: de aquí en adelante
        # siempre lo escribe Producto._corregir_campo() explícitamente.
        migrations.AddField(
            model_name='correccioncampoproducto',
            name='campo',
            field=models.CharField(
                choices=[('descripcion', 'Descripción'), ('unidad', 'Unidad')],
                default='descripcion',
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='correccioncampoproducto',
            options={
                'ordering': ['-fecha'],
                'verbose_name': 'Corrección de dato del producto',
                'verbose_name_plural': 'Correcciones de datos del producto',
            },
        ),
        # El related_name decía "correcciones_descripcion", que con la tabla
        # generalizada sería mentira. No lo usa nadie en el código; es solo el
        # nombre del acceso inverso.
        migrations.AlterField(
            model_name='correccioncampoproducto',
            name='producto',
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name='correcciones_campo',
                to='core.producto',
            ),
        ),
        migrations.AlterField(
            model_name='correccioncampoproducto',
            name='pedido',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='correcciones_campo',
                to='core.pedido',
            ),
        ),
        migrations.AlterField(
            model_name='correccioncampoproducto',
            name='usuario',
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name='correcciones_campo',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # Los choices de la unidad del renglón no cambian la columna: son para
        # documentar y para que el formulario valide contra las dos opciones.
        # El max_length se queda en 20 a propósito (ver el comentario del
        # modelo): acortarlo truncaría las variantes heredadas del sistema
        # viejo antes de que el comando de normalización las limpie.
        migrations.AlterField(
            model_name='renglonpedido',
            name='unidad',
            field=models.CharField(
                blank=True,
                choices=[('KGS.', 'Kilogramos'), ('LTS.', 'Litros')],
                max_length=20,
            ),
        ),
    ]
