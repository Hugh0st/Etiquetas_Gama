"""Le da al grupo "admin" permiso para consultar la bitácora de especificaciones.

Misma situación que la migración 0017: la 0005 fijó los permisos del grupo con
.set() sobre los modelos de catálogo que existían entonces, así que un admin
que no sea superusuario no vería el modelo nuevo en Catálogos. Se agrega solo
el permiso de ver: la bitácora es de solo lectura y su admin tampoco deja
agregar, editar ni borrar.
"""
from django.apps import apps as apps_reales
from django.contrib.auth.management import create_permissions
from django.db import migrations

MODELO = 'correccionespecificacionproducto'
PERMISO = f'view_{MODELO}'


def _permiso(apps):
    Permission = apps.get_model('auth', 'Permission')
    # Los permisos de "core" normalmente se crean hasta el final de todo el
    # migrate (señal post_migrate). Se fuerzan aquí para poder asignarlos ya
    # mismo, igual que en las migraciones 0005 y 0017.
    create_permissions(apps_reales.get_app_config('core'), verbosity=0)
    return Permission.objects.filter(
        content_type__app_label='core',
        content_type__model=MODELO,
        codename=PERMISO,
    ).first()


def agregar_permiso(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    grupo_admin = Group.objects.filter(name='admin').first()
    permiso = _permiso(apps)
    if grupo_admin is not None and permiso is not None:
        grupo_admin.permissions.add(permiso)


def quitar_permiso(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    grupo_admin = Group.objects.filter(name='admin').first()
    permiso = _permiso(apps)
    if grupo_admin is not None and permiso is not None:
        grupo_admin.permissions.remove(permiso)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_atar_resultados_a_su_linea'),
    ]

    operations = [
        migrations.RunPython(agregar_permiso, quitar_permiso),
    ]
