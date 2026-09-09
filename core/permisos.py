"""Roles del sistema.

Hay dos roles, implementados como grupos de Django:

  - "admin": puede todo, incluidos catálogos, calibración y cancelar pedidos.
  - "user":  levanta pedidos y captura resultados.

Un superusuario de Django cuenta siempre como admin, sin necesidad de estar
en el grupo.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

GRUPO_ADMIN = 'admin'


def es_admin(user):
    """True si el usuario puede hacer las tareas reservadas al rol admin."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=GRUPO_ADMIN).exists()


def solo_admin(vista):
    """Restringe una vista al rol admin.

    La verificación vive aquí, en el servidor: aunque alguien escriba la URL a
    mano o le manden el enlace, si no es admin no pasa. Se usa junto con
    @login_required.
    """
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not es_admin(request.user):
            messages.error(
                request,
                'No tienes permiso para esta acción. Solo un usuario administrador puede hacerla.',
            )
            return redirect('pedido_list')
        return vista(request, *args, **kwargs)

    return envoltura
