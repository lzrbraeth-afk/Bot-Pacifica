"""
Pacifica Grid Trading Bot - Sistema Principal
Executa estratégias de Grid Trading (Pure Grid e Market Making)
"""

import os
import sys
import time
import signal
import logging
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Importar módulos do bot (assumindo que estão no mesmo diretório)
from src.pacifica_auth import PacificaAuth
from src.grid_calculator import GridCalculator
from src.position_manager import PositionManager
from src.grid_strategy import GridStrategy
from src.dynamic_grid_strategy import DynamicGridStrategy
from src.multi_asset_strategy import MultiAssetStrategy
from src.multi_asset_enhanced_strategy import MultiAssetEnhancedStrategy
from src.directional_scalping_integrated import DirectionalScalping 
from src.performance_tracker import PerformanceTracker
from src.strategy_logger import create_strategy_logger, get_strategy_specific_messages
from src.telegram_notifier import TelegramNotifier
from src.grid_risk_manager import GridRiskManager
from src.margin_trend_protector import create_margin_trend_adapter
from src.positions_tracker import PositionsTracker



# Dashboard web será importado dinamicamente para evitar import circular
init_web_components = None

# Força UTF-8 no Windows para suportar emojis
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    try:
        os.system('chcp 65001 >nul 2>&1')
    except:
        pass

class GridTradingBot:
    def __init__(self):
        # Carregar configurações do .env primeiro
        load_dotenv()
        
        # 🔒 INTEGRAÇÃO COM CREDENCIAIS CRIPTOGRAFADAS
        self._load_secure_credentials_if_available()
        
        # Criar dicionário config com todas as variáveis de ambiente (incluindo credenciais descriptografadas)
        self.config = dict(os.environ)
        
        # Determinar tipo de estratégia - APENAS UMA VARIÁVEL: STRATEGY_TYPE
        strategy_type_env = os.getenv('STRATEGY_TYPE', 'market_making').lower()
        
        # Mapear todas as estratégias via STRATEGY_TYPE
        if strategy_type_env == 'multi_asset':
            self.strategy_type = 'multi_asset'
        elif strategy_type_env == 'multi_asset_enhanced':
            self.strategy_type = 'multi_asset_enhanced'
        elif strategy_type_env == 'scalping': 
            self.strategy_type = 'scalping'
        elif strategy_type_env in ['pure_grid', 'market_making', 'dynamic_grid']:
            self.strategy_type = 'grid'
            self.grid_type = strategy_type_env  # Salvar tipo específico do grid
        else:
            # Fallback para market_making se valor inválido
            self.strategy_type = 'grid'
            self.grid_type = 'market_making'
        
        # Setup logging
        self.setup_logging()
        
        # Criar logger específico da estratégia
        self.logger = create_strategy_logger('PacificaBot.Main', self.strategy_type)
        
        # Estado do bot
        self.running = False
        self.start_time = None
        
        # Configurações
        self.symbol = os.getenv('SYMBOL', 'BTC')
        self.leverage = int(os.getenv('LEVERAGE', '10'))
        self.rebalance_interval = int(os.getenv('REBALANCE_INTERVAL_SECONDS', '60'))
        self.check_balance = os.getenv('CHECK_BALANCE_BEFORE_ORDER', 'true').lower() == 'true'
        
        # ========== TRACKER PARA INTERFACE WEB ==========
        # Tracker para posições e ordens (interface web)
        self.positions_tracker = PositionsTracker()
        self.logger.info("📊 Interface tracker inicializado")
        # ================================================
        
        # ✨ NOVA FUNCIONALIDADE: Reset periódico do grid
        self.enable_periodic_reset = os.getenv('ENABLE_PERIODIC_GRID_RESET', 'false').lower() == 'true'
        self.grid_reset_interval = int(os.getenv('GRID_RESET_INTERVAL_MINUTES', '60')) * 60  # Converter para segundos

        # Configurações de controle de sessão
        self.session_stop_loss = float(os.getenv('SESSION_STOP_LOSS_USD', '100'))
        self.session_take_profit = float(os.getenv('SESSION_TAKE_PROFIT_USD', '200'))
        self.session_max_loss = float(os.getenv('SESSION_MAX_LOSS_USD', '150'))
        
        # Estado da sessão
        self.session_start_balance = 0.0
        self.session_realized_pnl = 0.0
        self.is_paused = False

        # Declarar componentes como None - serão inicializados em initialize_components()
        self.auth = None
        self.calculator = None
        self.position_mgr = None
        self.telegram = None
        self.risk_manager = None
        self.strategy = None

        # Protetor de margem será inicializado depois dos componentes
        self.margin_adapter = None

        # Setup signal handlers para shutdown gracioso
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def show_strategy_header(self):
        """Mostrar cabeçalho específico da estratégia"""
        
        self.logger.info("=" * 80, force=True)
        self.logger.info("🤖 PACIFICA TRADING BOT", force=True)
        self.logger.info("=" * 80, force=True)
        
        if self.strategy_type == 'scalping':
            self.logger.info(f"Estratégia: 🚀 DIRECTIONAL SCALPING", force=True)
            self.logger.info(f"Símbolo: {self.symbol}", force=True)
            
            # Mostrar configurações específicas do scalping
            duration = os.getenv('SCALPING_TRADE_DURATION', '30')
            min_pnl = os.getenv('SCALPING_MIN_PNL', '0.5')
            max_loss = os.getenv('SCALPING_MAX_LOSS_PERCENT', '-2.0')
            position_size = os.getenv('SCALPING_POSITION_SIZE', '100')
            cooldown = os.getenv('SCALPING_COOLDOWN', '10')
            confidence = os.getenv('SCALPING_MIN_CONFIDENCE', '0.6')
            
            self.logger.info(f"Duração do Trade: {duration}s", force=True)
            self.logger.info(f"Min PNL Alvo: ${min_pnl}", force=True)
            self.logger.info(f"Max Loss: {max_loss}%", force=True)
            self.logger.info(f"Tamanho Posição: ${position_size}", force=True)
            self.logger.info(f"Cooldown: {cooldown}s", force=True)
            self.logger.info(f"Min Confidence: {confidence}", force=True)
            
            # Mostrar configurações do analyzer
            use_ema = os.getenv('ANALYZER_USE_EMA', 'true').lower() == 'true'
            use_rsi = os.getenv('ANALYZER_USE_RSI', 'true').lower() == 'true'
            use_volume = os.getenv('ANALYZER_USE_VOLUME', 'true').lower() == 'true'
            min_confirmation = os.getenv('ANALYZER_MIN_CONFIRMATION', '0.6')
            
            indicators = []
            if use_ema: indicators.append("EMA")
            if use_rsi: indicators.append("RSI")
            if use_volume: indicators.append("Volume")
            
            self.logger.info(f"Indicadores: {', '.join(indicators)}", force=True)
            self.logger.info(f"Min Confirmation: {min_confirmation}", force=True)
        elif self.strategy_type == 'grid':
            grid_type = getattr(self, 'grid_type', 'market_making').upper()
            if grid_type == 'DYNAMIC_GRID':
                self.logger.info(f"Estratégia: 🎯 DYNAMIC GRID TRADING", force=True)
                # Mostrar configurações específicas do Dynamic Grid
                threshold = os.getenv('DYNAMIC_THRESHOLD_PERCENT', '1.0')
                max_distance = os.getenv('MAX_ADJUSTMENT_DISTANCE_PERCENT', '5.0')
                self.logger.info(f"Threshold de Ajuste: {threshold}%", force=True)
                self.logger.info(f"Distância Máxima: {max_distance}%", force=True)
            else:
                self.logger.info(f"Estratégia: GRID TRADING ({grid_type})", force=True)
            self.logger.info(f"Símbolo: {self.symbol}", force=True)
        elif self.strategy_type == 'multi_asset_enhanced':
            self.logger.info(f"Estratégia: 🧠 ENHANCED MULTI-ASSET", force=True)
            symbols = os.getenv('SYMBOLS', 'BTC,ETH,SOL')
            quality = os.getenv('ENHANCED_MIN_SIGNAL_QUALITY', '65')
            confidence = os.getenv('ENHANCED_MIN_CONFIDENCE', '75')
            self.logger.info(f"Símbolos: {symbols}", force=True)
            self.logger.info(f"Algoritmo: Quality≥{quality}, Confidence≥{confidence}", force=True)
        else:  # multi_asset
            self.logger.info(f"Estratégia: MULTI-ASSET SCALPING", force=True)
            symbols = os.getenv('SYMBOLS', 'BTC,ETH,SOL')
            self.logger.info(f"Símbolos: {symbols}", force=True)
            
        self.logger.info(f"Intervalo de Rebalanceamento: {self.rebalance_interval}s", force=True)
        
        # ✨ Mostrar configuração de reset periódico
        if self.enable_periodic_reset:
            reset_minutes = self.grid_reset_interval // 60
            self.logger.info(f"🔄 Reset Periódico: A cada {reset_minutes} minutos", force=True)
        else:
            self.logger.info("🔄 Reset Periódico: Desabilitado", force=True)
            
        self.logger.info("=" * 80, force=True)
        
        # 🔧 SISTEMA DE VALIDAÇÕES (NOVO)
        self._run_config_validations()
         
    def setup_logging(self):
        """Configura sistema de logging"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"grid_bot_{timestamp}.log"
        
        log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())
        
        log_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Root logger
        root_logger = logging.getLogger('PacificaBot')
        root_logger.setLevel(log_level)
        root_logger.handlers.clear()
        
        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_format)
        root_logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(log_format)
        root_logger.addHandler(console_handler)
    
    def _run_config_validations(self):
        """Executa validações de configuração sem afetar funcionalidade principal"""
        try:
            from src.config_validator import run_all_validations
            
            self.logger.info("🔧 Executando validações de configuração...")
            validation_result = run_all_validations(self.strategy_type)
            
            if validation_result['warnings']:
                self.logger.warning("⚠️ AVISOS DE CONFIGURAÇÃO:")
                for warning in validation_result['warnings']:
                    self.logger.warning(f"  • {warning}")
                    
            if validation_result['errors']:
                self.logger.error("❌ PROBLEMAS CRÍTICOS DE CONFIGURAÇÃO:")
                for error in validation_result['errors']:
                    self.logger.error(f"  • {error}")
                self.logger.error("⚠️ Bot pode não funcionar corretamente - verifique as configurações acima")
            else:
                self.logger.info("✅ Todas as validações passaram com sucesso")
                
        except ImportError:
            self.logger.debug("📋 Config validator não encontrado, pulando validações")
        except Exception as e:
            self.logger.debug(f"⚠️ Erro durante validações: {e}")
    
    def _load_secure_credentials_if_available(self):
        """Carrega credenciais criptografadas se disponíveis, mantendo compatibilidade com .env"""
        try:
            # Verificar se existe arquivo de credenciais criptografadas
            from pathlib import Path
            credentials_file = Path('.credentials_secure.json')
            
            if not credentials_file.exists():
                # Se não existe, usar .env normalmente
                return
            
            # Importar funções do app.py
            try:
                from app import load_credentials_secure, decrypt_credential
                
                # Carregar credenciais descriptografadas
                result = load_credentials_secure()
                
                if result['status'] == 'success':
                    credentials = result['credentials']
                    
                    # Mapear credenciais para variáveis de ambiente
                    credential_mapping = {
                        'MAIN_PUBLIC_KEY': credentials.get('MAIN_PUBLIC_KEY'),
                        'AGENT_PRIVATE_KEY_B58': credentials.get('AGENT_PRIVATE_KEY_B58'),
                        'API_ADDRESS': credentials.get('API_ADDRESS', 'https://api.pacifica.fi/api/v1')
                    }
                    
                    # Aplicar apenas credenciais válidas (não sobrescrever se já existe no .env)
                    for key, value in credential_mapping.items():
                        if value and (not os.getenv(key) or os.getenv(key) == ''):
                            os.environ[key] = str(value)
                    
                    # Criar um logger temporário para informar sobre o carregamento
                    print("🔒 Credenciais criptografadas carregadas com sucesso")
                    
                elif result['status'] == 'not_configured':
                    print("📋 Credenciais criptografadas não configuradas, usando .env")
                
            except ImportError:
                # Se não conseguir importar do app.py, usar .env normalmente
                print("⚠️ Módulo de credenciais não disponível, usando .env")
                
        except Exception as e:
            # Em caso de erro, continuar usando .env
            print(f"⚠️ Erro ao carregar credenciais criptografadas: {e}")
            print("📋 Continuando com credenciais do .env")
    
    def _verify_credentials(self) -> bool:
        """Verifica se as credenciais necessárias estão configuradas"""
        required_credentials = [
            'MAIN_PUBLIC_KEY',
            'AGENT_PRIVATE_KEY_B58'
        ]
        
        missing_credentials = []
        
        for cred in required_credentials:
            value = os.getenv(cred)
            if not value or value.strip() == '':
                missing_credentials.append(cred)
        
        if missing_credentials:
            self.logger.error("❌ Credenciais obrigatórias não encontradas:")
            for cred in missing_credentials:
                self.logger.error(f"   • {cred}")
            
            self.logger.error("📋 Configure através de:")
            self.logger.error("   1. Interface web: http://localhost:5000")
            self.logger.error("   2. Arquivo .env na raiz do projeto")
            return False
        
        # Verificar se as credenciais são válidas (formato básico)
        main_key = os.getenv('MAIN_PUBLIC_KEY')
        agent_key = os.getenv('AGENT_PRIVATE_KEY_B58')
        
        if len(main_key) < 32:
            self.logger.error("❌ MAIN_PUBLIC_KEY muito curta")
            return False
            
        if len(agent_key) < 32:
            self.logger.error("❌ AGENT_PRIVATE_KEY_B58 muito curta")
            return False
        
        self.logger.info("✅ Credenciais verificadas com sucesso")
        self.logger.info(f"🔑 Wallet: {main_key[:8]}...{main_key[-8:]}")
        self.logger.info(f"🔐 Agent Key: {agent_key[:8]}...{agent_key[-8:]}")
        
        return True
    
    def initialize_components(self) -> bool:
        """Inicializa todos os componentes do bot"""
        
        try:
            self.logger.info("🔧 Inicializando componentes...")
            
            # 🔒 Verificar se credenciais estão configuradas
            if not self._verify_credentials():
                self.logger.error("❌ Credenciais não configuradas!")
                self.logger.error("📋 Configure através da interface web ou arquivo .env")
                return False
            
            # 1. Autenticação
            self.logger.info("🔑 Iniciando autenticação...")
            self.auth = PacificaAuth()
            self.logger.info("✅ Auth Client inicializado")

            # 2. Telegram Notifier (antes do Risk Manager)
            self.logger.info("📱 Iniciando Telegram Notifier...")
            self.telegram = TelegramNotifier()
            self.logger.info("✅ Telegram Notifier inicializado")

            # 3. Limpar ordens antigas (se configurado)
            clean_on_start = os.getenv('CLEAN_ORDERS_ON_START', 'false').lower() == 'true'
            if clean_on_start:
                self.logger.warning("🧹 Limpando ordens antigas...")
                self._clean_old_orders()
                self.logger.info("✅ Ordens antigas limpas")
            
            # 4. Grid Calculator (COM auth para buscar market info)
            self.logger.info("📊 Iniciando Grid Calculator...")
            self.calculator = GridCalculator(auth_client=self.auth)
            self.logger.info("✅ Grid Calculator inicializado")
            
            # 5. Position Manager
            self.logger.info("📈 Iniciando Position Manager...")
            self.position_mgr = PositionManager(self.auth)
            self.logger.info("✅ Position Manager inicializado")

            # 6. Grid Risk Manager (apenas para estratégias grid)
            self.risk_manager = None
            if self.strategy_type == 'grid':
                self.risk_manager = GridRiskManager(
                    auth_client=self.auth,
                    position_manager=self.position_mgr,
                    telegram_notifier=self.telegram,
                    logger=self.logger
                )
                self.logger.info("✅ Grid Risk Manager inicializado")
            
            # 7. Inicializar strategy baseada no tipo configurado
            if self.strategy_type == 'scalping':
                self.logger.info("🚀 Inicializando estratégia Directional Scalping...")
                self.strategy = DirectionalScalping(
                    auth_client=self.auth,
                    calculator=self.calculator,
                    position_manager=self.position_mgr
                )
                self.logger.info("✅ Estratégia Directional Scalping inicializada")
            elif self.strategy_type == 'multi_asset':
                self.logger.info("🎯 Inicializando estratégia Multi-Asset Scalping...")
                self.strategy = MultiAssetStrategy(self.auth, self.calculator, self.position_mgr)
            elif self.strategy_type == 'multi_asset_enhanced':
                self.logger.info("🧠 Inicializando estratégia Enhanced Multi-Asset...")
                self.strategy = MultiAssetEnhancedStrategy(self.auth, self.calculator, self.position_mgr)
            else:
                # Verificar se deve usar estratégia dinâmica
                if hasattr(self, 'grid_type') and self.grid_type == 'dynamic_grid':
                    self.logger.info("🎯 Inicializando estratégia Dynamic Grid Trading...")
                    self.strategy = DynamicGridStrategy(self.auth, self.calculator, self.position_mgr)
                else:
                    self.logger.info("📊 Inicializando estratégia Grid Trading...")
                    self.strategy = GridStrategy(self.auth, self.calculator, self.position_mgr)
            
            self.logger.info("✅ Componentes inicializados com sucesso")
            
            # 8. Inicializar protetor de margem (após todos os componentes)
            try:
                self.margin_adapter = create_margin_trend_adapter(self, self.config)
                self.logger.info("✅ Proteção de margem inicializada")
            except Exception as margin_error:
                self.logger.error(f"❌ Erro ao inicializar proteção de margem: {margin_error}")
                self.margin_adapter = None
            
            # 9. Criar arquivo de status para comunicação com Flask
            try:
                import json
                from datetime import datetime
                
                bot_status = {
                    'status': 'running',
                    'pid': os.getpid(),
                    'started_at': datetime.now().isoformat(),
                    'strategy_type': self.strategy_type,
                    'symbol': getattr(self, 'symbol', 'BTC')
                }
                
                with open('bot_status.json', 'w') as f:
                    json.dump(bot_status, f, indent=2)
                    
                self.logger.info("✅ Arquivo de status criado para comunicação com Flask")
                
                # Tentar inicializar componentes web se Flask estiver disponível
                try:
                    from app import initialize_components as init_web_components
                    init_web_components(self.auth, self.position_mgr, self.calculator)
                    self.logger.info("✅ Painel de risco web inicializado")
                except ImportError:
                    self.logger.debug("ℹ️ Dashboard web não disponível (será ativado quando Flask iniciar)")
                except Exception as web_error:
                    self.logger.debug(f"ℹ️ Dashboard web será ativado quando Flask iniciar: {web_error}")
                    
            except Exception as e:
                self.logger.warning(f"⚠️ Erro ao criar arquivo de status: {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar componentes: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _update_symbols_cache(self):
        """Atualiza cache de símbolos da Pacifica.fi durante inicialização do bot"""
        try:
            self.logger.info("📦 Atualizando cache de símbolos da Pacifica.fi...")
            
            # Usar o cache de símbolos com método dedicado
            from src.cache import SymbolsCache
            symbols_cache = SymbolsCache(cache_duration_hours=24)
            
            # Atualizar usando método específico que fornece mais informações
            result = symbols_cache.update_cache(api_client=self.auth)
            
            self.logger.info(f"📊 Resultado: {result['message']}")
            self.logger.info(f"🎯 Fonte dos dados: {result['source']}")
            self.logger.info(f"📈 Total de símbolos: {result['symbols_count']}")
            
            if result['success'] and result['source'] in ['api_fresh', 'api_cached']:
                # Símbolos obtidos da API real da Pacifica.fi
                symbols = result['symbols']
                self.logger.info(f"✅ Símbolos REAIS da Pacifica.fi disponíveis para trade")
                self.logger.info(f"📋 Amostra: {', '.join(symbols[:10])}")
                
            elif result['symbols_count'] > 0:
                # Fallback funcionando
                self.logger.warning(f"⚠️ Usando fallback: {result.get('error', 'API temporariamente indisponível')}")
                
            else:
                # Problema grave
                self.logger.error("❌ Falha ao obter símbolos - verifique configuração da API")
                
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao atualizar cache de símbolos: {e}")
            self.logger.info("ℹ️ Interface web usará símbolos padrão como fallback")
    
    def _clean_old_orders(self):
        """Cancela todas as ordens abertas do símbolo com verificação robusta"""
        try:
            self.logger.info(f"🔍 Verificando ordens existentes para {self.symbol}...")
            
            # Buscar todas as ordens abertas
            all_open_orders = self.auth.get_open_orders()
            
            if not all_open_orders:
                self.logger.info("ℹ️ Nenhuma ordem encontrada na conta")
                return
            
            # Filtrar ordens do símbolo específico
            symbol_orders = []
            for order in all_open_orders:
                if order.get('symbol') == self.symbol:
                    symbol_orders.append(order)
            
            if not symbol_orders:
                self.logger.info(f"ℹ️ Nenhuma ordem encontrada para {self.symbol}")
                return
            
            self.logger.info(f"🚫 Cancelando {len(symbol_orders)} ordens de {self.symbol}...")
            
            cancelled_count = 0
            failed_count = 0
            
            for order in symbol_orders:
                order_id = order.get('order_id')
                price = order.get('price', 'N/A')
                side = order.get('side', 'N/A')
                order_type = order.get('type', 'LIMIT')
                
                if order_id:
                    try:
                        self.logger.debug(f"   Cancelando: {side} @ {price} (ID: {order_id})")
                        
                        # Passar o símbolo para o cancelamento
                        result = self.auth.cancel_order(str(order_id), self.symbol)
                        
                        if result and result.get('success'):
                            cancelled_count += 1
                            self.logger.debug(f"   ✅ Cancelada: {order_id}")
                        else:
                            failed_count += 1
                            error_msg = result.get('error', 'Erro desconhecido') if result else 'Sem resposta'
                            self.logger.warning(f"   ⚠️ Falha ao cancelar {order_id}: {error_msg}")
                        
                        time.sleep(0.15)  # Delay entre cancelamentos para evitar rate limit
                        
                    except Exception as cancel_error:
                        failed_count += 1
                        self.logger.error(f"   ❌ Erro ao cancelar {order_id}: {cancel_error}")
                else:
                    self.logger.warning(f"   ⚠️ Ordem sem ID válido: {order}")
            
            # Aguardar processamento dos cancelamentos
            if cancelled_count > 0:
                self.logger.info(f"⏳ Aguardando processamento dos cancelamentos...")
                time.sleep(2.0)
                
                # Verificar se realmente foram canceladas
                remaining_orders = self.auth.get_open_orders(self.symbol)
                remaining_count = len(remaining_orders) if remaining_orders else 0
                
                if remaining_count == 0:
                    self.logger.info(f"✅ Todas as {cancelled_count} ordens foram canceladas com sucesso")
                else:
                    self.logger.warning(f"⚠️ Ainda restam {remaining_count} ordens após cancelamento")
            
            if failed_count > 0:
                self.logger.warning(f"⚠️ {failed_count} ordens falharam no cancelamento")
                
            self.logger.info("🧹 Limpeza de ordens concluída")
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao limpar ordens: {e}")
            import traceback
            self.logger.debug(f"Stack trace: {traceback.format_exc()}")
    
    def get_current_price(self) -> float:
        """Obtém preço atual do mercado"""
        
        try:
            # Usar método real da API
            prices = self.auth.get_prices()
            
            if not prices:
                self.logger.warning("⚠️ API retornou dados vazios para preços")
                return 0
            
            if not isinstance(prices, dict):
                self.logger.warning(f"⚠️ API retornou formato inválido: {type(prices)}")
                return 0
                
            # API retorna {"success": true, "data": [...]}
            if not prices.get('success'):
                self.logger.warning(f"⚠️ API retornou erro: {prices}")
                return 0
                
            data = prices.get('data')
            if not data:
                self.logger.warning("⚠️ API não retornou dados de preços")
                return 0
                
            if not isinstance(data, list):
                self.logger.warning(f"⚠️ Dados de preços em formato inválido: {type(data)}")
                return 0
            
            # Procurar pelo símbolo específico
            for item in data:
                if item.get('symbol') == self.symbol:
                    # Preço está em 'mark' ou 'mid'
                    price = item.get('mark') or item.get('mid')
                    if price:
                        price_float = float(price)
                        if price_float > 0:
                            return price_float
                        else:
                            self.logger.warning(f"⚠️ Preço inválido recebido para {self.symbol}: {price}")
            
            self.logger.warning(f"⚠️ Símbolo {self.symbol} não encontrado nos dados da API")
            self.logger.debug(f"Símbolos disponíveis: {[item.get('symbol') for item in data[:5]]}")
            return 0
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter preço: {e}")
            import traceback
            self.logger.debug(f"Stack trace: {traceback.format_exc()}")
            return 0
    
    def _update_interface_data(self):
        """
        Atualiza dados para visualização na interface web
        Busca dados REAIS da API Pacifica e salva via tracker
        """
        try:
            # 🚨 ESTRATÉGIAS MULTI-ASSET TÊM SEU PRÓPRIO SISTEMA
            if self.strategy_type in ['multi_asset', 'multi_asset_enhanced']:
                # Se a estratégia tem seu próprio método de salvar dados, usar ele
                if hasattr(self.strategy, '_save_dashboard_data'):
                    self.strategy._save_dashboard_data()
                    self.logger.debug("📊 Interface atualizada via estratégia multi-asset")
                    return
                
                # Senão, buscar para TODOS os símbolos (não apenas self.symbol)
                api_positions = self.auth.get_positions()  # Todos os símbolos
                api_orders = self.auth.get_open_orders()    # Todas as ordens
            else:
                # Estratégias de grid (symbol-specific)
                api_positions = self.auth.get_positions(self.symbol)
                api_orders = self.auth.get_open_orders(self.symbol)
            
            # 3️⃣ BUSCAR PREÇO ATUAL REAL
            try:
                current_price = float(self.get_current_price())
            except:
                current_price = None
            
            # 4️⃣ FORMATAR POSIÇÕES PARA O TRACKER
            positions = []
            if api_positions:
                for pos in api_positions:
                    # Normalizar 'side': API retorna 'ask'/'bid', converter para 'long'/'short'
                    raw_side = pos.get("side", "long").lower()
                    if raw_side == "bid":
                        side = "long"
                    elif raw_side == "ask":
                        side = "short"
                    else:
                        side = raw_side  # Manter como está se já for long/short
                    
                    positions.append({
                        "symbol": pos.get("symbol", self.symbol or ""),
                        "side": side,
                        "size": float(pos.get("amount", 0) or pos.get("size", 0)),  # API v1 usa 'amount'
                        "entry_price": float(pos.get("entry_price", 0) or pos.get("avg_price", 0)),
                        "open_time": pos.get("created_at", datetime.now().isoformat()),
                        "leverage": pos.get("leverage", self.leverage)
                    })
            
            # 5️⃣ FORMATAR ORDENS PARA O TRACKER
            orders = []
            if api_orders:
                for order in api_orders:
                    # Normalizar side (bid/ask → buy/sell)
                    side = order.get("side", "").lower()
                    if side == "bid":
                        side = "buy"
                    elif side == "ask":
                        side = "sell"
                    
                    orders.append({
                        "order_id": order.get("order_id", "") or order.get("id", ""),
                        "symbol": order.get("symbol", self.symbol or ""),
                        "side": side,
                        "price": float(order.get("price", 0)),
                        "size": float(order.get("size", 0) or order.get("initial_amount", 0)),
                        "create_time": order.get("created_at", datetime.now().isoformat()),
                        "type": order.get("type", "limit")
                    })
            
            # 6️⃣ SALVAR VIA TRACKER (cria os arquivos JSON)
            self.positions_tracker.update_positions(positions, current_price)
            self.positions_tracker.update_orders(orders)
            
            self.logger.debug(
                f"📊 Interface atualizada: "
                f"{len(positions)} posições, {len(orders)} ordens"
            )
            
        except Exception as e:
            # Não é crítico - só log de debug
            self.logger.debug(f"Erro ao atualizar interface: {e}")
    
    def run(self):
        """Loop principal do bot"""
        
        self.logger.info("🚀 Iniciando Grid Trading Bot...")
        
        # Inicializar componentes
        if not self.initialize_components():
            self.logger.error("❌ Falha na inicialização - abortando")
            return

        # ✅ NOVA FUNCIONALIDADE: Atualizar cache de símbolos durante inicialização
        self._update_symbols_cache()

        # Inicializando teste de symbol info (apenas para estratégia grid)
        if self.strategy_type == 'grid':
            self.logger.info(f"🔍 Testando market info para {self.symbol}...")
            test_info = self.auth.get_symbol_info(self.symbol)
            if test_info:
                self.logger.info(f"✅ tick_size={test_info.get('tick_size')}, lot_size={test_info.get('lot_size')}")
        else:
            self.logger.info("🔍 Testando conexão com múltiplos símbolos...")

        
        # Obter preço inicial (apenas para estratégia grid)
        if self.strategy_type == 'grid':
            current_price = self.get_current_price()
            if current_price == 0:
                self.logger.warning("⚠️ Preço inicial não obtido - tentando recuperar...")
                # Fazer retry com delays
                for attempt in range(3):
                    time.sleep(2)  # Aguardar 2 segundos
                    current_price = self.get_current_price()
                    if current_price > 0:
                        self.logger.info(f"✅ Preço recuperado na tentativa {attempt + 1}")
                        break
                
                if current_price == 0:
                    self.logger.error("❌ Não foi possível obter preço inicial após 3 tentativas")
                    return
            
            self.logger.info(f"💰 Preço inicial {self.symbol}: ${current_price:,.2f}")
        else:
            current_price = 0  # Multi-asset gerencia seus próprios preços
            self.logger.info("💰 Estratégia Multi-Asset: preços gerenciados internamente")
        
        # Verificar saldo se configurado
        if self.check_balance:
            self.logger.info("💳 Verificando saldo da conta...")
            if not self.position_mgr.update_account_state():
                self.logger.error("❌ Falha ao verificar saldo")
                return
        
        # 🆕 Verifacao da conta
                
        self.logger.info("💳 Carregando informações da conta...")
        if self.position_mgr.update_account_state():
            self.logger.info("=" * 60)
            self.logger.info("💰 STATUS DA CONTA:")
            self.logger.info(f"   Saldo Total: ${self.position_mgr.account_balance:.2f}")
            self.logger.info(f"   Margem Usada: ${self.position_mgr.margin_used:.2f}")
            self.logger.info(f"   Margem Disponível: ${self.position_mgr.margin_available:.2f}")
            
            if self.position_mgr.account_balance > 0:
                margin_percent = (self.position_mgr.margin_available / 
                                self.position_mgr.account_balance * 100)
                self.logger.info(f"   Margem Livre: {margin_percent:.1f}%")
            
            self.logger.info("=" * 60)
        else:
            self.logger.error("❌ Falha ao carregar informações da conta")

        # Inicializar estratégia com mensagens específicas
        messages = get_strategy_specific_messages(self.strategy_type)
        self.logger.strategy_info(messages['initialization'])
        
        grid_initialized = self.strategy.initialize_grid(current_price)
        if not grid_initialized:
            if self.strategy_type == 'multi_asset':
                self.logger.warning("⚠️ Não foi possível inicializar Multi-Asset agora")
            else:
                self.logger.warning(f"⚠️ Não foi possível inicializar Grid agora (margem insuficiente)")
            self.logger.info("🔄 Bot continuará monitorando e tentará novamente...")
        
        # Verificar se estratégia foi inicializada
        grid_status = self.strategy.get_grid_status()
        messages = get_strategy_specific_messages(self.strategy_type)
        
        if self.strategy_type == 'grid':
            if grid_status['active_orders'] > 0:
                self.logger.strategy_info(f"Retomado com {grid_status['active_orders']} ordens existentes")
            elif grid_initialized:
                self.logger.strategy_info(f"Novo grid criado com {grid_status['active_orders']} ordens")
            else:
                self.logger.strategy_info("Aguardando condições para criar grid...")
        else:
            if grid_initialized:
                self.logger.strategy_info(messages['ready'])
            else:
                self.logger.strategy_info("Aguardando condições de mercado...")
        
        self.running = True
        self.start_time = datetime.now()
        
        self.logger.info("✅ Bot operando!", force=True)
        self.logger.info("=" * 80)
        
        # 🎯 VERIFICAÇÃO INICIAL DE TP/SL para estratégias Multi-Asset
        if self.strategy_type in ['multi_asset', 'multi_asset_enhanced']:
            self.logger.info("🔍 Executando verificação inicial de TP/SL...")
            try:
                if hasattr(self.strategy, '_check_all_tp_sl'):
                    self.strategy._check_all_tp_sl()
                    self.logger.info("✅ Verificação inicial de TP/SL concluída")
                else:
                    self.logger.warning("⚠️ Método _check_all_tp_sl não encontrado na estratégia")
            except Exception as e:
                self.logger.error(f"❌ Erro na verificação inicial de TP/SL: {e}")
        
        # Loop principal
        iteration = 0
        last_rebalance = time.time()
        last_price_check = time.time()
        last_grid_reset = time.time()  # ✨ NOVO: Controle do reset periódico
        last_daily_report = datetime.now().date()  # Controle do relatório diário
        
        # Inicializar current_price baseado na estratégia
        if self.strategy_type == 'grid':
            current_price = self.get_current_price()  # Grid usa preço único
        else:
            current_price = 0  # Multi-asset não usa preço único

        # Definir saldo inicial no risk manager
        if self.risk_manager:
            initial_balance = self.position_mgr.account_balance
            self.risk_manager.set_initial_balance(initial_balance)
        
        while self.running:
            try:
                iteration += 1
                current_time = time.time()

                # ===== VERIFICAR SE BOT ESTÁ PAUSADO =====
                if self.risk_manager and self.risk_manager.check_if_paused():
                    if iteration % 10 == 0:  # Log a cada 10 iterações
                        self.logger.info("⏸️ Bot pausado - aguardando retomada...")
                    time.sleep(10)  # Aguardar 10 segundos
                    continue  # Pular resto do loop

                # DEBUG: Enviar status do Risk Manager (apenas em modo debug)
                debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
                if self.risk_manager and debug_mode and iteration % 20 == 0:
                    self.risk_manager.send_periodic_debug_status()

                # 🔧 Obter preço apenas para estratégia grid com tratamento robusto
                if self.strategy_type == 'grid' and current_time - last_price_check >= 30:
                    new_price = self.get_current_price()
                    if new_price > 0:
                        current_price = new_price
                    else:
                        self.logger.warning("⚠️ Falha ao atualizar preço - mantendo preço anterior")
                    last_price_check = current_time

               # ===== VERIFICAR RISCO DA POSIÇÃO (NÍVEL 1) =====
                if self.risk_manager and self.strategy_type == 'grid':
                    should_close, reason = self.risk_manager.check_position_risk(self.symbol, current_price)
                    
                    if should_close:
                        self.logger.warning(f"🛑 Fechando posição por: {reason}")
                        
                        # Fechar posição
                        try:
                            position = self.position_mgr.positions.get(self.symbol, {})
                            quantity = position.get('quantity', 0)
                            
                            if quantity != 0:
                                # Determinar lado da ordem de fechamento
                                close_side = 'ask' if quantity > 0 else 'bid'
                                close_qty = abs(quantity)
                                
                                self.logger.info(f"📤 Criando ordem de fechamento: {close_side} {close_qty} @ MARKET")
                                
                                # 🔥 IMPLEMENTAÇÃO REAL DA ORDEM DE FECHAMENTO
                                try:
                                    # Criar ordem MARKET para fechar posição
                                    close_order = self.auth.create_order(
                                        symbol=self.symbol,
                                        side=close_side,
                                        amount=close_qty,
                                        price=current_price,
                                        order_type='IOC',
                                        reduce_only=True
                                    )
                                    
                                    if close_order and close_order.get('success'):
                                        self.logger.info(f"✅ Posição fechada com sucesso: {close_order.get('order_id')}")
                                        
                                        # Calcular PNL realizado
                                        avg_price = position.get('avg_price', 0)
                                        pnl_usd = (current_price - avg_price) * quantity
                                        
                                        # Registrar fechamento do ciclo
                                        self.risk_manager.record_cycle_close(self.symbol, pnl_usd, reason)
                                        
                                        # Cancelar todas as ordens do grid
                                        self.logger.info("🚫 Cancelando ordens do grid...")
                                        if hasattr(self.strategy, 'cancel_all_orders'):
                                            self.strategy.cancel_all_orders()
                                        
                                        # Aguardar cancelamentos
                                        time.sleep(2)
                                        
                                        # Resetar posição
                                        self.position_mgr.positions[self.symbol] = {
                                            'quantity': 0,
                                            'avg_price': 0,
                                            'realized_pnl': position.get('realized_pnl', 0) + pnl_usd,
                                            'unrealized_pnl': 0
                                        }
                                        
                                        # Reiniciar grid
                                        self.logger.info("♻️ Reiniciando grid...")
                                        self.risk_manager.reset_cycle()
                                        
                                        # Aguardar antes de recriar grid
                                        time.sleep(3)
                                        
                                        if self.strategy.initialize_grid(current_price):
                                            self.logger.info("✅ Grid reiniciado com sucesso!")
                                        else:
                                            self.logger.warning("⚠️ Aguardando condições para recriar grid...")
                                    else:
                                        error_msg = close_order.get('error', 'Erro desconhecido') if close_order else 'Sem resposta da API'
                                        self.logger.error(f"❌ Falha ao criar ordem de fechamento: {error_msg}")
                                        
                                        # Tentar novamente na próxima iteração
                                        self.logger.warning("⚠️ Tentará fechar posição novamente na próxima verificação")
                                        
                                except Exception as order_error:
                                    self.logger.error(f"❌ Erro ao executar ordem de fechamento: {order_error}")
                                    import traceback
                                    self.logger.error(traceback.format_exc())
                                    
                                    # Notificar via Telegram
                                    if self.telegram:
                                        try:
                                            self.telegram.send_error_alert(
                                                error_message=f"Falha ao fechar posição: {order_error}",
                                                traceback_info=traceback.format_exc()
                                            )
                                        except:
                                            pass
                                            
                        except Exception as e:
                            self.logger.error(f"❌ Erro ao fechar posição: {e}")
                            import traceback
                            self.logger.error(traceback.format_exc())
                
                # ===== VERIFICAR LIMITE DE SESSÃO (NÍVEL 2) =====
                if self.risk_manager:
                    should_stop, reason = self.risk_manager.check_session_limits()
                    
                    if should_stop:
                        self.logger.error(f"🚨 LIMITE DE SESSÃO ATINGIDO: {reason}")
                        
                        # Fechar posição se existir
                        position = self.position_mgr.positions.get(self.symbol, {})
                        if position.get('quantity', 0) != 0:
                            self.logger.warning("🛑 Fechando posição por limite de sessão...")
                            # Implementar fechamento aqui
                        
                        # Cancelar todas as ordens
                        if hasattr(self.strategy, 'cancel_all_orders'):
                            self.strategy.cancel_all_orders()
                        
                        # Verificar ação configurada
                        action = self.risk_manager.get_action_on_limit()
                        
                        if action == 'shutdown':
                            self.logger.error("🛑 Encerrando bot por limite de sessão...")
                            self.running = False
                            break
                        # Se for 'pause', o bot já foi pausado pelo risk_manager 
                
                # Log de heartbeat específico da estratégia
                if iteration % 10 == 0:
                    uptime = datetime.now() - self.start_time
                    if self.strategy_type == 'grid':
                        self.logger.info(f"💓 Heartbeat #{iteration} - Uptime: {uptime} | Preço: ${current_price:,.2f}", force=True)
                    else:
                        active_positions = len(getattr(self.strategy, 'active_positions', []))
                        self.logger.info(f"💓 Heartbeat #{iteration} - Uptime: {uptime} | Posições: {active_positions}", force=True)
                
                # ATIVAR VERIFICAÇÃO DE MARGEM (A CADA 5 ITERAÇÕES = ~5 SEGUNDOS)                
                if self.check_balance and iteration % 5 == 0:
                    # 1. Atualizar estado da conta
                    self.position_mgr.update_account_state()
                    
                    # 2. ✅ ATIVAR VERIFICAÇÃO DE MARGEM (DESCOMENTADO)
                    is_safe, msg = self.position_mgr.check_margin_safety()
                    
                    if not is_safe:
                        # Log do problema detectado
                        self.logger.warning(f"⚠️ {msg}")
                        
                        # 🔥 A FUNÇÃO JÁ EXECUTOU AS AÇÕES AUTOMATICAMENTE:
                        # - Se margem < 20% → Cancelou ordens
                        # - Se margem < 10% → Vendeu posição
                        
                        # Bot CONTINUA OPERANDO (não para)
                    else:
                        # Margem OK - apenas log debug
                        self.logger.debug(f"✅ {msg}")
                
                # Verificar ordens executadas a cada 10 segundos
                if iteration % 10 == 0:
                    self.logger.debug(f"🔍 Verificando ordens executadas...")
                    self.strategy.check_filled_orders(current_price)

                # Verificar condições de parada
                # should_stop, reason = self.position_mgr.should_stop_trading()
                # if should_stop:
                #     self.logger.error(f"🛑 Parando trading: {reason}")
                #     self.stop()
                #     break
                
                # Rebalancear estratégia se necessário
                if current_time - last_rebalance >= self.rebalance_interval:
                    
                    # Verificar margem ANTES de rebalancear
                    self.position_mgr.update_account_state()
                    
                    # ===== PROTEÇÃO DE MARGEM (LINHA ÚNICA) =====
                    if self.margin_adapter:
                        margin_result = self.margin_adapter.monitor_and_protect()
                        
                        # Log status detalhado a cada 100 iterações (para debug)
                        if iteration % 100 == 0:
                            self.margin_adapter.log_detailed_status()
                        
                        if margin_result.get("status") in ["protection_triggered", "paused"]:
                            last_rebalance = current_time
                            continue
                    
                    if self.position_mgr.account_balance > 0:
                        margin_percent = (self.position_mgr.margin_available / 
                                        self.position_mgr.account_balance * 100)
                        
                        if margin_percent < 20:
                            self.logger.warning(f"⚠️ Margem baixa ({margin_percent:.1f}%) - pulando rebalanceamento")
                            
                            # Verificar proteções
                            is_safe, msg = self.position_mgr.check_margin_safety()
                            if not is_safe:
                                self.logger.warning(f"🔧 {msg}")
                            
                            last_rebalance = current_time  # Atualizar timer
                            continue  # Pular para próxima iteração do loop
                    
                    if self.strategy_type == 'grid':
                        self.logger.info(f"🔄 Verificando rebalanceamento em ${current_price:,.2f}")
                        if self.risk_manager and iteration % 30 == 0:  # A cada 30 iterações
                            self.risk_manager.log_periodic_status()
                    else:
                        self.logger.info("🔄 Verificando sinais Multi-Asset")
                    
                    try:
                        self.strategy.check_and_rebalance(current_price)
                        
                        # 🆕 Se não há ordens ativas, tentar recriar grid
                        grid_status = self.strategy.get_grid_status()
                        if grid_status['active_orders'] == 0:
                            self.logger.info("🔄 Sem ordens ativas - tentando recriar grid...")
                            if self.strategy.initialize_grid(current_price):
                                self.logger.info("✅ Grid recriado com sucesso!")
                            else:
                                self.logger.info("⚠️ Ainda sem margem suficiente - continuando monitoramento...")
                        
                    except Exception as e:
                        self.logger.warning(f"⚠️ Erro no rebalanceamento: {e}")
                        # Não para o bot - apenas continua
                    last_rebalance = current_time 
                
                # ✨ NOVA FUNCIONALIDADE: Reset periódico do grid
                if (self.enable_periodic_reset and 
                    self.strategy_type == 'grid' and 
                    current_time - last_grid_reset >= self.grid_reset_interval):
                    
                    try:
                        reset_minutes = self.grid_reset_interval // 60
                        self.logger.info(f"🔄🔥 RESET PERIÓDICO: Refazendo grid completo após {reset_minutes} minutos")
                        
                        # Fazer reset completo do grid
                        if hasattr(self.strategy, 'reset_grid_completely'):
                            success = self.strategy.reset_grid_completely(current_price)
                            if success:
                                self.logger.info("✅ Grid resetado e recriado com sucesso!")
                            else:
                                self.logger.warning("⚠️ Falha no reset - mantendo grid atual")
                        else:
                            # Fallback: usar método tradicional
                            self.logger.info("🔄 Usando método tradicional de reset...")
                            self.strategy.cancel_all_orders()
                            time.sleep(2)  # Aguardar cancelamentos
                            if self.strategy.initialize_grid(current_price):
                                self.logger.info("✅ Grid resetado e recriado com sucesso!")
                            else:
                                self.logger.warning("⚠️ Falha no reset - tentando novamente no próximo ciclo")
                        
                    except Exception as e:
                        self.logger.error(f"❌ Erro no reset periódico: {e}")
                        # Continua operação normal mesmo com falha no reset
                    
                    last_grid_reset = current_time 
                        
                # Status periódico
                if iteration % 60 == 0:  # 🔧 A cada 60 iterações (1 minuto)
                    self.print_status()

                # ========== ATUALIZAR INTERFACE WEB ==========
                # Atualizar dados para interface web (a cada 30 segundos)
                if iteration % 30 == 0:
                    self._update_interface_data()
                # =============================================

                # Relatório detalhado a cada 10 minutos
                if iteration % 600 == 0:
                    self.print_detailed_performance()
                
                # Aguardar próxima iteração
                time.sleep(1)

            except KeyboardInterrupt:
                self.logger.info("🛑 Interrupção via teclado")
                break  # Sair do while loop

            except Exception as e:
                self.logger.error(f"❌ Erro no loop principal: {e}")
                import traceback
                traceback_str = traceback.format_exc()
                self.logger.error(traceback_str)

                # Notificar erro via Telegram (com proteção)
                try:
                    if hasattr(self, 'telegram') and self.telegram:
                        self.telegram.send_error_alert(
                            error_message=str(e),
                            traceback_info=traceback_str
                        )
                except Exception as telegram_error:
                    self.logger.warning(f"⚠️ Falha ao enviar erro via Telegram: {telegram_error}")
                
                # Aguardar antes de continuar
                time.sleep(5)

        # LIMPEZA FINAL (fora do while loop)
        try:
            if hasattr(self, 'risk_manager') and self.risk_manager:
                self.risk_manager.close_session()
        except Exception as rm_error:
            self.logger.warning(f"⚠️ Erro ao fechar risk manager: {rm_error}")
        
        # Limpar arquivo de status do bot
        try:
            status_file = 'bot_status.json'
            if os.path.exists(status_file):
                os.remove(status_file)
                self.logger.info("🧹 Arquivo de status removido")
        except Exception as status_error:
            self.logger.warning(f"⚠️ Erro ao remover arquivo de status: {status_error}")
        
        self.logger.info("🏁 Encerrando bot...")
        
        # Shutdown protegido
        try:
            self.shutdown()
        except Exception as shutdown_error:
            self.logger.error(f"❌ Erro durante shutdown: {shutdown_error}")
            # Tentar shutdown manual dos componentes críticos
            self.running = False
    
    def print_status(self):
        """Imprime status atual do bot com métricas avançadas"""
        
        self.logger.info("=" * 80)
        self.logger.info("📊 STATUS DO BOT")
        self.logger.info("=" * 80)
        
        # Status do grid/estratégia
        grid_status = self.strategy.get_grid_status()
        strategy_name = "Multi-Asset" if self.strategy_type == 'multi_asset' else "Grid"
        self.logger.info(f"{strategy_name} Ativo: {grid_status['active']}")
        
        if self.strategy_type == 'grid':
            self.logger.info(f"Preço Central: ${grid_status['center_price']:,.2f}")
            self.logger.info(f"Ordens Ativas: {grid_status['active_orders']}")
        else:
            self.logger.info(f"Posições Ativas: {grid_status['active_orders']}")  # Para multi-asset, são posições
        
        # 🆕 ADICIONAR: Métricas de performance
        try:
            performance_metrics = self.strategy.get_performance_metrics()
            
            self.logger.info("💹 PERFORMANCE:")
            self.logger.info(f"  Total Trades: {performance_metrics.get('total_trades', 0)}")
            self.logger.info(f"  Win Rate: {performance_metrics.get('win_rate', 0):.1f}%")
            self.logger.info(f"  Total Return: ${performance_metrics.get('total_return', 0):.2f}")
            self.logger.info(f"  Sharpe Ratio: {performance_metrics.get('sharpe_ratio', 0):.2f}")
            self.logger.info(f"  Max Drawdown: {performance_metrics.get('max_drawdown_percent', 0):.1f}%")
            
            self.logger.info("🔧 GRID ADAPTATIVO:")
            self.logger.info(f"  Modo: {'ATIVO' if performance_metrics.get('adaptive_mode') else 'INATIVO'}")
            self.logger.info(f"  Volatilidade: {performance_metrics.get('current_volatility', 0):.4f}")
            self.logger.info(f"  Spacing Atual: {performance_metrics.get('current_spacing', 0):.3f}%")
            self.logger.info(f"  Grid Efficiency: {performance_metrics.get('grid_efficiency', 0):.1f}%")
            
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao obter métricas: {e}")
        
        # Status de posição (manter código existente se desejado)
        # pos_status = self.position_mgr.get_status_summary()
        # self.logger.info(f"Saldo: ${pos_status['account_balance']:,.2f}")
        
        self.logger.info("=" * 80)
    
    def print_detailed_performance(self):
        """Imprime relatório detalhado de performance"""
        
        if self.strategy and hasattr(self.strategy, 'performance_tracker'):
            self.strategy.print_performance_summary()
            
        # 🆕 ESTATÍSTICAS ESPECÍFICAS DA VERSÃO ENHANCED
        if self.strategy_type == 'multi_asset_enhanced' and hasattr(self.strategy, 'get_enhanced_statistics'):
            self.strategy.log_performance_summary()
            
            # Analytics: Display final summary when stopping
            if hasattr(self.strategy, 'analytics') and self.strategy.analytics:
                try:
                    analytics_summary = self.strategy.analytics.get_analytics_summary()
                    self.logger.info("📊 ANALYTICS SUMMARY:")
                    self.logger.info(f"   🔍 Total signals analyzed: {analytics_summary.get('total_signals', 0)}")
                    self.logger.info(f"   ✅ Signals executed: {analytics_summary.get('executed_signals', 0)}")
                    self.logger.info(f"   ❌ Signals rejected: {analytics_summary.get('rejected_signals', 0)}")
                    self.logger.info(f"   💼 Total trades: {analytics_summary.get('total_trades', 0)}")
                    self.logger.info(f"   🔒 Total closures: {analytics_summary.get('total_closures', 0)}")
                    
                    if analytics_summary.get('total_trades', 0) > 0:
                        avg_execution_time = analytics_summary.get('avg_execution_time', 0)
                        self.logger.info(f"   ⏱️ Avg execution time: {avg_execution_time:.2f}s")
                    
                    self.logger.info(f"   📁 Data saved to: {analytics_summary.get('data_file', 'N/A')}")
                except Exception as e:
                    self.logger.error(f"❌ Analytics: Erro ao exibir resumo final: {e}")
                    
        else:
            self.logger.warning("⚠️ Performance tracker não disponível")
    
    def shutdown(self):
        """Encerra o bot graciosamente"""
        
        self.logger.info("🔄 Iniciando shutdown...")
        
        # Limpar arquivo de status do bot
        try:
            status_file = 'bot_status.json'
            if os.path.exists(status_file):
                os.remove(status_file)
                self.logger.info("🧹 Arquivo de status removido")
        except Exception as status_error:
            self.logger.warning(f"⚠️ Erro ao remover arquivo de status: {status_error}")
        
        # Cancelar todas as ordens
        # if self.strategy:
        #     self.logger.info("🚫 Cancelando ordens ativas...")
        #     self.strategy.cancel_all_orders()
        
        # Imprimir relatório final
        if self.start_time:
            uptime = datetime.now() - self.start_time
            self.logger.info(f"⏱️ Tempo de operação: {uptime}")
        
        # Status final
        # if self.position_mgr:
        #     pos_status = self.position_mgr.get_status_summary()
        #     self.logger.info(f"💰 Saldo Final: ${pos_status['account_balance']:,.2f}")
        #     
        #     for symbol, pos in pos_status['positions'].items():
        #         pnl = pos.get('realized_pnl', 0)
        #         self.logger.info(f"📊 {symbol} - PNL Realizado: ${pnl:,.2f}")
        
        self.logger.info("=" * 80)
        self.logger.info("✅ Bot encerrado com sucesso")
        self.logger.info("=" * 80)
    
    def stop(self):
        """Para o bot"""
        self.running = False
    
    def signal_handler(self, signum, frame):
        """Handler para sinais de sistema"""
        self.logger.info(f"🛑 Sinal recebido: {signum}")
        
        # Limpar arquivo de status antes de parar
        try:
            status_file = 'bot_status.json'
            if os.path.exists(status_file):
                os.remove(status_file)
                self.logger.info("🧹 Arquivo de status removido")
        except Exception as status_error:
            self.logger.warning(f"⚠️ Erro ao remover arquivo de status: {status_error}")
        
        self.stop()


def main():
    """Função principal"""
    
    print("=" * 80)
    print("🤖 PACIFICA GRID TRADING BOT")
    print("=" * 80)
    print()
    
    # Verificar arquivo .env
    if not Path('.env').exists():
        print("❌ Arquivo .env não encontrado!")
        print("📝 Crie um arquivo .env com as configurações necessárias")
        return
    
    # Criar e executar bot
    bot = GridTradingBot()
    
    try:
        bot.run()
    except Exception as e:
        print(f"❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n👋 Até logo!")


if __name__ == "__main__":
    main()