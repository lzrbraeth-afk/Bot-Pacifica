"""
Position Manager - Gerenciamento de posições, margem e risco
"""

import os
import time
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta

class PositionManager:
    def __init__(self, auth_client):
        self.logger = logging.getLogger('PacificaBot.PositionManager')
        self.auth = auth_client
        
        # Configurações de risco
        self.margin_safety_percent = float(os.getenv('MARGIN_SAFETY_PERCENT', '20'))
        self.max_position_size = float(os.getenv('MAX_POSITION_SIZE_USD', '1000'))
        self.max_open_orders = int(os.getenv('MAX_OPEN_ORDERS', '20'))
        self.leverage = int(os.getenv('LEVERAGE', '10'))
        self.auto_reduce = os.getenv('AUTO_REDUCE_ON_LOW_MARGIN', 'true').lower() == 'true'
        
        # 🆕 Configurações de Auto-Close
        self.auto_close_on_limit = os.getenv('AUTO_CLOSE_ON_MAX_POSITION', 'true').lower() == 'true'
        # Estratégias: cancel_distant_orders, force_partial_sell, stop_buy_orders, hybrid
        self.auto_close_strategy = os.getenv('AUTO_CLOSE_STRATEGY', 'hybrid')  
        self.auto_close_percentage = float(os.getenv('AUTO_CLOSE_PERCENTAGE', '20'))  # Percentual da posição a vender
        
        # Estado interno
        self.open_orders = {}  # {order_id: order_data}
        self.positions = {}    # {symbol: position_data}
        self.account_balance = 0
        self.margin_used = 0
        self.margin_available = 0
        
        self.logger.info(f"PositionManager inicializado - Safety: {self.margin_safety_percent}%, Max Position: ${self.max_position_size}")
        if self.auto_close_on_limit:
            self.logger.info(f"🔧 Auto-close ATIVADO: {self.auto_close_strategy}, {self.auto_close_percentage}%")
    
    def update_account_state(self) -> bool:
        """Atualiza estado da conta (saldo, margem, posições) COM CORREÇÃO"""
        
        try:
            self.logger.info("🔄 Atualizando estado da conta...")
            
            # 1. Obter dados da conta
            account_data = self.auth.get_account_info()
            
            if account_data and 'data' in account_data:
                data = account_data['data']
                
                # Extrair informações conforme documentação
                self.account_balance = float(data.get('balance', 0))
                account_equity = float(data.get('account_equity', 0))
                self.margin_available = float(data.get('available_to_spend', 0))
                self.margin_used = float(data.get('total_margin_used', 0))
                
                positions_count = data.get('positions_count', 0)
                orders_count = data.get('orders_count', 0)
                
                self.logger.info(f"💰 Saldo: ${self.account_balance:.2f}")
                self.logger.info(f"💰 Equity: ${account_equity:.2f}")
                self.logger.info(f"💰 Margem Usada: ${self.margin_used:.2f}")
                self.logger.info(f"💰 Margem Disponível: ${self.margin_available:.2f}")
                self.logger.info(f"📊 Posições: {positions_count} | Ordens: {orders_count}")
                
                # Atualizar contadores internos baseado no estado real da API
                self._sync_internal_state_with_api()
                
                # 🆕 Verificar auto-close baseado no valor da posição atual
                self._check_position_size_and_auto_close()
                
                # 🆕 Simular posição baseada na margem usada para auto-close
                # Se temos margem usada > 0, deve haver posições
                if self.margin_used > 0:
                    symbol = os.getenv('SYMBOL', 'SOL')
                    
                    # Estimar quantidade da posição baseada na margem usada
                    # Assumir que toda margem usada é de uma posição long no símbolo principal
                    estimated_position_value = self.margin_used * self.leverage
                    current_price = self._get_current_price(symbol)
                    
                    if current_price > 0:
                        estimated_quantity = estimated_position_value / current_price
                        
                        # Atualizar posição simulada
                        self.positions[symbol] = {
                            'symbol': symbol,
                            'side': 'long',  # Assumir long baseado na margem positiva
                            'quantity': estimated_quantity,
                            'entry_price': current_price,  # Aproximação
                            'value': estimated_position_value,
                            'pnl': 0,  # Não temos PnL real
                            'simulated': True  # Marcar como simulado
                        }
                        
                        self.logger.debug(f"📊 Posição simulada: {symbol} = {estimated_quantity:.6f} (${estimated_position_value:.2f})")
                
                return True
            else:
                self.logger.error("❌ Falha ao obter dados da conta")
                return False
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao atualizar conta: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _sync_internal_state_with_api(self):
        """ Sincroniza estado interno com API real - FILTRANDO POR SÍMBOLO"""
        
        try:
            # Obter símbolo configurado
            current_symbol = os.getenv('SYMBOL', 'BTC')
            
            # Obter ordens abertas REAIS da API
            real_open_orders = self.auth.get_open_orders()
            
            if real_open_orders is None:
                self.logger.warning("⚠️ Não foi possível obter ordens da API para sincronização")
                return
            
            # 🔧 FILTRAR POR SÍMBOLO PRIMEIRO, DEPOIS POR TIPO
            symbol_filtered_orders = []
            other_symbol_orders = []
            
            for order in real_open_orders:
                if order.get('symbol') == current_symbol:
                    symbol_filtered_orders.append(order)
                else:
                    other_symbol_orders.append(order)
            
            # 🔧 FILTRAR APENAS ORDENS PRINCIPAIS (não TP/SL) DO SÍMBOLO ATUAL
            main_orders = []
            tp_sl_orders = []
            
            for order in symbol_filtered_orders:
                order_type = order.get('type', '')
                order_subtype = order.get('subType', '')
                
                # Identificar ordens TP/SL pelos campos específicos
                if (order_type in ['TAKE_PROFIT', 'STOP_LOSS'] or 
                    order_subtype in ['take_profit', 'stop_loss'] or
                    'tp' in order.get('label', '').lower() or
                    'sl' in order.get('label', '').lower()):
                    tp_sl_orders.append(order)
                else:
                    main_orders.append(order)
            
            # Atualizar contadores SOMENTE com ordens principais DO SÍMBOLO ATUAL
            self.open_orders.clear()
            
            for order in main_orders:
                order_id = order.get('order_id', str(order.get('id', '')))
                
                self.open_orders[order_id] = {
                    'price': float(order.get('price', 0)),
                    'quantity': float(order.get('quantity', 0)),
                    'side': order.get('side', ''),
                    'symbol': order.get('symbol', ''),
                    'timestamp': datetime.now().isoformat(),
                    'margin': 0,  # Será calculado se necessário
                    'value': 0    # Será calculado se necessário
                }
            
            # Log da sincronização
            total_api_orders = len(real_open_orders)
            total_symbol_orders = len(symbol_filtered_orders)
            other_symbols_orders = len(other_symbol_orders)
            main_count = len(main_orders)
            tp_sl_count = len(tp_sl_orders)
            
            self.logger.info(f"🔄 Sincronização concluída:")
            self.logger.info(f"   Total API: {total_api_orders} ordens")
            self.logger.info(f"   {current_symbol}: {total_symbol_orders} ordens")
            self.logger.info(f"   Outros símbolos: {other_symbols_orders} ordens (IGNORADAS)")
            self.logger.info(f"   {current_symbol} principais: {main_count} ordens")
            self.logger.info(f"   {current_symbol} TP/SL: {tp_sl_count} ordens")
            self.logger.info(f"   Contadas para limite MAX_OPEN_ORDERS: {main_count}")
            
            # Atualizar margem se necessário
            self._recalculate_margin_from_orders()
            
        except Exception as e:
            self.logger.error(f"❌ Erro na sincronização: {e}")

    def _recalculate_margin_from_orders(self):
        """ Recalcula margem baseado nas ordens principais atuais"""
        
        total_margin = 0
        
        for order_data in self.open_orders.values():
            price = order_data.get('price', 0)
            quantity = order_data.get('quantity', 0)
            
            if price > 0 and quantity > 0:
                order_value = price * quantity
                margin = order_value / self.leverage
                total_margin += margin
                
                # Atualizar dados da ordem
                order_data['value'] = order_value
                order_data['margin'] = margin
        
        # ⚠️ NÃO sobrescrever margin_used da API - ela inclui posições + ordens
        # self.margin_used já foi atualizada pela API em update_account_state()
        # total_margin aqui são apenas as ordens, não as posições abertas
        
        # Manter margem disponível como está da API
        # self.margin_available já foi atualizada pela API em update_account_state()
        
        self.logger.debug(f"💰 Margem recalculada: ${total_margin:.2f}")

    def can_place_order(self, order_value: float) -> Tuple[bool, str]:
        """Verifica se pode colocar uma nova ordem COM CORREÇÃO"""
        
        #  Sincronizar com API antes da verificação
        if hasattr(self, '_last_sync_time'):
            time_since_sync = time.time() - self._last_sync_time
            if time_since_sync > 30:  # Re-sincronizar a cada 30 segundos
                self._sync_internal_state_with_api()
        else:
            self._sync_internal_state_with_api()
        
        self._last_sync_time = time.time()
        
        # Calcular margem necessária
        margin_needed = order_value / self.leverage
        
        # Verificar margem disponível
        if margin_needed > self.margin_available:
            return False, f"Margem insuficiente: precisa ${margin_needed:.2f}, disponível ${self.margin_available:.2f}"
        
        # 🔧 SEGUNDA CORREÇÃO: Contar APENAS ordens principais
        main_orders_count = len(self.open_orders)  # Agora já filtrado na sincronização
        
        # Verificar número máximo de ordens
        if main_orders_count >= self.max_open_orders:
            return False, f"Máximo de ordens atingido: {main_orders_count}/{self.max_open_orders}"

        # Verificar posição máxima
        total_exposure = sum(o.get('value', 0) for o in self.open_orders.values()) + order_value
        if total_exposure > self.max_position_size:
            return False, f"Exposição máxima excedida: ${total_exposure:.2f} > ${self.max_position_size}"
        
        return True, "OK"

    def add_order(self, order_id: str, order_data: Dict) -> None:
        """Adiciona ordem ao tracking COM VERIFICAÇÃO"""
        
        # 🔧 CORREÇÃO: Verificar se não é ordem TP/SL
        order_type = order_data.get('type', '')
        if order_type in ['TAKE_PROFIT', 'STOP_LOSS']:
            self.logger.debug(f"🎯 Ordem TP/SL {order_id} não contada para limite")
            return  # Não adicionar ao tracking de ordens principais
        
        self.open_orders[order_id] = {
            **order_data,
            'timestamp': datetime.now().isoformat(),
            'margin': (order_data['price'] * order_data['quantity']) / self.leverage,
            'value': order_data['price'] * order_data['quantity']
        }
        
        self.logger.info(f"📝 Ordem principal adicionada: {order_id} - {order_data['side']} {order_data['quantity']} @ ${order_data['price']}")
        
        # Atualizar margem
        self.margin_used += self.open_orders[order_id]['margin']
        self.margin_available = self.account_balance - self.margin_used
        
        # Log do status atual
        self.logger.info(f"📊 Ordens principais ativas: {len(self.open_orders)}/{self.max_open_orders}")

    """ Funcao usada para ordens scalping - estrategia diferente 
   
    def can_open_new_positions(self) -> Tuple[bool, str]:
        #Verifica se é seguro abrir novas posições (sem parar o bot)
        
        # Margem baixa para novas posições (< 15%)
        if self.account_balance > 0:
            margin_percent = (self.margin_available / self.account_balance) * 100
            if margin_percent < 15:
                return False, f"⚠️ ⚠️ Margem baixa: {margin_percent:.1f}% < 15.0%"
        
        # Saldo zero ou negativo
        if self.account_balance <= 0:
            return False, "⛔ SALDO ZERADO"
        
        # Perda total > 30% (menor que o critério de parada)
        total_pnl = sum(p.get('realized_pnl', 0) for p in self.positions.values())
        if total_pnl < -(self.account_balance * 0.3):
            return False, f"⚠️ PERDA ALTA: ${total_pnl:.2f}"
        
        return True, "OK""

        """

    def get_status_summary(self) -> Dict:
        """Retorna resumo do status atual COM CORREÇÃO"""
        
        # 🔧 CORREÇÃO: Mostrar contagem correta
        main_orders_count = len(self.open_orders)  # Só ordens principais
        
        return {
            'account_balance': self.account_balance,
            'margin_used': self.margin_used,
            'margin_available': self.margin_available,
            'margin_percent': (self.margin_available / self.account_balance * 100) if self.account_balance > 0 else 0,
            'open_orders_count': main_orders_count,  # 🔧 CORRIGIDO
            'max_orders': self.max_open_orders,
            'positions': self.positions,
            'total_exposure': sum(o.get('value', 0) for o in self.open_orders.values())
        }
    
    def get_current_balance(self) -> float:
        """Retorna saldo atual da conta"""
        return self.account_balance

    def get_balance_change_percent(self, initial_balance: float) -> float:
        """Calcula mudança percentual do saldo"""
        if initial_balance == 0:
            return 0.0
        
        return ((self.account_balance - initial_balance) / initial_balance) * 100
    
    def check_margin_safety(self) -> Tuple[bool, str]:
        """Verifica se margem está em nível seguro"""
        
        if self.account_balance == 0:
            return False, "Saldo zero"
        
        # Calcular % de margem disponível
        margin_percent = (self.margin_available / self.account_balance) * 100
        
        if margin_percent < self.margin_safety_percent:
            warning = f"⚠️ Margem baixa: {margin_percent:.1f}% < {self.margin_safety_percent}%"
            self.logger.warning(warning)
            
            if self.auto_reduce:
                self.logger.info("🔧 Auto-reduce ativado - cancelando ordens menos prioritárias")
                self._reduce_exposure()
            
            return False, warning
        
        return True, f"Margem OK: {margin_percent:.1f}%"
    
    def remove_order(self, order_id: str) -> Optional[Dict]:
        """Remove ordem do tracking (executada ou cancelada)"""
        
        if order_id in self.open_orders:
            order = self.open_orders.pop(order_id)
            
            # Liberar margem
            self.margin_used -= order['margin']
            self.margin_available = self.account_balance - self.margin_used
            
            self.logger.info(f"✅ Ordem removida: {order_id}")
            return order
        
        return None
    
    def update_position(self, symbol: str, side: str, quantity: float, price: float) -> None:
        """Atualiza posição após execução de ordem"""
        
        if symbol not in self.positions:
            self.positions[symbol] = {
                'quantity': 0,
                'avg_price': 0,
                'realized_pnl': 0,
                'unrealized_pnl': 0
            }
        
        pos = self.positions[symbol]

        # 🔧 MODIFIED: Log antes da atualização
        self.logger.debug(f"📊 Atualizando posição {symbol}:")
        self.logger.debug(f"   Antes: qty={pos['quantity']}, avg_price={pos['avg_price']}")
        self.logger.debug(f"   Operação: {side} {quantity} @ ${price}")
        # 🔧 END MODIFIED
        
        if side == 'buy':
            # Adicionar à posição long
            total_value = (pos['quantity'] * pos['avg_price']) + (quantity * price)
            pos['quantity'] += quantity
            pos['avg_price'] = total_value / pos['quantity'] if pos['quantity'] > 0 else 0
        else:  # sell
            # Reduzir posição ou adicionar short
            if pos['quantity'] > 0:
                # Fechando long - calcular lucro realizado
                pnl = (price - pos['avg_price']) * min(quantity, pos['quantity'])
                pos['realized_pnl'] += pnl
                self.logger.info(f"💰 Lucro realizado: ${pnl:.2f}")
            
            pos['quantity'] -= quantity
        
        # 🔧 MODIFIED: Log depois da atualização
        self.logger.debug(f"   Depois: qty={pos['quantity']}, avg_price={pos['avg_price']}")
        self.logger.info(f"📊 Posição {symbol}: {pos['quantity']:.6f} @ ${pos['avg_price']:.2f}")
        # 🔧 END MODIFIED
        
        self.logger.info(f"📊 Posição {symbol}: {pos['quantity']:.4f} @ ${pos['avg_price']:.2f}")

    def get_active_positions_summary(self) -> Dict:
        """Retorna resumo simplificado das posições ativas"""
        
        longs = []
        shorts = []
        neutral = []
        
        for symbol, pos_data in self.positions.items():
            qty = pos_data.get('quantity', 0)
            
            if qty > 0.00001:  # Tolerância para arredondamento
                longs.append({
                    'symbol': symbol,
                    'quantity': qty,
                    'avg_price': pos_data.get('avg_price', 0)
                })
            elif qty < -0.00001:
                shorts.append({
                    'symbol': symbol,
                    'quantity': abs(qty),
                    'avg_price': pos_data.get('avg_price', 0)
                })
            else:
                if pos_data.get('realized_pnl', 0) != 0:
                    neutral.append({
                        'symbol': symbol,
                        'pnl': pos_data.get('realized_pnl', 0)
                    })
        
        return {
            'longs': longs,
            'shorts': shorts,
            'neutral': neutral,
            'total_longs': len(longs),
            'total_shorts': len(shorts)
        }
    
    def calculate_unrealized_pnl(self, symbol: str, current_price: float) -> float:
        """Calcula PNL não realizado"""
        
        if symbol not in self.positions:
            return 0
        
        pos = self.positions[symbol]
        
        if pos['quantity'] == 0:
            return 0
        
        pnl = (current_price - pos['avg_price']) * pos['quantity']
        pos['unrealized_pnl'] = pnl
        
        return pnl
    
    def _reduce_exposure(self) -> None:
        """Reduz exposição cancelando ordens menos importantes"""
        
        if not self.open_orders:
            return
        
        # Ordenar ordens por distância do preço atual (cancelar as mais distantes)
        # Isso é um placeholder - implementar lógica real baseada na estratégia
        
        orders_to_cancel = []
        
        # Pegar 30% das ordens mais distantes
        cancel_count = max(1, len(self.open_orders) // 3)
        
        for order_id in list(self.open_orders.keys())[:cancel_count]:
            orders_to_cancel.append(order_id)
        
        self.logger.warning(f"🔪 Reduzindo exposição: cancelando {len(orders_to_cancel)} ordens")
        
        for order_id in orders_to_cancel:
            self.remove_order(order_id)
            # Aqui você chamaria a API para cancelar de fato
            # self.auth.cancel_order(order_id)

    # Função completamente nova para estatísticas
    def get_trade_summary(self) -> Dict:
        """Retorna resumo dos trades realizados"""
        
        total_pnl = 0
        trade_count = 0
        winning_trades = 0
        losing_trades = 0
        
        for symbol, pos in self.positions.items():
            pnl = pos.get('realized_pnl', 0)
            total_pnl += pnl
            
            if pnl > 0:
                winning_trades += 1
            elif pnl < 0:
                losing_trades += 1
            
            if pnl != 0:
                trade_count += 1
        
        win_rate = (winning_trades / trade_count * 100) if trade_count > 0 else 0
        
        return {
            'total_trades': trade_count,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl
        }
    
    def apply_loss_management(self, symbol: str = None) -> Dict:
        """
        🔴 FUNÇÃO PÚBLICA: Aplica gestão de loss cancelando ordens de compra
        
        Use esta função quando:
        - Posição está em loss significativo
        - Não quer acumular mais do ativo
        - Quer manter apenas ordens de venda para reduzir exposição
        
        Args:
            symbol: Símbolo a aplicar (padrão: SOL)
            
        Returns:
            Dict com resultado da operação
        """
        
        try:
            if not symbol:
                symbol = os.getenv('SYMBOL', 'SOL')
            
            # Obter informações antes
            buy_orders_before = len([o for o in self.open_orders.values() 
                                   if o['side'] in ['buy', 'bid'] and o['symbol'] == symbol])
            sell_orders_before = len([o for o in self.open_orders.values() 
                                    if o['side'] in ['sell', 'ask'] and o['symbol'] == symbol])
            
            self.logger.info(f"🔴 INICIANDO LOSS MANAGEMENT para {symbol}")
            self.logger.info(f"📊 Estado atual: {buy_orders_before} compras, {sell_orders_before} vendas")
            
            # Aplicar cancelamento de compras
            cancelled_count = self.cancel_buy_orders_only(symbol)
            
            # Obter informações depois
            buy_orders_after = len([o for o in self.open_orders.values() 
                                  if o['side'] in ['buy', 'bid'] and o['symbol'] == symbol])
            sell_orders_after = len([o for o in self.open_orders.values() 
                                   if o['side'] in ['sell', 'ask'] and o['symbol'] == symbol])
            
            result = {
                'success': True,
                'symbol': symbol,
                'cancelled_buy_orders': cancelled_count,
                'remaining_buy_orders': buy_orders_after,
                'remaining_sell_orders': sell_orders_after,
                'message': f"Canceladas {cancelled_count} ordens de compra. Mantidas {sell_orders_after} ordens de venda."
            }
            
            self.logger.info(f"✅ LOSS MANAGEMENT concluído: {result['message']}")
            
            return result
            
        except Exception as e:
            error_msg = f"Erro no loss management: {e}"
            self.logger.error(f"❌ {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'symbol': symbol,
                'cancelled_buy_orders': 0
            }
    
    def should_stop_trading(self) -> Tuple[bool, str]:
        """Verifica se deve parar de operar (condições de emergência)"""
        
        # Margem crítica (< 10%)
        if self.account_balance > 0:
            margin_percent = (self.margin_available / self.account_balance) * 100
            if margin_percent < 10:
                return True, f"⛔ MARGEM CRÍTICA: {margin_percent:.1f}%"
        
        # Saldo zero ou negativo
        if self.account_balance <= 0:
            return True, "⛔ SALDO ZERADO"
        
        # Perda total > 50%
        total_pnl = sum(p.get('realized_pnl', 0) for p in self.positions.values())
        if total_pnl < -(self.account_balance * 0.5):
            return True, f"⛔ PERDA EXCESSIVA: ${total_pnl:.2f}"
        
        return False, "OK"
    
    def _get_current_price(self, symbol: str) -> float:
        """Obtém preço atual do símbolo"""
        try:
            price_data = self.auth.get_prices()
            if price_data and 'data' in price_data:
                for item in price_data['data']:
                    item_symbol = item.get('symbol', '')
                    
                    if item_symbol == symbol:
                        # Usar 'mark' como preço principal
                        price = float(item.get('mark', 0))
                        self.logger.debug(f"✅ Preço {symbol}: ${price}")
                        return price
                        
                self.logger.warning(f"⚠️ Símbolo {symbol} não encontrado nos preços")
                return 0
            else:
                self.logger.warning("⚠️ Dados de preço não encontrados na resposta")
                return 0
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter preço {symbol}: {e}")
            return 0

    def _check_position_size_and_auto_close(self):
        """🆕 Verifica se a posição atual excede o limite e ativa auto-close"""
        
        if not self.auto_close_on_limit:
            return  # Auto-close desabilitado
        
        try:
            # Calcular valor total das posições usando margem usada como proxy
            # A margem usada reflete o valor notional das posições atuais
            position_value_usd = self.margin_used * self.leverage
            
            self.logger.info(f"💡 Debug cálculo posição: margin_used=${self.margin_used} * leverage={self.leverage} = ${position_value_usd}")
            self.logger.info(f"🔍 Verificando tamanho da posição: ${position_value_usd:.2f} vs limite ${self.max_position_size:.2f}")
            
            if position_value_usd > self.max_position_size:
                self.logger.warning(f"⚠️ Posição excede limite: ${position_value_usd:.2f} > ${self.max_position_size:.2f}")
                self.logger.info("🔧 Auto-close ativado - reduzindo posição...")
                
                # Calcular quanto precisa ser fechado
                excess_amount = position_value_usd - self.max_position_size
                self.logger.info(f"🎯 Tentando liberar espaço para ordem de ${excess_amount:.2f}")
                
                # Executar auto-close baseado na estratégia
                freed_amount = self._auto_close_positions(excess_amount)
                
                if freed_amount > 0:
                    self.logger.info(f"✅ Auto-close liberou ${freed_amount:.2f}")
                else:
                    self.logger.warning("⚠️ Não foi possível reduzir a posição automaticamente")
                    
        except Exception as e:
            self.logger.error(f"❌ Erro na verificação auto-close: {e}")

    def _auto_close_positions(self, target_amount: float) -> float:
        """🆕 Executa auto-close baseado na estratégia configurada"""
        
        freed_total = 0.0
        
        try:
            # 🆕 ALIASES para compatibilidade com documentação
            strategy = self.auto_close_strategy
            
            # Mapeamento de aliases da documentação para nomes internos
            strategy_aliases = {
                'cancel_orders': 'cancel_distant_orders',
                'force_sell': 'force_partial_sell', 
                'stop_buy': 'stop_buy_orders'
            }
            
            # Usar alias se existir, senão usar nome original
            internal_strategy = strategy_aliases.get(strategy, strategy)
            
            if internal_strategy == 'cancel_distant_orders':
                # Estratégia 1: Apenas cancelar ordens distantes
                freed_total = self._cancel_distant_sell_orders()
                
            elif internal_strategy == 'force_partial_sell':
                # Estratégia 2: Venda forçada de parte da posição
                freed_total = self._force_partial_sell()
                
            elif internal_strategy == 'stop_buy_orders':
                # 🆕 Estratégia 3: LOSS MANAGEMENT - Cancelar ordens de compra apenas
                self.logger.info(f"🔴 LOSS MANAGEMENT ativado - cancelando ordens de compra")
                cancelled_count = self.cancel_buy_orders_only()
                # Não liberamos margem diretamente, mas evitamos acúmulo
                freed_total = 0.0  # Não conta como margem liberada
                
            elif internal_strategy == 'hybrid':
                # Estratégia 4: Híbrida - tentar cancelar primeiro, depois vender
                freed_total = self._cancel_distant_sell_orders()
                
                if freed_total < target_amount:
                    self.logger.info(f"🔄 Ainda precisa de ${target_amount - freed_total:.2f} - vendendo posição parcial")
                    additional_freed = self._force_partial_sell()
                    freed_total += additional_freed
            
            else:
                self.logger.warning(f"⚠️ Estratégia AUTO_CLOSE desconhecida: {strategy}")
                return 0.0
            
            return freed_total
            
        except Exception as e:
            self.logger.error(f"❌ Erro no auto-close: {e}")
            return 0.0

    def _cancel_distant_sell_orders(self) -> float:
        """Cancela ordens sell muito distantes do preço atual"""
        
        try:
            symbol = os.getenv('SYMBOL', 'SOL')
            current_price = self._get_current_price(symbol)
            
            if current_price <= 0:
                self.logger.warning("⚠️ Não foi possível obter preço atual para cancelar ordens")
                return 0.0
            
            orders_to_cancel = []
            total_freed = 0
            
            # Identificar ordens sell > 2% acima do preço atual
            for order_id, order_data in self.open_orders.items():
                if (order_data['side'] == 'sell' and 
                    order_data['symbol'] == symbol):
                    
                    order_price = order_data['price']
                    distance_percent = ((order_price - current_price) / current_price) * 100
                    
                    # Cancelar sells > 2% acima do preço aproximado
                    if distance_percent > 2.0:
                        orders_to_cancel.append((order_id, order_data))
                        total_freed += order_data.get('value', 0)
            
            # Cancelar ordens identificadas
            cancelled_count = 0
            for order_id, order_data in orders_to_cancel:
                try:
                    # Cancelar na API
                    result = self.auth.cancel_order(str(order_id), symbol)
                    if result:  # cancel_order retorna True/False
                        self.remove_order(order_id)
                        cancelled_count += 1
                        self.logger.info(f"🗑️ Cancelada ordem distante: SELL @ ${order_data['price']:.2f}")
                        
                except Exception as e:
                    self.logger.error(f"❌ Erro ao cancelar ordem {order_id}: {e}")
            
            if cancelled_count > 0:
                self.logger.info(f"🗑️ {cancelled_count} ordens distantes canceladas - ${total_freed:.2f} liberado")
            
            return total_freed
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao cancelar ordens distantes: {e}")
            return 0.0

    def cancel_buy_orders_only(self, symbol: str = None) -> int:
        """
        🔴 LOSS MANAGEMENT: Cancela apenas ordens de COMPRA para evitar acumular mais posição
        Mantém ordens de VENDA para reduzir exposição
        
        Args:
            symbol: Símbolo (padrão: SOL do .env)
            
        Returns:
            int: Número de ordens canceladas
        """
        
        try:
            if not symbol:
                symbol = os.getenv('SYMBOL', 'SOL')
            
            current_price = self._get_current_price(symbol)
            
            if current_price <= 0:
                self.logger.warning("⚠️ Não foi possível obter preço atual para cancelar ordens de compra")
                return 0
            
            orders_to_cancel = []
            cancelled_count = 0
            
            # Identificar APENAS ordens de COMPRA (buy/bid)
            for order_id, order_data in self.open_orders.items():
                if (order_data['side'] in ['buy', 'bid'] and 
                    order_data['symbol'] == symbol):
                    
                    order_price = order_data['price']
                    orders_to_cancel.append((order_id, order_data))
            
            # Cancelar ordens de compra identificadas
            self.logger.info(f"🔴 LOSS MANAGEMENT: Cancelando {len(orders_to_cancel)} ordens de COMPRA para evitar acúmulo")
            
            for order_id, order_data in orders_to_cancel:
                try:
                    # Cancelar na API com símbolo
                    result = self.auth.cancel_order(str(order_id), symbol)
                    if result:  # cancel_order retorna True/False
                        self.remove_order(order_id)
                        cancelled_count += 1
                        self.logger.info(f"🗑️ Cancelada compra: BUY @ ${order_data['price']:.2f}")
                        
                except Exception as e:
                    self.logger.error(f"❌ Erro ao cancelar ordem de compra {order_id}: {e}")
            
            if cancelled_count > 0:
                self.logger.info(f"✅ LOSS MANAGEMENT: {cancelled_count} ordens de COMPRA canceladas")
                self.logger.info(f"🟢 Ordens de VENDA mantidas para reduzir exposição")
            else:
                self.logger.info(f"ℹ️ Nenhuma ordem de compra encontrada para cancelar")
            
            return cancelled_count
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao cancelar ordens de compra: {e}")
            return 0

    def _force_partial_sell(self) -> float:
        """Força venda de parte da posição para liberar espaço"""
        
        try:
            symbol = os.getenv('SYMBOL', 'SOL')
            
            # 🔧 SINCRONIZAR COM API ANTES DE TENTAR VENDA
            self.logger.info("🔄 Sincronizando posições com API antes da venda...")
            self._sync_internal_state_with_api()
            
            if symbol not in self.positions:
                self.logger.warning(f"⚠️ Nenhuma posição em {symbol} para vender")
                return 0.0
            
            pos = self.positions[symbol]
            current_qty = pos.get('quantity', 0)
            
            if current_qty <= 0:
                self.logger.warning(f"⚠️ Posição {symbol} já zerada ou short")
                return 0.0
            
            # 🔧 VERIFICAR SE REALMENTE EXISTE POSIÇÃO NA API
            self.logger.info(f"🔍 Verificando posição real na API para {symbol}...")
            api_positions = self.auth.get_positions()
            api_has_position = False
            api_quantity = 0.0
            
            if api_positions and isinstance(api_positions, list):
                for api_pos in api_positions:
                    if api_pos.get('symbol') == symbol:
                        # Usar 'amount' como quantidade, conforme documentação
                        api_amt = float(api_pos.get('amount', 0))
                        api_side = api_pos.get('side', '').lower()
                        # Aceitar tanto long (bid) quanto short (ask)
                        if abs(api_amt) > 0:
                            api_has_position = True
                            api_quantity = abs(api_amt)
                            position_side = api_side  # 'bid' (long) ou 'ask' (short)
                            break
            
            if not api_has_position or api_quantity <= 0:
                self.logger.warning(f"⚠️ API não confirma posição aberta em {symbol} (amount: {api_quantity})")
                self.logger.warning(f"⚠️ Removendo posição interna inconsistente")
                # Limpar posição interna inconsistente
                if symbol in self.positions:
                    del self.positions[symbol]
                return 0.0
            
            # 🔧 USAR QUANTIDADE REAL DA API PARA CÁLCULOS
            self.logger.info(f"✅ Posição confirmada na API: {api_quantity} {symbol}")
            
            # Calcular quantidade a vender (percentual configurado)
            sell_percentage = self.auto_close_percentage / 100
            qty_to_sell = api_quantity * sell_percentage
            # Determinar o lado da ordem para reduzir posição
            # Se posição é short (ask), ordem de compra ('bid')
            # Se posição é long (bid), ordem de venda ('ask')
            order_side = 'bid' if position_side == 'ask' else 'ask'
            if qty_to_sell < 0.001:
                self.logger.warning(f"⚠️ Quantidade a reduzir muito pequena: {qty_to_sell}")
                return 0.0
            
            # Obter preço atual do mercado (mais preciso que estimativas)
            current_price = self._get_current_price(symbol)
            if current_price <= 0:
                # Tentar usar preço da posição interna como fallback
                pos = self.positions.get(symbol, {})
                current_price = pos.get('entry_price', 0)
            
            if current_price <= 0:
                self.logger.warning(f"⚠️ Não foi possível obter preço para {symbol}")
                return 0.0
            
            freed_value = qty_to_sell * current_price
            
            # Log da operação
            self.logger.info(f"💰 Vendendo {self.auto_close_percentage}% da posição: {qty_to_sell:.6f} {symbol}")
            self.logger.info(f"💰 Preço atual: ${current_price:.2f} - Valor a liberar: ${freed_value:.2f}")
            
            # 🔥 EXECUÇÃO REAL DA VENDA (ativada)
            try:
                # Criar ordem para venda imediata  
                # Usar preço ligeiramente abaixo do mercado para garantir execução
                market_price = current_price * 0.999  # -0.1% do preço atual
                
                # 🔧 ARREDONDAR PREÇO PARA TICK_SIZE usando função do auth
                tick_size = self.auth._get_tick_size(symbol)
                market_price = self.auth._round_to_tick_size(market_price, tick_size)
                
                # 🔧 ARREDONDAR QUANTIDADE PARA LOT_SIZE  
                lot_size = 0.01  # SOL lot_size
                qty_to_sell = round(qty_to_sell / lot_size) * lot_size
                qty_to_sell = round(qty_to_sell, 2)  # Máximo 2 casas decimais
                
                self.logger.info(f"📄 Criando ordem: ask {qty_to_sell} {symbol} @ ${market_price}")
                
                # 🔧 VERIFICAÇÃO FINAL ANTES DE ENVIAR ORDEM
                # Dupla verificação para evitar erro "No position found for reduce-only order"
                final_check = self.auth.get_positions()
                has_final_position = False
                if final_check and isinstance(final_check, list):
                    for pos_check in final_check:
                        if pos_check.get('symbol') == symbol:
                            amt_final = float(pos_check.get('amount', 0))
                            side_final = pos_check.get('side', '').lower()
                            # Para short, precisa de pelo menos qty_to_sell em posição 'ask'; para long, em 'bid'
                            if position_side == 'ask' and abs(amt_final) >= qty_to_sell and side_final == 'ask':
                                has_final_position = True
                                break
                            elif position_side == 'bid' and abs(amt_final) >= qty_to_sell and side_final == 'bid':
                                has_final_position = True
                                break
                if not has_final_position:
                    self.logger.warning(f"⚠️ ABORTAR: Posição insuficiente na verificação final")
                    self.logger.warning(f"⚠️ Necessário: {qty_to_sell}, mas posição pode ter mudado")
                    return 0.0
                
                result = self.auth.create_order(
                    symbol=symbol,
                    side=order_side,  # lado correto para reduzir posição
                    amount=str(qty_to_sell),
                    price=str(market_price),
                    order_type="GTC",
                    reduce_only=True  # Para reduzir posição existente
                )
                
                if result and result.get('success'):
                    order_id = result.get('order_id', 'N/A')
                    self.logger.info(f"✅ Ordem de venda parcial criada!")
                    self.logger.info(f"✅ ID: {order_id} - Preço: ${market_price:.2f}")
                else:
                    error_msg = result.get('error', 'Erro desconhecido') if result else 'Resposta nula'
                    self.logger.error(f"❌ Falha na ordem reduce_only: {error_msg}")
                    
                    # 🔧 FALLBACK: Tentar sem reduce_only se o erro for de posição não encontrada
                    if "No position found" in str(error_msg):
                        self.logger.warning(f"🔄 Tentando ordem sem reduce_only como fallback...")
                        fallback_result = self.auth.create_order(
                            symbol=symbol,
                            side='ask',
                            amount=str(qty_to_sell),
                            price=str(market_price),
                            order_type="GTC",
                            reduce_only=False  # Sem reduce_only
                        )
                        
                        if fallback_result and fallback_result.get('success'):
                            order_id = fallback_result.get('order_id', 'N/A')
                            self.logger.info(f"✅ Ordem fallback criada: {order_id}")
                        else:
                            fallback_error = fallback_result.get('error', 'Erro desconhecido') if fallback_result else 'Resposta nula'
                            self.logger.error(f"❌ Fallback também falhou: {fallback_error}")
                            return 0.0
                    else:
                        return 0.0
                        
            except Exception as e:
                self.logger.error(f"❌ Erro ao executar venda: {e}")
                return 0.0
            
            # Atualizar posição internamente
            pos['quantity'] -= qty_to_sell
            if pos['quantity'] < 0.001:
                pos['quantity'] = 0  # Zerar se muito pequeno
            
            self.logger.info(f"📊 Nova posição {symbol}: {pos['quantity']:.6f}")
            
            return freed_value
            
        except Exception as e:
            self.logger.error(f"❌ Erro na venda parcial: {e}")
            return 0.0