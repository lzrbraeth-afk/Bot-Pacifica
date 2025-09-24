"""
Multi-Asset Enhanced Strategy - Versão com Algoritmo de Sinais Melhorado
Estratégia separada que usa análise técnica avançada para identificar oportunidades
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from src.performance_tracker import PerformanceTracker
from src.strategy_logger import create_strategy_logger
from src.enhanced_signal_detector import EnhancedSignalDetector

class MultiAssetEnhancedStrategy:
    def __init__(self, auth_client, calculator, position_manager):
        """Inicializa estratégia multi-asset com algoritmo de sinais melhorado"""
        self.logger = create_strategy_logger('PacificaBot.MultiAssetEnhanced', 'multi_asset_enhanced')
        
        self.auth = auth_client
        self.calculator = calculator
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
        
        # 🆕 CONFIGURAÇÕES ESPECÍFICAS DO ALGORITMO MELHORADO
        self.enhanced_min_signal_quality = int(os.getenv('ENHANCED_MIN_SIGNAL_QUALITY', '60'))  # 0-100
        self.enhanced_min_confidence = int(os.getenv('ENHANCED_MIN_CONFIDENCE', '70'))  # 0-100
        self.enhanced_use_rsi_filter = os.getenv('ENHANCED_USE_RSI_FILTER', 'true').lower() == 'true'
        self.enhanced_max_volatility = float(os.getenv('ENHANCED_MAX_VOLATILITY', '5.0'))  # %
        self.enhanced_min_history = int(os.getenv('ENHANCED_MIN_HISTORY', '20'))  # períodos
        
        # Estado interno
        self.price_history = {}  # {symbol: [prices]} - Histórico expandido
        self.lot_sizes = {}     # {symbol: lot_size}
        self.active_positions = {}  # {position_id: position_data}
        self.symbol_positions = {}  # {symbol: count}
        
        # 🆕 DETECTOR DE SINAIS MELHORADO
        self.signal_detector = EnhancedSignalDetector(self.logger)
        self.signal_detector.min_signal_quality = self.enhanced_min_signal_quality
        
        # Estatísticas da estratégia
        self.signals_detected = 0
        self.signals_executed = 0
        self.signals_rejected_quality = 0
        self.signals_rejected_limits = 0
        
        # TP/SL tracking
        self.position_max_profit = {}
        self.position_trailing_stops = {}
        
        # Performance tracking
        self.performance_tracker = PerformanceTracker(
            symbols=self.symbols if len(self.symbols) <= 5 else self.symbols[:5]
        )
        
        self.logger.strategy_info(f"Enhanced Multi-Asset inicializada com {len(self.symbols)} símbolos")
        self.logger.info(f"🧠 Algoritmo melhorado: Quality ≥ {self.enhanced_min_signal_quality}, Confidence ≥ {self.enhanced_min_confidence}")
        
    def _parse_symbols(self) -> List[str]:
        """Parse dos símbolos do .env"""
        symbols_str = os.getenv('SYMBOLS', 'BTC,ETH,SOL')
        if symbols_str.upper() == 'AUTO':
            return self._get_all_available_symbols()
        else:
            return [s.strip() for s in symbols_str.split(',')]
    
    def _get_all_available_symbols(self) -> List[str]:
        """Busca todos os símbolos disponíveis da API"""
        try:
            # Implementar busca de símbolos da API
            pass
        except:
            return ['BTC', 'ETH', 'SOL']
    
    def get_lot_size(self, symbol: str) -> float:
        """Obtém lot size para o símbolo"""
        lot_sizes = {
            'BTC': 0.00001, 'ETH': 0.0001, 'SOL': 0.01, 'AVAX': 0.01,
            'DOGE': 1, 'ADA': 1, 'MATIC': 0.1, 'DOT': 0.1,
            'LINK': 0.1, 'UNI': 0.1, 'AAVE': 0.01, 'ATOM': 0.01
        }
        return lot_sizes.get(symbol, 0.001)
    
    def initialize_grid(self, current_price: float) -> bool:
        """Método compatível com o bot principal - inicializa estratégia"""
        self.logger.strategy_info("Inicializando Enhanced Multi-Asset Strategy...")
        
        try:
            # Inicializar histórico de preços expandido
            prices = self.auth.get_prices()
            if prices and 'data' in prices:
                for item in prices['data']:
                    symbol = item.get('symbol')
                    price = item.get('mark') or item.get('mid')
                    if symbol in self.symbols and price:
                        # Inicializar com preço atual (histórico será construído)
                        self.price_history[symbol] = [float(price)]
                        
            self.logger.info(f"✅ Preços iniciais carregados para {len(self.price_history)} símbolos")
            
            # Log das configurações melhoradas
            status = self.signal_detector.get_algorithm_status()
            self.logger.info(f"🧠 Algoritmo: {status['version']} com {len(status['indicators'])} indicadores")
            self.logger.info(f"🎯 Pesos: Momentum={status['weights']['momentum']}% | Trend={status['weights']['trend']}% | RSI={status['weights']['rsi']}%")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar Enhanced Strategy: {e}")
            return False
    
    def check_filled_orders(self, current_price: float):
        """Verifica ordens executadas e analisa sinais - método compatível"""
        try:
            # 1. Verificar ordens preenchidas (mesmo processo da versão original)
            self._check_filled_orders_internal()
            
            # 2. Atualizar histórico de preços
            self._update_price_history()
            
            # 3. 🆕 ANÁLISE DE SINAIS MELHORADA
            self._analyze_market_signals()
            
            # 4. Verificar TP/SL manual se habilitado
            if not self.use_api_tp_sl:
                self._check_all_tp_sl()
                
        except Exception as e:
            self.logger.error(f"❌ Erro no check_filled_orders: {e}")
    
    def _check_filled_orders_internal(self):
        """Lógica interna de verificação de ordens preenchidas"""
        # Implementar verificação de ordens preenchidas
        # (mesmo processo da estratégia original)
        pass
    
    def _update_price_history(self):
        """Atualiza histórico de preços para análise técnica"""
        try:
            prices_data = self.auth.get_prices()
            if not prices_data or not prices_data.get('success'):
                return
                
            for item in prices_data.get('data', []):
                symbol = item.get('symbol')
                price = item.get('mark') or item.get('mid')
                
                if symbol in self.symbols and price:
                    current_price = float(price)
                    
                    if symbol not in self.price_history:
                        self.price_history[symbol] = []
                    
                    # Adicionar novo preço
                    self.price_history[symbol].append(current_price)
                    
                    # 🆕 MANTER HISTÓRICO EXPANDIDO (50 períodos para análise técnica)
                    max_history = max(50, self.enhanced_min_history + 10)
                    if len(self.price_history[symbol]) > max_history:
                        self.price_history[symbol].pop(0)
                        
        except Exception as e:
            self.logger.error(f"❌ Erro ao atualizar histórico de preços: {e}")
    
    def _analyze_market_signals(self):
        """🆕 ANÁLISE DE SINAIS COM ALGORITMO MELHORADO"""
        
        for symbol in self.symbols:
            if symbol not in self.price_history:
                continue
                
            try:
                current_price = self.price_history[symbol][-1]
                
                # 🧠 USAR DETECTOR MELHORADO
                signal = self.signal_detector.detect_signal(
                    symbol=symbol,
                    price_history=self.price_history[symbol],
                    current_price=current_price,
                    price_change_threshold=self.price_change_threshold
                )
                
                if signal:
                    self.signals_detected += 1
                    
                    # Verificar confiança mínima
                    if signal['confidence'] >= self.enhanced_min_confidence:
                        
                        # Verificar se pode executar
                        if self._can_execute_enhanced_signal(symbol, signal):
                            self._execute_enhanced_signal(symbol, signal)
                            self.signals_executed += 1
                        else:
                            self.signals_rejected_limits += 1
                    else:
                        self.signals_rejected_quality += 1
                        self.logger.debug(f"📊 {symbol}: Sinal rejeitado - Confidence {signal['confidence']} < {self.enhanced_min_confidence}")
                        
            except Exception as e:
                self.logger.error(f"❌ Erro ao analisar {symbol}: {e}")
    
    def _can_execute_enhanced_signal(self, symbol: str, signal: Dict) -> bool:
        """Verifica se pode executar sinal com validações adicionais"""
        
        # 1. Verificações básicas (mesmo da versão original)
        if len(self.active_positions) >= self.max_concurrent_trades:
            return False
        
        if not self.allow_multiple_per_symbol:
            if self.symbol_positions.get(symbol, 0) > 0:
                return False
        
        # 2. Verificar margem
        margin_needed = self.position_size_usd / self.leverage
        can_place, _ = self.position_mgr.can_place_order(self.position_size_usd)
        
        if not can_place:
            return False
        
        # 3. 🆕 FILTROS ADICIONAIS PARA ALGORITMO MELHORADO
        
        # Filtro de volatilidade extrema
        if signal['volatility'] > self.enhanced_max_volatility:
            self.logger.debug(f"📊 {symbol}: Rejeitado - volatilidade alta ({signal['volatility']:.2f}%)")
            return False
        
        # Filtro RSI se habilitado
        if self.enhanced_use_rsi_filter:
            rsi = signal['rsi']
            side = signal['side']
            
            # Evitar comprar em overbought ou vender em oversold
            if (side == 'LONG' and rsi > 80) or (side == 'SHORT' and rsi < 20):
                self.logger.debug(f"📊 {symbol}: Rejeitado - RSI extremo ({rsi:.1f})")
                return False
        
        return True
    
    def _execute_enhanced_signal(self, symbol: str, signal: Dict):
        """🆕 EXECUTA SINAL COM INFORMAÇÕES DETALHADAS"""
        
        try:
            side = signal['side']
            current_price = self.price_history[symbol][-1]
            quality_score = signal['quality_score']
            confidence = signal['confidence']
            
            # Log melhorado usando métodos específicos Enhanced
            self.logger.enhanced_signal(symbol, quality_score, confidence/100, side)
            
            # Detalhes técnicos usando enhanced_analysis
            indicators = {
                'Momentum': f"{signal['momentum']:.2f}%",
                'Trend': signal['trend'],
                'RSI': f"{signal['rsi']:.1f}",
                'Volatility': f"{signal['volatility']:.2f}%"
            }
            self.logger.enhanced_analysis(symbol, indicators)
            
            # Calcular quantidade ajustada pela confiança do sinal
            base_quantity = self.position_size_usd / current_price
            lot_size = self.get_lot_size(symbol)
            
            # 🆕 AJUSTE DE TAMANHO POR CONFIANÇA
            confidence_multiplier = min(1.2, confidence / 100 + 0.2)  # 0.2 a 1.2
            adjusted_quantity = base_quantity * confidence_multiplier
            quantity = max(lot_size, round(adjusted_quantity / lot_size) * lot_size)
            
            self.logger.info(f"   💰 Quantity: {quantity} (ajustada por confidence: {confidence_multiplier:.2f}x)")
            
            # Determinar lado da ordem
            order_side = 'bid' if side == 'LONG' else 'ask'
            
            # Preparar TP/SL se habilitado
            take_profit_config = None
            stop_loss_config = None
            
            if self.auto_close_enabled and self.use_api_tp_sl:
                if side == 'LONG':
                    tp_stop_price = round(current_price * (1 + self.take_profit_percent / 100), 4)
                    tp_limit_price = round(tp_stop_price * 0.999, 4)
                    sl_stop_price = round(current_price * (1 - self.stop_loss_percent / 100), 4)
                    sl_limit_price = round(sl_stop_price * 1.001, 4)
                else:  # SHORT
                    tp_stop_price = round(current_price * (1 - self.take_profit_percent / 100), 4)
                    tp_limit_price = round(tp_stop_price * 1.001, 4)
                    sl_stop_price = round(current_price * (1 + self.stop_loss_percent / 100), 4)
                    sl_limit_price = round(sl_stop_price * 0.999, 4)
                
                take_profit_config = {
                    "stop_price": tp_stop_price,
                    "limit_price": tp_limit_price
                }
                
                stop_loss_config = {
                    "stop_price": sl_stop_price,
                    "limit_price": sl_limit_price
                }
                
                self.logger.info(f"🎯 TP/SL: TP@${tp_stop_price:.4f}, SL@${sl_stop_price:.4f}")
            
            # Executar ordem com TP/SL integrado
            result = self.auth.create_order(
                symbol=symbol,
                side=order_side,
                amount=str(quantity),
                price=str(current_price),
                order_type='GTC',
                take_profit=take_profit_config,
                stop_loss=stop_loss_config
            )
            
            if result and result.get('success'):
                order_id = result.get('data', {}).get('order_id')
                position_id = f"{symbol}_{int(time.time())}"
                
                # Salvar posição com dados do sinal
                self.active_positions[position_id] = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity,
                    'price': current_price,
                    'order_id': order_id,
                    'timestamp': datetime.now(),
                    # 🆕 DADOS DO SINAL MELHORADO
                    'signal_quality': quality_score,
                    'signal_confidence': confidence,
                    'signal_momentum': signal['momentum'],
                    'signal_trend': signal['trend'],
                    'signal_rsi': signal['rsi'],
                    'signal_volatility': signal['volatility']
                }
                
                self.symbol_positions[symbol] = self.symbol_positions.get(symbol, 0) + 1
                
                self.logger.strategy_info(f"✅ Posição Enhanced aberta: {symbol} {side} {quantity} @ ${current_price:.4f}")
                
            else:
                self.logger.error(f"❌ Falha ao executar sinal Enhanced: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao executar sinal Enhanced: {e}")
    
    def _check_all_tp_sl(self):
        """Verificar TP/SL manual (mesmo da versão original)"""
        # Implementar verificação manual de TP/SL se necessário
        pass
    
    def get_grid_status(self) -> Dict:
        """Retornar status compatível com o bot principal"""
        return {
            'active': len(self.active_positions) > 0,
            'center_price': 0,
            'active_orders': len(self.active_positions)
        }
    
    def get_enhanced_statistics(self) -> Dict:
        """🆕 ESTATÍSTICAS ESPECÍFICAS DA VERSÃO MELHORADA"""
        
        total_signals = self.signals_detected
        success_rate = (self.signals_executed / total_signals * 100) if total_signals > 0 else 0
        
        return {
            'algorithm_version': 'enhanced_v2.0',
            'signals_detected': self.signals_detected,
            'signals_executed': self.signals_executed,
            'signals_rejected_quality': self.signals_rejected_quality,
            'signals_rejected_limits': self.signals_rejected_limits,
            'execution_rate': f"{success_rate:.1f}%",
            'active_positions': len(self.active_positions),
            'symbols_monitored': len(self.price_history),
            'min_signal_quality': self.enhanced_min_signal_quality,
            'min_confidence': self.enhanced_min_confidence,
            'history_length': {symbol: len(prices) for symbol, prices in self.price_history.items()}
        }
    
    def get_performance_metrics(self) -> Dict:
        """Compatibilidade com grid_bot.py - métricas básicas de performance"""
        
        # Usar performance_tracker se disponível
        if hasattr(self, 'performance_tracker') and self.performance_tracker:
            try:
                # Tentar usar métricas do performance_tracker
                total_trades = len(self.performance_tracker.trades)
                win_rate = 0
                total_return = 0
                
                if total_trades > 0:
                    wins = sum(1 for trade in self.performance_tracker.trades if trade.pnl > 0)
                    win_rate = (wins / total_trades) * 100
                    total_return = sum(trade.pnl for trade in self.performance_tracker.trades)
                
                return {
                    'total_trades': total_trades,
                    'win_rate': win_rate,
                    'total_return': total_return,
                    'sharpe_ratio': 0.0,  # Não implementado ainda
                    'max_drawdown_percent': 0.0,  # Não implementado ainda
                    # Métricas específicas Enhanced
                    'signals_detected': self.signals_detected,
                    'signals_executed': self.signals_executed,
                    'execution_rate': (self.signals_executed / self.signals_detected * 100) if self.signals_detected > 0 else 0,
                    'algorithm_version': 'enhanced_v2.0'
                }
            except Exception as e:
                self.logger.error(f"Erro ao calcular métricas do performance_tracker: {e}")
        
        # Fallback para métricas básicas Enhanced
        return {
            'total_trades': len(self.active_positions),
            'win_rate': 0.0,  # Sem dados históricos ainda
            'total_return': 0.0,  # Sem dados históricos ainda  
            'sharpe_ratio': 0.0,
            'max_drawdown_percent': 0.0,
            # Métricas específicas Enhanced
            'signals_detected': self.signals_detected,
            'signals_executed': self.signals_executed,
            'execution_rate': (self.signals_executed / self.signals_detected * 100) if self.signals_detected > 0 else 0,
            'algorithm_version': 'enhanced_v2.0'
        }
    
    def log_performance_summary(self):
        """Log resumo de performance da estratégia melhorada"""
        
        stats = self.get_enhanced_statistics()
        
        self.logger.info("📊 ENHANCED MULTI-ASSET PERFORMANCE:")
        self.logger.info(f"   🎯 Sinais detectados: {stats['signals_detected']}")
        self.logger.info(f"   ✅ Sinais executados: {stats['signals_executed']}")
        self.logger.info(f"   📈 Taxa de execução: {stats['execution_rate']}")
        self.logger.info(f"   🔍 Qualidade mínima: {stats['min_signal_quality']}/100")
        self.logger.info(f"   💪 Confiança mínima: {stats['min_confidence']}/100")
    
    def print_performance_summary(self):
        """Compatibilidade com grid_bot.py - imprimir resumo de performance"""
        
        # Usar performance_tracker se disponível  
        if hasattr(self, 'performance_tracker') and self.performance_tracker:
            try:
                summary = self.performance_tracker.get_performance_summary(include_advanced=True)
                self.logger.info("📊 PERFORMANCE TRACKER:")
                self.logger.info(summary)
            except Exception as e:
                self.logger.error(f"Erro ao gerar resumo do performance_tracker: {e}")
        
        # Sempre mostrar métricas Enhanced específicas
        self.log_performance_summary()