from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .certificado import generar_pdf_certificado_renglon, generar_pdf_certificados_pedido
from .etiquetas import generar_pdf_calibracion, generar_pdf_etiquetas
from .forms import ConfiguracionForm, PedidoForm, RenglonPedidoFormSet
from .models import (
    Cliente,
    Configuracion,
    MotivoCancelacionRequerido,
    Pedido,
    PedidoEmitidoNoSeElimina,
    PedidoSinResultados,
    Producto,
    ResultadoLaboratorio,
)
from .permisos import es_admin, solo_admin  # noqa: F401  (es_admin se reexporta por comodidad)

LIMITE_BUSQUEDA = 20
POSICIONES_VALIDAS = {1, 2, 3}


def _aplicar_correcciones_catalogo(formset, usuario, pedido):
    """Propaga al catálogo la descripción de los renglones cuya casilla
    "Corregir también en el catálogo" quedó marcada.

    El formulario ya descartó las casillas cuyo texto no difiere del catálogo,
    y el formset ya rechazó que dos renglones del mismo producto pidan
    descripciones distintas. Devuelve los modelos corregidos, para avisarle al
    usuario qué cambió para todos los pedidos futuros.
    """
    corregidos = []
    vistos = set()
    for form in formset.forms:
        datos = form.cleaned_data
        if not datos or datos.get('DELETE') or not datos.get('corregir_catalogo'):
            continue
        producto = datos['producto']
        # Dos renglones del mismo producto traen dos instancias distintas en
        # memoria; sin esto el segundo repetiría la corrección en la bitácora.
        if producto.pk in vistos:
            continue
        vistos.add(producto.pk)
        if producto.corregir_descripcion(datos['descripcion'], usuario, pedido):
            corregidos.append(producto.modelo)
    return corregidos


def _avisar_correcciones(request, corregidos):
    """Avisa qué productos quedaron corregidos en el catálogo.

    Se llama ya fuera de la transacción: si el guardado se deshizo, no hay
    nada que avisar.
    """
    if not corregidos:
        return
    modelos = ', '.join(corregidos)
    messages.success(
        request,
        f'Se corrigió la descripción en el catálogo de {modelos}. '
        f'Los pedidos nuevos ya la usarán.',
    )


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

    # Conteos por estado para los filtros. Son solo para mostrar: siempre
    # cuentan sobre el total, sin importar el filtro activo.
    base_conteos = _pedidos_con_conteos(Pedido.objects.all())
    conteos = {
        'todos': Pedido.objects.count(),
        'borrador': base_conteos.filter(emitido=False, num_resultados=0).count(),
        'con_resultados': base_conteos.filter(emitido=False, num_resultados__gt=0).count(),
        'emitido': Pedido.objects.filter(emitido=True, cancelado=False).count(),
        'cancelado': Pedido.objects.filter(cancelado=True).count(),
    }

    estado = request.GET.get('estado', '')
    if estado == 'borrador':
        pedidos = pedidos.filter(emitido=False, num_resultados=0)
    elif estado == 'con_resultados':
        pedidos = pedidos.filter(emitido=False, num_resultados__gt=0)
    elif estado == 'emitido':
        pedidos = pedidos.filter(emitido=True, cancelado=False)
    elif estado == 'cancelado':
        pedidos = pedidos.filter(cancelado=True)

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
        'conteos': conteos,
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
                corregidos = _aplicar_correcciones_catalogo(formset, request.user, pedido)
            messages.success(request, 'Pedido creado.')
            _avisar_correcciones(request, corregidos)
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
    if pedido.cancelado:
        messages.info(request, 'Este pedido está cancelado y no se puede editar.')
        return redirect('pedido_detail', pk=pedido.pk)
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
                corregidos = _aplicar_correcciones_catalogo(formset, request.user, pedido)
            messages.success(request, 'Pedido actualizado.')
            _avisar_correcciones(request, corregidos)
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
        if pedido.cancelado:
            messages.info(request, 'Este pedido está cancelado; los resultados no se pueden modificar.')
            return redirect('pedido_detail', pk=pedido.pk)
        if pedido.emitido:
            messages.info(request, 'Este pedido ya fue emitido; los resultados no se pueden modificar.')
            return redirect('pedido_detail', pk=pedido.pk)

        # Aquí lineas_especificacion siempre devuelve las del catálogo: este
        # bloque solo corre si el pedido no está emitido, y un pedido sin
        # emitir no tiene snapshot. Se usa la misma propiedad que al mostrar
        # para no tener dos ideas distintas de cuáles son las líneas.
        with transaction.atomic():
            for renglon in renglones:
                for linea in renglon.lineas_especificacion:
                    if linea['es_continuacion']:
                        continue
                    campo = f'resultado-{renglon.id}-{linea["orden"]}'
                    texto = request.POST.get(campo, '').strip()
                    ResultadoLaboratorio.objects.update_or_create(
                        renglon=renglon, orden=linea['orden'],
                        defaults={'texto': texto},
                    )
        messages.success(request, 'Resultados guardados.')
        return redirect('pedido_resultados', pk=pedido.pk)

    for renglon in renglones:
        existentes = {r.orden: r.texto for r in renglon.resultados.all()}
        renglon.filas_resultado = [
            {'linea': linea, 'texto': existentes.get(linea['orden'], '')}
            for linea in renglon.lineas_especificacion
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
    if pedido.cancelado:
        messages.info(request, 'Este pedido está cancelado y no se puede volver a emitir.')
        return redirect('pedido_detail', pk=pedido.pk)
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
def pedido_eliminar(request, pk):
    """Borra de la base un pedido que nunca se emitió (borrador o con resultados).

    Cualquier usuario puede hacerlo. Un pedido con folio no llega aquí: se
    rechaza en la vista, y además el modelo lo bloquea por si acaso.
    """
    pedido = get_object_or_404(Pedido.objects.select_related('cliente'), pk=pk)

    if not pedido.se_puede_eliminar:
        messages.error(
            request,
            f'El pedido {pedido.folio} ya fue emitido y no se puede eliminar. '
            f'Si hay que anularlo, se cancela.',
        )
        return redirect('pedido_detail', pk=pedido.pk)

    if request.method == 'POST':
        descripcion = f'{pedido.cliente.razon_social or pedido.cliente.nombre_corto}'
        try:
            pedido.delete()
        except PedidoEmitidoNoSeElimina:
            messages.error(request, 'El pedido ya fue emitido y no se puede eliminar.')
            return redirect('pedido_detail', pk=pedido.pk)
        messages.success(request, f'Se eliminó el pedido de {descripcion}.')
        return redirect('pedido_list')

    return render(request, 'core/pedido_eliminar.html', {
        'pedido': pedido,
        'num_renglones': pedido.renglones.count(),
        'num_resultados': ResultadoLaboratorio.objects.filter(renglon__pedido=pedido).count(),
    })


@login_required
@solo_admin
def pedido_cancelar(request, pk):
    """Anula un pedido emitido conservando folio, renglones y snapshots."""
    pedido = get_object_or_404(Pedido.objects.select_related('cliente'), pk=pk)

    if not pedido.emitido:
        messages.error(
            request,
            'Este pedido todavía no se emite, así que no hay nada que cancelar. '
            'Si ya no lo necesitas, puedes eliminarlo.',
        )
        return redirect('pedido_detail', pk=pedido.pk)

    if pedido.cancelado:
        messages.info(request, f'El pedido {pedido.folio} ya estaba cancelado.')
        return redirect('pedido_detail', pk=pedido.pk)

    motivo = ''
    if request.method == 'POST':
        motivo = request.POST.get('motivo', '')
        try:
            pedido.cancelar(request.user, motivo)
        except MotivoCancelacionRequerido:
            messages.error(request, 'Escribe el motivo de la cancelación.')
            return render(request, 'core/pedido_cancelar.html', {
                'pedido': pedido,
                'motivo': motivo,
                'falta_motivo': True,
            })
        messages.success(request, f'Se canceló el pedido {pedido.folio}.')
        return redirect('pedido_detail', pk=pedido.pk)

    return render(request, 'core/pedido_cancelar.html', {
        'pedido': pedido,
        'motivo': motivo,
        'falta_motivo': False,
    })


@login_required
def renglon_certificado_pdf(request, pedido_pk, renglon_pk):
    pedido = get_object_or_404(Pedido.objects.select_related('cliente'), pk=pedido_pk)
    if not pedido.emitido:
        messages.error(request, 'El pedido debe estar emitido para descargar el certificado.')
        return redirect('pedido_detail', pk=pedido.pk)

    renglon = get_object_or_404(
        pedido.renglones.select_related('producto').prefetch_related('resultados'),
        pk=renglon_pk,
    )
    buffer = generar_pdf_certificado_renglon(pedido, renglon)
    nombre = f'certificado-{pedido.folio}-{renglon.producto_id}.pdf'
    return FileResponse(buffer, content_type='application/pdf', filename=nombre)


@login_required
def pedido_certificados_pdf(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related('cliente'), pk=pk)
    if not pedido.emitido:
        messages.error(request, 'El pedido debe estar emitido para descargar los certificados.')
        return redirect('pedido_detail', pk=pedido.pk)

    buffer = generar_pdf_certificados_pedido(pedido)
    nombre = f'certificados-{pedido.folio}.pdf'
    return FileResponse(buffer, content_type='application/pdf', filename=nombre)


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
@solo_admin
def calibracion(request):
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
                # Suelta, además de dentro de 'texto', para poder autollenar
                # con ella el campo editable de descripción del renglón.
                'descripcion': p.descripcion,
                'unidad': p.unidad,
                'cas': p.cas,
                'onu': p.onu,
            }
            for p in productos
        ]
    return JsonResponse(resultados, safe=False)
