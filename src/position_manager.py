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
        
        # Estado interno
        self.open_orders = {}  # {order_id: order_data}
        self.positions = {}    # {symbol: position_data}
        self.account_balance = 0
        self.margin_used = 0
        self.margin_available = 0
        
        self.logger.info(f"PositionManager inicializado - Safety: {self.margin_safety_percent}%, Max Position: ${self.max_position_size}")
    
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
        """ Sincroniza estado interno com API real"""
        
        try:
            # Obter ordens abertas REAIS da API
            real_open_orders = self.auth.get_open_orders()
            
            if real_open_orders is None:
                self.logger.warning("⚠️ Não foi possível obter ordens da API para sincronização")
                return
            
            # 🔧 FILTRAR APENAS ORDENS PRINCIPAIS (não TP/SL)
            main_orders = []
            tp_sl_orders = []
            
            for order in real_open_orders:
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
            
            # Atualizar contadores SOMENTE com ordens principais
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
            main_count = len(main_orders)
            tp_sl_count = len(tp_sl_orders)
            
            self.logger.info(f"🔄 Sincronização concluída:")
            self.logger.info(f"   Total API: {total_api_orders} ordens")
            self.logger.info(f"   Principais: {main_count} ordens")
            self.logger.info(f"   TP/SL: {tp_sl_count} ordens")
            self.logger.info(f"   Contadas para limite: {main_count}")
            
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
        
        # Atualizar margem usada
        self.margin_used = total_margin
        self.margin_available = self.account_balance - self.margin_used
        
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