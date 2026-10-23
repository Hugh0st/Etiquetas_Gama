"""Clasificación de las líneas de especificación que son continuación visual.

Una línea de especificación puede no ser una característica propia, sino la
continuación visual de la de arriba. El sistema de consola viejo las indicaba
solo con el acomodo del texto en una pantalla monoespaciada, así que al
importar el catálogo esa distinción se perdió y hay que deducirla del texto.

Hay dos formas:

  - Continuación del NOMBRE del parámetro. Un indicador de temperatura que no
    trae valor propio:

        PESO ESPECIFICO          0.870   -   0.880
        A  25 C:                                      <- esta

  - Continuación del VALOR. Lo que no alcanzó a caber en la línea de arriba:

        SOLUBLIDAD:              1ML.EN 3ML. 60% ALCOHOL
                                 ETILICO                <- esta

Importa distinguirlas porque una continuación no lleva resultado de
laboratorio propio y, en el certificado, cada tipo se imprime en una columna
distinta (ver certificado._tabla_especificacion).

Estas mismas reglas están duplicadas en las migraciones 0010 y 0013, a
propósito: una migración es una foto de un momento y no debe cambiar de
comportamiento porque este módulo evolucione. Aquellas ya corrieron, pero sin
efecto sobre los datos de hoy, porque el catálogo se importó después. Este
módulo es el que usa el comando marcar_continuaciones.
"""
import re

CRITERIO_NOMBRE = 'nombre'
CRITERIO_VALOR = 'valor'

TIPO_PARAMETROS = 'parametros'
TIPO_ESPECIFICACION = 'especificacion'

# Continuación del nombre: arranca con "A <número>" y ahí se acaba. Si trajera
# un valor propio sería su propia característica, no una continuación.
_NOMBRE_ARRANQUE = re.compile(r'^A\s+\d+')
_NOMBRE_PURA = re.compile(r'^A\s+\d+O?\s*[^\dA-Za-z\s]{0,2}\s*[Cc]\s*[:;]?\s*$')

# Continuación del valor: arranca con una corrida de 2+ espacios, trae texto
# después, y no tiene ninguna otra corrida de 2+ espacios. Si la tuviera sería
# su propio par nombre/valor indentado, no una continuación.
_INDENTADA = re.compile(r'^ {2,}(\S.*)$')
_OTRA_CORRIDA = re.compile(r' {2,}')

# De las indentadas, dos subcasos leen como continuación del NOMBRE y no del
# valor: un indicador de grados sin número propio, o una unidad de medida sola.
_GRADOS = re.compile(r'^[oOºÂ°]{0,2}\s*[Cc]\s*[:;.]?$')
_TIENE_DIGITO = re.compile(r'\d')

UNIDADES_CONOCIDAS = frozenset({
    'G/ML', 'MG/G', 'MG/ML', 'MG/L', 'G/L', 'G/CM3', 'G/CM³',
    'PPM', 'CP', 'CPS', 'CENTIPOISE', 'CENTIPOISES',
    '%', 'KG/M3', 'MOL/L', 'MEQ/G', 'MEQ/KG', 'UI/G',
})


def clasificar(texto):
    """Clasifica una línea de especificación.

    Devuelve (es_continuacion, tipo_continuacion, criterio). Si la línea no es
    continuación, devuelve (False, '', None). El criterio dice por cuál de las
    dos reglas entró, para poder revisarlas por separado.
    """
    desnudo = (texto or '').strip()

    if _NOMBRE_ARRANQUE.match(desnudo) and _NOMBRE_PURA.match(desnudo):
        return True, TIPO_PARAMETROS, CRITERIO_NOMBRE

    indentada = _INDENTADA.match(texto or '')
    if indentada and not _OTRA_CORRIDA.search(indentada.group(1)):
        return True, _tipo_de_indentada(desnudo), CRITERIO_VALOR

    return False, '', None


def _tipo_de_indentada(contenido):
    """En qué columna del certificado va una continuación indentada."""
    if _GRADOS.match(contenido):
        return TIPO_PARAMETROS
    if not _TIENE_DIGITO.search(contenido):
        if contenido.rstrip(':;.').strip().upper() in UNIDADES_CONOCIDAS:
            return TIPO_PARAMETROS
    return TIPO_ESPECIFICACION
