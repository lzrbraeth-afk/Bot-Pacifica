"""
Dynamic Grid Strategy - Extensão da Grid Strategy com ajuste dinâmico de níveis
Esta estratégia ajusta automaticamente os níveis de venda quando o preço desce,
aumentando o volume de operações e mantendo a rentabilidade.
"""
import os
import time
import logging
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from src.grid_strategy import GridStrategy

class DynamicGridStrategy(GridStrategy):
    def __init__(self, auth_client, calculator, position_manager):
        super().__init__(auth_client, calculator, position_manager)
        
        # Configurações específicas para grid dinâmico
        self.dynamic_adjustment_threshold = float(os.getenv('DYNAMIC_THRESHOLD_PERCENT', '1.0'))
        self.max_adjustment_distance = float(os.getenv('MAX_ADJUSTMENT_DISTANCE_PERCENT', '5.0'))
        self.volume_boost_enabled = os.getenv('VOLUME_BOOST_ENABLED', 'true').lower() == 'true'
        
        # Rastreamento de preços
        self.last_adjustment_price = 0
        self.price_trend_history = []  # Histórico dos últimos preços
        self.trend_window = 10  # Janela para calcular tendência
        
        self.logger.info(f"🎯 Dynamic Grid Strategy inicializada")
        self.logger.info(f"   - Threshold de ajuste: {self.dynamic_adjustment_threshold}%")
        self.logger.info(f"   - Distância máxima: {self.max_adjustment_distance}%")
        self.logger.info(f"   - Volume boost: {'ATIVO' if self.volume_boost_enabled else 'INATIVO'}")
    
    def initialize_grid(self, current_price: float) -> bool:
        """Inicializa o grid e define preço base para ajustes dinâmicos"""
        
        result = super().initialize_grid(current_price)
        
        if result:
            self.last_adjustment_price = current_price
            self.price_trend_history = [current_price]
            self.logger.info(f"✅ Dynamic Grid inicializado com preço base: ${current_price}")
        
        return result
    
    def check_and_rebalance(self, current_price: float) -> None:
        """Verifica rebalanceamento com lógica de ajuste dinâmico"""
        
        if not self.grid_active:
            return
            
        # Atualizar histórico de preços
        self._update_price_history(current_price)
        
        # Verificar se precisa fazer ajuste dinâmico
        if self._should_adjust_dynamically(current_price):
            self.logger.info(f"🎯 Iniciando ajuste dinâmico do grid para ${current_price}")
            self._perform_dynamic_adjustment(current_price)
            self.last_adjustment_price = current_price
        else:
            # Rebalanceamento normal
            super().check_and_rebalance(current_price)
    
    def _update_price_history(self, current_price: float) -> None:
        """Atualiza histórico de preços para análise de tendência"""
        
        self.price_trend_history.append(current_price)
        
        # Manter apenas a janela especificada
        if len(self.price_trend_history) > self.trend_window:
            self.price_trend_history = self.price_trend_history[-self.trend_window:]
    
    def _should_adjust_dynamically(self, current_price: float) -> bool:
        """Verifica se deve fazer ajuste dinâmico baseado na movimentação de preço"""
        
        if self.last_adjustment_price == 0:
            return False
            
        # Calcular variação percentual desde o último ajuste
        price_change_percent = abs((current_price - self.last_adjustment_price) / self.last_adjustment_price * 100)
        
        # Verificar se ultrapassou o threshold
        if price_change_percent >= self.dynamic_adjustment_threshold:
            # Verificar tendência para confirmar movimento consistente
            if len(self.price_trend_history) >= 5:
                trend_direction = self._calculate_price_trend()
                
                # Só ajusta se há uma tendência clara
                if abs(trend_direction) > 0.5:  # Tendência significativa
                    self.logger.info(f"📈 Movimento detectado: {price_change_percent:.2f}% (threshold: {self.dynamic_adjustment_threshold}%)")
                    self.logger.info(f"📊 Tendência: {'BAIXISTA' if trend_direction < 0 else 'ALTISTA'} ({trend_direction:.2f})")
                    return True
        
        return False
    
    def _calculate_price_trend(self) -> float:
        """Calcula a tendência de preço (-1 a 1, onde -1 = forte baixa, 1 = forte alta)"""
        
        if len(self.price_trend_history) < 3:
            return 0
            
        # Calcular mudanças percentuais entre preços consecutivos
        changes = []
        for i in range(1, len(self.price_trend_history)):
            prev_price = self.price_trend_history[i-1]
            curr_price = self.price_trend_history[i]
            change_pct = (curr_price - prev_price) / prev_price
            changes.append(change_pct)
        
        # Calcular tendência média
        avg_change = sum(changes) / len(changes)
        
        # Normalizar para -1 a 1
        normalized_trend = max(-1, min(1, avg_change * 100))
        
        return normalized_trend
    
    def _perform_dynamic_adjustment(self, current_price: float) -> None:
        """Executa o ajuste dinâmico do grid"""
        
        try:
            trend_direction = self._calculate_price_trend()
            
            # Determinar estratégia de ajuste baseado na tendência
            if trend_direction < -0.3:  # Tendência baixista
                self._adjust_for_downtrend(current_price)
            elif trend_direction > 0.3:  # Tendência altista  
                self._adjust_for_uptrend(current_price)
            else:
                # Tendência lateral - rebalanceamento normal
                super().check_and_rebalance(current_price)
                
        except Exception as e:
            self.logger.error(f"❌ Erro no ajuste dinâmico: {e}")
            # Fallback para rebalanceamento normal
            super().check_and_rebalance(current_price)
    
    def _adjust_for_downtrend(self, current_price: float) -> None:
        """Ajusta o grid para tendência baixista - aproxima ordens de venda"""
        
        self.logger.info(f"📉 Ajustando para tendência baixista")
        
        # Buscar ordens de venda existentes
        all_open_orders = self.auth.get_open_orders()
        if not all_open_orders:
            return
            
        sell_orders_to_adjust = []
        
        # Filtrar ordens de venda do símbolo atual
        for order in all_open_orders:
            if (order.get('symbol') == self.symbol and 
                order.get('side') in ['sell', 'ask'] and
                not self._is_tp_sl_order(order)):
                
                order_price = float(order.get('price', 0))
                price_distance_pct = ((order_price - current_price) / current_price) * 100
                
                # Identificar ordens muito distantes do preço atual
                if price_distance_pct > self.max_adjustment_distance:
                    sell_orders_to_adjust.append({
                        'order_id': order.get('order_id'),
                        'old_price': order_price,
                        'quantity': float(order.get('quantity', 0)),
                        'distance_pct': price_distance_pct
                    })
        
        if not sell_orders_to_adjust:
            self.logger.info("ℹ️ Nenhuma ordem de venda precisa ser ajustada")
            return
            
        self.logger.info(f"🔧 Ajustando {len(sell_orders_to_adjust)} ordens de venda")
        
        # Ajustar ordens uma por vez
        for order_data in sell_orders_to_adjust:
            self._relocate_sell_order(order_data, current_price)
            time.sleep(0.3)  # Delay entre ajustes
    
    def _adjust_for_uptrend(self, current_price: float) -> None:
        """Ajusta o grid para tendência altista - aproxima ordens de compra"""
        
        self.logger.info(f"📈 Ajustando para tendência altista")
        
        # Buscar ordens de compra existentes
        all_open_orders = self.auth.get_open_orders()
        if not all_open_orders:
            return
            
        buy_orders_to_adjust = []
        
        # Filtrar ordens de compra do símbolo atual
        for order in all_open_orders:
            if (order.get('symbol') == self.symbol and 
                order.get('side') in ['buy', 'bid'] and
                not self._is_tp_sl_order(order)):
                
                order_price = float(order.get('price', 0))
                price_distance_pct = ((current_price - order_price) / current_price) * 100
                
                # Identificar ordens muito distantes do preço atual
                if price_distance_pct > self.max_adjustment_distance:
                    buy_orders_to_adjust.append({
                        'order_id': order.get('order_id'),
                        'old_price': order_price,
                        'quantity': float(order.get('quantity', 0)),
                        'distance_pct': price_distance_pct
                    })
        
        if not buy_orders_to_adjust:
            self.logger.info("ℹ️ Nenhuma ordem de compra precisa ser ajustada")
            return
            
        self.logger.info(f"🔧 Ajustando {len(buy_orders_to_adjust)} ordens de compra")
        
        # Ajustar ordens uma por vez
        for order_data in buy_orders_to_adjust:
            self._relocate_buy_order(order_data, current_price)
            time.sleep(0.3)  # Delay entre ajustes
    
    def _relocate_sell_order(self, order_data: dict, current_price: float) -> None:
        """Reposiciona uma ordem de venda mais próxima do preço atual"""
        
        try:
            old_price = order_data['old_price']
            order_id = order_data['order_id']
            quantity = order_data['quantity']
            
            # Calcular novo preço (mais próximo, mas ainda com margem de lucro)
            spacing_pct = self.calculator.spacing_percent
            new_price = current_price * (1 + (spacing_pct * 2) / 100)  # 2x spacing para margem
            new_price = self.calculator.round_price(new_price)
            
            # Verificar se realmente precisa mover
            if abs(new_price - old_price) / old_price < 0.005:  # < 0.5%
                return
                
            self.logger.info(f"🔄 Movendo SELL: ${old_price} → ${new_price} ({quantity} {self.symbol})")
            
            # Cancelar ordem antiga
            cancel_result = self.auth.cancel_order(str(order_id), self.symbol)
            if cancel_result and cancel_result.get('success'):
                # Remover do tracking
                old_price_key = self._price_key(old_price)
                if old_price_key in self.placed_orders:
                    del self.placed_orders[old_price_key]
                
                self.position_mgr.remove_order(str(order_id))
                
                # Aguardar processamento
                time.sleep(0.5)
                
                # Criar nova ordem
                if self._place_single_order(new_price, 'sell', quantity):
                    self.logger.info(f"✅ Ordem de venda reposicionada com sucesso")
                else:
                    self.logger.warning(f"⚠️ Falha ao criar nova ordem de venda")
            else:
                self.logger.warning(f"⚠️ Falha ao cancelar ordem antiga: {cancel_result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao reposicionar ordem de venda: {e}")
    
    def _relocate_buy_order(self, order_data: dict, current_price: float) -> None:
        """Reposiciona uma ordem de compra mais próxima do preço atual"""
        
        try:
            old_price = order_data['old_price']
            order_id = order_data['order_id']
            quantity = order_data['quantity']
            
            # Calcular novo preço (mais próximo, mas ainda abaixo do mercado)
            spacing_pct = self.calculator.spacing_percent
            new_price = current_price * (1 - (spacing_pct * 2) / 100)  # 2x spacing para margem
            new_price = self.calculator.round_price(new_price)
            
            # Verificar se realmente precisa mover
            if abs(new_price - old_price) / old_price < 0.005:  # < 0.5%
                return
                
            self.logger.info(f"🔄 Movendo BUY: ${old_price} → ${new_price} ({quantity} {self.symbol})")
            
            # Cancelar ordem antiga
            cancel_result = self.auth.cancel_order(str(order_id), self.symbol)
            if cancel_result and cancel_result.get('success'):
                # Remover do tracking
                old_price_key = self._price_key(old_price)
                if old_price_key in self.placed_orders:
                    del self.placed_orders[old_price_key]
                
                self.position_mgr.remove_order(str(order_id))
                
                # Aguardar processamento
                time.sleep(0.5)
                
                # Criar nova ordem
                if self._place_single_order(new_price, 'buy', quantity):
                    self.logger.info(f"✅ Ordem de compra reposicionada com sucesso")
                else:
                    self.logger.warning(f"⚠️ Falha ao criar nova ordem de compra")
            else:
                self.logger.warning(f"⚠️ Falha ao cancelar ordem antiga: {cancel_result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao reposicionar ordem de compra: {e}")
    
    def _is_tp_sl_order(self, order: dict) -> bool:
        """Verifica se uma ordem é Take Profit ou Stop Loss"""
        
        order_type = order.get('type', '')
        order_subtype = order.get('subType', '')
        order_label = str(order.get('label', '')).lower()
        
        return (order_type in ['TAKE_PROFIT', 'STOP_LOSS'] or
                order_subtype in ['take_profit', 'stop_loss'] or
                'tp' in order_label or 'sl' in order_label)
    
    def get_grid_status(self) -> dict:
        """Retorna status do grid dinâmico com informações adicionais"""
        
        base_status = super().get_grid_status()
        
        # Adicionar informações específicas do grid dinâmico
        if self.price_trend_history:
            current_trend = self._calculate_price_trend()
            trend_description = "BAIXISTA" if current_trend < -0.3 else "ALTISTA" if current_trend > 0.3 else "LATERAL"
            
            base_status.update({
                'dynamic_enabled': True,
                'last_adjustment_price': self.last_adjustment_price,
                'current_trend': current_trend,
                'trend_description': trend_description,
                'adjustment_threshold': self.dynamic_adjustment_threshold
            })
        else:
            base_status['dynamic_enabled'] = False
            
        return base_status