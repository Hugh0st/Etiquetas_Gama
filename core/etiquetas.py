"""
Generación del PDF de etiquetas.

Las etiquetas no se diseñan: se sobreimprimen valores en coordenadas
absolutas (en mm) sobre papel adhesivo tamaño carta ya preimpreso con el
diseño, los pictogramas y las leyendas de cada campo. Por eso este módulo
dibuja texto en posiciones exactas y nunca ajusta ni escala la página.
"""
import io

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

ETIQUETAS_POR_HOJA = 3

FUENTE = 'Helvetica'
TAMANO_MAXIMO = 10
TAMANO_MINIMO = 6
ANCHO_UTIL_MM = 58  # el bloque de "ATENCIÓN" empieza ~105mm; el valor no debe cruzarlo

# calib_y/calib_interlineado se miden desde el borde superior de las letras,
# pero reportlab dibuja desde la línea base. 0.75 aproxima el ascenso de
# Helvetica como fracción del tamaño de fuente.
FACTOR_ASCENSO_HELVETICA = 0.75

# Índice de renglón (n) de la rejilla -> clave del valor a imprimir ahí.
# Los índices 6, 7, 11 y 12 quedan vacíos a propósito.
FILAS = {
    0: 'vendido_a',
    1: 'producto',
    2: 'lote',
    3: 'salida',
    4: 'cas',
    5: 'onu',
    8: 'peso_bruto',
    9: 'peso_tara',
    10: 'peso_neto',
    13: 'caducidad',
    14: 'produccion',
}


def _con_unidad(valor, unidad):
    if valor is None:
        return ''
    texto = f'{valor} {unidad or ""}'.strip()
    return texto


def valores_renglon(pedido, renglon):
    """Arma el diccionario de las 11 leyendas para un renglón del pedido."""
    cliente = pedido.cliente
    return {
        'vendido_a': cliente.razon_social or cliente.nombre_corto,
        'producto': renglon.producto.descripcion,
        'lote': renglon.lote,
        'salida': renglon.salida,
        'cas': renglon.cas,
        'onu': renglon.onu,
        'peso_bruto': _con_unidad(renglon.peso_bruto, renglon.unidad),
        'peso_tara': _con_unidad(renglon.peso_tara, renglon.unidad),
        'peso_neto': _con_unidad(renglon.peso_neto, renglon.unidad),
        'caducidad': renglon.caducidad,
        'produccion': renglon.produccion,
    }


def _tamano_ajustado(c, texto):
    """Reduce el tamaño de fuente hasta que el texto quepa en ANCHO_UTIL_MM.
    Nunca se parte en dos líneas; si ni al mínimo cabe, se deja desbordar."""
    tamano = TAMANO_MAXIMO
    ancho_max = ANCHO_UTIL_MM * mm
    while tamano > TAMANO_MINIMO and c.stringWidth(texto, FUENTE, tamano) > ancho_max:
        tamano -= 0.5
    return max(tamano, TAMANO_MINIMO)


def _dibujar_etiqueta(c, config, posicion_etiqueta, valores):
    alto_hoja = letter[1]
    x_pts = (config.calib_x + config.offset_x) * mm

    for n, clave in FILAS.items():
        texto = (valores.get(clave) or '').strip()
        if not texto:
            continue

        y_mm = (
            config.calib_y
            + (config.calib_paso * posicion_etiqueta)
            + (config.calib_interlineado * n)
            + config.offset_y
        )

        # calib_y se midió con regla desde el borde superior de la hoja hasta
        # el borde SUPERIOR de las letras, pero drawString() ubica el texto
        # por su LÍNEA BASE (en coordenadas que miden desde abajo). Hay que
        # bajar la línea base el ascenso de la fuente para que el borde
        # superior del texto caiga exactamente en y_mm. El ascenso depende
        # del tamaño real usado en esta línea, así que primero se decide el
        # tamaño (por si el valor es largo y se tuvo que encoger) y luego se
        # calcula el ajuste con ese mismo tamaño.
        tamano = _tamano_ajustado(c, texto)
        y_pts = alto_hoja - (y_mm * mm) - (tamano * FACTOR_ASCENSO_HELVETICA)

        c.setFont(FUENTE, tamano)
        c.drawString(x_pts, y_pts, texto)


def generar_pdf_etiquetas(pedido, posicion_inicial, config):
    """Genera el PDF de etiquetas de un pedido.

    Cada renglón produce tantas etiquetas idénticas como su campo
    "paquetes" indique, en el orden de los renglones. posicion_inicial
    (1, 2 o 3) es la posición de la primera hoja en la que se empieza a
    imprimir; las posiciones anteriores de esa hoja se dejan en blanco.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    slot = posicion_inicial - 1
    pagina_actual = None

    for renglon in pedido.renglones.select_related('producto'):
        valores = valores_renglon(pedido, renglon)
        for _ in range(renglon.paquetes):
            pagina = slot // ETIQUETAS_POR_HOJA
            posicion = slot % ETIQUETAS_POR_HOJA
            if pagina != pagina_actual:
                if pagina_actual is not None:
                    c.showPage()
                pagina_actual = pagina
            _dibujar_etiqueta(c, config, posicion, valores)
            slot += 1

    if pagina_actual is not None:
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


VALORES_PRUEBA_NORMAL = {
    'vendido_a': 'AROMATICOS QUIMICOS POTOSINOS SA DE CV',
    'producto': 'ALDEHIDO C 12 AL 10% DPG',
    'lote': 'L-2026-001',
    'salida': 'S-001',
    'cas': '112-54-9',
    'onu': '3082',
    'peso_bruto': '225.800 KGS.',
    'peso_tara': '25.000 KGS.',
    'peso_neto': '200.800 KGS.',
    'caducidad': 'JULIO 2028',
    'produccion': 'JULIO 2026',
}

VALORES_PRUEBA_LARGOS = {
    'vendido_a': 'ADITIVOS Y SABORIZANTES MEXICANOS SA DE CV CUENTA LARGA',
    'producto': 'MUSGO DE ENCINO VERDE RESINOIDE ALDEHIDO ESPECIAL',
    'lote': 'LOTE-DE-PRUEBA-EXTRA-LARGO-2026',
    'salida': 'SALIDA-DE-PRUEBA-EXTRA-LARGA-2026',
    'cas': '8006-90-4 / MEZCLA DE REFERENCIA',
    'onu': 'UN 1993 GRUPO DE EMBALAJE III',
    'peso_bruto': '1234.567 KGS.',
    'peso_tara': '123.456 KGS.',
    'peso_neto': '1111.111 KGS.',
    'caducidad': 'SEPTIEMBRE 2031',
    'produccion': 'SEPTIEMBRE 2026',
}

VALORES_PRUEBA_REGLA = {clave: '|123456789' for clave in FILAS.values()}


def generar_pdf_calibracion(config):
    """Hoja de prueba con las 3 etiquetas de una hoja llenas con datos
    ficticios, para verificar la alineación contra el papel preimpreso."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    _dibujar_etiqueta(c, config, 0, VALORES_PRUEBA_NORMAL)
    _dibujar_etiqueta(c, config, 1, VALORES_PRUEBA_LARGOS)
    _dibujar_etiqueta(c, config, 2, VALORES_PRUEBA_REGLA)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer
