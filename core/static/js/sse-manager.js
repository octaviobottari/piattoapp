// static/js/sse-manager.js - VERSIÓN RÁPIDA Y SINCRONIZADA
class SSEManager {
    constructor(restauranteId) {
        this.restauranteId = restauranteId;
        this.eventSource = null;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.currentVersion = 0;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        
        console.log(`🚀 SSE Manager inicializado para restaurante: ${restauranteId}`);
        
        // ✅ NUEVO: Cache simple para evitar duplicados
        this.lastPedidoIds = new Set();
        
        // ✅ NUEVO: Forzar recarga cada 15 segundos como fallback
        this.forceRefreshInterval = setInterval(() => {
            this.forceRefreshIfNeeded();
        }, 15000);
    }

    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

        try {
            const url = `/api/pedidos-sse/${this.restauranteId}/?version=${this.currentVersion}&_=${Date.now()}`;
            console.log('🔗 Conectando SSE a:', url);
            this.eventSource = new EventSource(url);
            
            this.eventSource.onopen = () => {
                console.log('✅ SSE conectado exitosamente');
                this.isConnected = true;
                this.reconnectDelay = 1000;
                this.reconnectAttempts = 0;
                
                // ✅ CARGAR INMEDIATAMENTE AL CONECTAR
                this.recargarTodasLasColumnas();
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
                this.procesarPedidosActualizados(data.pedidos);
                break;
                
            case 'nuevo_pedido':
                console.log('🎉 Evento: NUEVO PEDIDO detectado:', data.pedido);
                this.procesarNuevoPedido(data.pedido);
                break;
                
            default:
                console.log('📨 SSE event desconocido:', data);
        }
    }

    // ✅ NUEVO: Procesamiento rápido de nuevos pedidos
    procesarNuevoPedido(nuevoPedido) {
        console.log('🎯 Procesando NUEVO pedido inmediatamente:', nuevoPedido);
        
        // ✅ SONIDO INMEDIATO
        this.reproducirSonidoInmediato();
        
        // ✅ NOTIFICACIÓN INMEDIATA
        this.mostrarNotificacionInmediata(`📦 Nuevo pedido #${nuevoPedido.numero_pedido}`);
        
        // ✅ ACTUALIZACIÓN INMEDIATA de solo pendientes
        this.actualizarColumnaInmediata('pendiente');
    }

    // ✅ NUEVO: Procesamiento rápido de actualizaciones
    procesarPedidosActualizados(pedidos) {
        console.log('🔄 Procesando pedidos actualizados:', pedidos.length);
        
        // Detectar cambios rápidamente
        const nuevosIds = new Set(pedidos.map(p => p.id));
        const nuevosPendientes = pedidos.filter(p => p.estado === 'pendiente' && !this.lastPedidoIds.has(p.id));
        
        if (nuevosPendientes.length > 0) {
            console.log('🎉 Nuevos pedidos pendientes detectados:', nuevosPendientes.length);
            this.reproducirSonidoInmediato();
            this.mostrarNotificacionInmediata(`📦 ${nuevosPendientes.length} nuevo(s) pedido(s)`);
        }
        
        // Actualizar cache
        this.lastPedidoIds = nuevosIds;
        
        // Recargar todas las columnas inmediatamente
        this.recargarTodasLasColumnas();
    }

    // ✅ NUEVO: Recarga forzada si es necesario
    forceRefreshIfNeeded() {
        if (this.isConnected) {
            console.log('🔄 Verificación periódica de cambios...');
            this.recargarTodasLasColumnas();
        }
    }

    // ✅ NUEVO: Actualización inmediata de columna
    actualizarColumnaInmediata(estado) {
        console.log(`⚡ Actualización inmediata de columna: ${estado}`);
        
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
                return;
        }
        
        // ✅ SIN CACHE
        url += `${url.includes('?') ? '&' : '?'}_=${Date.now()}`;
        
        fetch(url)
            .then(response => response.text())
            .then(html => {
                const columna = document.getElementById(estado);
                if (columna) {
                    columna.innerHTML = html;
                    console.log(`✅ Columna ${estado} actualizada inmediatamente`);
                }
            })
            .catch(error => {
                console.error(`❌ Error actualizando columna ${estado}:`, error);
            });
    }

    // ✅ NUEVO: Sonido inmediato
    reproducirSonidoInmediato() {
        if (this.isSoundEnabled()) {
            console.log('🔊 Reproduciendo sonido inmediatamente');
            const audio = document.getElementById('notificationSound');
            if (audio) {
                // Resetear y reproducir inmediatamente
                audio.currentTime = 0;
                audio.play().catch(e => console.log('🔇 Sonido bloqueado, necesita interacción:', e));
            }
        }
    }

    // ✅ NUEVO: Notificación inmediata
    mostrarNotificacionInmediata(mensaje) {
        if (typeof showNotification === 'function') {
            showNotification(mensaje, 'success');
        } else {
            // Fallback básico
            console.log(`📢 ${mensaje}`);
        }
    }

    recargarTodasLasColumnas() {
        console.log('🔄 Recargando todas las columnas');
        
        const estados = ['pendiente', 'en_preparacion', 'listo'];
        
        estados.forEach(estado => {
            this.actualizarColumnaInmediata(estado);
        });
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
        this.isConnected = false;
        
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }

    isSoundEnabled() {
        return localStorage.getItem('isSoundEnabled') === 'true';
    }
}

// ✅ INICIALIZACIÓN RÁPIDA
document.addEventListener('DOMContentLoaded', function() {
    const restauranteId = document.querySelector('meta[name="restaurante-id"]')?.content;
    
    if (restauranteId) {
        console.log('🎯 Inicializando SSE Manager para restaurante:', restauranteId);
        window.sseManager = new SSEManager(restauranteId);
        window.sseManager.connect();
        
        // Reconexión rápida cuando la página vuelve a ser visible
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden && window.sseManager && !window.sseManager.isConnected) {
                console.log('🔄 Página visible, reconectando SSE...');
                window.sseManager.connect();
            }
        });
    }
});