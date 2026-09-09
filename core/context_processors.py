from .permisos import es_admin as _es_admin


def rol(request):
    """Deja `es_admin` disponible en todas las plantillas.

    Sirve para mostrar u ocultar acciones según el rol. Ojo: esto es solo
    presentación; el permiso de verdad se verifica en la vista.
    """
    return {'es_admin': _es_admin(request.user)} if hasattr(request, 'user') else {}
