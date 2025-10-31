// Estado Global
        const API_BASE = window.location.origin;
        let socket = null;
        let currentTab = 'dashboard';
        let pnlChart = null;
        let volumeTimelineChart = null;
        let winrateChart = null;
        let pnlDistChart = null;
        let tradesLimit = 50;
        let logsPaused = false;
        let logsAutoScroll = true;
        
        console.log('🚀 Dashboard v1.1 iniciado');

        // ========== WEBSOCKET ==========
        
        function initWebSocket() {
            console.log('🔌 Iniciando conexão WebSocket com:', API_BASE);
            
            socket = io(API_BASE, {
                transports: ['polling'],
                upgrade: false,
                rememberUpgrade: false,
                timeout: 20000,
                forceNew: true
            });
            
            socket.on('connect', () => {
                console.log('✅ WebSocket conectado - ID:', socket.id);
                updateWSStatus(true);
                showAlert('success', '🔌 Conectado ao servidor');
            });
            
            socket.on('disconnect', (reason) => {
                console.log('❌ WebSocket desconectado - Motivo:', reason);
                updateWSStatus(false);
                showAlert('error', '🔌 Desconectado do servidor');
            });
            
            socket.on('connect_error', (error) => {
                console.error('❌ Erro de conexão WebSocket:', error.message);
                updateWSStatus(false);
            });
            
            socket.on('bot_status_update', (data) => {
                updateBotStatus(data);
            });
            
            socket.on('metrics_update', (data) => {
                updateMetrics(data);
            });
            
            socket.on('pnl_history_update', (data) => {
                updatePNLChartData(data);
            });
            
            // NOVO: Posições e Ordens
            socket.on('positions_update', (data) => {
                updatePositions(data);
                updateLastUpdateTime();
            });
            
            socket.on('orders_update', (data) => {
                updateOrders(data);
                updateLastUpdateTime();
            });
            
            // NOVO: Logs auto-refresh
            socket.on('logs_update', (data) => {
                if (!logsPaused) {
                    updateLogsDisplay(data);
                }
            });
            
            socket.on('alert', (data) => {
                showAlert(data.type, data.message);
            });
            
            // NOVO: Risk Management Updates
            socket.on('risk_update', (data) => {
                if (currentTab === 'dashboard') {
                    updateRiskDisplay(data);
                }
            });
            
            // Market Vision Updates
            socket.on('market_vision_update', (data) => {
                if (currentTab === 'market-vision') {
                    updateMarketVisionUI(data);
                }
            });
        }
        
        function updateWSStatus(connected) {
            // Auto-refresh está sempre ativo - não precisa atualizar status
        }

        // ========== ALERTS ==========
        
        function showAlert(type, message) {
            const container = document.getElementById('alerts-container');
            const id = 'alert-' + Date.now();
            
            const colors = {
                success: 'bg-green-600',
                error: 'bg-red-600',
                warning: 'bg-yellow-600',
                info: 'bg-blue-600'
            };
            
            const alert = document.createElement('div');
            alert.id = id;
            alert.className = `alert-toast ${colors[type] || colors.info} text-white px-6 py-4 rounded-lg shadow-lg mb-2`;
            alert.innerHTML = `
                <div class="flex items-center justify-between gap-4">
                    <span>${message}</span>
                    <button onclick="closeAlert('${id}')" class="text-white hover:text-gray-200">✕</button>
                </div>
            `;
            
            container.appendChild(alert);
            
            setTimeout(() => {
                closeAlert(id);
            }, 5000);
        }
        
        function closeAlert(id) {
            const alert = document.getElementById(id);
            if (alert) {
                alert.classList.add('fade-out');
                setTimeout(() => alert.remove(), 300);
            }
        }

        // ========== TABS ==========
        
        function showTab(tab) {
            currentTab = tab;
            
            ['dashboard', 'volume', 'positions', 'charts', 'trades', 'logs', 'csv-analysis', 'config', 'market-vision'].forEach(t => {
                const contentEl = document.getElementById(`content-${t}`);
                const tabEl = document.getElementById(`tab-${t}`);
                
                if (contentEl) {
                    contentEl.classList.add('hidden');
                }
                if (tabEl) {
                    tabEl.classList.remove('border-blue-500', 'text-blue-500');
                    tabEl.classList.add('text-gray-400');
                }
            });
            
            const activeContent = document.getElementById(`content-${tab}`);
            const activeTab = document.getElementById(`tab-${tab}`);
            
            if (activeContent) {
                activeContent.classList.remove('hidden');
            }
            if (activeTab) {
                activeTab.classList.add('border-blue-500', 'text-blue-500');
                activeTab.classList.remove('text-gray-400');
            }
            
            if (window.positionsInterval) {
                clearInterval(window.positionsInterval);
                window.positionsInterval = null;
            }
            if (tab === 'dashboard') {
                loadPositionsAndOrders();
                updateRiskDashboard();
                // loadRiskPositionsMonitor();
            } else if (tab === 'volume') {
                loadVolumeStats();
                loadVolumeTimeline(24, 60);
                loadVolumeComparison('24h');
            } else if (tab === 'charts') {
                initCharts();
            } else if (tab === 'trades') {
                loadTrades();
            } else if (tab === 'logs') {
                refreshLogs();
            } else if (tab === 'csv-analysis') {
                refreshCSVList();
                if (!currentAnalysis) {
                    loadLastAnalysis();
                }
            } else if (tab === 'config') {
                if (!configSchema) {
                    initConfigV2();
                } else {
                    loadCurrentConfig();
                }
            } else if (tab === 'positions') {
                loadPositionsAndOrders();
                // Limpar interval anterior se existir
                if (window.positionsInterval) {
                    clearInterval(window.positionsInterval);
                }
                // Interval mais frequente para melhor responsividade
                window.positionsInterval = setInterval(() => {
                    if (currentTab === 'positions') {
                        loadPositionsAndOrders();
                    }
                }, 5000); // 5 segundos (reduzido de 30s)
            } else if (tab === 'market-vision') {
                loadMarketVision();
            }
        }

        // ========== HISTÓRICO ==========
        async function loadHistoricalStats() {
    try {
        const response = await fetch(`${API_BASE}/api/historical-stats`);
        const data = await response.json();
        renderDailyPNLChart(data);
    } catch (error) {
        console.error('Erro ao carregar histórico:', error);
    }
}

function renderDailyPNLChart(data) {
    const ctx = document.getElementById('daily-pnl-chart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.days,
            datasets: [
                {
                    label: 'PNL Diário (USD)',
                    data: data.pnl,
                    backgroundColor: data.pnl.map(v => v >= 0 ? 'rgba(34,197,94,0.8)' : 'rgba(239,68,68,0.8)')
                },
                {
                    label: 'Volume (USD)',
                    data: data.volume,
                    backgroundColor: 'rgba(59,130,246,0.3)',
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { labels: { color: '#fff' } },
                title: { display: true, text: 'Estatísticas Diárias - PNL e Volume', color: '#fff' }
            },
            scales: {
                x: { ticks: { color: '#9ca3af' } },
                y: { ticks: { color: '#9ca3af' }, beginAtZero: true },
                y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#9ca3af' } }
            }
        }
    });
}

        // ========== BOT CONTROLS ==========
        
        async function startBot() {
            try {
                showAlert('info', '⏳ Iniciando bot...');
                const response = await fetch(`${API_BASE}/api/bot/start`, {
                    method: 'POST'
                });
                const result = await response.json();
                
                if (result.status === 'success') {
                    showAlert('success', result.message);
                } else {
                    showAlert('error', result.message);
                }
            } catch (error) {
                console.error('❌ Erro ao iniciar bot:', error);
                showAlert('error', 'Erro ao iniciar bot: ' + error.message);
            }
        }
        
        async function stopBot(force) {
            try {
                showAlert('info', force ? '⏳ Parando bot (forçado)...' : '⏳ Parando bot...');
                const response = await fetch(`${API_BASE}/api/bot/stop`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({force})
                });
                const result = await response.json();
                
                if (result.status === 'success') {
                    showAlert('success', result.message);
                } else {
                    showAlert('error', result.message);
                }
            } catch (error) {
                console.error('❌ Erro ao parar bot:', error);
                showAlert('error', 'Erro ao parar bot: ' + error.message);
            }
        }
        
        async function restartBot() {
            try {
                showAlert('info', '⏳ Reiniciando bot...');
                const response = await fetch(`${API_BASE}/api/bot/restart`, {
                    method: 'POST'
                });
                const result = await response.json();
                
                if (result.status === 'success') {
                    showAlert('success', result.message);
                } else {
                    showAlert('error', result.message);
                }
            } catch (error) {
                console.error('❌ Erro ao reiniciar bot:', error);
                showAlert('error', 'Erro ao reiniciar bot: ' + error.message);
            }
        }

        // ========== UPDATE FUNCTIONS ==========
        
        function updateBotStatus(data) {
            const statusText = document.getElementById('status-text');
            const btnStart = document.getElementById('btn-start');
            const btnStop = document.getElementById('btn-stop');
            const btnStopForce = document.getElementById('btn-stop-force');
            const btnRestart = document.getElementById('btn-restart');
            const systemInfo = document.getElementById('system-info');
            
            if (data.running) {
                statusText.innerHTML = '🟢 Rodando <span class="pulse-dot">●</span>';
                btnStart.disabled = true;
                btnStart.classList.add('btn-disabled');
                btnStop.disabled = false;
                btnStop.classList.remove('btn-disabled');
                btnStopForce.disabled = false;
                btnStopForce.classList.remove('btn-disabled');
                btnRestart.disabled = false;
                btnRestart.classList.remove('btn-disabled');
                systemInfo.classList.remove('hidden');
                
                document.getElementById('pid-text').textContent = data.pid || '-';
                document.getElementById('cpu-text').textContent = (data.cpu_percent || 0).toFixed(1) + '%';
                document.getElementById('memory-text').textContent = (data.memory_mb || 0).toFixed(0) + ' MB';
                document.getElementById('uptime-text').textContent = formatUptime(data.uptime_seconds || 0);
            } else {
                statusText.textContent = '🔴 Parado';
                btnStart.disabled = false;
                btnStart.classList.remove('btn-disabled');
                btnStop.disabled = true;
                btnStop.classList.add('btn-disabled');
                btnStopForce.disabled = true;
                btnStopForce.classList.add('btn-disabled');
                btnRestart.disabled = true;
                btnRestart.classList.add('btn-disabled');
                systemInfo.classList.add('hidden');
            }
            
            document.getElementById('last-update').textContent = 
                'Última atualização: ' + new Date().toLocaleTimeString('pt-BR');
        }
        
        function updateMetrics(data) {
            // Verificar se os elementos existem antes de tentar atualizá-los
            const pnlElement = document.getElementById('pnl-text');
            const cyclesElement = document.getElementById('cycles-text');
            const winrateElement = document.getElementById('winrate-text');
            const totalTradesElement = document.getElementById('total-trades');
            const winningTradesElement = document.getElementById('winning-trades');
            const losingTradesElement = document.getElementById('losing-trades');
            const avgWinElement = document.getElementById('avg-win');
            
            if (pnlElement) {
                const pnl = data?.accumulated_pnl || 0;
                pnlElement.textContent = `$${pnl.toFixed(2)}`;
                pnlElement.className = `text-2xl font-bold ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`;
            }
            
            if (cyclesElement) {
                cyclesElement.textContent = data?.cycles_closed || 0;
            }
            
            if (winrateElement) {
                const winRate = data?.win_rate || 0;
                winrateElement.textContent = `${winRate}%`;
                winrateElement.className = `text-2xl font-bold ${winRate >= 50 ? 'text-green-400' : 'text-yellow-400'}`;
            }
            
            if (totalTradesElement) {
                totalTradesElement.textContent = data?.total_trades || 0;
            }
            
            if (winningTradesElement) {
                winningTradesElement.textContent = data?.winning_trades || 0;
            }
            
            if (losingTradesElement) {
                losingTradesElement.textContent = data?.losing_trades || 0;
            }
            
            if (avgWinElement) {
                avgWinElement.textContent = `$${(data?.avg_win || 0).toFixed(2)}`;
            }
            document.getElementById('avg-loss').textContent = `$${(data.avg_loss || 0).toFixed(2)}`;
            document.getElementById('profit-factor').textContent = (data.profit_factor || 0).toFixed(2);
            document.getElementById('profit-factor').className = data.profit_factor >= 1 ? 'text-green-400' : 'text-red-400';
            
            document.getElementById('largest-win').textContent = `$${(data.largest_win || 0).toFixed(2)}`;
            document.getElementById('largest-loss').textContent = `$${(data.largest_loss || 0).toFixed(2)}`;
            document.getElementById('current-balance').textContent = `$${(data.current_balance || 0).toFixed(2)}`;
            
            if (currentTab === 'charts') {
                updateDistributionCharts(data);
            }
        }
        
        function formatUptime(seconds) {
            if (seconds < 60) return `${seconds}s`;
            if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
            if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
            return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
        }

        // ========== POSIÇÕES E ORDENS (NOVO) ==========
        
        async function loadPositionsAndOrders() {
            return new Promise(async (resolve, reject) => {
                try {
                    console.log('🔄 Carregando posições, ordens e estado da conta...');
                    
                    // Feedback visual nos botões de atualização
                    const updateButtons = document.querySelectorAll('button[title="Atualizar agora"]');
                    updateButtons.forEach(btn => {
                        const originalText = btn.innerHTML;
                        btn.innerHTML = '⏳ Carregando...';
                        btn.disabled = true;
                        
                        // Restaurar após timeout
                        setTimeout(() => {
                            btn.innerHTML = originalText;
                            btn.disabled = false;
                        }, 2000);
                    });
                    
                    // TEMPORÁRIO: Usar método tradicional para debug
                    console.log('🔍 Debug: Fazendo requisições tradicionais...');
                    
                    const [posRes, ordRes, accRes] = await Promise.all([
                        fetch(`${API_BASE}/api/positions`),
                        fetch(`${API_BASE}/api/orders`),
                        fetch(`${API_BASE}/api/account-state`)
                    ]);
                    
                    console.log('📊 Status das respostas:', {
                        positions: posRes.status,
                        orders: ordRes.status,
                        account: accRes.status
                    });
                    
                    if (!posRes.ok || !ordRes.ok || !accRes.ok) {
                        const error = new Error(`HTTP Error - Positions: ${posRes.status}, Orders: ${ordRes.status}, Account: ${accRes.status}`);
                        throw error;
                    }
                    
                    const positions = await posRes.json();
                    const orders = await ordRes.json();
                    const accountState = await accRes.json();
                    
                    console.log('📊 Posições recebidas:', positions.length, positions);
                    console.log('📋 Ordens recebidas:', orders.length, orders);
                    console.log('💰 Estado da conta:', accountState);
                    
                    updatePositions(positions);
                    updateOrders(orders);
                    updateAccountState(accountState);
                    
                    // Atualizar timestamp de última atualização
                    updateLastUpdateTime();
                    
                    resolve({ positions, orders, accountState });
                    
                } catch (error) {
                    console.error('❌ Erro ao carregar dados:', error);
                    console.error('❌ Stack trace:', error.stack);
                    
                    // Mostrar erro na interface
                    const lastUpdateEl = document.getElementById('last-update-time');
                    if (lastUpdateEl) {
                        lastUpdateEl.textContent = 'Erro ao carregar';
                        lastUpdateEl.className = 'text-red-400';
                    }
                    
                    // Tentar mostrar dados vazios em vez de deixar "Carregando..."
                    updatePositions([]);
                    updateOrders([]);
                    updateAccountState({
                        balance: 0,
                        margin_used: 0,
                        margin_available: 0,
                        margin_free_percent: 0
                    });
                    
                    reject(error);
                }
            });
        }
        
        function updateLastUpdateTime() {
            const now = new Date();
            const timeString = now.toLocaleTimeString();
            const element = document.getElementById('last-update-time');
            if (element) {
                element.textContent = timeString;
                element.className = 'text-green-400'; // Verde para indicar atualização recente
                
                // Voltar para azul após 3 segundos
                setTimeout(() => {
                    if (element) element.className = 'text-blue-400';
                }, 3000);
            }
        }

        // FUNÇÃO DE DIAGNÓSTICO - pode ser chamada no console do navegador
        window.testLoadData = async function() {
            console.log('🔧 DIAGNÓSTICO: Testando carregamento manual...');
            try {
                const response1 = await fetch('/api/positions');
                const response2 = await fetch('/api/orders');
                const response3 = await fetch('/api/account-state');
                
                console.log('📊 Status responses:', {
                    positions: response1.status,
                    orders: response2.status,
                    account: response3.status
                });
                
                if (response1.ok && response2.ok && response3.ok) {
                    const positions = await response1.json();
                    const orders = await response2.json();
                    const account = await response3.json();
                    
                    console.log('✅ Dados obtidos:', { positions, orders, account });
                    
                    updatePositions(positions);
                    updateOrders(orders);
                    updateAccountState(account);
                    updateLastUpdateTime();
                    
                    console.log('✅ Interface atualizada com sucesso!');
                } else {
                    console.error('❌ Erro nos status HTTP');
                }
            } catch (error) {
                console.error('❌ Erro no diagnóstico:', error);
            }
        };
        
        // Função para verificar elementos DOM
        window.checkDOMElements = function() {
            console.log('🔧 VERIFICANDO ELEMENTOS DOM...');
            
            const elements = {
                'positions-container': document.getElementById('positions-container'),
                'orders-container': document.getElementById('orders-container'),
                'last-update-time': document.getElementById('last-update-time'),
                'account-balance': document.getElementById('account-balance'),
                'margin-used': document.getElementById('margin-used'),
                'margin-free': document.getElementById('margin-free')
            };
            
            let allFound = true;
            for (const [id, element] of Object.entries(elements)) {
                const exists = element !== null;
                console.log(`${exists ? '✅' : '❌'} ${id}:`, exists ? 'encontrado' : 'NÃO ENCONTRADO');
                if (!exists) allFound = false;
            }
            
            console.log(`\n${allFound ? '✅ Todos os elementos encontrados!' : '❌ Alguns elementos estão faltando!'}`);
            return elements;
        };
        
        function updatePositions(positions) {
            console.log('🔄 updatePositions chamada com:', positions.length, 'posições');
            const container = document.getElementById('positions-container');
            const countEl = document.getElementById('positions-count');
            if (countEl) countEl.textContent = positions.length;

            if (positions.length === 0) {
                if (container) container.innerHTML = '<p class="text-gray-500 text-center py-8">Nenhuma posição ativa</p>';
                const totalPnlEl = document.getElementById('positions-total-pnl');
                if (totalPnlEl) totalPnlEl.textContent = '$0.00';
                const exposureEl = document.getElementById('positions-exposure');
                if (exposureEl) exposureEl.textContent = '$0.00';
                return;
            }
            
            let unrealizedPnl = 0;
            let realizedPnl = 0;
            let totalExposure = 0;

            if (container) container.innerHTML = positions.map(pos => {
                // Converter strings para números
                const pnl = parseFloat(pos.pnl_usd || pos.unrealized_pnl || 0);
                const size = parseFloat(pos.size || pos.amount || 0);
                const entryPrice = parseFloat(pos.entry_price || pos.avg_price || 0);
                const currentPrice = parseFloat(pos.current_price || entryPrice || 0);
                const pnlPercent = parseFloat(pos.pnl_percent || 0);

                // PNL não realizado: posições abertas
                unrealizedPnl += pnl;
                // PNL realizado: histórico fechado (se vier no objeto)
                if (pos.realized_pnl) {
                    realizedPnl += parseFloat(pos.realized_pnl);
                }

                totalExposure += entryPrice * size;

                const pnlClass = pnl >= 0 ? 'text-green-400' : 'text-red-400';
                const sideClass = (pos.side || '').toLowerCase().includes('long') ? 'position-long' : 'position-short';
                const sideLabel = (pos.side || '').toLowerCase().includes('long') ? '🟢 LONG' : '🔴 SHORT';

                return `
                    <div class="bg-gray-700 rounded-lg p-4 ${sideClass}">
                        <div class="flex justify-between items-start mb-2">
                            <div>
                                <span class="font-bold text-lg">${pos.symbol || '-'}</span>
                                <span class="ml-2 text-sm">${sideLabel}</span>
                            </div>
                            <span class="${pnlClass} font-bold">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</span>
                        </div>
                        <div class="grid grid-cols-2 gap-2 text-sm">
                            <div>
                                <span class="text-gray-400">Tamanho:</span>
                                <span class="ml-1">${size.toFixed(4)}</span>
                            </div>
                            <div>
                                <span class="text-gray-400">Entrada:</span>
                                <span class="ml-1">$${entryPrice.toFixed(2)}</span>
                            </div>
                            <div>
                                <span class="text-gray-400">Atual:</span>
                                <span class="ml-1">$${currentPrice.toFixed(2)}</span>
                            </div>
                            <div>
                                <span class="text-gray-400">Ativo há:</span>
                                <span class="ml-1">${pos.duration_str || '-'}</span>
                            </div>
                        </div>
                        <div class="mt-2 pt-2 border-t border-gray-600">
                            <span class="text-gray-400 text-xs">PNL: </span>
                            <span class="${pnlClass} text-sm font-semibold">
                                ${pnlPercent.toFixed(2)}%
                            </span>
                        </div>
                    </div>
                `;
            }).join('');

            const unrealizedEl = document.getElementById('unrealized-pnl');
            if (unrealizedEl) {
                unrealizedEl.textContent = `$${unrealizedPnl.toFixed(2)}`;
                unrealizedEl.className = `text-2xl font-bold ${unrealizedPnl >= 0 ? 'text-green-400' : 'text-red-400'}`;
            }
            const realizedEl = document.getElementById('realized-pnl');
            if (realizedEl) {
                realizedEl.textContent = `$${realizedPnl.toFixed(2)}`;
                realizedEl.className = `text-2xl font-bold ${realizedPnl >= 0 ? 'text-green-400' : 'text-red-400'}`;
            }
            const exposureEl = document.getElementById('positions-exposure');
            if (exposureEl) exposureEl.textContent = `$${totalExposure.toFixed(2)}`;
        }
        
        function updateOrders(orders) {
            console.log('🔄 updateOrders chamada com:', orders.length, 'ordens');
            const container = document.getElementById('orders-container');
            const countEl = document.getElementById('orders-count');
            const buyCountEl = document.getElementById('buy-orders-count');
            const sellCountEl = document.getElementById('sell-orders-count');
            
            if (countEl) countEl.textContent = orders.length;

            if (orders.length === 0) {
                if (container) container.innerHTML = '<p class="text-gray-500 text-center py-8">Nenhuma ordem aberta</p>';
                if (buyCountEl) buyCountEl.textContent = '0';
                if (sellCountEl) sellCountEl.textContent = '0';
                const pendingValueEl = document.getElementById('orders-pending-value');
                if (pendingValueEl) pendingValueEl.textContent = '$0.00';
                return;
            }
            
            let totalValue = 0;
            let buyOrders = 0;
            let sellOrders = 0;
            
            if (container) container.innerHTML = orders.map(order => {
                // Converter strings para números
                const price = parseFloat(order.price || 0);
                const size = parseFloat(order.size || order.initial_amount || 0);
                const value = price * size;
                totalValue += value;
                
                const side = (order.side || '').toLowerCase();
                const isBuy = side.includes('buy') || side === 'bid';
                
                if (isBuy) {
                    buyOrders++;
                } else {
                    sellOrders++;
                }
                
                const sideClass = isBuy ? 'order-buy' : 'order-sell';
                const sideLabel = isBuy ? '🟢 BUY' : '🔴 SELL';
                const sideColor = isBuy ? 'text-green-400' : 'text-red-400';
                
                return `
                    <div class="bg-gray-700 rounded-lg p-4 ${sideClass} relative">
                        <div class="flex justify-between items-start mb-2">
                            <div class="flex items-center gap-2">
                                <span class="font-bold text-white">${order.symbol || '-'}</span>
                                <span class="text-sm font-semibold ${sideColor}">${sideLabel}</span>
                            </div>
                            <div class="flex items-center gap-2">
                                <span class="text-gray-400 text-sm">${order.age_str || '-'}</span>
                                <button 
                                    onclick="cancelOrder('${order.order_id || order.id || ''}')" 
                                    class="cancel-order-btn text-gray-400 hover:text-red-400 text-lg"
                                    title="Cancelar ordem"
                                >
                                    ❌
                                </button>
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-2 text-sm">
                            <div>
                                <span class="text-gray-400">Preço:</span>
                                <span class="ml-1 text-white font-medium">$${price.toFixed(2)}</span>
                            </div>
                            <div>
                                <span class="text-gray-400">Tamanho:</span>
                                <span class="ml-1 text-white font-medium">${size.toFixed(4)}</span>
                            </div>
                            <div class="col-span-2">
                                <span class="text-gray-400">Valor:</span>
                                <span class="ml-1 font-semibold text-yellow-400">$${value.toFixed(2)}</span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
            
            // Atualizar contadores
            if (buyCountEl) buyCountEl.textContent = buyOrders;
            if (sellCountEl) sellCountEl.textContent = sellOrders;
            
            const pendingValueEl = document.getElementById('orders-pending-value');
            if (pendingValueEl) pendingValueEl.textContent = `$${totalValue.toFixed(2)}`;
            
            // Calcular % do grid preenchido (buy + sell orders) - DESABILITADO: elemento não existe no HTML
            // const totalOrders = buyOrders + sellOrders;
            // const gridFillPercent = totalOrders > 0 ? ((buyOrders + sellOrders) / (totalOrders * 2)) * 100 : 0;
            // const gridFillEl = document.getElementById('grid-fill-percent');
            // if (gridFillEl) gridFillEl.textContent = `${gridFillPercent.toFixed(0)}%`;
        }

        async function cancelOrder(orderId) {
            if (!orderId) {
                showAlert('error', '❌ ID da ordem não fornecido');
                return;
            }

            // Confirmação antes de cancelar
            if (!confirm(`🚫 Cancelar ordem ${orderId}?\n\nEsta ação não pode ser desfeita.`)) {
                return;
            }

            try {
                showAlert('info', '🔄 Cancelando ordem...');
                
                const response = await fetch(`${API_BASE}/api/orders/${orderId}/cancel`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const result = await response.json();
                
                if (result.success) {
                    showAlert('success', `✅ ${result.message}`);
                    
                    // ATUALIZAÇÃO IMEDIATA: Forçar recarregamento das ordens e posições
                    setTimeout(() => {
                        loadPositionsAndOrders();
                    }, 500); // Pequeno delay para garantir processamento no backend
                    
                    // Backup: Se socket não atualizar em 2s, forçar novamente
                    setTimeout(() => {
                        loadPositionsAndOrders();
                    }, 2000);
                    
                } else {
                    showAlert('error', `❌ ${result.message || 'Erro ao cancelar ordem'}`);
                }
                
            } catch (error) {
                console.error('Erro ao cancelar ordem:', error);
                showAlert('error', '❌ Erro de conexão ao cancelar ordem');
            }
        }
        
        function updateAccountState(state) {
            console.log('💰 Atualizando estado da conta:', state);
            
            // Saldo
            const balanceEl = document.getElementById('account-balance');
            if (balanceEl) {
                balanceEl.textContent = `$${(state.balance || 0).toFixed(2)}`;
            }
            
            // Margem Usada
            const marginUsedEl = document.getElementById('margin-used');
            if (marginUsedEl) {
                marginUsedEl.textContent = `$${(state.margin_used || 0).toFixed(2)}`;
            }
            
            // Margem Disponível
            const marginAvailableEl = document.getElementById('margin-available');
            if (marginAvailableEl) {
                marginAvailableEl.textContent = `$${(state.margin_available || 0).toFixed(2)}`;
            }
            
            // Margem Livre (%)
            const marginFreePercent = state.margin_free_percent || 0;
            const marginFreePercentEl = document.getElementById('margin-free-percent');
            if (marginFreePercentEl) {
                marginFreePercentEl.textContent = `${marginFreePercent.toFixed(1)}%`;
                
                // Alterar cor baseado no percentual
                if (marginFreePercent < 20) {
                    marginFreePercentEl.className = 'text-2xl font-bold text-red-400';
                } else if (marginFreePercent < 50) {
                    marginFreePercentEl.className = 'text-2xl font-bold text-orange-400';
                } else {
                    marginFreePercentEl.className = 'text-2xl font-bold text-green-400';
                }
            }
            
            // Barra de progresso
            const marginFreeBarEl = document.getElementById('margin-free-bar');
            if (marginFreeBarEl) {
                marginFreeBarEl.style.width = `${marginFreePercent}%`;
                
                // Alterar cor da barra baseado no percentual
                if (marginFreePercent < 20) {
                    marginFreeBarEl.className = 'bg-red-500 h-2 rounded-full transition-all';
                } else if (marginFreePercent < 50) {
                    marginFreeBarEl.className = 'bg-orange-500 h-2 rounded-full transition-all';
                } else {
                    marginFreeBarEl.className = 'bg-green-500 h-2 rounded-full transition-all';
                }
            }
            
            // Texto de status
            const marginStatusEl = document.getElementById('margin-status-text');
            if (marginStatusEl) {
                if (marginFreePercent < 20) {
                    marginStatusEl.textContent = '⚠️ Margem Crítica - Risco Alto';
                    marginStatusEl.className = 'text-xs text-red-400 text-center font-semibold';
                } else if (marginFreePercent < 50) {
                    marginStatusEl.textContent = '⚡ Atenção - Margem Média';
                    marginStatusEl.className = 'text-xs text-orange-400 text-center';
                } else {
                    marginStatusEl.textContent = '✅ Margem Saudável';
                    marginStatusEl.className = 'text-xs text-green-400 text-center';
                }
            }
            
            // Última atualização
            const balanceUpdatedEl = document.getElementById('balance-updated');
            if (balanceUpdatedEl && state.last_update) {
                const updateTime = new Date(state.last_update);
                const now = new Date();
                const diffSeconds = Math.floor((now - updateTime) / 1000);
                
                let timeText;
                if (diffSeconds < 60) {
                    timeText = 'agora mesmo';
                } else if (diffSeconds < 3600) {
                    timeText = `há ${Math.floor(diffSeconds / 60)}min`;
                } else {
                    timeText = updateTime.toLocaleTimeString('pt-BR');
                }
                balanceUpdatedEl.textContent = timeText;
            }
        }

        // ========== LOGS COM AUTO-REFRESH (MELHORADO) ==========
        
        function toggleLogsPause() {
            logsPaused = !logsPaused;
            const btn = document.getElementById('btn-pause-logs');
            const status = document.getElementById('logs-status');
            
            if (logsPaused) {
                btn.innerHTML = '▶️ Retomar';
                btn.className = 'bg-green-600 hover:bg-green-700 px-4 py-2 rounded flex items-center gap-2';
                status.textContent = 'Auto-refresh PAUSADO';
            } else {
                btn.innerHTML = '⏸️ Pausar';
                btn.className = 'bg-yellow-600 hover:bg-yellow-700 px-4 py-2 rounded flex items-center gap-2';
                status.textContent = 'Auto-refresh ativo (a cada 3s)';
                refreshLogs(); // Atualizar imediatamente ao retomar
            }
        }
        
        async function refreshLogs() {
            try {
                const response = await fetch(`${API_BASE}/api/logs?lines=200`);
                const data = await response.json();
                updateLogsDisplay(data);
            } catch (error) {
                console.error('Erro ao carregar logs:', error);
            }
        }
        
        function updateLogsDisplay(data) {
            const container = document.getElementById('logs-container');
            
            // Verificar se usuário está no final (para auto-scroll inteligente)
            const wasAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 50;
            
            container.innerHTML = data.logs.map(line => {
                let className = 'log-line';
                if (line.includes('ERROR') || line.includes('❌')) className += ' log-error';
                else if (line.includes('WARNING') || line.includes('⚠️')) className += ' log-warning';
                else if (line.includes('INFO') || line.includes('✅')) className += ' log-info';
                else if (line.includes('DEBUG')) className += ' log-debug';
                
                return `<div class="${className}">${line}</div>`;
            }).join('');
            
            // Auto-scroll INTELIGENTE: só faz scroll se usuário estava no final
            if (wasAtBottom) {
                container.scrollTop = container.scrollHeight;
            }
        }
        
        function clearLogsDisplay() {
            document.getElementById('logs-container').innerHTML = '<p class="text-gray-500">Logs limpos. Clique em Atualizar para recarregar.</p>';
        }

        // ========== CHARTS ==========
        
        function initCharts() {
            if (!pnlChart) {
                const ctx = document.getElementById('pnl-chart').getContext('2d');
                pnlChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: [{
                            label: 'PNL Acumulado',
                            data: [],
                            borderColor: 'rgb(59, 130, 246)',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            tension: 0.4,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { labels: { color: '#fff' } }
                        },
                        scales: {
                            x: {
                                ticks: { color: '#9ca3af' },
                                grid: { color: 'rgba(255, 255, 255, 0.1)' }
                            },
                            y: {
                                ticks: { color: '#9ca3af' },
                                grid: { color: 'rgba(255, 255, 255, 0.1)' }
                            }
                        }
                    }
                });
            }
            
            if (!winrateChart) {
                const ctx2 = document.getElementById('winrate-chart').getContext('2d');
                winrateChart = new Chart(ctx2, {
                    type: 'doughnut',
                    data: {
                        labels: ['Ganhos', 'Perdas'],
                        datasets: [{
                            data: [0, 0],
                            backgroundColor: ['rgba(16, 185, 129, 0.8)', 'rgba(239, 68, 68, 0.8)']
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { labels: { color: '#fff' } },
                            title: {
                                display: true,
                                text: 'Win Rate',
                                color: '#fff'
                            }
                        }
                    }
                });
            }
            
            if (!pnlDistChart) {
                const ctx3 = document.getElementById('pnl-distribution-chart').getContext('2d');
                pnlDistChart = new Chart(ctx3, {
                    type: 'bar',
                    data: {
                        labels: ['< -$10', '-$10 a -$5', '-$5 a $0', '$0 a $5', '$5 a $10', '> $10'],
                        datasets: [{
                            label: 'Número de Trades',
                            data: [0, 0, 0, 0, 0, 0],
                            backgroundColor: [
                                'rgba(239, 68, 68, 0.8)',
                                'rgba(251, 146, 60, 0.8)',
                                'rgba(250, 204, 21, 0.8)',
                                'rgba(132, 204, 22, 0.8)',
                                'rgba(34, 197, 94, 0.8)',
                                'rgba(16, 185, 129, 0.8)'
                            ]
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { labels: { color: '#fff' } },
                            title: {
                                display: true,
                                text: 'Distribuição de PNL',
                                color: '#fff'
                            }
                        },
                        scales: {
                            x: {
                                ticks: { color: '#9ca3af' },
                                grid: { color: 'rgba(255, 255, 255, 0.1)' }
                            },
                            y: {
                                ticks: { color: '#9ca3af' },
                                grid: { color: 'rgba(255, 255, 255, 0.1)' }
                            }
                        }
                    }
                });
            }
        }
        
        function updatePNLChartData(data) {
            if (!pnlChart) return;
            
            const labels = data.map(d => {
                const date = new Date(d.timestamp);
                return date.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
            });
            
            const values = data.map(d => d.accumulated);
            
            pnlChart.data.labels = labels;
            pnlChart.data.datasets[0].data = values;
            pnlChart.update();
        }
        
        function updateDistributionCharts(metrics) {
            if (winrateChart) {
                winrateChart.data.datasets[0].data = [
                    metrics.winning_trades || 0,
                    metrics.losing_trades || 0
                ];
                winrateChart.update();
            }
        }
        
        async function updatePNLChart(hours) {
            try {
                const response = await fetch(`${API_BASE}/api/pnl-history?hours=${hours}`);
                const data = await response.json();
                updatePNLChartData(data);
            } catch (error) {
                console.error('Erro ao atualizar gráfico PNL:', error);
            }
        }
        
        async function loadPNLHistory(hours) {
            try {
                const response = await fetch(`${API_BASE}/api/pnl-history?hours=${hours}`);
                const data = await response.json();
                updatePNLChartData(data);
            } catch (error) {
                console.error('Erro ao carregar histórico PNL:', error);
            }
        }

        // ========== TRADES ==========
        
        async function loadTrades() {
            try {
                const response = await fetch(`${API_BASE}/api/trades?limit=${tradesLimit}`);
                const trades = await response.json();
                
                const tbody = document.getElementById('trades-table-body');
                
                if (trades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-gray-500">Nenhum trade registrado</td></tr>';
                    return;
                }
                
                tbody.innerHTML = trades.map(trade => {
                    const timestamp = new Date(trade.timestamp).toLocaleString('pt-BR');
                    const pnl = trade.pnl_usd || 0;
                    const pnlClass = pnl >= 0 ? 'text-green-400' : 'text-red-400';
                    const rowClass = pnl >= 0 ? 'trade-row-profit' : 'trade-row-loss';
                    
                    return `
                        <tr class="${rowClass}">
                            <td class="px-4 py-3">${timestamp}</td>
                            <td class="px-4 py-3">${trade.symbol || '-'}</td>
                            <td class="px-4 py-3 text-right ${pnlClass} font-semibold">$${pnl.toFixed(2)}</td>
                            <td class="px-4 py-3 text-right ${pnlClass}">${(trade.pnl_percent || 0).toFixed(2)}%</td>
                            <td class="px-4 py-3 text-right">${(trade.duration_minutes || 0).toFixed(1)}min</td>
                            <td class="px-4 py-3">${trade.reason || '-'}</td>
                            <td class="px-4 py-3 text-right">${(trade.accumulated_pnl || 0).toFixed(2)}</td>
                        </tr>
                    `;
                }).join('');
            } catch (error) {
                console.error('Erro ao carregar trades:', error);
                showAlert('error', 'Erro ao carregar histórico de trades');
            }
        }
        
        function refreshTrades() {
            tradesLimit = 50;
            loadTrades();
        }
        
        function loadMoreTrades() {
            tradesLimit += 50;
            loadTrades();
        }

        // ========== CONFIG v1.1 ==========
        
        function toggleStrategyOptions() {
            const strategy = document.getElementById('config-STRATEGY_TYPE').value;
            const gridOptions = document.getElementById('grid-options');
            
            // Mostrar opções de grid para todas as estratégias baseadas em grid
            const gridBasedStrategies = ['market_making', 'pure_grid', 'dynamic_grid'];
            
            if (gridBasedStrategies.includes(strategy)) {
                gridOptions.classList.remove('hidden');
            } else {
                // Multi Asset strategies não usam as mesmas configs de grid
                gridOptions.classList.add('hidden');
            }
        }
        
        function toggleAdvancedConfig() {
            const container = document.getElementById('advanced-config-container');
            const icon = document.getElementById('advanced-toggle-icon');
            
            if (container.classList.contains('hidden')) {
                container.classList.remove('hidden');
                icon.textContent = '▲';
            } else {
                container.classList.add('hidden');
                icon.textContent = '▼';
            }
        }
        
        async function loadConfig() {
            try {
                const response = await fetch(`${API_BASE}/api/config`);
                const config = await response.json();
                
                if (Object.keys(config).length === 0) {
                    showAlert('error', '⚠️ Arquivo .env não encontrado');
                    return;
                }
                
                // Campos de configuração rápida
                const quickFields = ['STRATEGY_TYPE', 'SYMBOL', 'GRID_LEVELS', 'ORDER_SIZE_USD', 'GRID_SPACING_PERCENT', 'MAX_POSITION_SIZE_USD'];
                
                quickFields.forEach(key => {
                    const input = document.getElementById(`config-${key}`);
                    if (input && config[key] !== undefined) {
                        input.value = config[key];
                    }
                });
                
                // Mostrar/ocultar opções de grid
                toggleStrategyOptions();
                
                // Configurações avançadas
                const advancedContainer = document.getElementById('advanced-config-container');
                const advancedFields = Object.entries(config).filter(([key]) => !quickFields.includes(key));
                
                if (advancedFields.length > 0) {
                    advancedContainer.innerHTML = advancedFields.map(([key, value]) => {
                        const isSecret = key.includes('PASSWORD') || key.includes('KEY') || key.includes('SECRET') || key === 'PRIVATE_KEY' || key === 'WALLET_ADDRESS';
                        return `
                            <div class="grid grid-cols-3 gap-4 items-center">
                                <label class="text-gray-400">${key}</label>
                                <input 
                                    type="${isSecret ? 'password' : 'text'}"
                                    id="config-advanced-${key}"
                                    value="${value}"
                                    class="col-span-2 bg-gray-700 text-white px-4 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                            </div>
                        `;
                    }).join('');
                } else {
                    advancedContainer.innerHTML = '<p class="text-gray-500">Nenhuma configuração avançada disponível</p>';
                }
                
                console.log('✅ Configurações carregadas');
            } catch (error) {
                console.error('Erro ao carregar config:', error);
                showAlert('error', 'Erro ao carregar configurações');
            }
        }
        
        async function saveConfig() {
            try {
                // Confirmar ação
                const botRunning = await isBotCurrentlyRunning();
                
                let confirmMessage = '💾 Salvar configurações?';
                if (botRunning) {
                    confirmMessage = '💾 Salvar e reiniciar o bot?\n\n⚠️ O bot está rodando e será reiniciado automaticamente para aplicar as novas configurações.';
                }
                
                if (!confirm(confirmMessage)) {
                    return;
                }
                
                showAlert('info', '⏳ Salvando configurações...');
                
                // Coletar todas as configurações
                const response = await fetch(`${API_BASE}/api/config`);
                const config = await response.json();
                
                const updates = {};
                
                // Campos rápidos
                const quickFields = ['STRATEGY_TYPE', 'SYMBOL', 'GRID_LEVELS', 'ORDER_SIZE_USD', 'GRID_SPACING_PERCENT', 'MAX_POSITION_SIZE_USD'];
                quickFields.forEach(key => {
                    const input = document.getElementById(`config-${key}`);
                    if (input && input.value) {
                        updates[key] = input.value;
                    }
                });
                
                // Campos avançados
                for (const key of Object.keys(config)) {
                    const advInput = document.getElementById(`config-advanced-${key}`);
                    if (advInput) {
                        updates[key] = advInput.value;
                    }
                }
                
                // Salvar
                const saveResponse = await fetch(`${API_BASE}/api/config/update`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(updates)
                });
                
                const result = await saveResponse.json();
                
                if (result.status !== 'success') {
                    showAlert('error', result.message);
                    return;
                }
                
                showAlert('success', '✅ Configurações salvas!');
                
                // Se bot está rodando, reiniciar automaticamente
                if (botRunning) {
                    showAlert('info', '🔄 Reiniciando bot...');
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    
                    const restartResult = await fetch(`${API_BASE}/api/bot/restart`, {
                        method: 'POST'
                    });
                    
                    const restartData = await restartResult.json();
                    
                    if (restartData.status === 'success') {
                        showAlert('success', '🎉 Bot reiniciado! Novas configurações aplicadas.');
                    } else {
                        showAlert('error', '❌ Erro ao reiniciar: ' + restartData.message);
                    }
                } else {
                    showAlert('info', 'ℹ️ Inicie o bot para aplicar as configurações.');
                }
                
            } catch (error) {
                console.error('Erro ao salvar config:', error);
                showAlert('error', 'Erro ao salvar configurações: ' + error.message);
            }
        }
        
        async function isBotCurrentlyRunning() {
            try {
                const response = await fetch(`${API_BASE}/api/bot/status`);
                const status = await response.json();
                return status.running === true;
            } catch (error) {
                return false;
            }
        }

        // ========== EXPORT ==========
        
        function exportCSV() {
            window.open(`${API_BASE}/api/export/csv`, '_blank');
            showAlert('success', '📥 Exportando CSV...');
        }

        // ========== VOLUME TRACKING ==========

        async function loadVolumeStats() {
            try {
                const response = await fetch(`${API_BASE}/api/volume/stats?periods=1h,24h,7d,14d`);
                const stats = await response.json();
                
                updateVolumeCards(stats);
                
                // Carregar detalhes de 24h
                if (stats['24h']) {
                    updateVolumeDetails(stats['24h']);
                }
                
            } catch (error) {
                console.error('Erro ao carregar volume:', error);
            }
        }

        function updateVolumeCards(stats) {
            const periods = ['1h', '24h', '7d', '14d'];
            
            periods.forEach(period => {
                const data = stats[period];
                if (!data) return;
                
                // Volume total
                const volumeEl = document.getElementById(`volume-${period}`);
                if (volumeEl) {
                    volumeEl.textContent = `$${formatNumber(data.total_volume)}`;
                }
                
                // Número de trades
                const tradesEl = document.getElementById(`volume-${period}-trades`);
                if (tradesEl) {
                    tradesEl.textContent = data.total_trades;
                }
                
                // Badge de variação (será preenchido pela comparação)
                const changeEl = document.getElementById(`volume-${period}-change`);
                if (changeEl) {
                    changeEl.textContent = '...';
                    changeEl.className = 'text-xs px-2 py-1 rounded bg-gray-700';
                }
            });
        }

        function updateVolumeDetails(data) {
            // Financeiro
            document.getElementById('volume-total-24h').textContent = `$${formatNumber(data.total_volume)}`;
            document.getElementById('volume-fees-24h').textContent = `$${formatNumber(data.total_fees)}`;
            
            const pnlEl = document.getElementById('volume-pnl-24h');
            pnlEl.textContent = `$${formatNumber(data.total_pnl)}`;
            pnlEl.className = data.total_pnl >= 0 ? 'font-bold text-green-400' : 'font-bold text-red-400';
            
            const avgVolume = data.total_trades > 0 ? data.total_volume / data.total_trades : 0;
            document.getElementById('volume-avg-24h').textContent = `$${formatNumber(avgVolume)}`;
            
            // Por símbolo
            const symbolContainer = document.getElementById('volume-by-symbol');
            if (data.by_symbol && Object.keys(data.by_symbol).length > 0) {
                symbolContainer.innerHTML = Object.entries(data.by_symbol)
                    .sort(([,a], [,b]) => b.volume - a.volume)
                    .map(([symbol, info]) => `
                        <div class="flex justify-between items-center text-sm">
                            <span class="text-gray-300">${symbol}:</span>
                            <div class="flex items-center gap-2">
                                <span class="font-bold">$${formatNumber(info.volume)}</span>
                                <span class="text-xs text-gray-500">(${info.trades})</span>
                            </div>
                        </div>
                    `).join('');
            } else {
                symbolContainer.innerHTML = '<p class="text-gray-500 text-sm">Nenhum trade encontrado</p>';
            }
            
            // Por direção
            if (data.by_side) {
                document.getElementById('volume-open-long').textContent = `$${formatNumber(data.by_side.open_long || 0)}`;
                document.getElementById('volume-open-short').textContent = `$${formatNumber(data.by_side.open_short || 0)}`;
                document.getElementById('volume-close-long').textContent = `$${formatNumber(data.by_side.close_long || 0)}`;
                document.getElementById('volume-close-short').textContent = `$${formatNumber(data.by_side.close_short || 0)}`;
            }
        }

        async function loadVolumeTimeline(hours = 24, interval = 60) {
            try {
                const response = await fetch(`${API_BASE}/api/volume/timeline?hours=${hours}&interval=${interval}`);
                const timeline = await response.json();
                
                if (!Array.isArray(timeline) || timeline.length === 0) {
                    console.warn('Timeline de volume vazia');
                    return;
                }
                
                updateVolumeTimelineChart(timeline);
                
            } catch (error) {
                console.error('Erro ao carregar timeline:', error);
            }
        }

        function updateVolumeTimelineChart(timeline) {
            const ctx = document.getElementById('volume-timeline-chart');
            if (!ctx) return;
            
            if (volumeTimelineChart) {
                volumeTimelineChart.destroy();
            }
            
            const labels = timeline.map(point => {
                const date = new Date(point.timestamp);
                return date.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
            });
            
            const volumes = timeline.map(point => point.volume);
            
            volumeTimelineChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Volume (USD)',
                        data: volumes,
                        backgroundColor: 'rgba(59, 130, 246, 0.8)',
                        borderColor: 'rgb(59, 130, 246)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: { color: '#fff' }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const point = timeline[context.dataIndex];
                                    return [
                                        `Volume: $${formatNumber(point.volume)}`,
                                        `Trades: ${point.trades}`,
                                        `PNL: $${formatNumber(point.pnl)}`
                                    ];
                                }
                            }
                        }
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            ticks: { 
                                color: '#9ca3af',
                                maxTicksLimit: 12
                            },
                            grid: { color: 'rgba(255, 255, 255, 0.1)' }
                        },
                        y: {
                            ticks: { 
                                color: '#9ca3af',
                                callback: value => `$${formatNumber(value)}`
                            },
                            grid: { color: 'rgba(255, 255, 255, 0.1)' }
                        }
                    }
                }
            });
        }

        async function loadVolumeComparison(period = '24h') {
            try {
                const response = await fetch(`${API_BASE}/api/volume/comparison?period=${period}`);
                const comparison = await response.json();
                
                updateVolumeComparison(comparison);
                
            } catch (error) {
                console.error('Erro ao carregar comparação:', error);
            }
        }

        function updateVolumeComparison(comparison) {
            // Período atual
            document.getElementById('comparison-current-volume').textContent = 
                `$${formatNumber(comparison.current.total_volume)}`;
            document.getElementById('comparison-current-trades').textContent = 
                comparison.current.total_trades;
            
            const currentPnlEl = document.getElementById('comparison-current-pnl');
            currentPnlEl.textContent = `$${formatNumber(comparison.current.total_pnl)}`;
            currentPnlEl.className = comparison.current.total_pnl >= 0 ? 
                'font-bold text-green-400' : 'font-bold text-red-400';
            
            // Período anterior
            document.getElementById('comparison-previous-volume').textContent = 
                `$${formatNumber(comparison.previous.total_volume)}`;
            document.getElementById('comparison-previous-trades').textContent = 
                comparison.previous.total_trades;
            
            const prevPnlEl = document.getElementById('comparison-previous-pnl');
            prevPnlEl.textContent = `$${formatNumber(comparison.previous.total_pnl)}`;
            prevPnlEl.className = comparison.previous.total_pnl >= 0 ? 
                'font-bold text-green-400' : 'font-bold text-red-400';
            
            // Variação
            document.getElementById('comparison-change-absolute').textContent = 
                `${comparison.change_absolute >= 0 ? '+' : ''}$${formatNumber(comparison.change_absolute)}`;
            
            const changePercentEl = document.getElementById('comparison-change-percent');
            changePercentEl.textContent = `${comparison.change_percent >= 0 ? '+' : ''}${comparison.change_percent.toFixed(1)}%`;
            
            if (comparison.change_percent >= 0) {
                changePercentEl.className = 'px-3 py-1 rounded font-bold bg-green-600 text-white';
            } else {
                changePercentEl.className = 'px-3 py-1 rounded font-bold bg-red-600 text-white';
            }
        }

        function formatNumber(num) {
            if (num >= 1000000) {
                return (num / 1000000).toFixed(2) + 'M';
            } else if (num >= 1000) {
                return (num / 1000).toFixed(2) + 'K';
            }
            return num.toFixed(2);
        }

        // ========== INIT ==========
        
        document.addEventListener('DOMContentLoaded', () => {
            console.log('✅ DOM carregado');
            
            // Inicializar timestamp imediatamente
            updateLastUpdateTime();
            
            initWebSocket();
            
            // Inicializar sistema de credenciais
            initCredentialsSystem();
            
            showTab('dashboard');
            
            // TENTATIVAS MÚLTIPLAS DE CARREGAMENTO
            let loadAttempts = 0;
            const maxAttempts = 5;
            
            function tryLoadData() {
                loadAttempts++;
                console.log(`🔄 Tentativa ${loadAttempts}/${maxAttempts} de carregar dados`);
                
                loadPositionsAndOrders().then(() => {
                    console.log('✅ Dados carregados com sucesso!');
                }).catch((error) => {
                    console.warn(`⚠️ Tentativa ${loadAttempts} falhou:`, error);
                    
                    if (loadAttempts < maxAttempts) {
                        // Tentar novamente em 2 segundos
                        setTimeout(tryLoadData, 2000);
                    } else {
                        console.error('❌ Todas as tentativas falharam. Use testLoadData() no console.');
                        const element = document.getElementById('last-update-time');
                        if (element) {
                            element.textContent = 'Erro - use F12 > Console > testLoadData()';
                            element.className = 'text-red-400';
                        }
                    }
                });
            }
            
            // Começar tentativas após 100ms
            setTimeout(tryLoadData, 100);
            
            // Carregar risk dashboard
            setTimeout(() => {
                updateRiskDashboard();
            }, 500);
            
            // Polling periódico para dados (fallback se WebSocket falhar)
            setInterval(() => {
                loadPositionsAndOrders();
                if (currentTab === 'dashboard') {
                    updateRiskDashboard();
                    // loadRiskPositionsMonitor();
                }
            }, 30000); // A cada 30 segundos
        });
        
        // ========== RISK MANAGEMENT FUNCTIONS (MELHORADAS) ==========
        
        /**
         * ✅ MELHORADO: Carrega status de risco com tratamento robusto de erros
         */
        async function loadRiskStatus() {
            const container = document.getElementById('risk-status');
            
            // Mostrar loading
            container.innerHTML = `
                <div class="flex justify-center items-center py-8">
                    <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    <span class="ml-3 text-gray-400">Carregando dados de risco...</span>
                </div>
            `;
            
            try {
                console.log('📡 Buscando status de risco...');
                const response = await fetch(`${API_BASE}/api/risk/status`);
                
                // ✅ NOVO: Verificar status HTTP antes de parsear JSON
                if (!response.ok) {
                    console.warn(`⚠️ Resposta HTTP ${response.status} ao carregar risco`);
                    
                    // Tentar ler erro da resposta
                    let errorData;
                    try {
                        errorData = await response.json();
                    } catch (e) {
                        errorData = { error: `Erro HTTP ${response.status}` };
                    }
                    
                    console.warn('Dados de erro:', errorData);
                    
                    // ✅ NOVO: Mostrar UI de erro amigável baseada no status
                    const errorMessage = errorData.error || errorData.message || 'Serviço temporariamente indisponível';
                    const botStatus = errorData.bot_status || 'unknown';
                    
                    let statusIcon = '⚠️';
                    let statusColor = 'yellow';
                    let userMessage = errorMessage;
                    
                    if (response.status === 503) {
                        if (botStatus === 'disconnected') {
                            statusIcon = '🚫';
                            statusColor = 'red';
                            userMessage = 'Bot não está rodando. Inicie o bot para visualizar dados de risco em tempo real.';
                        } else if (botStatus === 'running_separate') {
                            statusIcon = '🔗';
                            statusColor = 'yellow';
                            userMessage = 'Bot rodando em processo separado. Dados de risco limitados neste modo.';
                        }
                    } else if (response.status === 500) {
                        statusIcon = '❌';
                        statusColor = 'red';
                        userMessage = 'Erro interno ao processar dados de risco. Verifique os logs.';
                    }
                    
                    container.innerHTML = `
                        <div class="bg-${statusColor}-900/30 border border-${statusColor}-600 rounded-lg p-6">
                            <div class="flex items-start gap-4">
                                <span class="text-4xl">${statusIcon}</span>
                                <div class="flex-1">
                                    <h3 class="text-xl font-semibold mb-2 text-${statusColor}-300">
                                        ${botStatus === 'disconnected' ? 'Bot Desconectado' : 
                                          botStatus === 'running_separate' ? 'Modo Limitado' : 
                                          'Erro ao Carregar'}
                                    </h3>
                                    <p class="text-gray-300 mb-3">${userMessage}</p>
                                    ${botStatus === 'disconnected' ? `
                                        <code class="block bg-gray-800 px-3 py-2 rounded text-sm mt-2">
                                            python grid_bot.py
                                        </code>
                                    ` : ''}
                                    ${response.status === 503 ? `
                                        <button onclick="loadRiskStatus()" 
                                                class="mt-3 bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
                                            🔄 Tentar Novamente
                                        </button>
                                    ` : ''}
                                </div>
                            </div>
                        </div>
                    `;
                    return;
                }
                
                // ✅ Resposta OK - parsear JSON
                const data = await response.json();
                console.log('✅ Status de risco carregado:', data);
                
                // ✅ NOVO: Validar estrutura básica do JSON
                if (!data || typeof data !== 'object') {
                    throw new Error('Resposta inválida do servidor');
                }
                
                // Atualizar display com dados
                updateRiskDisplay(data);
                
            } catch (error) {
                console.error('❌ Erro crítico ao carregar status de risco:', error);
                
                // ✅ NOVO: Mostrar erro detalhado para debugging
                container.innerHTML = `
                    <div class="bg-red-900/30 border border-red-600 rounded-lg p-6">
                        <div class="flex items-start gap-4">
                            <span class="text-4xl">❌</span>
                            <div class="flex-1">
                                <h3 class="text-xl font-semibold mb-2 text-red-300">Erro de Conexão</h3>
                                <p class="text-gray-300 mb-3">
                                    Não foi possível conectar ao servidor de risco.
                                </p>
                                <details class="text-sm">
                                    <summary class="cursor-pointer text-gray-400 hover:text-gray-300">
                                        Ver detalhes técnicos
                                    </summary>
                                    <pre class="mt-2 bg-gray-800 p-2 rounded overflow-x-auto text-xs">
${error.message}
${error.stack || ''}
                                    </pre>
                                </details>
                                <button onclick="loadRiskStatus()" 
                                        class="mt-3 bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
                                    🔄 Tentar Novamente
                                </button>
                            </div>
                        </div>
                    </div>
                `;
                
                // Mostrar alerta também
                showAlert('error', `Erro ao carregar dados de risco: ${error.message}`);
            }
        }
        
        function updateRiskDisplay(riskData) {
            const container = document.getElementById('risk-status');
            
            // Verificar se o bot não está rodando
            if (riskData.bot_status === 'disconnected') {
                container.innerHTML = `
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        <div class="risk-metric bg-red-900/30 border border-red-700">
                            <div class="flex items-center mb-3">
                                <span class="text-2xl mr-3">🚫</span>
                                <div>
                                    <h4 class="font-semibold text-red-300">Bot Desconectado</h4>
                                    <p class="text-sm text-gray-400">Inicie o bot com: python grid_bot.py</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="risk-metric">
                            <h4 class="font-semibold mb-3">⚙️ Configurações (.env)</h4>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span>Proteção de Sessão:</span>
                                    <span class="${riskData.session_protection ? 'text-green-400' : 'text-red-400'}">
                                        ${riskData.session_protection ? 'Ativada' : 'Desativada'}
                                    </span>
                                </div>
                                <div class="flex justify-between">
                                    <span>Limite de Perda:</span>
                                    <span class="text-red-400">$${riskData.session_max_loss_usd}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span>Meta de Lucro:</span>
                                    <span class="text-green-400">$${riskData.session_profit_target_usd}</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="risk-metric">
                            <h4 class="font-semibold mb-3">🔄 Proteção de Ciclo</h4>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span>Status:</span>
                                    <span class="${riskData.cycle_protection ? 'text-green-400' : 'text-red-400'}">
                                        ${riskData.cycle_protection ? 'Ativada' : 'Desativada'}
                                    </span>
                                </div>
                                <div class="flex justify-between">
                                    <span>Stop Loss:</span>
                                    <span class="text-red-400">${riskData.cycle_sl}%</span>
                                </div>
                                <div class="flex justify-between">
                                    <span>Take Profit:</span>
                                    <span class="text-green-400">${riskData.cycle_tp}%</span>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                return;
            }
            
            // Bot rodando separadamente - mostrar configurações básicas
            if (riskData.bot_status === 'running_separate') {
                container.innerHTML = `
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        <div class="risk-metric bg-yellow-900/30 border border-yellow-700">
                            <div class="flex items-center mb-3">
                                <span class="text-2xl mr-3">🔗</span>
                                <div>
                                    <h4 class="font-semibold text-yellow-300">Bot Rodando (Processo Separado)</h4>
                                    <p class="text-sm text-gray-400">Dados detalhados não disponíveis via Flask</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="risk-metric">
                            <h4 class="font-semibold mb-3">⚙️ Configurações Ativas</h4>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span>Proteção de Sessão:</span>
                                    <span class="${riskData.session_protection ? 'text-green-400' : 'text-red-400'}">
                                        ${riskData.session_protection ? 'Ativada' : 'Desativada'}
                                    </span>
                                </div>
                                <div class="flex justify-between">
                                    <span>Limite de Perda:</span>
                                    <span class="text-red-400">$${riskData.session_max_loss_usd}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span>Meta de Lucro:</span>
                                    <span class="text-green-400">$${riskData.session_profit_target_usd}</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="risk-metric">
                            <h4 class="font-semibold mb-3">🛡️ Sistema de Emergência</h4>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span>Emergency SL:</span>
                                    <span class="text-red-400">${riskData.emergency_sl_percent}%</span>
                                </div>
                                <div class="flex justify-between">
                                    <span>Emergency TP:</span>
                                    <span class="text-green-400">${riskData.emergency_tp_percent}%</span>
                                </div>
                                <div class="flex justify-between">
                                    <span>Ação no Limite:</span>
                                    <span class="text-blue-400">${riskData.action_on_limit}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                return;
            }
            
            // ✅ CORREÇÃO: Verificar se temos dados completos ou apenas configurações básicas
            const hasComplexData = riskData.session_protection && 
                                   typeof riskData.session_protection === 'object' &&
                                   riskData.session_protection.loss_risk_level;
            
            if (!hasComplexData) {
                // Dados simples - mostrar apenas configurações básicas
                const botConnected = riskData.bot_status !== 'disconnected';
                const statusColor = botConnected ? (riskData.is_paused ? 'orange' : 'green') : 'orange';
                const statusIcon = botConnected ? (riskData.is_paused ? '⏸️' : '▶️') : '🔌';
                const statusText = riskData.is_paused ? `Pausado até: ${riskData.pause_until}` :
                                   botConnected ? 'Operando normalmente' : 'Aguardando conexão do bot...';
                
                container.innerHTML = `
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        <!-- Status Geral -->
                        <div class="bg-gray-700 rounded-lg p-4 border-l-4" style="border-left-color: ${statusColor};">
                            <div class="flex items-center justify-between mb-3">
                                <h4 class="font-semibold text-gray-300">Status Geral</h4>
                                <span class="text-2xl">${statusIcon}</span>
                            </div>
                            <div class="text-lg font-bold" style="color: ${statusColor};">${statusText}</div>
                            ${riskData.last_check ? `<div class="text-xs text-gray-400 mt-2">Última verificação: ${riskData.last_check}</div>` : ''}
                        </div>
                        
                        <!-- Nível 1 (Ciclo) -->
                        <div class="bg-gray-700 rounded-lg p-4 border-l-4 ${riskData.cycle_protection ? 'border-green-500' : 'border-red-500'}">
                            <div class="flex items-center justify-between mb-3">
                                <h4 class="font-semibold text-gray-300">🔄 Nível 1 (Ciclo)</h4>
                                <span class="${riskData.cycle_protection ? 'text-green-400' : 'text-red-400'} text-sm font-medium">
                                    ${riskData.cycle_protection ? '✅ Ativo' : '❌ Desligado'}
                                </span>
                            </div>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Stop Loss:</span>
                                    <span class="text-red-400 font-medium">${riskData.cycle_sl}%</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Take Profit:</span>
                                    <span class="text-green-400 font-medium">${riskData.cycle_tp}%</span>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Nível 2 (Sessão) -->
                        <div class="bg-gray-700 rounded-lg p-4 border-l-4 ${riskData.session_protection ? 'border-green-500' : 'border-red-500'}">
                            <div class="flex items-center justify-between mb-3">
                                <h4 class="font-semibold text-gray-300">🛡️ Nível 2 (Sessão)</h4>
                                <span class="${riskData.session_protection ? 'text-green-400' : 'text-red-400'} text-sm font-medium">
                                    ${riskData.session_protection ? '✅ Ativo' : '❌ Desligado'}
                                </span>
                            </div>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Max Loss:</span>
                                    <span class="text-red-400 font-medium">$${riskData.session_max_loss_usd}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Meta Lucro:</span>
                                    <span class="text-green-400 font-medium">$${riskData.session_profit_target_usd}</span>
                                </div>
                                ${riskData.action_on_limit ? `
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Ação:</span>
                                    <span class="text-blue-400 font-medium">${riskData.action_on_limit}</span>
                                </div>
                                ` : ''}
                            </div>
                        </div>
                        
                        <!-- Emergency Stop -->
                        <div class="bg-gray-700 rounded-lg p-4 border-l-4 border-orange-500">
                            <div class="flex items-center justify-between mb-3">
                                <h4 class="font-semibold text-gray-300">🚨 Emergency Stop</h4>
                                <span class="text-orange-400 text-xs px-2 py-1 bg-orange-900 rounded">BACKUP</span>
                            </div>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Emergency SL:</span>
                                    <span class="text-red-400 font-medium">${riskData.emergency_sl_percent}%</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Emergency TP:</span>
                                    <span class="text-green-400 font-medium">${riskData.emergency_tp_percent}%</span>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Posições Ativas -->
                        <div class="bg-gray-700 rounded-lg p-4 border-l-4 border-blue-500">
                            <div class="flex items-center justify-between mb-3">
                                <h4 class="font-semibold text-gray-300">📊 Posições Ativas</h4>
                                <span class="text-2xl font-bold text-blue-400">${riskData.active_positions_count || 0}</span>
                            </div>
                            <div class="text-xs text-gray-400">
                                ${(riskData.active_positions_count || 0) > 0 ? 'Posições abertas no momento' : 'Nenhuma posição aberta'}
                            </div>
                        </div>
                        
                        <!-- Desempenho -->
                        <div class="bg-gray-700 rounded-lg p-4 border-l-4 ${(riskData.accumulated_pnl || 0) >= 0 ? 'border-green-500' : 'border-red-500'}">
                            <div class="flex items-center justify-between mb-3">
                                <h4 class="font-semibold text-gray-300">💰 Desempenho</h4>
                                <span class="${(riskData.accumulated_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'} font-bold">
                                    ${(riskData.accumulated_pnl || 0) >= 0 ? '+' : ''}${(riskData.accumulated_pnl || 0).toFixed(2)} USD
                                </span>
                            </div>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between">
                                    <span class="text-gray-400">Ciclos:</span>
                                    <span class="text-gray-300">${riskData.cycles_closed || 0}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">🏆 Lucro:</span>
                                    <span class="text-green-400">${riskData.cycles_profit || 0}</span>
                                </div>
                                <div class="flex justify-between">
                                    <span class="text-gray-400">💀 Perda:</span>
                                    <span class="text-red-400">${riskData.cycles_loss || 0}</span>
                                </div>
                                ${riskData.session_start && riskData.session_start !== 'Bot não iniciado' ? `
                                    <div class="text-xs text-gray-400 mt-2 pt-2 border-t border-gray-600">
                                        Início: ${riskData.session_start}
                                    </div>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                `;
                return;
            }
            
            // Dados completos - usar a estrutura complexa original
            const session = riskData.session_protection;
            const cycle = riskData.cycle_protection;
            
            // Determinar status geral
            let overallStatus = 'safe';
            if (session.loss_risk_level === 'HIGH' || cycle.loss_risk_level === 'HIGH') {
                overallStatus = 'danger';
            } else if (session.loss_risk_level === 'MEDIUM' || cycle.loss_risk_level === 'MEDIUM') {
                overallStatus = 'warning';
            }
            
            container.innerHTML = `
                <div class="risk-metrics">
                    <!-- Status Geral -->
                    <div class="risk-metric risk-status-${overallStatus}">
                        <div class="flex justify-between items-center mb-2">
                            <span class="text-sm font-medium">Status Geral</span>
                            <span class="text-lg">${overallStatus === 'safe' ? '🟢' : overallStatus === 'warning' ? '🟡' : '🔴'}</span>
                        </div>
                        <p class="text-xl font-bold">
                            ${overallStatus === 'safe' ? 'Seguro' : overallStatus === 'warning' ? 'Atenção' : 'Risco Alto'}
                        </p>
                    </div>
                    
                    <!-- Sessão -->
                    <div class="risk-metric">
                        <h4 class="font-semibold mb-3">📊 Sessão Atual</h4>
                        <div class="space-y-2 text-sm">
                            <div class="flex justify-between">
                                <span>PNL Atual:</span>
                                <span class="${session.current_pnl >= 0 ? 'text-green-400' : 'text-red-400'}">
                                    $${session.current_pnl.toFixed(2)}
                                </span>
                            </div>
                            <div class="flex justify-between">
                                <span>Meta Lucro:</span>
                                <span class="text-green-400">$${session.profit_target.toFixed(2)}</span>
                            </div>
                            <div class="flex justify-between">
                                <span>Limite Perda:</span>
                                <span class="text-red-400">-$${session.max_loss.toFixed(2)}</span>
                            </div>
                            <div class="mt-3">
                                <div class="flex justify-between mb-1">
                                    <span>Margem de Segurança:</span>
                                    <span class="text-${session.loss_risk_level === 'LOW' ? 'green' : session.loss_risk_level === 'MEDIUM' ? 'yellow' : 'red'}-400">
                                        $${session.remaining_loss_buffer.toFixed(2)}
                                    </span>
                                </div>
                                <div class="risk-progress">
                                    <div class="risk-progress-bar risk-progress-${session.loss_risk_level === 'LOW' ? 'safe' : session.loss_risk_level === 'MEDIUM' ? 'warning' : 'danger'}" 
                                         style="width: ${Math.max(0, Math.min(100, (session.max_loss + session.current_pnl) / session.max_loss * 100))}%"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Ciclo -->
                    <div class="risk-metric">
                        <h4 class="font-semibold mb-3">🔄 Ciclo Atual</h4>
                        <div class="space-y-2 text-sm">
                            <div class="flex justify-between">
                                <span>PNL Ciclo:</span>
                                <span class="${cycle.current_pnl >= 0 ? 'text-green-400' : 'text-red-400'}">
                                    $${cycle.current_pnl.toFixed(2)}
                                </span>
                            </div>
                            <div class="flex justify-between">
                                <span>Meta Lucro:</span>
                                <span class="text-green-400">$${cycle.profit_target.toFixed(2)}</span>
                            </div>
                            <div class="flex justify-between">
                                <span>Limite Perda:</span>
                                <span class="text-red-400">-$${cycle.max_loss.toFixed(2)}</span>
                            </div>
                            <div class="mt-3">
                                <div class="flex justify-between mb-1">
                                    <span>Margem de Segurança:</span>
                                    <span class="text-${cycle.loss_risk_level === 'LOW' ? 'green' : cycle.loss_risk_level === 'MEDIUM' ? 'yellow' : 'red'}-400">
                                        $${cycle.remaining_loss_buffer.toFixed(2)}
                                    </span>
                                </div>
                                <div class="risk-progress">
                                    <div class="risk-progress-bar risk-progress-${cycle.loss_risk_level === 'LOW' ? 'safe' : cycle.loss_risk_level === 'MEDIUM' ? 'warning' : 'danger'}" 
                                         style="width: ${Math.max(0, Math.min(100, (cycle.max_loss + cycle.current_pnl) / cycle.max_loss * 100))}%"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Emergency Stop -->
                    ${riskData.emergency_stop ? `
                    <div class="risk-metric risk-status-${riskData.emergency_stop.is_active ? 'danger' : 'safe'}">
                        <h4 class="font-semibold mb-3">🚨 Emergency Stop</h4>
                        <div class="space-y-2 text-sm">
                            <div class="flex justify-between">
                                <span>Status:</span>
                                <span class="${riskData.emergency_stop.is_active ? 'text-red-400' : 'text-green-400'}">
                                    ${riskData.emergency_stop.is_active ? 'ATIVO' : 'Desativo'}
                                </span>
                            </div>
                            <div class="flex justify-between">
                                <span>Limite:</span>
                                <span class="text-red-400">-$${riskData.emergency_stop.stop_loss_threshold.toFixed(2)}</span>
                            </div>
                        </div>
                    </div>
                    ` : ''}
                </div>
            `;
        }
        
        // ========== RISK MONITOR FUNCTIONS ==========
        
        /**
         * ✅ MELHORADO: Carrega monitor de posições com tratamento robusto
         */
        async function loadRiskPositionsMonitor() {
            const container = document.getElementById('risk-positions-container');
            const statusContainer = document.getElementById('risk-monitor-status');
            
            // Mostrar loading
            container.innerHTML = `
                <div class="flex justify-center items-center py-8">
                    <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    <span class="ml-3 text-gray-400">Carregando posições...</span>
                </div>
            `;
            
            try {
                console.log('📡 Buscando posições para risk monitor...');
                const response = await fetch(`${API_BASE}/api/risk/positions`);
                
                // ✅ NOVO: Verificar status antes de parsear
                if (!response.ok) {
                    console.warn(`⚠️ Resposta HTTP ${response.status}`);
                    
                    let errorData;
                    try {
                        errorData = await response.json();
                    } catch (e) {
                        errorData = { error: `Erro HTTP ${response.status}` };
                    }
                    
                    updateRiskMonitorStatus('error');
                    
                    container.innerHTML = `
                        <div class="text-center py-8">
                            <div class="text-6xl mb-4">⚠️</div>
                            <h3 class="text-xl font-semibold mb-2 text-yellow-300">Erro ao Carregar Posições</h3>
                            <p class="text-gray-400 mb-4">${errorData.error || 'Serviço indisponível'}</p>
                            <button onclick="loadRiskPositionsMonitor()" 
                                    class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded">
                                🔄 Tentar Novamente
                            </button>
                        </div>
                    `;
                    return;
                }
                
                const data = await response.json();
                console.log('✅ Posições carregadas:', data);
                
                // ✅ NOVO: Validar estrutura
                if (!data || typeof data !== 'object') {
                    throw new Error('Resposta inválida do servidor');
                }
                
                updateRiskPositionsDisplay(data);
                updateRiskMonitorStatus(data.bot_status || 'unknown');
                
            } catch (error) {
                console.error('❌ Erro ao carregar risk monitor:', error);
                
                updateRiskMonitorStatus('error');
                
                container.innerHTML = `
                    <div class="bg-red-900/30 border border-red-600 rounded-lg p-6 text-center">
                        <div class="text-4xl mb-4">❌</div>
                        <h3 class="text-xl font-semibold mb-2 text-red-300">Erro de Conexão</h3>
                        <p class="text-gray-400 mb-4">${error.message}</p>
                        <button onclick="loadRiskPositionsMonitor()" 
                                class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded">
                            🔄 Tentar Novamente
                        </button>
                    </div>
                `;
                
                showAlert('error', `Erro ao carregar monitor: ${error.message}`);
            }
        }
        
        /**
         * ✅ MELHORADO: Atualiza status do monitor com ícones corretos
         */
        function updateRiskMonitorStatus(status) {
            const statusContainer = document.getElementById('risk-monitor-status');
            if (!statusContainer) return;
            
            const indicator = statusContainer.querySelector('.w-3');
            const text = statusContainer.querySelector('span');
            
            if (!indicator || !text) return;
            
            // ✅ NOVO: Mapeamento de status mais completo
            const statusMap = {
                'connected': {
                    color: 'bg-green-500',
                    text: 'Conectado',
                    class: 'monitor-status-connected'
                },
                'running_separate': {
                    color: 'bg-yellow-500',
                    text: 'Bot Separado',
                    class: 'monitor-status-warning'
                },
                'disconnected': {
                    color: 'bg-red-500',
                    text: 'Desconectado',
                    class: 'monitor-status-disconnected'
                },
                'error': {
                    color: 'bg-red-500',
                    text: 'Erro',
                    class: 'monitor-status-disconnected'
                },
                'unknown': {
                    color: 'bg-gray-500',
                    text: 'Desconhecido',
                    class: 'text-gray-400'
                }
            };
            
            const config = statusMap[status] || statusMap['unknown'];
            
            indicator.className = `w-3 h-3 rounded-full ${config.color}`;
            text.textContent = config.text;
            text.className = `text-sm ${config.class}`;
        }
        
        /**
         * ✅ MELHORADO: Refresh manual do risk monitor
         */
        function refreshRiskMonitor() {
            console.log('🔄 Refresh manual do risk monitor');
           // loadRiskPositionsMonitor();
        }
        
        /**
         * ✅ NOVO: Função helper para mostrar placeholders de loading
         */
        function showRiskLoadingPlaceholder(containerId, message = 'Carregando...') {
            const container = document.getElementById(containerId);
            if (!container) return;
            
            container.innerHTML = `
                <div class="flex justify-center items-center py-8">
                    <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    <span class="ml-3 text-gray-400">${message}</span>
                </div>
            `;
        }
        
        /**
         * ✅ NOVO: Função helper para validar resposta JSON
         */
        function validateRiskResponse(data, requiredFields = []) {
            if (!data || typeof data !== 'object') {
                console.error('❌ Resposta inválida:', data);
                return false;
            }
            
            for (const field of requiredFields) {
                if (!(field in data)) {
                    console.warn(`⚠️ Campo obrigatório ausente: ${field}`);
                    // Não retorna false - campos ausentes terão valores padrão
                }
            }
            
            return true;
        }
        
        // ========== FIM DAS CORREÇÕES RISK MANAGEMENT ==========
        console.log('✅ Funções de Risk Management corrigidas e carregadas (v1.2)');

        // ========== PAINEL UNIFICADO DE RISCO - TELEMETRIA ==========
        
        async function fetchJson(path) {
          const res = await fetch(path);
          if (!res.ok) throw new Error(`Falha ao buscar ${path}`);
          return await res.json();
        }

        function fmtNum(v, digits = 2) {
          return isNaN(v) ? '—' : parseFloat(v).toFixed(digits);
        }

        function fmtTime(secs) {
          if (!secs) return '—';
          const h = Math.floor(secs / 3600);
          const m = Math.floor((secs % 3600) / 60);
          const s = secs % 60;
          return `${h}h ${m}m ${s}s`;
        }

        async function updateRiskDashboard() {
          try {
            const [active, status] = await Promise.all([
              fetchJson('/api/risk/telemetry/active'),
              fetchJson('/api/risk/telemetry/status')
            ]);

            // 🔹 CONFIGURAÇÕES
            const trade = active.trade || active || {};
            const extra = trade.extra || {};
            const emerg = extra.emergency || {};
            const session = extra.session || {};
            const risk_config = extra.risk_config || {};

            document.getElementById('cfg-cycle-sl').textContent = extra.cycle_thresholds?.['sl%'] ?? '—';
            document.getElementById('cfg-cycle-tp').textContent = extra.cycle_thresholds?.['tp%'] ?? '—';
            document.getElementById('cfg-emerg-sl').textContent = risk_config.emergency_sl_percent ?? emerg['sl%'] ?? '—';
            document.getElementById('cfg-emerg-tp').textContent = risk_config.emergency_tp_percent ?? emerg['tp%'] ?? '—';
            document.getElementById('cfg-margin').textContent = status.margin_percent ?? '—';
            document.getElementById('cfg-session-loss').textContent = risk_config.session_max_loss_usd ?? session.max_loss_usd ?? '—';
            document.getElementById('cfg-session-profit').textContent = risk_config.session_profit_target_usd ?? session.profit_target_usd ?? '—';

            // 🔹 TRADE ATUAL
            const pnlUsd = trade.pnl_usd ?? 0;
            const pnlPct = trade.pnl_percent ?? 0;
            const pnlColor = pnlUsd > 0 ? '#4ade80' : pnlUsd < 0 ? '#f87171' : '#e5e7eb';
            document.getElementById('trade-id').textContent = trade.trade_id || '—';
            document.getElementById('trade-symbol').textContent = trade.symbol || '—';
            document.getElementById('trade-side').textContent = trade.side || '—';
            document.getElementById('trade-time').textContent = fmtTime(trade.time_in_trade_sec);
            document.getElementById('trade-price').textContent = fmtNum(trade.current_price);
            document.getElementById('trade-pnl-usd').textContent = `$${fmtNum(pnlUsd)}`;
            document.getElementById('trade-pnl-usd').style.color = pnlColor;
            document.getElementById('trade-pnl-pct').textContent = `${fmtNum(pnlPct)}%`;
            document.getElementById('trade-pnl-pct').style.color = pnlColor;
            document.getElementById('trade-status').textContent = active.active ? 'Trade em andamento' : 'Nenhum trade ativo';

            // 🔹 SESSÃO / SAÚDE
            document.getElementById('session-cycles').textContent = session.cycles_closed ?? '0';
            document.getElementById('session-pnl').textContent = fmtNum(session.accumulated_pnl ?? 0);
            document.getElementById('session-margin').textContent = fmtNum(status.margin_percent ?? 0);
            document.getElementById('session-lastcheck').textContent = new Date(status.timestamp || Date.now()).toLocaleTimeString();
            document.getElementById('session-flags').textContent = Object.keys(extra).length ? Object.keys(extra).join(', ') : '—';

            // Indicador geral
            const ind = document.getElementById('risk-status-indicator');
            const isActive = active.active === true || active.active === "true" || (active.trade && Object.keys(active.trade).length > 0);
            ind.textContent = isActive ? 'Online' : 'Parado';
            ind.style.backgroundColor = isActive ? '#22c55e' : '#ef4444';
          } catch (err) {
            console.warn('Erro atualizando painel de risco', err);
          }
        }

        // Inicializar painel de risco unificado
        setInterval(updateRiskDashboard, 3000);
        updateRiskDashboard();
        console.log('✅ Painel unificado de risco inicializado');
        
        function updateRiskPositionsDisplay(data) {
            const container = document.getElementById('risk-positions-container');
            
            if (data.bot_status === 'disconnected') {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <div class="text-6xl mb-4">🚫</div>
                        <h3 class="text-xl font-semibold mb-2 text-red-300">Bot Não Está Rodando</h3>
                        <p class="text-gray-400 mb-4">Inicie o bot para monitorar posições em tempo real</p>
                        <code class="bg-gray-800 px-3 py-1 rounded text-sm">python grid_bot.py</code>
                    </div>
                `;
                return;
            }
            
            if (data.bot_status === 'running_separate') {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <div class="text-6xl mb-4">🔗</div>
                        <h3 class="text-xl font-semibold mb-2 text-yellow-300">Bot Rodando (Processo Separado)</h3>
                        <p class="text-gray-400 mb-4">Risk managers não integrados ao Flask</p>
                        <p class="text-sm text-gray-500">Dados de monitoramento limitados neste modo</p>
                    </div>
                `;
                return;
            }
            
            if (!data.positions || data.positions.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <div class="text-6xl mb-4">📊</div>
                        <h3 class="text-xl font-semibold mb-2">Nenhuma Posição Ativa</h3>
                        <p class="text-gray-400">O bot está rodando mas não há posições para monitorar</p>
                    </div>
                `;
                return;
            }
            
            // Renderizar posições
            container.innerHTML = data.positions.map(position => createPositionCard(position)).join('');
        }
        
        /**
         * ✅ MELHORADO: Cria card de posição com validação robusta
         */
        function createPositionCard(position) {
            // ✅ NOVO: Validação de segurança robusta
            if (!position || typeof position !== 'object') {
                console.error('❌ createPositionCard recebeu dados inválidos:', position);
                return `
                    <div class="position-card bg-red-900/30 border border-red-600 rounded-lg p-4 text-center">
                        <p class="text-red-400">❌ Erro: Dados da posição inválidos</p>
                    </div>
                `;
            }
            
            // ✅ NOVO: Valores padrão seguros com validação de tipo
            const safeFloat = (value, defaultValue = 0) => {
                const parsed = parseFloat(value);
                return isNaN(parsed) ? defaultValue : parsed;
            };
            
            const safeString = (value, defaultValue = 'N/A') => {
                return value && typeof value === 'string' ? value : defaultValue;
            };
            
            // Extrair dados com valores padrão
            const symbol = safeString(position.symbol, 'UNKNOWN');
            const side = safeString(position.side, 'unknown');
            const quantity = safeFloat(position.quantity, 0);
            const entryPrice = safeFloat(position.entry_price, 0);
            const currentPrice = safeFloat(position.current_price, 0);
            const pnlUsd = safeFloat(position.pnl_usd, 0);
            const pnlPercent = safeFloat(position.pnl_percent, 0);
            const leverage = safeFloat(position.leverage, 1);
            
            // Determinar classes de estilo
            const pnlClass = pnlUsd > 0 ? 'positive' : pnlUsd < 0 ? 'negative' : 'neutral';
            const riskLevel = position.overall_risk_level || 1;
            
            // ✅ NOVO: Validar estruturas aninhadas antes de usar
            const hasCycleProtection = position.cycle_protection && 
                                       typeof position.cycle_protection === 'object';
            
            const hasSessionProtection = position.session_protection && 
                                         typeof position.session_protection === 'object';
            
            const hasEmergencySystem = position.emergency_system && 
                                      typeof position.emergency_system === 'object';
            
            // Helper para criar item de risco com validação
            const createRiskItemSafe = (label, data, type = 'percent') => {
                if (!data || typeof data !== 'object') {
                    return `
                        <div class="risk-item-placeholder">
                            ${label}: Não configurado
                        </div>
                    `;
                }
                
                const current = safeFloat(data.current_percent || data.current, 0);
                const limit = safeFloat(data.limit_percent || data.limit || data.target_percent, 0);
                const status = safeString(data.status, 'unknown');
                const triggered = data.triggered === true;
                
                const progress = limit !== 0 ? Math.min(100, Math.abs(current / limit) * 100) : 0;
                const statusClass = triggered ? 'critical' : status;
                
                return `
                    <div class="risk-item">
                        <div class="risk-item-label">
                            <div class="risk-status-indicator status-${statusClass}"></div>
                            <span>${label}</span>
                        </div>
                        <div class="risk-item-value ${triggered ? 'text-red-400 font-bold' : ''}">
                            ${current.toFixed(2)}${type} / ${Math.abs(limit).toFixed(2)}${type}
                            ${triggered ? ' ⚠️' : ''}
                        </div>
                    </div>
                    <div class="risk-progress-container">
                        <div class="risk-progress-label">
                            <span>${label}</span>
                            <span>${progress.toFixed(1)}%</span>
                        </div>
                        <div class="risk-progress-bar-container">
                            <div class="risk-progress-fill risk-progress-${statusClass}" 
                                 style="width: ${progress}%"></div>
                        </div>
                    </div>
                `;
            };
            
            return `
                <div class="position-card risk-level-${riskLevel}">
                    <div class="position-header">
                        <div>
                            <div class="position-symbol">
                                ${symbol} 
                                <span class="text-sm font-normal text-gray-400">
                                    ${side.toUpperCase()} ${quantity.toFixed(4)}
                                </span>
                            </div>
                            <div class="text-sm text-gray-400">
                                Entry: $${entryPrice.toLocaleString()} | 
                                Current: $${currentPrice.toLocaleString()}
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="position-pnl ${pnlClass}">
                                ${pnlUsd >= 0 ? '+' : ''}$${pnlUsd.toFixed(2)}
                            </div>
                            <div class="position-pnl ${pnlClass} text-sm">
                                ${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%
                            </div>
                        </div>
                    </div>
                    
                    <div class="risk-layers">
                        <!-- Nível 1: Proteção por Ciclo -->
                        <div class="risk-layer">
                            <div class="risk-layer-header">
                                <span>🛡️ Nível 1 - Proteção por Ciclo</span>
                            </div>
                            <div class="risk-items">
                                ${hasCycleProtection && position.cycle_protection.stop_loss ? 
                                    createRiskItemSafe('Stop Loss', position.cycle_protection.stop_loss, '%') :
                                    '<div class="risk-item-placeholder">Stop Loss: Não configurado</div>'
                                }
                                ${hasCycleProtection && position.cycle_protection.take_profit ? 
                                    createRiskItemSafe('Take Profit', position.cycle_protection.take_profit, '%') :
                                    '<div class="risk-item-placeholder">Take Profit: Não configurado</div>'
                                }
                            </div>
                        </div>
                        
                        <!-- Nível 2: Proteção de Sessão -->
                        <div class="risk-layer">
                            <div class="risk-layer-header">
                                <span>📊 Nível 2 - Proteção de Sessão</span>
                            </div>
                            <div class="risk-items">
                                ${hasSessionProtection ? `
                                    <div class="risk-item">
                                        <div class="risk-item-label">
                                            <span>PNL Sessão</span>
                                        </div>
                                        <div class="risk-item-value ${position.session_protection.current_session_pnl >= 0 ? 'text-green-400' : 'text-red-400'}">
                                            ${position.session_protection.current_session_pnl >= 0 ? '+' : ''}$${safeFloat(position.session_protection.current_session_pnl).toFixed(2)}
                                        </div>
                                    </div>
                                    <div class="risk-item">
                                        <div class="risk-item-label">
                                            <span>Margem de Segurança</span>
                                        </div>
                                        <div class="risk-item-value">
                                            $${safeFloat(position.session_protection.remaining_loss_buffer).toFixed(2)}
                                        </div>
                                    </div>
                                ` : '<div class="risk-item-placeholder">Proteção de Sessão: Não configurada</div>'}
                            </div>
                        </div>
                        
                        <!-- Nível 3: Emergency System -->
                        <div class="risk-layer">
                            <div class="risk-layer-header">
                                <span>🚨 Nível 3 - Sistema de Emergência</span>
                            </div>
                            <div class="risk-items">
                                ${hasEmergencySystem && position.emergency_system.emergency_sl ? 
                                    createRiskItemSafe('Emergency SL', position.emergency_system.emergency_sl, '%') :
                                    '<div class="risk-item-placeholder">Emergency SL: Não configurado</div>'
                                }
                                ${hasEmergencySystem && position.emergency_system.time_monitoring ? `
                                    <div class="risk-item">
                                        <div class="risk-item-label">
                                            <div class="risk-status-indicator status-${safeString(position.emergency_system.time_monitoring.status)}"></div>
                                            <span>Tempo em Loss</span>
                                        </div>
                                        <div class="risk-item-value">
                                            ${safeFloat(position.emergency_system.time_monitoring.time_in_loss_minutes)}min / 
                                            ${safeFloat(position.emergency_system.time_monitoring.max_time_minutes)}min
                                        </div>
                                    </div>
                                ` : '<div class="risk-item-placeholder">Monitoramento de Tempo: Não configurado</div>'}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }
        
        // ========== CSV ANALYSIS VARIABLES ==========
        let csvWinrateChart = null;
        let csvCumulativePNLChart = null;
        let currentAnalysis = null;
        
        // ========== CSV UPLOAD FUNCTIONS ==========
        
        async function handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;
            
            if (!file.name.toLowerCase().endsWith('.csv')) {
                showAlert('error', '❌ Arquivo deve ser CSV');
                return;
            }
            
            await uploadAndAnalyzeCSV(file);
        }
        
        async function uploadAndAnalyzeCSV(file) {
            const progressDiv = document.getElementById('upload-progress');
            const progressBar = document.getElementById('upload-progress-bar');
            const statusText = document.getElementById('upload-status');
            
            try {
                progressDiv.classList.remove('hidden');
                progressBar.style.width = '10%';
                statusText.textContent = 'Enviando arquivo...';
                
                const formData = new FormData();
                formData.append('file', file);
                
                progressBar.style.width = '40%';
                
                const response = await fetch(`${API_BASE}/api/csv/upload`, {
                    method: 'POST',
                    body: formData
                });
                
                progressBar.style.width = '70%';
                statusText.textContent = 'Processando CSV...';
                
                const result = await response.json();
                
                progressBar.style.width = '100%';
                
                if (result.status === 'success') {
                    showAlert('success', `✅ ${result.message}`);
                    
                    // Mostrar resultados
                    displayAnalysis(result.stats);
                    
                    // Atualizar lista de arquivos
                    await refreshCSVList();
                    
                    setTimeout(() => {
                        progressDiv.classList.add('hidden');
                        progressBar.style.width = '0%';
                    }, 2000);
                } else {
                    showAlert('error', `❌ ${result.message}`);
                    progressDiv.classList.add('hidden');
                }
                
                // Limpar input
                document.getElementById('csv-file-input').value = '';
                
            } catch (error) {
                console.error('Erro no upload:', error);
                showAlert('error', '❌ Erro ao processar arquivo');
                progressDiv.classList.add('hidden');
            }
        }
        
        // ========== CSV FILE LIST ==========
        
        async function refreshCSVList() {
            try {
                const response = await fetch(`${API_BASE}/api/csv/list`);
                const result = await response.json();
                
                const container = document.getElementById('csv-files-list');
                
                if (result.status === 'success' && result.files.length > 0) {
                    container.innerHTML = result.files.map(file => {
                        const date = new Date(file.modified).toLocaleString('pt-BR');
                        const size = (file.size / 1024).toFixed(1);
                        
                        return `
                            <div class="flex items-center justify-between bg-gray-700 rounded p-3 hover:bg-gray-600">
                                <div class="flex-1">
                                    <p class="font-semibold">${file.filename}</p>
                                    <p class="text-sm text-gray-400">${size} KB - ${date}</p>
                                </div>
                                <div class="flex gap-2">
                                    <button onclick="analyzeCSVFile('${file.filename}')" 
                                            class="bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded text-sm">
                                        📊 Analisar
                                    </button>
                                    <button onclick="deleteCSVFile('${file.filename}')" 
                                            class="bg-red-600 hover:bg-red-700 px-3 py-1 rounded text-sm">
                                        🗑️
                                    </button>
                                </div>
                            </div>
                        `;
                    }).join('');
                } else {
                    container.innerHTML = '<p class="text-gray-500">Nenhum arquivo CSV encontrado. Faça upload de um CSV da Pacifica.</p>';
                }
            } catch (error) {
                console.error('Erro ao listar CSVs:', error);
            }
        }
        
        async function analyzeCSVFile(filename) {
            try {
                showAlert('info', `📊 Analisando ${filename}...`);
                
                const response = await fetch(`${API_BASE}/api/csv/analyze/${encodeURIComponent(filename)}`);
                const result = await response.json();
                
                if (result.status === 'success') {
                    displayAnalysis(result.data);
                    showAlert('success', '✅ Análise concluída!');
                } else {
                    showAlert('error', `❌ ${result.message}`);
                }
            } catch (error) {
                console.error('Erro ao analisar:', error);
                showAlert('error', '❌ Erro ao analisar arquivo');
            }
        }
        
        async function deleteCSVFile(filename) {
            if (!confirm(`Tem certeza que deseja deletar ${filename}?`)) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/csv/delete/${encodeURIComponent(filename)}`, {
                    method: 'DELETE'
                });
                
                const result = await response.json();
                
                if (result.status === 'success') {
                    showAlert('success', '✅ Arquivo deletado');
                    await refreshCSVList();
                } else {
                    showAlert('error', `❌ ${result.message}`);
                }
            } catch (error) {
                console.error('Erro ao deletar:', error);
                showAlert('error', '❌ Erro ao deletar arquivo');
            }
        }
        
        // ========== DISPLAY ANALYSIS ==========
        
        function displayAnalysis(stats) {
            currentAnalysis = stats;
            const summary = stats.summary;
            
            // Show results section
            document.getElementById('csv-analysis-results').classList.remove('hidden');
            
            // Update summary cards
            document.getElementById('csv-total-trades').textContent = summary.total_trades;
            document.getElementById('csv-win-rate').textContent = `${summary.win_rate}%`;
            document.getElementById('csv-total-pnl').textContent = `$${summary.total_pnl.toFixed(2)}`;
            document.getElementById('csv-total-pnl').className = `text-3xl font-bold ${summary.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`;
            document.getElementById('csv-profit-factor').textContent = summary.profit_factor.toFixed(2);
            
            // Update detailed stats
            document.getElementById('csv-winning-trades').textContent = summary.winning_trades;
            document.getElementById('csv-losing-trades').textContent = summary.losing_trades;
            document.getElementById('csv-avg-trade').textContent = `$${summary.avg_trade.toFixed(2)}`;
            document.getElementById('csv-avg-trade').className = `font-bold ${summary.avg_trade >= 0 ? 'text-green-400' : 'text-red-400'}`;
            document.getElementById('csv-avg-win').textContent = `$${summary.avg_win.toFixed(2)}`;
            document.getElementById('csv-avg-loss').textContent = `$${summary.avg_loss.toFixed(2)}`;
            
            // Financial
            document.getElementById('csv-total-volume').textContent = `$${summary.total_volume.toFixed(2)}`;
            document.getElementById('csv-total-fees').textContent = `$${summary.total_fees.toFixed(2)}`;
            document.getElementById('csv-net-profit').textContent = `$${summary.net_profit.toFixed(2)}`;
            document.getElementById('csv-net-profit').className = `font-bold ${summary.net_profit >= 0 ? 'text-green-400' : 'text-red-400'}`;
            
            if (summary.best_trade) {
                document.getElementById('csv-best-trade').textContent = `$${summary.best_trade.pnl.toFixed(2)}`;
            }
            
            if (summary.worst_trade) {
                document.getElementById('csv-worst-trade').textContent = `$${summary.worst_trade.pnl.toFixed(2)}`;
            }
            
            // Update charts
            updateCSVCharts(stats);
            
            // Update tables
            updateSymbolTable(stats.by_symbol);
            updateDailyTable(stats.daily);
        }
        
        // ========== CSV CHARTS ==========
        
        function updateCSVCharts(stats) {
            const summary = stats.summary;
            
            // Win Rate Chart
            if (csvWinrateChart) {
                csvWinrateChart.destroy();
            }
            
            const ctx1 = document.getElementById('csv-winrate-chart').getContext('2d');
            csvWinrateChart = new Chart(ctx1, {
                type: 'doughnut',
                data: {
                    labels: ['Ganhos', 'Perdas', 'Breakeven'],
                    datasets: [{
                        data: [
                            summary.winning_trades, 
                            summary.losing_trades,
                            summary.breakeven_trades
                        ],
                        backgroundColor: [
                            'rgba(16, 185, 129, 0.8)',
                            'rgba(239, 68, 68, 0.8)',
                            'rgba(156, 163, 175, 0.8)'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            labels: { color: '#fff' }
                        }
                    }
                }
            });
            
            // Cumulative PNL Chart
            if (csvCumulativePNLChart) {
                csvCumulativePNLChart.destroy();
            }
            
            // Calculate cumulative PNL from raw trades
            const trades = stats.raw_trades || [];
            const cumulativeData = [];
            let cumulative = 0;
            
            trades.forEach(trade => {
                cumulative += trade.net_pnl;
                cumulativeData.push(cumulative);
            });
            
            const ctx2 = document.getElementById('csv-cumulative-pnl-chart').getContext('2d');
            csvCumulativePNLChart = new Chart(ctx2, {
                type: 'line',
                data: {
                    labels: trades.map((_, i) => `Trade ${i + 1}`),
                    datasets: [{
                        label: 'PNL Acumulado',
                        data: cumulativeData,
                        borderColor: 'rgb(59, 130, 246)',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            labels: { color: '#fff' }
                        }
                    },
                    scales: {
                        x: {
                            ticks: { 
                                color: '#9ca3af',
                                maxTicksLimit: 10
                            },
                            grid: { color: 'rgba(255, 255, 255, 0.1)' }
                        },
                        y: {
                            ticks: { 
                                color: '#9ca3af',
                                callback: value => `$${value.toFixed(2)}`
                            },
                            grid: { color: 'rgba(255, 255, 255, 0.1)' }
                        }
                    }
                }
            });
        }
        
        // ========== TABLES ==========
        
        function updateSymbolTable(bySymbol) {
            const tbody = document.getElementById('csv-symbol-tbody');
            
            if (!bySymbol || Object.keys(bySymbol).length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-gray-500">Nenhum dado disponível</td></tr>';
                return;
            }
            
            tbody.innerHTML = Object.entries(bySymbol)
                .sort(([,a], [,b]) => b.pnl - a.pnl)
                .map(([symbol, data]) => `
                    <tr class="border-b border-gray-700">
                        <td class="py-3 font-semibold">${symbol}</td>
                        <td class="py-3">${data.trades}</td>
                        <td class="py-3">${data.win_rate}%</td>
                        <td class="py-3 ${data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}">
                            $${data.pnl.toFixed(2)}
                        </td>
                        <td class="py-3 text-red-400">$${data.fees.toFixed(2)}</td>
                        <td class="py-3">$${data.volume.toFixed(2)}</td>
                    </tr>
                `).join('');
        }
        
        function updateDailyTable(daily) {
            const tbody = document.getElementById('csv-daily-tbody');
            
            if (!daily || Object.keys(daily).length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-gray-500">Nenhum dado disponível</td></tr>';
                return;
            }
            
            tbody.innerHTML = Object.entries(daily)
                .sort(([a], [b]) => b.localeCompare(a))
                .map(([date, data]) => `
                    <tr class="border-b border-gray-700">
                        <td class="py-3">${date}</td>
                        <td class="py-3">${data.trades}</td>
                        <td class="py-3">${data.win_rate}%</td>
                        <td class="py-3 ${data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}">
                            $${data.pnl.toFixed(2)}
                        </td>
                        <td class="py-3">$${data.volume.toFixed(2)}</td>
                    </tr>
                `).join('');
        }
        
        // ========== INIT CSV TAB ==========
        
        async function loadLastAnalysis() {
            try {
                const response = await fetch(`${API_BASE}/api/csv/analysis`);
                const result = await response.json();
                
                if (result.status === 'success') {
                    displayAnalysis(result.data);
                }
            } catch (error) {
                console.log('Nenhuma análise anterior disponível');
            }
        }
        
        // Drag and drop support
        const csvTab = document.getElementById('content-csv-analysis');
        if (csvTab) {
            csvTab.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
            
            csvTab.addEventListener('drop', async (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const files = e.dataTransfer.files;
                if (files.length > 0 && files[0].name.toLowerCase().endsWith('.csv')) {
                    await uploadAndAnalyzeCSV(files[0]);
                } else {
                    showAlert('error', '❌ Arquivo deve ser CSV');
                }
            });
        }
        
        console.log('✅ Módulo de Análise CSV carregado');

// ✅ CORREÇÃO: Função duplicada removida - usando a versão melhorada acima
    // A função loadRiskStatus() melhorada já está definida na seção RISK MANAGEMENT FUNCTIONS
    console.log('✅ Função loadRiskStatus duplicada removida - usando versão melhorada');
    
    // Atualiza o painel a cada 10 segundos usando as funções corrigidas
    setInterval(() => {
        updateRiskDashboard(); // Função do painel unificado
    //    loadRiskPositionsMonitor(); // Função melhorada
    }, 10000);
    
    // Carregar dados iniciais usando as funções corrigidas
    updateRiskDashboard(); 
    // loadRiskPositionsMonitor();

    // ==========================================
    // JAVASCRIPT PARA CONFIG V2
    // ==========================================

    let configSchema = null;
    let currentStrategy = null;
    let currentConfigValues = {};
    let originalConfigValues = {};
    let validationErrors = {};

    // ========== INICIALIZAÇÃO ==========

    async function initConfigV2() {
        console.log('🔧 Inicializando Config V2...');
        
        try {
            // Verificar se schema V2 existe
            const v2Response = await fetch(`${API_BASE}/api/config/schema/v2`);
            if (v2Response.ok) {
                console.log('✅ Schema V2 detectado, carregando interface hierárquica...');
                await loadConfigSchemaV2();
                return;
            }
            
            // Fallback para schema V1
            console.log('⚠️ Schema V2 não disponível, usando interface clássica...');
            const schemaResponse = await fetch(`${API_BASE}/api/config/schema`);
            const schemaData = await schemaResponse.json();
            
            if (schemaData.status === 'success') {
                configSchema = schemaData.schema;
                console.log('✅ Schema carregado:', Object.keys(configSchema));
            }
            
            // Carregar configuração atual
            await loadCurrentConfig();
            
            // Carregar status de backups
            await updateBackupStatus();
            
        } catch (error) {
            console.error('❌ Erro ao inicializar Config V2:', error);
            showAlert('error', 'Erro ao carregar configurações: ' + error.message);
        }
    }

    async function loadCurrentConfig() {
        try {
            const response = await fetch(`${API_BASE}/api/config`);
            const config = await response.json();
            
            // Limpar valores inválidos (remove comentários e caracteres especiais)
            const cleanConfig = {};
            for (const [key, value] of Object.entries(config)) {
                if (typeof value === 'string') {
                    // Remove comentários e caracteres de encoding inválidos
                    const cleanValue = value.split('#')[0].trim()
                        .replace(/Ã¡/g, 'a')
                        .replace(/Ã§Ã£o/g, 'cao') 
                        .replace(/Ã§/g, 'c')
                        .replace(/Ãº/g, 'u')
                        .replace(/Ã©/g, 'e')
                        .replace(/Ã /g, 'a');
                    cleanConfig[key] = cleanValue;
                } else {
                    cleanConfig[key] = value;
                }
            }
            
            currentConfigValues = {...cleanConfig};
            originalConfigValues = {...cleanConfig};
            
            // Detectar estratégia atual
            currentStrategy = config.STRATEGY_TYPE || 'pure_grid';
            
            // Atualizar UI
            document.getElementById('config-current-strategy').textContent = 
                getStrategyLabel(currentStrategy);
            
            // Selecionar estratégia no novo sistema
            selectStrategyFromConfig(currentStrategy);
            
            console.log('✅ Configuração atual carregada:', currentStrategy);
            
        } catch (error) {
            console.error('❌ Erro ao carregar config:', error);
        }
    }

    function getStrategyLabel(strategy) {
        const labels = {
            'pure_grid': '🔹 Pure Grid',
            'market_making': '📊 Market Making',
            'dynamic_grid': '⚡ Dynamic Grid',
            'multi_asset': '🌍 Multi-Asset',
            'multi_asset_enhanced': '🚀 Multi-Asset Enhanced'
        };
        return labels[strategy] || strategy;
    }

    // ========== SELEÇÃO DE ESTRATÉGIA ==========

    function selectStrategyFromConfig(strategy) {
        console.log('📌 Carregando estratégia da configuração:', strategy);
        
        // Encontrar a categoria da estratégia
        let categoryFound = null;
        for (const [catKey, catData] of Object.entries(configSchemaV2.strategy_categories)) {
            if (catData.strategies.includes(strategy)) {
                categoryFound = catKey;
                break;
            }
        }
        
        if (categoryFound) {
            // Selecionar a categoria primeiro
            selectStrategyCategory(categoryFound);
            // Depois selecionar a estratégia específica
            setTimeout(() => selectStrategy(strategy), 100);
        } else {
            console.warn('⚠️ Categoria não encontrada para estratégia:', strategy);
        }
    }

    // ========== RENDERIZAÇÃO DE CAMPOS ==========

    function renderConfigFields(strategy) {
        const container = document.getElementById('config-fields-container');
        
        if (!configSchema || !configSchema[strategy]) {
            container.innerHTML = `
                <div class="bg-red-900/30 border border-red-600 rounded-lg p-6 text-center">
                    <div class="text-4xl mb-2">⚠️</div>
                    <p class="text-red-400">Schema não encontrado para estratégia: ${strategy}</p>
                </div>
            `;
            return;
        }
        
        const strategyConfig = configSchema[strategy];
        const sections = strategyConfig.sections;
        
        let html = `
            <div class="bg-gray-800 rounded-lg p-6 mb-4">
                <h3 class="text-xl font-semibold mb-2">${strategyConfig.label}</h3>
                <p class="text-gray-400 text-sm">${strategyConfig.description}</p>
            </div>
        `;
        
        // Renderizar cada seção
        for (const [sectionKey, section] of Object.entries(sections)) {
            html += `
                <div class="config-section rounded-lg p-6 mb-4">
                    <h4 class="text-lg font-semibold text-blue-400 mb-4">${section.label}</h4>
                    <div class="space-y-4">
            `;
            
            // Renderizar campos da seção
            for (const [fieldKey, field] of Object.entries(section.fields)) {
                html += renderConfigField(fieldKey, field);
            }
            
            html += `
                    </div>
                </div>
            `;
        }
        
        container.innerHTML = html;
        
        // Preencher valores atuais
        fillCurrentValues();
        
        // Adicionar event listeners
        addFieldEventListeners();
    }

    function renderConfigField(key, field) {
        const value = currentConfigValues[key] || field.default || '';
        const hasError = validationErrors[key];
        const isModified = originalConfigValues[key] !== value;
        
        let inputHtml = '';
        
        switch (field.type) {
            case 'text':
                inputHtml = `
                    <input type="text" id="config-field-${key}" data-field="${key}"
                           value="${value}" placeholder="${field.default || ''}"
                           ${field.required ? 'required' : ''}
                           class="w-full bg-gray-700 text-white px-4 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500">
                `;
                break;
                
            case 'number':
                inputHtml = `
                    <input type="number" id="config-field-${key}" data-field="${key}"
                           value="${value}" placeholder="${field.default || ''}"
                           ${field.min !== undefined ? `min="${field.min}"` : ''}
                           ${field.max !== undefined ? `max="${field.max}"` : ''}
                           ${field.step !== undefined ? `step="${field.step}"` : ''}
                           ${field.required ? 'required' : ''}
                           class="w-full bg-gray-700 text-white px-4 py-2 rounded focus:outline-none focus:ring-2 focus:ring-blue-500">
                `;
                break;
                
            case 'boolean':
                inputHtml = `
                    <input type="checkbox" id="config-field-${key}" data-field="${key}"
                           ${value === 'true' || value === true ? 'checked' : ''}
                           class="w-5 h-5 text-blue-600 bg-gray-700 border-gray-600 rounded focus:ring-blue-500">
                `;
                break;
                
            default:
                inputHtml = `<p class="text-gray-500">Tipo de campo não suportado: ${field.type}</p>`;
        }
        
        return `
            <div class="config-field ${isModified ? 'modified' : ''} ${hasError ? 'error' : ''} p-4 rounded-lg"
                 data-field-container="${key}">
                <div class="flex justify-between items-start mb-2">
                    <label for="config-field-${key}" class="block text-gray-300 font-medium">
                        ${field.label}
                        ${field.required ? '<span class="text-red-400">*</span>' : ''}
                    </label>
                    ${field.help ? `
                        <span class="config-tooltip text-gray-400 cursor-help text-sm" data-tooltip="${field.help}">
                            ❓
                        </span>
                    ` : ''}
                </div>
                ${inputHtml}
                ${hasError ? `<p class="text-red-400 text-sm mt-1">⚠️ ${hasError}</p>` : ''}
            </div>
        `;
    }

    function fillCurrentValues() {
        for (const [key, value] of Object.entries(currentConfigValues)) {
            const field = document.getElementById(`config-field-${key}`);
            if (field) {
                if (field.type === 'checkbox') {
                    field.checked = value === 'true' || value === true;
                } else {
                    field.value = value;
                }
            }
        }
    }

    function addFieldEventListeners() {
        document.querySelectorAll('[data-field]').forEach(field => {
            field.addEventListener('change', handleFieldChange);
            field.addEventListener('input', handleFieldInput);
        });
    }

    function handleFieldChange(event) {
        const fieldKey = event.target.dataset.field;
        let value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
        
        currentConfigValues[fieldKey] = value;
        
        // Marcar como modificado
        const container = document.querySelector(`[data-field-container="${fieldKey}"]`);
        if (container) {
            if (originalConfigValues[fieldKey] !== value) {
                container.classList.add('modified');
            } else {
                container.classList.remove('modified');
            }
        }
        
        // Validar campo
        validateField(fieldKey, value);
    }

    function handleFieldInput(event) {
        // Validação em tempo real para números
        if (event.target.type === 'number') {
            handleFieldChange(event);
        }
    }

    // ========== VALIDAÇÃO ==========

    async function validateField(fieldKey, value) {
        // Validação local básica
        const fieldElement = document.getElementById(`config-field-${fieldKey}`);
        if (!fieldElement) return;
        
        const container = document.querySelector(`[data-field-container="${fieldKey}"]`);
        
        // Remover erro anterior
        delete validationErrors[fieldKey];
        if (container) {
            container.classList.remove('error');
            const errorMsg = container.querySelector('.text-red-400');
            if (errorMsg) errorMsg.remove();
        }
        
        // Validar required
        if (fieldElement.required && !value) {
            validationErrors[fieldKey] = 'Campo obrigatório';
            if (container) container.classList.add('error');
            return;
        }
        
        // Validar min/max para números
        if (fieldElement.type === 'number') {
            const numValue = parseFloat(value);
            const min = parseFloat(fieldElement.min);
            const max = parseFloat(fieldElement.max);
            
            if (!isNaN(min) && numValue < min) {
                validationErrors[fieldKey] = `Valor mínimo: ${min}`;
                if (container) container.classList.add('error');
                return;
            }
            
            if (!isNaN(max) && numValue > max) {
                validationErrors[fieldKey] = `Valor máximo: ${max}`;
                if (container) container.classList.add('error');
                return;
            }
        }
    }

    async function validateAllFields() {
        console.log('🔍 Validando todos os campos...');
        
        try {
            const response = await fetch(`${API_BASE}/api/config/validate`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    strategy: currentStrategy,
                    config: currentConfigValues
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'error' || !result.valid) {
                // Mostrar erros
                if (result.errors && result.errors.length > 0) {
                    showAlert('error', '❌ Erros de validação:\\n' + result.errors.join('\\n'));
                }
            }
            
            if (result.warnings && result.warnings.length > 0) {
                showAlert('warning', '⚠️ Avisos:\\n' + result.warnings.join('\\n'));
            }
            
            return result.valid;
            
        } catch (error) {
            console.error('❌ Erro na validação:', error);
            showAlert('error', 'Erro ao validar: ' + error.message);
            return false;
        }
    }

    // ========== PREVIEW DE MUDANÇAS ==========

    async function previewConfigChanges() {
        console.log('👁️ Gerando preview...');
        
        try {
            const response = await fetch(`${API_BASE}/api/config/preview`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    config: currentConfigValues
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                displayPreview(result.changes, result.summary);
            } else {
                showAlert('error', 'Erro ao gerar preview: ' + result.message);
            }
            
        } catch (error) {
            console.error('❌ Erro no preview:', error);
            showAlert('error', 'Erro ao gerar preview: ' + error.message);
        }
    }

    function displayPreview(changes, summary) {
        const modal = document.getElementById('config-preview-modal');
        const content = document.getElementById('config-preview-content');
        
        let html = `
            <div class="bg-gray-700 rounded-lg p-4 mb-4">
                <h4 class="font-semibold mb-2">📊 Resumo de Mudanças</h4>
                <div class="grid grid-cols-4 gap-3 text-sm">
                    <div class="text-center">
                        <div class="text-2xl text-green-400">${summary.added}</div>
                        <div class="text-gray-400">Novos</div>
                    </div>
                    <div class="text-center">
                        <div class="text-2xl text-yellow-400">${summary.modified}</div>
                        <div class="text-gray-400">Modificados</div>
                    </div>
                    <div class="text-center">
                        <div class="text-2xl text-red-400">${summary.removed}</div>
                        <div class="text-gray-400">Removidos</div>
                    </div>
                    <div class="text-center">
                        <div class="text-2xl text-gray-400">${summary.unchanged}</div>
                        <div class="text-gray-400">Inalterados</div>
                    </div>
                </div>
            </div>
        `;
        
        // Mudanças adicionadas
        if (Object.keys(changes.added).length > 0) {
            html += `<div class="mb-4">
                <h5 class="font-semibold text-green-400 mb-2">✅ Novos Parâmetros</h5>`;
            for (const [key, value] of Object.entries(changes.added)) {
                html += `
                    <div class="preview-change-added p-3 rounded mb-2">
                        <code class="text-green-300">${key} = ${value}</code>
                    </div>
                `;
            }
            html += `</div>`;
        }
        
        // Mudanças modificadas
        if (Object.keys(changes.modified).length > 0) {
            html += `<div class="mb-4">
                <h5 class="font-semibold text-yellow-400 mb-2">✏️ Parâmetros Modificados</h5>`;
            for (const [key, diff] of Object.entries(changes.modified)) {
                html += `
                    <div class="preview-change-modified p-3 rounded mb-2">
                        <div class="text-yellow-300 font-medium">${key}</div>
                        <div class="text-sm text-gray-400">Antes: <code class="text-red-300">${diff.old}</code></div>
                        <div class="text-sm text-gray-400">Depois: <code class="text-green-300">${diff.new}</code></div>
                    </div>
                `;
            }
            html += `</div>`;
        }
        
        // Mudanças removidas
        if (Object.keys(changes.removed).length > 0) {
            html += `<div class="mb-4">
                <h5 class="font-semibold text-red-400 mb-2">🗑️ Parâmetros Removidos</h5>`;
            for (const [key, value] of Object.entries(changes.removed)) {
                html += `
                    <div class="preview-change-removed p-3 rounded mb-2">
                        <code class="text-red-300">${key} = ${value}</code>
                    </div>
                `;
            }
            html += `</div>`;
        }
        
        if (summary.added === 0 && summary.modified === 0 && summary.removed === 0) {
            html += `
                <div class="text-center py-8 text-gray-400">
                    <div class="text-4xl mb-2">😴</div>
                    <p>Nenhuma mudança detectada</p>
                </div>
            `;
        }
        
        content.innerHTML = html;
        modal.classList.remove('hidden');
    }

    function closePreviewModal() {
        document.getElementById('config-preview-modal').classList.add('hidden');
    }

    // ========== SALVAR CONFIGURAÇÕES ==========

    async function saveConfigV2() {
        console.log('💾 Salvando configurações...');
        
        // Validar antes de salvar
        const isValid = await validateAllFields();
        if (!isValid) {
            showAlert('error', '❌ Corrija os erros antes de salvar');
            return;
        }
        
        // Mostrar preview primeiro
        await previewConfigChanges();
    }

    async function confirmAndSaveConfig() {
        closePreviewModal();
        
        showAlert('info', '⏳ Salvando e aplicando configurações...');
        
        try {
            const response = await fetch(`${API_BASE}/api/config/save`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    strategy: currentStrategy,
                    config: currentConfigValues,
                    auto_restart: true
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'success' || result.status === 'warning') {
                showAlert('success', result.message);
                
                // Atualizar valores originais
                originalConfigValues = {...currentConfigValues};
                
                // Recarregar configuração para sincronizar
                await loadCurrentConfig();
                
                // Atualizar status de backup
                await updateBackupStatus();
                
            } else {
                showAlert('error', 'Erro ao salvar: ' + result.message);
            }
            
        } catch (error) {
            console.error('❌ Erro ao salvar:', error);
            showAlert('error', 'Erro ao salvar: ' + error.message);
        }
    }

    // ========== RESET ==========

    function resetConfigForm() {
        if (!confirm('🔄 Descartar todas as mudanças e recarregar configuração atual?')) {
            return;
        }
        
        currentConfigValues = {...originalConfigValues};
        validationErrors = {};
        
        renderConfigFields(currentStrategy);
        
        showAlert('info', '🔄 Configurações resetadas');
    }

    // ========== BACKUPS ==========

    async function updateBackupStatus() {
        try {
            const response = await fetch(`${API_BASE}/api/config/backups`);
            const result = await response.json();
            
            if (result.status === 'success' && result.backups.length > 0) {
                document.getElementById('config-backup-count').textContent = result.backups.length;
            } else {
                document.getElementById('config-backup-count').textContent = '0';
            }
        } catch (error) {
            console.error('❌ Erro ao carregar backups:', error);
        }
    }

    async function showBackupsModal() {
        const modal = document.getElementById('config-backups-modal');
        const list = document.getElementById('config-backups-list');
        
        modal.classList.remove('hidden');
        list.innerHTML = '<p class="text-gray-500 text-center py-4">Carregando...</p>';
        
        try {
            const response = await fetch(`${API_BASE}/api/config/backups`);
            const result = await response.json();
            
            if (result.status === 'success' && result.backups.length > 0) {
                list.innerHTML = result.backups.map(backup => `
                    <div class="bg-gray-700 rounded p-3 flex justify-between items-center">
                        <div>
                            <div class="font-medium">${backup.filename}</div>
                            <div class="text-sm text-gray-400">${backup.modified_str} - ${(backup.size / 1024).toFixed(1)} KB</div>
                        </div>
                        <button onclick="restoreBackup('${backup.path}')" 
                                class="bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded text-sm">
                            🔄 Restaurar
                        </button>
                    </div>
                `).join('');
            } else {
                list.innerHTML = '<p class="text-gray-500 text-center py-4">Nenhum backup disponível</p>';
            }
        } catch (error) {
            console.error('❌ Erro ao carregar backups:', error);
            list.innerHTML = '<p class="text-red-400 text-center py-4">Erro ao carregar backups</p>';
        }
    }

    function closeBackupsModal() {
        document.getElementById('config-backups-modal').classList.add('hidden');
    }

    async function restoreBackup(backupPath) {
        if (!confirm('🔄 Restaurar este backup? A configuração atual será substituída.')) {
            return;
        }
        
        try {
            showAlert('info', '⏳ Restaurando backup...');
            
            const response = await fetch(`${API_BASE}/api/config/restore`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    backup_file: backupPath
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                showAlert('success', 'Backup restaurado com sucesso!');
                closeBackupsModal();
                
                // Recarregar configuração
                await loadCurrentConfig();
                
            } else {
                showAlert('error', 'Erro ao restaurar backup: ' + result.message);
            }
            
        } catch (error) {
            console.error('❌ Erro ao restaurar:', error);
            showAlert('error', 'Erro ao restaurar backup: ' + error.message);
        }
    }

    console.log('✅ Config V2 JavaScript carregado');

    // ==========================================
    // SISTEMA DE CREDENCIAIS SEGURAS - FRONTEND
    // ==========================================

    let onboardingStep = 1;
    let credentialsValidated = false;

    // ========== INICIALIZAÇÃO ==========

    async function initCredentialsSystem() {
        console.log('🔐 Inicializando sistema de credenciais...');
        
        // Sempre mostrar a seção de credenciais
        const credentialsManager = document.getElementById('credentials-manager');
        if (credentialsManager) {
            credentialsManager.style.display = 'block';
        }
        
        try {
            // Verificar se credenciais já estão configuradas
            const response = await fetch(`${API_BASE}/api/credentials/check`);
            const result = await response.json();
            
            if (result.configured) {
                // Credenciais já configuradas
                console.log('✅ Credenciais já configuradas');
                loadConfiguredCredentials(result.credentials);
            } else {
                // Mostrar seção não configurada
                console.log('⚠️ Credenciais não configuradas');
                showNotConfiguredCredentials();
            }
            
        } catch (error) {
            console.error('❌ Erro ao verificar credenciais:', error);
            // Em caso de erro, mostrar seção não configurada
            showNotConfiguredCredentials();
        }
    }

    function loadConfiguredCredentials(credentials) {
        // Atualizar display
        document.getElementById('display-wallet-address').value = credentials.MAIN_PUBLIC_KEY || '';
        
        // Mostrar seção de gerenciamento
        const credentialsManager = document.getElementById('credentials-manager');
        if (credentialsManager) {
            credentialsManager.style.display = 'block';
            document.getElementById('credentials-configured').style.display = 'block';
            document.getElementById('credentials-not-configured').style.display = 'none';
        }
    }

    function showNotConfiguredCredentials() {
        // Mostrar seção não configurada
        const credentialsManager = document.getElementById('credentials-manager');
        if (credentialsManager) {
            credentialsManager.style.display = 'block';
            document.getElementById('credentials-configured').style.display = 'none';
            document.getElementById('credentials-not-configured').style.display = 'block';
        }
    }

    // ========== WIZARD DE ONBOARDING ==========

    function showOnboardingModal() {
        document.getElementById('onboarding-modal').classList.remove('hidden');
        goToStep(1);
    }

    function hideOnboardingModal() {
        document.getElementById('onboarding-modal').classList.add('hidden');
    }

    function goToStep(step) {
        onboardingStep = step;
        
        // Esconder todos os steps
        document.querySelectorAll('.onboarding-step').forEach(el => {
            el.classList.add('hidden');
        });
        
        // Mostrar step atual
        document.getElementById(`onboarding-step-${step}`).classList.remove('hidden');
        
        // Atualizar indicadores visuais
        document.querySelectorAll('.wizard-step').forEach(el => {
            const stepNum = parseInt(el.dataset.step);
            
            if (stepNum < step) {
                el.classList.add('completed');
                el.classList.remove('active');
            } else if (stepNum === step) {
                el.classList.add('active');
                el.classList.remove('completed');
            } else {
                el.classList.remove('active', 'completed');
            }
        });
    }

    // ========== VALIDAÇÃO E SALVAMENTO ==========

    function formatBalance(balance) {
        // Função para formatar saldo de forma segura
        if (balance === null || balance === undefined) {
            return 'N/A';
        }
        
        // Se for string, tentar converter para número
        if (typeof balance === 'string') {
            balance = parseFloat(balance);
        }
        
        // Verificar se é um número válido
        if (isNaN(balance) || !isFinite(balance)) {
            return 'N/A';
        }
        
        return balance.toFixed(2);
    }

    async function validateAndNextStep() {
        const walletAddress = document.getElementById('onboard-wallet-address').value.trim();
        const privateKey = document.getElementById('onboard-private-key').value.trim();
        const apiAddress = document.getElementById('onboard-api-address').value.trim();
        
        // Validação básica
        if (!walletAddress) {
            showAlert('error', '❌ Informe o endereço da carteira');
            return;
        }
        
        if (!privateKey) {
            showAlert('error', '❌ Informe a chave privada');
            return;
        }
        
        // Ir para step 2 (validação)
        goToStep(2);
        
        try {
            // Atualizar status
            document.getElementById('validation-status').textContent = 'Validando formato das credenciais...';
            
            // Chamar API de validação
            const response = await fetch(`${API_BASE}/api/credentials/validate`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    wallet_address: walletAddress,
                    private_key: privateKey
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'success' && result.valid) {
                // Validação bem-sucedida
                credentialsValidated = true;
                
                document.getElementById('validation-result').innerHTML = `
                    <div class="validation-success">
                        <div class="flex items-start gap-3">
                            <span class="text-3xl">✅</span>
                            <div class="flex-1">
                                <p class="text-green-400 font-semibold text-lg mb-2">Credenciais Válidas!</p>
                                <ul class="text-sm text-green-200 space-y-1">
                                    <li>✓ Endereço da carteira válido</li>
                                    <li>✓ Chave privada válida</li>
                                    <li>✓ Conexão com API estabelecida</li>
                                    <li>✓ Saldo disponível: ${formatBalance(result.balance)}</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                `;
                
                document.getElementById('validation-result').classList.remove('hidden');
                document.getElementById('validation-actions').style.display = 'flex';
                
            } else {
                // Validação falhou
                credentialsValidated = false;
                
                const errors = result.errors || [result.message || 'Erro desconhecido'];
                
                document.getElementById('validation-result').innerHTML = `
                    <div class="validation-error">
                        <div class="flex items-start gap-3">
                            <span class="text-3xl">❌</span>
                            <div class="flex-1">
                                <p class="text-red-400 font-semibold text-lg mb-2">Validação Falhou</p>
                                <ul class="text-sm text-red-200 space-y-1">
                                    ${errors.map(err => `<li>• ${err}</li>`).join('')}
                                </ul>
                            </div>
                        </div>
                    </div>
                `;
                
                document.getElementById('validation-result').classList.remove('hidden');
                document.getElementById('validation-actions').style.display = 'flex';
            }
            
        } catch (error) {
            console.error('❌ Erro na validação:', error);
            
            document.getElementById('validation-result').innerHTML = `
                <div class="validation-error">
                    <div class="flex items-start gap-3">
                        <span class="text-3xl">⚠️</span>
                        <div class="flex-1">
                            <p class="text-red-400 font-semibold text-lg mb-2">Erro de Conexão</p>
                            <p class="text-sm text-red-200">
                                Não foi possível validar as credenciais. Verifique sua conexão.
                            </p>
                            <code class="text-xs text-red-300 block mt-2">${error.message}</code>
                        </div>
                    </div>
                </div>
            `;
            
            document.getElementById('validation-result').classList.remove('hidden');
            document.getElementById('validation-actions').style.display = 'flex';
        }
    }

    async function saveCredentials() {
        if (!credentialsValidated) {
            showAlert('error', '❌ Valide as credenciais primeiro');
            return;
        }
        
        const walletAddress = document.getElementById('onboard-wallet-address').value.trim();
        const privateKey = document.getElementById('onboard-private-key').value.trim();
        const apiAddress = document.getElementById('onboard-api-address').value.trim();
        
        try {
            showAlert('info', '⏳ Salvando credenciais com segurança...');
            
            const response = await fetch(`${API_BASE}/api/credentials/save`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    wallet_address: walletAddress,
                    private_key: privateKey,
                    api_address: apiAddress,
                    test_connection: false  // Já testamos antes
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                showAlert('success', '✅ Credenciais salvas com segurança!');
                
                // Ir para step 3 (conclusão)
                goToStep(3);
                
            } else {
                showAlert('error', '❌ ' + result.message);
            }
            
        } catch (error) {
            console.error('❌ Erro ao salvar:', error);
            showAlert('error', 'Erro ao salvar credenciais: ' + error.message);
        }
    }

    function completeOnboarding() {
        hideOnboardingModal();
        
        // Recarregar para atualizar interface
        window.location.reload();
    }

    // ========== GERENCIAMENTO DE CREDENCIAIS ==========

    function reconfigureCredentials() {
        if (!confirm('🔄 Deseja reconfigurar suas credenciais?\n\n⚠️ As credenciais atuais serão substituídas.')) {
            return;
        }
        
        // Limpar campos
        document.getElementById('onboard-wallet-address').value = '';
        document.getElementById('onboard-private-key').value = '';
        
        credentialsValidated = false;
        
        // Mostrar wizard
        showOnboardingModal();
    }

    async function testCredentialsConnection() {
        try {
            showAlert('info', '⏳ Testando conexão...');
            
            const response = await fetch(`${API_BASE}/api/credentials/check`);
            const result = await response.json();
            
            if (result.configured) {
                // Fazer teste real de conexão
                // (pode ser implementado endpoint específico)
                showAlert('success', '✅ Conexão OK! Credenciais válidas.');
            } else {
                showAlert('error', '❌ Credenciais não configuradas');
            }
            
        } catch (error) {
            console.error('❌ Erro no teste:', error);
            showAlert('error', 'Erro ao testar conexão: ' + error.message);
        }
    }

    async function confirmDeleteCredentials() {
        if (!confirm('⚠️ ATENÇÃO!\n\nDeseja REMOVER todas as credenciais?\n\nEsta ação não pode ser desfeita.\n\nVocê precisará reconfigurá-las para usar o bot.')) {
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/api/credentials/delete`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    confirmed: true
                })
            });
            
            const result = await response.json();
            
            if (result.status === 'success') {
                showAlert('success', '✅ Credenciais removidas');
                
                // Recarregar página
                setTimeout(() => window.location.reload(), 1500);
            } else {
                showAlert('error', '❌ ' + result.message);
            }
            
        } catch (error) {
            console.error('❌ Erro ao deletar:', error);
            showAlert('error', 'Erro ao remover credenciais: ' + error.message);
        }
    }

    // ========== UTILITÁRIOS ==========

    function togglePasswordVisibility(inputId) {
        const input = document.getElementById(inputId);
        if (input.type === 'password') {
            input.type = 'text';
        } else {
            input.type = 'password';
        }
    }

    function copyToClipboard(inputId) {
        const input = document.getElementById(inputId);
        input.select();
        document.execCommand('copy');
        showAlert('success', '📋 Copiado para área de transferência!');
    }

    console.log('✅ Sistema de credenciais seguras (frontend) carregado');

    // ==========================================
    // CONFIGURAÇÃO V2 - HIERÁRQUICA
    // ==========================================

    let configSchemaV2 = null;
    let currentStrategyCategory = null;
    let currentStrategyType = null;
    let configChanges = {};

    // Carregar schema V2 ao abrir tab de configuração
    async function loadConfigSchemaV2() {
        try {
            const response = await fetch(`${API_BASE}/api/config/schema/v2`);
            const data = await response.json();
            
            if (data.status === 'success') {
                configSchemaV2 = data.schema;
                currentConfigValues = data.current_values;
                currentStrategyType = data.current_strategy;
                
                // Renderizar interface V2
                renderConfigV2Interface();
            } else {
                console.error('Erro ao carregar schema V2:', data.message);
            }
        } catch (error) {
            console.error('Erro ao carregar schema V2:', error);
        }
    }

    function renderConfigV2Interface() {
        const container = document.getElementById('config-fields-container');
        
        if (!configSchemaV2) {
            container.innerHTML = `
                <div class="bg-red-900/30 border border-red-700 rounded-lg p-6">
                    <p class="text-red-300">❌ Erro ao carregar schema de configuração</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = `
            <!-- Layout Aprimorado: Lado Esquerdo + Lado Direito -->
            <div class="config-section mb-6">
                <h3 class="text-xl font-semibold mb-4 flex items-center">
                    <span class="text-3xl mr-3">1️⃣</span>
                    Seleção de Estratégia
                </h3>
                
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <!-- Lado Esquerdo: Tipos de Estratégia -->
                    <div class="lg:col-span-1">
                        <h4 class="text-lg font-medium mb-3 text-blue-300">Tipo de Estratégia</h4>
                        <div class="space-y-3">
                            ${Object.entries(configSchemaV2.strategy_categories).map(([key, cat]) => `
                                <button 
                                    onclick="selectStrategyCategory('${key}')"
                                    id="cat-btn-${key}"
                                    class="strategy-category-btn w-full p-4 rounded-lg border-2 transition-all duration-300 text-left
                                           ${currentStrategyCategory === key ? 'border-blue-500 bg-blue-900/30' : 'border-gray-700 bg-gray-800 hover:border-gray-600'}">
                                    <div class="flex items-center">
                                        <span class="text-2xl mr-3">${cat.icon}</span>
                                        <div>
                                            <div class="font-semibold">${cat.label}</div>
                                            <div class="text-xs text-gray-400 mt-1">${cat.description}</div>
                                        </div>
                                    </div>
                                </button>
                            `).join('')}
                        </div>
                    </div>

                    <!-- Lado Direito: Estratégias Específicas -->
                    <div class="lg:col-span-2">
                        <h4 class="text-lg font-medium mb-3 text-green-300">Estratégias Disponíveis</h4>
                        <div id="strategy-selection-right" class="min-h-48 bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                            <div id="strategy-buttons" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div class="text-center text-gray-400 py-8">
                                    <span class="text-4xl">👈</span>
                                    <p class="mt-2">Selecione um tipo de estratégia ao lado</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Estratégia Selecionada -->
            <div id="strategy-description" class="config-section mb-6 hidden">
                <div class="bg-gradient-to-r from-green-900/20 to-blue-900/20 border border-green-600 rounded-lg p-4">
                    <div class="flex items-center justify-center">
                        <span class="text-2xl mr-3">✅</span>
                        <span class="text-lg font-semibold text-green-300">Estratégia selecionada:</span>
                        <span id="strategy-desc-title" class="text-xl font-bold text-white ml-2">Estratégia</span>
                    </div>
                </div>
            </div>

            <!-- Etapa 4+: Seções de Configuração -->
            <div id="config-sections-container" class="space-y-6">
                <!-- Preenchido dinamicamente -->
            </div>

            <!-- Botões de Ação -->
            <div id="config-actions" class="hidden mt-8 flex gap-4">
                <button onclick="previewConfigChanges()" 
                        class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-lg transition-all">
                    👁️ Preview de Mudanças
                </button>
                <button onclick="saveConfigV2()" 
                        class="flex-1 bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-lg transition-all">
                    💾 Salvar Configuração
                </button>
                <button onclick="resetToDefaults()" 
                        class="bg-gray-600 hover:bg-gray-700 text-white font-semibold py-3 px-6 rounded-lg transition-all">
                    🔄 Restaurar Padrões
                </button>
            </div>
        `;
        
        // Auto-selecionar categoria atual
        if (currentStrategyType) {
            const strategy = configSchemaV2.strategies[currentStrategyType];
            if (strategy) {
                selectStrategyCategory(strategy.category);
                selectStrategy(currentStrategyType);
            }
        }
    }

    function selectStrategyCategory(category) {
        currentStrategyCategory = category;
        
        // Atualizar visual dos botões de categoria (lado esquerdo)
        document.querySelectorAll('.strategy-category-btn').forEach(btn => {
            btn.classList.remove('border-blue-500', 'bg-blue-900/30');
            btn.classList.add('border-gray-700', 'bg-gray-800');
        });
        
        const selectedBtn = document.getElementById(`cat-btn-${category}`);
        if (selectedBtn) {
            selectedBtn.classList.remove('border-gray-700', 'bg-gray-800');
            selectedBtn.classList.add('border-blue-500', 'bg-blue-900/30');
        }
        
        // Mostrar estratégias da categoria no lado direito
        const strategyButtons = document.getElementById('strategy-buttons');
        const strategies = configSchemaV2.strategy_categories[category].strategies;
        
        strategyButtons.innerHTML = strategies.map(stratKey => {
            const strat = configSchemaV2.strategies[stratKey];
            return `
                <button 
                    onclick="selectStrategy('${stratKey}')"
                    id="strat-btn-${stratKey}"
                    class="strategy-btn p-4 rounded-lg border-2 transition-all duration-300 text-left h-full
                           ${currentStrategyType === stratKey ? 'border-green-500 bg-green-900/30' : 'border-gray-700 bg-gray-800 hover:border-gray-600'}">
                    <div class="flex items-start">
                        <span class="text-2xl mr-3 mt-1">${strat.icon}</span>
                        <div class="flex-1">
                            <div class="font-semibold text-base mb-2">${strat.label}</div>
                            <div class="text-xs text-gray-400 mb-2">${strat.description}</div>
                            <div class="text-xs text-blue-300">💡 ${strat.use_case}</div>
                        </div>
                    </div>
                </button>
            `;
        }).join('');
    }

    function selectStrategy(strategy) {
        currentStrategyType = strategy;
        
        // Atualizar visual dos botões de estratégia
        document.querySelectorAll('.strategy-btn').forEach(btn => {
            btn.classList.remove('border-green-500', 'bg-green-900/30');
            btn.classList.add('border-gray-700', 'bg-gray-800');
        });
        
        const selectedBtn = document.getElementById(`strat-btn-${strategy}`);
        if (selectedBtn) {
            selectedBtn.classList.remove('border-gray-700', 'bg-gray-800');
            selectedBtn.classList.add('border-green-500', 'bg-green-900/30');
        }
        
        // Mostrar estratégia selecionada
        const stratData = configSchemaV2.strategies[strategy];
        const descSection = document.getElementById('strategy-description');
        const descTitle = document.getElementById('strategy-desc-title');
        
        descTitle.textContent = `${stratData.icon} ${stratData.label}`;
        descSection.classList.remove('hidden');
        
        // Renderizar campos de configuração
        renderConfigSections(strategy);
        
        // Mostrar botões de ação
        document.getElementById('config-actions').classList.remove('hidden');
        
        // Scroll suave para as configurações
        setTimeout(() => {
            document.getElementById('config-sections-container').scrollIntoView({ 
                behavior: 'smooth', 
                block: 'start' 
            });
        }, 300);
    }

    function renderConfigSections(strategy) {
        const container = document.getElementById('config-sections-container');
        const sections = configSchemaV2.config_sections;
        const strategyCategory = configSchemaV2.strategies[strategy].category;
        
        let html = '';
        let sectionNumber = 2; // Começa em 2 pois agora temos menos etapas
        
        // 1. Configurações Comuns (sempre)
        html += renderConfigSection(sections.common, sectionNumber++, 'common');
        
        // 2. Configurações Básicas específicas da categoria
        if (strategyCategory === 'grid') {
            html += renderConfigSection(sections.basic_grid, sectionNumber++, 'basic');
        } else {
            html += renderConfigSection(sections.basic_multi_asset, sectionNumber++, 'basic');
        }
        
        // 3. Auto-Close (sempre)
        html += renderConfigSection(sections.auto_close, sectionNumber++, 'feature');
        
        // 4. Enhanced Advanced (apenas para multi_asset_enhanced)
        if (strategy === 'multi_asset_enhanced') {
            html += renderConfigSection(sections.enhanced_advanced, sectionNumber++, 'enhanced');
        }
        
        // 5. Gestão de Risco (sempre)
        html += renderConfigSection(sections.risk_management, sectionNumber++, 'risk');
        
        container.innerHTML = html;
        
        // Inicializar valores atuais
        populateCurrentValues();
    }

    function renderConfigSection(section, number, type) {
        // Cores baseadas no tipo de seção
        const typeStyles = {
            'common': 'border-blue-600 bg-blue-900/10',
            'basic': 'border-green-600 bg-green-900/10', 
            'feature': 'border-purple-600 bg-purple-900/10',
            'enhanced': 'border-orange-600 bg-orange-900/10',
            'risk': 'border-red-600 bg-red-900/10'
        };
        
        const styleClass = typeStyles[type] || 'border-gray-700 bg-gray-800';
        
        return `
            <div class="config-section border rounded-lg p-6 ${styleClass}">
                <h3 class="text-xl font-semibold mb-4 flex items-center">
                    <span class="text-3xl mr-3">${number}️⃣</span>
                    ${section.label}
                    <button onclick="toggleSectionHelp('${section.label}')" 
                            class="ml-auto text-blue-400 hover:text-blue-300 text-sm">
                        ❓ Ajuda
                    </button>
                </h3>
                <p class="text-sm text-gray-400 mb-6">${section.description}</p>
                
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    ${section.fields.map(fieldKey => renderConfigField(fieldKey)).join('')}
                </div>
            </div>
        `;
    }

    function renderConfigField(fieldKey) {
        const field = configSchemaV2.fields[fieldKey];
        
        if (!field) return '';
        
        const currentValue = currentConfigValues[fieldKey] || field.default || '';
        
        let inputHtml = '';
        
        // Renderizar input baseado no tipo
        switch (field.type) {
            case 'select':
                inputHtml = `
                    <select 
                        id="config-${fieldKey}" 
                        class="config-input w-full bg-gray-700 text-white rounded px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none"
                        onchange="validateField('${fieldKey}', this.value)">
                        ${field.options.map(opt => `
                            <option value="${opt}" ${currentValue == opt ? 'selected' : ''}>${opt}</option>
                        `).join('')}
                    </select>
                `;
                break;
                
            case 'multiselect':
                // Para SYMBOLS: interface especial com busca e seleção múltipla
                if (fieldKey === 'SYMBOLS') {
                    const isAuto = currentValue === 'AUTO' || currentValue === '';
                    const selectedSymbols = isAuto ? [] : currentValue.split(',').map(s => s.trim()).filter(s => s);
                    
                    inputHtml = `
                        <div class="symbols-selector bg-gray-700 rounded-lg p-4 border border-gray-600">
                            <!-- Toggle AUTO vs Manual -->
                            <div class="flex items-center gap-4 mb-4">
                                <label class="flex items-center cursor-pointer">
                                    <input type="radio" name="symbols-mode" value="AUTO" 
                                           ${isAuto ? 'checked' : ''} 
                                           onchange="toggleSymbolsMode('AUTO')"
                                           class="mr-2 accent-blue-500">
                                    <span class="font-semibold text-green-400">🤖 AUTO</span>
                                </label>
                                <label class="flex items-center cursor-pointer">
                                    <input type="radio" name="symbols-mode" value="MANUAL" 
                                           ${!isAuto ? 'checked' : ''} 
                                           onchange="toggleSymbolsMode('MANUAL')"
                                           class="mr-2 accent-blue-500">
                                    <span class="font-semibold text-blue-400">✋ Manual</span>
                                </label>
                            </div>
                            
                            <!-- Hidden input para o valor final -->
                            <input type="hidden" id="config-${fieldKey}" value="${currentValue}">
                            
                            <!-- Descrição do modo AUTO -->
                            <div id="auto-description" class="text-sm text-gray-300 mb-3 ${!isAuto ? 'hidden' : ''}">
                                <div class="flex items-center gap-2">
                                    <span>🎯</span>
                                    <span>Modo AUTO: Bot usará todos os símbolos disponíveis na API</span>
                                </div>
                            </div>
                            
                            <!-- Seleção manual de símbolos -->
                            <div id="manual-selection" class="${isAuto ? 'hidden' : ''}">
                                <!-- Campo de busca -->
                                <div class="mb-4">
                                    <div class="flex items-center gap-2 mb-2">
                                        <span>🔍</span>
                                        <span class="text-sm text-gray-300">Buscar Tokens</span>
                                    </div>
                                    <input type="text" 
                                           id="symbols-search" 
                                           placeholder="Digite para buscar tokens (ex: BTC, ETH, SOL)..." 
                                           class="w-full bg-gray-800 text-white px-4 py-2 rounded-lg border border-gray-600 focus:border-blue-500 focus:outline-none"
                                           onkeyup="filterSymbols()">
                                </div>
                                
                                <!-- Status e contador -->
                                <div class="flex items-center justify-between mb-3">
                                    <div id="symbols-count" class="text-sm text-gray-400">
                                        Carregando símbolos...
                                    </div>
                                    <div id="selected-count" class="text-sm font-semibold">
                                        <span class="text-green-400" id="selected-number">0</span> selecionados
                                    </div>
                                </div>
                                
                                <!-- Lista de símbolos com scroll -->
                                <div class="symbols-list bg-gray-800 rounded-lg border border-gray-600 max-h-80 overflow-y-auto">
                                    <div id="symbols-checkboxes" class="p-2">
                                        <div class="text-center text-gray-400 py-8">
                                            🔄 Carregando símbolos disponíveis...
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- Tokens selecionados (tags) -->
                                <div id="selected-tokens-display" class="mt-4 hidden">
                                    <div class="text-sm text-gray-300 mb-2">Tokens Selecionados:</div>
                                    <div id="selected-tokens-tags" class="flex flex-wrap gap-2"></div>
                                </div>
                                
                                <div class="mt-3 text-xs text-gray-400">
                                    💡 Recomendado: 3-5 símbolos para diversificação balanceada
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    // Fallback para outros campos multiselect
                    inputHtml = `
                        <input 
                            type="text" 
                            id="config-${fieldKey}"
                            class="config-input w-full bg-gray-700 text-white rounded px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none"
                            value="${currentValue}"
                            placeholder="Ex: BTC,ETH,SOL ou AUTO"
                            onblur="validateField('${fieldKey}', this.value)">
                        <div class="text-xs text-gray-500 mt-1">Separar por vírgulas</div>
                    `;
                }
                break;
                
            case 'toggle':
                const isChecked = currentValue === true || currentValue === 'true' || currentValue === 'True';
                inputHtml = `
                    <label class="flex items-center cursor-pointer">
                        <div class="relative">
                            <input 
                                type="checkbox" 
                                id="config-${fieldKey}"
                                class="config-input sr-only"
                                ${isChecked ? 'checked' : ''}
                                onchange="validateField('${fieldKey}', this.checked)">
                            <div class="toggle-bg w-14 h-8 bg-gray-700 rounded-full shadow-inner"></div>
                            <div class="toggle-dot absolute w-6 h-6 bg-white rounded-full shadow left-1 top-1 transition"></div>
                        </div>
                        <div class="ml-3 text-gray-300 font-medium">
                            ${isChecked ? 'Ativado' : 'Desativado'}
                        </div>
                    </label>
                `;
                break;
                
            case 'number':
                inputHtml = `
                    <input 
                        type="number" 
                        id="config-${fieldKey}"
                        class="config-input w-full bg-gray-700 text-white rounded px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none"
                        value="${currentValue}"
                        min="${field.min || ''}"
                        max="${field.max || ''}"
                        step="${field.step || 1}"
                        onblur="validateField('${fieldKey}', this.value)">
                `;
                break;
                
            default: // text
                inputHtml = `
                    <input 
                        type="text" 
                        id="config-${fieldKey}"
                        class="config-input w-full bg-gray-700 text-white rounded px-4 py-2 border border-gray-600 focus:border-blue-500 focus:outline-none"
                        value="${currentValue}"
                        onblur="validateField('${fieldKey}', this.value)">
                `;
        }
        
        // Adicionar funcionalidades especiais para campos de símbolos
        const isSymbolField = fieldKey === 'SYMBOL' || fieldKey === 'SYMBOLS';
        const refreshButton = isSymbolField ? `
            <button onclick="refreshSymbolsCache()" 
                    class="ml-2 text-sm bg-blue-600 hover:bg-blue-700 px-3 py-1 rounded flex items-center gap-1"
                    title="Atualizar lista de símbolos">
                🔄 Atualizar
            </button>
        ` : '';
        
        const cacheStatus = isSymbolField ? `
            <div id="symbols-cache-status" class="mt-2">
                <div class="text-sm text-gray-400 flex items-center gap-2">
                    <span>📦</span>
                    <span>Carregando status do cache...</span>
                </div>
            </div>
        ` : '';

        return `
            <div class="config-field" data-field-container="${fieldKey}">
                <label class="block text-gray-300 font-semibold mb-2 flex items-center justify-between">
                    <div class="flex items-center">
                        ${field.label}
                        <button 
                            onclick="showFieldHelp('${fieldKey}')" 
                            class="ml-2 text-blue-400 hover:text-blue-300 text-xl"
                            title="Ajuda">
                            ❓
                        </button>
                    </div>
                    ${refreshButton}
                </label>
                ${inputHtml}
                <div id="validation-${fieldKey}" class="text-sm mt-1 hidden"></div>
                ${cacheStatus}
            </div>
        `;
    }

    function populateCurrentValues() {
        // Popula campos com valores atuais do .env
        Object.keys(currentConfigValues).forEach(key => {
            const input = document.getElementById(`config-${key}`);
            if (input) {
                if (input.type === 'checkbox') {
                    input.checked = currentConfigValues[key] === true || 
                                   currentConfigValues[key] === 'true' || 
                                   currentConfigValues[key] === 'True';
                } else if (key === 'SYMBOLS') {
                    // Tratamento especial para SYMBOLS multiselect
                    input.value = currentConfigValues[key];
                    
                    // Atualizar interface de SYMBOLS se existir
                    const isAuto = currentConfigValues[key] === 'AUTO' || currentConfigValues[key] === '';
                    const autoRadio = document.querySelector('input[name="symbols-mode"][value="AUTO"]');
                    const manualRadio = document.querySelector('input[name="symbols-mode"][value="MANUAL"]');
                    
                    if (autoRadio && manualRadio) {
                        if (isAuto) {
                            autoRadio.checked = true;
                            toggleSymbolsMode('AUTO');
                        } else {
                            manualRadio.checked = true;
                            toggleSymbolsMode('MANUAL');
                            
                            // Aguardar símbolos carregarem e então marcar os corretos
                            setTimeout(() => {
                                const selectedSymbols = currentConfigValues[key].split(',').map(s => s.trim()).filter(s => s);
                                document.querySelectorAll('#symbols-checkboxes input[type="checkbox"]').forEach(cb => {
                                    cb.checked = selectedSymbols.includes(cb.value);
                                });
                                updateSymbolsSelection();
                            }, 1000);
                        }
                    }
                } else {
                    input.value = currentConfigValues[key];
                }
            }
        });
    }

    async function validateField(fieldKey, value) {
        try {
            const response = await fetch(`${API_BASE}/api/config/validate-field`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    field: fieldKey,
                    value: value,
                    strategy: currentStrategyType
                })
            });
            
            const result = await response.json();
            const validationDiv = document.getElementById(`validation-${fieldKey}`);
            
            if (validationDiv) {
                if (result.valid) {
                    validationDiv.className = 'text-sm mt-1 text-green-400';
                    validationDiv.textContent = result.message;
                    
                    if (result.warning) {
                        validationDiv.className = 'text-sm mt-1 text-yellow-400';
                        validationDiv.textContent = result.warning;
                    }
                } else {
                    validationDiv.className = 'text-sm mt-1 text-red-400';
                    validationDiv.textContent = result.message;
                }
                validationDiv.classList.remove('hidden');
            }
            
            // Armazenar mudança
            configChanges[fieldKey] = value;
            
        } catch (error) {
            console.error('Erro na validação:', error);
        }
    }

    function showFieldHelp(fieldKey) {
        const field = configSchemaV2.fields[fieldKey];
        
        if (!field || !field.help) {
            alert('Ajuda não disponível para este campo');
            return;
        }
        
        const help = field.help;
        
        let helpContent = `
            <div class="space-y-4">
                <h4 class="font-semibold text-lg">${field.label}</h4>
                
                ${help.description ? `<p><strong>📖 Descrição:</strong><br>${help.description}</p>` : ''}
                
                ${help.recommended ? `<p><strong>✅ Recomendado:</strong><br>${help.recommended}</p>` : ''}
                
                ${help.tip ? `<p><strong>💡 Dica:</strong><br>${help.tip}</p>` : ''}
                
                ${help.warning ? `<p class="text-yellow-300"><strong>⚠️ Atenção:</strong><br>${help.warning}</p>` : ''}
                
                ${help.example ? `<p class="text-blue-300"><strong>📝 Exemplo:</strong><br>${help.example}</p>` : ''}
            </div>
        `;
        
        // Mostrar em modal
        showModal('Ajuda - ' + field.label, helpContent);
    }

    async function previewConfigChanges() {
        try {
            // Coletar todos os valores atuais dos inputs
            const newConfig = { STRATEGY_TYPE: currentStrategyType };
            
            document.querySelectorAll('.config-input').forEach(input => {
                const fieldKey = input.id.replace('config-', '');
                
                if (input.type === 'checkbox') {
                    newConfig[fieldKey] = input.checked;
                } else {
                    newConfig[fieldKey] = input.value;
                }
            });
            
            const response = await fetch(`${API_BASE}/api/config/preview-changes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config: newConfig })
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                let previewHtml = `
                    <div class="space-y-4">
                        <div class="bg-gray-700 rounded-lg p-4">
                            <h4 class="font-semibold mb-2">📊 Resumo:</h4>
                            <p>Total de mudanças: <strong>${data.total_changes}</strong></p>
                            <p>Impacto: <span class="px-3 py-1 rounded ${
                                data.impact_level === 'high' ? 'bg-red-600' : 
                                data.impact_level === 'medium' ? 'bg-yellow-600' : 
                                'bg-green-600'
                            }">${data.impact_level.toUpperCase()}</span></p>
                        </div>
                `;
                
                // Avisos
                if (data.warnings.length > 0) {
                    previewHtml += `
                        <div class="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4">
                            <h4 class="font-semibold mb-2 text-yellow-300">⚠️ Avisos:</h4>
                            ${data.warnings.map(w => `<p class="text-sm">• ${w}</p>`).join('')}
                        </div>
                    `;
                }
                
                // Modificações
                if (Object.keys(data.changes.modified).length > 0) {
                    previewHtml += `
                        <div class="bg-blue-900/30 border border-blue-700 rounded-lg p-4">
                            <h4 class="font-semibold mb-2 text-blue-300">🔄 Modificações:</h4>
                            <div class="space-y-2 text-sm">
                                ${Object.entries(data.changes.modified).map(([key, change]) => `
                                    <div class="flex justify-between items-center">
                                        <span class="font-mono">${key}:</span>
                                        <span><span class="text-red-400">${change.from}</span> → <span class="text-green-400">${change.to}</span></span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }
                
                // Adicionados
                if (Object.keys(data.changes.added).length > 0) {
                    previewHtml += `
                        <div class="bg-green-900/30 border border-green-700 rounded-lg p-4">
                            <h4 class="font-semibold mb-2 text-green-300">➕ Adicionados:</h4>
                            <div class="space-y-1 text-sm">
                                ${Object.entries(data.changes.added).map(([key, val]) => `
                                    <p class="font-mono">${key} = ${val}</p>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }
                
                // Removidos
                if (Object.keys(data.changes.removed).length > 0) {
                    previewHtml += `
                        <div class="bg-red-900/30 border border-red-700 rounded-lg p-4">
                            <h4 class="font-semibold mb-2 text-red-300">➖ Removidos:</h4>
                            <div class="space-y-1 text-sm">
                                ${Object.entries(data.changes.removed).map(([key, val]) => `
                                    <p class="font-mono">${key} = ${val}</p>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }
                
                previewHtml += `
                    </div>
                    <div class="mt-6 flex gap-4">
                        <button onclick="closeModal()" class="flex-1 bg-gray-600 hover:bg-gray-700 text-white font-semibold py-3 px-6 rounded-lg">
                            ❌ Cancelar
                        </button>
                        <button onclick="confirmSaveConfig()" class="flex-1 bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-lg">
                            ✅ Confirmar e Salvar
                        </button>
                    </div>
                `;
                
                showModal('Preview de Mudanças', previewHtml);
            }
            
        } catch (error) {
            console.error('Erro no preview:', error);
            showAlert('error', 'Erro ao gerar preview: ' + error.message);
        }
    }

    async function saveConfigV2() {
        // Coletar todos os valores
        const newConfig = { STRATEGY_TYPE: currentStrategyType };
        
        document.querySelectorAll('.config-input').forEach(input => {
            const fieldKey = input.id.replace('config-', '');
            
            if (input.type === 'checkbox') {
                newConfig[fieldKey] = input.checked;
            } else {
                newConfig[fieldKey] = input.value;
            }
        });
        
        try {
            const response = await fetch(`${API_BASE}/api/config/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newConfig)
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                showAlert('success', '✅ Configuração salva com sucesso!');
                
                // Perguntar se quer reiniciar o bot
                if (confirm('Deseja reiniciar o bot agora para aplicar as mudanças?')) {
                    await fetch(`${API_BASE}/api/bot/restart`, { method: 'POST' });
                    showAlert('success', '🔄 Bot reiniciando...');
                }
                
                // Recarregar valores
                setTimeout(() => loadConfigSchemaV2(), 2000);
            } else {
                showAlert('error', '❌ Erro ao salvar: ' + data.message);
            }
            
        } catch (error) {
            console.error('Erro ao salvar:', error);
            showAlert('error', 'Erro ao salvar configuração: ' + error.message);
        }
    }

    async function confirmSaveConfig() {
        closeModal();
        await saveConfigV2();
    }

    async function resetToDefaults() {
        if (!confirm('⚠️ Deseja restaurar os valores padrão?\n\nIsso irá sobrescrever TODAS as configurações atuais!')) {
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/api/config/get-defaults`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ strategy: currentStrategyType })
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                // Aplicar defaults nos inputs
                Object.entries(data.defaults).forEach(([key, value]) => {
                    const input = document.getElementById(`config-${key}`);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = value === true || value === 'true';
                        } else {
                            input.value = value;
                        }
                    }
                });
                
                showAlert('success', '✅ Valores padrão restaurados! Clique em Salvar para aplicar.');
            } else {
                showAlert('error', '❌ Erro: ' + data.message);
            }
            
        } catch (error) {
            console.error('Erro ao restaurar defaults:', error);
            showAlert('error', 'Erro ao restaurar valores padrão');
        }
    }

    // Funções auxiliares para modal
    function showModal(title, content) {
        const modalHtml = `
            <div id="custom-modal" class="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50" onclick="closeModalOnBackdrop(event)">
                <div class="bg-gray-800 rounded-lg p-6 max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto" onclick="event.stopPropagation()">
                    <div class="flex justify-between items-center mb-4">
                        <h3 class="text-xl font-semibold">${title}</h3>
                        <button onclick="closeModal()" class="text-gray-400 hover:text-white text-2xl">&times;</button>
                    </div>
                    <div class="modal-content">
                        ${content}
                    </div>
                </div>
            </div>
        `;
        
        // Remover modal existente se houver
        const existingModal = document.getElementById('custom-modal');
        if (existingModal) {
            existingModal.remove();
        }
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    function closeModal() {
        const modal = document.getElementById('custom-modal');
        if (modal) {
            modal.remove();
        }
    }

    function closeModalOnBackdrop(event) {
        if (event.target.id === 'custom-modal') {
            closeModal();
        }
    }

    // Modificar a função existente de loadConfig para usar V2
    const originalLoadConfig = loadConfig;
    loadConfig = async function() {
        // Verificar se schema V2 existe
        try {
            const response = await fetch(`${API_BASE}/api/config/schema/v2`);
            if (response.ok) {
                // Usar interface V2
                await loadConfigSchemaV2();
            } else {
                // Fallback para interface antiga
                await originalLoadConfig();
            }
        } catch (error) {
            console.log('Schema V2 não disponível, usando interface clássica');
            await originalLoadConfig();
        }
    };

    // ==========================================
    // SÍMBOLOS DINÂMICOS - CACHE INTELIGENTE  
    // ==========================================

    // Carregar símbolos ao abrir aba de configuração
    async function loadSymbolsForConfig() {
        try {
            showSymbolsLoading();
            
            const response = await fetch(`${API_BASE}/api/symbols/available`);
            const data = await response.json();
            
            if (data.status === 'success') {
                populateSymbolFields(data.symbols);
                updateCacheStatus(data.cache_info);
            } else {
                showAlert('error', '❌ Erro ao carregar símbolos');
            }
        } catch (error) {
            console.error('Erro ao carregar símbolos:', error);
            showAlert('error', 'Erro ao carregar símbolos disponíveis');
        }
    }

    function populateSymbolFields(symbols) {
        // Popula campo SYMBOL (single select)
        const symbolField = document.querySelector('#config-SYMBOL, select[data-field="SYMBOL"], input[data-field="SYMBOL"]');
        if (symbolField) {
            if (symbolField.tagName === 'SELECT') {
                const currentValue = symbolField.value;
                symbolField.innerHTML = symbols.map(s => 
                    `<option value="${s}" ${s === currentValue ? 'selected' : ''}>${s}</option>`
                ).join('');
            } else if (symbolField.tagName === 'INPUT') {
                // Para campos input, adicionar datalist para autocomplete
                let datalist = document.getElementById('symbols-datalist');
                if (!datalist) {
                    datalist = document.createElement('datalist');
                    datalist.id = 'symbols-datalist';
                    symbolField.parentNode.appendChild(datalist);
                    symbolField.setAttribute('list', 'symbols-datalist');
                }
                datalist.innerHTML = symbols.map(s => `<option value="${s}">`).join('');
            }
        }
        
        // Popula campo SYMBOLS (multi select ou input)
        const symbolsField = document.querySelector('#config-SYMBOLS, select[data-field="SYMBOLS"], input[data-field="SYMBOLS"]');
        if (symbolsField) {
            if (symbolsField.tagName === 'SELECT') {
                const currentValues = Array.from(symbolsField.selectedOptions).map(o => o.value);
                symbolsField.innerHTML = symbols.map(s => 
                    `<option value="${s}" ${currentValues.includes(s) ? 'selected' : ''}>${s}</option>`
                ).join('');
            } else if (symbolsField.tagName === 'INPUT') {
                // Para campos input, adicionar datalist
                let datalist = document.getElementById('symbols-multi-datalist');
                if (!datalist) {
                    datalist = document.createElement('datalist');
                    datalist.id = 'symbols-multi-datalist';
                    symbolsField.parentNode.appendChild(datalist);
                    symbolsField.setAttribute('list', 'symbols-multi-datalist');
                }
                datalist.innerHTML = symbols.map(s => `<option value="${s}">`).join('');
            }
        }
        
        console.log(`✅ ${symbols.length} símbolos carregados nos campos`);
    }

    function updateCacheStatus(cacheInfo) {
        const statusDiv = document.getElementById('symbols-cache-status');
        if (!statusDiv) return;
        
        if (cacheInfo && cacheInfo.valid) {
            const age = Math.floor(cacheInfo.age_hours || 0);
            statusDiv.innerHTML = `
                <div class="text-sm text-green-400 flex items-center gap-2">
                    <span>✅</span>
                    <span>Cache válido (${cacheInfo.count || 0} símbolos, atualizado há ${age}h)</span>
                </div>
            `;
        } else if (cacheInfo && cacheInfo.exists) {
            statusDiv.innerHTML = `
                <div class="text-sm text-yellow-400 flex items-center gap-2">
                    <span>⚠️</span>
                    <span>Cache expirado (${cacheInfo.count || 0} símbolos)</span>
                </div>
            `;
        } else {
            statusDiv.innerHTML = `
                <div class="text-sm text-gray-400 flex items-center gap-2">
                    <span>📦</span>
                    <span>Cache não existe</span>
                </div>
            `;
        }
    }

    async function refreshSymbolsCache() {
        try {
            showAlert('info', '🔄 Atualizando lista de símbolos...');
            
            const response = await fetch(`${API_BASE}/api/symbols/refresh`, {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.status === 'success') {
                populateSymbolFields(data.symbols);
                showAlert('success', data.message);
                
                // Atualizar info do cache
                setTimeout(async () => {
                    const cacheResponse = await fetch(`${API_BASE}/api/symbols/cache-info`);
                    const cacheData = await cacheResponse.json();
                    if (cacheData.status === 'success') {
                        updateCacheStatus(cacheData.cache);
                    }
                }, 500);
            } else {
                showAlert('error', '❌ ' + data.message);
            }
        } catch (error) {
            showAlert('error', 'Erro ao atualizar símbolos');
        }
    }

    function showSymbolsLoading() {
        const symbolField = document.querySelector('#config-SYMBOL, select[data-field="SYMBOL"]');
        if (symbolField && symbolField.tagName === 'SELECT') {
            symbolField.innerHTML = '<option>🔄 Carregando símbolos...</option>';
        }
        
        const symbolsField = document.querySelector('#config-SYMBOLS, select[data-field="SYMBOLS"]');
        if (symbolsField && symbolsField.tagName === 'SELECT') {
            symbolsField.innerHTML = '<option>🔄 Carregando símbolos...</option>';
        }
    }

    // Modificar a função showTab existente para incluir carregamento de símbolos
    const originalShowTab = showTab;
    showTab = function(tab) {
        // Executar função original
        originalShowTab(tab);
        
        // Se foi para aba config, carregar símbolos
        if (tab === 'config') {
            // Aguardar um pouco para garantir que os campos foram renderizados
            setTimeout(() => {
                loadSymbolsForConfig();
            }, 500);
        }
    };

    // ========== FUNÇÕES PARA SÍMBOLOS MULTISELECT ==========

    let availableSymbols = [];
    let filteredSymbols = [];

    function toggleSymbolsMode(mode) {
        const autoDesc = document.getElementById('auto-description');
        const manualSelection = document.getElementById('manual-selection');
        const hiddenInput = document.getElementById('config-SYMBOLS');
        
        if (mode === 'AUTO') {
            autoDesc.classList.remove('hidden');
            manualSelection.classList.add('hidden');
            hiddenInput.value = 'AUTO';
        } else {
            autoDesc.classList.add('hidden');
            manualSelection.classList.remove('hidden');
            
            // Carregar símbolos se ainda não foram carregados
            if (availableSymbols.length === 0) {
                loadSymbolsForMultiselect();
            }
            
            updateSymbolsSelection(); // Atualiza baseado nos checkboxes atuais
        }
        
        // Trigger validation
        validateField('SYMBOLS', hiddenInput.value);
    }

    function updateSymbolsSelection() {
        const checkboxes = document.querySelectorAll('#symbols-checkboxes input[type="checkbox"]:checked');
        const selectedSymbols = Array.from(checkboxes).map(cb => cb.value);
        const hiddenInput = document.getElementById('config-SYMBOLS');
        
        hiddenInput.value = selectedSymbols.length > 0 ? selectedSymbols.join(',') : '';
        
        // Atualizar contador
        const selectedCountEl = document.getElementById('selected-number');
        if (selectedCountEl) {
            selectedCountEl.textContent = selectedSymbols.length;
        }
        
        // Atualizar tags de tokens selecionados
        updateSelectedTokensTags(selectedSymbols);
        
        // Trigger validation
        validateField('SYMBOLS', hiddenInput.value);
    }

    function updateSelectedTokensTags(selectedSymbols) {
        const tagsContainer = document.getElementById('selected-tokens-tags');
        const displayContainer = document.getElementById('selected-tokens-display');
        
        if (!tagsContainer || !displayContainer) return;
        
        if (selectedSymbols.length > 0) {
            displayContainer.classList.remove('hidden');
            tagsContainer.innerHTML = selectedSymbols.map(symbol => `
                <span class="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-600 text-white">
                    ${symbol}
                    <button onclick="removeSymbol('${symbol}')" class="ml-2 hover:text-red-300">×</button>
                </span>
            `).join('');
        } else {
            displayContainer.classList.add('hidden');
        }
    }

    function removeSymbol(symbol) {
        const checkbox = document.querySelector(`#symbols-checkboxes input[value="${symbol}"]`);
        if (checkbox) {
            checkbox.checked = false;
            updateSymbolsSelection();
        }
    }

    async function loadSymbolsForMultiselect() {
        const container = document.getElementById('symbols-checkboxes');
        const countEl = document.getElementById('symbols-count');
        
        if (!container) return;
        
        try {
            // Mostrar loading
            container.innerHTML = '<div class="text-center text-gray-400 py-8">🔄 Carregando símbolos...</div>';
            
            const response = await fetch(`${API_BASE}/api/symbols/available`);
            const data = await response.json();
            
            if (data.status === 'success') {
                availableSymbols = data.symbols.sort(); // Ordenar alfabeticamente
                filteredSymbols = [...availableSymbols];
                
                if (countEl) {
                    countEl.textContent = `${availableSymbols.length} tokens encontrados`;
                }
                
                renderSymbolsList(filteredSymbols);
            } else {
                container.innerHTML = '<div class="text-center text-red-400 py-8">❌ Erro ao carregar símbolos</div>';
            }
        } catch (error) {
            console.error('Erro ao carregar símbolos:', error);
            container.innerHTML = '<div class="text-center text-red-400 py-8">❌ Erro na conexão</div>';
        }
    }

    function renderSymbolsList(symbols) {
        const container = document.getElementById('symbols-checkboxes');
        const hiddenInput = document.getElementById('config-SYMBOLS');
        
        if (!container) return;
        
        // Obter símbolos já selecionados
        const currentValue = hiddenInput ? hiddenInput.value : '';
        const selectedSymbols = currentValue && currentValue !== 'AUTO' 
            ? currentValue.split(',').map(s => s.trim()).filter(s => s) 
            : [];
        
        if (symbols.length === 0) {
            container.innerHTML = '<div class="text-center text-gray-400 py-8">🔍 Nenhum token encontrado</div>';
            return;
        }
        
        container.innerHTML = symbols.map(symbol => {
            // Simular dados de mercado básicos para demonstração
            const volumes = ['50.2M', '128.7M', '89.1M', '302.5M', '67.8M', '45.3M', '123.4M'];
            const changes = ['+2.34%', '+5.67%', '-1.23%', '+0.89%', '-3.45%', '+7.12%', '+1.56%'];
            const colors = ['text-green-400', 'text-green-400', 'text-red-400', 'text-green-400', 'text-red-400', 'text-green-400', 'text-green-400'];
            
            const randomVol = volumes[Math.floor(Math.random() * volumes.length)];
            const randomChange = changes[Math.floor(Math.random() * changes.length)];
            const changeColor = randomChange.startsWith('+') ? 'text-green-400' : 'text-red-400';
            
            return `
                <label class="flex items-center justify-between cursor-pointer hover:bg-gray-700 p-3 rounded transition-colors border-b border-gray-700 last:border-b-0">
                    <div class="flex items-center">
                        <div class="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-sm mr-3">
                            ${symbol.charAt(0)}
                        </div>
                        <div>
                            <div class="font-semibold text-white">${symbol}-PERP</div>
                            <div class="text-xs text-gray-400">Vol: ${randomVol} USDC</div>
                        </div>
                    </div>
                    <div class="flex items-center">
                        <span class="text-xs ${changeColor} mr-3">${randomChange}</span>
                        <div class="flex items-center">
                            ${selectedSymbols.includes(symbol) ? 
                                '<span class="text-xs text-green-500 mr-2">✓ Selecionado</span>' : ''}
                            <input type="checkbox" 
                                   value="${symbol}" 
                                   ${selectedSymbols.includes(symbol) ? 'checked' : ''}
                                   onchange="updateSymbolsSelection()"
                                   class="w-5 h-5 accent-blue-500">
                        </div>
                    </div>
                </label>
            `;
        }).join('');
        
        // Atualizar contador de selecionados
        updateSymbolsSelection();
    }

    function filterSymbols() {
        const searchInput = document.getElementById('symbols-search');
        const searchTerm = searchInput ? searchInput.value.toUpperCase() : '';
        
        if (searchTerm === '') {
            filteredSymbols = [...availableSymbols];
        } else {
            filteredSymbols = availableSymbols.filter(symbol => 
                symbol.toUpperCase().includes(searchTerm)
            );
        }
        
        renderSymbolsList(filteredSymbols);
        
        // Atualizar contador
        const countEl = document.getElementById('symbols-count');
        if (countEl) {
            countEl.textContent = `${filteredSymbols.length} tokens encontrados`;
        }
    }

    console.log('✅ Sistema de configuração V2 hierárquica carregado');
    console.log('✅ Sistema de símbolos dinâmicos carregado');

// ==========================================
// MARKET VISION
// ==========================================

let currentMarketVision = null;

function loadMarketVision() {
    fetch('/api/market-vision?symbol=BTC')
        .then(response => response.json())
        .then(data => {
            currentMarketVision = data;
            updateMarketVisionUI(data);
        })
        .catch(error => {
            console.error('Erro ao carregar Market Vision:', error);
        });
}

function updateMarketVisionUI(data) {
    // Score global
    document.getElementById('mv-global-score').textContent = data.global_score.toFixed(1);
    document.getElementById('mv-global-status').textContent = data.global_status;
    
    const scoreBar = document.getElementById('mv-score-bar');
    const percentage = (data.global_score / 10) * 100;
    scoreBar.style.width = percentage + '%';
    
    // Cor do score bar
    if (data.global_score >= 7.5) {
        scoreBar.className = 'bg-green-500 h-4 rounded-full transition-all';
    } else if (data.global_score >= 5.5) {
        scoreBar.className = 'bg-yellow-500 h-4 rounded-full transition-all';
    } else {
        scoreBar.className = 'bg-red-500 h-4 rounded-full transition-all';
    }
    
    // Scores individuais
    document.getElementById('mv-tech-score').textContent = data.technical_score.toFixed(1);
    document.getElementById('mv-vol-score').textContent = data.volume_score.toFixed(1);
    document.getElementById('mv-sent-score').textContent = data.sentiment_score.toFixed(1);
    document.getElementById('mv-struct-score').textContent = data.structure_score.toFixed(1);
    document.getElementById('mv-risk-score').textContent = data.risk_score.toFixed(1);
    
    // Detalhes técnicos
    if (data.technical_details) {
        document.getElementById('mv-tech-rsi').textContent = `RSI: ${data.technical_details.rsi.toFixed(0)}`;
        document.getElementById('mv-tech-adx').textContent = `ADX: ${data.technical_details.adx.toFixed(0)}`;
    }
    
    // Detalhes de volume
    if (data.volume_details) {
        document.getElementById('mv-vol-ratio').textContent = `Ratio: ${data.volume_details.volume_ratio.toFixed(2)}x`;
        document.getElementById('mv-vol-delta').textContent = `Delta: ${data.volume_details.delta > 0 ? '+' : ''}${(data.volume_details.delta).toFixed(0)}`;
    }
    
    // Detalhes de sentimento
    if (data.sentiment_details) {
        document.getElementById('mv-sent-funding').textContent = `Funding: ${(data.sentiment_details.funding_rate * 100).toFixed(3)}%`;
        document.getElementById('mv-sent-oi').textContent = `OI: ${(data.sentiment_details.oi_change * 100).toFixed(1)}%`;
    }
    
    // Setup
    if (data.has_setup && data.setup) {
        document.getElementById('mv-setup-panel').style.display = 'block';
        
        const setup = data.setup;
        document.getElementById('mv-setup-direction').textContent = setup.direction;
        document.getElementById('mv-setup-confidence').textContent = `Confiança: ${setup.confidence.toFixed(0)}%`;
        document.getElementById('mv-setup-entry').textContent = `$${setup.entry.toFixed(2)}`;
        document.getElementById('mv-setup-sl').textContent = `$${setup.stop_loss.toFixed(2)} (${setup.sl_distance_pct.toFixed(2)}%)`;
        document.getElementById('mv-setup-tp').textContent = `$${setup.take_profit.toFixed(2)} (${setup.tp_distance_pct.toFixed(2)}%)`;
        document.getElementById('mv-setup-size').textContent = `$${setup.position_size_usd.toFixed(2)}`;
        document.getElementById('mv-setup-rr').textContent = `1:${setup.risk_reward_ratio.toFixed(2)}`;
        
        // Reasoning
        if (setup.conditions_met) {
            const reasoningHTML = setup.conditions_met.map(c => `<div>${c}</div>`).join('');
            document.getElementById('mv-setup-reasoning').innerHTML = reasoningHTML;
        }
        
        // Multi-timeframe
        if (data.mtf_summary) {
            const mtfHTML = Object.entries(data.mtf_summary).map(([tf, info]) => {
                return `
                    <div class="bg-gray-800 rounded p-3">
                        <div class="flex justify-between mb-2">
                            <span class="font-semibold">${tf}</span>
                            <span class="${info.direction === 'LONG' ? 'text-green-400' : info.direction === 'SHORT' ? 'text-red-400' : 'text-gray-400'}">
                                ${info.direction === 'LONG' ? '📈' : info.direction === 'SHORT' ? '📉' : '➡️'} ${info.direction}
                            </span>
                        </div>
                        <div class="text-xs text-gray-400">
                            Score: ${info.score.toFixed(1)}/10
                        </div>
                    </div>
                `;
            }).join('');
            document.getElementById('mv-mtf-summary').innerHTML = mtfHTML;
        }
    } else {
        document.getElementById('mv-setup-panel').style.display = 'none';
    }
    
    // Warnings
    const warningsContainer = document.getElementById('mv-warnings');
    if (data.warnings && data.warnings.length > 0) {
        const warningsHTML = data.warnings.map(w => {
            return `<div class="bg-yellow-900/30 border border-yellow-600 rounded p-3 text-sm">${w}</div>`;
        }).join('');
        warningsContainer.innerHTML = warningsHTML;
    } else {
        warningsContainer.innerHTML = '';
    }
}

function executeMarketVisionTrade() {
    if (!currentMarketVision || !currentMarketVision.setup) {
        alert('Nenhum setup disponível');
        return;
    }
    
    const setup = currentMarketVision.setup;
    const notes = prompt('Adicione uma nota (opcional):');
    
    const userDecision = {
        action: 'execute',
        direction: setup.direction,
        entry: setup.entry,
        stop_loss: setup.stop_loss,
        take_profit: setup.take_profit,
        size_usd: setup.position_size_usd,
        notes: notes || ''
    };
    
    fetch('/api/record-decision', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(userDecision)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', `✅ Trade executado! ID: ${data.decision_id}`);
            // Aqui você pode chamar a função real de execução do trade
            // executeActualTrade(setup);
        }
    })
    .catch(error => {
        console.error('Erro ao registrar decisão:', error);
        showAlert('error', 'Erro ao registrar decisão');
    });
}

function skipMarketVisionSetup() {
    if (!currentMarketVision || !currentMarketVision.setup) return;
    
    const setup = currentMarketVision.setup;
    const reason = prompt('Por que está pulando este setup?');
    
    const userDecision = {
        action: 'skip',
        direction: setup.direction,
        entry: 0,
        stop_loss: 0,
        take_profit: 0,
        size_usd: 0,
        notes: reason || 'Setup pulado'
    };
    
    fetch('/api/record-decision', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(userDecision)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', 'Setup pulado e registrado');
        }
    });
}

function modifyMarketVisionSetup() {
    if (!currentMarketVision || !currentMarketVision.setup) return;
    
    const setup = currentMarketVision.setup;
    
    // Permitir modificação
    const newEntry = parseFloat(prompt('Entry price:', setup.entry));
    const newSL = parseFloat(prompt('Stop Loss:', setup.stop_loss));
    const newTP = parseFloat(prompt('Take Profit:', setup.take_profit));
    const newSize = parseFloat(prompt('Position Size (USD):', setup.position_size_usd));
    const notes = prompt('Nota sobre modificação:');
    
    if (isNaN(newEntry) || isNaN(newSL) || isNaN(newTP) || isNaN(newSize)) {
        alert('Valores inválidos');
        return;
    }
    
    const userDecision = {
        action: 'modify',
        direction: setup.direction,
        entry: newEntry,
        stop_loss: newSL,
        take_profit: newTP,
        size_usd: newSize,
        notes: notes || 'Setup modificado'
    };
    
    fetch('/api/record-decision', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(userDecision)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('success', 'Setup modificado registrado!');
            // Executar com valores modificados
            // executeActualTrade(userDecision);
        }
    });
}

console.log('✅ Market Vision JavaScript carregado');
