from django import forms
from django.contrib import admin

from .models import (
    Cliente,
    CorreccionCampoProducto,
    CorreccionEspecificacionProducto,
    LineaEspecificacion,
    Producto,
    normalizar_descripcion,
)
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


class ProductoAdminForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = '__all__'

    def clean_descripcion(self):
        # Mismo criterio que en la captura del pedido, para que el catálogo no
        # termine con dos estilos de escritura según dónde se corrigió. El
        # modelo se toma de cleaned_data (Django limpia los campos en el orden
        # del modelo, y modelo va primero) y, si no validó, de la instancia.
        modelo = self.cleaned_data.get('modelo') or self.instance.modelo
        return normalizar_descripcion(self.cleaned_data['descripcion'], modelo)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    form = ProductoAdminForm
    list_display = ('modelo', 'descripcion', 'unidad', 'cas', 'onu', 'activo')
    search_fields = ('modelo', 'descripcion')
    list_filter = ('activo', 'unidad')
    inlines = [LineaEspecificacionInline]

    def save_model(self, request, obj, form, change):
        """Registra en la bitácora las correcciones hechas desde esta pantalla.

        Así hay un solo lugar donde rastrear de dónde salió un dato, sin
        importar si se corrigió aquí o desde la captura del pedido. Se compara
        contra lo que hay en la base y no contra form.changed_data, porque
        normalizar el texto puede marcar el campo como cambiado aunque el valor
        final sea el mismo.
        """
        if not change:
            super().save_model(request, obj, form, change)
            return

        campos = [c for c, _ in CorreccionCampoProducto.CAMPO_CHOICES]
        antes = Producto.objects.values(*campos).get(pk=obj.pk)
        super().save_model(request, obj, form, change)

        for campo in campos:
            nuevo = getattr(obj, campo)
            if antes[campo] == nuevo:
                continue
            CorreccionCampoProducto.objects.create(
                producto=obj,
                campo=campo,
                valor_anterior=antes[campo],
                valor_nuevo=nuevo,
                usuario=request.user,
                origen=CorreccionCampoProducto.ORIGEN_CATALOGO,
            )


@admin.register(CorreccionCampoProducto)
class CorreccionCampoProductoAdmin(admin.ModelAdmin):
    """Bitácora de las correcciones a un dato de un producto.

    Es de solo lectura: sirve para rastrear de dónde salió un dato, así que no
    se agrega, ni se edita, ni se borra desde aquí. Se escribe sola cuando
    alguien corrige una descripción o una unidad, desde el pedido o desde
    Catálogos.
    """
    list_display = (
        'fecha', 'producto', 'campo', 'valor_anterior', 'valor_nuevo',
        'usuario', 'procedencia',
    )
    list_filter = ('campo', 'origen', 'fecha', 'usuario')
    search_fields = ('producto__modelo', 'valor_anterior', 'valor_nuevo')
    date_hierarchy = 'fecha'
    list_select_related = ('producto', 'usuario', 'pedido')

    @admin.display(description='Se corrigió desde')
    def procedencia(self, obj):
        return obj.procedencia

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CorreccionEspecificacionProducto)
class CorreccionEspecificacionProductoAdmin(admin.ModelAdmin):
    """Bitácora de las ediciones a la especificación de un producto.

    De solo lectura, igual que la de descripciones: sirve para rastrear de
    dónde salió una línea, no para editarla. Se escribe sola cuando alguien
    corrige una especificación desde la captura de resultados.

    El antes y el después se guardan completos, así que desde aquí se puede
    reconstruir cómo estaba la especificación en cualquier momento.
    """
    list_display = (
        'fecha', 'producto', 'resumen', 'resultados_eliminados',
        'usuario', 'procedencia',
    )
    list_filter = ('origen', 'fecha', 'usuario')
    search_fields = ('producto__modelo',)
    date_hierarchy = 'fecha'
    list_select_related = ('producto', 'usuario', 'pedido')

    @admin.display(description='Cambio')
    def resumen(self, obj):
        return obj.resumen

    @admin.display(description='Se corrigió desde')
    def procedencia(self, obj):
        return obj.procedencia

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
