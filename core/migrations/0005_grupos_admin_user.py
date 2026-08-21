from django.apps import apps as apps_reales
from django.contrib.auth.management import create_permissions
from django.db import migrations

MODELOS_CATALOGO = ['cliente', 'producto', 'lineaespecificacion']


def crear_grupos(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    # Los permisos de los modelos de "core" normalmente los crea Django hasta
    # el final de todo el "migrate" (señal post_migrate). Los forzamos aquí
    # para poder asignarlos ya mismo.
    config_core = apps_reales.get_app_config('core')
    create_permissions(config_core, verbosity=0)

    grupo_admin, _ = Group.objects.get_or_create(name='admin')
    Group.objects.get_or_create(name='user')

    permisos_catalogo = Permission.objects.filter(
        content_type__app_label='core',
        content_type__model__in=MODELOS_CATALOGO,
    )
    grupo_admin.permissions.set(permisos_catalogo)


def eliminar_grupos(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=['admin', 'user']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_renglonpedido_cas_renglonpedido_onu'),
    ]

    operations = [
        migrations.RunPython(crear_grupos, eliminar_grupos),
    ]
