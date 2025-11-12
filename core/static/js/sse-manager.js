// static/js/sse-manager.js - VERSIÓN MEJORADA
class SSEManager {
    constructor(restauranteId) {
        this.restauranteId = restauranteId;
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.currentVersion = 0;
        this.isConnected = false;
        this.heartbeatInterval = null;
        this.lastPedidos = {};
        
        console.log(`SSE Manager inicializado para restaurante: ${restauranteId}`);
    }

    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

        try {
            const url = `/api/pedidos-sse/${this.restauranteId}/?version=${this.currentVersion}`;
            console.log('Conectando SSE a:', url);
            this.eventSource = new EventSource(url);
            
            this.eventSource.onopen = () => {
                console.log('SSE conectado exitosamente');
                this.isConnected = true;
                this.reconnectDelay = 1000;
                this.showNotification('Conexión en tiempo real establecida', 'success');
                
                this.startHeartbeatCheck();
            };

            this.eventSource.onmessage = (event) => {
                try {
                    console.log('SSE mensaje recibido:', event.data);
                    const data = JSON.parse(event.data);
                    this.handleEvent(data);
                } catch (e) {
                    console.error('Error parsing SSE data:', e, 'Raw data:', event.data);
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
        console.log('Procesando evento SSE:', data.type);
        
        switch(data.type) {
            case 'pedidos_updated':
                this.currentVersion = data.version;
                this.actualizarInterfazPedidos(data.pedidos);
                break;
                
            case 'heartbeat':
                this.lastHeartbeat = Date.now();
                console.log('Heartbeat recibido');
                break;
                
            case 'error':
                console.error('Error del servidor SSE:', data.message);
                this.showNotification(`Error: ${data.message}`, 'error');
                break;
                
            default:
                console.log('SSE event desconocido:', data);
        }
    }

    actualizarInterfazPedidos(pedidos) {
        console.log('Actualizando interfaz con', pedidos.length, 'pedidos');
        
        // ✅ ESTRATEGIA MEJORADA: Recargar columnas completas solo si hay cambios significativos
        const cambiosSignificativos = this.detectarCambiosSignificativos(pedidos);
        
        if (cambiosSignificativos) {
            console.log('Cambios significativos detectados, recargando columnas...');
            this.recargarTodasLasColumnas();
        } else {
            console.log('Cambios menores, actualizando individualmente...');
            this.actualizarPedidosIndividuales(pedidos);
        }
        
        this.lastPedidos = this.agruparPorEstado(pedidos);
    }

    detectarCambiosSignificativos(nuevosPedidos) {
        const nuevosAgrupados = this.agruparPorEstado(nuevosPedidos);
        const anterioresAgrupados = this.lastPedidos;
        
        // Considerar cambios significativos si:
        // 1. Cambió la cantidad de pedidos en alguna columna
        // 2. Hay nuevos pedidos pendientes (para sonido)
        for (const estado in nuevosAgrupados) {
            const cantidadAnterior = anterioresAgrupados[estado] ? anterioresAgrupados[estado].length : 0;
            const cantidadNueva = nuevosAgrupados[estado].length;
            
            if (Math.abs(cantidadNueva - cantidadAnterior) > 0) {
                if (estado === 'pendiente' && cantidadNueva > cantidadAnterior) {
                    this.mostrarNotificacionNuevosPedidos(nuevosAgrupados[estado]);
                }
                return true;
            }
        }
        
        return false;
    }

    agruparPorEstado(pedidos) {
        return {
            'pendiente': pedidos.filter(p => p.estado === 'pendiente'),
            'en_preparacion': pedidos.filter(p => p.estado === 'en_preparacion'),
            'listo': pedidos.filter(p => p.estado === 'listo'),
            'procesando_pago': pedidos.filter(p => p.estado === 'procesando_pago')
        };
    }

    recargarTodasLasColumnas() {
        ['pendiente', 'en_preparacion', 'listo'].forEach(estado => {
            this.cargarColumnaViaAPI(estado);
        });
    }

    cargarColumnaViaAPI(estado) {
        console.log(`Recargando columna ${estado} via API`);
        
        fetch(`/panel/pedidos/${estado}/html/`)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.text();
            })
            .then(html => {
                const columna = document.getElementById(estado);
                if (columna) {
                    columna.innerHTML = html;
                    this.inicializarEventosColumna(estado);
                    console.log(`Columna ${estado} actualizada`);
                }
            })
            .catch(error => {
                console.error(`Error cargando columna ${estado}:`, error);
            });
    }

    actualizarPedidosIndividuales(pedidos) {
        // Implementación simple: recargar si hay cambios
        this.recargarTodasLasColumnas();
    }

    inicializarEventosColumna(estado) {
        // Los eventos ya están manejados por delegación en el documento
        console.log(`Eventos inicializados para columna ${estado}`);
    }

    startHeartbeatCheck() {
        this.lastHeartbeat = Date.now();
        this.heartbeatInterval = setInterval(() => {
            const timeSinceHeartbeat = Date.now() - this.lastHeartbeat;
            if (timeSinceHeartbeat > 35000) {
                console.warn('No heartbeat received, reconnecting...');
                this.reconnect();
            }
        }, 10000);
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
            this.reproducirSonidoNotificacion(pedidosNuevos[0].id);
        }
        
        const mensaje = pedidosNuevos.length === 1 
            ? `Nuevo pedido #${pedidosNuevos[0].numero_pedido} recibido`
            : `${pedidosNuevos.length} nuevos pedidos recibidos`;
            
        this.showNotification(mensaje, 'success');
    }

    isSoundEnabled() {
        return localStorage.getItem('isSoundEnabled') === 'true';
    }

    reproducirSonidoNotificacion(pedidoId) {
        if (typeof window.playNotificationSound === 'function') {
            window.playNotificationSound(pedidoId);
        } else {
            const audio = document.getElementById('notificationSound');
            if (audio) {
                audio.play().catch(e => console.log('No se pudo reproducir sonido:', e));
            }
        }
    }

    showNotification(message, type) {
        if (typeof showNotification === 'function') {
            showNotification(message, type);
        } else {
            // Fallback simple
            console.log(`${type}: ${message}`);
        }
    }
}

// Inicialización automática
document.addEventListener('DOMContentLoaded', function() {
    const restauranteId = document.querySelector('meta[name="restaurante-id"]')?.content;
    
    if (restauranteId) {
        window.sseManager = new SSEManager(restauranteId);
        window.sseManager.connect();
        
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden && !window.sseManager.isConnected) {
                window.sseManager.connect();
            }
        });
    }
});