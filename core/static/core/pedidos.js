(function () {
    'use strict';

    function debounce(fn, espera) {
        let temporizador;
        return function (...args) {
            clearTimeout(temporizador);
            temporizador = setTimeout(() => fn.apply(this, args), espera);
        };
    }

    function attachAutocomplete(input, url, onSelect) {
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
                li.textContent = item.texto;
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

        attachAutocomplete(buscarProducto, '/api/productos/', (item) => {
            buscarProducto.value = item.texto;
            productoHidden.value = item.valor;
            unidad.value = item.unidad;

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
        });

        renglon.querySelector('[name$="-peso_bruto"]').addEventListener('input', () => actualizarPesoNeto(renglon));
        renglon.querySelector('[name$="-peso_tara"]').addEventListener('input', () => actualizarPesoNeto(renglon));
        actualizarPesoNeto(renglon);

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
