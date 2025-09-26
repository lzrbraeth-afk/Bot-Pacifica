"""
Performance Tracker - Sistema de Métricas Avançadas para Grid Trading
Calcula métricas de performance, eficiência do grid e analytics detalhados
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
import statistics

@dataclass
class Trade:
    """Estrutura para armazenar dados de um trade"""
    id: str
    symbol: str
    side: str  # 'buy' ou 'sell'
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    commission: float
    grid_level: int
    
    @property
    def duration_seconds(self) -> float:
        return (self.exit_time - self.entry_time).total_seconds()
    
    @property
    def return_percent(self) -> float:
        if self.side == 'buy':
            return ((self.exit_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.exit_price) / self.entry_price) * 100

@dataclass
class GridExecution:
    """Dados de execução de ordem do grid"""
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    timestamp: datetime
    executed: bool = False
    execution_time: Optional[datetime] = None
    fill_price: Optional[float] = None
    commission: float = 0.0

class PerformanceTracker:
    def __init__(self, symbol: str = "BTC", symbols: List[str] = None):
        self.logger = logging.getLogger('PacificaBot.PerformanceTracker')
        
        # Suporte para símbolos múltiplos (multi-asset) ou único (grid)
        if symbols:
            self.symbol = "MULTI"  # Nome para estratégia multi-asset
            self.symbols = symbols
            self.is_multi_asset = True
        else:
            self.symbol = symbol
            self.symbols = [symbol]
            self.is_multi_asset = False
        self.trades: List[Trade] = []
        self.grid_executions: List[GridExecution] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.daily_pnl: Dict[str, float] = {}
        
        # Métricas em tempo real
        self.session_start = datetime.now()
        self.initial_balance = 0
        self.current_balance = 0
        self.peak_balance = 0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # Configurações
        self.risk_free_rate = 0.02  # 2% ao ano
        self.save_interval = 300  # Salvar dados a cada 5 minutos
        
        # Carregar dados históricos se existirem
        self._load_historical_data()
        
        self.logger.info(f"PerformanceTracker iniciado para {symbol}")
    
    def record_trade(self, trade: Trade) -> None:
        """Registra um trade completo com limitação de memória"""
        self.trades.append(trade)
        self.total_trades += 1
        
        # 🔧 NOVA ADIÇÃO: Limitar tamanho da lista de trades para evitar memory leak
        MAX_TRADES_HISTORY = 1000  # Manter apenas 1000 últimos trades
        if len(self.trades) > MAX_TRADES_HISTORY:
            # Remove 50% quando atinge limite (otimização de performance)
            self.trades = self.trades[-500:]
            self.logger.debug(f"🧹 Lista de trades limitada a 500 entradas para evitar memory leak")
        
        if trade.pnl > 0:
            self.winning_trades += 1
        elif trade.pnl < 0:
            self.losing_trades += 1
        
        # Atualizar PNL diário
        date_key = trade.exit_time.strftime('%Y-%m-%d')
        self.daily_pnl[date_key] = self.daily_pnl.get(date_key, 0) + trade.pnl
        
        # Atualizar curva de equity
        self.current_balance += trade.pnl
        self.equity_curve.append((trade.exit_time, self.current_balance))
        
        # 🔧 NOVA ADIÇÃO: Limitar tamanho da curva de equity
        MAX_EQUITY_HISTORY = 1000  # Manter apenas 1000 últimos pontos
        if len(self.equity_curve) > MAX_EQUITY_HISTORY:
            self.equity_curve = self.equity_curve[-500:]
            self.logger.debug(f"🧹 Curva de equity limitada a 500 entradas para evitar memory leak")
        
        # Atualizar peak para drawdown
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        
        self.logger.info(f"📈 Trade registrado: {trade.symbol} {trade.side} PNL: ${trade.pnl:.2f}")
        
        # Salvar dados periodicamente
        if len(self.trades) % 10 == 0:
            self._save_data()
    
    def record_grid_execution(self, execution: GridExecution) -> None:
        """Registra execução de ordem do grid com limitação de memória"""
        self.grid_executions.append(execution)
        
        # 🔧 NOVA ADIÇÃO: Limitar tamanho da lista de execuções de grid
        MAX_GRID_EXECUTIONS = 500  # Manter apenas 500 últimas execuções
        if len(self.grid_executions) > MAX_GRID_EXECUTIONS:
            # Remove 50% quando atinge limite (otimização de performance)
            self.grid_executions = self.grid_executions[-250:]
            self.logger.debug(f"🧹 Lista de grid executions limitada a 250 entradas para evitar memory leak")
        
        if execution.executed:
            self.logger.debug(f"🎯 Grid executado: {execution.side} @ ${execution.fill_price}")
    
    def update_balance(self, new_balance: float) -> None:
        """Atualiza saldo atual"""
        if self.initial_balance == 0:
            self.initial_balance = new_balance
            self.peak_balance = new_balance
        
        self.current_balance = new_balance
        
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
        
        # Adicionar à curva de equity
        self.equity_curve.append((datetime.now(), new_balance))
        
        # 🔧 NOVA ADIÇÃO: Limitar tamanho da curva de equity (caso update_balance seja chamado diretamente)
        MAX_EQUITY_HISTORY = 1000  # Manter apenas 1000 últimos pontos
        if len(self.equity_curve) > MAX_EQUITY_HISTORY:
            self.equity_curve = self.equity_curve[-500:]
            self.logger.debug(f"🧹 Curva de equity limitada a 500 entradas para evitar memory leak")
    
    def calculate_metrics(self, include_advanced=False):
        """Calcula todas as métricas de performance"""
        if not self.trades:
            return self._empty_metrics()
        
        # Métricas básicas (sempre calculadas)
        metrics = {
            # Métricas básicas
            'total_trades': len(self.trades),
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.calculate_win_rate(),
            
            # Retornos
            'total_return': self.calculate_total_return(),
            'total_return_percent': self.calculate_total_return_percent(),
            'average_trade_pnl': self.calculate_average_trade_pnl(),
            
            # Métricas de grid
            'grid_efficiency': self.calculate_grid_efficiency(),
            'fill_rate': self.calculate_fill_rate(),
            'avg_trade_duration': self.calculate_avg_trade_duration(),
            
            # Métricas de tempo
            'session_duration': self.get_session_duration(),
            'trades_per_day': self.calculate_trades_per_day(),
        }
        
        # Métricas avançadas (só quando solicitadas)
        if include_advanced:
            advanced_metrics = {
                # Métricas de risco (computacionalmente pesadas)
                'sharpe_ratio': self.calculate_sharpe_ratio(),
                'max_drawdown': self.calculate_max_drawdown(),
                'max_drawdown_percent': self.calculate_max_drawdown_percent(),
                'profit_factor': self.calculate_profit_factor(),
                
                # Estatísticas avançadas (requerem mais cálculos)
                'sortino_ratio': self.calculate_sortino_ratio(),
                'calmar_ratio': self.calculate_calmar_ratio(),
                'recovery_factor': self.calculate_recovery_factor(),
            }
            metrics.update(advanced_metrics)
        else:
            # Valores padrão para métricas avançadas quando não calculadas
            advanced_defaults = {
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'max_drawdown_percent': 0.0,
                'profit_factor': 1.0,
                'sortino_ratio': 0.0,
                'calmar_ratio': 0.0,
                'recovery_factor': 0.0,
            }
            metrics.update(advanced_defaults)
        
        return metrics
    
    def calculate_win_rate(self) -> float:
        """Taxa de acerto"""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    def calculate_total_return(self) -> float:
        """Retorno total em USD"""
        return sum(trade.pnl for trade in self.trades)
    
    def calculate_total_return_percent(self) -> float:
        """Retorno total em %"""
        if self.initial_balance == 0:
            return 0.0
        return (self.calculate_total_return() / self.initial_balance) * 100
    
    def calculate_average_trade_pnl(self) -> float:
        """PNL médio por trade"""
        if not self.trades:
            return 0.0
        return statistics.mean(trade.pnl for trade in self.trades)
    
    def calculate_sharpe_ratio(self) -> float:
        """Sharpe Ratio - retorno ajustado pelo risco"""
        if len(self.daily_pnl) < 2:
            return 0.0
        
        daily_returns = list(self.daily_pnl.values())
        
        if not daily_returns:
            return 0.0
        
        avg_return = statistics.mean(daily_returns)
        std_return = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
        
        if std_return == 0:
            return 0.0
        
        # Converter para anualizado
        daily_risk_free = self.risk_free_rate / 365
        sharpe = (avg_return - daily_risk_free) / std_return * (365 ** 0.5)
        
        return sharpe
    
    def calculate_max_drawdown(self) -> float:
        """Máximo drawdown em USD"""
        if not self.equity_curve:
            return 0.0
        
        peak = self.equity_curve[0][1]
        max_dd = 0.0
        
        for timestamp, balance in self.equity_curve:
            if balance > peak:
                peak = balance
            
            drawdown = peak - balance
            if drawdown > max_dd:
                max_dd = drawdown
        
        return max_dd
    
    def calculate_max_drawdown_percent(self) -> float:
        """Máximo drawdown em %"""
        max_dd = self.calculate_max_drawdown()
        if self.peak_balance == 0:
            return 0.0
        return (max_dd / self.peak_balance) * 100
    
    def calculate_profit_factor(self) -> float:
        """Profit Factor - ganhos totais / perdas totais"""
        gross_profit = sum(trade.pnl for trade in self.trades if trade.pnl > 0)
        gross_loss = abs(sum(trade.pnl for trade in self.trades if trade.pnl < 0))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 1.0
        
        return gross_profit / gross_loss
    
    def calculate_grid_efficiency(self) -> float:
        """Eficiência do grid - % de ordens que foram executadas"""
        if not self.grid_executions:
            return 0.0
        
        executed_orders = sum(1 for exec in self.grid_executions if exec.executed)
        total_orders = len(self.grid_executions)
        
        return (executed_orders / total_orders) * 100
    
    def calculate_fill_rate(self) -> float:
        """Taxa de preenchimento das ordens"""
        return self.calculate_grid_efficiency()  # Mesmo cálculo
    
    def calculate_avg_trade_duration(self) -> float:
        """Duração média dos trades em segundos"""
        if not self.trades:
            return 0.0
        
        durations = [trade.duration_seconds for trade in self.trades]
        return statistics.mean(durations)
    
    def get_session_duration(self) -> float:
        """Duração da sessão atual em horas"""
        duration = datetime.now() - self.session_start
        return duration.total_seconds() / 3600
    
    def calculate_trades_per_day(self) -> float:
        """Número de trades por dia"""
        session_hours = self.get_session_duration()
        if session_hours == 0:
            return 0.0
        
        trades_per_hour = len(self.trades) / session_hours
        return trades_per_hour * 24
    
    def calculate_sortino_ratio(self) -> float:
        """Sortino Ratio - como Sharpe mas só considera volatilidade negativa"""
        if len(self.daily_pnl) < 2:
            return 0.0
        
        daily_returns = list(self.daily_pnl.values())
        avg_return = statistics.mean(daily_returns)
        
        # Apenas retornos negativos para downside deviation
        negative_returns = [r for r in daily_returns if r < 0]
        
        if not negative_returns:
            return float('inf') if avg_return > 0 else 0.0
        
        downside_deviation = statistics.stdev(negative_returns)
        daily_risk_free = self.risk_free_rate / 365
        
        return (avg_return - daily_risk_free) / downside_deviation * (365 ** 0.5)
    
    def calculate_calmar_ratio(self) -> float:
        """Calmar Ratio - retorno anual / max drawdown"""
        annual_return = self.calculate_total_return_percent() * (365 / max(1, self.get_session_duration() * 24))
        max_dd_percent = self.calculate_max_drawdown_percent()
        
        if max_dd_percent == 0:
            return float('inf') if annual_return > 0 else 0.0
        
        return annual_return / max_dd_percent
    
    def calculate_recovery_factor(self) -> float:
        """Recovery Factor - lucro líquido / max drawdown"""
        net_profit = self.calculate_total_return()
        max_dd = self.calculate_max_drawdown()
        
        if max_dd == 0:
            return float('inf') if net_profit > 0 else 0.0
        
        return net_profit / max_dd
    
    def get_performance_summary(self, include_advanced=True) -> str:
        """Retorna resumo formatado da performance"""
        metrics = self.calculate_metrics(include_advanced=include_advanced)
        
        summary = f"""
    📊 PERFORMANCE SUMMARY - {self.symbol}
    {'='*50}
    💰 Total Return: ${metrics['total_return']:.2f} ({metrics['total_return_percent']:.2f}%)
    📈 Total Trades: {metrics['total_trades']} | Win Rate: {metrics['win_rate']:.1f}%
    🎯 Grid Efficiency: {metrics['grid_efficiency']:.1f}%
    ⏱️  Avg Trade Duration: {metrics['avg_trade_duration']/60:.1f} min
    ⏰ Session Duration: {metrics['session_duration']:.1f}h"""

        if include_advanced:
            summary += f"""
    ⚡ Sharpe Ratio: {metrics['sharpe_ratio']:.2f}
    📉 Max Drawdown: {metrics['max_drawdown_percent']:.2f}%
    📊 Profit Factor: {metrics['profit_factor']:.2f}"""
        
        summary += f"""
    {'='*50}
            """
        
        return summary
    
    def _empty_metrics(self) -> Dict:
        """Retorna métricas vazias quando não há trades"""
        return {key: 0.0 for key in [
            'total_trades', 'winning_trades', 'losing_trades', 'win_rate',
            'total_return', 'total_return_percent', 'average_trade_pnl',
            'sharpe_ratio', 'max_drawdown', 'max_drawdown_percent', 'profit_factor',
            'grid_efficiency', 'fill_rate', 'avg_trade_duration',
            'session_duration', 'trades_per_day',
            'sortino_ratio', 'calmar_ratio', 'recovery_factor'
        ]}
    
    def _save_data(self) -> None:
        """Salva dados de performance em arquivo"""
        try:
            data_dir = Path("data")
            data_dir.mkdir(exist_ok=True)
            
            # Converter trades para dict para JSON
            trades_data = []
            for trade in self.trades:
                trades_data.append({
                    'id': trade.id,
                    'symbol': trade.symbol,
                    'side': trade.side,
                    'entry_price': trade.entry_price,
                    'exit_price': trade.exit_price,
                    'quantity': trade.quantity,
                    'entry_time': trade.entry_time.isoformat(),
                    'exit_time': trade.exit_time.isoformat(),
                    'pnl': trade.pnl,
                    'commission': trade.commission,
                    'grid_level': trade.grid_level
                })
            
            data = {
                'symbol': self.symbol,
                'session_start': self.session_start.isoformat(),
                'trades': trades_data,
                'daily_pnl': self.daily_pnl,
                'initial_balance': self.initial_balance,
                'peak_balance': self.peak_balance
            }
            
            filename = data_dir / f"performance_{self.symbol}_{datetime.now().strftime('%Y%m%d')}.json"
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug(f"💾 Dados salvos em {filename}")
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao salvar dados: {e}")
    
    def _load_historical_data(self) -> None:
        """Carrega dados históricos se existirem"""
        try:
            data_dir = Path("data")
            if not data_dir.exists():
                return
            
            # Procurar arquivo mais recente
            pattern = f"performance_{self.symbol}_*.json"
            files = list(data_dir.glob(pattern))
            
            if not files:
                return
            
            latest_file = max(files, key=lambda x: x.stat().st_mtime)
            
            with open(latest_file, 'r') as f:
                data = json.load(f)
            
            # Reconstruir trades
            for trade_data in data.get('trades', []):
                trade = Trade(
                    id=trade_data['id'],
                    symbol=trade_data['symbol'],
                    side=trade_data['side'],
                    entry_price=trade_data['entry_price'],
                    exit_price=trade_data['exit_price'],
                    quantity=trade_data['quantity'],
                    entry_time=datetime.fromisoformat(trade_data['entry_time']),
                    exit_time=datetime.fromisoformat(trade_data['exit_time']),
                    pnl=trade_data['pnl'],
                    commission=trade_data['commission'],
                    grid_level=trade_data['grid_level']
                )
                self.trades.append(trade)
            
            self.daily_pnl = data.get('daily_pnl', {})
            self.initial_balance = data.get('initial_balance', 0)
            self.peak_balance = data.get('peak_balance', 0)
            
            # Recalcular contadores
            self.total_trades = len(self.trades)
            self.winning_trades = sum(1 for t in self.trades if t.pnl > 0)
            self.losing_trades = sum(1 for t in self.trades if t.pnl < 0)
            
            self.logger.info(f"📂 Dados históricos carregados: {len(self.trades)} trades")
            
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao carregar dados históricos: {e}")
    
    def export_trades_csv(self, filename: Optional[str] = None) -> str:
        """Export de CSV desativado pelo usuário — função mantida como no-op para compatibilidade."""
        self.logger.info("📄 Export de CSV de trades está desativado (removido conforme solicitado).")
        return ""