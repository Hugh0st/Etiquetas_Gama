import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def estatico_versionado(ruta):
    """URL de un archivo estático con la fecha de modificación pegada al final.

    Sirve para que el navegador no siga mostrando una versión vieja guardada en
    caché: al cambiar el archivo cambia la URL, y el navegador lo vuelve a
    descargar solo, sin tener que recargar a la fuerza.
    """
    url = static(ruta)
    archivo = finders.find(ruta)
    if archivo and os.path.exists(archivo):
        return f'{url}?v={int(os.path.getmtime(archivo))}'
    return url
