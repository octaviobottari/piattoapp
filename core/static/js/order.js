// Removed: const csrftoken = typeof window.csrftoken !== 'undefined' ? window.csrftoken : getCookie('csrftoken');

// Log csrftoken for debugging
console.log('CSRF Token from base.html:', window.csrftoken);

function getCsrfToken() {
    console.log('getCsrfToken called');
    let token = window.csrftoken;
    if (!token) {
        console.warn('window.csrftoken is undefined, attempting fallback');
        // Try cookie
        token = getCookie('csrftoken');
        console.log('Token from cookie:', token);
        // Try form input
        if (!token) {
            const csrfInput = document.querySelector('#csrf-form input[name="csrfmiddlewaretoken"]');
            if (csrfInput) {
                token = csrfInput.value;
                console.log('Token from form:', token);
            }
        }
        // Update window.csrftoken for future use
        if (token) {
            window.csrftoken = token;
        }
    }
    console.log('Final CSRF token:', token);
    return token;
}

// Function to get cookie (duplicated here for completeness, ideally defined once)
function getCookie(name) {
    console.log('getCookie called for:', name);
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    console.log('Cookie value:', cookieValue);
    return cookieValue;
}

// Rest of the variables unchanged
let tipoPedido = '';
let pedidoData = {
    productos: [],
    datosCliente: {},
    subtotal: 0,
    costoEnvio: 0,
    montoDescuento: 0,
    montoDescuentoCodigo: 0,
    montoDescuentoEfectivo: 0,
    subtotalAjustado: 0,
    total: 0,
    descuentoPorcentaje: 0,
    cashDiscountApplied: false,
    cashDiscountPercentage: window.cashDiscountPercentage || 0,
    codigoDescuentoValido: true,
    codigoDescuento: ''
};

// Función para parsear precios, manejando comas y valores no numéricos
function parsePrice(value) {
    if (typeof value === 'string') {
        value = value.replace(',', '.');
    }
    return isNaN(parseFloat(value)) ? 0 : parseFloat(value);
}

// Función para redondear a dos decimales
function roundToTwoDecimals(value) {
    return Math.round(value * 100) / 100;
}

function showErrorModal(message) {
    console.log('showErrorModal called:', message);
    try {
        const errorMessageElement = document.getElementById('error-message');
        const modalElement = document.getElementById('modalError');
        if (!errorMessageElement || !modalElement) {
            console.error('Error modal elements not found:', { errorMessageElement, modalElement });
            return;
        }
        errorMessageElement.textContent = message;
        const modal = bootstrap.Modal.getInstance(modalElement) || new bootstrap.Modal(modalElement, { backdrop: true });
        modal.show();
    } catch (e) {
        console.error('showErrorModal error:', e);
    }
}

function hideAllModals() {
    console.log('hideAllModals called');
    try {
        document.querySelectorAll('.modal.show').forEach(modal => {
            const modalInstance = bootstrap.Modal.getInstance(modal);
            if (modalInstance) {
                modalInstance.hide();
            }
        });
        document.querySelectorAll('.modal-backdrop').forEach(backdrop => backdrop.remove());
    } catch (e) {
        console.error('hideAllModals error:', e);
    }
}

function sanitizeInput(input) {
    console.log('sanitizeInput called:', input);
    try {
        const div = document.createElement('div');
        div.textContent = input;
        return div.innerHTML;
    } catch (e) {
        console.error('sanitizeInput error:', e);
        return input;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOMContentLoaded fired');
    try {
        const siguienteBtnPaso3 = document.getElementById('siguiente-paso3-btn');
        if (siguienteBtnPaso3) {
            console.log('siguiente-paso3-btn bound');
        } else {
            console.error('siguiente-paso3-btn not found');
        }

        const verificarBtnResumen = document.getElementById('verificar-codigo-resumen-btn');
        const siguienteBtnResumen = document.getElementById('siguiente-resumen-pedido-btn');
        if (verificarBtnResumen) {
            verificarBtnResumen.addEventListener('click', verificarCodigoDescuentoResumen);
            console.log('verificar-codigo-resumen-btn bound');
        } else {
            console.error('verificar-codigo-resumen-btn not found');
        }
        if (siguienteBtnResumen) {
            console.log('siguiente-resumen-pedido-btn bound');
        } else {
            console.error('siguiente-resumen-pedido-btn not found');
        }

        const metodoPagoSelect = document.getElementById('metodo_pago_resumen');
        if (metodoPagoSelect) {
            metodoPagoSelect.value = '';
            metodoPagoSelect.addEventListener('change', () => {
                updateAclaracionesPlaceholder();
                actualizarResumen(true);
                mostrarResumenPedido();
            });
            console.log('metodo_pago_resumen select bound');
        } else {
            console.error('metodo_pago_resumen select not found');
        }

        // Enforce max selections for checkboxes
        document.querySelectorAll('.opcion-categoria').forEach(categoria => {
            const inputs = categoria.querySelectorAll('input[type="checkbox"]');
            const maxSelecciones = parseInt(inputs[0]?.dataset.maxSelecciones) || 1;
            inputs.forEach(input => {
                input.addEventListener('change', function() {
                    const categoriaId = this.dataset.categoriaId;
                    const checkedInputs = categoria.querySelectorAll(`input[name="opciones_${input.name.split('_')[1]}_${categoriaId}"]:checked`);
                    const errorElement = document.getElementById(`opcion-error-${input.name.split('_')[1]}-${categoriaId}`);
                    if (checkedInputs.length > maxSelecciones) {
                        this.checked = false;
                        if (errorElement) {
                            errorElement.style.display = 'block';
                            errorElement.textContent = `Máximo ${maxSelecciones} opción(es) permitida(s).`;
                        }
                    } else {
                        if (errorElement) {
                            errorElement.style.display = 'none';
                        }
                        actualizarPrecioModal(input.name.split('_')[1]);
                    }
                });
            });
        });
    } catch (e) {
        console.error('DOMContentLoaded error:', e);
    }

    document.querySelectorAll('[id^="productoModal"]').forEach(modal => {
        modal.addEventListener('show.bs.modal', function() {
            try {
                const productoId = this.id.replace('productoModal', '');
                console.log('Modal show:', productoId);
                const productCard = document.querySelector(`.product [data-bs-target="#productoModal${productoId}"]`)?.closest('.product');
                const precioBase = parseFloat(productCard?.dataset.precioBase) || 0;
                this.querySelector('.modal-body').dataset.precioBase = precioBase;
                const cantidadInput = document.getElementById(`cantidad_${productoId}`);
                if (cantidadInput) cantidadInput.value = 1;
                const opciones = document.querySelectorAll(`#opciones-container-${productoId} input`);
                opciones.forEach(opcion => opcion.checked = false);
                const errorElements = document.querySelectorAll(`#opciones-container-${productoId} .text-danger`);
                errorElements.forEach(error => error.style.display = 'none');
                actualizarPrecioModal(productoId);
            } catch (e) {
                console.error('Modal show error:', e);
            }
        });

        modal.addEventListener('hide.bs.modal', function() {
            try {
                const productoId = this.id.replace('productoModal', '');
                console.log('Modal hide:', productoId);
                const cantidadInput = document.getElementById(`cantidad_${productoId}`);
                if (cantidadInput) cantidadInput.value = 1;
                const opciones = document.querySelectorAll(`#opciones-container-${productoId} input`);
                opciones.forEach(opcion => opcion.checked = false);
                const totalElement = document.getElementById(`total-modal-${productoId}`);
                if (totalElement) {
                    const productCard = document.querySelector(`.product [data-bs-target="#productoModal${productoId}"]`)?.closest('.product');
                    const precioBase = parseFloat(productCard?.dataset.precioBase) || 0;
                    totalElement.textContent = `$${precioBase.toFixed(2)}`;
                }
            } catch (e) {
                console.error('Modal hide error:', e);
            }
        });
    });
});

function updateAclaracionesPlaceholder() {
    console.log('updateAclaracionesPlaceholder called');
    try {
        const metodoPago = document.getElementById('metodo_pago_resumen')?.value;
        const aclaraciones = document.getElementById('aclaraciones');
        if (!aclaraciones) {
            console.error('aclaraciones textarea not found');
            return;
        }
        if (metodoPago === 'efectivo') {
            aclaraciones.placeholder = 'Por favor, indique con cuánto pagará para preparar el cambio (ej. $5000).';
        } else {
            aclaraciones.placeholder = 'Ej. Sin sal, entrega en puerta';
        }
    } catch (e) {
        console.error('updateAclaracionesPlaceholder error:', e);
    }
}

function navigateBack(currentModalId) {
    console.log('navigateBack called:', currentModalId);
    try {
        hideAllModals();
        let previousModalId = '';
        switch (currentModalId) {
            case 'modalResumen':
                previousModalId = 'modalPaso3';
                break;
            case 'modalPaso3':
                previousModalId = 'modalPaso2';
                break;
            case 'modalPaso2':
                previousModalId = 'modalResumenPedido';
                break;
            case 'modalResumenPedido':
            case 'productoModal':
                return;
            default:
                console.error('Unknown modal ID:', currentModalId);
                return;
        }
        if (previousModalId) {
            const previousModalElement = document.getElementById(previousModalId);
            if (previousModalElement) {
                const previousModal = new bootstrap.Modal(previousModalElement, { backdrop: true });
                previousModal.show();
            } else {
                console.error('Previous modal not found:', previousModalId);
            }
        }
    } catch (e) {
        console.error('navigateBack error:', e);
    }
}

function limpiarCodigoDescuentoResumen() {
    console.log('limpiarCodigoDescuentoResumen called');
    try {
        const codigoInput = document.querySelector('input[name="codigo_descuento_resumen"]');
        const feedbackElement = document.getElementById('codigo-descuento-resumen-feedback');
        const siguienteBtn = document.getElementById('siguiente-resumen-pedido-btn');
        if (!codigoInput || !feedbackElement || !siguienteBtn) {
            console.error('Missing elements:', { codigoInput, feedbackElement, siguienteBtn });
            return;
        }
        codigoInput.value = '';
        feedbackElement.textContent = '';
        feedbackElement.className = 'resumen-pedido-feedback mt-2';
        feedbackElement.style.display = 'none';
        pedidoData.codigoDescuentoValido = true;
        pedidoData.codigoDescuento = '';
        pedidoData.descuentoPorcentaje = 0;
        pedidoData.montoDescuentoCodigo = 0;
        actualizarResumen(true);
        mostrarResumenPedido();
        console.log('Discount code cleared in resumen pedido');
    } catch (e) {
        console.error('limpiarCodigoDescuentoResumen error:', e);
    }
}

function verificarCodigoDescuentoResumen() {
    console.log('verificarCodigoDescuentoResumen called');
    try {
        const codigoInput = document.querySelector('input[name="codigo_descuento_resumen"]');
        const feedbackElement = document.getElementById('codigo-descuento-resumen-feedback');
        const verifyButton = document.getElementById('verificar-codigo-resumen-btn');
        const siguienteBtn = document.getElementById('siguiente-resumen-pedido-btn');
        if (!codigoInput || !feedbackElement || !verifyButton || !siguienteBtn) {
            console.error('Missing elements:', { codigoInput, feedbackElement, verifyButton, siguienteBtn });
            showErrorModal('Error: No se encontraron los elementos del formulario.');
            return;
        }
        const codigo = codigoInput.value.trim().toUpperCase();
        console.log('Código ingresado:', codigo);
        if (!codigo) {
            feedbackElement.textContent = 'Ingresa un código o déjalo en blanco.';
            feedbackElement.className = 'resumen-pedido-feedback mt-2 text-info';
            feedbackElement.style.display = 'block';
            pedidoData.codigoDescuentoValido = true;
            pedidoData.codigoDescuento = '';
            pedidoData.descuentoPorcentaje = 0;
            pedidoData.montoDescuentoCodigo = 0;
            actualizarResumen(true);
            mostrarResumenPedido();
            console.log('No code entered');
            return;
        }
        if (!window.validarCodigoUrl) {
            console.error('validarCodigoUrl is undefined');
            feedbackElement.textContent = 'Error: No se pudo conectar con el servidor. Por favor, déjalo en blanco.';
            feedbackElement.className = 'resumen-pedido-feedback mt-2 text-danger';
            feedbackElement.style.display = 'block';
            pedidoData.codigoDescuentoValido = true;
            pedidoData.codigoDescuento = '';
            pedidoData.descuentoPorcentaje = 0;
            pedidoData.montoDescuentoCodigo = 0;
            codigoInput.value = '';
            actualizarResumen(true);
            mostrarResumenPedido();
            showErrorModal('Error de configuración del servidor. Usa el botón Limpiar para continuar.');
            return;
        }
        const csrftoken = getCsrfToken();
        if (!csrftoken) {
            console.error('CSRF token is missing or invalid:', csrftoken);
            feedbackElement.textContent = 'Error: No se pudo obtener el token de seguridad. Por favor, recarga la página.';
            feedbackElement.className = 'resumen-pedido-feedback mt-2 text-danger';
            feedbackElement.style.display = 'block';
            pedidoData.codigoDescuentoValido = true;
            pedidoData.codigoDescuento = '';
            pedidoData.descuentoPorcentaje = 0;
            pedidoData.montoDescuentoCodigo = 0;
            codigoInput.value = '';
            actualizarResumen(true);
            mostrarResumenPedido();
            showErrorModal('Error: Token de seguridad no disponible. Por favor, recarga la página.');
            return;
        }
        console.log('CSRF Token:', csrftoken);
        verifyButton.disabled = true;
        verifyButton.textContent = 'Verificando...';
        const formData = new FormData();
        formData.append('codigo', codigo);
        console.log('Sending fetch to:', window.validarCodigoUrl);
        fetch(window.validarCodigoUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': csrftoken
            },
            credentials: 'include'
        })
        .then(response => {
            console.log('Fetch response:', {
                status: response.status,
                statusText: response.statusText,
                url: response.url
            });
            if (!response.ok) {
                return response.text().then(text => {
                    throw new Error(`HTTP error ${response.status}: ${text}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Fetch data:', data);
            if (data.valid) {
                pedidoData.descuentoPorcentaje = parseFloat(data.porcentaje);
                pedidoData.codigoDescuentoValido = true;
                pedidoData.codigoDescuento = codigo;
                feedbackElement.textContent = `Código válido: ${data.porcentaje}% de descuento aplicado.`;
                feedbackElement.className = 'resumen-pedido-feedback mt-2 text-success';
                siguienteBtn.disabled = false;
            } else {
                pedidoData.descuentoPorcentaje = 0;
                pedidoData.montoDescuentoCodigo = 0;
                pedidoData.codigoDescuentoValido = false;
                pedidoData.codigoDescuento = '';
                feedbackElement.textContent = data.error || 'Código no válido. Por favor, intenta de nuevo o déjalo en blanco.';
                feedbackElement.className = 'resumen-pedido-feedback mt-2 text-danger';
                codigoInput.value = '';
                siguienteBtn.disabled = false;
            }
            actualizarResumen(true);
            feedbackElement.style.display = 'block';
            mostrarResumenPedido();
        })
        .catch(error => {
            console.error('Fetch error:', error);
            feedbackElement.textContent = `Error al verificar el código: ${error.message}. Por favor, déjalo en blanco o recarga la página.`;
            feedbackElement.className = 'resumen-pedido-feedback mt-2 text-danger';
            feedbackElement.style.display = 'block';
            pedidoData.descuentoPorcentaje = 0;
            pedidoData.montoDescuentoCodigo = 0;
            pedidoData.codigoDescuentoValido = false;
            pedidoData.codigoDescuento = '';
            actualizarResumen(true);
            mostrarResumenPedido();
            showErrorModal(`Error al verificar el código: ${error.message}. Por favor, recarga la página.`);
        })
        .finally(() => {
            verifyButton.disabled = false;
            verifyButton.textContent = 'Verificar';
        });
    } catch (e) {
        console.error('verificarCodigoDescuentoResumen error:', e);
        showErrorModal('Error al verificar el código de descuento. Por favor, recarga la página.');
    }
}

function addToOrder(productoId, nombre, precioBase, cantidad) {
    console.log('addToOrder called:', { productoId, nombre, precioBase, cantidad });
    try {
        const finalCantidad = Math.max(1, parseInt(cantidad) || 1);
        if (!productoId || !nombre || isNaN(precioBase) || isNaN(finalCantidad)) {
            console.error('Invalid parameters:', { productoId, nombre, precioBase, finalCantidad });
            showErrorModal('Error al añadir el producto. Por favor, verifica los datos.');
            return;
        }
        agregarAlPedido(productoId, nombre, precioBase, finalCantidad, []);
    } catch (e) {
        console.error('addToOrder error:', e);
        showErrorModal('Error al añadir el producto.');
    }
}

function addToOrderFromModal(productoId, nombre, precioBase) {
    console.log('addToOrderFromModal called:', { productoId, nombre, precioBase });
    try {
        const cantidadInput = document.getElementById(`cantidad_${productoId}`);
        const cantidad = parseInt(cantidadInput?.value) || 1;
        const productCard = document.querySelector(`.product [data-bs-target="#productoModal${productoId}"]`)?.closest('.product');
        const tieneOpciones = productCard?.dataset.tieneOpciones === 'true';

        let opcionesSeleccionadas = [];
        if (tieneOpciones) {
            let allCategoriesValid = true;
            document.querySelectorAll(`#opciones-container-${productoId} .opcion-categoria`).forEach(categoria => {
                const categoriaId = categoria.querySelector('input')?.dataset.categoriaId;
                const maxSelecciones = parseInt(categoria.querySelector('input')?.dataset.maxSelecciones) || 1;
                const inputs = categoria.querySelectorAll(`input[name="opciones_${productoId}_${categoriaId}"]:checked`);
                const errorElement = document.getElementById(`opcion-error-${productoId}-${categoriaId}`);

                if (maxSelecciones > 0 && inputs.length === 0) {
                    if (errorElement) {
                        errorElement.style.display = 'block';
                        errorElement.textContent = 'Selecciona al menos una opción.';
                    }
                    allCategoriesValid = false;
                } else if (inputs.length > maxSelecciones) {
                    if (errorElement) {
                        errorElement.style.display = 'block';
                        errorElement.textContent = `Máximo ${maxSelecciones} opción(es).`;
                    }
                    allCategoriesValid = false;
                } else {
                    if (errorElement) errorElement.style.display = 'none';
                    inputs.forEach(input => {
                        const label = input.nextElementSibling.textContent.trim().split(' (+$')[0];
                        const precioAdicional = parsePrice(input.dataset.precioAdicional);
                        opcionesSeleccionadas.push({
                            id: input.value,
                            nombre: label,
                            precio_adicional: precioAdicional,
                            categoria_id: categoriaId
                        });
                    });
                }
            });
            if (!allCategoriesValid) {
                console.log('Invalid options selection');
                return;
            }
        }
        console.log('Opciones seleccionadas:', opcionesSeleccionadas);
        agregarAlPedido(productoId, nombre, precioBase, cantidad, opcionesSeleccionadas);

        const modalElement = document.getElementById(`productoModal${productoId}`);
        if (modalElement) {
            const modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) modal.hide();
        }
    } catch (e) {
        console.error('addToOrderFromModal error:', e);
        showErrorModal('Error al añadir el producto desde el modal.');
    }
}

function agregarAlPedido(productoId, nombre, precioBase, cantidad, opcionesSeleccionadas) {
    console.log('agregarAlPedido called:', { productoId, nombre, precioBase, cantidad, opcionesSeleccionadas });
    try {
        let precioAdicional = 0;
        let opcionesData = [];
        if (opcionesSeleccionadas && opcionesSeleccionadas.length > 0) {
            opcionesSeleccionadas.forEach(opcion => {
                const adicional = parsePrice(opcion.precio_adicional);
                precioAdicional += adicional;
                opcionesData.push(opcion);
            });
        }
        const precioUnitario = roundToTwoDecimals(parseFloat(precioBase) + precioAdicional);
        const precioTotal = roundToTwoDecimals(precioUnitario * cantidad);

        const existingProductIndex = pedidoData.productos.findIndex(p =>
            p.id === productoId && JSON.stringify(p.opciones) === JSON.stringify(opcionesData)
        );
        if (existingProductIndex >= 0) {
            pedidoData.productos[existingProductIndex].cantidad += cantidad;
            pedidoData.productos[existingProductIndex].precio_total = roundToTwoDecimals(pedidoData.productos[existingProductIndex].precio_total + precioTotal);
        } else {
            const nuevoProducto = {
                id: productoId,
                nombre: nombre,
                cantidad: cantidad,
                precio_unitario: precioUnitario,
                precio_total: precioTotal,
                opciones: opcionesData
            };
            pedidoData.productos.push(nuevoProducto);
        }
        actualizarResumen(true);
    } catch (e) {
        console.error('agregarAlPedido error:', e);
    }
}

function actualizarResumen(isResumenFinal = false) {
    console.log('actualizarResumen called, isResumenFinal:', isResumenFinal);
    try {
        let subtotal = 0;
        let cantidadTotal = 0;
        pedidoData.productos.forEach(producto => {
            subtotal += producto.precio_total;
            cantidadTotal += producto.cantidad;
        });
        pedidoData.subtotal = roundToTwoDecimals(subtotal);

        let costoEnvio = 0;
        if (isResumenFinal && tipoPedido === 'delivery') {
            const costoBase = parseFloat(window.costoEnvioBase) || 0;
            const umbralGratis = parseFloat(window.umbralEnvioGratis) || 0;
            if (costoBase > 0) {
                costoEnvio = costoBase;
                if (umbralGratis > 0 && pedidoData.subtotal >= umbralGratis) {
                    costoEnvio = 0;
                }
            }
        }
        pedidoData.costoEnvio = roundToTwoDecimals(costoEnvio);

        // Aplicar descuento en efectivo solo si está habilitado
        const metodoPago = document.getElementById('metodo_pago_resumen')?.value;
        if (metodoPago === 'efectivo' && window.cashDiscountEnabled && pedidoData.cashDiscountPercentage > 0) {
            pedidoData.montoDescuentoEfectivo = roundToTwoDecimals(pedidoData.subtotal * (pedidoData.cashDiscountPercentage / 100));
            pedidoData.cashDiscountApplied = true;
        } else {
            pedidoData.montoDescuentoEfectivo = 0;
            pedidoData.cashDiscountApplied = false;
        }

        // Calcular subtotal ajustado después del descuento en efectivo
        pedidoData.subtotalAjustado = roundToTwoDecimals(pedidoData.subtotal - pedidoData.montoDescuentoEfectivo);

        // Aplicar descuento por código sobre el subtotal ajustado
        pedidoData.montoDescuentoCodigo = pedidoData.descuentoPorcentaje ? roundToTwoDecimals(pedidoData.subtotalAjustado * (pedidoData.descuentoPorcentaje / 100)) : 0;

        // Total descuento
        pedidoData.montoDescuento = roundToTwoDecimals(pedidoData.montoDescuentoEfectivo + pedidoData.montoDescuentoCodigo);

        // Calcular total
        pedidoData.total = roundToTwoDecimals(pedidoData.subtotalAjustado - pedidoData.montoDescuentoCodigo + (isResumenFinal ? pedidoData.costoEnvio : 0));

        const stickyBar = document.getElementById('stickyOrderBar');
        const cantidadProductos = document.getElementById('cantidad-productos');
        const totalPedido = document.getElementById('total-pedido');
        if (!stickyBar || !cantidadProductos || !totalPedido) {
            console.error('Resumen elements missing:', { stickyBar, cantidadProductos, totalPedido });
            return;
        }
        cantidadProductos.textContent = cantidadTotal;
        totalPedido.textContent = pedidoData.total.toFixed(2);
        stickyBar.style.display = pedidoData.productos.length > 0 ? 'flex' : 'none';
    } catch (e) {
        console.error('actualizarResumen error:', e);
    }
}

function eliminarProducto(index) {
    console.log('eliminarProducto called:', { index });
    try {
        const producto = pedidoData.productos[index];
        if (producto) {
            if (producto.cantidad > 1) {
                producto.cantidad -= 1;
                producto.precio_total = roundToTwoDecimals(producto.precio_total - producto.precio_unitario);
            } else {
                pedidoData.productos.splice(index, 1);
            }
            actualizarResumen(true);
            if (pedidoData.productos.length === 0) {
                pedidoData.codigoDescuento = '';
                pedidoData.descuentoPorcentaje = 0;
                pedidoData.montoDescuento = 0;
                pedidoData.montoDescuentoCodigo = 0;
                pedidoData.montoDescuentoEfectivo = 0;
                pedidoData.subtotalAjustado = 0;
                pedidoData.codigoDescuentoValido = true;
                const codigoInput = document.querySelector('input[name="codigo_descuento_resumen"]');
                if (codigoInput) {
                    codigoInput.value = '';
                }
                const feedbackElement = document.getElementById('codigo-descuento-resumen-feedback');
                if (feedbackElement) {
                    feedbackElement.textContent = '';
                    feedbackElement.className = 'resumen-pedido-feedback mt-2';
                    feedbackElement.style.display = 'none';
                }
                const modalElement = document.getElementById('modalResumenPedido');
                if (modalElement) {
                    const modal = bootstrap.Modal.getInstance(modalElement);
                    if (modal) modal.hide();
                }
                hideAllModals();
            }
            actualizarResumen(true);
            mostrarResumenPedido();
        }
    } catch (e) {
        console.error('eliminarProducto error:', e);
    }
}

function mostrarResumenPedido() {
    console.log('mostrarResumenPedido called');
    try {
        if (!tipoPedido && window.costoEnvioBase > 0) {
            tipoPedido = 'delivery';
            pedidoData.tipoPedido = 'delivery';
        }
        actualizarResumen(false); // No incluir costoEnvio en esta etapa

        const resumenPedido = document.getElementById('resumen-pedido');
        const costoEnvioLine = document.getElementById('costo-envio-line-resumen-pedido');
        const costoEnvioElement = document.getElementById('costo-envio-resumen-pedido');
        if (!resumenPedido || !costoEnvioElement) {
            console.error('Resumen elements not found:', { resumenPedido, costoEnvioElement });
            showErrorModal('Error: No se encontraron los elementos del resumen.');
            return;
        }

        resumenPedido.innerHTML = '';
        pedidoData.productos.forEach((producto, index) => {
            const div = document.createElement('div');
            div.className = 'order-item';
            let opcionesHtml = '';
            if (producto.opciones && producto.opciones.length > 0) {
                const groupedOptions = {};
                producto.opciones.forEach(op => {
                    if (!groupedOptions[op.categoria_id]) {
                        groupedOptions[op.categoria_id] = [];
                    }
                    groupedOptions[op.categoria_id].push(op);
                });
                for (const categoriaId in groupedOptions) {
                    const options = groupedOptions[categoriaId];
                    const categoriaNombre = options[0].nombre.split(' (')[0];
                    const opcionesList = options.map(op => {
                        const precioAdicional = op.precio_adicional > 0 ? ` (+$${op.precio_adicional.toFixed(2)})` : '';
                        return `+ ${op.nombre}${precioAdicional}`;
                    }).join('<br>');
                    opcionesHtml += `<p class="option"><span class="category">Elige ${categoriaNombre}:</span><br>${opcionesList}</p>`;
                }
            }
            div.innerHTML = `
                <div class="item-details">
                    <p class="modal-title">${producto.nombre}</p>
                    <span class="producto-cantidad">${producto.cantidad}x <span class="item-price">$${producto.precio_unitario.toFixed(2)}</span></span>
                    ${opcionesHtml}
                    <p class="item-total">Total: $${producto.precio_total.toFixed(2)}</p>
                </div>
                <button type="button" class="btn resumen-pedido-btn-delete" onclick="eliminarProducto(${index})" aria-label="Eliminar producto">
                    <i class="fa-solid fa-trash"></i>
                </button>
            `;
            resumenPedido.appendChild(div);
        });

        const subtotalElement = document.getElementById('subtotal-pedido-resumen-pedido');
        const conDescuentoElement = document.getElementById('con-descuento-resumen-pedido');
        const conDescuentoLine = document.getElementById('con-descuento-line-resumen-pedido');
        const subtotalConDescuentosElement = document.getElementById('subtotal-con-descuentos-resumen-pedido');
        const subtotalConDescuentosLine = document.getElementById('subtotal-con-descuentos-line-resumen-pedido');
        const totalElement = document.getElementById('total-pedido-resumen-pedido');
        if (!subtotalElement || !conDescuentoElement || !conDescuentoLine || !subtotalConDescuentosElement || !subtotalConDescuentosLine || !totalElement) {
            console.error('Costos elements not found:', { subtotalElement, conDescuentoElement, conDescuentoLine, subtotalConDescuentosElement, subtotalConDescuentosLine, totalElement });
            return;
        }

        subtotalElement.textContent = `$${pedidoData.subtotal.toFixed(2)}`;
        costoEnvioLine.style.display = 'none'; // Ocultar costo de envío en modalResumenPedido
        costoEnvioElement.textContent = '';

        // Mostrar descuentos solo si existen
        let discountDetails = '';
        if (pedidoData.cashDiscountApplied && pedidoData.montoDescuentoEfectivo > 0) {
            discountDetails += `Descuento por Pago en Efectivo (${pedidoData.cashDiscountPercentage}%): -$${pedidoData.montoDescuentoEfectivo.toFixed(2)}<br>`;
        }
        if (pedidoData.montoDescuentoCodigo > 0) {
            discountDetails += `Descuento por Código (${pedidoData.codigoDescuento}, ${pedidoData.descuentoPorcentaje}%): -$${pedidoData.montoDescuentoCodigo.toFixed(2)}<br>`;
        }
        if (pedidoData.montoDescuento > 0) {
            discountDetails += `Total Descuentos: -$${pedidoData.montoDescuento.toFixed(2)}`;
            conDescuentoLine.style.display = 'block';
            conDescuentoElement.innerHTML = discountDetails;
            subtotalConDescuentosLine.style.display = 'block';
            const subtotalConDescuentos = roundToTwoDecimals(pedidoData.subtotal - pedidoData.montoDescuento);
            subtotalConDescuentosElement.textContent = `$${subtotalConDescuentos.toFixed(2)}`;
        } else {
            conDescuentoLine.style.display = 'none';
            conDescuentoElement.innerHTML = '';
            subtotalConDescuentosLine.style.display = 'none';
            subtotalConDescuentosElement.textContent = '';
        }

        totalElement.textContent = `$${pedidoData.total.toFixed(2)}`;

        const modalElement = document.getElementById('modalResumenPedido');
        if (modalElement) {
            const modal = bootstrap.Modal.getInstance(modalElement) || new bootstrap.Modal(modalElement, { backdrop: true });
            modal.show();
        }
    } catch (e) {
        console.error('mostrarResumenPedido error:', e);
    }
}

function mostrarPaso2() {
    console.log('mostrarPaso2 called');
    try {
        if (pedidoData.productos.length === 0) {
            showErrorModal('Por favor, selecciona al menos un producto.');
            return;
        }
        const metodoPago = document.getElementById('metodo_pago_resumen')?.value;
        if (!metodoPago) {
            showErrorModal('Por favor, selecciona un método de pago.');
            return;
        }
        const codigoInput = document.querySelector('input[name="codigo_descuento_resumen"]');
        const codigoDescuento = codigoInput?.value.trim().toUpperCase() || '';
        if (codigoDescuento && !pedidoData.codigoDescuentoValido) {
            console.log('Invalid discount code entered:', codigoDescuento);
            showErrorModal('Por favor, verifica el código de descuento, déjalo en blanco o usa el botón Limpiar.');
            return;
        }
        if (!tipoPedido && window.costoEnvioBase > 0) {
            tipoPedido = 'delivery';
            pedidoData.tipoPedido = 'delivery';
        }
        hideAllModals();
        const modalPaso2 = document.getElementById('modalPaso2');
        if (modalPaso2) {
            const modal = new bootstrap.Modal(modalPaso2, { backdrop: true });
            modal.show();
        }
    } catch (e) {
        console.error('mostrarPaso2 error:', e);
    }
}

function seleccionarTipoPedido(tipo) {
    console.log('seleccionarTipoPedido called:', tipo);
    try {
        tipoPedido = tipo;
        pedidoData.tipoPedido = tipo;
        hideAllModals();
        const modalPaso3 = document.getElementById('modalPaso3');
        const campoDireccion = document.getElementById('campo-direccion');
        const direccionInput = campoDireccion?.querySelector('input[name="direccion"]');
        if (campoDireccion) {
            campoDireccion.style.display = tipo === 'delivery' ? 'block' : 'none';
        }
        if (direccionInput) {
            if (tipo === 'delivery') {
                direccionInput.setAttribute('required', 'required');
            } else {
                direccionInput.removeAttribute('required');
            }
        }
        if (modalPaso3) {
            const modal = new bootstrap.Modal(modalPaso3, { backdrop: true });
            modal.show();
        }
        actualizarResumen(true);
    } catch (e) {
        console.error('seleccionarTipoPedido error:', e);
    }
}

function updateQuantity(productoId, change) {
    console.log('updateQuantity called:', { productoId, change });
    try {
        const cantidadInput = document.getElementById(`cantidad_${productoId}`);
        if (!cantidadInput) {
            console.error('Cantidad input not found for ID:', productoId);
            return;
        }
        let currentValue = parseInt(cantidadInput.value) || 1;
        const maxValue = parseInt(cantidadInput.getAttribute('max')) || Infinity;
        const minValue = parseInt(cantidadInput.getAttribute('min')) || 1;
        const newValue = Math.max(minValue, Math.min(maxValue, currentValue + change));
        if (newValue !== currentValue) {
            cantidadInput.value = newValue;
            actualizarPrecioModal(productoId);
        }
    } catch (e) {
        console.error('updateQuantity error:', e);
    }
}

function actualizarPrecioModal(productoId) {
    console.log('actualizarPrecioModal called:', productoId);
    try {
        const productCard = document.querySelector(`.product [data-bs-target="#productoModal${productoId}"]`)?.closest('.product');
        if (!productCard) {
            console.error(`Product card for producto ${productoId} not found`);
            return;
        }
        const precioBase = parsePrice(productCard.dataset.precioBase);
        const cantidadInput = document.getElementById(`cantidad_${productoId}`);
        const totalElement = document.getElementById(`total-modal-${productoId}`);
        const cashDiscountPriceElement = document.getElementById(`cash-discount-price-${productoId}`);
        const cashDiscountPercentage = parseFloat(productCard.dataset.cashDiscountPercentage) || 0;

        if (!cantidadInput || !totalElement) {
            console.error('Modal elements missing:', { cantidadInput, totalElement, cashDiscountPriceElement });
            return;
        }

        const cantidad = parseInt(cantidadInput.value) || 1;
        let precioAdicional = 0;
        document.querySelectorAll(`#opciones-container-${productoId} input:checked`).forEach(input => {
            const adicional = parsePrice(input.dataset.precioAdicional);
            precioAdicional += adicional;
        });

        const precioUnitario = roundToTwoDecimals(precioBase + precioAdicional);
        const precioTotal = roundToTwoDecimals(precioUnitario * cantidad);
        totalElement.textContent = `$${precioTotal.toFixed(2)}`;

        // Mostrar precio con descuento en efectivo solo si está habilitado
        if (cashDiscountPriceElement && window.cashDiscountEnabled && cashDiscountPercentage > 0) {
            const metodoPago = document.getElementById('metodo_pago_resumen')?.value;
            if (metodoPago === 'efectivo') {
                const precioConDescuento = roundToTwoDecimals(precioTotal * (1 - cashDiscountPercentage / 100));
                cashDiscountPriceElement.textContent = `$${precioConDescuento.toFixed(2)}`;
            } else {
                cashDiscountPriceElement.textContent = '';
            }
        }
    } catch (e) {
        console.error('actualizarPrecioModal error:', e);
    }
}

function mostrarResumen() {
    console.log('mostrarResumen called');
    try {
        const form = document.getElementById('form-datos-cliente');
        if (!form) {
            console.error('Form form-datos-cliente not found');
            showErrorModal('Error: No se encontraron los datos del cliente.');
            return;
        }

        const nombre = form.querySelector('input[name="nombre"]').value.trim();
        const telefono = form.querySelector('input[name="telefono"]').value.trim();
        const direccion = form.querySelector('input[name="direccion"]')?.value.trim() || '';
        const aclaraciones = form.querySelector('textarea[name="aclaraciones"]').value.trim();
        const metodoPago = document.getElementById('metodo_pago_resumen')?.value;

        if (!nombre) {
            showErrorModal('Por favor, ingresa un nombre válido.');
            return;
        }
        if (!telefono || !/^\d{10}$/.test(telefono)) {
            showErrorModal('Por favor, ingresa un número de teléfono válido de 10 dígitos.');
            return;
        }
        if (tipoPedido === 'delivery' && !direccion) {
            showErrorModal('Por favor, ingresa una dirección de entrega.');
            return;
        }
        if (!metodoPago) {
            showErrorModal('Por favor, selecciona un método de pago.');
            return;
        }

        pedidoData.datosCliente = { nombre, telefono, direccion, aclaraciones, metodo_pago: metodoPago };
        actualizarResumen(true);

        const resumenPedidoFinal = document.getElementById('resumen-pedido-final');
        if (!resumenPedidoFinal) {
            console.error('resumen-pedido-final not found');
            return;
        }
        resumenPedidoFinal.innerHTML = '';
        pedidoData.productos.forEach(producto => {
            const div = document.createElement('div');
            div.className = 'order-item';
            let opcionesHtml = '';
            if (producto.opciones && producto.opciones.length > 0) {
                const groupedOptions = {};
                producto.opciones.forEach(op => {
                    if (!groupedOptions[op.categoria_id]) {
                        groupedOptions[op.categoria_id] = [];
                    }
                    groupedOptions[op.categoria_id].push(op);
                });
                for (const categoriaId in groupedOptions) {
                    const options = groupedOptions[categoriaId];
                    const categoriaNombre = options[0].nombre.split(' (')[0];
                    const opcionesList = options.map(op => {
                        const precioAdicional = op.precio_adicional > 0 ? ` (+$${op.precio_adicional.toFixed(2)})` : '';
                        return `+ ${op.nombre}${precioAdicional}`;
                    }).join('<br>');
                    opcionesHtml += `<p class="option"><span class="category">Elige ${categoriaNombre}:</span><br>${opcionesList}</p>`;
                }
            }
            div.innerHTML = `
                <div class="item-details">
                    <p class="modal-title">${producto.nombre}</p>
                    <span class="producto-cantidad">${producto.cantidad}x <span class="item-price">$${producto.precio_unitario.toFixed(2)}</span></span>
                    ${opcionesHtml}
                    <p class="item-total">Total: $${producto.precio_total.toFixed(2)}</p>
                </div>
            `;
            resumenPedidoFinal.appendChild(div);
        });

        const subtotalElement = document.getElementById('subtotal-pedido-resumen');
        const costoEnvioElement = document.getElementById('costo-envio-resumen');
        const conDescuentoElement = document.getElementById('con-descuento-resumen');
        const conDescuentoLine = document.getElementById('con-descuento-line-resumen');
        const subtotalConDescuentosElement = document.getElementById('subtotal-con-descuentos-resumen');
        const subtotalConDescuentosLine = document.getElementById('subtotal-con-descuentos-line-resumen');
        const totalElement = document.getElementById('total-pedido-resumen-resumen');
        if (!subtotalElement || !costoEnvioElement || !conDescuentoElement || !conDescuentoLine || !subtotalConDescuentosElement || !subtotalConDescuentosLine || !totalElement) {
            console.error('Costos elements not found:', { subtotalElement, costoEnvioElement, conDescuentoElement, conDescuentoLine, subtotalConDescuentosElement, subtotalConDescuentosLine, totalElement });
            return;
        }

        subtotalElement.textContent = `$${pedidoData.subtotal.toFixed(2)}`;
        const umbralGratis = parseFloat(window.umbralEnvioGratis) || 0;
        const isFreeShipping = umbralGratis > 0 && pedidoData.subtotal >= umbralGratis && tipoPedido === 'delivery';
        costoEnvioElement.textContent = isFreeShipping ? 'Envío Gratis' : `$${pedidoData.costoEnvio.toFixed(2)}`;

        // Mostrar descuentos solo si existen
        let discountDetails = '';
        if (pedidoData.cashDiscountApplied && pedidoData.montoDescuentoEfectivo > 0) {
            discountDetails += `Descuento por Pago en Efectivo (${pedidoData.cashDiscountPercentage}%): -$${pedidoData.montoDescuentoEfectivo.toFixed(2)}<br>`;
        }
        if (pedidoData.montoDescuentoCodigo > 0) {
            discountDetails += `Descuento por Código (${pedidoData.codigoDescuento}, ${pedidoData.descuentoPorcentaje}%): -$${pedidoData.montoDescuentoCodigo.toFixed(2)}<br>`;
        }
        if (pedidoData.montoDescuento > 0) {
            discountDetails += `Total Descuentos: -$${pedidoData.montoDescuento.toFixed(2)}`;
            conDescuentoLine.style.display = 'block';
            conDescuentoElement.innerHTML = discountDetails;
            subtotalConDescuentosLine.style.display = 'block';
            const subtotalConDescuentos = roundToTwoDecimals(pedidoData.subtotal - pedidoData.montoDescuento);
            subtotalConDescuentosElement.textContent = `$${subtotalConDescuentos.toFixed(2)}`;
        } else {
            conDescuentoLine.style.display = 'none';
            conDescuentoElement.innerHTML = '';
            subtotalConDescuentosLine.style.display = 'none';
            subtotalConDescuentosElement.textContent = '';
        }

        totalElement.textContent = `$${pedidoData.total.toFixed(2)}`;

        document.getElementById('resumen-nombre').textContent = `Nombre: ${sanitizeInput(nombre)}`;
        document.getElementById('resumen-telefono').textContent = `Teléfono: ${sanitizeInput(telefono)}`;
        document.getElementById('resumen-metodo-pago').textContent = `Método de Pago: ${metodoPago === 'efectivo' ? 'Efectivo' : 'Mercado Pago'}`;
        document.getElementById('resumen-direccion').textContent = tipoPedido === 'delivery' ? `Dirección: ${sanitizeInput(direccion)}` : 'Retiro en Local';
        document.getElementById('resumen-codigo-descuento').textContent = pedidoData.codigoDescuento ? `Código de Descuento: ${pedidoData.codigoDescuento}` : '';
        document.getElementById('resumen-aclaraciones').textContent = aclaraciones ? `Aclaraciones: ${sanitizeInput(aclaraciones)}` : '';

        hideAllModals();
        const modalResumen = document.getElementById('modalResumen');
        if (modalResumen) {
            const modal = new bootstrap.Modal(modalResumen, { backdrop: true });
            modal.show();
        }
    } catch (e) {
        console.error('mostrarResumen error:', e);
        showErrorModal('Error al mostrar el resumen del pedido.');
    }
}

// static/js/order.js
function confirmarPedido(url) {
    console.log('confirmarPedido called:', url);
    try {
        const form = document.getElementById('form-confirmacion');
        if (!form) {
            console.error('Form form-confirmacion not found');
            showErrorModal('Error: No se encontró el formulario de confirmación.');
            return;
        }

        const nombre = pedidoData.datosCliente.nombre?.trim();
        if (!nombre) {
            console.error('Nombre del cliente no especificado:', pedidoData.datosCliente);
            showErrorModal('El nombre del cliente es requerido.');
            return;
        }

        const datosCliente = { ...pedidoData.datosCliente, nombre };
        console.log('Datos cliente enviados:', datosCliente);

        const formData = new FormData();
        formData.append('productos', JSON.stringify(pedidoData.productos));
        formData.append('datos_cliente', JSON.stringify(datosCliente));
        formData.append('subtotal', pedidoData.subtotal);
        formData.append('costo_envio', pedidoData.costo_envio);
        formData.append('monto_descuento', pedidoData.montoDescuento);
        formData.append('monto_descuento_codigo', pedidoData.montoDescuentoCodigo);
        formData.append('monto_descuento_efectivo', pedidoData.montoDescuentoEfectivo);
        formData.append('total', pedidoData.total);
        formData.append('tipo_pedido', tipoPedido);
        formData.append('codigo_descuento', pedidoData.codigoDescuento);

        const csrftoken = getCsrfToken();
        if (!csrftoken) {
            console.error('CSRF token is missing for confirmarPedido:', csrftoken);
            showErrorModal('Error: Token de seguridad no disponible. Por favor, recarga la página.');
            return;
        }

        fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': csrftoken
            },
            credentials: 'include'
        })
        .then(response => {
            console.log('Fetch response:', {
                status: response.status,
                statusText: response.statusText,
                url: response.url
            });
            // Check Content-Type to ensure it's JSON
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                return response.text().then(text => {
                    throw new Error(`Expected JSON, received ${contentType}: ${text.substring(0, 100)}...`);
                });
            }
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(`HTTP error ${response.status}: ${data.error || 'Unknown error'}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Fetch data:', data);
            if (data.success) {
                window.location.href = data.redirect_url || '/';
            } else {
                showErrorModal(data.error || 'Error al confirmar el pedido. Por favor, intenta de nuevo.');
            }
        })
        .catch(error => {
            console.error('Fetch error:', error);
            showErrorModal(`Error al confirmar el pedido: ${error.message}`);
        });
    } catch (e) {
        console.error('confirmarPedido error:', e);
        showErrorModal('Error al confirmar el pedido.');
    }
}