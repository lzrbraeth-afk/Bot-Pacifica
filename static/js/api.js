// ==========================================
    // POSITIONS & ORDERS
    // ==========================================

    async getPositions() {
        return this.get('/api/positions');
    }

    async getOrders() {
        return this.get('/api/orders');
    }

    async cancelOrder(orderId) {
        return this.post(`/api/orders/${orderId}/cancel`);
    }

    async getAccountState() {
        return this.get('/api/account-state');
    }

    // ==========================================
    // METRICS & HISTORY
    // ==========================================

    async getMetrics() {
        return this.get('/api/metrics');
    }

    async getPNLHistory(hours = 24) {
        return this.get('/api/pnl-history', { hours });
    }

    async getTrades(limit = 50) {
        return this.get('/api/trades', { limit });
    }

    // ==========================================
    // VOLUME TRACKING
    // ==========================================

    async getVolumeStats(periods = '1h,24h,7d,14d') {
        return this.get('/api/volume/stats', { periods });
    }

    async getVolumeTimeline(hours = 24, interval = 60) {
        return this.get('/api/volume/timeline', { hours, interval });
    }

    async getVolumeComparison(period = '24h') {
        return this.get('/api/volume/comparison', { period });
    }

    // ==========================================
    // LOGS
    // ==========================================

    async getLogs(lines = 200) {
        return this.get('/api/logs', { lines });
    }

    // ==========================================
    // CONFIGURATION
    // ==========================================

    async getConfig() {
        return this.get('/api/config');
    }

    async updateConfig(config) {
        return this.post('/api/config/update', config);
    }

    async getConfigSchema() {
        return this.get('/api/config/schema');
    }

    async getConfigSchemaV2() {
        return this.get('/api/config/schema/v2');
    }

    async validateConfig(strategy, config) {
        return this.post('/api/config/validate', { strategy, config });
    }

    async previewConfigChanges(config) {
        return this.post('/api/config/preview', { config });
    }

    // ==========================================
    // CREDENTIALS MANAGEMENT
    // ==========================================

    async checkCredentials() {
        return this.get('/api/credentials/check');
    }

    async validateCredentials(walletAddress, privateKey) {
        return this.post('/api/credentials/validate', {
            wallet_address: walletAddress,
            private_key: privateKey
        });
    }

    async saveCredentials(credentials) {
        return this.post('/api/credentials/save', credentials);
    }

    async deleteCredentials() {
        return this.post('/api/credentials/delete', { confirmed: true });
    }

    // ==========================================
    // RISK MANAGEMENT
    // ==========================================

    async getRiskStatus() {
        return this.get('/api/risk/status');
    }

    async getRiskTelemetry() {
        return this.get('/api/risk/telemetry/active');
    }

    async getRiskPositions() {
        return this.get('/api/risk/positions');
    }

    // ==========================================
    // CSV ANALYSIS
    // ==========================================

    async uploadCSV(file) {
        const formData = new FormData();
        formData.append('file', file);

        return this.request('/api/csv/upload', {
            method: 'POST',
            body: formData,
            headers: {} // Let browser set Content-Type for FormData
        });
    }

    async getCSVList() {
        return this.get('/api/csv/list');
    }

    async analyzeCSV(filename) {
        return this.get(`/api/csv/analyze/${encodeURIComponent(filename)}`);
    }

    async deleteCSV(filename) {
        return this.delete(`/api/csv/delete/${encodeURIComponent(filename)}`);
    }

    // ==========================================
    // SYMBOLS MANAGEMENT
    // ==========================================

    async getAvailableSymbols() {
        return this.get('/api/symbols/available');
    }

    async refreshSymbols() {
        return this.post('/api/symbols/refresh');
    }

    async getSymbolsCacheInfo() {
        return this.get('/api/symbols/cache-info');
    }
}

// Create singleton instance
const api = new APIClient();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
}