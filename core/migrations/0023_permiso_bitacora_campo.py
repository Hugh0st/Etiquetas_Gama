"""Reotorga al grupo "admin" el permiso de ver la bitácora, ya renombrada.

Renombrar el modelo cambia el codename del permiso: el que la migración 0017 le
dio al grupo era `view_correcciondescripcionproducto`, y ahora el modelo genera
`view_correccioncampoproducto`. Django no mueve los permisos al renombrar, así
que sin esto un admin que no sea superusuario dejaría de ver la bitácora en
Catálogos.

De paso se quita el permiso viejo del grupo. La fila en auth_permission queda
huérfana —Django tampoco la borra sola— pero al menos no sigue asignada a
nadie, para que no aparezca en la pantalla de permisos del usuario.

Mismo patrón que las migraciones 0017 y 0020.
"""
from django.apps import apps as apps_reales
from django.contrib.auth.management import create_permissions
from django.db import migrations

MODELO_NUEVO = 'correccioncampoproducto'
MODELO_VIEJO = 'correcciondescripcionproducto'


def _permiso(apps, modelo):
    Permission = apps.get_model('auth', 'Permission')
    # Los permisos de "core" normalmente se crean hasta el final de todo el
    # migrate (señal post_migrate). Se fuerzan aquí para poder asignarlos ya
    # mismo, igual que en las migraciones 0005, 0017 y 0020.
    create_permissions(apps_reales.get_app_config('core'), verbosity=0)
    return Permission.objects.filter(
        content_type__app_label='core',
        content_type__model=modelo,
        codename=f'view_{modelo}',
    ).first()


def mover_permiso(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    grupo_admin = Group.objects.filter(name='admin').first()
    if grupo_admin is None:
        return

    nuevo = _permiso(apps, MODELO_NUEVO)
    if nuevo is not None:
        grupo_admin.permissions.add(nuevo)

    viejo = _permiso(apps, MODELO_VIEJO)
    if viejo is not None:
        grupo_admin.permissions.remove(viejo)


def devolver_permiso(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    grupo_admin = Group.objects.filter(name='admin').first()
    if grupo_admin is None:
        return

    viejo = _permiso(apps, MODELO_VIEJO)
    if viejo is not None:
        grupo_admin.permissions.add(viejo)

    nuevo = _permiso(apps, MODELO_NUEVO)
    if nuevo is not None:
        grupo_admin.permissions.remove(nuevo)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_bitacora_campo_producto'),
    ]

    operations = [
        migrations.RunPython(mover_permiso, devolver_permiso),
    ]
