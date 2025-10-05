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
        # self.logger.info(f"*** _calculate_position_pnl CALLED ***")

        # Tentar obter do cache primeiro
        if symbol not in self.position_mgr.positions:
            self.logger.info(f"*** SYMBOL {symbol} NOT IN positions - UPDATING... ***")
            
            # Forçar atualização
            self.position_mgr.update_account_state()
            
            # Verificar novamente
            if symbol not in self.position_mgr.positions:
                self.logger.info(f"*** STILL NOT FOUND after update ***")
                return None
        
        position = self.position_mgr.positions[symbol]

        if symbol not in self.position_mgr.positions:
            self.logger.info(f"*** SYMBOL {symbol} NOT IN positions ***")
            self.logger.info(f"*** Available symbols: {list(self.position_mgr.positions.keys())} ***")
            return None
        
        position = self.position_mgr.positions[symbol]
        # self.logger.info(f"*** Position data: {position} ***")
        
        quantity = position.get('quantity', 0)
        avg_price = position.get('avg_price', 0)
        
        # self.logger.info(f"*** quantity={quantity}, avg_price={avg_price} ***")
        
        if quantity == 0 or avg_price == 0:
            self.logger.info(f"*** RETURNING NONE: quantity={quantity}, avg_price={avg_price} ***")
            return None
        
        # Calcular PNL
        pnl_usd = (current_price - avg_price) * quantity
        pnl_percent = ((current_price - avg_price) / avg_price) * 100
        
        # self.logger.info(f"*** CALCULATED PNL: ${pnl_usd:.2f} ({pnl_percent:.2f}%) ***")
        
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
        """Log periódico do status"""
        
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