// static/js/sse-manager.js - VERSIÓN ULTRA-RÁPIDA
class SSEManager {
    constructor(restauranteId) {
        this.restauranteId = restauranteId;
        this.eventSource = null;
        this.reconnectDelay = 500; // ✅ REDUCIDO: 500ms
        this.maxReconnectDelay = 10000; // ✅ REDUCIDO: 10 segundos
        this.currentVersion = 0;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        
        console.log(`🚀 SSE Manager ULTRA-RÁPIDO inicializado para restaurante: ${restauranteId}`);
        
        // ✅ NUEVO: Cache para evitar duplicados
        this.lastPedidoIds = new Set();
        this.lastUpdateTime = Date.now();
        
        // ✅ NUEVO: Heartbeat para mantener conexión activa
        this.heartbeatInterval = setInterval(() => {
            if (this.isConnected) {
                console.log('💓 SSE Heartbeat');
            }
        }, 30000); // 30 segundos
    }

    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

        try {
            const url = `/api/pedidos-sse/${this.restauranteId}/?version=${this.currentVersion}&_=${Date.now()}`;
            console.log('🔗 Conectando SSE ULTRA-RÁPIDO a:', url);
            this.eventSource = new EventSource(url);
            
            this.eventSource.onopen = () => {
                console.log('✅ SSE conectado EXITOSAMENTE');
                this.isConnected = true;
                this.reconnectDelay = 500;
                this.reconnectAttempts = 0;
                this.lastUpdateTime = Date.now();
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('📨 Evento SSE RECIBIDO:', data.type, data.immediate ? '(INMEDIATO)' : '');
                    this.handleEvent(data);
                    this.lastUpdateTime = Date.now();
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
                console.log('🔄 Evento: pedidos_updated, version:', data.version, data.triggered ? '(TRIGGERED)' : '');
                this.currentVersion = data.version;
                this.procesarPedidosActualizados(data.pedidos);
                break;
                
            default:
                console.log('📨 SSE event desconocido:', data);
        }
    }

    procesarPedidosActualizados(pedidos) {
        console.log('⚡ Procesando pedidos actualizados:', pedidos.length);
        
        // ✅ ACTUALIZACIÓN INMEDIATA de todas las columnas
        this.recargarTodasLasColumnas();
    }

    recargarTodasLasColumnas() {
        console.log('🔄 Recargando TODAS las columnas INMEDIATAMENTE');
        
        const estados = ['pendiente', 'en_preparacion', 'listo'];
        const timestamp = Date.now();
        
        estados.forEach(estado => {
            this.actualizarColumnaInmediata(estado, timestamp);
        });
    }

    actualizarColumnaInmediata(estado, timestamp) {
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
        
        // ✅ SIN CACHE - timestamp único
        url += `${url.includes('?') ? '&' : '?'}_=${timestamp}`;
        
        fetch(url)
            .then(response => {
                if (!response.ok) throw new Error('Network error');
                return response.text();
            })
            .then(html => {
                const columna = document.getElementById(estado);
                if (columna) {
                    columna.innerHTML = html;
                    console.log(`✅ Columna ${estado} actualizada INSTANTÁNEAMENTE`);
                }
            })
            .catch(error => {
                console.error(`❌ Error actualizando columna ${estado}:`, error);
            });
    }

    reconnect() {
        this.disconnect();
        
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('🚨 Máximo de reconexiones alcanzado');
            return;
        }
        
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
        
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
        }
    }
}

// ✅ INICIALIZACIÓN ULTRA-RÁPIDA
document.addEventListener('DOMContentLoaded', function() {
    const restauranteId = document.querySelector('meta[name="restaurante-id"]')?.content;
    
    if (restauranteId) {
        console.log('🎯 Inicializando SSE Manager ULTRA-RÁPIDO para restaurante:', restauranteId);
        window.sseManager = new SSEManager(restauranteId);
        window.sseManager.connect();
        
        // Reconexión cuando la página vuelve a ser visible
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden && window.sseManager && !window.sseManager.isConnected) {
                console.log('🔄 Página visible, reconectando SSE...');
                window.sseManager.connect();
            }
        });
    }
});