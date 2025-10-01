"""
Bot de Scalping Multi-Ativos - Versão com TP/SL Automático
Suporta múltiplos ativos, posição/leverage configurável, TP/SL automático
"""

import os
import time
import signal
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import sys
import traceback
from pathlib import Path

# Imports dos módulos existentes
from src.pacifica_auth import PacificaAuth
from src.position_manager import PositionManager
from src.performance_tracker import PerformanceTracker

class MultiAssetScalpingStrategy:
    def __init__(self, auth_client, position_manager):
        self.logger = logging.getLogger('PacificaBot.MultiAssetScalping')
        
        self.auth = auth_client
        self.position_mgr = position_manager
        
        # CONFIGURAÇÕES DO .ENV
        self.symbols = self._parse_symbols()
        self.position_size_usd = float(os.getenv('POSITION_SIZE_USD', '20'))
        self.leverage = int(os.getenv('LEVERAGE', '10'))
        self.max_concurrent_trades = int(os.getenv('MAX_CONCURRENT_TRADES', '3'))
        self.allow_multiple_per_symbol = os.getenv('ALLOW_MULTIPLE_PER_SYMBOL', 'false').lower() == 'true'
        self.price_change_threshold = float(os.getenv('PRICE_CHANGE_THRESHOLD', '0.3'))
        
        # CONFIGURAÇÕES DE TP/SL
        self.auto_close_enabled = os.getenv('AUTO_CLOSE_ENABLED', 'true').lower() == 'true'
        self.use_api_tp_sl = os.getenv('USE_API_TP_SL', 'true').lower() == 'true'
        self.stop_loss_percent = float(os.getenv('STOP_LOSS_PERCENT', '1.5'))   # ✅ Limite de perda menor
        self.take_profit_percent = float(os.getenv('TAKE_PROFIT_PERCENT', '2.0')) # ✅ Meta de lucro maior
        self.trailing_stop_enabled = os.getenv('TRAILING_STOP_ENABLED', 'false').lower() == 'true'
        self.trailing_stop_percent = float(os.getenv('TRAILING_STOP_PERCENT', '0.5'))
        self.max_position_time_minutes = int(os.getenv('MAX_POSITION_TIME_MINUTES', '60'))
        
        # Calcular margem necessária por trade
        self.margin_per_trade = self.position_size_usd / self.leverage
        
        # Dados de mercado por símbolo
        self.price_history = {}  # {symbol: [prices]}
        self.lot_sizes = {}     # {symbol: lot_size}
        self.active_positions = {}  # {position_id: position_data}
        self.symbol_positions = {}  # {symbol: count}
        
        # Dados para TP/SL tracking
        self.position_entry_prices = {}  # {position_id: entry_price}
        self.position_max_profit = {}    # {position_id: max_profit_seen}
        self.position_trailing_stops = {} # {position_id: trailing_stop_price}
        
        # Inicializar estruturas para cada símbolo
        for symbol in self.symbols:
            self.price_history[symbol] = []
            self.lot_sizes[symbol] = self._get_lot_size(symbol)
            self.symbol_positions[symbol] = 0
        
        self.logger.info(f"MultiAssetScalping inicializado:")
        self.logger.info(f"  Símbolos: {self.symbols}")
        self.logger.info(f"  Posição: ${self.position_size_usd} (margem: ${self.margin_per_trade:.2f})")
        self.logger.info(f"  Leverage: {self.leverage}x")
        self.logger.info(f"  Max trades simultâneos: {self.max_concurrent_trades}")
        self.logger.info(f"  Múltiplos por símbolo: {'SIM' if self.allow_multiple_per_symbol else 'NÃO'}")
        self.logger.info(f"  Threshold movimento: {self.price_change_threshold}%")
        
        # Log das configurações de TP/SL
        self.logger.info(f"  Auto close: {'ATIVO' if self.auto_close_enabled else 'INATIVO'}")
        if self.auto_close_enabled:
            self.logger.info(f"    Método: {'API Nativa' if self.use_api_tp_sl else 'Monitoramento'}")
            self.logger.info(f"    Stop Loss: {self.stop_loss_percent}%")
            self.logger.info(f"    Take Profit: {self.take_profit_percent}%")
            self.logger.info(f"    Trailing Stop: {'SIM' if self.trailing_stop_enabled else 'NÃO'}")
            if self.trailing_stop_enabled:
                self.logger.info(f"    Trailing: {self.trailing_stop_percent}%")
            self.logger.info(f"    Max tempo posição: {self.max_position_time_minutes}min")
    
    def _parse_symbols(self) -> List[str]:
        """Parse símbolos do .env"""
        symbols_env = os.getenv('SYMBOLS', 'AUTO')
        
        if symbols_env.upper() == 'AUTO':
            # Buscar todos os símbolos disponíveis da API
            return self._get_all_available_symbols()
        else:
            # Símbolos específicos separados por vírgula
            return [s.strip().upper() for s in symbols_env.split(',')]
    
    def _get_all_available_symbols(self) -> List[str]:
        """Busca todos os símbolos disponíveis com blacklist configurável"""
        try:
            prices_data = self.auth.get_prices()
            
            # Validar resposta
            if not prices_data:
                self.logger.warning("⚠️ API não retornou dados de preços")
                return ['BTC', 'ETH', 'SOL']
            
            # Extrair dados (suporta diferentes estruturas)
            if isinstance(prices_data, dict):
                data_list = prices_data.get('data', [])
            elif isinstance(prices_data, list):
                data_list = prices_data
            else:
                self.logger.error(f"❌ Formato inesperado da API: {type(prices_data)}")
                return ['BTC', 'ETH', 'SOL']
            
            if not data_list:
                self.logger.warning("⚠️ Lista de dados vazia na resposta da API")
                return ['BTC', 'ETH', 'SOL']
            
            # Extrair todos os símbolos
            all_symbols = []
            for item in data_list:
                symbol = item.get('symbol')
                if symbol:
                    all_symbols.append(symbol)
            
            if not all_symbols:
                self.logger.warning("⚠️ Nenhum símbolo encontrado nos dados")
                return ['BTC', 'ETH', 'SOL']
            
            self.logger.info(f"✅ Total de símbolos na exchange: {len(all_symbols)}")
            self.logger.info(f"📋 Todos os símbolos: {all_symbols}")
            
            # 🆕 LER BLACKLIST DO .ENV
            use_blacklist = os.getenv('SYMBOLS_USE_BLACKLIST', 'true').lower() == 'true'
            blacklist_str = os.getenv('SYMBOLS_BLACKLIST', 'PUMP,kPEPE,FARTCOIN')
            max_symbols = int(os.getenv('SYMBOLS_MAX_COUNT', '0'))
            
            # Aplicar blacklist se configurado
            if use_blacklist and blacklist_str:
                blacklist = [s.strip().upper() for s in blacklist_str.split(',')]
                filtered_symbols = [s for s in all_symbols if s not in blacklist]
                
                removed_count = len(all_symbols) - len(filtered_symbols)
                if removed_count > 0:
                    removed_list = [s for s in all_symbols if s in blacklist]
                    self.logger.info(f"🚫 Blacklist removeu {removed_count} símbolos: {removed_list}")
                else:
                    self.logger.info("ℹ️ Nenhum símbolo na blacklist foi encontrado")
                
                symbols = filtered_symbols
            else:
                symbols = all_symbols
                self.logger.info("ℹ️ Blacklist desativada - usando todos os símbolos")
            
            # Aplicar limite se configurado
            if max_symbols > 0 and len(symbols) > max_symbols:
                self.logger.info(f"📊 Limitando de {len(symbols)} para {max_symbols} símbolos")
                symbols = symbols[:max_symbols]
            
            self.logger.info(f"🎯 Símbolos finais selecionados: {len(symbols)}")
            self.logger.info(f"📋 Lista final: {symbols}")
            
            return symbols
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao buscar símbolos: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
        
        # Fallback final
        self.logger.warning("⚠️ Usando fallback padrão: BTC, ETH, SOL")
        return ['BTC', 'ETH', 'SOL']
    
    def _get_lot_size(self, symbol: str) -> float:
        """Obter lot_size específico do símbolo"""
        try:
            info = self.auth.get_symbol_info(symbol)
            if info and 'lot_size' in info:
                lot_size = float(info['lot_size'])
                self.logger.debug(f"{symbol} lot_size: {lot_size}")
                return lot_size
        except Exception as e:
            self.logger.warning(f"Erro ao obter lot_size para {symbol}: {e}")
        
        # Fallback para valores conhecidos
        lot_sizes = {
            'BTC': 0.00001,
            'ETH': 0.0001, 
            'SOL': 0.01,
            'BNB': 0.001,
            'AVAX': 0.001,
            'LTC': 0.001
        }
        return lot_sizes.get(symbol, 0.001)
    
    def update_market_data(self, symbol: str, price: float):
        """Atualizar dados de mercado para um símbolo"""
        
        if symbol not in self.price_history:
            return
        
        self.price_history[symbol].append(price)
        
        # Manter apenas últimos 10 preços por símbolo
        if len(self.price_history[symbol]) > 10:
            self.price_history[symbol].pop(0)
        
        # Verificar sinais se temos dados suficientes
        if len(self.price_history[symbol]) >= 3:
            self._check_signals_for_symbol(symbol, price)
        
        # Verificar condições de TP/SL para posições deste símbolo
        if self.auto_close_enabled and not self.use_api_tp_sl:
            # Só usar monitoramento interno se não estiver usando API nativa
            self._check_tp_sl_for_symbol(symbol, price)
    
    def _check_signals_for_symbol(self, symbol: str, current_price: float):
        """Verificar sinais para um símbolo específico"""
        
        # Verificar se pode abrir nova posição
        if not self._can_open_position(symbol):
            return
        
        # Calcular movimento de preço nos últimos 3 ticks
        prices = self.price_history[symbol]
        if len(prices) >= 3:
            price_change = (current_price - prices[-3]) / prices[-3] * 100
            
            if price_change > self.price_change_threshold:
                self._create_signal(symbol, 'LONG', current_price, abs(price_change))
            elif price_change < -self.price_change_threshold:
                self._create_signal(symbol, 'SHORT', current_price, abs(price_change))
    
    def _check_tp_sl_for_symbol(self, symbol: str, current_price: float):
        """Verificar condições de TP/SL para um símbolo específico"""
        
        positions_to_close = []
        
        for position_id, position in self.active_positions.items():
            if position['symbol'] != symbol:
                continue
            
            entry_price = position['price']
            side = position['side']
            quantity = position['quantity']
            position_time = datetime.now() - position['timestamp']
            
            # Calcular PNL atual
            if side == 'bid':  # Long position (compramos)
                pnl_percent = ((current_price - entry_price) / entry_price) * 100
                pnl_usd = (current_price - entry_price) * quantity
            else:  # Short position (vendemos) - side == 'ask'
                pnl_percent = ((entry_price - current_price) / entry_price) * 100
                pnl_usd = (entry_price - current_price) * quantity
            
            # Verificar condições de fechamento
            should_close = False
            close_reason = ""
            
            # 1. STOP LOSS
            if pnl_percent <= -self.stop_loss_percent:
                should_close = True
                close_reason = f"Stop Loss: {pnl_percent:.2f}% <= -{self.stop_loss_percent}%"
            
            # 2. TAKE PROFIT FIXO
            elif not self.trailing_stop_enabled and pnl_percent >= self.take_profit_percent:
                should_close = True
                close_reason = f"Take Profit: {pnl_percent:.2f}% >= {self.take_profit_percent}%"
            
            # 3. TRAILING STOP
            elif self.trailing_stop_enabled:
                # Atualizar máximo lucro visto
                if position_id not in self.position_max_profit:
                    self.position_max_profit[position_id] = pnl_percent
                
                if pnl_percent > self.position_max_profit[position_id]:
                    self.position_max_profit[position_id] = pnl_percent
                    
                    # Atualizar trailing stop apenas se lucro > take profit mínimo
                    if pnl_percent >= self.take_profit_percent:
                        if side == 'bid':  # Long position
                            new_trailing = current_price * (1 - self.trailing_stop_percent / 100)
                        else:  # Short position - side == 'ask'
                            new_trailing = current_price * (1 + self.trailing_stop_percent / 100)
                        
                        self.position_trailing_stops[position_id] = new_trailing
                        self.logger.debug(f"Trailing stop atualizado {position_id}: ${new_trailing:.4f}")
                
                # Verificar se atingiu trailing stop
                if position_id in self.position_trailing_stops:
                    trailing_price = self.position_trailing_stops[position_id]
                    
                    if side == 'bid' and current_price <= trailing_price:
                        should_close = True
                        close_reason = f"Trailing Stop: ${current_price:.4f} <= ${trailing_price:.4f}"
                    elif side == 'ask' and current_price >= trailing_price:
                        should_close = True
                        close_reason = f"Trailing Stop: ${current_price:.4f} >= ${trailing_price:.4f}"
                
                # Take profit fixo como backup se não há trailing
                elif pnl_percent >= self.take_profit_percent * 2:  # 2x o TP para forçar saída
                    should_close = True
                    close_reason = f"Take Profit Máximo: {pnl_percent:.2f}% >= {self.take_profit_percent * 2}%"
            
            # 4. TEMPO MÁXIMO
            if position_time.total_seconds() > (self.max_position_time_minutes * 60):
                should_close = True
                close_reason = f"Tempo Limite: {position_time.total_seconds()/60:.1f}min >= {self.max_position_time_minutes}min"
            
            # Executar fechamento se necessário
            if should_close:
                self.logger.info(f"FECHANDO {position_id}: {close_reason}")
                self.logger.info(f"  PNL: {pnl_percent:+.2f}% (${pnl_usd:+.2f})")
                positions_to_close.append((position_id, position, current_price, close_reason, pnl_usd))
        
        # Fechar posições (fora do loop para evitar modificação durante iteração)
        for position_id, position, close_price, reason, pnl in positions_to_close:
            self._close_position(position_id, position, close_price, reason, pnl)
    
    def _close_position(self, position_id: str, position: Dict, close_price: float, reason: str, pnl_usd: float):
        """Fechar uma posição específica"""
        
        try:
            symbol = position['symbol']
            side = position['side']
            quantity = position['quantity']
            
            # Determinar lado oposto para fechamento
            close_side = 'ask' if side == 'bid' else 'bid'
            
            self.logger.info(f"Fechando posição {symbol} {side}: {quantity} @ ${close_price:.4f}")
            
            # Executar ordem de fechamento
            result = self.auth.create_order(
                symbol=symbol,
                side=close_side,
                amount=str(quantity),
                price=str(close_price),
                order_type='GTC',
                reduce_only=True
            )
            
            if result and result.get('success'):
                close_order_id = result.get('data', {}).get('order_id')
                
                # Remover posição do tracking
                del self.active_positions[position_id]
                self.symbol_positions[symbol] = max(0, self.symbol_positions.get(symbol, 0) - 1)
                
                # Limpar dados de tracking
                if position_id in self.position_max_profit:
                    del self.position_max_profit[position_id]
                if position_id in self.position_trailing_stops:
                    del self.position_trailing_stops[position_id]
                
                # Log do resultado
                duration = datetime.now() - position['timestamp']
                duration_minutes = duration.total_seconds() / 60
                
                self.logger.info(f"✅ POSIÇÃO FECHADA {symbol}:")
                self.logger.info(f"  Razão: {reason}")
                self.logger.info(f"  Duração: {duration_minutes:.1f}min")
                self.logger.info(f"  PNL: ${pnl_usd:+.2f}")
                self.logger.info(f"  Order ID: {close_order_id}")
                
                # Atualizar resumo
                self._log_positions_summary()
                
            else:
                self.logger.error(f"❌ Falha ao fechar posição {position_id}: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao fechar posição {position_id}: {e}")
            self.logger.error(traceback.format_exc())
    
    def _can_open_position(self, symbol: str) -> bool:
        """Verificar se pode abrir posição"""
        
        # Verificar limite total de trades
        if len(self.active_positions) >= self.max_concurrent_trades:
            return False
        
        # Verificar se permite múltiplos no mesmo símbolo
        if not self.allow_multiple_per_symbol:
            if self.symbol_positions.get(symbol, 0) > 0:
                return False
        
        # Verificar margem disponível
        margin_needed = self.margin_per_trade
        can_place, reason = self.position_mgr.can_place_order(margin_needed * self.leverage)
        
        return can_place
    
    def _create_signal(self, symbol: str, side: str, price: float, strength: float):
        """Criar e executar sinal de trading"""
        
        self.logger.info(f"SINAL {side} {symbol} @ ${price:.4f} (força: {strength:.2f}%)")
        self._execute_trade(symbol, side, price)
    
    def _execute_trade(self, symbol: str, side: str, price: float):
        """Executar trade COM TP/SL (SEM duplicação)"""
        
        try:
            # 🆕 OBTER TICK_SIZE DO SÍMBOLO PRIMEIRO
            tick_size = self._get_symbol_tick_size(symbol)
            
            # 🔧 ARREDONDAR PREÇO DE ENTRADA PARA TICK_SIZE
            price_rounded = self._round_to_tick_size(price, tick_size)
            
            self.logger.info(f"📏 {symbol} tick_size: {tick_size}")
            self.logger.info(f"💰 Preço: {price:.6f} -> {price_rounded} (arredondado)")
            
            # Calcular quantidade baseada no tamanho da posição
            quantity_raw = self.position_size_usd / price_rounded
            lot_size = self.lot_sizes[symbol]
            
            # Arredondar para lot_size
            quantity = round(quantity_raw / lot_size) * lot_size
            
            # Garantir quantidade mínima
            if quantity < lot_size:
                quantity = lot_size
            
            # Formatação baseada no lot_size
            if lot_size >= 0.01:
                decimals = 2
            elif lot_size >= 0.001:
                decimals = 3
            elif lot_size >= 0.0001:
                decimals = 4
            else:
                decimals = 5
                
            quantity = round(quantity, decimals)
            
            # Verificar valor final da ordem
            order_value = quantity * price_rounded
            
            self.logger.info(f"Executando {side} {symbol}:")
            self.logger.info(f"  Quantidade: {quantity} (lot_size: {lot_size})")
            self.logger.info(f"  Valor da ordem: ${order_value:.2f}")
            self.logger.info(f"  Margem necessária: ${order_value/self.leverage:.2f}")
            
            # Executar ordem
            api_side = 'bid' if side == 'LONG' else 'ask'
            
            # 🔧 ESCOLHER MÉTODO DE TP/SL (SEM DUPLICAÇÃO)
            if self.auto_close_enabled and self.use_api_tp_sl:
                # ✅ MÉTODO CORRETO: Criar ordem + TP/SL juntos
                self.logger.info(f"🎯 Criando ordem COM TP/SL na mesma requisição:")
                self.logger.info(f"   Stop Loss: {self.stop_loss_percent}%")
                self.logger.info(f"   Take Profit: {self.take_profit_percent}%")
                
                result = self.auth.create_order_with_auto_tpsl(
                    symbol=symbol,
                    side=api_side,
                    amount=str(quantity),
                    price=str(price_rounded),
                    tp_percent=self.take_profit_percent,
                    sl_percent=self.stop_loss_percent,
                    order_type='GTC',
                    reduce_only=False
                )
                
                # 🔧 IMPORTANTE: NÃO chamar _create_api_tp_sl aqui!
                # O TP/SL já foi criado junto com a ordem principal
                
            else:
                # Ordem tradicional sem TP/SL (ou monitoramento interno)
                self.logger.info(f"📝 Criando ordem SEM TP/SL automático")
                
                result = self.auth.create_order(
                    symbol=symbol,
                    side=api_side,
                    amount=str(quantity),
                    price=str(price_rounded),
                    order_type='GTC',
                    reduce_only=False
                )
            
            if result and result.get('success'):
                order_data = result.get('data', {})
                order_id = order_data.get('order_id')
                
                # Registrar posição
                position_id = f"{symbol}_{side}_{int(time.time())}"
                position_info = {
                    'symbol': symbol,
                    'order_id': order_id,
                    'side': api_side,  # 'bid' ou 'ask' conforme API
                    'price': price_rounded,
                    'quantity': quantity,
                    'timestamp': datetime.now(),
                    'value': order_value,
                    'margin_used': order_value / self.leverage
                }
                
                # 🆕 ADICIONAR IDs DE TP/SL SE CRIADOS (pela API)
                if 'take_profit_order_id' in order_data:
                    position_info['take_profit_order_id'] = order_data['take_profit_order_id']
                    self.logger.info(f"✅ Take Profit criado junto: {order_data['take_profit_order_id']}")
                    
                if 'stop_loss_order_id' in order_data:
                    position_info['stop_loss_order_id'] = order_data['stop_loss_order_id']
                    self.logger.info(f"✅ Stop Loss criado junto: {order_data['stop_loss_order_id']}")
                
                self.active_positions[position_id] = position_info
                
                # Incrementar contador do símbolo
                self.symbol_positions[symbol] = self.symbol_positions.get(symbol, 0) + 1
                
                # 🔧 CONFIGURAR MONITORAMENTO INTERNO APENAS SE:
                # 1. Auto close ativado E
                # 2. NÃO usar API TP/SL (fallback)
                if self.auto_close_enabled and not self.use_api_tp_sl:
                    self.logger.info("🔄 Configurando monitoramento interno de TP/SL")
                    self._setup_internal_monitoring(position_id, price_rounded, side)
                
                self.logger.info(f"✅ {side} {symbol} executado! ID: {order_id}")
                
                # Log do método de TP/SL usado
                if self.auto_close_enabled:
                    if self.use_api_tp_sl:
                        # Verificar se TP/SL foram realmente criados
                        if 'take_profit_order_id' in order_data or 'stop_loss_order_id' in order_data:
                            self.logger.info("🎯 TP/SL gerenciado pela EXCHANGE (criado junto)")
                        else:
                            self.logger.warning("⚠️ TP/SL não foi criado pela API - configurando monitoramento interno")
                            self._setup_internal_monitoring(position_id, price_rounded, side)
                    else:
                        self.logger.info("🔄 TP/SL gerenciado pelo BOT (monitoramento interno)")
                else:
                    self.logger.info("⚠️ SEM TP/SL automático")
                
                self._log_positions_summary()
                
            else:
                self.logger.error(f"❌ Falha ao executar {side} {symbol}: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao executar trade {symbol}: {e}")
            self.logger.error(traceback.format_exc())

    # 🔧 MANTER esta função para uso FUTURO em checagens posteriores
    def _create_api_tp_sl_for_existing_position(self, order_id: str, symbol: str, side: str, entry_price: float, quantity: float):
        """
        🆕 RENOMEADA: Criar TP/SL para posição JÁ ABERTA (uso futuro)
        Esta função será útil para:
        - Adicionar TP/SL a posições que não tinham
        - Modificar TP/SL existentes
        - Checagens posteriores de ajuste
        """
        
        try:
            # 🔧 CORREÇÃO CRÍTICA: Usar preço ATUAL, não preço de entrada
            current_price = self._get_current_price(symbol)
            if not current_price:
                self.logger.error(f"❌ Não foi possível obter preço atual para {symbol}")
                return False
            
            # Log da correção de preço
            price_change_percent = ((current_price - entry_price) / entry_price) * 100
            self.logger.info(f"💰 {symbol} - Entry: ${entry_price:.6f}, Atual: ${current_price:.6f} ({price_change_percent:+.2f}%)")
            
            # Calcular preços de TP e SL baseado no preço ATUAL
            if side == 'bid':  # Long position (comprando)
                stop_loss_price = current_price * (1 - self.stop_loss_percent / 100)
                take_profit_price = current_price * (1 + self.take_profit_percent / 100)
                api_side = 'bid'
            else:  # Short position (vendendo) - side == 'ask'
                stop_loss_price = current_price * (1 + self.stop_loss_percent / 100)
                take_profit_price = current_price * (1 - self.take_profit_percent / 100)
                api_side = 'ask'
            
            self.logger.info(f"🔧 Adicionando TP/SL para posição existente {symbol} {side}:")
            self.logger.info(f"  Stop Loss: ${stop_loss_price:.4f} ({self.stop_loss_percent}%)")
            self.logger.info(f"  Take Profit: ${take_profit_price:.4f} ({self.take_profit_percent}%)")
            
            # Usar endpoint /positions/tpsl para posições já abertas
            result = self.auth.create_position_tp_sl(
                symbol=symbol,
                side=api_side,
                take_profit_stop=take_profit_price,
                take_profit_limit=take_profit_price * 0.999 if side == 'bid' else take_profit_price * 1.001,
                stop_loss_stop=stop_loss_price,
                stop_loss_limit=stop_loss_price * 0.999 if side == 'ask' else stop_loss_price * 1.001
            )
            
            if result and result.get('success'):
                self.logger.info(f"✅ TP/SL adicionado para posição existente {order_id}")
                return True
            else:
                self.logger.error(f"❌ Falha ao adicionar TP/SL para posição: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao adicionar TP/SL para posição: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False

    # 🆕 FUNÇÕES PARA USO FUTURO (checagens posteriores)
    
    def check_and_adjust_tpsl(self):
        """
        Verifica todas as posições ativas e ajusta TP/SL se necessário
        🎯 USO FUTURO: Chamada periódica para otimizar TP/SL
        """
        
        if not self.active_positions:
            return
        
        self.logger.info("🔍 Verificando TP/SL de todas as posições...")
        
        for position_id, position in self.active_positions.items():
            try:
                symbol = position['symbol']
                order_id = position['order_id']
                side = position['side']
                entry_price = position['price']
                
                # Verificar se já tem TP/SL
                has_tp = 'take_profit_order_id' in position
                has_sl = 'stop_loss_order_id' in position
                
                if not has_tp or not has_sl:
                    self.logger.info(f"🔧 Posição {symbol} sem TP/SL completo - adicionando...")
                    self._create_api_tp_sl_for_existing_position(
                        order_id, symbol, side, entry_price, position['quantity']
                    )
                
            except Exception as e:
                self.logger.error(f"❌ Erro ao verificar TP/SL de {position_id}: {e}")
    
    def modify_existing_tpsl(self, position_id: str, new_tp_percent: float = None, new_sl_percent: float = None):
        """
        Modifica TP/SL de uma posição específica
        🎯 USO FUTURO: Ajuste dinâmico baseado em condições de mercado
        """
        
        if position_id not in self.active_positions:
            self.logger.error(f"❌ Posição {position_id} não encontrada")
            return False
        
        position = self.active_positions[position_id]
        
        # Cancelar TP/SL existentes se houver
        if 'take_profit_order_id' in position:
            self.logger.info(f"🚫 Cancelando TP existente: {position['take_profit_order_id']}")
            self.auth.cancel_order(position['take_profit_order_id'])
        
        if 'stop_loss_order_id' in position:
            self.logger.info(f"🚫 Cancelando SL existente: {position['stop_loss_order_id']}")
            self.auth.cancel_order(position['stop_loss_order_id'])
        
        # Criar novos TP/SL com percentuais atualizados
        old_tp = self.take_profit_percent
        old_sl = self.stop_loss_percent
        
        if new_tp_percent:
            self.take_profit_percent = new_tp_percent
        if new_sl_percent:
            self.stop_loss_percent = new_sl_percent
        
        success = self._create_api_tp_sl_for_existing_position(
            position['order_id'], 
            position['symbol'], 
            position['side'], 
            position['price'], 
            position['quantity']
        )
        
        # Restaurar valores originais
        self.take_profit_percent = old_tp
        self.stop_loss_percent = old_sl
        
        if success:
            self.logger.info(f"✅ TP/SL modificado para {position_id}")
        
        return success
    
    def get_positions_without_tpsl(self) -> List[str]:
        """
        Retorna lista de posições que não têm TP/SL completo
        🎯 USO FUTURO: Identificar posições que precisam de TP/SL
        """
        
        positions_without_tpsl = []
        
        for position_id, position in self.active_positions.items():
            has_tp = 'take_profit_order_id' in position
            has_sl = 'stop_loss_order_id' in position
            
            if not has_tp or not has_sl:
                positions_without_tpsl.append(position_id)
                self.logger.debug(f"📋 {position_id}: TP={has_tp}, SL={has_sl}")
        
        if positions_without_tpsl:
            self.logger.info(f"⚠️ {len(positions_without_tpsl)} posições sem TP/SL completo")
        
        return positions_without_tpsl
    
    def emergency_add_tpsl_to_all(self):
        """
        Adiciona TP/SL a TODAS as posições que não têm
        🎯 USO FUTURO: Função de emergência para proteger posições
        """
        
        positions_without = self.get_positions_without_tpsl()
        
        if not positions_without:
            self.logger.info("✅ Todas as posições já têm TP/SL")
            return
        
        self.logger.warning(f"🚨 EMERGÊNCIA: Adicionando TP/SL a {len(positions_without)} posições")
        
        success_count = 0
        for position_id in positions_without:
            position = self.active_positions[position_id]
            
            success = self._create_api_tp_sl_for_existing_position(
                position['order_id'],
                position['symbol'],
                position['side'],
                position['price'],
                position['quantity']
            )
            
            if success:
                success_count += 1
        
        self.logger.info(f"✅ TP/SL adicionado a {success_count}/{len(positions_without)} posições")

    # 🔧 EXEMPLO DE USO FUTURO NO LOOP PRINCIPAL
    def periodic_tpsl_check(self):
        """
        Verificação periódica de TP/SL (pode ser chamada no loop principal)
        """
        
        # Verificar apenas a cada 5 minutos para não sobrecarregar
        current_time = datetime.now()
        
        if not hasattr(self, 'last_tpsl_check'):
            self.last_tpsl_check = current_time
        
        time_since_check = (current_time - self.last_tpsl_check).total_seconds()
        
        if time_since_check >= 300:  # 5 minutos
            self.logger.info("🔍 Verificação periódica de TP/SL...")
            
            # Verificar posições sem TP/SL
            positions_without = self.get_positions_without_tpsl()
            
            if positions_without:
                self.logger.warning(f"⚠️ {len(positions_without)} posições sem TP/SL - corrigindo...")
                self.check_and_adjust_tpsl()
            
            self.last_tpsl_check = current_time

    def _get_symbol_tick_size(self, symbol: str) -> float:
        """Obtém tick_size específico do símbolo"""
        try:
            info = self.auth.get_symbol_info(symbol)
            if info and 'tick_size' in info:
                tick_size = float(info['tick_size'])
                self.logger.debug(f"📏 {symbol} tick_size da API: {tick_size}")
                return tick_size
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao obter tick_size para {symbol}: {e}")
        
        # Fallback para valores conhecidos
        tick_sizes = {
            'BTC': 0.00001,
            'ETH': 0.0001, 
            'SOL': 0.01,
            'BNB': 0.001,
            'AVAX': 0.001,
            'LTC': 0.001
        }
        fallback = tick_sizes.get(symbol, 0.01)
        self.logger.warning(f"⚠️ Usando tick_size fallback para {symbol}: {fallback}")
        return fallback

    def _round_to_tick_size(self, price: float, tick_size: float) -> float:
        """
        Arredonda preço para múltiplo válido do tick_size
        🔧 BASEADO NO grid_calculator.py que já funciona
        """
        
        if tick_size >= 1:
            return float(round(price))
        
        # Usar Decimal para evitar erros de precisão
        from decimal import Decimal, ROUND_HALF_UP
        
        price_dec = Decimal(str(price))
        tick_dec = Decimal(str(tick_size))
        
        # Arredondar para múltiplo mais próximo
        multiple = (price_dec / tick_dec).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        result = float(multiple * tick_dec)
        
        # Forçar casas decimais corretas baseado no tick_size
        if tick_size == 0.01:
            return round(result, 2)
        elif tick_size == 0.001:
            return round(result, 3)
        elif tick_size == 0.0001:
            return round(result, 4)
        elif tick_size == 0.00001:
            return round(result, 5)
        else:
            return round(result, 8)  # Máximo de 8 decimais para crypto

    def _setup_internal_monitoring(self, position_id: str, entry_price: float, side: str):
        """Configurar monitoramento interno como fallback"""
        self.position_entry_prices[position_id] = entry_price
        self.position_max_profit[position_id] = 0.0
        
        # Calcular níveis
        if side == 'LONG':
            stop_loss_price = entry_price * (1 - self.stop_loss_percent / 100)
            take_profit_price = entry_price * (1 + self.take_profit_percent / 100)
        else:
            stop_loss_price = entry_price * (1 + self.stop_loss_percent / 100)
            take_profit_price = entry_price * (1 - self.take_profit_percent / 100)
        
        self.logger.info(f"📊 Monitoramento interno ativo:")
        self.logger.info(f"  Stop Loss: ${stop_loss_price:.4f}")
        self.logger.info(f"  Take Profit: ${take_profit_price:.4f}")
        if self.trailing_stop_enabled:
            self.logger.info(f"  Trailing: {self.trailing_stop_percent}% (ativo após TP)")
    
    def _create_api_tp_sl(self, order_id: str, symbol: str, side: str, entry_price: float, quantity: float):
        """Criar TP/SL usando endpoint nativo da API Pacifica.fi CORRIGIDO"""
        
        try:
            # 🔧 CORREÇÃO CRÍTICA: Usar preço ATUAL, não preço de entrada
            current_price = self._get_current_price(symbol)
            if not current_price:
                self.logger.error(f"❌ Não foi possível obter preço atual para {symbol}")
                return False
            
            # Log da correção de preço
            price_change_percent = ((current_price - entry_price) / entry_price) * 100
            self.logger.info(f"💰 {symbol} - Entry: ${entry_price:.6f}, Atual: ${current_price:.6f} ({price_change_percent:+.2f}%)")
            
            # Calcular preços de TP e SL baseado no preço ATUAL
            if side == 'bid':  # Long position (comprando)
                stop_loss_price = current_price * (1 - self.stop_loss_percent / 100)
                take_profit_price = current_price * (1 + self.take_profit_percent / 100)
                api_side = 'bid'  # Para posição LONG, as ordens de TP/SL são 'bid'
            else:  # Short position (vendendo) - side == 'ask'
                stop_loss_price = current_price * (1 + self.stop_loss_percent / 100)
                take_profit_price = current_price * (1 - self.take_profit_percent / 100)
                api_side = 'ask'  # Para posição SHORT, as ordens de TP/SL são 'ask'
            
            self.logger.info(f"Criando TP/SL via API para {symbol} {side}:")
            self.logger.info(f"  Stop Loss: ${stop_loss_price:.4f} ({self.stop_loss_percent}%)")
            self.logger.info(f"  Take Profit: ${take_profit_price:.4f} ({self.take_profit_percent}%)")
            
            # 🔧 CORRIGIR: Usar método correto da API conforme documentação
            result = self.auth.create_position_tp_sl(
                symbol=symbol,
                side=api_side,
                take_profit_stop=take_profit_price,
                take_profit_limit=take_profit_price * 0.999 if side == 'bid' else take_profit_price * 1.001,
                stop_loss_stop=stop_loss_price,
                stop_loss_limit=stop_loss_price * 0.999 if side == 'ask' else stop_loss_price * 1.001
            )
            
            if result and result.get('success'):
                self.logger.info(f"✅ TP/SL criado via API para ordem {order_id}")
                self.logger.info(f"📊 TP/SL ID: {result.get('data', {}).get('id', 'N/A')}")
                return True
            else:
                self.logger.error(f"❌ Falha ao criar TP/SL via API: {result}")
                # Fallback para monitoramento interno
                self.logger.info("🔄 Usando fallback para monitoramento interno")
                self._setup_internal_monitoring(order_id, entry_price, side)
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao criar TP/SL via API: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Fallback para monitoramento interno
            self.logger.info("🔄 Usando fallback para monitoramento interno")
            self._setup_internal_monitoring(order_id, entry_price, side)
            return False
    
    def _setup_internal_monitoring(self, order_id: str, entry_price: float, side: str):
        """Configurar monitoramento interno como fallback"""
        position_id = f"{order_id}_internal"
        self.position_entry_prices[position_id] = entry_price
        self.position_max_profit[position_id] = 0.0
        
        # Calcular níveis
        if side == 'LONG':
            stop_loss_price = entry_price * (1 - self.stop_loss_percent / 100)
            take_profit_price = entry_price * (1 + self.take_profit_percent / 100)
        else:
            stop_loss_price = entry_price * (1 + self.stop_loss_percent / 100)
            take_profit_price = entry_price * (1 - self.take_profit_percent / 100)
        
        self.logger.info(f"📊 Monitoramento interno ativo:")
        self.logger.info(f"  Stop Loss: ${stop_loss_price:.4f}")
        self.logger.info(f"  Take Profit: ${take_profit_price:.4f}")

    def _log_positions_summary(self):
        """Log resumo das posições"""
        total_positions = len(self.active_positions)
        total_margin = sum(pos['margin_used'] for pos in self.active_positions.values())
        
        self.logger.info(f"📊 Posições ativas: {total_positions}/{self.max_concurrent_trades}")
        self.logger.info(f"💰 Margem total usada: ${total_margin:.2f}")
        
        # Resumo por símbolo
        symbol_summary = {}
        for pos in self.active_positions.values():
            symbol = pos['symbol']
            if symbol not in symbol_summary:
                symbol_summary[symbol] = {'count': 0, 'margin': 0}
            symbol_summary[symbol]['count'] += 1
            symbol_summary[symbol]['margin'] += pos['margin_used']
        
        for symbol, data in symbol_summary.items():
            self.logger.info(f"  {symbol}: {data['count']} posições, ${data['margin']:.2f} margem")
    
    def get_strategy_status(self) -> Dict:
        """Status da estratégia"""
        
        total_margin = sum(pos['margin_used'] for pos in self.active_positions.values())
        
        return {
            'active_positions': len(self.active_positions),
            'max_positions': self.max_concurrent_trades,
            'capital_used': total_margin * self.leverage,
            'margin_used': total_margin,
            'unrealized_pnl': 0.0,
            'symbols_tracked': len(self.symbols),
            'signals_generated_today': 0,
            'avg_signal_strength': 0,
            'position_size_usd': self.position_size_usd,
            'leverage': self.leverage
        }
    
    def update_all_prices(self):
        """Atualizar preços de todos os símbolos"""
        try:
            prices_data = self.auth.get_prices()
            
            if prices_data and 'data' in prices_data:
                prices_updated = 0
                
                for item in prices_data['data']:
                    symbol = item.get('symbol')
                    
                    if symbol in self.symbols:
                        price = item.get('mid') or item.get('mark') or item.get('oracle')
                        
                        if price:
                            price_float = float(price)
                            self.update_market_data(symbol, price_float)
                            prices_updated += 1
                
                self.logger.debug(f"Preços atualizados: {prices_updated}/{len(self.symbols)} símbolos")
                
        except Exception as e:
            self.logger.error(f"Erro ao atualizar preços: {e}")

class MultiAssetScalpingBot:
    def __init__(self):
        self.logger = self._setup_logging()
        
        # Sistema de shutdown gracioso
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Componentes
        self.auth = None
        self.position_mgr = None
        self.strategy = None
        self.performance_tracker = None
        
        # Controles de tempo
        self.start_time = datetime.now()
        self.last_price_update = None
        self.last_balance_check = None
        self.last_status_log = None
        
        # Configurações de timing
        self.price_check_interval = int(os.getenv('PRICE_CHECK_INTERVAL_SECONDS', '15'))
        self.balance_check_interval = 300
        self.status_log_interval = 180
        self.heartbeat_interval = 60
        
        # Métricas
        self.session_stats = {
            'total_signals': 0,
            'trades_opened': 0,
            'api_calls': 0,
            'errors': 0
        }
        
        self.logger.info("🚀 MULTI-ASSET SCALPING BOT COM TP/SL AUTOMÁTICO")
    
    def _setup_logging(self):
        """Configura logging"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"multi_asset_scalping_{timestamp}.log"
        
        logger = logging.getLogger('ScalpingBot')
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        return logger
    
    def _signal_handler(self, signum, frame):
        """Handler shutdown"""
        self.logger.info(f"Sinal {signum} recebido - iniciando shutdown...")
        self.running = False
    
    def initialize_components(self):
        """Inicializa componentes"""
        try:
            self.logger.info("🔧 Inicializando componentes...")
            
            # Autenticação
            self.auth = PacificaAuth()
            if not self.auth.test_connection():
                return False
            
            # Position Manager
            self.position_mgr = PositionManager(self.auth)
            if not self.position_mgr.update_account_state():
                return False
            
            # Performance Tracker
            self.performance_tracker = PerformanceTracker(symbols=self.symbols)
            initial_balance = self.position_mgr.get_current_balance()
            self.performance_tracker.update_balance(initial_balance)
            
            # Estratégia Multi-Asset
            self.strategy = MultiAssetScalpingStrategy(self.auth, self.position_mgr)
            
            self.logger.info("✅ Todos os componentes inicializados!")
            self._log_initial_setup()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro na inicialização: {e}")
            return False
    
    def _log_initial_setup(self):
        """Log configuração inicial"""
        balance = self.position_mgr.get_current_balance()
        
        self.logger.info("📋 CONFIGURAÇÃO INICIAL:")
        self.logger.info(f"💰 Saldo: ${balance:.2f}")
        self.logger.info(f"📊 Símbolos: {len(self.strategy.symbols)}")
        self.logger.info(f"💵 Posição por trade: ${self.strategy.position_size_usd}")
        self.logger.info(f"⚖️ Leverage: {self.strategy.leverage}x")
        self.logger.info(f"🔄 Max trades simultâneos: {self.strategy.max_concurrent_trades}")
        self.logger.info(f"🚫 Múltiplos por símbolo: {'SIM' if self.strategy.allow_multiple_per_symbol else 'NÃO'}")
        self.logger.info(f"🎯 TP/SL automático: {'ATIVO' if self.strategy.auto_close_enabled else 'INATIVO'}")
    
    def run_main_loop(self):
        """Loop principal"""
        self.logger.info("🎮 INICIANDO LOOP PRINCIPAL - MULTI ASSETS COM TP/SL")
        
        iteration_count = 0
        last_heartbeat = datetime.now()
        
        while self.running:
            try:
                iteration_count += 1
                current_time = datetime.now()
                
                # Heartbeat
                if (current_time - last_heartbeat).total_seconds() >= self.heartbeat_interval:
                    self._log_heartbeat(iteration_count)
                    last_heartbeat = current_time
                
                # Atualizar preços de todos os símbolos
                if (not self.last_price_update or 
                    (current_time - self.last_price_update).total_seconds() >= self.price_check_interval):
                    
                    self.session_stats['api_calls'] += 1
                    self.strategy.update_all_prices()
                    self.last_price_update = current_time
                
                # Verificar saldo
                if (not self.last_balance_check or 
                    (current_time - self.last_balance_check).total_seconds() >= self.balance_check_interval):
                    
                    self._check_account_health()
                    self.last_balance_check = current_time
                
                # Status detalhado
                if (not self.last_status_log or 
                    (current_time - self.last_status_log).total_seconds() >= self.status_log_interval):
                    
                    self._log_detailed_status()
                    self.last_status_log = current_time
                
                # Verificar parada de emergência
                should_stop, reason = self.position_mgr.should_stop_trading()
                if should_stop:
                    self.logger.error(f"🛑 PARADA DE EMERGÊNCIA: {reason}")
                    break
                
                time.sleep(3)
                
            except KeyboardInterrupt:
                self.logger.info("⌨️ Interrupção manual")
                break
                
            except Exception as e:
                self.logger.error(f"❌ Erro no loop: {e}")
                self.session_stats['errors'] += 1
                
                if self.session_stats['errors'] > 10:
                    self.logger.error("🛑 Muitos erros - parando")
                    break
                
                time.sleep(5)
        
        self.logger.info("🔄 Saindo do loop principal...")
    
    def _log_heartbeat(self, iteration):
        """Log heartbeat"""
        uptime = datetime.now() - self.start_time
        uptime_str = str(uptime).split('.')[0]
        
        strategy_status = self.strategy.get_strategy_status()
        
        self.logger.info(f"💓 HEARTBEAT #{iteration} | Uptime: {uptime_str}")
        self.logger.info(f"🔄 Posições: {strategy_status['active_positions']}/{strategy_status['max_positions']}")
        self.logger.info(f"📊 Símbolos monitorados: {strategy_status['symbols_tracked']}")
    
    def _check_account_health(self):
        """Verificar saúde da conta"""
        self.logger.info("🏥 Verificando saúde da conta...")
        
        success = self.position_mgr.update_account_state()
        if success:
            is_safe, message = self.position_mgr.check_margin_safety()
            self.logger.info(f"{'✅' if is_safe else '⚠️'} {message}")
            
            balance = self.position_mgr.get_current_balance()
            self.logger.info(f"💰 Saldo: ${balance:.2f}")
    
    def _log_detailed_status(self):
        """Status detalhado"""
        self.logger.info("📊 STATUS DETALHADO")
        
        strategy_status = self.strategy.get_strategy_status()
        
        self.logger.info(f"⚡ Estratégia: Multi-Asset Scalping")
        self.logger.info(f"🔄 Posições: {strategy_status['active_positions']}/{strategy_status['max_positions']}")
        self.logger.info(f"💰 Capital usado: ${strategy_status['capital_used']:.2f}")
        self.logger.info(f"📊 Margem usada: ${strategy_status['margin_used']:.2f}")
        self.logger.info(f"📈 Símbolos: {strategy_status['symbols_tracked']}")
        
        uptime = (datetime.now() - self.start_time).total_seconds() / 3600
        self.logger.info(f"🔗 API calls: {self.session_stats['api_calls']}")
        self.logger.info(f"⏰ Uptime: {uptime:.1f}h")
    
    def _log_emergency_status(self):
        """Log periódico do sistema de emergência"""
        stats = self.emergency_sl.get_statistics()
        
        if stats['total_emergency_closures'] > 0:
            self.logger.info("🚨 Emergency SL Stats:")
            self.logger.info(f"  Total closures: {stats['total_emergency_closures']}")
            
            if stats['recent_closures']:
                self.logger.info("  Recent:")
                for closure in stats['recent_closures']:
                    self.logger.info(f"    {closure['symbol']}: {closure['reason']}")
    
    def shutdown_gracefully(self):
        """Shutdown gracioso"""
        self.logger.info("🔄 SHUTDOWN GRACIOSO")
        
        try:
            if hasattr(self.strategy, 'active_positions'):
                positions = len(self.strategy.active_positions)
                if positions > 0:
                    self.logger.info(f"⏳ {positions} posições ativas")
                    self.logger.info("💡 Posições serão fechadas automaticamente pelo TP/SL")
            
            uptime = datetime.now() - self.start_time
            self.logger.info(f"⏰ Duração: {str(uptime).split('.')[0]}")
            self.logger.info(f"🔗 API calls: {self.session_stats['api_calls']}")
            
        except Exception as e:
            self.logger.error(f"Erro durante shutdown: {e}")
        
        self.logger.info("✅ Shutdown concluído")

def main():
    """Função principal"""
    print("🚀 PACIFICA MULTI-ASSET SCALPING BOT v3.1")
    print("📊 Suporte a múltiplos ativos simultâneos")
    print("🎯 TP/SL automático integrado")
    print("⚙️ Totalmente configurável via .env")
    
    bot = MultiAssetScalpingBot()
    
    try:
        if not bot.initialize_components():
            return 1
        
        bot.run_main_loop()
        
    except KeyboardInterrupt:
        print("\n⌨️ Interrupção manual")
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        return 1
    finally:
        bot.shutdown_gracefully()
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)