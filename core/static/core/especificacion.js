/*
 * Editor de la especificación de un producto.
 *
 * El orden de las líneas no viaja como un número por fila, sino como la lista
 * de claves en un campo oculto: el servidor lee esa lista y renumera 1..N.
 * Así subir, bajar, agregar y quitar son solo mover filas de la tabla, y no
 * hay que recalcular índices en ningún lado.
 */
(function () {
    'use strict';

    const cuerpo = document.getElementById('lineas-especificacion');
    const campoOrden = document.getElementById('orden-filas');
    const plantilla = document.getElementById('linea-vacia');
    const botonAgregar = document.getElementById('agregar-linea');
    if (!cuerpo || !campoOrden) return;

    let contadorNuevas = 0;

    function filas() {
        return [...cuerpo.querySelectorAll('.linea-espec')];
    }

    // Lo único que el servidor necesita para saber el orden y qué filas quedan.
    // Una fila quitada simplemente desaparece de esta lista.
    function sincronizarOrden() {
        campoOrden.value = filas().map((fila) => fila.dataset.clave).join(',');
    }

    // El tipo de continuación solo tiene sentido si la línea es continuación.
    // Se deshabilita en vez de ocultarse para que se vea por qué no aplica.
    function activarMarcaContinuacion(fila) {
        const marca = fila.querySelector('[name^="continuacion-"]');
        const tipo = fila.querySelector('.tipo-continuacion');
        const celdaResultado = fila.querySelector('.col-resultado');
        if (!marca || !tipo) return;

        function revisar() {
            tipo.disabled = !marca.checked;
            fila.classList.toggle('es-continuacion', marca.checked);
            // Aviso en el momento: marcar como continuación deja huérfano el
            // resultado que ya estaba capturado. El servidor lo confirma al
            // guardar, pero conviene verlo antes de llegar ahí.
            const capturado = celdaResultado.querySelector('.resultado-capturado');
            if (capturado) {
                capturado.classList.toggle('se-va-a-perder', marca.checked);
            }
        }

        marca.addEventListener('change', revisar);
        revisar();
    }

    function activarFila(fila) {
        fila.querySelector('.subir').addEventListener('click', () => {
            const anterior = fila.previousElementSibling;
            if (anterior) {
                cuerpo.insertBefore(fila, anterior);
                sincronizarOrden();
                fila.querySelector('.subir').focus();
            }
        });

        fila.querySelector('.bajar').addEventListener('click', () => {
            const siguiente = fila.nextElementSibling;
            if (siguiente) {
                cuerpo.insertBefore(siguiente, fila);
                sincronizarOrden();
                fila.querySelector('.bajar').focus();
            }
        });

        fila.querySelector('.quitar-linea').addEventListener('click', () => {
            // Se saca de la tabla y por tanto de la lista de orden. Nada se
            // borra en la base hasta guardar, y si esa línea tenía resultados
            // capturados el servidor lo va a preguntar antes de aplicarlo.
            fila.remove();
            sincronizarOrden();
        });

        activarMarcaContinuacion(fila);
    }

    if (botonAgregar && plantilla) {
        botonAgregar.addEventListener('click', () => {
            contadorNuevas += 1;
            const clave = 'N' + contadorNuevas;
            const html = plantilla.innerHTML.replaceAll('__CLAVE__', clave);
            const envoltura = document.createElement('tbody');
            envoltura.innerHTML = html.trim();
            const nueva = envoltura.querySelector('.linea-espec');
            cuerpo.appendChild(nueva);
            activarFila(nueva);
            sincronizarOrden();
            nueva.querySelector('.texto-linea').focus();
        });
    }

    filas().forEach(activarFila);
    sincronizarOrden();
})();
