/**
 * ================================================
 * CONFIGURATION & CONSTANTS
 * ================================================
 * Centralized configuration file for the dashboard
 */

const CONFIG = {
    // API Configuration
    API: {
        BASE_URL: window.location.origin,
        TIMEOUT: 30000, // 30 seconds
        RETRY_ATTEMPTS: 3,
        RETRY_DELAY: 1000 // 1 second
    },

    // WebSocket Configuration
    WEBSOCKET: {
        TRANSPORTS: ['polling'],
        UPGRADE: false,
        REMEMBER_UPGRADE: false,
        TIMEOUT: 20000,
        FORCE_NEW: true
    },

    // Update Intervals (in milliseconds)
    INTERVALS: {
        POSITIONS_UPDATE: 5000,      // 5 seconds
        LOGS_UPDATE: 3000,           // 3 seconds
        RISK_DASHBOARD: 3000,        // 3 seconds
        VOLUME_UPDATE: 30000,        // 30 seconds
        AUTO_REFRESH: 30000          // 30 seconds
    },

    // UI Configuration
    UI: {
        TOAST_DURATION: 5000,        // 5 seconds
        MODAL_ANIMATION: 300,         // 300ms
        CHART_ANIMATION: 400,         // 400ms
        MAX_LOG_LINES: 200,
        MAX_TRADES_PER_PAGE: 50
    },

    // Feature Flags
    FEATURES: {
        WEBSOCKET_ENABLED: true,
        AUTO_REFRESH_ENABLED: true,
        RISK_MANAGEMENT: true,
        CSV_ANALYSIS: true,
        CONFIG_V2: true
    },

    // Chart Colors
    CHARTS: {
        COLORS: {
            PRIMARY: 'rgb(59, 130, 246)',
            SUCCESS: 'rgb(16, 185, 129)',
            DANGER: 'rgb(239, 68, 68)',
            WARNING: 'rgb(245, 158, 11)',
            INFO: 'rgb(59, 130, 246)'
        },
        OPACITY: {
            FILL: 0.1,
            BORDER: 0.8
        }
    },

    // Local Storage Keys
    STORAGE: {
        USER_PREFERENCES: 'pacifica_user_prefs',
        LAST_TAB: 'pacifica_last_tab',
        CREDENTIALS: 'pacifica_credentials_configured'
    }
};

// Freeze configuration to prevent modifications
Object.freeze(CONFIG);

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}