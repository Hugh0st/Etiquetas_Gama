(function () {
    'use strict';

    function debounce(fn, espera) {
        let temporizador;
        return function (...args) {
            clearTimeout(temporizador);
            temporizador = setTimeout(() => fn.apply(this, args), espera);
        };
    }

    // renderItem es opcional: recibe el <li> y el resultado para pintarlo a
    // mano. Sin él, el <li> muestra item.texto tal cual.
    function attachAutocomplete(input, url, onSelect, renderItem) {
        const lista = input.nextElementSibling;
        let activo = -1;

        function ocultar() {
            lista.hidden = true;
            lista.innerHTML = '';
            activo = -1;
        }

        function marcarActivo() {
            [...lista.children].forEach((li, i) => li.classList.toggle('activo', i === activo));
        }

        const buscar = debounce(async () => {
            const q = input.value.trim();
            if (q.length < 1) {
                ocultar();
                return;
            }
            const resp = await fetch(url + '?q=' + encodeURIComponent(q));
            const datos = await resp.json();
            lista.innerHTML = '';
            activo = -1;
            datos.forEach((item) => {
                const li = document.createElement('li');
                if (renderItem) {
                    renderItem(li, item);
                } else {
                    li.textContent = item.texto;
                }
                li.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    onSelect(item);
                    ocultar();
                });
                li.dataset.item = JSON.stringify(item);
                lista.appendChild(li);
            });
            lista.hidden = datos.length === 0;
        }, 200);

        input.addEventListener('input', buscar);

        input.addEventListener('keydown', (e) => {
            if (lista.hidden) return;
            const items = [...lista.children];
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                activo = Math.min(activo + 1, items.length - 1);
                marcarActivo();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                activo = Math.max(activo - 1, 0);
                marcarActivo();
            } else if (e.key === 'Enter') {
                if (activo >= 0 && items[activo]) {
                    e.preventDefault();
                    onSelect(JSON.parse(items[activo].dataset.item));
                    ocultar();
                }
            } else if (e.key === 'Escape') {
                ocultar();
            }
        });

        input.addEventListener('blur', () => setTimeout(ocultar, 150));
    }

    function activarBuscadorCliente() {
        const input = document.getElementById('buscar-cliente');
        if (!input) return;
        const hidden = document.getElementById('id_cliente');
        attachAutocomplete(input, '/api/clientes/', (item) => {
            input.value = item.texto;
            hidden.value = item.valor;
        });
    }

    // Mismo criterio que normalizar_descripcion() en el servidor: si no
    // coincidieran, la casilla podría aparecer por una diferencia que el
    // servidor no considera diferencia (espacios dobles o minúsculas).
    function normalizarDescripcion(texto) {
        return (texto || '').trim().replace(/\s+/g, ' ').toUpperCase();
    }

    // Maneja los dos avisos del campo de descripción:
    //
    // - La casilla de "corregir también en el catálogo" solo aparece cuando lo
    //   escrito es realmente distinto a lo que el catálogo tiene hoy. Si el
    //   usuario regresa al texto original, se oculta y se desmarca: no tiene
    //   sentido "corregir" con lo mismo.
    // - El aviso de que el producto no trae descripción en el catálogo (hay 19
    //   así), para que no se pase de largo y la etiqueta salga sin nombre.
    //
    // Esto es solo la pantalla: quien decide si se toca el catálogo es el
    // servidor, y nada de esto bloquea el guardado.
    function activarDescripcion(renglon) {
        const campo = renglon.querySelector('.campo-descripcion');
        const descripcion = renglon.querySelector('[name$="-descripcion"]');
        const producto = renglon.querySelector('[name$="-producto"]');
        const casilla = renglon.querySelector('.corregir-catalogo');
        const marca = casilla.querySelector('input[type="checkbox"]');
        const avisoSinCatalogo = renglon.querySelector('.aviso-sin-descripcion');

        function revisar() {
            const catalogo = normalizarDescripcion(renglon.dataset.descripcionCatalogo);
            const escrito = normalizarDescripcion(descripcion.value);
            // Mientras no haya producto elegido no hay catálogo que corregir
            // ni del que avisar.
            const hayProducto = producto.value !== '';

            const faltaEnCatalogo = hayProducto && catalogo === '';
            avisoSinCatalogo.hidden = !faltaEnCatalogo;
            campo.classList.toggle('sin-catalogo', faltaEnCatalogo);

            // Un producto sin descripción en el catálogo también cuenta como
            // distinto: llenarla es la misma clase de arreglo que enderezar
            // un nombre invertido.
            const distinto = hayProducto && escrito !== '' && escrito !== catalogo;
            casilla.hidden = !distinto;
            if (!distinto) marca.checked = false;
        }

        descripcion.addEventListener('input', revisar);
        return revisar;
    }

    function actualizarPesoNeto(renglon) {
        const bruto = parseFloat(renglon.querySelector('[name$="-peso_bruto"]').value);
        const tara = parseFloat(renglon.querySelector('[name$="-peso_tara"]').value);
        const salida = renglon.querySelector('.peso-neto');
        salida.value = (!isNaN(bruto) && !isNaN(tara)) ? (bruto - tara).toFixed(3) : '';
    }

    function activarRenglon(renglon) {
        const buscarProducto = renglon.querySelector('.buscar-producto');
        const productoHidden = renglon.querySelector('[name$="-producto"]');
        const unidad = renglon.querySelector('[name$="-unidad"]');
        const cas = renglon.querySelector('[name$="-cas"]');
        const onu = renglon.querySelector('[name$="-onu"]');
        const descripcion = renglon.querySelector('[name$="-descripcion"]');
        const revisarDescripcion = activarDescripcion(renglon);

        attachAutocomplete(buscarProducto, '/api/productos/', (item) => {
            // Solo el modelo: el campo de al lado es el del nombre, y dejar
            // aquí "E7000 — NOMBRE" invita a escribir el modelo también allá.
            buscarProducto.value = item.valor;
            productoHidden.value = item.valor;
            unidad.value = item.unidad;

            // Al cambiar de producto la descripción se rehace con la del
            // nuevo: lo que se hubiera corregido para el anterior ya no
            // aplica, y dejarlo sería imprimir un nombre que no es.
            renglon.dataset.descripcionCatalogo = item.descripcion;
            descripcion.value = item.descripcion;
            revisarDescripcion();

            if (item.cas) {
                cas.value = item.cas;
                cas.readOnly = true;
            } else {
                cas.value = '';
                cas.readOnly = false;
            }

            if (item.onu) {
                onu.value = item.onu;
                onu.readOnly = true;
            } else {
                onu.value = '';
                onu.readOnly = false;
            }
        }, (li, item) => {
            // El modelo y el nombre van en dos columnas, no como una sola
            // frase: el formato "E7000 — NOMBRE" era justo lo que invitaba a
            // copiarlo completo al campo de descripción.
            const modelo = document.createElement('span');
            modelo.className = 'resultado-modelo';
            modelo.textContent = item.valor;

            const nombre = document.createElement('span');
            nombre.className = 'resultado-nombre';
            if (item.descripcion) {
                nombre.textContent = item.descripcion;
            } else {
                // Se avisa desde aquí, antes de elegirlo, no solo después.
                nombre.textContent = 'sin descripción en el catálogo';
                nombre.classList.add('resultado-nombre-vacio');
            }

            li.append(modelo, nombre);
        });

        renglon.querySelector('[name$="-peso_bruto"]').addEventListener('input', () => actualizarPesoNeto(renglon));
        renglon.querySelector('[name$="-peso_tara"]').addEventListener('input', () => actualizarPesoNeto(renglon));
        actualizarPesoNeto(renglon);

        // Al abrir la pantalla: si este renglón ya traía una descripción
        // distinta a la del catálogo (porque se corrigió antes sin marcar la
        // casilla), la casilla aparece ofreciendo corregirlo ahora; y si el
        // producto no tiene descripción en el catálogo, sale el aviso.
        revisarDescripcion();

        renglon.querySelector('.quitar-renglon').addEventListener('click', () => {
            renglon.querySelector('[name$="-DELETE"]').checked = true;
            renglon.style.display = 'none';
        });
    }

    function activarAgregarRenglon() {
        const lista = document.getElementById('renglones-lista');
        const boton = document.getElementById('agregar-renglon');
        const plantilla = document.getElementById('renglon-vacio');
        if (!lista || !boton || !plantilla) return;

        const prefix = lista.dataset.prefix;
        const totalForms = document.getElementById('id_' + prefix + '-TOTAL_FORMS');

        boton.addEventListener('click', () => {
            const index = parseInt(totalForms.value, 10);
            const html = plantilla.innerHTML.replaceAll('__prefix__', index);
            const envoltura = document.createElement('div');
            envoltura.innerHTML = html.trim();
            const nuevoRenglon = envoltura.firstElementChild;
            lista.appendChild(nuevoRenglon);
            activarRenglon(nuevoRenglon);
            totalForms.value = index + 1;
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        activarBuscadorCliente();
        document.querySelectorAll('#renglones-lista .renglon').forEach(activarRenglon);
        activarAgregarRenglon();
    });
})();
