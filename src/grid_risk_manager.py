"""
Grid Risk Manager - Sistema de Gerenciamento de Risco para Grid Trading
Implementa proteção em 2 níveis: PNL por Ciclo e PNL Acumulado
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from pathlib import Path
from src.positions_tracker import PositionsTracker
from src.risk_health_reporter import RiskHealthReporter  # ⬅️ ADD

class GridRiskManager:
    """
    Sistema de Gerenciamento de Risco para Grid Trading
    
    Níveis de Proteção:
    - Nível 1: PNL por Ciclo (posição aberta individual)
    - Nível 2: PNL Acumulado (total da sessão)
    """
    
    def __init__(self, auth_client, position_manager, telegram_notifier, logger: Optional[logging.Logger] = None):
        self.auth = auth_client
        self.position_mgr = position_manager
        self.telegram = telegram_notifier
        self.logger = logger or logging.getLogger('PacificaBot.GridRisk')
        
        # ==================== CONFIGURAÇÕES NÍVEL 1: CICLO ====================
        self.enable_cycle_protection = os.getenv('ENABLE_CYCLE_PROTECTION', 'true').lower() == 'true'
        self.cycle_stop_loss_percent = float(os.getenv('GRID_CYCLE_STOP_LOSS_PERCENT', '5.0'))
        self.cycle_take_profit_percent = float(os.getenv('GRID_CYCLE_TAKE_PROFIT_PERCENT', '8.0'))
        self.session_profit_target_percent = float(os.getenv('GRID_SESSION_PROFIT_TARGET_PERCENT', '40.0'))

        # ==================== CONFIGURAÇÕES NÍVEL 2: SESSÃO ====================
        self.enable_session_protection = os.getenv('ENABLE_SESSION_PROTECTION', 'true').lower() == 'true'
        self.session_max_loss_usd = float(os.getenv('GRID_SESSION_MAX_LOSS_USD', '80.0'))
        self.session_max_loss_percent = float(os.getenv('GRID_SESSION_MAX_LOSS_PERCENT', '20.0'))
        self.session_profit_target_usd = float(os.getenv('GRID_SESSION_PROFIT_TARGET_USD', '160.0'))
        
        # Configurações adicionais de sessão
        self.session_stop_loss = float(os.getenv('SESSION_STOP_LOSS_USD', '100'))
        self.session_max_loss = float(os.getenv('SESSION_MAX_LOSS_USD', '200'))
        self.session_profit_target = float(os.getenv('SESSION_PROFIT_TARGET_USD', '500'))
        
        # Contadores de sessão
        self.session_realized_pnl = 0.0
        self.session_start_balance = 0.0
        
        # ==================== CONFIGURAÇÕES DE AÇÃO ====================
        self.action_on_limit = os.getenv('GRID_ACTION_ON_LIMIT', 'pause').lower()  # 'pause' ou 'shutdown'
        self.pause_duration_minutes = int(os.getenv('GRID_PAUSE_DURATION_MINUTES', '120'))
        
        # ==================== CONFIGURAÇÕES AVANÇADAS ====================
        self.check_interval_seconds = int(os.getenv('GRID_CHECK_INTERVAL_SECONDS', '30'))
        self.save_history = os.getenv('GRID_SAVE_PNL_HISTORY', 'true').lower() == 'true'
        self.log_interval_minutes = int(os.getenv('GRID_LOG_PNL_EVERY_MINUTES', '15'))
        
        # ==================== ESTADO DO GERENCIADOR ====================
        self.initial_balance = 0.0
        self.current_balance = 0.0
        
        # PNL Acumulado
        self.accumulated_pnl = 0.0
        self.accumulated_pnl_history = []  # Lista de dicts com histórico de ciclos
        
        # Ciclos
        self.cycles_closed = 0
        self.cycles_profit = 0
        self.cycles_loss = 0
        self.current_cycle_id = 1
        self.current_cycle_start = datetime.now()
        
        # Controle de Pausa
        self.is_paused = False
        self.pause_until = None
        self.pause_reason = ""
        
        # Tracking
        self.last_check_time = 0
        self.last_log_time = time.time()
        self.session_start = datetime.now()
        
        # Arquivo de histórico
        self.history_file = Path('data/grid_pnl_history.json')
        self.history_file.parent.mkdir(exist_ok=True)

        # ▶️ Telemetria/saúde do gestor de risco
        self.health = RiskHealthReporter(strategy_name="grid")  # ⬅️ ADD
        self._ui_tracker = PositionsTracker()
        
        # Carregar histórico se existir
        self._load_history()
        
        # Log de inicialização
        self._log_initialization()
        
        # 🆕 MODO DEBUG: Enviar status inicial via Telegram
        self._send_debug_status("INICIALIZAÇÃO")
    
    def _send_debug_status(self, event_type: str):
        """
        🆕 FUNÇÃO DE DEBUG: Envia status detalhado via Telegram
        Para monitoramento temporário durante desenvolvimento
        """
        # Verificar se o modo debug está ativado
        debug_enabled = os.getenv('RISK_MANAGER_DEBUG_MODE', 'false').lower() == 'true'
        if not debug_enabled or not self.telegram:
            return
            
        try:
            # Coletar informações do status atual
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Status dos níveis de proteção
            nivel1_status = "✅ ATIVO" if self.enable_cycle_protection else "❌ DESABILITADO"
            nivel2_status = "✅ ATIVO" if self.enable_session_protection else "❌ DESABILITADO"
            
            # Informações de PNL
            pnl_acumulado = self.accumulated_pnl
            ciclos_fechados = len(self.accumulated_pnl_history)
            
            # Montar mensagem
            debug_message = f"""
🛡️ **RISK MANAGER DEBUG** ({event_type})
⏰ **Horário:** {current_time}

📊 **PROTEÇÕES:**
• Nível 1 (Ciclo): {nivel1_status}
• Nível 2 (Sessão): {nivel2_status}

💰 **PNL ACUMULADO:** ${pnl_acumulado:+.2f}
🔄 **Ciclos Fechados:** {ciclos_fechados}

🎯 **CONFIGURAÇÕES:**
• Stop Loss Ciclo: {self.cycle_stop_loss_percent}%
• Take Profit Ciclo: {self.cycle_take_profit_percent}%
• Stop Loss Sessão: {self.session_stop_loss}%
• Take Profit Sessão: {self.session_take_profit}%

---
*Debug Mode - Remover após teste*
"""
            
            # Enviar via Telegram
            self.telegram.send_notification(debug_message)
            self.logger.debug(f"📱 Debug status enviado: {event_type}")
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao enviar debug status: {e}")
    
    def send_periodic_debug_status(self):
        """
        🆕 FUNÇÃO PARA CHAMAR NO LOOP PRINCIPAL
        Envia status periódico para monitoramento
        """
        self._send_debug_status("STATUS PERIÓDICO")

    def _extract_price_from_item(self, item: dict) -> float:
        for k in ('mark', 'mid', 'last', 'bid', 'price'):
            try:
                v = float(item.get(k, 0) or 0); 
                if v > 0: return v
            except Exception: 
                pass
        return 0.0

    def _get_realtime_positions(self) -> list:
        try:
            pos_resp = self.auth.get_positions() or []
            # Tratar caso onde API retorna lista diretamente ou objeto com 'data'
            if isinstance(pos_resp, list):
                pos_list = pos_resp
            elif isinstance(pos_resp, dict):
                pos_list = pos_resp.get('data', [])
            else:
                pos_list = []
            
            prices = self.auth.get_prices() or {}
            items = prices.get('data', prices if isinstance(prices, list) else [])
            pmap = {it.get('symbol'): self._extract_price_from_item(it) for it in items if isinstance(it, dict) and it.get('symbol')}
            result = []
            for p in pos_list:
                if not isinstance(p, dict):
                    continue
                sym = p.get('symbol'); 
                if not sym: 
                    continue
                entry = float(p.get('entry_price') or p.get('entryPrice') or 0)
                size  = float(p.get('size') or p.get('amount') or 0)
                side  = (p.get('side') or 'long').lower()
                current = pmap.get(sym, entry)
                pnl_usd = (current - entry) * size if side in ('long','buy','bid') else (entry - current) * size
                pnl_pct = (pnl_usd / (entry*size) * 100) if entry>0 and size>0 else 0.0
                result.append({
                    "symbol": sym, "side": side, "size": size,
                    "entry_price": entry, "current_price": current,
                    "pnl_usd": round(pnl_usd,2), "pnl_percent": round(pnl_pct,2),
                })
            return result
        except Exception as e:
            self.logger.error(f"❌ _get_realtime_positions: {e}")
            return []

    def _auto_detect_active_trade(self):
        """
        Detecta posições abertas na corretora e sincroniza com RiskHealthReporter.
        Cria, atualiza e encerra trade ativo automaticamente.
        """
        try:
            positions = self._get_realtime_positions()
            if positions:
                # Pega primeira posição como referência (pode adaptar para multi-asset)
                pos = positions[0]
                trade_id = f"{pos['symbol']}-{int(datetime.now().timestamp())}"

                # Inicia trade se não houver ativo
                if not self.health.active:
                    self.health.start_trade(
                        trade_id,
                        symbol=pos['symbol'],
                        side=pos['side'],
                        size=pos['size'],
                        entry_price=pos['entry_price'],
                        entry_time=datetime.now().isoformat(),
                        tp_percent=self.cycle_take_profit_percent,
                        sl_percent=self.cycle_stop_loss_percent,
                        extra={"auto_detected": True}
                    )
                    self.logger.info(f"🟢 Trade detectado e iniciado automaticamente: {pos['symbol']} {pos['side']}")

                # Atualiza PNL em tempo real
                if self.health.active:
                    entry_time = datetime.fromisoformat(self.health.active.entry_time)
                    time_in_trade = int((datetime.now() - entry_time).total_seconds())
                    
                    # Campos de configuração de risco (fixos por sessão ou carregados do .env)
                    risk_cfg = {
                        "cycle_stop_loss_percent": getattr(self, "cycle_stop_loss_percent", None),
                        "cycle_take_profit_percent": getattr(self, "cycle_take_profit_percent", None),
                        "emergency_sl_percent": float(os.getenv('EMERGENCY_SL_PERCENT', '3.0')),
                        "emergency_tp_percent": float(os.getenv('EMERGENCY_TP_PERCENT', '5.0')),
                        "session_max_loss_usd": getattr(self, "session_max_loss_usd", None),
                        "session_profit_target_usd": getattr(self, "session_profit_target_usd", None)
                    }
                    
                    # Adiciona ao JSON de trade ativo
                    self.health.update_trade(
                        current_price=pos['current_price'],
                        pnl_usd=pos['pnl_usd'],
                        pnl_percent=pos['pnl_percent'],
                        time_in_trade_sec=time_in_trade,
                        extra={
                            "positions": positions,
                            "risk_config": risk_cfg,
                            "cycle_thresholds": {
                                "sl%": self.cycle_stop_loss_percent,
                                "tp%": self.cycle_take_profit_percent
                            }
                        }
                    )

            else:
                # Se não houver posições e havia trade ativo, encerra
                if self.health.active:
                    self.health.end_trade(reason="position_closed", result="manual_or_tp")
                    self.logger.info("🔴 Nenhuma posição aberta — trade encerrado automaticamente.")

        except Exception as e:
            self.logger.error(f"❌ Erro no _auto_detect_active_trade: {e}")
    
    def _log_initialization(self):
        """Log detalhado da inicialização"""
        self.logger.info("=" * 80)
        self.logger.info("🛡️ GRID RISK MANAGER INICIALIZADO")
        self.logger.info("=" * 80)
        
        self.logger.info("📊 NÍVEL 1 - PROTEÇÃO POR CICLO:")
        if self.enable_cycle_protection:
            self.logger.info(f"  ✅ ATIVO")
            self.logger.info(f"  🛑 Stop Loss: {self.cycle_stop_loss_percent}%")
            self.logger.info(f"  🎯 Take Profit: {self.cycle_take_profit_percent}%")
        else:
            self.logger.info(f"  ❌ DESABILITADO")
        
        self.logger.info("")
        self.logger.info("📊 NÍVEL 2 - PROTEÇÃO ACUMULADA:")
        if self.enable_session_protection:
            self.logger.info(f"  ✅ ATIVO")
            self.logger.info(f"  🛑 Max Loss: ${self.session_max_loss_usd:.2f} ({self.session_max_loss_percent}%)")
            self.logger.info(f"  🎯 Profit Target: ${self.session_profit_target_usd:.2f} ({self.session_profit_target_percent}%)")
        else:
            self.logger.info(f"  ❌ DESABILITADO")
        
        self.logger.info("")
        self.logger.info(f"⚙️ AÇÃO AO ATINGIR LIMITE: {self.action_on_limit.upper()}")
        if self.action_on_limit == 'pause':
            self.logger.info(f"  ⏸️ Duração da pausa: {self.pause_duration_minutes} minutos")
        
        self.logger.info("=" * 80)
    
    def set_initial_balance(self, balance: float):
        """Define saldo inicial da sessão"""
        if self.initial_balance == 0:
            self.initial_balance = balance
            self.current_balance = balance
            self.logger.info(f"💰 Saldo inicial definido: ${balance:.2f}")
    
    def check_position_risk(self, symbol: str, current_price: float) -> Tuple[bool, Optional[str]]:
        """
        Verifica risco da posição atual (NÍVEL 1)
        
        Returns:
            (should_close, reason)
        """
        if not self.enable_cycle_protection:
            return False, None

        # 🔹 Chamada da nova função automática de detecção
        self._auto_detect_active_trade()

        # Telemetria: atualizar trade ativo e status de sessão
        rt_positions = self._get_realtime_positions()
        total_pnl = sum(p["pnl_usd"] for p in rt_positions) if rt_positions else 0.0
        avg_pct   = (sum(p["pnl_percent"] for p in rt_positions)/len(rt_positions)) if rt_positions else 0.0
        age_sec = int((datetime.now() - self.current_cycle_start).total_seconds()) if self.current_cycle_start else 0

        self.health.update_trade(
            current_price=rt_positions[0]["current_price"] if rt_positions else None,
            pnl_usd=total_pnl,
            pnl_percent=avg_pct,
            time_in_trade_sec=age_sec,
            extra={
                "positions": rt_positions,
                "cycle_thresholds": {
                    "sl%": self.cycle_stop_loss_percent,
                    "tp%": self.cycle_take_profit_percent
                },
                "session": {
                    "accumulated_pnl": self.accumulated_pnl,
                    "cycles_closed": self.cycles_closed
                }
            }
        )
        self.health.log_check("risk_check", {
            "age_sec": age_sec,
            "positions_count": len(rt_positions),
            "cycle_sl_percent": self.cycle_stop_loss_percent,
            "cycle_tp_percent": self.cycle_take_profit_percent,
            "session_pnl": self.accumulated_pnl
        })
    
        # Calcular PNL da posição aberta
        position_pnl = self._calculate_position_pnl(symbol, current_price)
        
        if position_pnl is None:
            return False, None
        
        pnl_usd = position_pnl['pnl_usd']
        pnl_percent = position_pnl['pnl_percent']

        # Verificar Stop Loss
        if pnl_percent <= -self.cycle_stop_loss_percent:
            reason = f"CYCLE_STOP_LOSS: {pnl_percent:.2f}% <= -{self.cycle_stop_loss_percent}%"
            self.logger.warning(f"🛑 {reason}")
            
            # 🆕 DEBUG: Notificar detecção de stop loss
            self._send_debug_status(f"STOP LOSS DETECTADO - {pnl_percent:.2f}%")
            
            # Notificar Telegram
            self.telegram.send_stop_loss_alert('cycle', {
                'pnl_usd': pnl_usd,
                'pnl_percent': pnl_percent,
                'accumulated_pnl': self.accumulated_pnl,
                'limit_percent': self.session_max_loss_percent, 
                'action': 'Fechando posição e reiniciando grid'
            })
            
            self.health.end_trade(reason="cycle_sl", result="sl")
            return True, reason
        
        # Verificar Take Profit
        if pnl_percent >= self.cycle_take_profit_percent:
            reason = f"CYCLE_TAKE_PROFIT: {pnl_percent:.2f}% >= {self.cycle_take_profit_percent}%"
            self.logger.info(f"🎯 {reason}")
            
            # 🆕 DEBUG: Notificar detecção de take profit
            self._send_debug_status(f"TAKE PROFIT DETECTADO - {pnl_percent:.2f}%")
            
            # Notificar Telegram
            self.telegram.send_take_profit_alert('cycle', {
                'pnl_usd': pnl_usd,
                'pnl_percent': pnl_percent,
                'accumulated_pnl': self.accumulated_pnl,
                'target_percent': self.cycle_take_profit_percent,  # ✅ Este funciona
                'action': 'Realizando lucro e reiniciando grid'
            })
            
            self.health.end_trade(reason="cycle_tp", result="tp")
            return True, reason
        
        return False, None
    
    def check_session_limits(self) -> Tuple[bool, Optional[str]]:
        """
        Verifica limites da sessão (NÍVEL 2)
        
        Returns:
            (should_stop, reason)
        """
        
        if not self.enable_session_protection:
            return False, None
        
        # Calcular % do capital inicial
        if self.initial_balance > 0:
            accumulated_percent = (self.accumulated_pnl / self.initial_balance) * 100
        else:
            accumulated_percent = 0
        
        # Verificar Stop Loss Acumulado (USD ou %)
        if self.accumulated_pnl <= -self.session_max_loss_usd:
            reason = f"SESSION_STOP_LOSS_USD: ${self.accumulated_pnl:.2f} <= -${self.session_max_loss_usd:.2f}"
            self._trigger_session_limit(reason, 'stop_loss')
            return True, reason
        
        if accumulated_percent <= -self.session_max_loss_percent:
            reason = f"SESSION_STOP_LOSS_PCT: {accumulated_percent:.2f}% <= -{self.session_max_loss_percent}%"
            self._trigger_session_limit(reason, 'stop_loss')
            return True, reason
        
        # Verificar Take Profit Acumulado
        if self.accumulated_pnl >= self.session_profit_target_usd:
            reason = f"SESSION_TAKE_PROFIT: ${self.accumulated_pnl:.2f} >= ${self.session_profit_target_usd:.2f}"
            self._trigger_session_limit(reason, 'take_profit')
            return True, reason
        
        # Verificar Take Profit Acumulado por PERCENTUAL
        if accumulated_percent >= self.session_profit_target_percent:
            reason = f"SESSION_TAKE_PROFIT_PCT: {accumulated_percent:.2f}% >= {self.session_profit_target_percent}%"
            self._trigger_session_limit(reason, 'take_profit')
            return True, reason
        
        return False, None
    
    def record_cycle_close(self, symbol: str, pnl_usd: float, reason: str = "normal"):
        """Registra fechamento de ciclo e atualiza acumulado"""
        
        # Calcular duração do ciclo
        cycle_duration = (datetime.now() - self.current_cycle_start).total_seconds() / 60
        
        # Atualizar contadores
        self.cycles_closed += 1
        if pnl_usd > 0:
            self.cycles_profit += 1
        elif pnl_usd < 0:
            self.cycles_loss += 1
        
        # Atualizar PNL acumulado
        self.accumulated_pnl += pnl_usd
        
        # 🆕 DEBUG: Notificar fechamento de ciclo
        self._send_debug_status(f"CICLO FECHADO - PNL: ${pnl_usd:+.2f}")
        
        # Calcular % do PNL em relação ao valor da posição
        position = self.position_mgr.positions.get(symbol, {})
        position_value = abs(position.get('quantity', 0) * position.get('avg_price', 0))
        pnl_percent = (pnl_usd / position_value * 100) if position_value > 0 else 0
        
        # Adicionar ao histórico
        cycle_record = {
            'cycle_id': self.current_cycle_id,
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'pnl_usd': pnl_usd,
            'pnl_percent': pnl_percent,
            'duration_minutes': cycle_duration,
            'reason': reason,
            'accumulated_pnl': self.accumulated_pnl
        }
        self.accumulated_pnl_history.append(cycle_record)
        
        # Log do fechamento
        emoji = "✅" if pnl_usd > 0 else "📉" if pnl_usd < 0 else "➖"
        self.logger.info(f"{emoji} Ciclo #{self.current_cycle_id} fechado: ${pnl_usd:+.2f} ({pnl_percent:+.2f}%) | Acumulado: ${self.accumulated_pnl:+.2f}")
        
        # Notificar Telegram
        self.telegram.send_cycle_close_notification({
            'cycle_id': self.current_cycle_id,
            'pnl_usd': pnl_usd,
            'pnl_percent': pnl_percent,
            'accumulated_pnl': self.accumulated_pnl,
            'duration_minutes': cycle_duration,
            'reason': reason
        })
        
        # Salvar histórico
        if self.save_history:
            self._save_history()
        
        # Preparar próximo ciclo
        self.current_cycle_id += 1
        self.current_cycle_start = datetime.now()
    
    def _trigger_session_limit(self, reason: str, limit_type: str):
        """Dispara ação ao atingir limite de sessão"""
        
        self.logger.error("=" * 80)
        self.logger.error(f"🚨 LIMITE DE SESSÃO ATINGIDO: {reason}")
        self.logger.error("=" * 80)
        
        self.health.end_trade(reason="session_limit", result="limit_hit")
        
        # Calcular estatísticas
        win_rate = (self.cycles_profit / self.cycles_closed * 100) if self.cycles_closed > 0 else 0
        
        # Notificar Telegram
        accumulated_percent = (self.accumulated_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0
        
        self.telegram.send_session_limit_alert({
            'action': self.action_on_limit,
            'pause_duration': self.pause_duration_minutes,
            'accumulated_pnl': self.accumulated_pnl,
            'limit_usd': self.session_max_loss_usd if limit_type == 'stop_loss' else self.session_profit_target_usd,
            'limit_percent': self.session_max_loss_percent if limit_type == 'stop_loss' else self.session_profit_target_percent,
            'cycles_closed': self.cycles_closed,
            'cycles_profit': self.cycles_profit,
            'cycles_loss': self.cycles_loss
        })
        
        # Executar ação configurada
        if self.action_on_limit == 'pause':
            self._pause_bot(self.pause_duration_minutes, reason)
        else:
            self.logger.error("🛑 Ação: SHUTDOWN - Bot será encerrado!")
            # O bot principal deve verificar isso e fazer shutdown
    
    def _pause_bot(self, duration_minutes: int, reason: str):
        """Pausa o bot temporariamente"""
        
        self.is_paused = True
        self.pause_until = datetime.now() + timedelta(minutes=duration_minutes)
        self.pause_reason = reason
        
        self.logger.warning(f"⏸️ BOT PAUSADO por {duration_minutes} minutos")
        self.logger.warning(f"⏰ Retomará em: {self.pause_until.strftime('%H:%M:%S')}")
        
        # Notificar Telegram
        self.telegram.send_pause_alert(duration_minutes, reason)
    
    def check_if_paused(self) -> bool:
        """Verifica se bot deve continuar pausado"""
        
        if not self.is_paused:
            return False
        
        if datetime.now() >= self.pause_until:
            # Fim da pausa
            pause_duration = (datetime.now() - (self.pause_until - timedelta(minutes=self.pause_duration_minutes))).total_seconds() / 60
            
            self.logger.info("=" * 80)
            self.logger.info(f"▶️ RETOMANDO OPERAÇÃO após {pause_duration:.0f} minutos de pausa")
            self.logger.info("=" * 80)
            
            # Notificar Telegram
            self.telegram.send_resume_alert(int(pause_duration))
            
            self.is_paused = False
            self.pause_until = None
            self.pause_reason = ""
            return False
        
        return True
    
    def _calculate_position_pnl(self, symbol: str, current_price: float) -> Optional[Dict]:
        # self.logger.info(f"*** _calculate_position_pnl CHAMADO ***")

        # Tentar obter do cache primeiro
        if symbol not in self.position_mgr.positions:
            self.logger.info(f"⚠️ Símbolo {symbol} não encontrado nas posições - Atualizando...")
            
            # Forçar atualização
            self.position_mgr.update_account_state()
            
            # Verificar novamente
            if symbol not in self.position_mgr.positions:
                self.logger.info(f"⚠️ Símbolo {symbol} ainda não encontrado após atualização")
                return None
        
        position = self.position_mgr.positions[symbol]

        if symbol not in self.position_mgr.positions:
            self.logger.info(f"⚠️ Símbolo {symbol} não está nas posições")
            self.logger.info(f"📋 Símbolos disponíveis: {list(self.position_mgr.positions.keys())}")
            return None
        
        position = self.position_mgr.positions[symbol]
        # self.logger.info(f"*** Dados da posição: {position} ***")
        
        quantity = position.get('quantity', 0)
        avg_price = position.get('avg_price', 0)
        
        # self.logger.info(f"*** quantidade={quantity}, preço_médio={avg_price} ***")
        
        if quantity == 0 or avg_price == 0:
            self.logger.info(f"⚠️ Retornando None: quantidade={quantity}, preço_médio={avg_price}")
            return None
        
        # Calcular PNL
        pnl_usd = (current_price - avg_price) * quantity
        pnl_percent = ((current_price - avg_price) / avg_price) * 100
        
        # self.logger.info(f"*** PNL CALCULADO: ${pnl_usd:.2f} ({pnl_percent:.2f}%) ***")
        
        return {
            'pnl_usd': pnl_usd,
            'pnl_percent': pnl_percent,
            'quantity': quantity,
            'avg_entry': avg_price,
            'current_price': current_price,
            'position_value': abs(quantity * avg_price)
        }
    
    def get_status_summary(self) -> Dict:
        """Retorna resumo do status atual"""
        
        # Calcular % do capital inicial
        accumulated_percent = 0
        if self.initial_balance > 0:
            accumulated_percent = (self.accumulated_pnl / self.initial_balance) * 100
        
        # Win rate
        win_rate = 0
        if self.cycles_closed > 0:
            win_rate = (self.cycles_profit / self.cycles_closed) * 100
        
        # Uptime
        uptime = datetime.now() - self.session_start
        uptime_str = f"{int(uptime.total_seconds() // 3600)}h {int((uptime.total_seconds() % 3600) // 60)}m"
        
        return {
            'session_start': self.session_start.isoformat(),
            'uptime': uptime_str,
            'initial_balance': self.initial_balance,
            'current_balance': self.current_balance,
            'accumulated_pnl': self.accumulated_pnl,
            'accumulated_pnl_percent': accumulated_percent,
            'cycles_closed': self.cycles_closed,
            'cycles_profit': self.cycles_profit,
            'cycles_loss': self.cycles_loss,
            'win_rate': win_rate,
            'is_paused': self.is_paused,
            'pause_until': self.pause_until.isoformat() if self.pause_until else None,
            'pause_reason': self.pause_reason,
            'current_cycle_id': self.current_cycle_id
        }
    
    def log_periodic_status(self):
        """Log periódico do status com comparações detalhadas dos limites"""
        
        current_time = time.time()
        
        # Verificar se é hora de logar
        if current_time - self.last_log_time < (self.log_interval_minutes * 60):
            return
        
        self.last_log_time = current_time
        
        # Obter status
        status = self.get_status_summary()
        
        # Log formatado
        self.logger.info("=" * 80)
        self.logger.info("📊 STATUS DO GRID RISK MANAGER")
        self.logger.info("=" * 80)
        self.logger.info(f"💰 PNL Acumulado: ${status['accumulated_pnl']:+.2f} ({status['accumulated_pnl_percent']:+.2f}%)")
        
        # 🆕 MOSTRAR COMPARAÇÕES DETALHADAS COM LIMITES
        if self.enable_session_protection:
            self.logger.info("")
            self.logger.info("🛡️ LIMITES DE PROTEÇÃO:")
            
            # Stop Loss USD
            remaining_loss_usd = abs(self.session_max_loss_usd) - abs(status['accumulated_pnl'])
            loss_percentage_used = (abs(status['accumulated_pnl']) / abs(self.session_max_loss_usd)) * 100 if self.session_max_loss_usd != 0 else 0
            
            if status['accumulated_pnl'] <= 0:
                self.logger.info(f"   🚨 Stop Loss USD: ${-self.session_max_loss_usd:.2f} | Atual: ${status['accumulated_pnl']:.2f} | Restam: ${remaining_loss_usd:.2f} ({100-loss_percentage_used:.1f}%)")
            else:
                self.logger.info(f"   🚨 Stop Loss USD: ${-self.session_max_loss_usd:.2f} | Atual: ${status['accumulated_pnl']:.2f} | ✅ SEGURO")
                
            # Stop Loss Percentual
            remaining_loss_percent = self.session_max_loss_percent - abs(status['accumulated_pnl_percent'])
            if status['accumulated_pnl_percent'] <= 0:
                self.logger.info(f"   🚨 Stop Loss %:   -{self.session_max_loss_percent:.1f}% | Atual: {status['accumulated_pnl_percent']:+.2f}% | Restam: {remaining_loss_percent:.2f}pp")
            else:
                self.logger.info(f"   🚨 Stop Loss %:   -{self.session_max_loss_percent:.1f}% | Atual: {status['accumulated_pnl_percent']:+.2f}% | ✅ SEGURO")
            
            # Take Profit USD
            remaining_profit_usd = self.session_profit_target_usd - status['accumulated_pnl']
            profit_percentage_reached = (status['accumulated_pnl'] / self.session_profit_target_usd) * 100 if self.session_profit_target_usd != 0 else 0
            
            if status['accumulated_pnl'] >= self.session_profit_target_usd:
                self.logger.info(f"   🎯 Take Profit USD: ${self.session_profit_target_usd:.2f} | Atual: ${status['accumulated_pnl']:.2f} | 🎉 ATINGIDO!")
            else:
                self.logger.info(f"   🎯 Take Profit USD: ${self.session_profit_target_usd:.2f} | Atual: ${status['accumulated_pnl']:.2f} | Faltam: ${remaining_profit_usd:.2f} ({profit_percentage_reached:.1f}%)")
            
            # Take Profit Percentual
            remaining_profit_percent = self.session_profit_target_percent - status['accumulated_pnl_percent']
            if status['accumulated_pnl_percent'] >= self.session_profit_target_percent:
                self.logger.info(f"   🎯 Take Profit %:   +{self.session_profit_target_percent:.1f}% | Atual: {status['accumulated_pnl_percent']:+.2f}% | 🎉 ATINGIDO!")
            else:
                self.logger.info(f"   🎯 Take Profit %:   +{self.session_profit_target_percent:.1f}% | Atual: {status['accumulated_pnl_percent']:+.2f}% | Faltam: {remaining_profit_percent:.2f}pp")
        
        self.logger.info("")
        self.logger.info(f"🔄 Ciclos: {status['cycles_closed']} (✅{status['cycles_profit']} / ❌{status['cycles_loss']})")
        self.logger.info(f"📈 Win Rate: {status['win_rate']:.1f}%")
        self.logger.info(f"⏱️ Uptime: {status['uptime']}")
        
        if status['is_paused']:
            self.logger.info(f"⏸️ STATUS: PAUSADO até {status['pause_until']}")
        else:
            self.logger.info(f"✅ STATUS: ATIVO - Ciclo #{status['current_cycle_id']}")
        
        self.logger.info("=" * 80)
        
        # Enviar heartbeat no Telegram (se habilitado)
        self.telegram.send_heartbeat({
            'accumulated_pnl': status['accumulated_pnl'],
            'cycles_closed': status['cycles_closed'],
            'win_rate': status['win_rate'],
            'uptime': status['uptime']
        })
    
    def _save_history(self):
        """Salva histórico em arquivo JSON"""
        
        try:
            data = {
                'session_start': self.session_start.isoformat(),
                'initial_balance': self.initial_balance,
                'current_balance': self.current_balance,
                'accumulated_pnl': self.accumulated_pnl,
                'cycles_closed': self.cycles_closed,
                'cycles_profit': self.cycles_profit,
                'cycles_loss': self.cycles_loss,
                'cycles_history': self.accumulated_pnl_history,
                'last_update': datetime.now().isoformat()
            }
            
            with open(self.history_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.debug(f"💾 Histórico salvo em {self.history_file}")
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao salvar histórico: {e}")
    
    def _load_history(self):
        """Carrega histórico de arquivo JSON"""
        
        if not self.history_file.exists():
            self.logger.info("📁 Nenhum histórico anterior encontrado - iniciando nova sessão")
            return
        
        try:
            with open(self.history_file, 'r') as f:
                data = json.load(f)
            
            # Perguntar se quer continuar sessão anterior
            self.logger.info("=" * 80)
            self.logger.info("📂 HISTÓRICO ANTERIOR ENCONTRADO")
            self.logger.info(f"   Início: {data.get('session_start', 'N/A')}")
            self.logger.info(f"   PNL Acumulado: ${data.get('accumulated_pnl', 0):+.2f}")
            self.logger.info(f"   Ciclos: {data.get('cycles_closed', 0)}")
            self.logger.info("=" * 80)
            self.logger.info("⚠️ Iniciando NOVA SESSÃO (histórico anterior será preservado)")
            self.logger.info("=" * 80)
            
            # Por enquanto sempre inicia nova sessão
            # Futuro: adicionar opção de continuar sessão anterior
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao carregar histórico: {e}")
    
    def should_close_position(self) -> bool:
        """Verifica se deve fechar posição por limite de sessão"""
        should_stop, reason = self.check_session_limits()
        
        if should_stop:
            self.logger.error(f"🚨 Fechando posição por limite de sessão: {reason}")
            return True
        
        return False
    
    def get_action_on_limit(self) -> str:
        """Retorna ação configurada ao atingir limite"""
        return self.action_on_limit
    
    def reset_cycle(self):
        """Reseta ciclo atual (usado ao reiniciar grid)"""
        self.current_cycle_start = datetime.now()
        # ID de trade por ciclo (simples e único)
        trade_id = f"grid-{getattr(self, 'symbol', 'GRID')}-{int(self.current_cycle_start.timestamp())}"
        self.health.start_trade(
            trade_id,
            symbol=getattr(self, 'symbol', 'GRID'),
            side="mixed",  # grid pode alternar; se tiver lado atual, substitua
            size=0.0,      # opcional: pode preencher com exposição
            entry_price=0.0,
            entry_time=self.current_cycle_start.isoformat(),
            tp_percent=self.cycle_take_profit_percent,
            sl_percent=self.cycle_stop_loss_percent,
            extra={
                "session_targets": {
                    "max_loss_usd": self.session_max_loss_usd,
                    "profit_target_usd": self.session_profit_target_usd
                }
            }
        )
        self.logger.info(f"🔄 Ciclo #{self.current_cycle_id} iniciado")
    
    def close_session(self):
        """Fecha sessão e salva histórico final"""
        
        self.logger.info("=" * 80)
        self.logger.info("🏁 ENCERRANDO SESSÃO DE GRID TRADING")
        self.logger.info("=" * 80)
        
        status = self.get_status_summary()
        
        self.logger.info(f"⏱️ Duração Total: {status['uptime']}")
        self.logger.info(f"💰 PNL Final: ${status['accumulated_pnl']:+.2f} ({status['accumulated_pnl_percent']:+.2f}%)")
        self.logger.info(f"🔄 Total de Ciclos: {status['cycles_closed']}")
        self.logger.info(f"✅ Ciclos com Lucro: {status['cycles_profit']}")
        self.logger.info(f"❌ Ciclos com Perda: {status['cycles_loss']}")
        self.logger.info(f"📈 Win Rate: {status['win_rate']:.1f}%")
        self.logger.info("=" * 80)
        
        # Salvar histórico final
        if self.save_history:
            self._save_history()
            self.logger.info(f"💾 Histórico salvo em {self.history_file}")
        
        # Notificar Telegram
        self.telegram.send_notification(f"""
        🏁 **SESSÃO ENCERRADA**

        📊 Resumo da Sessão:
        ⏱️ Duração: {status['uptime']}
        💰 PNL Final: ${status['accumulated_pnl']:+.2f} ({status['accumulated_pnl_percent']:+.2f}%)
        🔄 Ciclos: {status['cycles_closed']} (✅{status['cycles_profit']} / ❌{status['cycles_loss']})
        📈 Win Rate: {status['win_rate']:.1f}%
        """)