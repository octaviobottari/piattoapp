// static/js/sse-manager.js - VERSIÓN CORREGIDA
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
        
        // ✅ NUEVO: Cache de pedidos por estado para detectar cambios
        this.pedidosCache = {
            'pendiente': [],
            'en_preparacion': [],
            'listo': [],
            'procesando_pago': []
        };
    }

    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

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
                
                if (this.reconnectAttempts === 0) {
                    this.showNotification('Conexión en tiempo real establecida', 'success');
                }
                
                this.startHeartbeatCheck();
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('📨 Evento SSE recibido:', data.type);
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
                console.log('🔄 Evento: pedidos_updated, version:', data.version);
                this.currentVersion = data.version;
                this.debouncedUpdate(data.pedidos);
                break;
                
            case 'nuevo_pedido':
                console.log('🎉 Evento: NUEVO PEDIDO detectado:', data.pedido);
                this.handleNuevoPedido(data.pedido);
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

    // ✅ NUEVO: Manejo específico para nuevos pedidos
    handleNuevoPedido(nuevoPedido) {
        console.log('🎯 Procesando NUEVO pedido:', nuevoPedido);
        
        // Reproducir sonido si está habilitado
        if (this.isSoundEnabled()) {
            this.reproducirSonidoNotificacion(nuevoPedido.id);
        }
        
        // Mostrar notificación
        this.mostrarNotificacionNuevosPedidos([nuevoPedido]);
        
        // Actualizar la columna de pendientes
        this.actualizarColumnaPendientes();
    }

    // ✅ NUEVO: Actualizar solo columna de pendientes
    actualizarColumnaPendientes() {
        console.log('🔄 Actualizando columna de pendientes...');
        this.cargarColumnaViaAPI('pendiente')
            .then(() => {
                console.log('✅ Columna pendientes actualizada');
            })
            .catch(error => {
                console.error('❌ Error actualizando pendientes:', error);
            });
    }

    debouncedUpdate(pedidos) {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        this.debounceTimer = setTimeout(() => {
            this.actualizarInterfazPedidos(pedidos);
        }, 500);
    }

    actualizarInterfazPedidos(pedidos) {
        console.log('🔄 Actualizando interfaz con', pedidos.length, 'pedidos');
        
        const cambios = this.detectarCambiosPorColumna(pedidos);
        
        if (cambios.todos) {
            console.log('🔄 Cambios múltiples, recargando todas las columnas');
            this.recargarTodasLasColumnas();
        } else {
            console.log('🔄 Cambios en columnas:', cambios.columnas);
            cambios.columnas.forEach(estado => {
                this.cargarColumnaViaAPI(estado);
            });
        }
        
        // ✅ MEJORADO: Detección más precisa de nuevos pedidos
        if (cambios.nuevosPendientes.length > 0) {
            console.log('🎉 Nuevos pedidos pendientes detectados:', cambios.nuevosPendientes);
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
            const pedidosAnteriores = anterioresAgrupados[estado] || [];
            const pedidosNuevos = nuevosAgrupados[estado];
            
            const idsAnteriores = new Set(pedidosAnteriores.map(p => p.id));
            const idsNuevos = new Set(pedidosNuevos.map(p => p.id));
            
            // Verificar si hay cambios en cantidad
            if (pedidosNuevos.length !== pedidosAnteriores.length) {
                cambios.columnas.push(estado);
            }
            
            // Verificar si hay pedidos nuevos (solo para pendientes)
            if (estado === 'pendiente') {
                const nuevosIds = [...idsNuevos].filter(id => !idsAnteriores.has(id));
                if (nuevosIds.length > 0) {
                    const nuevosPedidosDetectados = pedidosNuevos.filter(p => nuevosIds.includes(p.id));
                    cambios.nuevosPendientes.push(...nuevosPedidosDetectados);
                }
            }
        }
        
        // Si hay cambios en múltiples columnas, recargar todo
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
        
        console.log(`📡 Cargando columna ${estado} desde: ${url}`);
        
        return fetch(url)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.text();
            })
            .then(html => {
                const columna = document.getElementById(estado);
                if (columna) {
                    columna.innerHTML = html;
                    console.log(`✅ Columna ${estado} actualizada con éxito`);
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

    switchToPolling() {
        console.log('🔄 Cambiando a modo Polling');
        this.disconnect();
        
        this.pollingInterval = setInterval(() => {
            this.checkUpdatesViaPolling();
        }, 10000);
        
        this.showNotification('Modo polling activado', 'info');
    }

    checkUpdatesViaPolling() {
        console.log('📡 Verificando actualizaciones via polling...');
        fetch(`/api/pedidos-polling/${this.restauranteId}/?version=${this.currentVersion}`)
            .then(response => response.json())
            .then(data => {
                if (data.version > this.currentVersion) {
                    console.log('🔄 Cambios detectados via polling, version:', data.version);
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
            if (timeSinceHeartbeat > 45000) {
                console.warn('⏰ No heartbeat received, reconnecting...');
                this.reconnect();
            }
        }, 15000);
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
            console.log('🔊 Reproduciendo sonido para nuevo pedido');
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
        } else {
            console.log('🔊 Función playNotificationSound no disponible, reproduciendo sonido directamente');
            // Fallback directo
            const audio = document.getElementById('notificationSound');
            if (audio) {
                audio.play().catch(e => console.error('Error reproduciendo sonido:', e));
            }
        }
    }

    showNotification(message, type) {
        if (typeof showNotification === 'function') {
            showNotification(message, type);
        } else {
            // Fallback básico
            console.log(`📢 ${type.toUpperCase()}: ${message}`);
        }
    }
}

// ✅ INICIALIZACIÓN MEJORADA
document.addEventListener('DOMContentLoaded', function() {
    const restauranteId = document.querySelector('meta[name="restaurante-id"]')?.content;
    
    if (restauranteId) {
        console.log('🎯 Inicializando SSE Manager para restaurante:', restauranteId);
        
        // ✅ INICIALIZACIÓN INMEDIATA (sin delay)
        window.sseManager = new SSEManager(restauranteId);
        window.sseManager.connect();
        
        // ✅ RECONECTAR CUANDO LA PÁGINA VUELVE A SER VISIBLE
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden && window.sseManager && !window.sseManager.isConnected) {
                console.log('🔄 Página visible, reconectando SSE...');
                window.sseManager.connect();
            }
        });

        // ✅ RECARGAR MANUAL SI SE NECESITA
        window.recargarPedidos = function() {
            if (window.sseManager) {
                console.log('🔄 Recarga manual solicitada');
                window.sseManager.recargarTodasLasColumnas();
            }
        };
    } else {
        console.error('❌ No se encontró restaurante-id para inicializar SSE');
    }
});