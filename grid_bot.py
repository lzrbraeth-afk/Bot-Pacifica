"""
Pacifica Grid Trading Bot - Sistema Principal
Executa estratégias de Grid Trading (Pure Grid e Market Making)
"""

import os
import sys
import time
import signal
import logging
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
from src.performance_tracker import PerformanceTracker
from src.strategy_logger import create_strategy_logger, get_strategy_specific_messages

class GridTradingBot:
    def __init__(self):
        # Carregar configurações
        load_dotenv()
        
        # Determinar tipo de estratégia - APENAS UMA VARIÁVEL: STRATEGY_TYPE
        strategy_type_env = os.getenv('STRATEGY_TYPE', 'market_making').lower()
        
        # Mapear todas as estratégias via STRATEGY_TYPE
        if strategy_type_env == 'multi_asset':
            self.strategy_type = 'multi_asset'
        elif strategy_type_env == 'multi_asset_enhanced':
            self.strategy_type = 'multi_asset_enhanced'
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
        self.rebalance_interval = int(os.getenv('REBALANCE_INTERVAL_SECONDS', '60'))
        self.check_balance = os.getenv('CHECK_BALANCE_BEFORE_ORDER', 'true').lower() == 'true'
        
        # ✨ NOVA FUNCIONALIDADE: Reset periódico do grid
        self.enable_periodic_reset = os.getenv('ENABLE_PERIODIC_GRID_RESET', 'false').lower() == 'true'
        self.grid_reset_interval = int(os.getenv('GRID_RESET_INTERVAL_MINUTES', '60')) * 60  # Converter para segundos
        
        # Headers específicos por estratégia
        self.show_strategy_header()
        
        # Inicializar componentes
        self.auth = None
        self.calculator = None
        self.position_mgr = None
        self.strategy = None
        
        # Setup signal handlers para shutdown gracioso
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def show_strategy_header(self):
        """Mostrar cabeçalho específico da estratégia"""
        
        self.logger.info("=" * 80, force=True)
        self.logger.info("🤖 PACIFICA TRADING BOT", force=True)
        self.logger.info("=" * 80, force=True)
        
        if self.strategy_type == 'grid':
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
        
        # Inicializar componentes
        self.auth = None
        self.calculator = None
        self.position_mgr = None
        self.strategy = None
        
        # Setup signal handlers para shutdown gracioso
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
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
    
    def initialize_components(self) -> bool:
        """Inicializa todos os componentes do bot"""
        
        try:
            self.logger.info("🔧 Inicializando componentes...")
            
            # Inicializar autenticação
            self.auth = PacificaAuth()

            #  Limpar ordens antigas
            clean_on_start = os.getenv('CLEAN_ORDERS_ON_START', 'false').lower() == 'true'
            if clean_on_start:
                self.logger.warning("🧹 Limpando ordens antigas...")
                self._clean_old_orders()
            
            # Inicializar calculator COM auth para buscar market info
            self.calculator = GridCalculator(auth_client=self.auth)  # PASSAR AUTH
            
            # Inicializar position manager
            self.position_mgr = PositionManager(self.auth)
            
            # Inicializar strategy baseada no tipo configurado
            if self.strategy_type == 'multi_asset':
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
            
            self.logger.info("✅ Componentes inicializados")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar componentes: {e}")
            return False
    
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
    
    def run(self):
        """Loop principal do bot"""
        
        self.logger.info("🚀 Iniciando Grid Trading Bot...")
        
        # Inicializar componentes
        if not self.initialize_components():
            self.logger.error("❌ Falha na inicialização - abortando")
            return
        
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
        
        # 🔧 CORREÇÃO: Mover para FORA do if/else
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
        
        # Inicializar current_price baseado na estratégia
        if self.strategy_type == 'grid':
            current_price = self.get_current_price()  # Grid usa preço único
        else:
            current_price = 0  # Multi-asset não usa preço único
        
        while self.running:
            try:
                iteration += 1
                current_time = time.time()

                # 🔧 Obter preço apenas para estratégia grid com tratamento robusto
                if self.strategy_type == 'grid' and current_time - last_price_check >= 30:
                    new_price = self.get_current_price()
                    if new_price > 0:
                        current_price = new_price
                    else:
                        self.logger.warning("⚠️ Falha ao atualizar preço - mantendo preço anterior")
                    last_price_check = current_time
                
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
                    
                    # ========== ✅ ADICIONAR VERIFICAÇÃO DE MARGEM ==========
                    # Verificar margem ANTES de rebalancear
                    self.position_mgr.update_account_state()
                    
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
                    # ========== FIM DO BLOCO ==========
                    
                    if self.strategy_type == 'grid':
                        self.logger.info(f"🔄 Verificando rebalanceamento em ${current_price:,.2f}")
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

                # Relatório detalhado a cada 10 minutos
                if iteration % 600 == 0:
                    self.print_detailed_performance()
                
                # Aguardar próxima iteração
                time.sleep(1)
                
            except KeyboardInterrupt:
                self.logger.info("⌨️ Interrompido pelo usuário")
                break
            
            except Exception as e:
                self.logger.error(f"❌ Erro no loop principal: {e}")
                time.sleep(5)  # Aguardar antes de continuar
        
        # Shutdown
        self.logger.info("🏁 Encerrando bot...")
        self.shutdown()
    
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
                
        else:
            self.logger.warning("⚠️ Performance tracker não disponível")
    
    def shutdown(self):
        """Encerra o bot graciosamente"""
        
        self.logger.info("🔄 Iniciando shutdown...")
        
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