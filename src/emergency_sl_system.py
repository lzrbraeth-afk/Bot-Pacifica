"""
Emergency Stop Loss System - Camada 3 de Proteção
Failsafe independente que age quando todas as outras proteções falharam
"""

import os
import time
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
from src.risk_health_reporter import RiskHealthReporter  # ⬅️ ADD

class EmergencyStopLoss:
    """
    Sistema de proteção de última instância
    
    Camadas de proteção:
    1. TP/SL da API (criado com ordem)
    2. Shadow SL (monitoramento interno normal)
    3. Emergency SL (este sistema) - age quando 1 e 2 falharam
    """
    
    def __init__(self, auth_client, position_manager, logger):
        self.auth = auth_client
        self.position_mgr = position_manager
        self.logger = logger
        
        # Configurações de emergência (mais agressivas que Shadow SL)
        self.emergency_sl_percent = float(os.getenv('EMERGENCY_SL_PERCENT', '3.0'))
        self.emergency_tp_percent = float(os.getenv('EMERGENCY_TP_PERCENT', '5.0'))
        self.max_loss_time_minutes = int(os.getenv('EMERGENCY_MAX_LOSS_TIME_MINUTES', '15'))
        self.check_interval_seconds = int(os.getenv('EMERGENCY_CHECK_INTERVAL_SECONDS', '10'))
        
        # Estado interno
        self.last_check_time = 0
        self.positions_in_loss = {}  # {position_id: {'timestamp': time, 'max_loss': float}}
        self.emergency_closures = []  # Histórico de fechamentos de emergência
        
        self.logger.info("=" * 80)
        self.logger.info("EMERGENCY STOP LOSS SYSTEM - Camada 3 Ativada")
        self.logger.info(f"  Emergency SL: {self.emergency_sl_percent}% (vs Shadow SL normal)")
        self.logger.info(f"  Emergency TP: {self.emergency_tp_percent}% (proteção extrema)")
        self.logger.info(f"  Max tempo em loss: {self.max_loss_time_minutes} minutos")
        self.logger.info(f"  Intervalo de verificação: {self.check_interval_seconds}s")
        self.logger.info("=" * 80)
        self.logger.info("🚨 EMERGENCY STOP LOSS SYSTEM - Camada 3 Ativada")
        # ▶️ Reporter compartilhado (nome 'risk_emergency' só para tag)
        self.health = RiskHealthReporter(strategy_name="risk_emergency")  # ⬅️ ADD
        self.logger.info(f"  Emergency SL: {self.emergency_sl_percent}%")
    
    def check_all_positions(self, active_positions: Dict) -> None:
        """
        Verifica TODAS as posições ativas em busca de condições de emergência
        Esta função deve ser chamada no loop principal
        """
        
        current_time = time.time()
        
        # Throttle - não verificar muito frequentemente
        if (current_time - self.last_check_time) < self.check_interval_seconds:
            return
        
        self.last_check_time = current_time
        
        if not active_positions:
            return
        
        self.logger.info(f"🚨 Emergency SL: Verificando {len(active_positions)} posições (Camada 3 ativa)")

        for position_id, position in active_positions.items():
            self._check_single_position(position_id, position, current_time)
    
    def _check_single_position(self, position_id: str, position: Dict, current_time: float):
        """Verifica uma posição individual"""
        
        try:
            symbol = position.get('symbol')
            side = position.get('side')
            entry_price = position.get('price', 0)
            quantity = position.get('quantity', 0)
            
            if not symbol or not side or entry_price <= 0:
                return
            
            # Obter preço atual
            current_price = self._get_current_price(symbol)
            if not current_price or current_price <= 0:
                return
            
             # 🔍 LOG DETALHADO ANTES DE CALCULAR PNL
            self.logger.info(f"🔍 Verificando {symbol}:")
            self.logger.info(f"   Entry price salvo: ${entry_price}")
            self.logger.info(f"   Current price: ${current_price}")
            self.logger.info(f"   Side salvo: {side}")
            self.logger.info(f"   Quantity: {quantity}")
            
            # Calcular PNL
            pnl_percent = self._calculate_pnl_percent(side, entry_price, current_price)
            
            self.logger.info(f"   PNL calculado: {pnl_percent:.2f}%")
            # Telemetria de cada checagem de emergência
            self.health.log_check("emergency_check", {
                "symbol": symbol, "side": side, "pnl_percent": pnl_percent,
                "emergency_sl_percent": self.emergency_sl_percent,
                "time_check_sec": self.check_interval_seconds
            })
            self.health.update_trade(
                current_price=current_price,
                pnl_percent=pnl_percent,
                extra={"emergency": {"sl%": self.emergency_sl_percent, "tp%": self.emergency_tp_percent}}
            )
            
            # Verificar tempo da posição
            position_age = self._get_position_age(position)
            
            # CONDIÇÃO 1: Perda extrema (> Emergency SL)
            if pnl_percent <= -self.emergency_sl_percent:
                self._trigger_emergency_close(
                    position_id, position, current_price,
                    f"PERDA CRÍTICA: {pnl_percent:.2f}% <= -{self.emergency_sl_percent}%",
                    pnl_percent
                )
                self.health.end_trade(reason="emergency_sl", result="emergency",
                                      final_snapshot={"pnl_percent": pnl_percent, "symbol": symbol})
                return
            
            # CONDIÇÃO 2: Lucro extremo inesperado (proteção contra reversão)
            if pnl_percent >= self.emergency_tp_percent:
                self._trigger_emergency_close(
                    position_id, position, current_price,
                    f"LUCRO EXTREMO: {pnl_percent:.2f}% >= {self.emergency_tp_percent}% (proteger ganhos)",
                    pnl_percent
                )
                self.health.end_trade(reason="emergency_tp", result="emergency",
                                      final_snapshot={"pnl_percent": pnl_percent, "symbol": symbol})
                return
            
            # CONDIÇÃO 3: Tempo excessivo em perda
            if pnl_percent < 0:
                self._track_loss_time(position_id, pnl_percent, current_time)
                
                if position_id in self.positions_in_loss:
                    loss_data = self.positions_in_loss[position_id]
                    time_in_loss_minutes = (current_time - loss_data['timestamp']) / 60
                    
                    if time_in_loss_minutes >= self.max_loss_time_minutes:
                        self._trigger_emergency_close(
                            position_id, position, current_price,
                            f"LOSS PROLONGADO: {time_in_loss_minutes:.1f}min em perda de {pnl_percent:.2f}%",
                            pnl_percent
                        )
                        self.health.end_trade(reason="emergency_time_sl", result="emergency",
                                              final_snapshot={"pnl_percent": pnl_percent, "symbol": symbol, "time_in_loss_minutes": time_in_loss_minutes})
                        return
            else:
                # Posição em lucro - limpar tracking de loss
                if position_id in self.positions_in_loss:
                    del self.positions_in_loss[position_id]
            
        except Exception as e:
            self.logger.error(f"Erro ao verificar posição {position_id}: {e}")
    
    def _track_loss_time(self, position_id: str, pnl_percent: float, current_time: float):
        """Rastreia há quanto tempo posição está em loss"""
        
        if position_id not in self.positions_in_loss:
            # Primeira vez que detecta loss
            self.positions_in_loss[position_id] = {
                'timestamp': current_time,
                'max_loss': pnl_percent,
                'initial_loss': pnl_percent
            }
            self.logger.debug(f"Position {position_id} entrou em loss: {pnl_percent:.2f}%")
        else:
            # Atualizar max_loss se piorou
            loss_data = self.positions_in_loss[position_id]
            if pnl_percent < loss_data['max_loss']:
                loss_data['max_loss'] = pnl_percent
    
    def _trigger_emergency_close(self, position_id: str, position: Dict, 
                                 current_price: float, reason: str, pnl_percent: float):
        """
        EXECUTA FECHAMENTO DE EMERGÊNCIA
        Usa ordem IOC (Immediate or Cancel) para fechamento rápido
        """
        
        symbol = position['symbol']
        side = position['side']
        quantity = position['quantity']
        
        self.logger.error("=" * 80)
        self.logger.error("EMERGENCY STOP LOSS TRIGGERED")
        self.logger.error(f"Symbol: {symbol}")
        self.logger.error(f"Reason: {reason}")
        self.logger.error(f"PNL: {pnl_percent:+.2f}%")
        self.logger.error("=" * 80)
        
        # Determinar lado da ordem de fechamento
        close_side = 'ask' if side == 'bid' else 'bid'
        
        try:
            # Calcular preço de execução favorável para garantir fechamento rápido
            if close_side == 'ask':
                # Vendendo - usar preço abaixo do mercado
                execution_price = current_price * 0.995  # -0.5%
            else:
                # Comprando - usar preço acima do mercado
                execution_price = current_price * 1.005  # +0.5%
            
            # Arredondar para tick_size
            tick_size = self._get_tick_size(symbol)
            execution_price = self.auth._round_to_tick_size(execution_price, tick_size)
            
            # Arredondar quantidade para lot_size
            lot_size = self._get_lot_size(symbol)
            
            # 🔧 USAR DECIMAL PARA EVITAR ERRO DE PRECISÃO
            from decimal import Decimal, ROUND_DOWN
            
            quantity_dec = Decimal(str(quantity))
            lot_size_dec = Decimal(str(lot_size))
            
            # Arredondar para baixo para múltiplo do lot_size
            multiple = int(quantity_dec / lot_size_dec)
            quantity_rounded = float(multiple * lot_size_dec)
            
            # Garantir que não seja zero
            if quantity_rounded < lot_size:
                quantity_rounded = lot_size
            
            # Formatar com precisão baseada no lot_size
            if lot_size >= 1:
                quantity_rounded = round(quantity_rounded, 0)
            elif lot_size >= 0.01:
                quantity_rounded = round(quantity_rounded, 2)
            elif lot_size >= 0.001:
                quantity_rounded = round(quantity_rounded, 3)
            else:
                quantity_rounded = round(quantity_rounded, 4)
            
            self.logger.error(f"Executando fechamento: {close_side} {quantity_rounded} @ ${execution_price}")
            
            # Criar ordem IOC (Immediate or Cancel) para execução rápida
            result = self.auth.create_order(
                symbol=symbol,
                side=close_side,
                amount=str(quantity_rounded),
                price=str(execution_price),
                order_type="IOC",  # Executa imediatamente ou cancela
                reduce_only=True
            )
            
            if result and result.get('success'):
                order_id = result.get('data', {}).get('order_id', 'N/A')
                
                # Registrar fechamento
                self._record_emergency_closure(position_id, symbol, reason, pnl_percent, order_id)
                
                self.logger.error(f"EMERGENCY CLOSE EXECUTED: Order ID {order_id}")
                self.logger.error("=" * 80)
                
                return True
            else:
                error_msg = result.get('error', 'Unknown') if result else 'No response'
                self.logger.error(f"IOC order failed: {error_msg}")
                
                # FALLBACK: Tentar GTC se IOC falhar
                self.logger.error("Trying GTC as fallback...")
                
                result_gtc = self.auth.create_order(
                    symbol=symbol,
                    side=close_side,
                    amount=str(quantity_rounded),
                    price=str(execution_price),
                    order_type="GTC",
                    reduce_only=True
                )
                
                if result_gtc and result_gtc.get('success'):
                    order_id = result_gtc.get('data', {}).get('order_id', 'N/A')
                    self._record_emergency_closure(position_id, symbol, reason, pnl_percent, order_id)
                    self.logger.error(f"EMERGENCY CLOSE (GTC) EXECUTED: Order ID {order_id}")
                    self.logger.error("=" * 80)
                    return True
                else:
                    self.logger.error("GTC fallback also failed!")
                    self.logger.error("=" * 80)
                    return False
                    
        except Exception as e:
            self.logger.error(f"EXCEPTION IN EMERGENCY CLOSE: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.logger.error("=" * 80)
            return False
    
    def _record_emergency_closure(self, position_id: str, symbol: str, 
                                  reason: str, pnl_percent: float, order_id: str):
        """Registra fechamento de emergência para análise"""
        
        closure_record = {
            'timestamp': datetime.now(),
            'position_id': position_id,
            'symbol': symbol,
            'reason': reason,
            'pnl_percent': pnl_percent,
            'order_id': order_id
        }
        
        self.emergency_closures.append(closure_record)
        
        # Limpar tracking
        if position_id in self.positions_in_loss:
            del self.positions_in_loss[position_id]
    
    def _calculate_pnl_percent(self, side: str, entry_price: float, current_price: float) -> float:
        """Calcula PNL percentual"""
        
        if side in ['bid', 'buy', 'LONG']:
            # Long position
            return ((current_price - entry_price) / entry_price) * 100
        else:
            # Short position
            return ((entry_price - current_price) / entry_price) * 100
    
    def _get_position_age(self, position: Dict) -> float:
        """Retorna idade da posição em minutos"""
        
        timestamp = position.get('timestamp')
        if isinstance(timestamp, datetime):
            age_seconds = (datetime.now() - timestamp).total_seconds()
        elif isinstance(timestamp, (int, float)):
            age_seconds = time.time() - timestamp
        else:
            return 0
        
        return age_seconds / 60
    
    def _get_current_price(self, symbol: str) -> float:
        """Obtém preço atual do símbolo"""
        
        try:
            prices_data = self.auth.get_prices()
            if prices_data and prices_data.get('success'):
                for item in prices_data.get('data', []):
                    if item.get('symbol') == symbol:
                        return float(item.get('mark') or item.get('mid') or 0)
            return 0.0
        except Exception as e:
            self.logger.error(f"Erro ao obter preço {symbol}: {e}")
            return 0.0
    
    def _get_tick_size(self, symbol: str) -> float:
        """Obtém tick_size do símbolo"""
        try:
            info = self.auth.get_symbol_info(symbol)
            if info and 'tick_size' in info:
                return float(info['tick_size'])
        except:
            pass
        
        # Fallback
        tick_sizes = {
            'BTC': 0.00001, 'ETH': 0.0001, 'SOL': 0.01,
            'BNB': 0.001, 'AVAX': 0.001, 'LTC': 0.001
        }
        return tick_sizes.get(symbol, 0.01)
    
    def _get_lot_size(self, symbol: str) -> float:
        """Obtém lot_size do símbolo"""
        try:
            info = self.auth.get_symbol_info(symbol)
            if info and 'lot_size' in info:
                return float(info['lot_size'])
        except:
            pass
        
        # Fallback
        lot_sizes = {
            'BTC': 0.00001, 'ETH': 0.0001, 'SOL': 0.01,
            'BNB': 0.001, 'AVAX': 0.001, 'LTC': 0.001
        }
        return lot_sizes.get(symbol, 0.001)
    
    def get_statistics(self) -> Dict:
        """Retorna estatísticas do sistema de emergência"""
        
        return {
            'total_emergency_closures': len(self.emergency_closures),
            'positions_currently_in_loss': len(self.positions_in_loss),
            'last_check': datetime.fromtimestamp(self.last_check_time) if self.last_check_time > 0 else None,
            'recent_closures': self.emergency_closures[-5:] if self.emergency_closures else []
        }
    
    def log_status(self):
        """Log do status atual do sistema"""
        
        stats = self.get_statistics()
        
        self.logger.info("Emergency SL Status:")
        self.logger.info(f"  Total emergency closures: {stats['total_emergency_closures']}")
        self.logger.info(f"  Positions in loss: {stats['positions_currently_in_loss']}")
        
        if stats['positions_currently_in_loss'] > 0:
            for pos_id, data in self.positions_in_loss.items():
                time_in_loss = (time.time() - data['timestamp']) / 60
                self.logger.info(f"    {pos_id}: {time_in_loss:.1f}min em loss de {data['max_loss']:.2f}%")