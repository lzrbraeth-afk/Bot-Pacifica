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
from src.strategy_logger import create_strategy_logger

class MultiAssetStrategy:
    def __init__(self, auth_client, calculator, position_manager):
        """Inicializa estratégia multi-asset integrada ao bot principal"""
        self.logger = create_strategy_logger('PacificaBot.MultiAssetStrategy', 'multi_asset')
        
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
        self.stop_loss_percent = float(os.getenv('STOP_LOSS_PERCENT', '1.5'))   # ✅ Limite de perda menor
        self.take_profit_percent = float(os.getenv('TAKE_PROFIT_PERCENT', '2.0')) # ✅ Meta de lucro maior
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
        """Obter lot_size para um símbolo com validação detalhada"""
        try:
            info = self.auth.get_symbol_info(symbol)
            if info and 'lot_size' in info:
                lot_size = float(info['lot_size'])
                tick_size = float(info.get('tick_size', 0.01))
                
                # ✅ LOG DETALHADO DE VALIDAÇÃO (como esperado pelo usuário)
                self.logger.info(f"✅ {symbol} encontrado: tick_size={tick_size}, lot_size={lot_size}")
                return lot_size
        except Exception as e:
            self.logger.warning(f"Erro ao obter lot_size para {symbol}: {e}")
        
        # Fallback baseado no símbolo
        lot_sizes = {
            'BTC': 0.00001, 'ETH': 0.0001, 'SOL': 0.01,
            'BNB': 0.001, 'AVAX': 0.001, 'LTC': 0.001
        }
        fallback = lot_sizes.get(symbol, 0.001)
        self.logger.warning(f"⚠️ {symbol}: usando fallback lot_size={fallback}")
        return fallback
    
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
        self.logger.debug(f"📊 MultiAsset: Iniciando check_and_rebalance - {len(self.symbols)} símbolos para análise")
        
        # Atualizar preços e verificar sinais
        self._update_all_prices()
        
        # 🆕 Verificação periódica de TP/SL (a cada 3 ciclos)
        if not hasattr(self, '_tp_sl_check_counter'):
            self._tp_sl_check_counter = 0
        self._tp_sl_check_counter += 1
        
        if self._tp_sl_check_counter >= 3:  # A cada 3 ciclos de rebalanceamento
            self.logger.debug("🔍 Verificação periódica de TP/SL...")
            self._check_all_tp_sl()
            self._tp_sl_check_counter = 0
        
        symbols_analyzed = 0
        signals_found = 0
        
        # Verificar sinais para todos os símbolos
        for symbol in self.symbols:
            if symbol in self.price_history:
                history_length = len(self.price_history[symbol])
                if history_length >= 3:
                    symbols_analyzed += 1
                    latest_price = self.price_history[symbol][-1]
                    signal_found = self._check_signals_for_symbol(symbol, latest_price)
                    if signal_found:
                        signals_found += 1
                else:
                    self.logger.debug(f"📊 {symbol}: {history_length} pontos de histórico (precisa 3+)")
        
        self.logger.info(f"📊 MultiAsset: Análise concluída - {symbols_analyzed}/{len(self.symbols)} símbolos analisados, {signals_found} sinais encontrados")
    
    def _update_all_prices(self):
        """Atualizar preços de todos os símbolos"""
        try:
            prices = self.auth.get_prices()
            
            if prices and 'data' in prices:
                prices_updated = 0
                for item in prices['data']:
                    symbol = item.get('symbol')
                    price = item.get('mark') or item.get('mid')
                    
                    if symbol in self.symbols and price:
                        self._update_price_history(symbol, float(price))
                        prices_updated += 1
                        
                self.logger.debug(f"📈 MultiAsset: {prices_updated} preços atualizados")
                        
        except Exception as e:
            self.logger.error(f"Erro ao atualizar preços: {e}")
    
    def _update_price_history(self, symbol: str, price: float):
        """Atualizar histórico de preços com limitação de memória"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append(price)
        
        # 🔧 NOVA ADIÇÃO: Limitar tamanho do histórico para evitar memory leak
        MAX_HISTORY_SIZE = 100  # Manter apenas 100 últimos preços
        if len(self.price_history[symbol]) > MAX_HISTORY_SIZE:
            # Remove 50% quando atinge limite (otimização de performance)
            self.price_history[symbol] = self.price_history[symbol][-50:]
            self.logger.debug(f"🧹 Histórico {symbol} limitado a 50 entradas para evitar memory leak")
    
    def _check_signals_for_symbol(self, symbol: str, current_price: float):
        """Verificar sinais de trading para um símbolo"""
        if not self._can_open_position(symbol):
            return False
        
        prices = self.price_history[symbol]
        if len(prices) >= 3:
            # Calcular mudança percentual
            price_change = (current_price - prices[-3]) / prices[-3] * 100
            
            if abs(price_change) >= self.price_change_threshold:
                side = 'LONG' if price_change > 0 else 'SHORT'
                self.logger.info(f"⚡ {symbol}: Sinal detectado - {side}, Variação: {price_change:.2f}%")
                self._execute_signal(symbol, side, current_price, abs(price_change))
                return True
        
        return False
    
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
            
            # Preparar TP/SL se habilitado
            take_profit_config = None
            stop_loss_config = None
            
            if self.auto_close_enabled and self.use_api_tp_sl:
                if side == 'LONG':
                    tp_stop_price = round(price * (1 + self.take_profit_percent / 100), 4)
                    tp_limit_price = round(tp_stop_price * 0.999, 4)
                    sl_stop_price = round(price * (1 - self.stop_loss_percent / 100), 4)
                    sl_limit_price = round(sl_stop_price * 1.001, 4)
                else:  # SHORT
                    tp_stop_price = round(price * (1 - self.take_profit_percent / 100), 4)
                    tp_limit_price = round(tp_stop_price * 1.001, 4)
                    sl_stop_price = round(price * (1 + self.stop_loss_percent / 100), 4)
                    sl_limit_price = round(sl_stop_price * 0.999, 4)
                
                take_profit_config = {
                    "stop_price": tp_stop_price,
                    "limit_price": tp_limit_price
                }
                
                stop_loss_config = {
                    "stop_price": sl_stop_price,
                    "limit_price": sl_limit_price
                }
                
                self.logger.info(f"🎯 TP/SL configurado: TP@${tp_stop_price:.4f}, SL@${sl_stop_price:.4f}")
            
            # Executar ordem com TP/SL integrado
            result = self.auth.create_order(
                symbol=symbol,
                side=order_side,
                amount=str(quantity),
                price=str(price),
                order_type='GTC',
                take_profit=take_profit_config,
                stop_loss=stop_loss_config
            )
            
            if result and result.get('success'):
                order_data = result.get('data', {})
                order_id = order_data.get('order_id')
                position_id = f"{symbol}_{int(time.time())}"
                
                # Salvar posição
                position_info = {
                    'symbol': symbol,
                    'side': order_side,  # 'bid' ou 'ask' conforme API
                    'quantity': quantity,
                    'price': price,
                    'order_id': order_id,
                    'timestamp': datetime.now()
                }
                
                # ✅ SALVAR IDs DE TP/SL SE CRIADOS JUNTO COM A ORDEM
                if 'take_profit_order_id' in order_data:
                    position_info['take_profit_order_id'] = order_data['take_profit_order_id']
                    self.logger.info(f"🎯 TP ID salvo: {order_data['take_profit_order_id']}")
                    
                if 'stop_loss_order_id' in order_data:
                    position_info['stop_loss_order_id'] = order_data['stop_loss_order_id']
                    self.logger.info(f"🛡️ SL ID salvo: {order_data['stop_loss_order_id']}")
                
                self.active_positions[position_id] = position_info
                
                self.symbol_positions[symbol] = self.symbol_positions.get(symbol, 0) + 1
                
                self.logger.info(f"✅ Posição aberta: {symbol} {side} {quantity} @ ${price:.4f}")
                
                # TP/SL já configurado na ordem principal se habilitado
                
            else:
                self.logger.error(f"❌ Falha ao abrir posição: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao executar sinal: {e}")
    
    def _setup_tp_sl_deprecated(self, position_id: str, symbol: str, side: str, entry_price: float, quantity: float):
        """
        MÉTODO DEPRECIADO - TP/SL agora é configurado diretamente na ordem principal
        Configurar TP/SL via API - VERSÃO ANTIGA (criava ordens separadas)
        """
        # Este método não é mais usado - TP/SL agora é incluído na ordem principal
        # conforme o formato esperado pela API: take_profit e stop_loss na mesma requisição
        self.logger.debug("⚠️ _setup_tp_sl_deprecated chamado - usando versão integrada na ordem principal")
        pass
    
    def _check_all_tp_sl(self):
        """Verificar TP/SL de todas as posições ativas"""
        if self.use_api_tp_sl:
            # Verificar se posições têm TP/SL via API
            self._verify_api_tp_sl()
        else:
            # Monitoramento manual de TP/SL
            self._check_manual_tp_sl()
    
    def _verify_api_tp_sl(self):
        """Verificar se todas as posições têm TP/SL via API"""
        if not self.active_positions:
            return
        
        missing_tp_sl = []
        
        for position_id, position in self.active_positions.items():
            has_tp = 'take_profit_order_id' in position and position['take_profit_order_id']
            has_sl = 'stop_loss_order_id' in position and position['stop_loss_order_id']
            
            if not has_tp or not has_sl:
                missing_tp_sl.append({
                    'position_id': position_id,
                    'symbol': position['symbol'],
                    'side': position['side'],
                    'price': position['price'],
                    'quantity': position['quantity'],
                    'has_tp': has_tp,
                    'has_sl': has_sl
                })
        
        if missing_tp_sl:
            self.logger.warning(f"⚠️ {len(missing_tp_sl)} posições sem TP/SL completo")
            for pos in missing_tp_sl:
                self.logger.info(f"🔧 Adicionando TP/SL para {pos['symbol']} - TP:{pos['has_tp']} SL:{pos['has_sl']}")
                self._add_missing_tp_sl(pos)
    
    def _add_missing_tp_sl(self, position_data):
        """Adicionar TP/SL em posição existente via API"""
        try:
            symbol = position_data['symbol']
            side = position_data['side']
            entry_price = position_data['price']
            position_id = position_data['position_id']
            
            # 🔧 VERIFICAR SE A POSIÇÃO AINDA EXISTE NA API
            self.logger.info(f"🔍 Verificando se posição {symbol} ainda existe na API...")
            
            # Buscar posições atuais da API
            api_positions = self.auth.get_positions()
            if not api_positions:
                self.logger.warning(f"⚠️ Não foi possível obter posições da API para verificar {symbol}")
            else:
                # Verificar se a posição local ainda existe na API
                position_found = False
                for api_pos in api_positions:
                    if api_pos.get('symbol') == symbol and api_pos.get('side') == side:
                        position_found = True
                        self.logger.info(f"✅ Posição {symbol} {side} confirmada na API")
                        break
                
                if not position_found:
                    self.logger.warning(f"❌ Posição {symbol} {side} NÃO encontrada na API - removendo local")
                    # Remover posição local que não existe mais na API
                    if position_id in self.active_positions:
                        del self.active_positions[position_id]
                    return False
            
            # 🔧 CORREÇÃO CRÍTICA: Usar preço ATUAL, não preço de entrada
            current_price = self._get_current_price(symbol)
            if not current_price:
                self.logger.error(f"❌ Não foi possível obter preço atual para {symbol}")
                return False
            
            # Log da correção de preço
            price_change_percent = ((current_price - entry_price) / entry_price) * 100
            self.logger.info(f"💰 {symbol} - Entry: ${entry_price:.6f}, Atual: ${current_price:.6f} ({price_change_percent:+.2f}%)")
            
            # Calcular preços de TP/SL baseado no preço ATUAL
            if side == 'bid':  # Long position (comprando)
                tp_stop_price = current_price * (1 + self.take_profit_percent / 100)
                tp_limit_price = tp_stop_price * 0.999
                sl_stop_price = current_price * (1 - self.stop_loss_percent / 100)
                sl_limit_price = sl_stop_price * 1.001
            else:  # Short position - side == 'ask'
                tp_stop_price = current_price * (1 - self.take_profit_percent / 100)
                tp_limit_price = tp_stop_price * 0.999  
                sl_stop_price = current_price * (1 + self.stop_loss_percent / 100)
                sl_limit_price = sl_stop_price * 1.001  
            
            # Arredondar preços
            tp_stop_price = round(tp_stop_price, 4)
            tp_limit_price = round(tp_limit_price, 4)
            sl_stop_price = round(sl_stop_price, 4)
            sl_limit_price = round(sl_limit_price, 4)
            
            # Chamar API para adicionar TP/SL
            result = self.auth.create_position_tp_sl(
                symbol=symbol,
                side=side,
                take_profit_stop=tp_stop_price,
                take_profit_limit=tp_limit_price,
                stop_loss_stop=sl_stop_price,
                stop_loss_limit=sl_limit_price
            )
            
            if result and result.get('success'):
                self.logger.info(f"✅ TP/SL criado para {symbol}: TP@{tp_stop_price} SL@{sl_stop_price}")
                
                # Aguardar processamento pela API
                time.sleep(2)
                
                # Buscar IDs das ordens TP/SL criadas
                tp_sl_ids = self._find_tpsl_orders_for_position(symbol, side)
                
                # Atualizar posição local se IDs foram encontrados
                if tp_sl_ids.get('take_profit_order_id') or tp_sl_ids.get('stop_loss_order_id'):
                    position_id = position_data['position_id']
                    if position_id in self.active_positions:
                        self.active_positions[position_id].update(tp_sl_ids)
                        self.logger.info(f"✅ IDs TP/SL salvos: TP={tp_sl_ids.get('take_profit_order_id')}, SL={tp_sl_ids.get('stop_loss_order_id')}")
                else:
                    self.logger.warning(f"⚠️ TP/SL criado mas IDs não encontrados - será verificado no próximo ciclo")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao adicionar TP/SL: {e}")
    
    def _find_tpsl_orders_for_position(self, symbol: str, side: str) -> dict:
        """
        Busca IDs de ordens TP/SL para uma posição específica
        
        Args:
            symbol: Símbolo da posição
            side: Side da posição ('bid' para long, 'ask' para short)
            
        Returns:
            Dict com take_profit_order_id e stop_loss_order_id
        """
        try:
            # Buscar todas as ordens abertas
            all_orders = self.auth.get_open_orders()
            
            if not all_orders:
                return {}
            
            tp_id = None
            sl_id = None
            current_price = self._get_current_price(symbol)
            
            if current_price <= 0:
                self.logger.warning(f"⚠️ Preço atual inválido para {symbol}")
                return {}
            
            # Procurar ordens TP/SL deste símbolo
            for order in all_orders:
                # Filtrar por símbolo
                if order.get('symbol') != symbol:
                    continue
                
                # Identificar se é ordem stop
                stop_price = order.get('stop_price')
                if stop_price is None:
                    continue  # Não é ordem stop
                
                stop_price_float = float(stop_price)
                order_id = order.get('order_id')
                
                # Determinar se é TP ou SL baseado na posição do stop_price
                if side == 'bid':  # Long position
                    # TP está acima do preço atual, SL abaixo
                    if stop_price_float > current_price:
                        tp_id = order_id
                        self.logger.debug(f"   TP encontrado: {order_id} @ ${stop_price_float}")
                    else:
                        sl_id = order_id
                        self.logger.debug(f"   SL encontrado: {order_id} @ ${stop_price_float}")
                else:  # Short position (side == 'ask')
                    # TP está abaixo do preço atual, SL acima
                    if stop_price_float < current_price:
                        tp_id = order_id
                        self.logger.debug(f"   TP encontrado: {order_id} @ ${stop_price_float}")
                    else:
                        sl_id = order_id
                        self.logger.debug(f"   SL encontrado: {order_id} @ ${stop_price_float}")
            
            result = {
                'take_profit_order_id': tp_id,
                'stop_loss_order_id': sl_id
            }
            
            if tp_id or sl_id:
                self.logger.info(f"🔍 IDs encontrados para {symbol}: TP={tp_id}, SL={sl_id}")
            else:
                self.logger.warning(f"⚠️ Nenhuma ordem TP/SL encontrada para {symbol}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao buscar IDs TP/SL: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return {}
    
    def _check_manual_tp_sl(self):
        """Monitoramento manual de TP/SL (quando USE_API_TP_SL=false)"""
        if not self.active_positions:
            return
        
        positions_to_close = []
        
        for position_id, position in self.active_positions.items():
            try:
                symbol = position['symbol']
                entry_price = position['price']
                side = position['side']
                quantity = position['quantity']
                
                # Obter preço atual
                current_price = self._get_current_price(symbol)
                if not current_price:
                    continue
                
                # Calcular PNL
                if side == 'bid':  # Long position (compramos)
                    pnl_percent = ((current_price - entry_price) / entry_price) * 100
                else:  # Short position (vendemos) - side == 'ask'
                    pnl_percent = ((entry_price - current_price) / entry_price) * 100
                
                # Verificar condições de fechamento
                should_close = False
                close_reason = ""
                
                if pnl_percent <= -self.stop_loss_percent:
                    should_close = True
                    close_reason = f"STOP LOSS: {pnl_percent:.2f}%"
                elif pnl_percent >= self.take_profit_percent:
                    should_close = True
                    close_reason = f"TAKE PROFIT: {pnl_percent:.2f}%"
                
                if should_close:
                    positions_to_close.append({
                        'position_id': position_id,
                        'symbol': symbol,
                        'side': side,
                        'quantity': quantity,
                        'current_price': current_price,
                        'reason': close_reason
                    })
                    
            except Exception as e:
                self.logger.error(f"❌ Erro ao verificar TP/SL manual para {position_id}: {e}")
        
        # Fechar posições que atingiram TP/SL
        for pos in positions_to_close:
            self._close_position_manual(pos)
    
    def _close_position_manual(self, position_data):
        """Fechar posição manualmente por TP/SL"""
        try:
            symbol = position_data['symbol']
            side = position_data['side']
            quantity = position_data['quantity']
            current_price = position_data['current_price']
            reason = position_data['reason']
            
            # Determinar lado da ordem de fechamento
            close_side = 'ask' if side == 'bid' else 'bid'
            
            self.logger.info(f"🎯 Fechando posição {symbol} - {reason}")
            
            # Criar ordem de fechamento
            result = self.auth.create_order(
                symbol=symbol,
                side=close_side,
                amount=str(quantity),
                price=str(current_price),
                order_type="GTC",
                reduce_only=True
            )
            
            if result:
                self.logger.info(f"✅ Ordem de fechamento criada para {symbol}")
                # Remover da lista de posições ativas
                position_id = position_data['position_id']
                if position_id in self.active_positions:
                    del self.active_positions[position_id]
            else:
                self.logger.error(f"❌ Falha ao criar ordem de fechamento para {symbol}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao fechar posição manual: {e}")
    
    def _get_current_price(self, symbol: str) -> float:
        """Obter preço atual de um símbolo"""
        try:
            prices_data = self.auth.get_prices()
            if prices_data and prices_data.get('success'):
                for item in prices_data.get('data', []):
                    if item.get('symbol') == symbol:
                        return float(item.get('mark') or item.get('mid') or 0)
            return 0.0
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter preço de {symbol}: {e}")
            return 0.0
    
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