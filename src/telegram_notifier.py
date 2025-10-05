"""
Sistema de Notificações Telegram para Bot Pacifica
Implementa envio de notificações com robustez, fallbacks e persistência
"""

import os
import time
import logging
import requests
from typing import Dict, Any, Optional, List
import urllib3
from dotenv import load_dotenv
import json
from pathlib import Path

# Desabilitar warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TelegramNotifier:
    """Sistema robusto de notificações Telegram com fallbacks e persistência"""
    
    def __init__(self):
        """Inicializa o sistema de notificação Telegram"""
        load_dotenv()
        
        self.logger = logging.getLogger(__name__)
        
        # Configurações do ambiente
        self.enabled = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID', '').strip()
        
        # Validação básica
        if self.enabled and (not self.bot_token or not self.chat_id):
            self.logger.error("❌ TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados")
            self.enabled = False
        
        # Configurações de timeout e retry
        self.request_timeout = int(os.getenv('TELEGRAM_TIMEOUT_SECONDS', '45'))
        self.connect_timeout = int(os.getenv('TELEGRAM_CONNECT_TIMEOUT', '20'))
        self.max_retries = int(os.getenv('TELEGRAM_MAX_RETRIES', '5'))
        self.retry_delay = float(os.getenv('TELEGRAM_RETRY_DELAY_SECONDS', '3.0'))
        self.rate_limit = float(os.getenv('TELEGRAM_RATE_LIMIT_SECONDS', '2.0'))
        
        # URLs da API Telegram
        self.api_urls = [
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        ]
        
        # Rate limiting
        self.last_message_time = 0
        
        # Sistema de fila persistente
        self.queue_file = Path("data/telegram_queue.json")
        self.backup_file = Path("logs/telegram_backup.log")
        self.message_queue = []
        self.max_queue_size = 100
        
        # Configurações de notificação específicas
        self.notify_config = {
            'cycle_close': os.getenv('TELEGRAM_NOTIFY_CYCLE_CLOSE', 'true').lower() == 'true',
            'stop_loss': os.getenv('TELEGRAM_NOTIFY_STOP_LOSS', 'true').lower() == 'true',
            'take_profit': os.getenv('TELEGRAM_NOTIFY_TAKE_PROFIT', 'true').lower() == 'true',
            'session_limit': os.getenv('TELEGRAM_NOTIFY_SESSION_LIMIT', 'true').lower() == 'true',
            'pause_resume': os.getenv('TELEGRAM_NOTIFY_PAUSE_RESUME', 'true').lower() == 'true',
            'heartbeat': os.getenv('TELEGRAM_NOTIFY_HEARTBEAT', 'false').lower() == 'true'
        }
        
        # Carregar fila de mensagens salvas
        self._load_message_queue()
        
        if self.enabled:
            self.logger.info(f"✅ Telegram Notifier ativado")
            self.logger.info(f"   Request timeout: {self.request_timeout}s")
            self.logger.info(f"   Connect timeout: {self.connect_timeout}s") 
            self.logger.info(f"   Max retries: {self.max_retries}")
            self.logger.info(f"   Chat ID: {self.chat_id}")
            if self.message_queue:
                self.logger.info(f"   📦 {len(self.message_queue)} mensagens pendentes na fila")
        else:
            self.logger.info("🔇 Telegram Notifier desabilitado")

    def _ensure_directories(self):
        """Garante que os diretórios necessários existam"""
        self.queue_file.parent.mkdir(exist_ok=True)
        self.backup_file.parent.mkdir(exist_ok=True)

    def _load_message_queue(self):
        """Carrega fila de mensagens do arquivo"""
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    self.message_queue = json.load(f)
                self.logger.debug(f"📥 {len(self.message_queue)} mensagens carregadas da fila")
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao carregar fila: {e}")
            self.message_queue = []

    def _save_message_queue(self):
        """Salva fila de mensagens no arquivo"""
        try:
            self._ensure_directories()
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(self.message_queue, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao salvar fila: {e}")

    def _add_to_queue(self, message: str, priority: str = "INFO", notification_type: str = "general"):
        """Adiciona mensagem na fila para envio posterior"""
        timestamp = time.time()
        queued_message = {
            "timestamp": timestamp,
            "message": message,
            "priority": priority,
            "type": notification_type,
            "attempts": 0,
            "max_attempts": 5
        }
        
        self.message_queue.append(queued_message)
        
        # Limitar tamanho da fila
        if len(self.message_queue) > self.max_queue_size:
            self.message_queue.pop(0)  # Remove mensagem mais antiga
        
        self._save_message_queue()
        self.logger.info(f"📦 Mensagem adicionada à fila (total: {len(self.message_queue)})")

    def _send_http_request(self, message: str) -> bool:
        """Envia mensagem via HTTP com configurações otimizadas"""
        
        for attempt in range(1, self.max_retries + 1):
            for url_index, api_url in enumerate(self.api_urls):
                try:
                    self.logger.debug(f"📱 Enviando via HTTP (tentativa {attempt}/{self.max_retries})")
                    
                    payload = {
                        'chat_id': self.chat_id,
                        'text': message,
                        'parse_mode': 'HTML',
                        'disable_web_page_preview': True
                    }
                    
                    # Configurações de sessão otimizadas
                    session = requests.Session()
                    session.headers.update({
                        'Connection': 'close',
                        'User-Agent': 'BotPacifica/2.0',
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    })
                    
                    timeout = (self.connect_timeout, self.request_timeout)
                    
                    response = session.post(
                        api_url,
                        json=payload,
                        timeout=timeout,
                        verify=True,  # Usar verificação SSL padrão
                        allow_redirects=True
                    )
                    
                    session.close()
                    
                    if response.status_code == 200:
                        self.logger.debug("✅ Mensagem Telegram enviada com sucesso")
                        return True
                    elif response.status_code == 429:
                        # Rate limiting do Telegram
                        retry_after = int(response.headers.get('Retry-After', 5))
                        self.logger.warning(f"🚫 Rate limit atingido. Aguardando {retry_after}s...")
                        time.sleep(retry_after)
                        continue
                    elif response.status_code == 400:
                        # Erro de request (chat_id inválido, etc)
                        error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                        self.logger.error(f"❌ Erro de configuração Telegram: {error_data}")
                        return False  # Não tentar novamente
                    else:
                        self.logger.warning(f"❌ Erro HTTP {response.status_code}: {response.text[:200]}")
                        
                except requests.exceptions.ConnectTimeout as e:
                    self.logger.warning(f"⏰ Timeout de conexão (tentativa {attempt}): {str(e)}")
                except requests.exceptions.ReadTimeout as e:
                    self.logger.warning(f"⏰ Timeout de leitura (tentativa {attempt}): {str(e)}")
                except requests.exceptions.SSLError as e:
                    self.logger.warning(f"🔒 Erro SSL (tentativa {attempt}): {str(e)}")
                except requests.exceptions.ConnectionError as e:
                    self.logger.warning(f"🌐 Erro de conexão (tentativa {attempt}): {str(e)}")
                except Exception as e:
                    self.logger.warning(f"❌ Erro inesperado (tentativa {attempt}): {str(e)}")
            
            # Aguardar antes da próxima tentativa
            if attempt < self.max_retries:
                delay = self.retry_delay * attempt  # Backoff linear
                self.logger.debug(f"🔄 Tentando novamente em {delay}s...")
                time.sleep(delay)
        
        return False

    def _backup_message(self, message: str, error: str = ""):
        """Salva mensagem em backup local"""
        try:
            self._ensure_directories()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] TELEGRAM_BACKUP: {message}"
            if error:
                log_entry += f" | ERROR: {error}"
            
            with open(self.backup_file, "a", encoding="utf-8") as f:
                f.write(log_entry + "\n")
            self.logger.debug("💾 Mensagem salva em backup local")
        except Exception as e:
            self.logger.error(f"❌ Erro ao salvar backup: {e}")

    def _format_message(self, title: str, message: str, priority: str = "INFO") -> str:
        """Formata mensagem com emoji e estrutura padrão"""
        emoji_map = {
            "INFO": "ℹ️",
            "SUCCESS": "✅", 
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨",
            "TRADE": "💹",
            "PROFIT": "💰",
            "LOSS": "📉"
        }
        
        emoji = emoji_map.get(priority.upper(), "📢")
        timestamp = time.strftime("%H:%M:%S")
        
        formatted_message = f"{emoji} <b>{title}</b> ({timestamp})\n{message}"
        
        # Limitar tamanho da mensagem (Telegram tem limite de 4096 caracteres)
        if len(formatted_message) > 4000:
            formatted_message = formatted_message[:3950] + "...\n<i>[Mensagem truncada]</i>"
        
        return formatted_message

    def _should_send_notification(self, notification_type: str) -> bool:
        """Verifica se deve enviar notificação baseado nas configurações"""
        if not self.enabled:
            return False
        
        return self.notify_config.get(notification_type, True)

    def send_notification(self, title: str, message: str, priority: str = "INFO", 
                         notification_type: str = "general") -> bool:
        """Envia notificação formatada com fallbacks"""
        
        if not self._should_send_notification(notification_type):
            self.logger.debug(f"🔇 Notificação '{notification_type}' desabilitada")
            return True
        
        if not self.enabled:
            self.logger.debug("🔇 Telegram desabilitado - notificação ignorada")
            return True
        
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_message_time
        if time_since_last < self.rate_limit:
            time.sleep(self.rate_limit - time_since_last)
        
        # Formatar mensagem
        formatted_message = self._format_message(title, message, priority)
        
        # Tentar enviar
        success = self._send_http_request(formatted_message)
        
        if success:
            self.last_message_time = time.time()
        else:
            # Adicionar na fila e fazer backup
            self._add_to_queue(formatted_message, priority, notification_type)
            self._backup_message(formatted_message, "Failed to send")
        
        return success

    def send_trade_notification(self, action: str, symbol: str, price: float, 
                              quantity: float, pnl: float = None) -> bool:
        """Envia notificação de trade formatada"""
        
        action_emoji = {
            "BUY": "🟢 COMPRA",
            "SELL": "🔴 VENDA", 
            "CLOSE": "⚪ FECHAMENTO"
        }
        
        action_text = action_emoji.get(action.upper(), f"📊 {action}")
        
        message = f"{action_text} - {symbol}\n"
        message += f"💰 Preço: <code>${price:.4f}</code>\n"
        message += f"📊 Quantidade: <code>{quantity}</code>"
        
        if pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            pnl_color = "+" if pnl >= 0 else ""
            message += f"\n{pnl_emoji} PnL: <code>{pnl_color}${pnl:.2f}</code>"
        
        priority = "SUCCESS" if pnl is None or pnl >= 0 else "WARNING"
        return self.send_notification("Trade Executado", message, priority, "trade")

    def send_cycle_notification(self, cycle_data: Dict[str, Any]) -> bool:
        """Envia notificação de fechamento de ciclo"""
        
        profit = cycle_data.get('profit', 0)
        trades = cycle_data.get('trades', 0)
        duration = cycle_data.get('duration', 0)
        
        emoji = "🎯" if profit >= 0 else "📉"
        message = f"Ciclo de Grid Finalizado\n"
        message += f"💹 Trades: <code>{trades}</code>\n"
        message += f"⏱️ Duração: <code>{duration}min</code>\n"
        message += f"💰 Resultado: <code>${profit:.2f}</code>"
        
        priority = "SUCCESS" if profit >= 0 else "WARNING"
        return self.send_notification("Ciclo Completo", message, priority, "cycle_close")

    def send_risk_alert(self, alert_type: str, details: Dict[str, Any]) -> bool:
        """Envia alerta de gerenciamento de risco"""
        
        risk_emoji = {
            "STOP_LOSS": "🛑",
            "TAKE_PROFIT": "🎯",
            "MAX_LOSS": "⚠️",
            "POSITION_LIMIT": "📊",
            "MARGIN_CALL": "🚨"
        }
        
        emoji = risk_emoji.get(alert_type, "⚠️")
        
        message = f"{emoji} <b>Alerta de Risco</b>\n"
        message += f"🔔 Tipo: <code>{alert_type}</code>\n"
        
        for key, value in details.items():
            if isinstance(value, float):
                message += f"• {key}: <code>{value:.4f}</code>\n"
            else:
                message += f"• {key}: <code>{value}</code>\n"
        
        notification_type = alert_type.lower()
        return self.send_notification("Risk Manager", message, "WARNING", notification_type)

    def send_status_update(self, status: str, details: Dict[str, Any] = None) -> bool:
        """Envia atualização de status do bot"""
        
        status_emoji = {
            "STARTED": "🚀",
            "STOPPED": "🛑",
            "PAUSED": "⏸️",
            "RESUMED": "▶️",
            "ERROR": "❌",
            "HEALTHY": "💚"
        }
        
        emoji = status_emoji.get(status.upper(), "📊")
        message = f"Status do Bot: <b>{status}</b>"
        
        if details:
            message += "\n"
            for key, value in details.items():
                message += f"\n• {key}: <code>{value}</code>"
        
        priority = "ERROR" if status.upper() == "ERROR" else "INFO"
        return self.send_notification("Bot Status", message, priority, "pause_resume")

    def send_heartbeat(self, stats: Dict[str, Any] = None) -> bool:
        """Envia heartbeat periódico"""
        
        if not self._should_send_notification("heartbeat"):
            return True
        
        message = "Bot ativo e operando"
        
        if stats:
            message += "\n"
            for key, value in stats.items():
                if isinstance(value, float):
                    message += f"\n• {key}: <code>{value:.2f}</code>"
                else:
                    message += f"\n• {key}: <code>{value}</code>"
        
        return self.send_notification("Heartbeat", message, "INFO", "heartbeat")

    def test_connection(self) -> bool:
        """Testa a conexão com o Telegram"""
        
        if not self.enabled:
            self.logger.info("🔇 Telegram desabilitado - teste ignorado")
            return True
        
        test_message = "🧪 Teste de conexão Telegram - Bot Pacifica ativo!"
        return self.send_notification("Teste de Conexão", test_message, "INFO")

    def process_message_queue(self) -> int:
        """Processa mensagens na fila para reenvio"""
        
        if not self.message_queue:
            return 0
        
        sent_count = 0
        remaining_messages = []
        
        for queued_msg in self.message_queue:
            queued_msg["attempts"] += 1
            
            # Tentar enviar mensagem da fila
            success = self._send_http_request(queued_msg["message"])
            
            if success:
                sent_count += 1
                self.logger.info(f"✅ Mensagem da fila enviada (tentativa {queued_msg['attempts']})")
            elif queued_msg["attempts"] < queued_msg.get("max_attempts", 5):
                remaining_messages.append(queued_msg)
            else:
                self.logger.warning(f"❌ Mensagem descartada após {queued_msg['attempts']} tentativas")
                self._backup_message(queued_msg["message"], "Max attempts reached")
        
        self.message_queue = remaining_messages
        self._save_message_queue()
        
        if sent_count > 0:
            self.logger.info(f"📤 {sent_count} mensagens da fila enviadas com sucesso")
        
        return sent_count

    def get_queue_stats(self) -> Dict[str, int]:
        """Retorna estatísticas da fila de mensagens"""
        stats = {
            "total_messages": len(self.message_queue),
            "high_priority": 0,
            "medium_priority": 0,
            "low_priority": 0
        }
        
        for msg in self.message_queue:
            priority = msg.get("priority", "INFO").upper()
            if priority in ["CRITICAL", "ERROR"]:
                stats["high_priority"] += 1
            elif priority in ["WARNING"]:
                stats["medium_priority"] += 1
            else:
                stats["low_priority"] += 1
        
        return stats

    def clear_queue(self) -> int:
        """Limpa a fila de mensagens"""
        count = len(self.message_queue)
        self.message_queue = []
        self._save_message_queue()
        self.logger.info(f"🗑️ {count} mensagens removidas da fila")
        return count


# Função de conveniência para compatibilidade
def create_telegram_notifier() -> TelegramNotifier:
    """Cria instância do notificador Telegram"""
    return TelegramNotifier()


if __name__ == "__main__":
    # Teste rápido
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    notifier = TelegramNotifier()
    
    if notifier.enabled:
        print("🧪 Testando Telegram Notifier...")
        
        # Teste de conexão
        success = notifier.test_connection()
        print(f"✅ Teste de conexão: {'✓' if success else '✗'}")
        
        # Teste de notificação de trade
        success = notifier.send_trade_notification("BUY", "SOL", 150.25, 10.0, 15.50)
        print(f"✅ Teste de trade: {'✓' if success else '✗'}")
        
        # Estatísticas da fila
        stats = notifier.get_queue_stats()
        print(f"📊 Fila: {stats['total_messages']} mensagens")
        
        # Processar fila se houver mensagens pendentes
        if stats['total_messages'] > 0:
            sent = notifier.process_message_queue()
            print(f"📤 {sent} mensagens da fila processadas")
    else:
        print("🔇 Telegram desabilitado")