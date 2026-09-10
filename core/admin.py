from django.contrib import admin

from .models import Cliente, LineaEspecificacion, Producto
from .permisos import es_admin

# El admin de Django es la pantalla "Catálogos". Django normalmente solo pide
# que el usuario tenga marcado "Staff status"; aquí además exigimos el rol
# admin. Así, aunque a alguien se le marque "Staff status" por error, si no
# está en el grupo "admin" no entra. Esta verificación corre en el servidor:
# no depende de que el enlace esté oculto en el menú.
admin.site.has_permission = lambda request: es_admin(request.user)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre_corto', 'razon_social', 'ciudad', 'estado', 'activo')
    search_fields = ('codigo', 'nombre_corto', 'razon_social')
    list_filter = ('activo', 'estado')


class LineaEspecificacionInline(admin.TabularInline):
    model = LineaEspecificacion
    extra = 0
    ordering = ('orden',)
    fields = ('orden', 'texto', 'es_continuacion', 'tipo_continuacion')


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('modelo', 'descripcion', 'unidad', 'cas', 'onu', 'activo')
    search_fields = ('modelo', 'descripcion')
    list_filter = ('activo', 'unidad')
    inlines = [LineaEspecificacionInline]
