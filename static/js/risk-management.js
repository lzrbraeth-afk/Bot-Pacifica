/**
 * ================================================
 * RISK MANAGEMENT MODULE
 * ================================================
 * Handles risk monitoring and display
 */

class RiskManager {
    constructor() {
        this.updateInterval = null;
        this.isMonitoring = false;
    }

    /**
     * Start risk monitoring
     */
    startMonitoring() {
        if (this.isMonitoring) return;

        this.isMonitoring = true;
        this.updateRiskData();

        this.updateInterval = setInterval(() => {
            this.updateRiskData();
        }, CONFIG.INTERVALS.RISK_DASHBOARD);

        console.log('✅ Risk monitoring started');
    }

    /**
     * Stop risk monitoring
     */
    stopMonitoring() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        this.isMonitoring = false;

        console.log('⏸️ Risk monitoring stopped');
    }

    /**
     * Update risk data
     */
    async updateRiskData() {
        try {
            const [active, status] = await Promise.all([
                api.getRiskTelemetry(),
                api.getRiskStatus()
            ]);

            this.displayRiskMetrics(active, status);
        } catch (error) {
            console.error('Error updating risk data:', error);
        }
    }

    /**
     * Display risk metrics
     */
    displayRiskMetrics(active, status) {
        // Update configurations
        this.updateElement('cfg-cycle-sl', this.getValue(active, 'extra.cycle_thresholds.sl%', '—'));
        this.updateElement('cfg-cycle-tp', this.getValue(active, 'extra.cycle_thresholds.tp%', '—'));
        this.updateElement('cfg-emerg-sl', this.getValue(status, 'emergency_sl_percent', '—'));
        this.updateElement('cfg-emerg-tp', this.getValue(status, 'emergency_tp_percent', '—'));
        this.updateElement('cfg-margin', this.getValue(status, 'margin_percent', '—'));
        this.updateElement('cfg-session-loss', this.getValue(status, 'session_max_loss_usd', '—'));
        this.updateElement('cfg-session-profit', this.getValue(status, 'session_profit_target_usd', '—'));

        // Update active trade
        const trade = active.trade || {};
        this.updateElement('trade-id', trade.trade_id || '—');
        this.updateElement('trade-symbol', trade.symbol || '—');
        this.updateElement('trade-side', trade.side || '—');
        this.updateElement('trade-time', this.formatTime(trade.time_in_trade_sec));
        this.updateElement('trade-price', this.formatNumber(trade.current_price));

        // Update PNL with color
        const pnlUsd = trade.pnl_usd || 0;
        const pnlPct = trade.pnl_percent || 0;
        const pnlColor = pnlUsd > 0 ? '#4ade80' : pnlUsd < 0 ? '#f87171' : '#e5e7eb';

        const pnlUsdElement = document.getElementById('trade-pnl-usd');
        const pnlPctElement = document.getElementById('trade-pnl-pct');

        if (pnlUsdElement) {
            pnlUsdElement.textContent = `$${this.formatNumber(pnlUsd)}`;
            pnlUsdElement.style.color = pnlColor;
        }

        if (pnlPctElement) {
            pnlPctElement.textContent = `${this.formatNumber(pnlPct)}%`;
            pnlPctElement.style.color = pnlColor;
        }

        // Update trade status
        const statusText = active.active ? 'Trade em andamento' : 'Nenhum trade ativo';
        this.updateElement('trade-status', statusText);

        // Update session metrics
        const session = this.getValue(active, 'extra.session', {});
        this.updateElement('session-cycles', session.cycles_closed || '0');
        this.updateElement('session-pnl', this.formatNumber(session.accumulated_pnl || 0));
        this.updateElement('session-margin', this.formatNumber(status.margin_percent || 0));
        this.updateElement('session-lastcheck', new Date().toLocaleTimeString());

        // Update status indicator
        const indicator = document.getElementById('risk-status-indicator');
        if (indicator) {
            const isActive = active.active === true || (active.trade && Object.keys(active.trade).length > 0);
            indicator.textContent = isActive ? 'Online' : 'Parado';
            indicator.className = isActive ? 'status-badge status-badge--success' : 'status-badge status-badge--danger';
        }
    }

    /**
     * Get nested property value safely
     */
    getValue(obj, path, defaultValue = '—') {
        const keys = path.split('.');
        let value = obj;

        for (const key of keys) {
            if (value && typeof value === 'object' && key in value) {
                value = value[key];
            } else {
                return defaultValue;
            }
        }

        return value !== null && value !== undefined ? value : defaultValue;
    }

    /**
     * Format number
     */
    formatNumber(value, decimals = 2) {
        if (value === null || value === undefined || isNaN(value)) {
            return '—';
        }
        return parseFloat(value).toFixed(decimals);
    }

    /**
     * Format time in seconds to readable format
     */
    formatTime(seconds) {
        if (!seconds || isNaN(seconds)) return '—';

        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;

        return `${h}h ${m}m ${s}s`;
    }

    /**
     * Update element content safely
     */
    updateElement(id, content) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = content;
        }
    }
}

// Create singleton instance
const riskManager = new RiskManager();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = riskManager;
}