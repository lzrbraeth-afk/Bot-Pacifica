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
from src.performance_tracker import PerformanceTracker

class GridTradingBot:
    def __init__(self):
        # Carregar configurações
        load_dotenv()
        
        # Setup logging
        self.setup_logging()
        self.logger = logging.getLogger('PacificaBot.Main')
        
        # Estado do bot
        self.running = False
        self.start_time = None
        
        # Configurações
        self.symbol = os.getenv('SYMBOL', 'BTC')
        self.rebalance_interval = int(os.getenv('REBALANCE_INTERVAL_SECONDS', '60'))
        self.check_balance = os.getenv('CHECK_BALANCE_BEFORE_ORDER', 'true').lower() == 'true'
        
        self.logger.info("=" * 80)
        self.logger.info("🤖 PACIFICA GRID TRADING BOT")
        self.logger.info("=" * 80)
        self.logger.info(f"Símbolo: {self.symbol}")
        self.logger.info(f"Intervalo de Rebalanceamento: {self.rebalance_interval}s")
        self.logger.info("=" * 80)
        
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
            
            # Inicializar strategy
            self.strategy = GridStrategy(self.auth, self.calculator, self.position_mgr)
            
            self.logger.info("✅ Componentes inicializados")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar componentes: {e}")
            return False
    
    def _clean_old_orders(self):
        """Cancela todas as ordens abertas do símbolo"""
        try:
            open_orders = self.auth.get_open_orders(self.symbol)
            
            if open_orders:
                self.logger.info(f"🚫 Cancelando {len(open_orders)} ordens antigas...")
                
                for order in main_orders:
                    order_id = order.get('order_id')
                    if order_id:
                        self.auth.cancel_order(str(order_id))
                        time.sleep(0.1)  # Pequeno delay entre cancelamentos
                
                self.logger.info("✅ Ordens antigas canceladas")
        except Exception as e:
            self.logger.error(f"⚠️ Erro ao limpar ordens: {e}")
    
    def get_current_price(self) -> float:
        """Obtém preço atual do mercado"""
        
        try:
            # Usar método real da API
            prices = self.auth.get_prices()
            
            if prices and isinstance(prices, dict):
                # API retorna {"success": true, "data": [...]}
                if prices.get('success') and 'data' in prices:
                    data = prices['data']
                    
                    if isinstance(data, list):
                        for item in data:
                            if item.get('symbol') == self.symbol:
                                # Preço está em 'mark' ou 'mid'
                                price = item.get('mark') or item.get('mid')
                                if price:
                                    return float(price)
            
            self.logger.warning("⚠️ Não foi possível obter preço da API")
            return 0
        
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter preço: {e}")
            return 0
    
    def run(self):
        """Loop principal do bot"""
        
        self.logger.info("🚀 Iniciando Grid Trading Bot...")
        
        # Inicializar componentes
        if not self.initialize_components():
            self.logger.error("❌ Falha na inicialização - abortando")
            return
        
        # Inicializando teste de symbol info
        self.logger.info(f"🔍 Testando market info para {self.symbol}...")
        test_info = self.auth.get_symbol_info(self.symbol)
        if test_info:
            self.logger.info(f"✅ tick_size={test_info.get('tick_size')}, lot_size={test_info.get('lot_size')}")

        
        # Obter preço inicial
        current_price = self.get_current_price()
        if current_price == 0:
            self.logger.error("❌ Não foi possível obter preço inicial")
            return
        
        self.logger.info(f"💰 Preço inicial {self.symbol}: ${current_price:,.2f}")
        
        # Verificar saldo se configurado
        if self.check_balance:
            self.logger.info("💳 Verificando saldo da conta...")
            if not self.position_mgr.update_account_state():
                self.logger.error("❌ Falha ao verificar saldo")
                return
        
        # Inicializar grid
        self.logger.info("🎯 Inicializando grid...")
        if not self.strategy.initialize_grid(current_price):
            self.logger.error("❌ Falha ao inicializar grid")
            return
        
        # Verificar se grid foi criado ou retomado
        grid_status = self.strategy.get_grid_status()
        if grid_status['active_orders'] > 0:
            self.logger.info(f"♻️ Grid retomado com {grid_status['active_orders']} ordens existentes")
        else:
            self.logger.info(f"🆕 Novo grid criado com {grid_status['active_orders']} ordens")
        
        # 🔧 CORREÇÃO: Mover para FORA do if/else
        self.running = True
        self.start_time = datetime.now()
        
        self.logger.info("✅ Bot operando!")
        self.logger.info("=" * 80)
        
        # Loop principal
        iteration = 0
        last_rebalance = time.time()
        last_price_check = time.time()
        current_price = self.get_current_price()  # 🔧 Já pegar o preço aqui
        
        while self.running:
            try:
                iteration += 1
                current_time = time.time()

                # 🔧 Obter preço apenas a cada x segundos (configurável)
                if current_time - last_price_check >= 30:
                    new_price = self.get_current_price()
                    if new_price > 0:
                        current_price = new_price
                    last_price_check = current_time
                
                # Log de heartbeat
                if iteration % 10 == 0:
                    uptime = datetime.now() - self.start_time
                    self.logger.info(f"💓 Heartbeat #{iteration} - Uptime: {uptime} | Preço: ${current_price:,.2f}")
                
                # Verificar margem
                if self.check_balance and iteration % 5 == 0:
                    # is_safe, msg = self.position_mgr.check_margin_safety()
                    # if not is_safe:
                    #     self.logger.warning(f"⚠️ {msg}")
                    pass
                
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
                
                # Rebalancear grid se necessário
                if current_time - last_rebalance >= self.rebalance_interval:
                    self.logger.info(f"🔄 Verificando rebalanceamento em ${current_price:,.2f}")
                    try:
                        self.strategy.check_and_rebalance(current_price)
                    except Exception as e:
                        self.logger.warning(f"⚠️ Erro no rebalanceamento: {e}")
                        # Não para o bot - apenas continua
                    last_rebalance = current_time 
                        
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
        
        # Status do grid
        grid_status = self.strategy.get_grid_status()
        self.logger.info(f"Grid Ativo: {grid_status['active']}")
        self.logger.info(f"Preço Central: ${grid_status['center_price']:,.2f}")
        self.logger.info(f"Ordens Ativas: {grid_status['active_orders']}")
        
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
            
            # Exportar trades para CSV
            try:
                csv_file = self.strategy.performance_tracker.export_trades_csv()
                self.logger.info(f"📄 Trades exportados para: {csv_file}")
            except Exception as e:
                self.logger.warning(f"⚠️ Erro ao exportar trades: {e}")
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