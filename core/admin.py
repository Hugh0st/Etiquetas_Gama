from django.contrib import admin

from .models import Cliente, LineaEspecificacion, Producto


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre_corto', 'razon_social', 'ciudad', 'estado', 'activo')
    search_fields = ('codigo', 'nombre_corto', 'razon_social')
    list_filter = ('activo', 'estado')


class LineaEspecificacionInline(admin.TabularInline):
    model = LineaEspecificacion
    extra = 0
    ordering = ('orden',)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('modelo', 'descripcion', 'unidad', 'cas', 'onu', 'activo')
    search_fields = ('modelo', 'descripcion')
    list_filter = ('activo', 'unidad')
    inlines = [LineaEspecificacionInline]
