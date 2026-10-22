import pathlib

from django.test import SimpleTestCase

RAIZ_PLANTILLAS = pathlib.Path(__file__).resolve().parent / 'templates'


class ComentariosDePlantillaTest(SimpleTestCase):
    """Revisa que ningún comentario de plantilla quede abierto.

    Django solo oculta un comentario de la forma corta (llaves y gato) cuando
    abre y cierra en la MISMA línea. Si el cierre queda en otra, Django deja de
    tratarlo como comentario y el texto se imprime como contenido visible de la
    página. Ya pasó dos veces, y es de las cosas que no se notan leyendo el
    código: para un comentario de varias líneas hay que usar la etiqueta
    {% comment %} ... {% endcomment %}.
    """

    def test_ningun_comentario_queda_abierto(self):
        plantillas = sorted(RAIZ_PLANTILLAS.rglob('*.html'))
        self.assertGreater(len(plantillas), 0, 'No se encontró ninguna plantilla que revisar.')

        abiertos = []
        for archivo in plantillas:
            lineas = archivo.read_text(encoding='utf-8').splitlines()
            for numero, linea in enumerate(lineas, 1):
                desde = 0
                while (inicio := linea.find('{#', desde)) != -1:
                    if linea.find('#}', inicio + 2) == -1:
                        relativa = archivo.relative_to(RAIZ_PLANTILLAS).as_posix()
                        abiertos.append(f'  {relativa}:{numero}  {linea.strip()[:70]}')
                    desde = inicio + 2

        self.assertEqual(
            abiertos, [],
            'Hay comentarios de plantilla que no cierran en su misma línea, así que se '
            'van a imprimir en la página. Usa {% comment %} para varias líneas:\n'
            + '\n'.join(abiertos),
        )
