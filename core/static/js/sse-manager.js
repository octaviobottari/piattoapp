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
            console.log('🔄 Evento SSE recibido:', data.pedidos.length, 'pedidos');
            
            // ✅ SONIDO INMEDIATO si hay nuevos pedidos
            if (data.pedidos && data.pedidos.length > 0 && !data.immediate) {
                const nuevoPedido = data.pedidos.find(p => 
                    p.estado === 'pendiente' || p.estado === 'procesando_pago'
                );
                if (nuevoPedido) {
                    console.log('🔔 Nuevo pedido detectado:', nuevoPedido.numero_pedido);
                    this.playNotificationSound(nuevoPedido.numero_pedido);
                }
            }
            
            this.currentVersion = data.version;
            this.procesarPedidosActualizados(data.pedidos);
            break;
    }
}

playNotificationSound(pedidoId) {
    const audio = document.getElementById('notificationSound');
    const soundEnabled = localStorage.getItem('isSoundEnabled') !== 'false';
    
    if (!soundEnabled || !audio) {
        console.log('🔇 Sonido deshabilitado o audio no encontrado');
        return;
    }
    
    // ✅ RESET Y REPRODUCIR
    audio.currentTime = 0;
    audio.play().catch(error => {
        console.log('🔇 Sonido bloqueado, necesita interacción:', error);
        // Mostrar notificación visual
        this.showVisualNotification(pedidoId);
    });
}

// ✅ NOTIFICACIÓN VISUAL DE FALLBACK
showVisualNotification(pedidoId) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(`Nuevo Pedido #${pedidoId}`, {
            body: 'Tienes un nuevo pedido pendiente',
            icon: '/static/images/logo.png'
        });
    }
    
    // Notificación en página
    const notification = document.createElement('div');
    notification.innerHTML = `
        <div style="position: fixed; top: 20px; right: 20px; background: #28a745; color: white; padding: 15px; border-radius: 5px; z-index: 10000;">
            <strong>Nuevo Pedido #${pedidoId}</strong>
            <button onclick="this.parentElement.remove()" style="background: none; border: none; color: white; margin-left: 10px;">×</button>
        </div>
    `;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
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