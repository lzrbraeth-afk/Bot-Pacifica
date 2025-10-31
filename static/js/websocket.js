/**
 * ================================================
 * WEBSOCKET MANAGER
 * ================================================
 * Handles real-time communication via Socket.IO
 */

class WebSocketManager {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.eventHandlers = new Map();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    /**
     * Initialize WebSocket connection
     */
    connect() {
        if (this.socket) {
            console.warn('WebSocket already connected');
            return;
        }

        console.log('🔌 Initializing WebSocket connection...');

        this.socket = io(CONFIG.API.BASE_URL, CONFIG.WEBSOCKET);

        this.setupEventListeners();
    }

    /**
     * Setup default event listeners
     */
    setupEventListeners() {
        // Connection events
        this.socket.on('connect', () => {
            console.log('✅ WebSocket connected - ID:', this.socket.id);
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.updateConnectionStatus(true);
            this.emit('connected');
        });

        this.socket.on('disconnect', (reason) => {
            console.log('❌ WebSocket disconnected - Reason:', reason);
            this.isConnected = false;
            this.updateConnectionStatus(false);
            this.emit('disconnected', reason);
        });

        this.socket.on('connect_error', (error) => {
            console.error('❌ WebSocket connection error:', error.message);
            this.reconnectAttempts++;
            
            if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                console.error('❌ Max reconnection attempts reached');
                this.emit('connection_failed');
            }
        });

        // Application-specific events
        this.socket.on('bot_status_update', (data) => {
            this.emit('bot_status_update', data);
        });

        this.socket.on('metrics_update', (data) => {
            this.emit('metrics_update', data);
        });

        this.socket.on('pnl_history_update', (data) => {
            this.emit('pnl_history_update', data);
        });

        this.socket.on('positions_update', (data) => {
            this.emit('positions_update', data);
        });

        this.socket.on('orders_update', (data) => {
            this.emit('orders_update', data);
        });

        this.socket.on('logs_update', (data) => {
            this.emit('logs_update', data);
        });

        this.socket.on('risk_update', (data) => {
            this.emit('risk_update', data);
        });

        this.socket.on('alert', (data) => {
            this.emit('alert', data);
        });
    }

    /**
     * Register event handler
     */
    on(event, handler) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, []);
        }
        this.eventHandlers.get(event).push(handler);
    }

    /**
     * Remove event handler
     */
    off(event, handler) {
        if (!this.eventHandlers.has(event)) return;
        
        const handlers = this.eventHandlers.get(event);
        const index = handlers.indexOf(handler);
        
        if (index > -1) {
            handlers.splice(index, 1);
        }
    }

    /**
     * Emit event to registered handlers
     */
    emit(event, data) {
        if (!this.eventHandlers.has(event)) return;
        
        this.eventHandlers.get(event).forEach(handler => {
            try {
                handler(data);
            } catch (error) {
                console.error(`Error in event handler for ${event}:`, error);
            }
        });
    }

    /**
     * Update connection status in UI
     */
    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('refresh-status');
        if (!statusElement) return;

        const dot = statusElement.querySelector('.status-dot');
        const text = statusElement.querySelector('span:last-child');

        if (connected) {
            dot.classList.remove('status-dot--inactive');
            dot.classList.add('status-dot--active');
            text.textContent = 'Ativo (30s)';
        } else {
            dot.classList.remove('status-dot--active');
            dot.classList.add('status-dot--inactive');
            text.textContent = 'Desconectado';
        }
    }

    /**
     * Disconnect WebSocket
     */
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
            this.isConnected = false;
        }
    }

    /**
     * Reconnect WebSocket
     */
    reconnect() {
        this.disconnect();
        this.reconnectAttempts = 0;
        setTimeout(() => this.connect(), 1000);
    }
}

// Create singleton instance
const websocket = new WebSocketManager();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = websocket;
}