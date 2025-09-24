"""
Multi-Asset Scalping Strategy - Integração com o Bot Principal
Versão adaptada para funcionar como uma estratégia dentro do sistema principal
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from src.performance_tracker import PerformanceTracker

class MultiAssetStrategy:
    def __init__(self, auth_client, calculator, position_manager):
        """Inicializa estratégia multi-asset integrada ao bot principal"""
        self.logger = logging.getLogger('PacificaBot.MultiAssetStrategy')
        
        self.auth = auth_client
        self.calculator = calculator  # Pode ser usado para cálculos auxiliares
        self.position_mgr = position_manager
        
        # Configurações específicas do multi-asset
        self.symbols = self._parse_symbols()
        self.position_size_usd = float(os.getenv('POSITION_SIZE_USD', '20'))
        self.leverage = int(os.getenv('LEVERAGE', '10'))
        self.max_concurrent_trades = int(os.getenv('MAX_CONCURRENT_TRADES', '3'))
        self.allow_multiple_per_symbol = os.getenv('ALLOW_MULTIPLE_PER_SYMBOL', 'false').lower() == 'true'
        self.price_change_threshold = float(os.getenv('PRICE_CHANGE_THRESHOLD', '0.3'))
        
        # Configurações de TP/SL
        self.auto_close_enabled = os.getenv('AUTO_CLOSE_ENABLED', 'true').lower() == 'true'
        self.use_api_tp_sl = os.getenv('USE_API_TP_SL', 'true').lower() == 'true'
        self.stop_loss_percent = float(os.getenv('STOP_LOSS_PERCENT', '2.0'))
        self.take_profit_percent = float(os.getenv('TAKE_PROFIT_PERCENT', '1.5'))
        self.trailing_stop_enabled = os.getenv('TRAILING_STOP_ENABLED', 'false').lower() == 'true'
        self.trailing_stop_percent = float(os.getenv('TRAILING_STOP_PERCENT', '0.5'))
        self.max_position_time_minutes = int(os.getenv('MAX_POSITION_TIME_MINUTES', '60'))
        
        # Estado interno
        self.price_history = {}  # {symbol: [prices]}
        self.lot_sizes = {}     # {symbol: lot_size}
        self.active_positions = {}  # {position_id: position_data}
        self.symbol_positions = {}  # {symbol: count}
        
        # TP/SL tracking
        self.position_max_profit = {}    # {position_id: max_profit_seen}
        self.position_trailing_stops = {} # {position_id: trailing_stop_price}
        
        # Performance tracking
        self.performance_tracker = PerformanceTracker(symbols=self.symbols)
        
        # Inicializar estruturas para cada símbolo
        self._initialize_symbols()
        
        self.logger.info("🎯 MultiAssetStrategy inicializada:")
        self.logger.info(f"  Símbolos: {self.symbols}")
        self.logger.info(f"  Posição: ${self.position_size_usd} (leverage: {self.leverage}x)")
        self.logger.info(f"  Max trades: {self.max_concurrent_trades}")
        
    def _parse_symbols(self) -> List[str]:
        """Parse símbolos do .env"""
        symbols_env = os.getenv('SYMBOLS', 'BTC,ETH,SOL')
        
        if symbols_env.upper() == 'AUTO':
            return self._get_priority_symbols()
        else:
            return [s.strip().upper() for s in symbols_env.split(',')]
    
    def _get_priority_symbols(self) -> List[str]:
        """Busca símbolos prioritários da exchange"""
        try:
            prices_data = self.auth.get_prices()
            
            if prices_data and 'data' in prices_data:
                available_symbols = []
                for item in prices_data['data']:
                    symbol = item.get('symbol')
                    if symbol:
                        available_symbols.append(symbol)
                
                # Símbolos prioritários
                priority_list = ['BTC', 'ETH', 'SOL', 'BNB', 'AVAX', 'LTC', 'XRP', 'DOGE']
                found_symbols = [s for s in priority_list if s in available_symbols]
                
                if found_symbols:
                    return found_symbols[:5]  # Máximo 5 símbolos
                else:
                    return available_symbols[:3]  # Fallback
                    
        except Exception as e:
            self.logger.error(f"Erro ao buscar símbolos: {e}")
        
        return ['BTC', 'ETH', 'SOL']  # Fallback padrão
    
    def _initialize_symbols(self):
        """Inicializar estruturas para cada símbolo"""
        for symbol in self.symbols:
            self.price_history[symbol] = []
            self.lot_sizes[symbol] = self._get_lot_size(symbol)
            self.symbol_positions[symbol] = 0
    
    def _get_lot_size(self, symbol: str) -> float:
        """Obter lot_size para um símbolo"""
        try:
            info = self.auth.get_symbol_info(symbol)
            if info and 'lot_size' in info:
                return float(info['lot_size'])
        except Exception as e:
            self.logger.warning(f"Erro ao obter lot_size para {symbol}: {e}")
        
        # Fallback baseado no símbolo
        lot_sizes = {
            'BTC': 0.00001, 'ETH': 0.0001, 'SOL': 0.01,
            'BNB': 0.001, 'AVAX': 0.001, 'LTC': 0.001
        }
        return lot_sizes.get(symbol, 0.001)
    
    def initialize_grid(self, current_price: float) -> bool:
        """Método compatível com o bot principal - inicializa estratégia"""
        self.logger.info("🚀 Inicializando estratégia Multi-Asset Scalping...")
        
        # Atualizar preços iniciais
        try:
            prices = self.auth.get_prices()
            if prices and 'data' in prices:
                for item in prices['data']:
                    symbol = item.get('symbol')
                    price = item.get('mark') or item.get('mid')
                    if symbol in self.symbols and price:
                        self.price_history[symbol] = [float(price)]
                        
            self.logger.info("✅ Preços iniciais carregados")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar: {e}")
            return False
    
    def check_filled_orders(self, current_price: float):
        """Verifica ordens executadas - método compatível"""
        # Para multi-asset, vamos verificar todas as posições ativas
        self._update_all_prices()
        self._check_all_tp_sl()
    
    def check_and_rebalance(self, current_price: float):
        """Rebalancear estratégia - método compatível"""
        # Atualizar preços e verificar sinais
        self._update_all_prices()
        
        # Verificar sinais para todos os símbolos
        for symbol in self.symbols:
            if symbol in self.price_history and len(self.price_history[symbol]) >= 3:
                latest_price = self.price_history[symbol][-1]
                self._check_signals_for_symbol(symbol, latest_price)
    
    def _update_all_prices(self):
        """Atualizar preços de todos os símbolos"""
        try:
            prices = self.auth.get_prices()
            
            if prices and 'data' in prices:
                for item in prices['data']:
                    symbol = item.get('symbol')
                    price = item.get('mark') or item.get('mid')
                    
                    if symbol in self.symbols and price:
                        self._update_price_history(symbol, float(price))
                        
        except Exception as e:
            self.logger.error(f"Erro ao atualizar preços: {e}")
    
    def _update_price_history(self, symbol: str, price: float):
        """Atualizar histórico de preços"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append(price)
        
        # Manter apenas últimos 10 preços
        if len(self.price_history[symbol]) > 10:
            self.price_history[symbol].pop(0)
    
    def _check_signals_for_symbol(self, symbol: str, current_price: float):
        """Verificar sinais de trading para um símbolo"""
        if not self._can_open_position(symbol):
            return
        
        prices = self.price_history[symbol]
        if len(prices) >= 3:
            # Calcular mudança percentual
            price_change = (current_price - prices[-3]) / prices[-3] * 100
            
            if abs(price_change) >= self.price_change_threshold:
                side = 'LONG' if price_change > 0 else 'SHORT'
                self._execute_signal(symbol, side, current_price, abs(price_change))
    
    def _can_open_position(self, symbol: str) -> bool:
        """Verificar se pode abrir nova posição"""
        # Verificar limite total
        if len(self.active_positions) >= self.max_concurrent_trades:
            return False
        
        # Verificar múltiplos por símbolo
        if not self.allow_multiple_per_symbol:
            if self.symbol_positions.get(symbol, 0) > 0:
                return False
        
        # Verificar margem (usando o position manager existente)
        margin_needed = self.position_size_usd / self.leverage
        can_place, _ = self.position_mgr.can_place_order(self.position_size_usd)
        
        return can_place
    
    def _execute_signal(self, symbol: str, side: str, price: float, strength: float):
        """Executar sinal de trading"""
        try:
            self.logger.info(f"🎯 SINAL {side} {symbol} @ ${price:.4f} (força: {strength:.2f}%)")
            
            # Calcular quantidade baseada no lot_size
            lot_size = self.lot_sizes[symbol]
            quantity = max(lot_size, round(self.position_size_usd / price, 8))
            
            # Ajustar para múltiplos do lot_size
            quantity = round(quantity / lot_size) * lot_size
            
            if quantity < lot_size:
                self.logger.warning(f"⚠️ Quantidade muito pequena: {quantity} < {lot_size}")
                return
            
            # Determinar lado da ordem
            order_side = 'bid' if side == 'LONG' else 'ask'
            
            # Executar ordem
            result = self.auth.create_order(
                symbol=symbol,
                side=order_side,
                amount=str(quantity),
                price=str(price),
                order_type='GTC'
            )
            
            if result and result.get('success'):
                order_id = result.get('data', {}).get('order_id')
                position_id = f"{symbol}_{int(time.time())}"
                
                # Salvar posição
                self.active_positions[position_id] = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity,
                    'price': price,
                    'order_id': order_id,
                    'timestamp': datetime.now()
                }
                
                self.symbol_positions[symbol] = self.symbol_positions.get(symbol, 0) + 1
                
                self.logger.info(f"✅ Posição aberta: {symbol} {side} {quantity} @ ${price:.4f}")
                
                # Configurar TP/SL se habilitado
                if self.auto_close_enabled and self.use_api_tp_sl:
                    self._setup_tp_sl(position_id, symbol, side, price, quantity)
                
            else:
                self.logger.error(f"❌ Falha ao abrir posição: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao executar sinal: {e}")
    
    def _setup_tp_sl(self, position_id: str, symbol: str, side: str, entry_price: float, quantity: float):
        """Configurar TP/SL via API"""
        try:
            if side == 'LONG':
                tp_price = entry_price * (1 + self.take_profit_percent / 100)
                sl_price = entry_price * (1 - self.stop_loss_percent / 100)
            else:  # SHORT
                tp_price = entry_price * (1 - self.take_profit_percent / 100)
                sl_price = entry_price * (1 + self.stop_loss_percent / 100)
            
            # Criar ordem de Take Profit
            tp_result = self.auth.create_order(
                symbol=symbol,
                side='ask' if side == 'LONG' else 'bid',
                amount=str(quantity),
                price=str(tp_price),
                order_type='TAKE_PROFIT',
                reduce_only=True
            )
            
            # Criar ordem de Stop Loss
            sl_result = self.auth.create_order(
                symbol=symbol,
                side='ask' if side == 'LONG' else 'bid',
                amount=str(quantity),
                price=str(sl_price),
                order_type='STOP_LOSS',
                reduce_only=True
            )
            
            if tp_result and tp_result.get('success'):
                self.logger.info(f"✅ TP configurado: ${tp_price:.4f}")
            if sl_result and sl_result.get('success'):
                self.logger.info(f"✅ SL configurado: ${sl_price:.4f}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao configurar TP/SL: {e}")
    
    def _check_all_tp_sl(self):
        """Verificar TP/SL de todas as posições (se não usando API nativa)"""
        if self.use_api_tp_sl:
            return  # TP/SL gerenciado pela API
        
        # Implementar monitoramento manual se necessário
        pass
    
    def get_grid_status(self) -> Dict:
        """Retornar status compatível com o bot principal"""
        return {
            'active': len(self.active_positions) > 0,
            'center_price': 0,  # N/A para multi-asset
            'active_orders': len(self.active_positions)
        }
    
    def get_performance_metrics(self) -> Dict:
        """Retornar métricas de performance"""
        try:
            if hasattr(self.performance_tracker, 'get_metrics'):
                base_metrics = self.performance_tracker.get_metrics()
            else:
                base_metrics = {}
            
            # Adicionar métricas específicas do multi-asset
            return {
                **base_metrics,
                'active_positions': len(self.active_positions),
                'symbols_trading': len([s for s, count in self.symbol_positions.items() if count > 0]),
                'strategy_type': 'multi_asset_scalping'
            }
        except Exception as e:
            self.logger.error(f"Erro ao obter métricas: {e}")
            return {}
    
    def print_performance_summary(self):
        """Imprimir resumo de performance"""
        self.logger.info("📊 MULTI-ASSET PERFORMANCE SUMMARY:")
        self.logger.info(f"  Posições Ativas: {len(self.active_positions)}")
        self.logger.info(f"  Símbolos Ativos: {len([s for s, c in self.symbol_positions.items() if c > 0])}")
        
        for symbol, count in self.symbol_positions.items():
            if count > 0:
                latest_price = self.price_history.get(symbol, [0])[-1] if self.price_history.get(symbol) else 0
                self.logger.info(f"    {symbol}: {count} posições @ ${latest_price:.4f}")