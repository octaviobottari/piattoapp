// static/js/sse-manager.js - REEMPLAZA websocket.js
class SSEManager {
    constructor(restauranteId) {
        this.restauranteId = restauranteId;
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.currentVersion = 0;
        this.isConnected = false;
        this.heartbeatInterval = null;
        
        console.log(`SSE Manager inicializado para restaurante: ${restauranteId}`);
    }

    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

        try {
            const url = `/api/pedidos-sse/${this.restauranteId}/?version=${this.currentVersion}`;
            this.eventSource = new EventSource(url);
            
            this.eventSource.onopen = () => {
                console.log('SSE conectado exitosamente');
                this.isConnected = true;
                this.reconnectDelay = 1000;
                this.showNotification('Conexión en tiempo real establecida', 'success');
                
                // Iniciar verificación de heartbeat
                this.startHeartbeatCheck();
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleEvent(data);
                } catch (e) {
                    console.error('Error parsing SSE data:', e);
                }
            };

            this.eventSource.onerror = (error) => {
                console.error('SSE error:', error);
                this.isConnected = false;
                this.stopHeartbeatCheck();
                this.reconnect();
            };

        } catch (error) {
            console.error('Error creating SSE connection:', error);
            this.reconnect();
        }
    }

    handleEvent(data) {
        switch(data.type) {
            case 'pedidos_updated':
                this.currentVersion = data.version;
                this.actualizarInterfazPedidos(data.pedidos);
                break;
                
            case 'heartbeat':
                // Reset heartbeat check
                this.lastHeartbeat = Date.now();
                break;
                
            default:
                console.log('SSE event desconocido:', data);
        }
    }

    actualizarInterfazPedidos(pedidos) {
        console.log('Actualizando interfaz con', pedidos.length, 'pedidos');
        
        // Agrupar pedidos por estado
        const pedidosPorEstado = {
            'pendiente': pedidos.filter(p => p.estado === 'pendiente'),
            'en_preparacion': pedidos.filter(p => p.estado === 'en_preparacion'),
            'listo': pedidos.filter(p => p.estado === 'listo'),
            'procesando_pago': pedidos.filter(p => p.estado === 'procesando_pago')
        };

        // Actualizar cada columna
        this.actualizarColumna('pendiente', pedidosPorEstado.pendiente);
        this.actualizarColumna('en_preparacion', pedidosPorEstado.en_preparacion);
        this.actualizarColumna('listo', pedidosPorEstado.listo);
        
        // Mostrar notificación si hay nuevos pedidos
        if (pedidosPorEstado.pendiente.length > 0) {
            this.mostrarNotificacionNuevosPedidos(pedidosPorEstado.pendiente);
        }
    }

    actualizarColumna(estado, pedidos) {
        const columna = document.getElementById(estado);
        if (!columna) return;

        // Si es la primera carga o hay cambios significativos, recargar completa
        if (pedidos.length === 0 || this.debeRecargarColumna(estado, pedidos)) {
            this.cargarColumnaViaAPI(estado);
        } else {
            // Actualización incremental (más eficiente)
            this.actualizarPedidosIndividuales(estado, pedidos);
        }
    }

    cargarColumnaViaAPI(estado) {
        fetch(`/panel/pedidos/${estado}/html/`)
            .then(response => response.text())
            .then(html => {
                const columna = document.getElementById(estado);
                if (columna) {
                    columna.innerHTML = html;
                    this.inicializarEventosColumna(estado);
                }
            })
            .catch(error => {
                console.error(`Error cargando columna ${estado}:`, error);
            });
    }

    startHeartbeatCheck() {
        this.lastHeartbeat = Date.now();
        this.heartbeatInterval = setInterval(() => {
            const timeSinceHeartbeat = Date.now() - this.lastHeartbeat;
            if (timeSinceHeartbeat > 35000) { // 35 segundos sin heartbeat
                console.warn('No heartbeat received, reconnecting...');
                this.reconnect();
            }
        }, 10000); // Verificar cada 10 segundos
    }

    stopHeartbeatCheck() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    reconnect() {
        this.disconnect();
        
        setTimeout(() => {
            console.log(`Reconectando SSE (delay: ${this.reconnectDelay}ms)`);
            this.connect();
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
        }, this.reconnectDelay);
    }

    disconnect() {
        this.stopHeartbeatCheck();
        this.isConnected = false;
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }

    mostrarNotificacionNuevosPedidos(pedidosNuevos) {
        if (pedidosNuevos.length > 0 && this.isSoundEnabled()) {
            this.reproducirSonidoNotificacion();
        }
        
        const mensaje = pedidosNuevos.length === 1 
            ? `Nuevo pedido #${pedidosNuevos[0].numero_pedido} recibido`
            : `${pedidosNuevos.length} nuevos pedidos recibidos`;
            
        this.showNotification(mensaje, 'success');
    }

    isSoundEnabled() {
        return localStorage.getItem('isSoundEnabled') === 'true';
    }

    reproducirSonidoNotificacion() {
        // Usar el mismo audio que ya tienes
        const audio = document.getElementById('notificationSound');
        if (audio) {
            audio.play().catch(e => console.log('No se pudo reproducir sonido:', e));
        }
    }

    showNotification(message, type) {
        // Usar tu función existente de notificación
        if (typeof showNotification === 'function') {
            showNotification(message, type);
        } else {
            // Fallback simple
            console.log(`${type}: ${message}`);
        }
    }

    // Helper methods
    debeRecargarColumna(estado, nuevosPedidos) {
        const columna = document.getElementById(estado);
        const cantidadActual = columna.querySelectorAll('.order-card').length;
        return Math.abs(cantidadActual - nuevosPedidos.length) > 2;
    }
}

// Inicialización automática cuando el DOM está listo
document.addEventListener('DOMContentLoaded', function() {
    const restauranteId = document.querySelector('meta[name="restaurante-id"]')?.content;
    
    if (restauranteId) {
        window.sseManager = new SSEManager(restauranteId);
        window.sseManager.connect();
        
        // Reconectar cuando la página vuelve a estar visible
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden && !window.sseManager.isConnected) {
                window.sseManager.connect();
            }
        });
    }
});