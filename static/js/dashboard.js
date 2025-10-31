/**
 * ================================================
 * DASHBOARD CONTROLLER
 * ================================================
 * Main dashboard logic and UI management
 */

class Dashboard {
    constructor() {
        this.currentTab = 'dashboard';
        this.updateIntervals = new Map();
        this.charts = new Map();
    }

    /**
     * Initialize dashboard
     */
    async init() {
        console.log('🚀 Initializing Dashboard...');

        // Setup event listeners
        this.setupEventListeners();

        // Connect WebSocket
        if (CONFIG.FEATURES.WEBSOCKET_ENABLED) {
            websocket.connect();
            this.setupWebSocketHandlers();
        }

        // Load initial data
        await this.loadInitialData();

        // Setup auto-refresh intervals
        this.setupAutoRefresh();

        // Show dashboard tab
        this.showTab('dashboard');

        console.log('✅ Dashboard initialized');
    }

    /**
     * Setup DOM event listeners
     */
    setupEventListeners() {
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const tabId = tab.id.replace('tab-', '');
                this.showTab(tabId);
            });
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + R: Refresh current view
            if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
                e.preventDefault();
                this.refreshCurrentView();
            }
        });
    }

    /**
     * Setup WebSocket event handlers
     */
    setupWebSocketHandlers() {
        websocket.on('bot_status_update', (data) => {
            this.updateBotStatus(data);
        });

        websocket.on('metrics_update', (data) => {
            this.updateMetrics(data);
        });

        websocket.on('positions_update', (data) => {
            this.updatePositions(data);
            this.updateLastUpdateTime();
        });

        websocket.on('orders_update', (data) => {
            this.updateOrders(data);
            this.updateLastUpdateTime();
        });

        websocket.on('logs_update', (data) => {
            this.updateLogs(data);
        });

        websocket.on('risk_update', (data) => {
            if (this.currentTab === 'dashboard') {
                this.updateRiskDashboard(data);
            }
        });

        websocket.on('alert', (data) => {
            this.showAlert(data.type, data.message);
        });
    }

    /**
     * Load initial data
     */
    async loadInitialData() {
        try {
            // Load bot status
            const status = await api.getBotStatus();
            this.updateBotStatus(status);

            // Load positions and orders
            await this.loadPositionsAndOrders();

            // Load account state
            const accountState = await api.getAccountState();
            this.updateAccountState(accountState);

        } catch (error) {
            console.error('❌ Error loading initial data:', error);
            this.showAlert('error', 'Erro ao carregar dados iniciais');
        }
    }

    /**
     * Setup auto-refresh intervals
     */
    setupAutoRefresh() {
        // Positions and orders refresh
        this.updateIntervals.set('positions', setInterval(() => {
            if (this.currentTab === 'dashboard') {
                this.loadPositionsAndOrders();
            }
        }, CONFIG.INTERVALS.POSITIONS_UPDATE));

        // Risk dashboard refresh
        this.updateIntervals.set('risk', setInterval(() => {
            if (this.currentTab === 'dashboard') {
                this.updateRiskDashboard();
            }
        }, CONFIG.INTERVALS.RISK_DASHBOARD));
    }

    /**
     * Show specific tab
     */
    showTab(tabId) {
        this.currentTab = tabId;

        // Update tab buttons
        document.querySelectorAll('.tab').forEach(tab => {
            const isActive = tab.id === `tab-${tabId}`;
            tab.classList.toggle('tab--active', isActive);
            tab.setAttribute('aria-selected', isActive);
        });

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            const isActive = content.id === `content-${tabId}`;
            content.classList.toggle('tab-content--active', isActive);
        });

        // Load tab-specific data
        this.loadTabData(tabId);

        // Save last tab to localStorage
        localStorage.setItem(CONFIG.STORAGE.LAST_TAB, tabId);
    }

    /**
     * Load tab-specific data
     */
    async loadTabData(tabId) {
        switch (tabId) {
            case 'dashboard':
                await this.loadPositionsAndOrders();
                await this.updateRiskDashboard();
                break;
            case 'volume':
                await this.loadVolumeData();
                break;
            case 'trades':
                await this.loadTrades();
                break;
            case 'logs':
                await this.loadLogs();
                break;
            case 'csv-analysis':
                await this.loadCSVAnalysis();
                break;
            case 'config':
                await this.loadConfiguration();
                break;
        }
    }

    /**
     * Update bot status
     */
    updateBotStatus(data) {
        const statusText = document.getElementById('status-text');
        const btnStart = document.getElementById('btn-start');
        const btnStop = document.getElementById('btn-stop');
        const btnStopForce = document.getElementById('btn-stop-force');
        const btnRestart = document.getElementById('btn-restart');

        if (data.running) {
            statusText.innerHTML = '🟢 Rodando <span class="status-dot status-dot--active"></span>';
            
            btnStart.disabled = true;
            btnStop.disabled = false;
            btnStopForce.disabled = false;
            btnRestart.disabled = false;
        } else {
            statusText.textContent = '🔴 Parado';
            
            btnStart.disabled = false;
            btnStop.disabled = true;
            btnStopForce.disabled = true;
            btnRestart.disabled = true;
        }

        // Update last update timestamp
        this.updateLastUpdateTime();
    }

    /**
     * Update metrics
     */
    updateMetrics(data) {
        // PNL
        const pnlElement = document.getElementById('pnl-text');
        if (pnlElement) {
            const pnl = data?.accumulated_pnl || 0;
            pnlElement.textContent = `$${pnl.toFixed(2)}`;
            pnlElement.className = pnl >= 0 ? 'metric-card__value text-success' : 'metric-card__value text-danger';
        }

        // Volume
        const volumeElement = document.getElementById('volume-text');
        if (volumeElement) {
            volumeElement.textContent = `$${(data?.total_volume || 0).toFixed(0)}`;
        }

        // Summary metrics
        this.updateElement('unrealized-pnl', `$${(data?.unrealized_pnl || 0).toFixed(2)}`);
        this.updateElement('realized-pnl', `$${(data?.realized_pnl || 0).toFixed(2)}`);
    }

    /**
     * Load positions and orders
     */
    async loadPositionsAndOrders() {
        try {
            const [positions, orders, accountState] = await Promise.all([
                api.getPositions(),
                api.getOrders(),
                api.getAccountState()
            ]);

            this.updatePositions(positions);
            this.updateOrders(orders);
            this.updateAccountState(accountState);
            this.updateLastUpdateTime();

        } catch (error) {
            console.error('❌ Error loading positions/orders:', error);
        }
    }

    /**
     * Update positions display
     */
    updatePositions(positions) {
        const container = document.getElementById('positions-container');
        const countElement = document.getElementById('positions-count');

        if (!container) return;

        if (countElement) {
            countElement.textContent = positions.length;
        }

        if (positions.length === 0) {
            container.innerHTML = '<p class="empty-state">Nenhuma posição ativa</p>';
            return;
        }

        container.innerHTML = positions.map(position => this.createPositionCard(position)).join('');
    }

    /**
     * Create position card HTML
     */
    createPositionCard(position) {
        const pnl = parseFloat(position.pnl_usd || 0);
        const pnlPercent = parseFloat(position.pnl_percent || 0);
        const pnlClass = pnl >= 0 ? 'text-success' : 'text-danger';
        const sideClass = (position.side || '').toLowerCase().includes('long') ? 
            'position-card--long' : 'position-card--short';
        const sideLabel = (position.side || '').toLowerCase().includes('long') ? 
            '🟢 LONG' : '🔴 SHORT';

        return `
            <div class="position-card ${sideClass}">
                <div class="position-header">
                    <div>
                        <div class="position-symbol">${position.symbol || '-'}</div>
                        <small class="text-muted">${sideLabel}</small>
                    </div>
                    <div class="position-pnl ${pnlClass}">
                        ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}
                    </div>
                </div>
                <div class="position-details">
                    <div class="detail-item">
                        <span class="detail-label">Tamanho:</span>
                        <span class="detail-value">${parseFloat(position.size || 0).toFixed(4)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Entrada:</span>
                        <span class="detail-value">$${parseFloat(position.entry_price || 0).toFixed(2)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Atual:</span>
                        <span class="detail-value">$${parseFloat(position.current_price || 0).toFixed(2)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">PNL %:</span>
                        <span class="detail-value ${pnlClass}">${pnlPercent.toFixed(2)}%</span>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Update orders display
     */
    updateOrders(orders) {
        const container = document.getElementById('orders-container');
        const countElement = document.getElementById('orders-count');
        const buyCountElement = document.getElementById('buy-orders-count');
        const sellCountElement = document.getElementById('sell-orders-count');

        if (!container) return;

        const buyOrders = orders.filter(o => {
            const side = (o.side || '').toLowerCase();
            return side.includes('buy') || side === 'bid';
        }).length;

        const sellOrders = orders.length - buyOrders;

        if (countElement) countElement.textContent = orders.length;
        if (buyCountElement) buyCountElement.textContent = buyOrders;
        if (sellCountElement) sellCountElement.textContent = sellOrders;

        if (orders.length === 0) {
            container.innerHTML = '<p class="empty-state">Nenhuma ordem aberta</p>';
            return;
        }

        container.innerHTML = orders.map(order => this.createOrderCard(order)).join('');
    }

    /**
     * Create order card HTML
     */
    createOrderCard(order) {
        const side = (order.side || '').toLowerCase();
        const isBuy = side.includes('buy') || side === 'bid';
        const sideClass = isBuy ? 'order-card--buy' : 'order-card--sell';
        const sideLabel = isBuy ? '🟢 BUY' : '🔴 SELL';

        return `
            <div class="order-card ${sideClass}">
                <div class="order-header">
                    <div>
                        <span class="order-symbol">${order.symbol || '-'}</span>
                        <span class="${isBuy ? 'text-success' : 'text-danger'}">${sideLabel}</span>
                    </div>
                    <button onclick="dashboard.cancelOrder('${order.order_id || order.id}')" 
                            class="btn btn--sm btn--danger"
                            title="Cancelar ordem">
                        ❌
                    </button>
                </div>
                <div class="order-details">
                    <div class="detail-item">
                        <span class="detail-label">Preço:</span>
                        <span class="detail-value">$${parseFloat(order.price || 0).toFixed(2)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Tamanho:</span>
                        <span class="detail-value">${parseFloat(order.size || 0).toFixed(4)}</span>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Cancel order
     */
    async cancelOrder(orderId) {
        if (!confirm('🚫 Cancelar esta ordem?')) return;

        try {
            this.showAlert('info', '🔄 Cancelando ordem...');
            
            const result = await api.cancelOrder(orderId);
            
            if (result.success) {
                this.showAlert('success', '✅ Ordem cancelada');
                setTimeout(() => this.loadPositionsAndOrders(), 500);
            } else {
                this.showAlert('error', `❌ ${result.message}`);
            }
        } catch (error) {
            console.error('Error canceling order:', error);
            this.showAlert('error', '❌ Erro ao cancelar ordem');
        }
    }

    /**
     * Update account state
     */
    updateAccountState(state) {
        this.updateElement('account-balance', `$${(state.balance || 0).toFixed(2)}`);
        this.updateElement('margin-used', `$${(state.margin_used || 0).toFixed(2)}`);
        this.updateElement('margin-available', `$${(state.margin_available || 0).toFixed(2)}`);

        const marginPercent = state.margin_free_percent || 0;
        const marginPercentElement = document.getElementById('margin-free-percent');
        const marginBarElement = document.getElementById('margin-free-bar');

        if (marginPercentElement) {
            marginPercentElement.textContent = `${marginPercent.toFixed(1)}%`;
            
            // Update color based on percentage
            const colorClass = marginPercent < 20 ? 'text-danger' : 
                              marginPercent < 50 ? 'text-warning' : 'text-success';
            marginPercentElement.className = `utilization__value ${colorClass}`;
        }

        if (marginBarElement) {
            marginBarElement.style.width = `${marginPercent}%`;
            
            const barClass = marginPercent < 20 ? 'progress-bar__fill--danger' :
                            marginPercent < 50 ? 'progress-bar__fill--warning' : '';
            marginBarElement.className = `progress-bar__fill ${barClass}`;
        }
    }

    /**
     * Update risk dashboard
     */
    async updateRiskDashboard() {
        try {
            const [active, status] = await Promise.all([
                api.getRiskTelemetry(),
                api.getRiskStatus()
            ]);

            // Update risk metrics in UI
            // Implementation depends on specific risk dashboard structure
            
        } catch (error) {
            console.error('Error updating risk dashboard:', error);
        }
    }

    /**
     * Update last update timestamp
     */
    updateLastUpdateTime() {
        const now = new Date();
        const timeString = now.toLocaleTimeString('pt-BR');
        this.updateElement('last-update', `Última atualização: ${timeString}`);
    }

    /**
     * Show alert/toast
     */
    showAlert(type, message, duration = CONFIG.UI.TOAST_DURATION) {
        const container = document.getElementById('alerts-container');
        if (!container) return;

        const id = `alert-${Date.now()}`;
        const alert = document.createElement('div');
        alert.id = id;
        alert.className = `alert alert--${type}`;
        alert.innerHTML = `
            <span>${message}</span>
            <button class="alert__close" onclick="dashboard.closeAlert('${id}')" aria-label="Fechar">✕</button>
        `;

        container.appendChild(alert);

        setTimeout(() => this.closeAlert(id), duration);
    }

    /**
     * Close alert
     */
    closeAlert(id) {
        const alert = document.getElementById(id);
        if (alert) {
            alert.style.animation = 'fadeOut 0.3s ease-out forwards';
            setTimeout(() => alert.remove(), 300);
        }
    }

    /**
     * Utility: Update element text content
     */
    updateElement(id, content) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = content;
        }
    }

    /**
     * Refresh current view
     */
    refreshCurrentView() {
        console.log('🔄 Refreshing current view...');
        this.loadTabData(this.currentTab);
    }

    /**
     * Load volume data (stub - implement as needed)
     */
    async loadVolumeData() {
        console.log('Loading volume data...');
        // Implementation...
    }

    /**
     * Load trades (stub - implement as needed)
     */
    async loadTrades() {
        console.log('Loading trades...');
        // Implementation...
    }

    /**
     * Load logs (stub - implement as needed)
     */
    async loadLogs() {
        console.log('Loading logs...');
        // Implementation...
    }

    /**
     * Load CSV analysis (stub - implement as needed)
     */
    async loadCSVAnalysis() {
        console.log('Loading CSV analysis...');
        // Implementation...
    }

    /**
     * Load configuration (stub - implement as needed)
     */
    async loadConfiguration() {
        console.log('Loading configuration...');
        // Implementation...
    }

    /**
     * Cleanup on destroy
     */
    destroy() {
        // Clear all intervals
        this.updateIntervals.forEach(interval => clearInterval(interval));
        this.updateIntervals.clear();

        // Disconnect WebSocket
        websocket.disconnect();

        // Destroy charts
        this.charts.forEach(chart => chart.destroy());
        this.charts.clear();
    }
}

// Create singleton instance
const dashboard = new Dashboard();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = dashboard;
}