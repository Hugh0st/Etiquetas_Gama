"""Ata cada resultado de laboratorio a su línea de especificación.

Hasta ahora el vínculo era posicional: ResultadoLaboratorio.orden contra
LineaEspecificacion.orden. Con el FK nuevo pasa a ser por identidad.

Dos reglas, y la segunda es la importante:

  - Pedidos EN CURSO: se busca la línea por (producto del renglón, orden) y se
    ata. De aquí en adelante reordenar la especificación no desalinea nada.

  - Pedidos EMITIDOS: se dejan en NULL a propósito. Un pedido emitido es
    autocontenido: su especificacion_snapshot y el orden de sus resultados lo
    dicen todo, y Pedido.emitir() desata los resultados por la misma razón.
    Si se ataran aquí, editar el catálogo podría alcanzar un certificado que
    ya se entregó a un cliente, que es exactamente lo que se está evitando.

Los resultados a los que no se les encuentra línea se quedan en NULL y se
reportan. Ya hoy son invisibles en pantalla (la pantalla recorre las líneas,
no los resultados), así que no se pierde nada; solo conviene saber cuántos
son. Esta migración no borra ningún resultado.
"""
from django.db import migrations


def atar_a_su_linea(apps, schema_editor):
    LineaEspecificacion = apps.get_model('core', 'LineaEspecificacion')
    ResultadoLaboratorio = apps.get_model('core', 'ResultadoLaboratorio')

    # El catálogo completo son ~8000 líneas: cabe de sobra en memoria, y así
    # no se va a la base una vez por resultado.
    por_producto_y_orden = {
        (producto_id, orden): linea_id
        for linea_id, producto_id, orden in LineaEspecificacion.objects.values_list(
            'id', 'producto_id', 'orden',
        )
    }

    en_curso = (
        ResultadoLaboratorio.objects
        .filter(renglon__pedido__emitido=False)
        .select_related('renglon')
    )

    atados = []
    sin_linea = 0
    for resultado in en_curso.iterator():
        linea_id = por_producto_y_orden.get(
            (resultado.renglon.producto_id, resultado.orden)
        )
        if linea_id is None:
            sin_linea += 1
            continue
        resultado.linea_id = linea_id
        atados.append(resultado)

    ResultadoLaboratorio.objects.bulk_update(atados, ['linea'], batch_size=500)

    total = ResultadoLaboratorio.objects.count()
    emitidos = ResultadoLaboratorio.objects.filter(renglon__pedido__emitido=True).count()
    print('')
    print(f'  Resultados en total:                      {total}')
    print(f'  Atados a su linea (pedidos en curso):     {len(atados)}')
    print(f'  Dejados sueltos por estar emitidos:       {emitidos}')
    print(f'  Dejados sueltos por no encontrar linea:   {sin_linea}')
    if sin_linea:
        print('  (esos ya eran invisibles en pantalla; no se borro ninguno)')


def desatar(apps, schema_editor):
    ResultadoLaboratorio = apps.get_model('core', 'ResultadoLaboratorio')
    ResultadoLaboratorio.objects.update(linea=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_resultado_linea_y_bitacora_especificacion'),
    ]

    operations = [
        migrations.RunPython(atar_a_su_linea, desatar),
    ]
