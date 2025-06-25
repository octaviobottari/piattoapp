$(document).ready(function() {
    console.log("panel.js cargado correctamente");

    // Configurar CSRF token para todas las solicitudes AJAX
    function getCookie(name) {
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
        return cookieValue;
    }

    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                const csrftoken = getCookie('csrftoken');
                if (csrftoken) {
                    xhr.setRequestHeader("X-CSRFToken", csrftoken);
                } else {
                    console.error("CSRF token no encontrado");
                }
            }
        }
    });

    // Manejo de audio
    const audio = document.getElementById('notificationSound');
    audio.load();
    let isSoundEnabled = localStorage.getItem('isSoundEnabled') === 'true';
    $('#soundToggle').prop('checked', isSoundEnabled);

    $(document).one('click', function() {
        audio.play().then(() => {
            audio.pause();
            audio.currentTime = 0;
            console.log("Audio desbloqueado tras interacción del usuario");
        }).catch(e => console.error("Error al desbloquear audio:", e));
    });

    $('#soundToggle').change(function() {
        isSoundEnabled = $(this).is(':checked');
        localStorage.setItem('isSoundEnabled', isSoundEnabled);
        if (isSoundEnabled) {
            audio.play().then(() => {
                audio.pause();
                audio.currentTime = 0;
            }).catch(e => console.error("Error al reproducir sonido de prueba:", e));
        }
    });

    // Buscador
    $('#searchInput').on('keyup', function() {
        const searchText = $(this).val().toLowerCase();
        $('.order-card').each(function() {
            const pedidoId = $(this).data('pedido-id').toString();
            const cliente = $(this).find('.order-name').text().toLowerCase();
            $(this).toggle(pedidoId.includes(searchText) || cliente.includes(searchText));
        });
    });

    // Evitar clics múltiples
    function disableButton($btn) {
        $btn.addClass('disabled').prop('disabled', true);
    }

    function enableButton($btn) {
        $btn.removeClass('disabled').prop('disabled', false);
    }

    // Sincronizar estado al cargar la página
    function syncPedidos() {
        // Obtener todos los pedidos del servidor
        $.get('/panel/pedidos/json/', (pedidos) => {
            // Limpiar columnas
            $('#pendientes, #en_preparacion, #listo').empty();

            // Procesar cada pedido
            pedidos.forEach(pedido => {
                const card = createOrderCard(pedido);
                updateCardEstado($(card), pedido);
            });

            // Mostrar mensaje si las columnas están vacías
            ['pendientes', 'en_preparacion', 'listo'].forEach(col => {
                if ($(`#${col}`).children().length === 0) {
                    $(`#${col}`).html('<p class="text-center">No hay pedidos en este estado.</p>');
                }
            });
        }).fail((xhr) => {
            console.error("Error al sincronizar pedidos:", xhr.status, xhr.responseText);
            showNotification("Error al cargar los pedidos", "error");
        });
    }

    // Crear una tarjeta de pedido
    function createOrderCard(pedido) {
        const fechaFormatted = pedido.fecha_creacion 
            ? new Date(pedido.fecha_creacion).toLocaleString('es-AR', { 
                day: '2-digit', 
                month: '2-digit', 
                year: 'numeric', 
                hour: '2-digit', 
                minute: '2-digit', 
                hour12: false 
            }).replace(',', '')
            : 'Sin fecha';
        return `
            <div class="order-card mb-3" data-pedido-id="${pedido.id}">
                <div class="order-info">
                    <div class="order-header">#${pedido.numero_pedido || 'Sin número'} - ${fechaFormatted}</div>
                    <div class="order-name">${pedido.nombre_cliente || 'Sin nombre'}</div>
                    <a href="#" class="order-phone" data-pedido-id="${pedido.id}" data-telefono="${pedido.telefono_cliente || ''}">${pedido.telefono_cliente || 'Sin teléfono'}</a>
                    <div class="order-address">
                        <i class="fas fa-map-marker-alt"></i> ${pedido.direccion_entrega || 'Retiro en local'}
                    </div>
                </div>
                <div class="order-actions text-end">
                    <div class="icon-group mb-2"></div>
                    <div class="order-price">$${parseFloat(pedido.total || 0).toFixed(2)}</div>
                    <div class="order-method">${pedido.metodo_pago ? pedido.metodo_pago.charAt(0).toUpperCase() + pedido.metodo_pago.slice(1).toLowerCase() : 'Sin método'}</div>
                </div>
            </div>`;
    }

    // Actualizar tarjeta según estado
    function updateCardEstado(card, pedido) {
        const pedidoId = card.data('pedido-id');
        const iconGroup = card.find('.icon-group');
        iconGroup.empty(); // Limpiar acciones previas

        // Añadir acción de imprimir
        iconGroup.append(`
            <a href="/pedidos/imprimir/${pedidoId}/" class="text-decoration-none print-ticket">
                <i class="fas fa-print"></i>
            </a>
        `);

        if (pedido.estado === 'pendiente') {
            iconGroup.append(`
                <div class="dropdown d-inline-block">
                    <i class="fas fa-check icon-check dropdown-toggle" data-bs-toggle="dropdown"></i>
                    <ul class="dropdown-menu">
                        ${window.tiemposEstimados.map(([value, label]) => `
                            <li>
                                <a class="dropdown-item aceptar-pedido" href="#" data-pedido-id="${pedidoId}" data-tiempo="${value}">${label}</a>
                            </li>
                        `).join('')}
                    </ul>
                </div>
                <div class="dropdown d-inline-block">
                    <i class="fas fa-times icon-cross dropdown-toggle" data-bs-toggle="dropdown"></i>
                    <ul class="dropdown-menu">
                        ${window.motivosCancelacion.map(([value, label]) => `
                            <li>
                                <a class="dropdown-item rechazar-pedido" href="#" data-pedido-id="${pedidoId}" data-motivo="${value}">${label}</a>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            `);
            card.find('.order-timing').remove();
            $('#pendientes').prepend(card);
        } else if (pedido.estado === 'en_preparacion') {
            iconGroup.append(`
                <i class="fas fa-backward icon-backward mover-atras" data-pedido-id="${pedidoId}" title="Mover a Pendientes"></i>
                <i class="fas fa-forward icon-forward mover-a-listo" data-pedido-id="${pedidoId}" title="Mover a Listos para Entregar"></i>
                <div class="dropdown d-inline-block">
                    <i class="fas fa-times icon-cross dropdown-toggle" data-bs-toggle="dropdown"></i>
                    <ul class="dropdown-menu">
                        ${window.motivosCancelacion.map(([value, label]) => `
                            <li>
                                <a class="dropdown-item rechazar-pedido" href="#" data-pedido-id="${pedidoId}" data-motivo="${value}">${label}</a>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            `);
            card.find('.order-timing').remove();
            if (pedido.tiempo_estimado) {
                const tiempoLabel = window.tiemposEstimados.find(t => t[0] === pedido.tiempo_estimado)?.[1] || 'Sin tiempo estimado';
                card.find('.order-actions').append(`<div class="order-timing">${tiempoLabel}</div>`);
            }
            $('#en_preparacion').prepend(card);
        } else if (pedido.estado === 'listo') {
            iconGroup.append(`
                <i class="fas fa-backward icon-backward mover-atras" data-pedido-id="${pedidoId}" title="Mover a En Preparación"></i>
            `);
            const direccion = pedido.direccion_entrega || 'Retiro en local';
            if (direccion !== 'Retiro en local') {
                iconGroup.append(`
                    <i class="fas fa-motorcycle icon-motorcycle marcar-en-entrega" data-pedido-id="${pedidoId}" title="Marcar como En Entrega"></i>
                `);
            } else {
                iconGroup.append(`
                    <i class="fas fa-save icon-save archivar-pedido" data-pedido-id="${pedidoId}" title="Archivar Pedido"></i>
                `);
            }
            iconGroup.append(`
                <div class="dropdown d-inline-block">
                    <i class="fas fa-times icon-cross dropdown-toggle" data-bs-toggle="dropdown"></i>
                    <ul class="dropdown-menu">
                        ${window.motivosCancelacion.map(([value, label]) => `
                            <li>
                                <a class="dropdown-item rechazar-pedido" href="#" data-pedido-id="${pedidoId}" data-motivo="${value}">${label}</a>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            `);
            card.find('.order-timing').remove();
            $('#listo').prepend(card);
        } else {
            card.remove();
            return;
        }

        // Actualizar datos de la tarjeta
        const fechaFormatted = pedido.fecha_creacion 
            ? new Date(pedido.fecha_creacion).toLocaleString('es-AR', { 
                day: '2-digit', 
                month: '2-digit', 
                year: 'numeric', 
                hour: '2-digit', 
                minute: '2-digit', 
                hour12: false 
            }).replace(',', '')
            : 'Sin fecha';
        card.find('.order-header').text(`#${pedido.numero_pedido || 'Sin número'} - ${fechaFormatted}`);
        card.find('.order-name').text(pedido.nombre_cliente || 'Sin nombre');
        card.find('.order-phone').text(pedido.telefono_cliente || 'Sin teléfono').data('telefono', pedido.telefono_cliente || '');
        card.find('.order-address').html(`<i class="fas fa-map-marker-alt"></i> ${pedido.direccion_entrega || 'Retiro en local'}`);
        card.find('.order-price').text(`$${parseFloat(pedido.total || 0).toFixed(2)}`);
        card.find('.order-method').text(pedido.metodo_pago ? pedido.metodo_pago.charAt(0).toUpperCase() + pedido.metodo_pago.slice(1).toLowerCase() : 'Sin método');

        $('.dropdown-toggle').dropdown();
    }

    // Mostrar detalles del pedido
    $(document).on('click', '.order-info', function(e) {
        if ($(e.target).closest('.order-phone').length) return;
        e.preventDefault();
        e.stopPropagation();
        const pedidoId = $(this).closest('.order-card').data('pedido-id');
        $.get(`/panel/pedidos/${pedidoId}/json/`, (pedido) => {
            $('#modalPedidoTitle').text(`Pedido #${pedido.numero_pedido || 'Sin número'}`);
            $('#modalCliente').text(pedido.nombre_cliente || 'Sin nombre');
            $('#modalTelefono').text(pedido.telefono_cliente || 'Sin teléfono');
            $('#modalDireccion').text(pedido.direccion_entrega || 'Retiro en local');
            $('#modalAclaraciones').text(pedido.aclaraciones || 'Sin aclaraciones');
            $('#modalFecha').text(pedido.fecha_creacion 
                ? new Date(pedido.fecha_creacion).toLocaleString('es-AR', {
                    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false
                }).replace(',', '')
                : 'Sin fecha');
            $('#modalMetodoPago').text(pedido.metodo_pago 
                ? pedido.metodo_pago.charAt(0).toUpperCase() + pedido.metodo_pago.slice(1).toLowerCase()
                : 'Sin método');
            $('#modalEstado').text(pedido.estado ? pedido.estado.charAt(0).toUpperCase() + pedido.estado.slice(1) : 'Sin estado');
            $('#modalTiempoEstimado').text(pedido.tiempo_estimado 
                ? window.tiemposEstimados.find(t => t[0] === pedido.tiempo_estimado)?.[1] || 'Sin tiempo estimado'
                : 'Sin tiempo estimado');
            $('#modalSubtotal').text(parseFloat(pedido.subtotal || 0).toFixed(2));
            $('#modalDescuentoEfectivo').text(parseFloat(pedido.monto_descuento_efectivo || 0).toFixed(2));
            $('#modalDescuentoCodigo').text(parseFloat(pedido.monto_descuento_codigo || 0).toFixed(2));
            $('#modalDescuentoTotal').text(parseFloat(pedido.monto_descuento || 0).toFixed(2));
            $('#modalCostoEnvio').text(parseFloat(pedido.costo_envio || 0).toFixed(2));
            $('#modalTotal').text(parseFloat(pedido.total || 0).toFixed(2));

            $('#modalDescuentoEfectivoContainer').toggle(parseFloat(pedido.monto_descuento_efectivo || 0) > 0);
            $('#modalDescuentoCodigoContainer').toggle(parseFloat(pedido.monto_descuento_codigo || 0) > 0);

            const tbody = $('#modalProductos');
            tbody.empty();
            pedido.items.forEach(item => {
                let opcionesHtml = item.opciones_seleccionadas?.length 
                    ? item.opciones_seleccionadas.map(opt => `${opt.nombre} (+$${parseFloat(opt.precio_adicional || 0).toFixed(2)})`).join('<br>')
                    : '-';
                tbody.append(`
                    <tr>
                        <td>${item.nombre_producto || 'Sin nombre'}</td>
                        <td>${item.cantidad || 0}</td>
                        <td>$${parseFloat(item.precio_unitario || 0).toFixed(2)}</td>
                        <td>$${parseFloat(item.subtotal || item.precio_unitario * item.cantidad || 0).toFixed(2)}</td>
                        <td>${opcionesHtml}</td>
                    </tr>
                `);
            });

            $('#modalPedido').modal('show');
        }).fail((xhr) => {
            console.error("Error al obtener detalles del pedido:", xhr.status, xhr.responseText);
            showNotification("Error al cargar detalles del pedido", "error");
        });
    });

    // Abrir WhatsApp
    $(document).on('click', '.order-phone', function(e) {
        e.preventDefault();
        e.stopPropagation();
        const $this = $(this);
        const pedidoId = $this.data('pedido-id');
        const telefonoRaw = $this.attr('data-telefono');

        if (!telefonoRaw || typeof telefonoRaw !== 'string' || telefonoRaw.trim() === '') {
            $('#modalWhatsAppTitle').text('Error en WhatsApp');
            $('#whatsappMessage').text('Número inválido. No se puede contactar por WhatsApp.');
            $('#whatsappLink').hide();
            $('#modalWhatsApp').modal('show');
            return;
        }

        const telefono = telefonoRaw.replace(/\D/g, '');
        if (telefono.length !== 10 || isNaN(telefono)) {
            $('#modalWhatsAppTitle').text('Error en WhatsApp');
            $('#whatsappMessage').text('Número inválido. Debe tener 10 dígitos numéricos.');
            $('#whatsappLink').hide();
            $('#modalWhatsApp').modal('show');
            return;
        }

        const numeroWhatsApp = `+54${telefono}`;

        $.get(`/panel/pedidos/${pedidoId}/json/`, (pedido) => {
            let mensaje = `Hola ${pedido.nombre_cliente || 'Cliente'}, tu pedido #${pedido.numero_pedido || pedidoId} ha sido confirmado!\n\n*Detalles del pedido:*\n`;
            pedido.items.forEach(item => {
                mensaje += `- ${item.cantidad}x ${item.nombre_producto} ($${parseFloat(item.subtotal || item.precio_unitario * item.cantidad || 0).toFixed(2)})\n`;
                if (item.opciones_seleccionadas?.length) {
                    mensaje += `  Opciones:\n`;
                    item.opciones_seleccionadas.forEach(opt => {
                        mensaje += `    * ${opt.nombre} (+$${parseFloat(opt.precio_adicional || 0).toFixed(2)})\n`;
                    });
                }
            });
            mensaje += `\n*Total*: $${parseFloat(pedido.total || 0).toFixed(2)}`;
            if (pedido.direccion_entrega && pedido.direccion_entrega !== 'Retiro en local') {
                mensaje += `\n\n*Entrega en*: ${pedido.direccion_entrega}`;
            } else {
                mensaje += `\n\n*Retiro en local*`;
            }
            if (pedido.tiempo_estimado) {
                const tiempoLabel = window.tiemposEstimados.find(t => t[0] === pedido.tiempo_estimado)?.[1] || pedido.tiempo_estimado;
                mensaje += `\n*Tiempo estimado*: ${tiempoLabel}`;
            }

            const mensajeEncoded = encodeURIComponent(mensaje);
            const whatsappUrl = `https://wa.me/${numeroWhatsApp}?text=${mensajeEncoded}`;

            $('#modalWhatsAppTitle').text('Contactar por WhatsApp');
            $('#whatsappMessage').text(mensaje);
            $('#whatsappLink').attr('href', whatsappUrl).show();
            $('#modalWhatsApp').modal('show');
        }).fail((xhr) => {
            $('#modalWhatsAppTitle').text('Error en WhatsApp');
            $('#whatsappMessage').text('Error al cargar detalles del pedido.');
            $('#whatsappLink').hide();
            $('#modalWhatsApp').modal('show');
        });
    });

    // Aceptar pedido
    $(document).on('click', '.aceptar-pedido', function(e) {
        e.preventDefault();
        const $this = $(this);
        if ($this.hasClass('disabled')) return;
        disableButton($this);

        const pedidoId = $this.data('pedido-id');
        const tiempoEstimado = $this.data('tiempo');

        $.ajax({
            url: `/panel/pedidos/${pedidoId}/aceptar/`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ tiempo_estimado: tiempoEstimado }),
            success: function(response) {
                if (response.success) {
                    const card = $(`.order-card[data-pedido-id="${pedidoId}"]`);
                    updateCardEstado(card, {
                        id: pedidoId,
                        estado: 'en_preparacion',
                        tiempo_estimado: tiempoEstimado,
                        numero_pedido: card.find('.order-header').text().split(' - ')[0].replace('#', ''),
                        nombre_cliente: card.find('.order-name').text(),
                        telefono_cliente: card.find('.order-phone').data('telefono'),
                        direccion_entrega: card.find('.order-address').text().replace('📍 ', ''),
                        total: card.find('.order-price').text().replace('$', ''),
                        metodo_pago: card.find('.order-method').text(),
                        fecha_creacion: new Date().toISOString()
                    });
                    showNotification(`Pedido #${pedidoId} aceptado`, "success");
                } else {
                    showNotification(`Error al aceptar el pedido: ${response.error || 'Error desconocido'}`, "error");
                }
            },
            error: function(xhr) {
                showNotification(`Error al aceptar el pedido: ${xhr.responseJSON?.error || 'Error en la solicitud'}`, "error");
            },
            complete: function() {
                enableButton($this);
            }
        });
    });

    // Retroceder pedido
    $(document).on('click', '.mover-atras', function(e) {
        e.preventDefault();
        const $this = $(this);
        if ($this.hasClass('disabled')) return;
        disableButton($this);

        const pedidoId = $this.data('pedido-id');
        const currentColumn = $this.closest('.order-column').attr('id');
        let newEstado;

        if (currentColumn === 'en_preparacion') {
            newEstado = 'pendiente';
        } else if (currentColumn === 'listo') {
            newEstado = 'en_preparacion';
        } else {
            showNotification(`Estado no válido para retroceder: ${currentColumn}`, "error");
            enableButton($this);
            return;
        }

        $.ajax({
            url: `/panel/pedidos/${pedidoId}/retroceder/`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ estado: newEstado }),
            success: function(response) {
                if (response.success) {
                    const card = $(`.order-card[data-pedido-id="${pedidoId}"]`);
                    updateCardEstado(card, {
                        id: pedidoId,
                        estado: newEstado,
                        tiempo_estimado: response.tiempo_estimado,
                        numero_pedido: card.find('.order-header').text().split(' - ')[0].replace('#', ''),
                        nombre_cliente: card.find('.order-name').text(),
                        telefono_cliente: card.find('.order-phone').data('telefono'),
                        direccion_entrega: card.find('.order-address').text().replace('📍 ', ''),
                        total: card.find('.order-price').text().replace('$', ''),
                        metodo_pago: card.find('.order-method').text(),
                        fecha_creacion: new Date().toISOString()
                    });
                    showNotification(`Pedido #${pedidoId} movido a ${newEstado}`, "success");
                } else {
                    showNotification(`Error al retroceder el pedido: ${response.error}`, "error");
                }
            },
            error: function(xhr) {
                showNotification(`Error al retroceder el pedido: ${xhr.responseJSON?.error || 'Error en la solicitud'}`, "error");
            },
            complete: function() {
                enableButton($this);
            }
        });
    });

    // Mover a listo
    $(document).on('click', '.mover-a-listo', function(e) {
        e.preventDefault();
        const $this = $(this);
        if ($this.hasClass('disabled')) return;
        disableButton($this);

        const pedidoId = $this.data('pedido-id');

        $.ajax({
            url: `/panel/pedidos/${pedidoId}/actualizar_estado/`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ estado: 'listo' }),
            success: function(response) {
                if (response.success) {
                    const card = $(`.order-card[data-pedido-id="${pedidoId}"]`);
                    updateCardEstado(card, {
                        id: pedidoId,
                        estado: 'listo',
                        numero_pedido: card.find('.order-header').text().split(' - ')[0].replace('#', ''),
                        nombre_cliente: card.find('.order-name').text(),
                        telefono_cliente: card.find('.order-phone').data('telefono'),
                        direccion_entrega: card.find('.order-address').text().replace('📍 ', ''),
                        total: card.find('.order-price').text().replace('$', ''),
                        metodo_pago: card.find('.order-method').text(),
                        fecha_creacion: new Date().toISOString()
                    });
                    showNotification(`Pedido #${pedidoId} movido a Listo`, "success");
                } else {
                    showNotification(`Error al mover a listo: ${response.error}`, "error");
                }
            },
            error: function(xhr) {
                showNotification(`Error al mover a listo: ${xhr.responseJSON?.error || 'Error en la solicitud'}`, "error");
            },
            complete: function() {
                enableButton($this);
            }
        });
    });

    // Rechazar pedido
    $(document).on('click', '.rechazar-pedido', function(e) {
        e.preventDefault();
        const $this = $(this);
        if ($this.hasClass('disabled')) return;
        disableButton($this);

        const pedidoId = $this.data('pedido-id');
        const motivo = $this.data('motivo');
        const card = $this.closest('.order-card');
        const telefonoRaw = card.find('.order-phone').data('telefono');

        if (!telefonoRaw || typeof telefonoRaw !== 'string' || telefonoRaw.trim() === '') {
            $('#modalWhatsAppTitle').text('Error en WhatsApp');
            $('#whatsappMessage').text('Número inválido. No se puede contactar por WhatsApp.');
            $('#whatsappLink').hide();
            $('#modalWhatsApp').modal('show');
            enableButton($this);
            return;
        }

        const telefono = telefonoRaw.replace(/\D/g, '');
        if (telefono.length !== 10 || isNaN(telefono)) {
            $('#modalWhatsAppTitle').text('Error en WhatsApp');
            $('#whatsappMessage').text('Número inválido. Debe tener 10 dígitos numéricos.');
            $('#whatsappLink').hide();
            $('#modalWhatsApp').modal('show');
            enableButton($this);
            return;
        }

        const numeroWhatsApp = `+54${telefono}`;

        $.get(`/panel/pedidos/${pedidoId}/json/`, (pedido) => {
            let mensaje = `Hola ${pedido.nombre_cliente || 'Cliente'}, lamentamos informarte que tu pedido #${pedido.numero_pedido || pedidoId} ha sido cancelado.\n`;
            mensaje += `*Motivo*: ${window.motivosCancelacion.find(m => m[0] === motivo)?.[1] || motivo}\n\n`;
            mensaje += `*Detalles del pedido:*\n`;
            pedido.items.forEach(item => {
                const subtotal = item.subtotal || (item.precio_unitario * item.cantidad) || 0;
                mensaje += `- ${item.cantidad}x ${item.nombre_producto} ($${parseFloat(subtotal).toFixed(2)})\n`;
                if (item.opciones_seleccionadas?.length) {
                    mensaje += `  Opciones:\n`;
                    item.opciones_seleccionadas.forEach(opt => {
                        mensaje += `    * ${opt.nombre} (+$${parseFloat(opt.precio_adicional || 0).toFixed(2)})\n`;
                    });
                }
            });
            mensaje += `\n*Total*: $${parseFloat(pedido.total || 0).toFixed(2)}`;
            mensaje += `\n\n¡Esperamos verte pronto!`;

            const mensajeEncoded = encodeURIComponent(mensaje);
            const whatsappUrl = `https://wa.me/${numeroWhatsApp}?text=${mensajeEncoded}`;

            $('#modalWhatsAppTitle').text('Notificar Cancelación por WhatsApp');
            $('#whatsappMessage').text(mensaje);
            $('#whatsappLink').attr('href', whatsappUrl).show().off('click').on('click', function(e) {
                e.preventDefault();
                window.open(whatsappUrl, '_blank');
                $('#modalWhatsApp').modal('hide');
            });
            $('#modalWhatsApp').data('pedido-id', pedidoId).data('motivo', motivo).data('action', 'rechazar').modal('show');

            $('#modalWhatsApp').off('hidden.bs.modal').on('hidden.bs.modal', function() {
                const storedPedidoId = $(this).data('pedido-id');
                const action = $(this).data('action');
                const storedMotivo = $(this).data('motivo');

                if (storedPedidoId && action === 'rechazar') {
                    $.ajax({
                        url: `/panel/pedidos/${storedPedidoId}/rechazar/`,
                        method: 'POST',
                        contentType: 'application/json',
                        data: JSON.stringify({ motivo: storedMotivo }),
                        success: function(response) {
                            if (response.success) {
                                $(`.order-card[data-pedido-id="${storedPedidoId}"]`).remove();
                                showNotification(`Pedido #${storedPedidoId} cancelado`, "success");
                            } else {
                                showNotification(`Error al rechazar el pedido: ${response.error}`, "error");
                            }
                        },
                        error: function(xhr) {
                            showNotification(`Error al rechazar el pedido: ${xhr.responseJSON?.error || 'Error en la solicitud'}`, "error");
                        }
                    });
                }
                $(this).removeData('pedido-id').removeData('motivo').removeData('action');
            });
        }).fail((xhr) => {
            $('#modalWhatsAppTitle').text('Error en WhatsApp');
            $('#whatsappMessage').text('Error al cargar detalles del pedido.');
            $('#whatsappLink').hide();
            $('#modalWhatsApp').modal('show');
        }).always(() => {
            enableButton($this);
        });
    });

    // Marcar en entrega
    $(document).on('click', '.marcar-en-entrega', function(e) {
        e.preventDefault();
        const $this = $(this);
        if ($this.hasClass('disabled')) return;
        disableButton($this);

        const pedidoId = $this.data('pedido-id');
        $('#confirmarEntregaBtn').data('pedido-id', pedidoId);
        $('#modalConfirmarEntrega').modal('show');
    });

    $('#confirmarEntregaBtn').on('click', function() {
        const pedidoId = $(this).data('pedido-id');
        const $button = $(`.marcar-en-entrega[data-pedido-id="${pedidoId}"]`);

        $.ajax({
            url: `/panel/pedidos/${pedidoId}/marcar_en_entrega/`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({}),
            success: function(response) {
                if (response.success) {
                    const card = $(`.order-card[data-pedido-id="${pedidoId}"]`);
                    const telefonoRaw = card.find('.order-phone').data('telefono');

                    if (!telefonoRaw || typeof telefonoRaw !== 'string' || telefonoRaw.trim() === '') {
                        $('#modalWhatsAppTitle').text('Error en WhatsApp');
                        $('#whatsappMessage').text('Número inválido. No se puede contactar por WhatsApp.');
                        $('#whatsappLink').hide();
                        $('#modalWhatsApp').modal('show');
                        card.remove();
                        showNotification(`Pedido #${pedidoId} marcado como En Entrega`, "success");
                        $('#modalConfirmarEntrega').modal('hide');
                        return;
                    }

                    const telefono = telefonoRaw.replace(/\D/g, '');
                    if (telefono.length !== 10 || isNaN(telefono)) {
                        $('#modalWhatsAppTitle').text('Error en WhatsApp');
                        $('#whatsappMessage').text('Número inválido. Debe tener 10 dígitos numéricos.');
                        $('#whatsappLink').hide();
                        $('#modalWhatsApp').modal('show');
                        card.remove();
                        showNotification(`Pedido #${pedidoId} marcado como En Entrega`, "success");
                        $('#modalConfirmarEntrega').modal('hide');
                        return;
                    }

                    const numeroWhatsApp = `+54${telefono}`;

                    $.get(`/panel/pedidos/${pedidoId}/json/`, (pedido) => {
                        let mensaje = `Hola ${pedido.nombre_cliente || 'Cliente'}, tu pedido #${pedido.numero_pedido || pedidoId} ha sido confirmado!\n\n*Detalles del pedido:*\n`;
                        pedido.items.forEach(item => {
                            mensaje += `- ${item.cantidad}x ${item.nombre_producto} ($${parseFloat(item.subtotal || item.precio_unitario * item.cantidad || 0).toFixed(2)})\n`;
                            if (item.opciones_seleccionadas?.length) {
                                mensaje += `  Opciones:\n`;
                                item.opciones_seleccionadas.forEach(opt => {
                                    mensaje += `    * ${opt.nombre} (+$${parseFloat(opt.precio_adicional || 0).toFixed(2)})\n`;
                                });
                            }
                        });
                        mensaje += `\n*Total*: $${parseFloat(pedido.total || 0).toFixed(2)}`;
                        if (pedido.direccion_entrega && pedido.direccion_entrega !== 'Retiro en local') {
                            mensaje += `\n\n*Entrega en*: ${pedido.direccion_entrega}`;
                        } else {
                            mensaje += `\n\n*Retiro en local*`;
                        }
                        if (pedido.tiempo_estimado) {
                            const tiempoLabel = window.tiemposEstimados.find(t => t[0] === pedido.tiempo_estimado)?.[1] || pedido.tiempo_estimado;
                            mensaje += `\n*Tiempo estimado*: ${tiempoLabel}`;
                        }

                        const mensajeEncoded = encodeURIComponent(mensaje);
                        const whatsappUrl = `https://wa.me/${numeroWhatsApp}?text=${mensajeEncoded}`;

                        $('#modalWhatsAppTitle').text('Notificar Entrega por WhatsApp');
                        $('#whatsappMessage').text(mensaje);
                        $('#whatsappLink').attr('href', whatsappUrl).show();
                        $('#modalWhatsApp').modal('show');

                        card.remove();
                        showNotification(`Pedido #${pedidoId} marcado como En Entrega`, "success");
                        $('#modalConfirmarEntrega').modal('hide');
                    }).fail((xhr) => {
                        $('#modalWhatsAppTitle').text('Error en WhatsApp');
                        $('#whatsappMessage').text('Error al cargar detalles del pedido.');
                        $('#whatsappLink').hide();
                        $('#modalWhatsApp').modal('show');
                        card.remove();
                        showNotification(`Pedido #${pedidoId} marcado como En Entrega`, "success");
                        $('#modalConfirmarEntrega').modal('hide');
                    });
                } else {
                    showNotification(`Error al marcar en entrega: ${response.error}`, "error");
                }
            },
            error: function(xhr) {
                showNotification(`Error al marcar en entrega: ${xhr.responseJSON?.error || 'Error en la solicitud'}`, "error");
            },
            complete: function() {
                enableButton($button);
            }
        });
    });

    // Archivar pedido
    $(document).on('click', '.archivar-pedido', function(e) {
        e.preventDefault();
        const $this = $(this);
        if ($this.hasClass('disabled')) return;
        disableButton($this);

        const pedidoId = $this.data('pedido-id');

        $.ajax({
            url: `/panel/pedidos/${pedidoId}/archivar/`,
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({}),
            success: function(response) {
                if (response.success) {
                    $(`.order-card[data-pedido-id="${pedidoId}"]`).remove();
                    showNotification(`Pedido #${pedidoId} archivado`, "success");
                } else {
                    showNotification(`Error al archivar: ${response.error}`, "error");
                }
            },
            error: function(xhr) {
                showNotification(`Error al archivar: ${xhr.responseJSON?.error || 'Error en la solicitud'}`, "error");
            },
            complete: function() {
                enableButton($this);
            }
        });
    });

    // Manejo de WebSocket messages
    window.addEventListener('websocketMessage', (e) => {
        const data = e.detail;

        if (data.type === 'new_pedido') {
            if ($(`.order-card[data-pedido-id="${data.pedido_id}"]`).length > 0) {
                console.log(`El pedido #${data.pedido_id} ya existe en la UI`);
                return;
            }

            if (isSoundEnabled) {
                audio.play().catch(e => console.error("Error al reproducir sonido:", e));
            }

            $.get(`/panel/pedidos/${data.pedido_id}/json/`, (pedido) => {
                const newCard = createOrderCard(pedido);
                $('#pendientes').prepend(newCard);
                updateCardEstado($(`.order-card[data-pedido-id="${data.pedido_id}"]`), pedido);
                $('.dropdown-toggle').dropdown();
                showNotification(`Nuevo pedido #${pedido.numero_pedido || data.pedido_id} recibido`, "success");
            }).fail((xhr) => {
                showNotification("Error al cargar el nuevo pedido", "error");
            });
        } else if (data.type === 'pedido_updated') {
            const card = $(`.order-card[data-pedido-id="${data.pedido_id}"]`);
            if (card.length === 0) return;

            if (['cancelado', 'en_entrega', 'archivado'].includes(data.estado)) {
                card.remove();
                showNotification(`Pedido #${data.pedido_id} ${data.estado}`, "info");
                return;
            }

            $.get(`/panel/pedidos/${data.pedido_id}/json/`, (pedido) => {
                updateCardEstado(card, pedido);
                showNotification(`Pedido #${data.pedido_id} actualizado a ${data.estado}`, "success");
            }).fail((xhr) => {
                showNotification("Error al actualizar el pedido", "error");
            });
        }
    });

    // Sincronizar al cargar
    syncPedidos();

    // Prevenir cierre accidental del WebSocket
    window.addEventListener('beforeunload', () => {
        if (window.myWebSocket && window.myWebSocket.readyState === WebSocket.OPEN) {
            window.myWebSocket.close(1000, 'Cerrando conexión por navegación');
        }
    });

    // Función para mostrar notificaciones
    function showNotification(message, type) {
        const notificationDiv = document.createElement("div");
        notificationDiv.className = `alert alert-${type === "error" ? "danger" : type} alert-dismissible fade show`;
        notificationDiv.style.position = "fixed";
        notificationDiv.style.top = "20px";
        notificationDiv.style.right = "20px";
        notificationDiv.style.zIndex = "1000";
        notificationDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(notificationDiv);
        setTimeout(() => notificationDiv.remove(), 5000);
    }
});