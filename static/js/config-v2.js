/**
 * ================================================
 * CONFIGURATION V2 MODULE
 * ================================================
 * Handles advanced configuration management
 */

class ConfigurationManager {
    constructor() {
        this.schema = null;
        this.currentStrategy = null;
        this.currentValues = {};
        this.originalValues = {};
        this.availableSymbols = [];
    }

    /**
     * Initialize configuration system
     */
    async init() {
        console.log('🔧 Initializing Configuration V2...');

        try {
            // Try to load V2 schema
            const schemaData = await api.getConfigSchemaV2();
            
            if (schemaData.status === 'success') {
                this.schema = schemaData.schema;
                this.currentValues = schemaData.current_values;
                this.currentStrategy = schemaData.current_strategy;
                
                this.renderConfigInterface();
                console.log('✅ Configuration V2 loaded');
            } else {
                throw new Error('V2 schema not available');
            }
        } catch (error) {
            console.warn('⚠️ V2 schema not available, using fallback');
            await this.initLegacyConfig();
        }
    }

    /**
     * Initialize legacy configuration
     */
    async initLegacyConfig() {
        console.log('📝 Loading legacy configuration...');
        
        try {
            const config = await api.getConfig();
            this.currentValues = config;
            this.originalValues = { ...config };
            
            this.renderLegacyInterface();
        } catch (error) {
            console.error('Error loading configuration:', error);
            dashboard.showAlert('error', 'Erro ao carregar configurações');
        }
    }

    /**
     * Render V2 configuration interface
     */
    renderConfigInterface() {
        const container = document.getElementById('config-fields-container');
        if (!container) return;

        // Implementation would render the hierarchical configuration UI
        // This is a simplified version
        container.innerHTML = `
            <div class="config-section">
                <h3>📝 Configuração de Estratégia</h3>
                <p>Sistema de configuração V2 carregado</p>
                <div id="strategy-selection"></div>
                <div id="config-sections"></div>
            </div>
        `;

        // Render strategy selection
        this.renderStrategySelection();
    }

    /**
     * Render strategy selection
     */
    renderStrategySelection() {
        const container = document.getElementById('strategy-selection');
        if (!container || !this.schema) return;

        const categories = this.schema.strategy_categories;
        
        let html = '<div class="grid grid--3-col">';
        
        for (const [key, category] of Object.entries(categories)) {
            html += `
                <button class="card card--hover" onclick="configManager.selectStrategyCategory('${key}')">
                    <div class="card__body">
                        <div class="text-4xl mb-2">${category.icon}</div>
                        <h4 class="font-semibold">${category.label}</h4>
                        <p class="text-sm text-muted mt-2">${category.description}</p>
                    </div>
                </button>
            `;
        }
        
        html += '</div>';
        container.innerHTML = html;
    }

    /**
     * Select strategy category
     */
    selectStrategyCategory(categoryKey) {
        console.log('Selected category:', categoryKey);
        // Implementation would show strategies in this category
        dashboard.showAlert('info', `Categoria selecionada: ${categoryKey}`);
    }

    /**
     * Render legacy interface
     */
    renderLegacyInterface() {
        const container = document.getElementById('config-fields-container');
        if (!container) return;

        container.innerHTML = `
            <div class="config-section">
                <h3>⚙️ Configurações</h3>
                <p class="text-muted">Sistema de configuração clássico</p>
                <div class="form-group">
                    <label class="form-label">Estratégia</label>
                    <select class="form-select" id="legacy-strategy">
                        <option value="pure_grid">Pure Grid</option>
                        <option value="market_making">Market Making</option>
                        <option value="dynamic_grid">Dynamic Grid</option>
                    </select>
                </div>
                <button onclick="configManager.saveLegacyConfig()" class="btn btn--primary">
                    💾 Salvar Configuração
                </button>
            </div>
        `;
    }

    /**
     * Save legacy configuration
     */
    async saveLegacyConfig() {
        try {
            dashboard.showAlert('info', '⏳ Salvando configuração...');
            
            const strategy = document.getElementById('legacy-strategy')?.value;
            const config = {
                STRATEGY_TYPE: strategy,
                ...this.currentValues
            };

            const result = await api.updateConfig(config);
            
            if (result.status === 'success') {
                dashboard.showAlert('success', '✅ Configuração salva!');
            } else {
                dashboard.showAlert('error', result.message);
            }
        } catch (error) {
            console.error('Error saving config:', error);
            dashboard.showAlert('error', 'Erro ao salvar configuração');
        }
    }

    /**
     * Load available symbols
     */
    async loadSymbols() {
        try {
            const result = await api.getAvailableSymbols();
            
            if (result.status === 'success') {
                this.availableSymbols = result.symbols;
                return this.availableSymbols;
            }
        } catch (error) {
            console.error('Error loading symbols:', error);
        }
        return [];
    }

    /**
     * Refresh symbols cache
     */
    async refreshSymbols() {
        try {
            dashboard.showAlert('info', '🔄 Atualizando símbolos...');
            
            const result = await api.refreshSymbols();
            
            if (result.status === 'success') {
                this.availableSymbols = result.symbols;
                dashboard.showAlert('success', result.message);
            } else {
                dashboard.showAlert('error', result.message);
            }
        } catch (error) {
            console.error('Error refreshing symbols:', error);
            dashboard.showAlert('error', 'Erro ao atualizar símbolos');
        }
    }
}

// Create singleton instance
const configManager = new ConfigurationManager();

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = configManager;
}