from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .etiquetas import generar_pdf_calibracion, generar_pdf_etiquetas
from .forms import ConfiguracionForm, PedidoForm, RenglonPedidoFormSet
from .models import Cliente, Configuracion, Pedido, PedidoSinResultados, Producto, ResultadoLaboratorio

LIMITE_BUSQUEDA = 20
POSICIONES_VALIDAS = {1, 2, 3}


def es_admin(user):
    return user.is_superuser or user.groups.filter(name='admin').exists()


def _pedidos_con_conteos(queryset):
    return queryset.annotate(
        num_renglones=Count('renglones', distinct=True),
        num_resultados=Count(
            'renglones__resultados',
            filter=~Q(renglones__resultados__texto=''),
            distinct=True,
        ),
    )


@login_required
def pedido_list(request):
    pedidos = _pedidos_con_conteos(Pedido.objects.select_related('cliente'))

    estado = request.GET.get('estado', '')
    if estado == 'borrador':
        pedidos = pedidos.filter(emitido=False, num_resultados=0)
    elif estado == 'con_resultados':
        pedidos = pedidos.filter(emitido=False, num_resultados__gt=0)
    elif estado == 'emitido':
        pedidos = pedidos.filter(emitido=True)

    q = request.GET.get('q', '').strip()
    if q:
        pedidos = pedidos.filter(
            Q(folio__icontains=q)
            | Q(cliente__nombre_corto__icontains=q)
            | Q(cliente__razon_social__icontains=q)
        )

    return render(request, 'core/pedido_list.html', {
        'pedidos': pedidos,
        'estado': estado,
        'q': q,
    })


@login_required
def pedido_create(request):
    if request.method == 'POST':
        form = PedidoForm(request.POST)
        formset = RenglonPedidoFormSet(request.POST, instance=Pedido())
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                pedido = form.save(commit=False)
                pedido.usuario_creador = request.user
                pedido.save()
                formset.instance = pedido
                formset.save()
            messages.success(request, 'Pedido creado.')
            return redirect('pedido_detail', pk=pedido.pk)
    else:
        form = PedidoForm()
        formset = RenglonPedidoFormSet(instance=Pedido())

    return render(request, 'core/pedido_form.html', {
        'form': form,
        'formset': formset,
        'pedido': None,
    })


@login_required
def pedido_edit(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    if pedido.emitido:
        messages.info(request, 'Este pedido ya fue emitido y no se puede editar.')
        return redirect('pedido_detail', pk=pedido.pk)

    if request.method == 'POST':
        form = PedidoForm(request.POST, instance=pedido)
        formset = RenglonPedidoFormSet(request.POST, instance=pedido)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, 'Pedido actualizado.')
            return redirect('pedido_detail', pk=pedido.pk)
    else:
        form = PedidoForm(instance=pedido)
        formset = RenglonPedidoFormSet(instance=pedido)

    return render(request, 'core/pedido_form.html', {
        'form': form,
        'formset': formset,
        'pedido': pedido,
    })


@login_required
def pedido_detail(request, pk):
    pedido = get_object_or_404(
        _pedidos_con_conteos(Pedido.objects.select_related('cliente', 'usuario_creador')),
        pk=pk,
    )
    renglones = pedido.renglones.select_related('producto')
    return render(request, 'core/pedido_detail.html', {
        'pedido': pedido,
        'renglones': renglones,
    })


@login_required
def pedido_resultados(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related('cliente'), pk=pk)
    renglones = list(
        pedido.renglones.select_related('producto')
        .prefetch_related('producto__especificacion', 'resultados')
    )

    if request.method == 'POST':
        if pedido.emitido:
            messages.info(request, 'Este pedido ya fue emitido; los resultados no se pueden modificar.')
            return redirect('pedido_detail', pk=pedido.pk)

        with transaction.atomic():
            for renglon in renglones:
                for linea in renglon.producto.especificacion.all():
                    campo = f'resultado-{renglon.id}-{linea.orden}'
                    texto = request.POST.get(campo, '').strip()
                    ResultadoLaboratorio.objects.update_or_create(
                        renglon=renglon, orden=linea.orden,
                        defaults={'texto': texto},
                    )
        messages.success(request, 'Resultados guardados.')
        return redirect('pedido_resultados', pk=pedido.pk)

    for renglon in renglones:
        existentes = {r.orden: r.texto for r in renglon.resultados.all()}
        renglon.filas_resultado = [
            {'linea': linea, 'texto': existentes.get(linea.orden, '')}
            for linea in renglon.producto.especificacion.all()
        ]

    return render(request, 'core/pedido_resultados.html', {
        'pedido': pedido,
        'renglones': renglones,
        'solo_lectura': pedido.emitido,
    })


@login_required
@require_POST
def pedido_emitir(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    if pedido.emitido:
        messages.info(request, 'Este pedido ya estaba emitido.')
        return redirect('pedido_detail', pk=pedido.pk)

    try:
        pedido.emitir()
    except PedidoSinResultados:
        messages.error(request, 'No se puede emitir: el pedido no tiene resultados de laboratorio capturados.')
        return redirect('pedido_detail', pk=pedido.pk)

    messages.success(request, f'Certificado emitido con folio {pedido.folio}.')
    return redirect('pedido_detail', pk=pedido.pk)


@login_required
def pedido_etiquetas(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related('cliente'), pk=pk)
    renglones = pedido.renglones.select_related('producto')
    total_etiquetas = sum(r.paquetes for r in renglones)
    return render(request, 'core/pedido_etiquetas.html', {
        'pedido': pedido,
        'renglones': renglones,
        'total_etiquetas': total_etiquetas,
    })


@login_required
def pedido_etiquetas_pdf(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related('cliente'), pk=pk)

    try:
        posicion = int(request.GET.get('posicion', 1))
    except ValueError:
        posicion = 1
    if posicion not in POSICIONES_VALIDAS:
        posicion = 1

    config = Configuracion.obtener()
    buffer = generar_pdf_etiquetas(pedido, posicion, config)

    nombre = f'etiquetas-{pedido.folio}.pdf' if pedido.folio else f'etiquetas-pedido-{pedido.pk}.pdf'
    return FileResponse(buffer, content_type='application/pdf', filename=nombre)


@login_required
def calibracion(request):
    if not es_admin(request.user):
        messages.error(request, 'Esta pantalla es solo para administradores.')
        return redirect('pedido_list')

    config = Configuracion.obtener()

    if request.method == 'POST':
        form = ConfiguracionForm(request.POST, instance=config)
        accion = request.POST.get('accion')

        if form.is_valid():
            if accion == 'probar':
                config_prueba = form.save(commit=False)
                buffer = generar_pdf_calibracion(config_prueba)
                return FileResponse(buffer, content_type='application/pdf', filename='hoja-prueba-calibracion.pdf')
            else:
                form.save()
                messages.success(request, 'Configuración guardada.')
                return redirect('calibracion')
    else:
        form = ConfiguracionForm(instance=config)

    return render(request, 'core/calibracion.html', {'form': form})


@login_required
def api_clientes_buscar(request):
    q = request.GET.get('q', '').strip()
    resultados = []
    if q:
        clientes = Cliente.objects.filter(activo=True).filter(
            Q(codigo__icontains=q) | Q(nombre_corto__icontains=q) | Q(razon_social__icontains=q)
        )[:LIMITE_BUSQUEDA]
        resultados = [
            {
                'valor': c.codigo,
                'texto': f'{c.codigo} — {c.razon_social or c.nombre_corto}',
            }
            for c in clientes
        ]
    return JsonResponse(resultados, safe=False)


@login_required
def api_productos_buscar(request):
    q = request.GET.get('q', '').strip()
    resultados = []
    if q:
        productos = Producto.objects.filter(activo=True).filter(
            Q(modelo__icontains=q) | Q(descripcion__icontains=q)
        )[:LIMITE_BUSQUEDA]
        resultados = [
            {
                'valor': p.modelo,
                'texto': f'{p.modelo} — {p.descripcion}',
                'unidad': p.unidad,
                'cas': p.cas,
                'onu': p.onu,
            }
            for p in productos
        ]
    return JsonResponse(resultados, safe=False)
