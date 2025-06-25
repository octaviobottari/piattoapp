$(document).ready(function() {
  // Obtener restauranteId desde el DOM
  const restauranteId = document.querySelector('meta[name="restaurante-id"]')?.content || '';
  if (!restauranteId) {
    console.error("Error: restauranteId no definido. No se puede conectar al WebSocket.");
    showNotification("Error: ID de restaurante no definido. Por favor, recarga la página.", "error");
    return;
  }

  const wsUrl = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws/pedidos/' + restauranteId + '/';
  console.log("URL del WebSocket:", wsUrl);

  let ws = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 10;
  const baseReconnectDelay = 5000;

  function connectWebSocket() {
    console.log("Intentando conectar WebSocket a:", wsUrl);
    ws = new WebSocket(wsUrl);

    ws.onopen = function() {
      console.log("WebSocket conectado exitosamente para restaurante:", restauranteId);
      reconnectAttempts = 0;
      showNotification("Conexión WebSocket establecida", "success");
    };

    ws.onmessage = function(e) {
      console.log("Mensaje WebSocket recibido (crudo):", e.data);
      try {
        const data = JSON.parse(e.data);
        console.log("Mensaje WebSocket parseado:", data);

        if (data.error) {
          console.error("Error recibido del WebSocket:", data.error);
          showNotification(data.error, "error");
          return;
        }

        if (data.type === 'new_pedido' || data.type === 'pedido_updated') {
          console.log(`Evento recibido: ${data.type}, Pedido ID: ${data.pedido_id}, Estado: ${data.estado || 'nuevo'}`);
          // Evitar duplicados
          if (data.type === 'new_pedido' && $(`.order-card[data-pedido-id="${data.pedido_id}"]`).length > 0) {
            console.log(`Pedido #${data.pedido_id} ya existe en el DOM, ignorando.`);
            return;
          }
          // Reproducir sonido solo para nuevos pedidos si está habilitado
          const isSoundEnabled = localStorage.getItem('isSoundEnabled') === 'true';
          if (isSoundEnabled && data.type === 'new_pedido' && typeof window.playNotificationSound === 'function') {
            console.log("Llamando a playNotificationSound para pedido:", data.pedido_id);
            window.playNotificationSound(data.pedido_id);
          } else {
            console.log("Sonido no reproducido. Razón:", !isSoundEnabled ? "Sonido deshabilitado" : "playNotificationSound no definido");
          }
          // Refrescar todas las columnas
          refreshAllColumns(data);
        } else {
          console.log("Mensaje WebSocket desconocido:", data);
        }
      } catch (err) {
        console.error("Error al parsear mensaje WebSocket:", err, "Datos crudos:", e.data);
        showNotification("Error al procesar mensaje WebSocket", "error");
      }
    };

    ws.onclose = function(e) {
      console.warn("WebSocket cerrado:", e.code, e.reason);
      if (reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
        const delay = baseReconnectDelay * Math.pow(2, reconnectAttempts - 1);
        console.log(`Intentando reconectar WebSocket (${reconnectAttempts}/${maxReconnectAttempts}) en ${delay/1000} segundos...`);
        setTimeout(connectWebSocket, delay);
      } else {
        console.error("Máximo de intentos de reconexión alcanzado");
        showNotification("No se pudo reconectar al WebSocket. Por favor, recarga la página.", "error");
      }
    };

    ws.onerror = function(err) {
      console.error("Error en WebSocket:", err);
      showNotification("Error en la conexión WebSocket", "error");
    };
  }

  // Iniciar conexión WebSocket
  connectWebSocket();

  // Prevenir cierre accidental del WebSocket
  window.addEventListener('beforeunload', function() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close(1000, 'Cerrando conexión por navegación');
    }
  });

  // Función para refrescar todas las columnas
  function refreshAllColumns(data) {
    // Refrescar Pendientes
    $.ajax({
      url: '/panel/pedidos/pendientes/html/',
      method: 'GET',
      cache: false,
      timeout: 10000,
      success: function(html) {
        const $pendientes = $('#pendientes');
        $pendientes.html(html);
        $('.dropdown-toggle', $pendientes).dropdown();
        $pendientes[0].scrollTop = 0;
      },
      error: function(xhr) {
        console.error("Error al obtener pedidos pendientes:", xhr.status, xhr.statusText, xhr.responseText);
        showNotification("Error al actualizar pedidos pendientes: " + (xhr.responseJSON?.error || xhr.statusText || "Error en la solicitud"), "error");
      }
    });

    // Refrescar En Preparación
    $.ajax({
      url: '/panel/pedidos/en_preparacion/html/',
      method: 'GET',
      cache: false,
      timeout: 10000,
      success: function(html) {
        const $enPreparacion = $('#en_preparacion');
        $enPreparacion.html(html);
        $('.dropdown-toggle', $enPreparacion).dropdown();
        $enPreparacion[0].scrollTop = 0;
      },
      error: function(xhr) {
        console.error("Error al obtener pedidos en preparación:", xhr.status, xhr.statusText, xhr.responseText);
        showNotification("Error al actualizar pedidos en preparación: " + (xhr.responseJSON?.error || xhr.statusText || "Error en la solicitud"), "error");
      }
    });

    // Refrescar Listos
    $.ajax({
      url: '/panel/pedidos/listos/html/',
      method: 'GET',
      cache: false,
      timeout: 10000,
      success: function(html) {
        const $listo = $('#listo');
        $listo.html(html);
        $('.dropdown-toggle', $listo).dropdown();
        $listo[0].scrollTop = 0;
      },
      error: function(xhr) {
        console.error("Error al obtener pedidos listos:", xhr.status, xhr.statusText, xhr.responseText);
        showNotification("Error al actualizar pedidos listos: " + (xhr.responseJSON?.error || xhr.statusText || "Error en la solicitud"), "error");
      }
    });

    // Mostrar notificación
    if (data.type === 'new_pedido') {
      showNotification(`Nuevo pedido #${data.numero_pedido || data.pedido_id} recibido`, "success");
    } else if (data.type === 'pedido_updated') {
      showNotification(`Pedido #${data.numero_pedido || data.pedido_id} actualizado a "${data.estado || 'desconocido'}"`, "success");
    }
  }

  // Función para mostrar notificaciones
  function showNotification(message, type) {
    const notificationDiv = document.createElement("div");
    notificationDiv.className = `alert alert-${type === "error" ? "danger" : type === "warning" ? "warning" : "success"} alert-dismissible fade show`;
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