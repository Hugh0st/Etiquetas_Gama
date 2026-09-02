"""
Generación del PDF del certificado de análisis.

A diferencia de las etiquetas, este documento se diseña por completo (hoja
blanca tamaño carta normal, sin coordenadas de Configuracion) y se genera
con reportlab Platypus para que el salto de página, la repetición del
encabezado de la tabla y el ajuste de texto largo se manejen solos.

El certificado se emite por renglón: un producto, un documento completo.
"""
import io
import os
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .models import Configuracion

LOGO_PATH = os.path.join(os.path.dirname(__file__), 'static', 'core', 'logo_gama.png')

MARGEN_LR = 18 * mm
MARGEN_TB = 15 * mm
ANCHO_UTIL = letter[0] - 2 * MARGEN_LR

COLOR_ACENTO = colors.HexColor('#7a2331')
COLOR_GRIS = colors.HexColor('#8f887c')
COLOR_REGLA = colors.HexColor('#c9c3b7')

# El sistema viejo separaba el nombre del parámetro de su valor con una
# corrida de 2+ espacios (pensada para una fuente monoespaciada). Se usa esa
# misma corrida para partir la línea en las dos columnas reales de la tabla.
PATRON_DIVISION_ESPEC = re.compile(r' {2,}')

TEXTO_ALMACENAMIENTO_DEFECTO = (
    'NO SE REQUIEREN PRECAUCIONES ESPECIALES\n'
    'MANTENGASE EN LUGAR SECO Y FRESCO\n'
    'NO SE EXPONGA A LA LUZ DEL SOL\n'
    'CONSERVESE EN RECIPIENTES PERFECTAMENTE CERRADOS Y DE PREFERENCIA LLENOS.\n'
    'NO SE EXPONGA A FUENTES DE CALOR DIRECTAS.'
)

DIRECCION_EMPRESA = (
    'DIRECCIÓN Blvd. Espíritu Santo - Chiluca #39 | Colonia Barrio Dos Caminos | '
    'Jilotzingo, Estado de México | C.P. 54570<br/>'
    'Teléfono Fijo 52 (55) 89969701&nbsp;&nbsp;(55) 89969703&nbsp;&nbsp;&nbsp;'
    'Celular 52 (55) 4529 4337<br/>'
    'WEB: www.esenciasgama.com.mx'
)


# ----------------------------------------------------------------------
# Número de paquetes escrito con letra
# ----------------------------------------------------------------------
_CERO_A_VEINTINUEVE = [
    'CERO', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE',
    'DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISEIS', 'DIECISIETE',
    'DIECIOCHO', 'DIECINUEVE', 'VEINTE', 'VEINTIUNO', 'VEINTIDOS', 'VEINTITRES',
    'VEINTICUATRO', 'VEINTICINCO', 'VEINTISEIS', 'VEINTISIETE', 'VEINTIOCHO', 'VEINTINUEVE',
]
_DECENAS = {3: 'TREINTA', 4: 'CUARENTA', 5: 'CINCUENTA', 6: 'SESENTA', 7: 'SETENTA', 8: 'OCHENTA', 9: 'NOVENTA'}
_CENTENAS = {
    1: 'CIENTO', 2: 'DOSCIENTOS', 3: 'TRESCIENTOS', 4: 'CUATROCIENTOS', 5: 'QUINIENTOS',
    6: 'SEISCIENTOS', 7: 'SETECIENTOS', 8: 'OCHOCIENTOS', 9: 'NOVECIENTOS',
}


def _bloque_hasta_999(n):
    if n < 30:
        return _CERO_A_VEINTINUEVE[n]
    if n < 100:
        decena, unidad = divmod(n, 10)
        palabra = _DECENAS[decena]
        if unidad:
            palabra += ' Y ' + _CERO_A_VEINTINUEVE[unidad]
        return palabra
    if n == 100:
        return 'CIEN'
    centena, resto = divmod(n, 100)
    palabra = _CENTENAS[centena]
    if resto:
        palabra += ' ' + _bloque_hasta_999(resto)
    return palabra


def numero_a_letras(n):
    """Convierte un entero no negativo a su escritura en español, en mayúsculas."""
    if n == 0:
        return 'CERO'
    if n < 1000:
        return _bloque_hasta_999(n)
    miles, resto = divmod(n, 1000)
    palabra = 'MIL' if miles == 1 else _bloque_hasta_999(miles) + ' MIL'
    if resto:
        palabra += ' ' + _bloque_hasta_999(resto)
    return palabra


# ----------------------------------------------------------------------
# Estilos
# ----------------------------------------------------------------------
def _construir_estilos():
    return {
        'titulo': ParagraphStyle('titulo', fontName='Helvetica-Bold', fontSize=19, leading=21),
        'subtitulo_certificado': ParagraphStyle(
            'subtitulo_certificado', fontName='Helvetica-Bold', fontSize=13, leading=15,
            alignment=TA_CENTER, textColor=COLOR_ACENTO, spaceBefore=1.5 * mm, spaceAfter=1.5 * mm,
        ),
        'aviso_uso': ParagraphStyle(
            'aviso_uso', fontName='Helvetica-Oblique', fontSize=6.5, leading=8,
            alignment=TA_CENTER, textColor=colors.HexColor('#5c574e'),
        ),
        'folio_valor': ParagraphStyle('folio_valor', fontName='Helvetica-Bold', fontSize=14, alignment=TA_RIGHT, leading=16),
        'dato_label': ParagraphStyle('dato_label', fontName='Helvetica-Bold', fontSize=8.5, leading=11),
        'dato_valor': ParagraphStyle('dato_valor', fontName='Helvetica', fontSize=8.5, leading=11),
        'tabla_header': ParagraphStyle('tabla_header', fontName='Helvetica-Bold', fontSize=6.8, leading=8.2),
        'espec': ParagraphStyle('espec', fontName='Helvetica', fontSize=7.5, leading=9),
        'espec_continuacion': ParagraphStyle(
            'espec_continuacion', fontName='Helvetica', fontSize=7.5, leading=9,
            textColor=COLOR_GRIS, leftIndent=4 * mm,
        ),
        'resultado': ParagraphStyle('resultado', fontName='Helvetica', fontSize=8, leading=9.5),
        'aviso_tabla': ParagraphStyle('aviso_tabla', fontName='Helvetica-Oblique', fontSize=8.5, textColor=COLOR_GRIS),
        'almacenamiento_label': ParagraphStyle('almacenamiento_label', fontName='Helvetica-Bold', fontSize=7.5, leading=9),
        'almacenamiento_texto': ParagraphStyle('almacenamiento_texto', fontName='Helvetica', fontSize=7.5, leading=10.5),
        'firma_rotulo': ParagraphStyle('firma_rotulo', fontName='Helvetica-Bold', fontSize=6.8, leading=8.2, alignment=TA_CENTER),
        'firma_nombre': ParagraphStyle('firma_nombre', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_CENTER),
        'nota_proveedor': ParagraphStyle(
            'nota_proveedor', fontName='Helvetica-Bold', fontSize=7.5, leading=9,
            alignment=TA_CENTER, textColor=colors.HexColor('#5c574e'),
        ),
        'direccion': ParagraphStyle('direccion', fontName='Helvetica', fontSize=6.3, leading=8.5, alignment=TA_CENTER, textColor=colors.HexColor('#5c574e')),
    }


def _texto_monoespaciado(texto):
    """Escapa el texto y convierte espacios normales en espacios duros, para
    que Paragraph no colapse el alineado hecho a mano con espacios."""
    return escape(texto or '').replace(' ', '\xa0')


def _dividir_parametro_especificacion(texto):
    """Parte una línea de especificación en (parámetro, especificación) por
    la primera corrida de 2+ espacios. Si no hay ninguna, todo es parámetro."""
    partes = PATRON_DIVISION_ESPEC.split(texto, maxsplit=1)
    parametro = partes[0]
    especificacion = partes[1].strip() if len(partes) > 1 else ''
    return parametro, especificacion


# ----------------------------------------------------------------------
# Bloques del documento
# ----------------------------------------------------------------------
def _tabla_encabezado(folio, styles):
    if os.path.exists(LOGO_PATH):
        logo = Image(LOGO_PATH, width=22 * mm, height=22 * mm)
    else:
        logo = Spacer(22 * mm, 22 * mm)

    titulo = Paragraph('ESENCIAS GAMA', styles['titulo'])

    folio_parrafo = Paragraph(
        f'<font size="6.5">FOLIO</font><br/><font size="14"><b>{escape(folio)}</b></font>',
        styles['folio_valor'],
    )
    ancho_folio = 42 * mm
    folio_celda = Table(
        [[folio_parrafo]],
        colWidths=[ancho_folio],
        style=TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.75, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2 * mm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
        ]),
    )

    ancho_logo = 26 * mm
    return Table(
        [[logo, titulo, folio_celda]],
        colWidths=[ancho_logo, ANCHO_UTIL - ancho_logo - ancho_folio, ancho_folio],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]),
    )


def _tabla_datos(pedido, renglon, cliente_nombre, styles):
    cantidad_texto = f'{renglon.cantidad} {renglon.unidad}'.strip()

    def fila(etiqueta, valor):
        return [
            Paragraph(escape(etiqueta), styles['dato_label']),
            Paragraph(escape(valor or ''), styles['dato_valor']),
        ]

    filas = [
        fila('FECHA/DATE:', pedido.fecha_emision.strftime('%d/%m/%Y')),
        fila('CLIENTE/CUSTOMER:', cliente_nombre),
        fila('PRODUCTO/PRODUCT:', renglon.producto.descripcion),
        fila('CANTIDAD/QUANTITY:', cantidad_texto),
        fila('No. DE LOTE/BATCH No:', renglon.lote),
        fila('No. DE PAQUETES:', numero_a_letras(renglon.paquetes)),
        fila('CADUCIDAD:', renglon.caducidad),
        fila('PRODUCCION:', renglon.produccion),
    ]
    ancho_etiqueta = 48 * mm
    return Table(
        filas,
        colWidths=[ancho_etiqueta, ANCHO_UTIL - ancho_etiqueta],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 0.8 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0.8 * mm),
        ]),
    )


def _tabla_especificacion(especificacion_snapshot, resultados_por_orden, styles):
    if not especificacion_snapshot:
        return Paragraph('Este producto no tiene especificación registrada.', styles['aviso_tabla'])

    encabezado = [
        Paragraph('PARAMETROS/<br/>PROPERTIES', styles['tabla_header']),
        Paragraph('ESPECIFICACION/<br/>SPECIFICATIONS', styles['tabla_header']),
        Paragraph('RESULTADO/<br/>RESULTS', styles['tabla_header']),
    ]
    filas = [encabezado]

    for linea in especificacion_snapshot:
        es_continuacion = linea.get('es_continuacion', False)
        tipo_continuacion = linea.get('tipo_continuacion', 'parametros')
        # Solo se recorta el espacio en blanco al INICIO de la línea, para que
        # todas arranquen en el mismo punto; el resto del texto no se toca.
        texto = (linea.get('texto') or '').lstrip()

        if es_continuacion and tipo_continuacion == 'especificacion':
            # Continúa el VALOR de la línea de arriba: va en la columna de
            # especificación, con el mismo estilo que un valor normal (sin
            # gris), para que se lea como la segunda línea de ese valor.
            celda_parametro = ''
            celda_especificacion = Paragraph(_texto_monoespaciado(texto), styles['espec'])
            celda_resultado = ''
        elif es_continuacion:
            # Continúa el NOMBRE del parámetro (ej. "A 25 C:").
            celda_parametro = Paragraph(_texto_monoespaciado(texto), styles['espec_continuacion'])
            celda_especificacion = ''
            celda_resultado = ''
        else:
            parametro, especificacion_valor = _dividir_parametro_especificacion(texto)
            celda_parametro = Paragraph(escape(parametro), styles['espec'])
            celda_especificacion = (
                Paragraph(_texto_monoespaciado(especificacion_valor), styles['espec'])
                if especificacion_valor else ''
            )
            resultado = resultados_por_orden.get(linea.get('orden'), '')
            celda_resultado = Paragraph(escape(resultado), styles['resultado']) if resultado else ''

        filas.append([celda_parametro, celda_especificacion, celda_resultado])

    ancho_parametros = 45 * mm
    ancho_especificacion = 68 * mm
    ancho_resultado = ANCHO_UTIL - ancho_parametros - ancho_especificacion

    tabla = Table(
        filas,
        colWidths=[ancho_parametros, ancho_especificacion, ancho_resultado],
        repeatRows=1,
    )
    tabla.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 0.8, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.black),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, COLOR_REGLA),
        ('LINEAFTER', (0, 0), (0, -1), 0.4, COLOR_REGLA),
        ('LINEAFTER', (1, 0), (1, -1), 0.5, COLOR_REGLA),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 1 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1 * mm),
    ]))
    return tabla


def _bloque_almacenamiento(texto, styles):
    texto_html = escape(texto).replace('\n', '<br/>')
    ancho_etiqueta = 32 * mm
    return Table(
        [[
            Paragraph('ALMACENAMIENTO:', styles['almacenamiento_label']),
            Paragraph(texto_html, styles['almacenamiento_texto']),
        ]],
        colWidths=[ancho_etiqueta, ANCHO_UTIL - ancho_etiqueta],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, COLOR_REGLA),
        ]),
    )


def _pie_pagina(nombre_control_calidad, styles):
    """Bloque de firma, centrado en el ancho completo de la página."""
    ancho_linea = 65 * mm
    return Table(
        [
            [Spacer(1, 14 * mm)],
            [Paragraph('CONTROL DE CALIDAD / QUALITY CONTROL', styles['firma_rotulo'])],
            [Paragraph(escape(nombre_control_calidad or ''), styles['firma_nombre'])],
        ],
        colWidths=[ancho_linea],
        style=TableStyle([
            ('LINEABOVE', (0, 1), (0, 1), 0.6, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0.8 * mm),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
        hAlign='CENTER',
    )


# ----------------------------------------------------------------------
# Ensamblado del documento
# ----------------------------------------------------------------------
def _story_renglon(pedido, renglon, styles):
    cliente_snapshot = pedido.cliente_snapshot or {}
    cliente_nombre = cliente_snapshot.get('razon_social') or cliente_snapshot.get('nombre_corto', '')

    config = Configuracion.obtener()
    texto_almacenamiento = config.texto_almacenamiento or TEXTO_ALMACENAMIENTO_DEFECTO

    especificacion = renglon.especificacion_snapshot or []
    resultados_por_orden = {r.orden: r.texto for r in renglon.resultados.all()}

    story = [
        _tabla_encabezado(pedido.folio, styles),
        Paragraph('CERTIFICADO DE ANÁLISIS', styles['subtitulo_certificado']),
        Paragraph(
            'EL USO Y LA APLICACIÓN SON RESPONSABILIDAD EXCLUSIVA DEL CLIENTE',
            styles['aviso_uso'],
        ),
        HRFlowable(width='100%', thickness=1, color=colors.black, spaceBefore=2 * mm, spaceAfter=4 * mm),
        _tabla_datos(pedido, renglon, cliente_nombre, styles),
        Spacer(1, 4 * mm),
        _tabla_especificacion(especificacion, resultados_por_orden, styles),
        KeepTogether([
            _bloque_almacenamiento(texto_almacenamiento, styles),
            Spacer(1, 6 * mm),
            _pie_pagina(config.nombre_control_calidad, styles),
            Spacer(1, 4 * mm),
            Paragraph('ESTOS DATOS SON COPIA FIEL DE NUESTRO PROVEEDOR', styles['nota_proveedor']),
            Spacer(1, 2 * mm),
            Paragraph(DIRECCION_EMPRESA, styles['direccion']),
        ]),
    ]
    return story


def _nuevo_documento(buffer, titulo):
    return SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=MARGEN_LR,
        rightMargin=MARGEN_LR,
        topMargin=MARGEN_TB,
        bottomMargin=MARGEN_TB,
        title=titulo,
    )


def generar_pdf_certificado_renglon(pedido, renglon):
    """PDF del certificado de un solo renglón (un producto)."""
    if not pedido.emitido:
        raise ValueError('El pedido debe estar emitido para generar su certificado.')

    buffer = io.BytesIO()
    doc = _nuevo_documento(buffer, f'Certificado {pedido.folio} - {renglon.producto_id}')
    styles = _construir_estilos()
    doc.build(_story_renglon(pedido, renglon, styles))
    buffer.seek(0)
    return buffer


def generar_pdf_certificados_pedido(pedido):
    """PDF con un certificado por renglón, uno por página, del pedido completo."""
    if not pedido.emitido:
        raise ValueError('El pedido debe estar emitido para generar sus certificados.')

    buffer = io.BytesIO()
    doc = _nuevo_documento(buffer, f'Certificados {pedido.folio}')
    styles = _construir_estilos()

    story = []
    renglones = list(pedido.renglones.select_related('producto').prefetch_related('resultados'))
    for i, renglon in enumerate(renglones):
        if i > 0:
            story.append(PageBreak())
        story.extend(_story_renglon(pedido, renglon, styles))

    doc.build(story)
    buffer.seek(0)
    return buffer
