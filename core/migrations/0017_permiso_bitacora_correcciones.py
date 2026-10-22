"""Le da al grupo "admin" permiso para consultar la bitácora de correcciones.

La migración 0005 fijó los permisos del grupo con .set() sobre los tres
modelos de catálogo que existían entonces, así que un admin que no sea
superusuario no vería el modelo nuevo en Catálogos. Aquí se le agrega, y solo
el permiso de ver: la bitácora es de solo lectura y el admin del modelo
tampoco deja agregar, editar ni borrar.
"""
from django.apps import apps as apps_reales
from django.contrib.auth.management import create_permissions
from django.db import migrations

MODELO = 'correcciondescripcionproducto'
PERMISO = f'view_{MODELO}'


def agregar_permiso(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    # Los permisos de los modelos de "core" normalmente los crea Django hasta
    # el final de todo el "migrate" (señal post_migrate). Los forzamos aquí
    # para poder asignarlos ya mismo, igual que en la migración 0005.
    create_permissions(apps_reales.get_app_config('core'), verbosity=0)

    grupo_admin = Group.objects.filter(name='admin').first()
    if grupo_admin is None:
        return

    permiso = Permission.objects.filter(
        content_type__app_label='core',
        content_type__model=MODELO,
        codename=PERMISO,
    ).first()
    if permiso is not None:
        grupo_admin.permissions.add(permiso)


def quitar_permiso(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    grupo_admin = Group.objects.filter(name='admin').first()
    if grupo_admin is None:
        return

    permiso = Permission.objects.filter(
        content_type__app_label='core',
        content_type__model=MODELO,
        codename=PERMISO,
    ).first()
    if permiso is not None:
        grupo_admin.permissions.remove(permiso)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_llenar_descripcion_renglones'),
    ]

    operations = [
        migrations.RunPython(agregar_permiso, quitar_permiso),
    ]
