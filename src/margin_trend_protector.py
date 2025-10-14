"""
Proteção por Tendência de Margem - Universal
Detecta quedas súbitas de margem e toma ações preventivas
Aplica-se a TODAS as estratégias (grid, multi-asset, etc.)
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from pathlib import Path
import json
from src.risk_health_reporter import RiskHealthReporter  # ⬅️ ADD

@dataclass
class MarginSnapshot:
    """Snapshot de margem em um momento específico"""
    timestamp: datetime
    margin_percent: float
    balance_usd: float
    
class MarginTrendProtector:
    """
    Protetor Universal de Tendência de Margem
    """
    
    def __init__(self, config: dict, external_logger=None):
        """Inicializar com configurações do .env"""
        
        # Configurações básicas
        self.enabled = config.get('ENABLE_MARGIN_TREND_PROTECTION', 'false').lower() == 'true'
        self.drop_threshold = float(config.get('MARGIN_DROP_THRESHOLD_PERCENT', 15.0))
        self.history_minutes = int(config.get('MARGIN_HISTORY_MINUTES', 3))
        self.check_interval = int(config.get('MARGIN_TREND_CHECK_INTERVAL', 30))
        self.action = config.get('MARGIN_TREND_ACTION', 'cancel_orders')
        self.pause_minutes = int(config.get('MARGIN_TREND_PAUSE_MINUTES', 30))
        self.log_enabled = config.get('MARGIN_TREND_LOG_ENABLED', 'true').lower() == 'true'
        
        # Histórico de margem
        self.margin_history: List[MarginSnapshot] = []
        
        # Controle de estado
        self.is_paused = False
        self.pause_until: Optional[datetime] = None
        self.last_check = datetime.now()
        
        # Callbacks para ações (serão definidos externamente)
        self.callbacks = {
            'cancel_orders': None,
            'reduce_positions': None,
            'pause_bot': None,
            'shutdown_bot': None,
            'get_current_margin': None
        }
        
        # Setup logging - usar logger externo se fornecido
        if external_logger:
            self.logger = external_logger
        else:
            self.logger = logging.getLogger('MarginTrendProtector')
            if self.log_enabled:
                self.logger.setLevel(logging.INFO)
        
        # Arquivo de histórico
        self.history_file = Path("data/margin_trend_history.json")
        self.history_file.parent.mkdir(exist_ok=True)
        
        if self.enabled:
            self.logger.info(f"✅ Proteção de Margem ATIVADA - Threshold: {self.drop_threshold}%")
            self.logger.info(f"📊 Histórico: {self.history_minutes}min | Ação: {self.action} | Intervalo: {self.check_interval}s")
        else:
            self.logger.info("⏸️ Proteção de Margem DESATIVADA")
        
        # Contador para logs periódicos
        self.status_log_counter = 0
        self.health = RiskHealthReporter(strategy_name="margin_trend")  # ⬅️ ADD
    
    def register_callback(self, action: str, callback: Callable):
        """Registrar callbacks para ações específicas"""
        self.callbacks[action] = callback
        self.logger.debug(f"Callback registrado: {action}")
    
    def add_margin_snapshot(self, margin_percent: float, balance_usd: float = 0):
        """Adicionar snapshot de margem ao histórico"""
        if not self.enabled:
            return
        
        snapshot = MarginSnapshot(
            timestamp=datetime.now(),
            margin_percent=margin_percent,
            balance_usd=balance_usd
        )
        
        self.margin_history.append(snapshot)
        
        # Limpar histórico antigo (manter apenas o período necessário)
        cutoff_time = datetime.now() - timedelta(minutes=self.history_minutes)
        self.margin_history = [
            s for s in self.margin_history 
            if s.timestamp > cutoff_time
        ]
        
        if self.log_enabled:
            # Log detalhado a cada 10 snapshots (para não spammar)
            if len(self.margin_history) % 10 == 0 or len(self.margin_history) <= 3:
                self.logger.info(f"📊 Margem: {margin_percent:.1f}% | Histórico: {len(self.margin_history)} pontos | Período: {self.history_minutes}min")
            else:
                self.logger.debug(f"Margem: {margin_percent:.2f}% - Histórico: {len(self.margin_history)} pontos")
        # Telemetria leve de margem
        self.health.update_status({
            "margin_percent": margin_percent,
            "balance_usd": balance_usd,
            "history_points": len(self.margin_history)
        })
    
    def check_margin_trend(self) -> Dict:
        """
        Verificar tendência de margem e tomar ação se necessário
        Retorna resultado da verificação
        """
        if not self.enabled:
            return {"status": "disabled"}
        
        # Verificar se ainda está pausado
        if self.is_paused and self.pause_until:
            if datetime.now() < self.pause_until:
                return {"status": "paused", "pause_until": self.pause_until}
            else:
                self.is_paused = False
                self.pause_until = None
                self.logger.info("✅ Proteção de margem reativada após pausa")
        
        # Verificar se é hora de checar
        if (datetime.now() - self.last_check).seconds < self.check_interval:
            return {"status": "waiting"}
        
        self.last_check = datetime.now()
        
        # Precisamos de pelo menos 2 pontos para comparar
        if len(self.margin_history) < 2:
            return {"status": "insufficient_data", "points": len(self.margin_history)}
        
        # Obter margem atual e histórica
        current_snapshot = self.margin_history[-1]
        oldest_snapshot = self.margin_history[0]
        
        # Calcular queda percentual
        margin_drop = oldest_snapshot.margin_percent - current_snapshot.margin_percent
        drop_percent = (margin_drop / oldest_snapshot.margin_percent) * 100
        
        # Log da verificação
        if self.log_enabled:
            time_diff = (current_snapshot.timestamp - oldest_snapshot.timestamp).seconds / 60
            
            # Log normal a cada 20 verificações ou quando há mudança significativa
            self.status_log_counter += 1
            should_log = (self.status_log_counter % 20 == 0) or (abs(drop_percent) > self.drop_threshold * 0.5)
            
            if should_log:
                trend_icon = "📈" if drop_percent < 0 else "📉" if drop_percent > 5 else "➡️"
                self.logger.info(
                    f"🔍 {trend_icon} Verificação: Margem {oldest_snapshot.margin_percent:.1f}% → "
                    f"{current_snapshot.margin_percent:.1f}% em {time_diff:.1f}min "
                    f"(variação: {drop_percent:+.1f}% | limite: {self.drop_threshold}%)"
                )
        
        # Telemetria da checagem
        self.health.log_check("margin_check", {
            "current_margin": current_snapshot.margin_percent,
            "drop_percent": round(drop_percent,2),
            "threshold": self.drop_threshold,
            "window_min": self.history_minutes
        })
        # Verificar se excedeu threshold
        if drop_percent >= self.drop_threshold:
            return self._trigger_protection(drop_percent, current_snapshot, oldest_snapshot)
        
        return {
            "status": "normal",
            "drop_percent": round(drop_percent, 2),
            "threshold": self.drop_threshold,
            "current_margin": current_snapshot.margin_percent
        }
    
    def _trigger_protection(self, drop_percent: float, current: MarginSnapshot, oldest: MarginSnapshot) -> Dict:
        """Acionar proteção de margem"""
        
        time_diff = (current.timestamp - oldest.timestamp).seconds / 60
        
        self.logger.critical("=" * 80)
        self.logger.critical("🚨 PROTEÇÃO DE MARGEM ACIONADA!")
        self.health.log_check("margin_protection_triggered", {
            "drop_percent": round(drop_percent,2),
            "action": self.action,
            "window_min": self.history_minutes
        })
        self.logger.critical(f"📊 Margem caiu {drop_percent:.1f}% em {time_diff:.1f} minutos")
        self.logger.critical(f"📈 Margem anterior: {oldest.margin_percent:.1f}%")
        self.logger.critical(f"📉 Margem atual: {current.margin_percent:.1f}%")
        self.logger.critical(f"⚠️ Limite configurado: {self.drop_threshold}%")
        self.logger.critical(f"🔧 Ação a ser executada: {self.action.upper()}")
        self.logger.critical("=" * 80)
        
        # Salvar evento no histórico
        self._save_protection_event(drop_percent, current, oldest)
        
        # Executar ação configurada
        action_result = self._execute_action()
        
        return {
            "status": "protection_triggered",
            "drop_percent": round(drop_percent, 2),
            "action": self.action,
            "action_result": action_result,
            "current_margin": current.margin_percent,
            "previous_margin": oldest.margin_percent
        }
    
    def _execute_action(self) -> Dict:
        """Executar ação de proteção"""
        
        try:
            if self.action == 'pause':
                return self._pause_protection()
            
            elif self.action == 'cancel_orders':
                if self.callbacks['cancel_orders']:
                    result = self.callbacks['cancel_orders']()
                    self.logger.info("📋 Ordens canceladas por proteção de margem")
                    return {"success": True, "message": "Ordens canceladas", "details": result}
                else:
                    self.logger.error("❌ Callback cancel_orders não registrado")
                    return {"success": False, "error": "Callback não disponível"}
            
            elif self.action == 'reduce_positions':
                if self.callbacks['reduce_positions']:
                    result = self.callbacks['reduce_positions']()
                    self.logger.info("📉 Posições reduzidas por proteção de margem")
                    return {"success": True, "message": "Posições reduzidas", "details": result}
                else:
                    self.logger.error("❌ Callback reduce_positions não registrado")
                    return {"success": False, "error": "Callback não disponível"}
            
            elif self.action == 'shutdown':
                if self.callbacks['shutdown_bot']:
                    result = self.callbacks['shutdown_bot']()
                    self.logger.critical("🛑 Bot desligado por proteção de margem")
                    return {"success": True, "message": "Bot desligado", "details": result}
                else:
                    self.logger.error("❌ Callback shutdown_bot não registrado")
                    return {"success": False, "error": "Callback não disponível"}
            
            else:
                self.logger.error(f"❌ Ação desconhecida: {self.action}")
                return {"success": False, "error": f"Ação '{self.action}' não implementada"}
        
        except Exception as e:
            self.logger.error(f"❌ Erro ao executar ação {self.action}: {e}")
            return {"success": False, "error": str(e)}
    
    def _pause_protection(self) -> Dict:
        """Pausar proteção por tempo determinado"""
        self.is_paused = True
        self.pause_until = datetime.now() + timedelta(minutes=self.pause_minutes)
        
        self.logger.warning(f"⏸️ Proteção pausada por {self.pause_minutes} minutos até {self.pause_until}")
        
        return {
            "success": True,
            "message": f"Proteção pausada por {self.pause_minutes} minutos",
            "pause_until": self.pause_until.isoformat()
        }
    
    def _save_protection_event(self, drop_percent: float, current: MarginSnapshot, oldest: MarginSnapshot):
        """Salvar evento de proteção no histórico"""
        try:
            event = {
                "timestamp": datetime.now().isoformat(),
                "drop_percent": round(drop_percent, 2),
                "current_margin": current.margin_percent,
                "previous_margin": oldest.margin_percent,
                "action": self.action,
                "threshold": self.drop_threshold,
                "time_window_minutes": self.history_minutes
            }
            
            # Ler histórico existente
            history = []
            if self.history_file.exists():
                try:
                    history = json.loads(self.history_file.read_text())
                except:
                    history = []
            
            # Adicionar novo evento
            history.append(event)
            
            # Manter apenas últimos 100 eventos
            if len(history) > 100:
                history = history[-100:]
            
            # Salvar
            self.history_file.write_text(json.dumps(history, indent=2))
            
        except Exception as e:
            self.logger.error(f"Erro ao salvar evento: {e}")
    
    def get_status(self) -> Dict:
        """Obter status atual da proteção"""
        return {
            "enabled": self.enabled,
            "is_paused": self.is_paused,
            "pause_until": self.pause_until.isoformat() if self.pause_until else None,
            "drop_threshold": self.drop_threshold,
            "history_minutes": self.history_minutes,
            "action": self.action,
            "history_points": len(self.margin_history),
            "last_check": self.last_check.isoformat()
        }
    
    def manual_trigger(self, reason: str = "Manual") -> Dict:
        """Acionar proteção manualmente para testes"""
        self.logger.warning(f"🔧 Proteção acionada manualmente: {reason}")
        return self._execute_action()

# ========== FUNÇÃO DE INTEGRAÇÃO ==========

def create_margin_protector(config: dict) -> MarginTrendProtector:
    """
    Factory function para criar protetor de margem
    """
    return MarginTrendProtector(config)

# ========== EXEMPLO DE USO ==========

if __name__ == "__main__":
    # Teste rápido
    config = {
        'ENABLE_MARGIN_TREND_PROTECTION': 'true',
        'MARGIN_DROP_THRESHOLD_PERCENT': '10.0',
        'MARGIN_HISTORY_MINUTES': '2',
        'MARGIN_TREND_ACTION': 'pause'
    }
    
    protector = create_margin_protector(config)
    
    # Simular quedas de margem
    protector.add_margin_snapshot(50.0)
    time.sleep(1)
    protector.add_margin_snapshot(45.0)
    time.sleep(1)
    protector.add_margin_snapshot(40.0)  # Queda de 20%
    
    result = protector.check_margin_trend()
    print(f"Resultado: {result}")

# ========== CLASSE ADAPTADORA PARA GRID BOT ==========

class MarginTrendAdapter:
    """
    Adaptador que integra o MarginTrendProtector com qualquer bot
    sem poluir o código principal
    """
    
    def __init__(self, bot_instance, config: dict):
        """
        Inicializar adaptador
        
        Args:
            bot_instance: Instância do bot (GridTradingBot, etc.)
            config: Configurações do ambiente
        """
        self.bot = bot_instance
        # Usar o logger do bot principal para garantir que apareça nos logs
        if hasattr(bot_instance, 'logger') and bot_instance.logger:
            self.logger = bot_instance.logger
        else:
            self.logger = logging.getLogger('MarginTrendAdapter')
        
        # Criar protetor de margem com logger compartilhado
        self.protector = MarginTrendProtector(config, external_logger=self.logger)
        
        # Auto-registrar callbacks
        self._register_callbacks()
        
        # Log status da proteção
        if self.protector.enabled:
            self.logger.info("✅ Adaptador de proteção de margem inicializado")
            self.logger.info(f"🔧 Configuração: {self.protector.drop_threshold}% em {self.protector.history_minutes}min → {self.protector.action}")
        else:
            self.logger.info("⏸️ Adaptador inicializado (proteção DESABILITADA)")
        
        # Contador para logs periódicos
        self.monitor_counter = 0
    
    def _register_callbacks(self):
        """Registrar callbacks automaticamente"""
        self.protector.register_callback('cancel_orders', self._cancel_all_orders)
        self.protector.register_callback('reduce_positions', self._reduce_positions)
        self.protector.register_callback('shutdown_bot', self._shutdown_bot)
        self.protector.register_callback('get_current_margin', self._get_margin_percent)
    
    def _cancel_all_orders(self):
        """Cancelar todas as ordens ativas"""
        try:
            if hasattr(self.bot, 'strategy') and self.bot.strategy and hasattr(self.bot.strategy, 'cancel_all_orders'):
                self.logger.warning("🚫 Cancelando todas as ordens via estratégia")
                result = self.bot.strategy.cancel_all_orders()
                return {"success": True, "message": "Ordens canceladas pela estratégia", "details": result}
            elif hasattr(self.bot, 'auth') and self.bot.auth:
                self.logger.warning("🚫 Cancelando todas as ordens via API")
                symbol = getattr(self.bot, 'symbol', 'BTC')
                result = self.bot.auth.cancel_all_orders(symbol)
                return {"success": True, "message": "Ordens canceladas via API", "details": result}
            else:
                self.logger.error("❌ Nenhum método disponível para cancelar ordens")
                return {"success": False, "error": "Nenhum método disponível"}
        except Exception as e:
            self.logger.error(f"❌ Erro ao cancelar ordens: {e}")
            return {"success": False, "error": str(e)}
    
    def _reduce_positions(self):
        """Reduzir posições ativas"""
        try:
            if hasattr(self.bot, 'position_mgr') and self.bot.position_mgr:
                self.logger.warning("📉 Reduzindo posições por proteção de margem")
                # Usar o método interno de redução de posição em margem baixa
                if hasattr(self.bot.position_mgr, '_reduce_position_on_low_margin'):
                    result = self.bot.position_mgr._reduce_position_on_low_margin()
                    return {"success": True, "message": "Posições reduzidas", "freed_margin": result}
                else:
                    self.logger.error("❌ Método de redução de posição não disponível")
                    return {"success": False, "error": "Método não disponível"}
            else:
                self.logger.error("❌ Position manager não disponível")
                return {"success": False, "error": "Position manager não disponível"}
        except Exception as e:
            self.logger.error(f"❌ Erro ao reduzir posições: {e}")
            return {"success": False, "error": str(e)}
    
    def _shutdown_bot(self):
        """Desligar bot"""
        try:
            if hasattr(self.bot, 'shutdown'):
                self.logger.critical("🛑 Desligando bot por proteção de margem")
                result = self.bot.shutdown()
                return {"success": True, "message": "Bot desligado", "details": result}
            elif hasattr(self.bot, 'stop'):
                self.logger.critical("🛑 Parando bot por proteção de margem")
                self.bot.stop()
                return {"success": True, "message": "Bot parado"}
            else:
                self.logger.error("❌ Método de shutdown não disponível")
                return {"success": False, "error": "Método não disponível"}
        except Exception as e:
            self.logger.error(f"❌ Erro ao desligar bot: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_margin_percent(self):
        """Obter percentual de margem atual"""
        try:
            if hasattr(self.bot, 'position_mgr') and self.bot.position_mgr:
                # Calcular margem livre como percentual
                total_balance = self.bot.position_mgr.margin_used + self.bot.position_mgr.margin_available
                if total_balance > 0:
                    margin_percent = (self.bot.position_mgr.margin_available / total_balance) * 100
                    return margin_percent
                else:
                    return 100.0  # Se não há posições, margem está 100% livre
            else:
                self.logger.warning("⚠️ Position manager não disponível para calcular margem")
                return 50.0  # Valor padrão conservador
        except Exception as e:
            self.logger.error(f"❌ Erro ao calcular margem: {e}")
            return 50.0  # Valor padrão em caso de erro
    
    def _get_balance(self):
        """Obter saldo atual para histórico"""
        try:
            if hasattr(self.bot, 'position_mgr') and self.bot.position_mgr:
                return self.bot.position_mgr.margin_used + self.bot.position_mgr.margin_available
            else:
                return 0.0
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter saldo: {e}")
            return 0.0
    
    def monitor_and_protect(self):
        """
        Método principal para monitorar e proteger
        Deve ser chamado no loop do bot
        """
        try:
            self.monitor_counter += 1
            
            # Obter dados atuais
            current_margin = self._get_margin_percent()
            current_balance = self._get_balance()
            
            # Log de status periódico (a cada 50 chamadas = ~50 minutos se chamado a cada minuto)
            if self.monitor_counter % 50 == 1:
                self.logger.info(f"💡 Monitor de Margem - Status: Margem {current_margin:.1f}% | Saldo ${current_balance:,.2f}")
            
            # Adicionar snapshot ao histórico
            self.protector.add_margin_snapshot(current_margin, current_balance)
            
            # Verificar proteção
            result = self.protector.check_margin_trend()
            
            # Log eventos importantes
            status = result.get("status")
            if status == "protection_triggered":
                self.logger.critical(f"🚨 ADAPTADOR: Proteção acionada! Resultado: {result}")
                return result
            elif status == "paused":
                # Log apenas a cada 10 chamadas quando pausado
                if self.monitor_counter % 10 == 0:
                    self.logger.warning("⏸️ Proteção pausada - aguardando retomada...")
                return result
            elif status == "normal":
                # Log ocasional do status normal
                if self.monitor_counter % 100 == 0:  # A cada ~100 chamadas
                    drop = result.get("drop_percent", 0)
                    threshold = result.get("threshold", 0)
                    self.logger.info(f"✅ Status normal - Variação: {drop:+.1f}% (limite: {threshold}%)")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erro no monitoramento de margem: {e}")
            return {"status": "error", "error": str(e)}
    
    def get_status(self):
        """Obter status da proteção"""
        return self.protector.get_status()
    
    def log_detailed_status(self):
        """Log status detalhado da proteção (para debug)"""
        try:
            status = self.get_status()
            current_margin = self._get_margin_percent()
            current_balance = self._get_balance()
            
            self.logger.info("=" * 50)
            self.logger.info("📊 STATUS DETALHADO DA PROTEÇÃO DE MARGEM")
            self.logger.info(f"🔧 Habilitada: {'SIM' if status['enabled'] else 'NÃO'}")
            self.logger.info(f"⏸️ Pausada: {'SIM' if status['is_paused'] else 'NÃO'}")
            self.logger.info(f"📈 Margem Atual: {current_margin:.1f}%")
            self.logger.info(f"💰 Saldo Atual: ${current_balance:,.2f}")
            self.logger.info(f"⚠️ Limite de Queda: {status['drop_threshold']}%")
            self.logger.info(f"⏱️ Período de Análise: {status['history_minutes']} minutos")
            self.logger.info(f"🔧 Ação Configurada: {status['action']}")
            self.logger.info(f"📋 Pontos no Histórico: {status['history_points']}")
            self.logger.info(f"🕒 Última Verificação: {status['last_check']}")
            if status['is_paused'] and status['pause_until']:
                self.logger.info(f"⏰ Pausa até: {status['pause_until']}")
            self.logger.info("=" * 50)
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter status detalhado: {e}")
    
    def manual_trigger(self, reason: str = "Manual"):
        """Acionar proteção manualmente"""
        return self.protector.manual_trigger(reason)

# ========== FUNÇÃO FACTORY SIMPLIFICADA ==========

def create_margin_trend_adapter(bot_instance, config: dict) -> MarginTrendAdapter:
    """
    Factory function para criar adaptador de proteção de margem
    
    Args:
        bot_instance: Instância do bot
        config: Configurações do ambiente
    
    Returns:
        MarginTrendAdapter configurado e pronto para uso
    """
    return MarginTrendAdapter(bot_instance, config)