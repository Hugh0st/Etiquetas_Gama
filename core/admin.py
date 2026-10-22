from django import forms
from django.contrib import admin

from .models import (
    Cliente,
    CorreccionDescripcionProducto,
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

        Así hay un solo lugar donde rastrear de dónde salió una descripción,
        sin importar si se corrigió aquí o desde la captura del pedido. Se
        compara contra lo que hay en la base y no contra form.changed_data,
        porque normalizar el texto puede marcar el campo como cambiado aunque
        el valor final sea el mismo.
        """
        if not change:
            super().save_model(request, obj, form, change)
            return

        anterior = Producto.objects.values_list('descripcion', flat=True).get(pk=obj.pk)
        super().save_model(request, obj, form, change)
        if anterior != obj.descripcion:
            CorreccionDescripcionProducto.objects.create(
                producto=obj,
                descripcion_anterior=anterior,
                descripcion_nueva=obj.descripcion,
                usuario=request.user,
                origen=CorreccionDescripcionProducto.ORIGEN_CATALOGO,
            )


@admin.register(CorreccionDescripcionProducto)
class CorreccionDescripcionProductoAdmin(admin.ModelAdmin):
    """Bitácora de las correcciones a la descripción de un producto.

    Es de solo lectura: sirve para rastrear de dónde salió un nombre, así que
    no se agrega, ni se edita, ni se borra desde aquí. Se escribe sola cuando
    alguien corrige una descripción, desde el pedido o desde Catálogos.
    """
    list_display = (
        'fecha', 'producto', 'descripcion_anterior', 'descripcion_nueva',
        'usuario', 'procedencia',
    )
    list_filter = ('origen', 'fecha', 'usuario')
    search_fields = ('producto__modelo', 'descripcion_anterior', 'descripcion_nueva')
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
