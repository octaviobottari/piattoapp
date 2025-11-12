// static/js/sse-manager.js - OPTIMIZADO PARA 1000+ CONEXIONES
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
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.debounceTimer = null;
        
        console.log(`🚀 SSE Manager inicializado para restaurante: ${restauranteId}`);
    }

    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

        // ✅ LIMITAR RECONEXIONES EXCESIVAS
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('🚫 Máximo de intentos de reconexión alcanzado. Cambiando a polling.');
            this.switchToPolling();
            return;
        }

        try {
            const url = `/api/pedidos-sse/${this.restauranteId}/?version=${this.currentVersion}`;
            console.log('🔗 Conectando SSE a:', url);
            this.eventSource = new EventSource(url);
            
            this.eventSource.onopen = () => {
                console.log('✅ SSE conectado exitosamente');
                this.isConnected = true;
                this.reconnectDelay = 1000;
                this.reconnectAttempts = 0;
                
                // ✅ NOTIFICACIÓN SOLO EN PRIMERA CONEXIÓN
                if (this.reconnectAttempts === 0) {
                    this.showNotification('Conexión en tiempo real establecida', 'success');
                }
                
                this.startHeartbeatCheck();
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleEvent(data);
                } catch (e) {
                    console.error('❌ Error parsing SSE data:', e);
                }
            };

            this.eventSource.onerror = (error) => {
                console.error('❌ SSE error:', error);
                this.isConnected = false;
                this.stopHeartbeatCheck();
                this.reconnectAttempts++;
                this.reconnect();
            };

        } catch (error) {
            console.error('❌ Error creating SSE connection:', error);
            this.reconnectAttempts++;
            this.reconnect();
        }
    }

    handleEvent(data) {
        switch(data.type) {
            case 'pedidos_updated':
                this.currentVersion = data.version;
                // ✅ DEBOUNCE PARA EVITAR ACTUALIZACIONES MÚLTIPLES
                this.debouncedUpdate(data.pedidos);
                break;
                
            case 'heartbeat':
                this.lastHeartbeat = Date.now();
                break;
                
            case 'error':
                console.error('❌ Error del servidor SSE:', data.message);
                break;
                
            default:
                console.log('📨 SSE event desconocido:', data);
        }
    }

    // ✅ DEBOUNCE PARA EVITAR SOBRECARGA
    debouncedUpdate(pedidos) {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        this.debounceTimer = setTimeout(() => {
            this.actualizarInterfazPedidos(pedidos);
        }, 500); // 500ms debounce
    }

    actualizarInterfazPedidos(pedidos) {
        console.log('🔄 Actualizando interfaz con', pedidos.length, 'pedidos');
        
        // ✅ ESTRATEGIA INTELIGENTE: Solo recargar columnas con cambios
        const cambios = this.detectarCambiosPorColumna(pedidos);
        
        if (cambios.todos) {
            this.recargarTodasLasColumnas();
        } else {
            // Recargar solo las columnas que cambiaron
            cambios.columnas.forEach(estado => {
                this.cargarColumnaViaAPI(estado);
            });
        }
        
        // ✅ NOTIFICACIÓN PARA NUEVOS PEDIDOS
        if (cambios.nuevosPendientes.length > 0) {
            this.mostrarNotificacionNuevosPedidos(cambios.nuevosPendientes);
        }
        
        this.lastPedidos = this.agruparPorEstado(pedidos);
    }

    detectarCambiosPorColumna(nuevosPedidos) {
        const nuevosAgrupados = this.agruparPorEstado(nuevosPedidos);
        const anterioresAgrupados = this.lastPedidos;
        
        const cambios = {
            todos: false,
            columnas: [],
            nuevosPendientes: []
        };
        
        // Verificar cambios por columna
        for (const estado in nuevosAgrupados) {
            const cantidadAnterior = anterioresAgrupados[estado] ? anterioresAgrupados[estado].length : 0;
            const cantidadNueva = nuevosAgrupados[estado].length;
            
            if (cantidadNueva !== cantidadAnterior) {
                cambios.columnas.push(estado);
                
                // Detectar nuevos pedidos pendientes
                if (estado === 'pendiente' && cantidadNueva > cantidadAnterior) {
                    cambios.nuevosPendientes = nuevosAgrupados[estado].slice(cantidadAnterior);
                }
            }
        }
        
        // Si hay muchos cambios, recargar todo
        if (cambios.columnas.length >= 2) {
            cambios.todos = true;
        }
        
        return cambios;
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
        console.log('🔄 Recargando todas las columnas');
        
        const estados = ['pendiente', 'en_preparacion', 'listo'];
        
        // ✅ CARGAR EN PARALELO PERO CON LIMITE
        const promises = estados.map(estado => this.cargarColumnaViaAPI(estado));
        
        Promise.allSettled(promises)
            .then(results => {
                let exitosas = 0;
                results.forEach((result, index) => {
                    if (result.status === 'fulfilled') {
                        exitosas++;
                        console.log(`✅ Columna ${estados[index]} actualizada`);
                    } else {
                        console.error(`❌ Error en columna ${estados[index]}:`, result.reason);
                    }
                });
                console.log(`📊 Columnas actualizadas: ${exitosas}/${estados.length}`);
            });
    }

    cargarColumnaViaAPI(estado) {
        // ✅ URLs CORREGIDAS
        let url;
        switch(estado) {
            case 'pendiente':
                url = '/panel/pedidos/pendientes/html/';
                break;
            case 'en_preparacion':
                url = '/panel/pedidos/en_preparacion/html/';
                break;
            case 'listo':
                url = '/panel/pedidos/listos/html/';
                break;
            default:
                return Promise.reject(`Estado desconocido: ${estado}`);
        }
        
        return fetch(url)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.text();
            })
            .then(html => {
                const columna = document.getElementById(estado);
                if (columna) {
                    columna.innerHTML = html;
                    return html;
                } else {
                    throw new Error(`Elemento #${estado} no encontrado`);
                }
            })
            .catch(error => {
                console.error(`❌ Error cargando columna ${estado}:`, error);
                throw error;
            });
    }

    // ✅ FALLBACK A POLLING
    switchToPolling() {
        console.log('🔄 Cambiando a modo Polling');
        this.disconnect();
        
        this.pollingInterval = setInterval(() => {
            this.checkUpdatesViaPolling();
        }, 10000); // Cada 10 segundos
        
        this.showNotification('Modo polling activado', 'info');
    }

    checkUpdatesViaPolling() {
        fetch(`/api/pedidos-polling/${this.restauranteId}/?version=${this.currentVersion}`)
            .then(response => response.json())
            .then(data => {
                if (data.version > this.currentVersion) {
                    this.currentVersion = data.version;
                    this.actualizarInterfazPedidos(data.pedidos);
                }
            })
            .catch(error => console.error('❌ Error en polling:', error));
    }

    startHeartbeatCheck() {
        this.lastHeartbeat = Date.now();
        this.heartbeatInterval = setInterval(() => {
            const timeSinceHeartbeat = Date.now() - this.lastHeartbeat;
            if (timeSinceHeartbeat > 45000) { // 45 segundos
                console.warn('⏰ No heartbeat received, reconnecting...');
                this.reconnect();
            }
        }, 15000); // Verificar cada 15 segundos
    }

    stopHeartbeatCheck() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    reconnect() {
        this.disconnect();
        
        const delay = Math.min(this.reconnectDelay, this.maxReconnectDelay);
        console.log(`🔄 Reconectando en ${delay}ms (intento ${this.reconnectAttempts})`);
        
        setTimeout(() => {
            this.connect();
            this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
        }, delay);
    }

    disconnect() {
        this.stopHeartbeatCheck();
        this.isConnected = false;
        
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = null;
        }
        
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
        
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
            ? `📦 Nuevo pedido #${pedidosNuevos[0].numero_pedido}`
            : `📦 ${pedidosNuevos.length} nuevos pedidos`;
            
        this.showNotification(mensaje, 'success');
    }

    isSoundEnabled() {
        return localStorage.getItem('isSoundEnabled') === 'true';
    }

    reproducirSonidoNotificacion(pedidoId) {
        if (typeof window.playNotificationSound === 'function') {
            window.playNotificationSound(pedidoId);
        }
    }

    showNotification(message, type) {
        if (typeof showNotification === 'function') {
            showNotification(message, type);
        }
    }
}

// ✅ INICIALIZACIÓN OPTIMIZADA
document.addEventListener('DOMContentLoaded', function() {
    const restauranteId = document.querySelector('meta[name="restaurante-id"]')?.content;
    
    if (restauranteId) {
        // ✅ RETRASO INICIAL PARA EVITAR SOBRECARGA AL CARGAR LA PÁGINA
        setTimeout(() => {
            window.sseManager = new SSEManager(restauranteId);
            window.sseManager.connect();
        }, 2000);
        
        // ✅ RECONECTAR CUANDO LA PÁGINA VUELVE A SER VISIBLE
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden && window.sseManager && !window.sseManager.isConnected) {
                setTimeout(() => {
                    window.sseManager.connect();
                }, 1000);
            }
        });
    }
});