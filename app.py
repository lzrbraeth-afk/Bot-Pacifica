"""
Interface Web Flask Melhorada - Bot Trading Pacifica.fi
Versão 1.2 - CORREÇÕES CRÍTICAS APLICADAS:
1. Inicialização de componentes de risco implementada
2. Respostas de erro padronizadas
3. Endpoint duplicado removido (/risk_status)
4. Sistema de fallback robusto
5. Melhor tratamento de exceções

CHANGELOG v1.1 → v1.2:
- ✅ CORREÇÃO 1: Função initialize_risk_components() criada e chamada no startup
- ✅ CORREÇÃO 2: Helper risk_error_response() para respostas consistentes
- ✅ CORREÇÃO 4: Removido endpoint duplicado /risk_status
- ✅ Adicionado sistema de fallback para arquivos JSON
- ✅ Logs melhorados para debugging
- ✅ Validação de componentes antes de uso
"""
from flask import Flask, render_template, jsonify, request, send_file, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ===== IMPORTS PARA MÓDULO CSV =====
from werkzeug.utils import secure_filename
import shutil
from src.csv_trade_parser import PacificaCSVParser, analyze_pacifica_csv

# ===== IMPORT VOLUME TRACKER =====
from src.volume_tracker import get_volume_tracker

# ===== IMPORTS PARA GERENCIAMENTO DE RISCO =====
# NOTA: Imports condicionais movidos para initialize_risk_components()

import subprocess
import psutil
import os
import json
import csv
from pathlib import Path
from datetime import datetime, timedelta
import logging
import threading
import time
import traceback
from io import StringIO, BytesIO
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pacifica-bot-secret-key-2024'
CORS(app)

# CONFIGURAÇÃO MAIS CONSERVADORA PARA WINDOWS  
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=120,
    ping_interval=60,
    allow_upgrades=False,
    transports=['polling'],
    always_connect=False
)

# ===== CONFIGURAÇÃO UPLOAD CSV =====
UPLOAD_FOLDER = Path("data/uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {'csv'}

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# ===== INSTÂNCIAS PRINCIPAIS PARA O PAINEL DE RISCO =====
# ⚠️ CORREÇÃO 1: Variáveis globais serão inicializadas na função initialize_risk_components()
grid_risk_manager = None
emergency_sl = None
strategy = None
risk_components_initialized = False  # ✅ NOVO: Flag de controle

# Configurações
BOT_SCRIPT = "grid_bot.py"
PID_FILE = Path("bot.pid")
ENV_FILE = Path(".env")
LOGS_DIR = Path("logs")
DATA_DIR = Path("data")
PNL_HISTORY_FILE = DATA_DIR / "grid_pnl_history.json"
POSITIONS_FILE = DATA_DIR / "active_positions.json"
ORDERS_FILE = DATA_DIR / "active_orders.json"

# Detectar Python correto
import sys
PYTHON_EXECUTABLE = sys.executable

# Thread de monitoramento
monitor_thread = None
monitor_active = False
logs_monitor_thread = None

# ========== ✅ CORREÇÃO 2: FUNÇÃO HELPER PARA RESPOSTAS DE ERRO PADRONIZADAS ==========

def risk_error_response(error_msg, bot_status="unknown", http_code=503):
    """
    ✅ NOVO: Retorna resposta de erro padronizada para endpoints de risco
    Garante que o frontend sempre recebe uma estrutura JSON válida
    
    Args:
        error_msg: Mensagem de erro descritiva
        bot_status: Status do bot (disconnected, running_separate, error, unknown)
        http_code: Código HTTP a retornar (padrão: 503 Service Unavailable)
    
    Returns:
        tuple: (jsonify(data), http_code)
    """
    return jsonify({
        "status": "error",
        "error": error_msg,
        "bot_status": bot_status,
        "initialized": risk_components_initialized,
        "timestamp": datetime.now().isoformat(),
        # Estruturas mínimas para não quebrar o frontend
        "protection_config": {
            "cycle_protection_enabled": False,
            "session_protection_enabled": False
        },
        "session_status": {
            "is_paused": False,
            "session_start": None
        },
        "performance": {
            "accumulated_pnl_usd": 0,
            "cycles_closed": 0,
            "win_rate": 0
        },
        "limits_analysis": {},
        "emergency_system": {},
        "positions": {
            "active_count": 0,
            "max_concurrent": 0
        }
    }), http_code

def safe_read_json_file(file_path, default_value=None):
    """
    ✅ NOVO: Lê arquivo JSON com tratamento de erro robusto
    
    Args:
        file_path: Caminho do arquivo
        default_value: Valor padrão se arquivo não existir ou erro
    
    Returns:
        Dados do arquivo ou default_value
    """
    try:
        if not Path(file_path).exists():
            return default_value
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"⚠️ Erro ao ler {file_path}: {e}")
        return default_value

# ========== FUNÇÕES DE GERENCIAMENTO DO BOT (MANTIDAS INTACTAS) ==========

def is_bot_running():
    """Verifica se o bot está rodando"""
    if not PID_FILE.exists():
        return False
    
    try:
        pid = int(PID_FILE.read_text().strip())
        process = psutil.Process(pid)
        cmdline = ' '.join(process.cmdline())
        is_grid_bot = 'grid_bot' in cmdline or 'python' in cmdline
        
        if not is_grid_bot:
            PID_FILE.unlink()
            return False
        
        return process.is_running()
    except (psutil.NoSuchProcess, ProcessLookupError, ValueError):
        if PID_FILE.exists():
            PID_FILE.unlink()
        return False

def get_bot_status():
    """Obtém status detalhado do bot"""
    if not is_bot_running():
        return {
            "running": False,
            "pid": None,
            "cpu_percent": 0,
            "memory_mb": 0,
            "uptime_seconds": 0
        }
    
    try:
        pid = int(PID_FILE.read_text().strip())
        process = psutil.Process(pid)
        create_time = process.create_time()
        uptime = time.time() - create_time
        
        return {
            "running": True,
            "pid": pid,
            "cpu_percent": process.cpu_percent(interval=0.1),
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "uptime_seconds": int(uptime)
        }
    except Exception as e:
        logger.error(f"Erro ao obter status: {e}")
        return {
            "running": False,
            "pid": None,
            "cpu_percent": 0,
            "memory_mb": 0,
            "uptime_seconds": 0
        }

def start_bot():
    """Inicia o bot"""
    if is_bot_running():
        return {"status": "error", "message": "Bot já está rodando"}
    
    try:
        if not Path(BOT_SCRIPT).exists():
            return {"status": "error", "message": f"Arquivo {BOT_SCRIPT} não encontrado"}
        
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        
        process = subprocess.Popen(
            [PYTHON_EXECUTABLE, BOT_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd(),
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        )
        
        time.sleep(2)
        
        if process.poll() is None:
            PID_FILE.write_text(str(process.pid))
            logger.info(f"✅ Bot iniciado com PID {process.pid}")
            
            socketio.emit('bot_status_changed', {'running': True, 'pid': process.pid})
            socketio.emit('alert', {
                'type': 'success',
                'message': f'🤖 Bot iniciado com sucesso! PID: {process.pid}',
                'timestamp': datetime.now().isoformat()
            })
            
            return {"status": "success", "message": f"Bot iniciado com PID {process.pid}", "pid": process.pid}
        else:
            stdout, stderr = process.communicate()
            error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Erro desconhecido"
            
            logger.error(f"❌ Bot crashou ao iniciar: {error_msg}")
            
            socketio.emit('alert', {
                'type': 'error',
                'message': f'❌ Bot crashou ao iniciar. Verifique os logs.',
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                "status": "error", 
                "message": f"Bot crashou ao iniciar. Erro: {error_msg[:200]}"
            }
            
    except Exception as e:
        logger.error(f"❌ Erro ao iniciar bot: {e}")
        return {"status": "error", "message": str(e)}

def stop_bot(force=False):
    """Para o bot"""
    if not is_bot_running():
        return {"status": "error", "message": "Bot não está rodando"}
    
    try:
        pid = int(PID_FILE.read_text().strip())
        process = psutil.Process(pid)
        
        if force:
            process.kill()
            logger.info(f"🛑 Bot parado forçadamente (PID {pid})")
            message = f"Bot parado forçadamente (PID {pid})"
        else:
            process.terminate()
            process.wait(timeout=10)
            logger.info(f"🛑 Bot parado graciosamente (PID {pid})")
            message = f"Bot parado graciosamente (PID {pid})"
        
        if PID_FILE.exists():
            PID_FILE.unlink()
        
        socketio.emit('bot_status_changed', {'running': False, 'pid': None})
        socketio.emit('alert', {
            'type': 'warning',
            'message': f'🛑 {message}',
            'timestamp': datetime.now().isoformat()
        })
        
        return {"status": "success", "message": message}
    except Exception as e:
        logger.error(f"❌ Erro ao parar bot: {e}")
        return {"status": "error", "message": str(e)}

def restart_bot():
    """Reinicia o bot"""
    stop_result = stop_bot()
    if stop_result["status"] == "success":
        time.sleep(2)
        return start_bot()
    return stop_result

# ========== ✅ CORREÇÃO 1: FUNÇÃO DE INICIALIZAÇÃO DE COMPONENTES DE RISCO ==========

def initialize_risk_components():
    """
    ✅ NOVO: Inicializa componentes de gerenciamento de risco para o painel web
    
    Esta função tenta inicializar os componentes de risco que são usados
    pelos endpoints /api/risk/*. Se falhar, o sistema funcionará com dados
    dos arquivos JSON como fallback.
    
    Returns:
        bool: True se pelo menos um componente foi inicializado, False caso contrário
    """
    global grid_risk_manager, emergency_sl, strategy, risk_components_initialized
    
    logger.info("🔧 Iniciando componentes de gerenciamento de risco...")
    
    try:
        # Importar módulos necessários
        from src.pacifica_auth import PacificaAuth
        from src.position_manager import PositionManager
        from src.grid_calculator import GridCalculator
        from src.grid_risk_manager import GridRiskManager
        from src.emergency_sl_system import EmergencyStopLoss
        from src.multi_asset_enhanced_strategy import MultiAssetEnhancedStrategy
        
        success_count = 0
        
        # 1. Inicializar componentes básicos
        logger.info("📡 Inicializando PacificaAuth...")
        auth_client = PacificaAuth()
        
        logger.info("💼 Inicializando PositionManager...")
        position_manager = PositionManager(auth_client)
        
        logger.info("🧮 Inicializando GridCalculator...")
        calculator = GridCalculator(auth_client)
        
        # 2. Grid Risk Manager (essencial)
        try:
            logger.info("🛡️ Inicializando GridRiskManager...")
            grid_risk_manager = GridRiskManager(
                auth_client=auth_client,
                position_manager=position_manager,
                telegram_notifier=None,  # Telegram não é necessário para o dashboard
                logger=logger
            )
            logger.info("✅ GridRiskManager inicializado com sucesso")
            success_count += 1
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar GridRiskManager: {e}")
            logger.debug(traceback.format_exc())
        
        # 3. Estratégia (opcional para dashboard)
        try:
            logger.info("🎯 Inicializando MultiAssetEnhancedStrategy...")
            strategy = MultiAssetEnhancedStrategy(
                auth_client=auth_client,
                calculator=calculator,
                position_manager=position_manager
            )
            logger.info("✅ MultiAssetEnhancedStrategy inicializada")
            success_count += 1
        except Exception as e:
            logger.warning(f"⚠️ Estratégia não inicializada (dashboard funciona sem ela): {e}")
            logger.debug(traceback.format_exc())
            strategy = None
        
        # 4. Emergency Stop Loss
        try:
            logger.info("🚨 Inicializando EmergencyStopLoss...")
            emergency_logger = strategy.logger if strategy and hasattr(strategy, 'logger') else logger
            emergency_sl = EmergencyStopLoss(
                auth_client=auth_client,
                position_manager=position_manager,
                logger=emergency_logger
            )
            logger.info("✅ EmergencyStopLoss inicializado")
            success_count += 1
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar EmergencyStopLoss: {e}")
            logger.debug(traceback.format_exc())
        
        # Atualizar flag de inicialização
        if success_count > 0:
            risk_components_initialized = True
            logger.info(f"🎉 Painel de risco inicializado: {success_count}/3 componentes OK")
            logger.info("✅ Dashboard operará com dados em tempo real dos componentes")
            return True
        else:
            risk_components_initialized = False
            logger.error("❌ Falha ao inicializar componentes de risco")
            logger.info("ℹ️ Dashboard operará com fallback (arquivos JSON)")
            return False
            
    except ImportError as e:
        logger.error(f"❌ Erro ao importar módulos: {e}")
        logger.info("ℹ️ Verifique se todos os arquivos src/*.py estão presentes")
        logger.debug(traceback.format_exc())
        risk_components_initialized = False
        return False
    except Exception as e:
        logger.error(f"❌ Erro inesperado ao inicializar componentes: {e}")
        logger.debug(traceback.format_exc())
        risk_components_initialized = False
        return False

# ========== FUNÇÕES DE DADOS (MANTIDAS + MELHORIAS) ==========

def get_metrics():
    """Obtém métricas de trading"""
    default_metrics = {
        "accumulated_pnl": 0,
        "cycles_closed": 0,
        "win_rate": 0,
        "initial_balance": 0,
        "current_balance": 0,
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "avg_win": 0,
        "avg_loss": 0,
        "largest_win": 0,
        "largest_loss": 0,
        "profit_factor": 0
    }
    
    data = safe_read_json_file(PNL_HISTORY_FILE, {})
    if not data:
        return default_metrics
    
    try:
        cycles = data.get("cycles_history", [])
        
        if cycles:
            wins = [c["pnl_usd"] for c in cycles if c.get("pnl_usd", 0) > 0]
            losses = [abs(c["pnl_usd"]) for c in cycles if c.get("pnl_usd", 0) < 0]
            
            win_rate = (len(wins) / len(cycles) * 100) if cycles else 0
            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            
            total_wins = sum(wins)
            total_losses = sum(losses)
            profit_factor = total_wins / total_losses if total_losses > 0 else 0
        else:
            win_rate = avg_win = avg_loss = profit_factor = 0
            wins = []
            losses = []
        
        return {
            "accumulated_pnl": data.get("accumulated_pnl", 0),
            "cycles_closed": len(cycles),
            "win_rate": round(win_rate, 1),
            "initial_balance": data.get("initial_balance", 0),
            "current_balance": data.get("current_balance", 0),
            "total_trades": len(cycles),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "largest_win": round(max(wins), 2) if wins else 0,
            "largest_loss": round(max(losses), 2) if losses else 0,
            "profit_factor": round(profit_factor, 2)
        }
    except Exception as e:
        logger.error(f"Erro ao processar métricas: {e}")
        return default_metrics

def get_pnl_history(hours=24):
    """Obtém histórico de PNL para gráficos"""
    data = safe_read_json_file(PNL_HISTORY_FILE, {})
    if not data:
        return []
    
    try:
        cycles = data.get("cycles_history", [])
        cutoff = datetime.now() - timedelta(hours=hours)
        
        pnl_series = []
        accumulated = 0
        
        for cycle in cycles:
            timestamp = cycle.get("timestamp", "")
            if not timestamp:
                continue
            
            try:
                cycle_time = datetime.fromisoformat(timestamp)
                if cycle_time < cutoff:
                    continue
            except:
                continue
            
            accumulated += cycle.get("pnl_usd", 0)
            pnl_series.append({
                "timestamp": timestamp,
                "pnl": round(cycle.get("pnl_usd", 0), 2),
                "accumulated": round(accumulated, 2),
                "symbol": cycle.get("symbol", ""),
                "reason": cycle.get("reason", "")
            })
        
        return pnl_series
    except Exception as e:
        logger.error(f"Erro ao obter histórico PNL: {e}")
        return []

def get_trades_history(limit=100):
    """Obtém histórico de trades"""
    data = safe_read_json_file(PNL_HISTORY_FILE, {})
    if not data:
        return []
    
    try:
        cycles = data.get("cycles_history", [])
        trades = sorted(cycles, key=lambda x: x.get("timestamp", ""), reverse=True)
        return trades[:limit]
    except Exception as e:
        logger.error(f"Erro ao obter histórico de trades: {e}")
        return []

# ========== NOVAS FUNÇÕES: POSIÇÕES E ORDENS ==========

def get_active_positions():
    """Obtém posições ativas do arquivo ou API"""
    data = safe_read_json_file(POSITIONS_FILE, {})
    if not data:
        return []
    
    try:
        positions = data.get("positions", [])
        
        # Enriquecer com dados calculados
        for pos in positions:
            # Calcular tempo ativo
            if "open_time" in pos:
                try:
                    open_time = datetime.fromisoformat(pos["open_time"])
                    duration = datetime.now() - open_time
                    pos["duration_minutes"] = int(duration.total_seconds() / 60)
                    pos["duration_str"] = format_duration(duration.total_seconds())
                except:
                    pos["duration_minutes"] = 0
                    pos["duration_str"] = "-"
            
            # Calcular PNL estimado se tiver preço atual
            if "entry_price" in pos and "current_price" in pos and "size" in pos:
                entry = float(pos.get("entry_price", 0))
                current = float(pos.get("current_price", 0))
                size = float(pos.get("size", 0))
                side = pos.get("side", "long").lower()
                
                if side in ["long", "buy"]:
                    pnl = (current - entry) * size
                else:
                    pnl = (entry - current) * size
                
                pos["pnl_usd"] = round(pnl, 2)
                pos["pnl_percent"] = round((pnl / (entry * size)) * 100, 2) if entry > 0 else 0
            else:
                pos["pnl_usd"] = 0
                pos["pnl_percent"] = 0
        
        return positions
    except Exception as e:
        logger.error(f"Erro ao obter posições: {e}")
        return []

def get_active_orders():
    """Obtém ordens abertas do arquivo ou API"""
    data = safe_read_json_file(ORDERS_FILE, {})
    if not data:
        return []
    
    try:
        orders = data.get("orders", [])
        
        # Enriquecer com tempo ativo
        for order in orders:
            if "create_time" in order:
                try:
                    create_time = datetime.fromisoformat(order["create_time"])
                    duration = datetime.now() - create_time
                    order["age_minutes"] = int(duration.total_seconds() / 60)
                    order["age_str"] = format_duration(duration.total_seconds())
                except:
                    order["age_minutes"] = 0
                    order["age_str"] = "-"
        
        return orders
    except Exception as e:
        logger.error(f"Erro ao obter ordens: {e}")
        return []

def format_duration(seconds):
    """Formata duração em formato legível"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"
    else:
        days = int(seconds / 86400)
        hours = int((seconds % 86400) / 3600)
        return f"{days}d {hours}h"

# ========== FUNÇÕES DE LOGS ==========

def tail_logs(lines=100):
    """Obtém últimas linhas dos logs"""
    log_files = sorted(LOGS_DIR.glob("*.log"), key=os.path.getmtime, reverse=True)
    
    if not log_files:
        return {"logs": ["Nenhum log encontrado"], "file": None}
    
    log_file = log_files[0]
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]
            return {"logs": [line.rstrip() for line in last_lines], "file": log_file.name}
    except Exception as e:
        logger.error(f"Erro ao ler logs: {e}")
        return {"logs": [f"Erro ao ler logs: {e}"], "file": None}

def read_env():
    """Lê arquivo .env com encoding UTF-8"""
    if not ENV_FILE.exists():
        return {}
    
    config = {}
    try:
        with open(ENV_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
        
        return config
    except Exception as e:
        logger.error(f"Erro ao ler .env: {e}")
        return {}

def update_env(updates):
    """Atualiza arquivo .env com encoding UTF-8"""
    if not ENV_FILE.exists():
        return {"status": "error", "message": "Arquivo .env não encontrado"}
    
    try:
        with open(ENV_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        new_lines = []
        updated_keys = set()
        
        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                key = line.split('=')[0].strip()
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}\n")
                    updated_keys.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        for key, value in updates.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={value}\n")
        
        with open(ENV_FILE, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        socketio.emit('alert', {
            'type': 'success',
            'message': '✅ Configurações salvas com sucesso',
            'timestamp': datetime.now().isoformat()
        })
        
        return {"status": "success", "message": "Configurações atualizadas"}
    except Exception as e:
        logger.error(f"Erro ao atualizar .env: {e}")
        return {"status": "error", "message": str(e)}

# ========== FUNÇÕES DE EXPORT ==========

def export_csv():
    """Exporta relatório em CSV"""
    try:
        trades = get_trades_history(limit=1000)
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Timestamp', 'Symbol', 'PNL USD', 'PNL %', 'Duration (min)', 'Reason', 'Accumulated PNL'])
        
        for trade in trades:
            writer.writerow([
                trade.get('timestamp', ''),
                trade.get('symbol', ''),
                trade.get('pnl_usd', 0),
                trade.get('pnl_percent', 0),
                trade.get('duration_minutes', 0),
                trade.get('reason', ''),
                trade.get('accumulated_pnl', 0)
            ])
        
        output.seek(0)
        return output.getvalue()
    except Exception as e:
        logger.error(f"Erro ao exportar CSV: {e}")
        return None

# ========== MONITOR THREADS ==========

def monitor_bot():
    """Thread que monitora o bot e envia updates via WebSocket"""
    global monitor_active
    logger.info("🔄 Monitor thread iniciada")
    
    last_metrics = None
    last_status = None
    
    while monitor_active:
        try:
            # Status do bot
            status = get_bot_status()
            if status != last_status:
                socketio.emit('bot_status_update', status)
                last_status = status
            
            # Métricas
            metrics = get_metrics()
            if metrics != last_metrics:
                socketio.emit('metrics_update', metrics)
                last_metrics = metrics
            
            # PNL History (últimas 24h)
            pnl_history = get_pnl_history(hours=24)
            socketio.emit('pnl_history_update', pnl_history)
            
            # Posições e Ordens
            positions = get_active_positions()
            socketio.emit('positions_update', positions)
            
            orders = get_active_orders()
            socketio.emit('orders_update', orders)
            
            time.sleep(3)
        except Exception as e:
            logger.error(f"Erro no monitor thread: {e}")
            time.sleep(5)
    
    logger.info("🛑 Monitor thread parada")

def monitor_logs():
    """Thread que monitora logs e envia updates via WebSocket"""
    global monitor_active
    logger.info("📜 Logs monitor thread iniciada")
    
    last_log_content = None
    
    while monitor_active:
        try:
            logs_data = tail_logs(lines=100)
            current_content = ''.join(logs_data['logs'])
            
            if current_content != last_log_content:
                socketio.emit('logs_update', logs_data)
                last_log_content = current_content
            
            time.sleep(3)
        except Exception as e:
            logger.error(f"Erro no logs monitor thread: {e}")
            time.sleep(5)
    
    logger.info("🛑 Logs monitor thread parada")

# ========== ROTAS HTTP BÁSICAS ==========

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/api/bot/status')
def api_bot_status():
    """API: Status do bot"""
    try:
        status = get_bot_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Erro em /api/bot/status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/bot/start', methods=['POST'])
def api_bot_start():
    """API: Iniciar bot"""
    try:
        result = start_bot()
        status_code = 200 if result["status"] == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Erro em /api/bot/start: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/bot/stop', methods=['POST'])
def api_bot_stop():
    """API: Parar bot"""
    try:
        force = request.json.get('force', False) if request.json else False
        result = stop_bot(force=force)
        status_code = 200 if result["status"] == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Erro em /api/bot/stop: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/bot/restart', methods=['POST'])
def api_bot_restart():
    """API: Reiniciar bot"""
    try:
        result = restart_bot()
        status_code = 200 if result["status"] == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Erro em /api/bot/restart: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/config')
def api_config():
    """API: Obter configurações"""
    try:
        config = read_env()
        return jsonify(config)
    except Exception as e:
        logger.error(f"Erro em /api/config: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/config/update', methods=['POST'])
def api_config_update():
    """API: Atualizar configurações"""
    try:
        updates = request.json
        result = update_env(updates)
        status_code = 200 if result["status"] == "success" else 400
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"Erro em /api/config/update: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/positions')
def api_positions():
    """API: Posições ativas"""
    try:
        positions = get_active_positions()
        return jsonify(positions)
    except Exception as e:
        logger.error(f"Erro em /api/positions: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/orders')
def api_orders():
    """API: Ordens abertas"""
    try:
        orders = get_active_orders()
        return jsonify(orders)
    except Exception as e:
        logger.error(f"Erro em /api/orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/account-state')
def api_account_state():
    """API: Estado da conta (saldo e margem)"""
    try:
        account_state = safe_read_json_file(DATA_DIR / "account_state.json", {
            "last_update": None,
            "balance": 0,
            "margin_used": 0,
            "margin_available": 0,
            "margin_free_percent": 0
        })
        
        return jsonify(account_state)
    except Exception as e:
        logger.error(f"Erro em /api/account-state: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/logs')
def api_logs():
    """API: Obtém logs do bot"""
    try:
        lines = request.args.get('lines', 100, type=int)
        log_data = tail_logs(lines)
        return jsonify(log_data)
    except Exception as e:
        logger.error(f"Erro em /api/logs: {e}")
        return jsonify({"error": str(e), "logs": [], "file": None}), 500

# ==========================================
# ✅ CORREÇÃO 2: ENDPOINTS DE RISCO MELHORADOS
# ==========================================

@app.route('/api/risk/status')
def get_risk_status():
    """
    ✅ MELHORADO: Retorna status consolidado do gerenciamento de risco
    Usa helper risk_error_response() para respostas consistentes
    """
    global grid_risk_manager, emergency_sl, strategy
    
    # Verificar se o bot está rodando
    status_file = 'bot_status.json'
    bot_running = os.path.exists(status_file)
    
    # Se bot não está rodando, retornar configurações do .env
    if not bot_running:
        logger.debug("Bot não está rodando - retornando configurações do .env")
        
        # Configurações do arquivo .env
        try:
            cycle_protection = os.getenv('ENABLE_CYCLE_PROTECTION', 'false').lower() == 'true'
            session_protection = os.getenv('ENABLE_SESSION_PROTECTION', 'false').lower() == 'true'
            
            cycle_sl = float(os.getenv('GRID_CYCLE_STOP_LOSS_PERCENT', '5.0'))
            cycle_tp = float(os.getenv('GRID_CYCLE_TAKE_PROFIT_PERCENT', '10.0'))
            
            session_max_loss = float(os.getenv('GRID_SESSION_MAX_LOSS_USD', '100.0'))
            session_profit_target = float(os.getenv('GRID_SESSION_PROFIT_TARGET_USD', '200.0'))
            
            emergency_sl_pct = float(os.getenv('EMERGENCY_SL_PERCENT', '15.0'))
            emergency_tp_pct = float(os.getenv('EMERGENCY_TP_PERCENT', '25.0'))
            
            action_on_limit = os.getenv('GRID_SESSION_ACTION_ON_LIMIT', 'PAUSE').upper()
            
            return jsonify({
                'bot_status': 'disconnected',
                'initialized': False,
                'cycle_protection': cycle_protection,
                'cycle_sl': cycle_sl,
                'cycle_tp': cycle_tp,
                'session_protection': session_protection,
                'session_max_loss_usd': session_max_loss,
                'session_profit_target_usd': session_profit_target,
                'action_on_limit': action_on_limit,
                'emergency_sl_percent': emergency_sl_pct,
                'emergency_tp_percent': emergency_tp_pct,
                'active_positions_count': 0,
                'accumulated_pnl': 0.0,
                'cycles_closed': 0,
                'cycles_profit': 0,
                'cycles_loss': 0,
                'session_start': 'Bot não iniciado',
                'last_check': datetime.now().strftime('%H:%M:%S'),
                'is_paused': False,
                'pause_until': None
            })
        except Exception as e:
            logger.error(f"Erro ao ler configurações do .env: {e}")
            return risk_error_response(
                f"Erro ao ler configurações: {e}",
                bot_status="disconnected"
            )
    
    # Bot rodando mas componentes não inicializados
    if not risk_components_initialized or not grid_risk_manager:
        logger.debug("Componentes de risco não inicializados - tentando fallback para arquivos JSON")
        
        # Tentar ler dados dos arquivos JSON como fallback
        try:
            pnl_data = safe_read_json_file(PNL_HISTORY_FILE, {})
            positions_data = safe_read_json_file(POSITIONS_FILE, {})
            
            # Configurações do .env
            cycle_protection = os.getenv('ENABLE_CYCLE_PROTECTION', 'false').lower() == 'true'
            session_protection = os.getenv('ENABLE_SESSION_PROTECTION', 'false').lower() == 'true'
            
            return jsonify({
                'bot_status': 'running_separate',
                'initialized': False,
                'message': 'Bot rodando em processo separado - dados limitados',
                'cycle_protection': cycle_protection,
                'cycle_sl': float(os.getenv('GRID_CYCLE_STOP_LOSS_PERCENT', '5.0')),
                'cycle_tp': float(os.getenv('GRID_CYCLE_TAKE_PROFIT_PERCENT', '10.0')),
                'session_protection': session_protection,
                'session_max_loss_usd': float(os.getenv('GRID_SESSION_MAX_LOSS_USD', '100.0')),
                'session_profit_target_usd': float(os.getenv('GRID_SESSION_PROFIT_TARGET_USD', '200.0')),
                'accumulated_pnl': pnl_data.get('accumulated_pnl', 0.0),
                'cycles_closed': pnl_data.get('cycles_closed', 0),
                'active_positions_count': len(positions_data.get('positions', [])),
                'last_check': datetime.now().strftime('%H:%M:%S')
            })
        except Exception as e:
            logger.error(f"Erro ao ler arquivos de fallback: {e}")
            return risk_error_response(
                "Bot rodando mas componentes não disponíveis via Flask",
                bot_status="running_separate"
            )
    
    # Componentes inicializados - retornar dados completos
    try:
        # Coletar dados detalhados dos componentes
        accumulated_pnl = grid_risk_manager.accumulated_pnl
        accumulated_pnl_percent = 0
        if grid_risk_manager.initial_balance > 0:
            accumulated_pnl_percent = (accumulated_pnl / grid_risk_manager.initial_balance) * 100

        # Cálculos de limites
        limits_analysis = {}
        
        if grid_risk_manager.enable_session_protection:
            remaining_loss_usd = abs(grid_risk_manager.session_max_loss_usd) - abs(accumulated_pnl)
            loss_percentage_used = (abs(accumulated_pnl) / abs(grid_risk_manager.session_max_loss_usd)) * 100 if grid_risk_manager.session_max_loss_usd != 0 else 0
            
            remaining_loss_percent = grid_risk_manager.session_max_loss_percent - abs(accumulated_pnl_percent)
            
            remaining_profit_usd = grid_risk_manager.session_profit_target_usd - accumulated_pnl
            profit_percentage_reached = (accumulated_pnl / grid_risk_manager.session_profit_target_usd) * 100 if grid_risk_manager.session_profit_target_usd != 0 else 0
            
            remaining_profit_percent = grid_risk_manager.session_profit_target_percent - accumulated_pnl_percent
            
            limits_analysis = {
                "stop_loss_usd": {
                    "limit": -grid_risk_manager.session_max_loss_usd,
                    "current": accumulated_pnl,
                    "remaining": remaining_loss_usd,
                    "percentage_used": loss_percentage_used,
                    "is_safe": accumulated_pnl > -grid_risk_manager.session_max_loss_usd
                },
                "stop_loss_percent": {
                    "limit": -grid_risk_manager.session_max_loss_percent,
                    "current": accumulated_pnl_percent,
                    "remaining": remaining_loss_percent,
                    "is_safe": accumulated_pnl_percent > -grid_risk_manager.session_max_loss_percent
                },
                "take_profit_usd": {
                    "target": grid_risk_manager.session_profit_target_usd,
                    "current": accumulated_pnl,
                    "remaining": remaining_profit_usd,
                    "percentage_reached": profit_percentage_reached,
                    "is_achieved": accumulated_pnl >= grid_risk_manager.session_profit_target_usd
                },
                "take_profit_percent": {
                    "target": grid_risk_manager.session_profit_target_percent,
                    "current": accumulated_pnl_percent,
                    "remaining": remaining_profit_percent,
                    "is_achieved": accumulated_pnl_percent >= grid_risk_manager.session_profit_target_percent
                }
            }

        # Win rate
        win_rate = 0
        if grid_risk_manager.cycles_closed > 0:
            win_rate = (grid_risk_manager.cycles_profit / grid_risk_manager.cycles_closed) * 100

        # Uptime
        uptime = datetime.now() - grid_risk_manager.session_start
        uptime_str = f"{int(uptime.total_seconds() // 3600)}h {int((uptime.total_seconds() % 3600) // 60)}m"

        # Estatísticas do EmergencyStopLoss
        emergency_stats = {}
        if emergency_sl:
            try:
                emergency_stats = emergency_sl.get_statistics()
            except Exception as e:
                logger.warning(f"Erro ao obter estatísticas do EmergencyStopLoss: {e}")

        status = {
            "initialized": True,
            "bot_status": "connected",
            "timestamp": datetime.now().isoformat(),
            "last_check": datetime.now().strftime("%H:%M:%S"),
            
            # Configurações de Proteção
            "protection_config": {
                "cycle_protection_enabled": grid_risk_manager.enable_cycle_protection,
                "cycle_sl_percent": grid_risk_manager.cycle_stop_loss_percent,
                "cycle_tp_percent": grid_risk_manager.cycle_take_profit_percent,
                "session_protection_enabled": grid_risk_manager.enable_session_protection,
                "action_on_limit": grid_risk_manager.action_on_limit,
                "pause_duration_minutes": getattr(grid_risk_manager, 'pause_duration_minutes', 120)
            },
            
            # Status da Sessão
            "session_status": {
                "is_paused": grid_risk_manager.is_paused,
                "pause_until": grid_risk_manager.pause_until.isoformat() if grid_risk_manager.pause_until else None,
                "pause_reason": getattr(grid_risk_manager, 'pause_reason', None),
                "session_start": grid_risk_manager.session_start.isoformat(),
                "uptime": uptime_str,
                "initial_balance": grid_risk_manager.initial_balance,
                "current_cycle_id": grid_risk_manager.current_cycle_id
            },
            
            # PNL e Performance
            "performance": {
                "accumulated_pnl_usd": accumulated_pnl,
                "accumulated_pnl_percent": accumulated_pnl_percent,
                "cycles_closed": grid_risk_manager.cycles_closed,
                "cycles_profit": grid_risk_manager.cycles_profit,
                "cycles_loss": grid_risk_manager.cycles_loss,
                "win_rate": win_rate
            },
            
            # Análise Detalhada de Limites
            "limits_analysis": limits_analysis,
            
            # Emergency Stop Loss
            "emergency_system": {
                "enabled": True,
                "sl_percent": emergency_sl.emergency_sl_percent if emergency_sl else 0,
                "tp_percent": getattr(emergency_sl, 'emergency_tp_percent', 0) if emergency_sl else 0,
                "statistics": emergency_stats
            },
            
            # Posições Ativas
            "positions": {
                "active_count": len(strategy.active_positions) if strategy and hasattr(strategy, 'active_positions') else 0,
                "max_concurrent": getattr(strategy, 'max_concurrent_trades', 0) if strategy else 0
            }
        }
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Erro no endpoint /api/risk/status: {e}")
        logger.debug(traceback.format_exc())
        return risk_error_response(
            f"Erro ao coletar dados de risco: {str(e)}",
            bot_status="error",
            http_code=500
        )

@app.route('/api/risk/positions')
def get_risk_positions_monitor():
    """
    ✅ MELHORADO: Monitoramento detalhado de risco por posição
    Sistema de fallback robusto para leitura de arquivos
    """
    global grid_risk_manager, emergency_sl, strategy
    
    try:
        # Verificar se o bot está rodando
        status_file = 'bot_status.json'
        bot_running = os.path.exists(status_file)
        
        if not bot_running:
            return jsonify({
                "bot_status": "disconnected",
                "positions": [],
                "message": "Bot não está rodando - inicie com: python grid_bot.py"
            })
        
        # Se componentes não estão disponíveis, usar arquivos JSON
        if not risk_components_initialized or not grid_risk_manager or not emergency_sl:
            logger.debug("Usando fallback - lendo dados dos arquivos JSON")
            
            # Ler posições ativas do arquivo
            active_positions_file = DATA_DIR / "active_positions.json"
            pnl_history_file = DATA_DIR / "grid_pnl_history.json"
            
            positions_data = []
            
            if active_positions_file.exists() and pnl_history_file.exists():
                active_data = safe_read_json_file(active_positions_file, {})
                pnl_data = safe_read_json_file(pnl_history_file, {})
                
                if active_data.get('positions'):
                    for pos in active_data['positions']:
                        positions_data.append({
                            "symbol": pos.get('symbol', 'UNKNOWN'),
                            "side": pos.get('side', 'unknown'),
                            "quantity": pos.get('size', 0),
                            "entry_price": pos.get('entry_price', 0),
                            "current_price": pos.get('current_price', 0),
                            "pnl_usd": pos.get('pnl_usd', 0),
                            "pnl_percent": pos.get('pnl_percent', 0),
                            "leverage": pos.get('leverage', 1),
                            "overall_risk_level": 1  # Fallback seguro
                        })
                
                return jsonify({
                    "bot_status": "running_separate",
                    "message": "✅ Bot rodando - dados dos arquivos (componentes em processo separado)",
                    "positions": positions_data,
                    "session_info": {
                        "balance_inicial": pnl_data.get('initial_balance', 0),
                        "pnl_acumulado": pnl_data.get('accumulated_pnl', 0),
                        "ciclos_fechados": pnl_data.get('cycles_closed', 0),
                        "ultima_atualizacao": active_data.get('last_update', 'N/A')
                    }
                })
            
            return jsonify({
                "bot_status": "running_separate",
                "positions": [],
                "message": "Bot rodando - aguardando dados de posições"
            })
        
        # Componentes disponíveis - processar posições com dados completos
        positions_data = []
        
        # Configurações de risco (definir antes do loop)
        cycle_sl_limit = grid_risk_manager.cycle_stop_loss_percent
        cycle_tp_limit = grid_risk_manager.cycle_take_profit_percent
        emergency_sl_limit = emergency_sl.emergency_sl_percent
        emergency_tp_limit = getattr(emergency_sl, 'emergency_tp_percent', 5.0)
        session_pnl = grid_risk_manager.accumulated_pnl
        session_max_loss = grid_risk_manager.session_max_loss_usd
        session_profit_target = grid_risk_manager.session_profit_target_usd
        
        # Obter posições ativas
        active_positions = {}
        if strategy and hasattr(strategy, 'active_positions'):
            active_positions = strategy.active_positions
        
        # Se não tiver do strategy, tentar API
        if not active_positions:
            try:
                positions_response = get_active_positions()
                for pos in positions_response:
                    if pos.get('size', 0) != 0:
                        symbol = pos.get('symbol', 'UNKNOWN')
                        active_positions[symbol] = {
                            'quantity': pos.get('size', 0),
                            'entry_price': pos.get('entry_price', 0),
                            'current_price': pos.get('mark_price', 0),
                            'pnl': pos.get('unrealized_pnl', 0),
                            'side': 'long' if pos.get('size', 0) > 0 else 'short'
                        }
            except Exception as e:
                logger.warning(f"Erro ao obter posições via API: {e}")
        
        # Processar cada posição com análise de risco completa
        for symbol, position in active_positions.items():
            
            quantity = position.get('quantity', 0)
            entry_price = position.get('entry_price', 0)
            current_price = position.get('current_price', 0)
            pnl_usd = position.get('pnl', 0)
            
            pnl_percent = 0
            if entry_price > 0:
                if quantity > 0:
                    pnl_percent = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_percent = ((entry_price - current_price) / entry_price) * 100
            
            # Usar configurações de risco já definidas acima
            
            # Status dos níveis
            cycle_sl_status = "safe"
            cycle_tp_status = "safe"
            emergency_status = "safe"
            
            if abs(pnl_percent) > cycle_sl_limit * 0.8:
                cycle_sl_status = "critical"
            elif abs(pnl_percent) > cycle_sl_limit * 0.6:
                cycle_sl_status = "warning"
            
            if pnl_percent > cycle_tp_limit * 0.8:
                cycle_tp_status = "near_target"
            elif pnl_percent > cycle_tp_limit * 0.6:
                cycle_tp_status = "approaching"
            
            if abs(pnl_percent) > emergency_sl_limit * 0.9:
                emergency_status = "critical"
            elif abs(pnl_percent) > emergency_sl_limit * 0.7:
                emergency_status = "warning"
            
            # PNL de sessão já definidos acima
            
            position_data = {
                "symbol": symbol,
                "side": "long" if quantity > 0 else "short",
                "quantity": abs(quantity),
                "entry_price": entry_price,
                "current_price": current_price,
                "pnl_usd": pnl_usd,
                "pnl_percent": pnl_percent,
                
                # Nível 1 - Proteção por Ciclo
                "cycle_protection": {
                    "stop_loss": {
                        "current_percent": pnl_percent if pnl_percent < 0 else 0,
                        "limit_percent": -cycle_sl_limit,
                        "remaining_percent": cycle_sl_limit - abs(pnl_percent) if pnl_percent < 0 else cycle_sl_limit,
                        "status": cycle_sl_status,
                        "triggered": abs(pnl_percent) >= cycle_sl_limit and pnl_percent < 0
                    },
                    "take_profit": {
                        "current_percent": pnl_percent if pnl_percent > 0 else 0,
                        "target_percent": cycle_tp_limit,
                        "remaining_percent": cycle_tp_limit - pnl_percent if pnl_percent > 0 else cycle_tp_limit,
                        "status": cycle_tp_status,
                        "triggered": pnl_percent >= cycle_tp_limit
                    }
                },
                
                # Nível 2 - Proteção de Sessão
                "session_protection": {
                    "current_session_pnl": session_pnl,
                    "max_loss_limit": -session_max_loss,
                    "profit_target": session_profit_target,
                    "position_contribution": pnl_usd,
                    "remaining_loss_buffer": session_max_loss - abs(session_pnl) if session_pnl < 0 else session_max_loss
                },
                
                # Nível 3 - Emergency System
                "emergency_system": {
                    "emergency_sl": {
                        "current_percent": pnl_percent if pnl_percent < 0 else 0,
                        "limit_percent": -emergency_sl_limit,
                        "status": emergency_status,
                        "triggered": abs(pnl_percent) >= emergency_sl_limit and pnl_percent < 0
                    },
                    "emergency_tp": {
                        "current_percent": pnl_percent if pnl_percent > 0 else 0,
                        "limit_percent": emergency_tp_limit,
                        "triggered": pnl_percent >= emergency_tp_limit
                    },
                    "time_monitoring": {
                        "time_in_loss_minutes": 0,
                        "max_time_minutes": getattr(emergency_sl, 'max_time_in_loss_minutes', 15),
                        "status": "safe"
                    }
                },
                
                # Metadata
                "last_update": datetime.now().isoformat(),
                "overall_risk_level": max([
                    1 if cycle_sl_status == "safe" else (2 if cycle_sl_status == "warning" else 3),
                    1 if emergency_status == "safe" else (2 if emergency_status == "warning" else 3)
                ])
            }
            
            positions_data.append(position_data)
        
        return jsonify({
            "bot_status": "connected",
            "positions": positions_data,
            "total_positions": len(positions_data),
            "last_update": datetime.now().isoformat(),
            "risk_config": {
                "cycle_sl_percent": cycle_sl_limit,
                "cycle_tp_percent": cycle_tp_limit,
                "emergency_sl_percent": emergency_sl_limit,
                "emergency_tp_percent": emergency_tp_limit,
                "session_max_loss_usd": session_max_loss,
                "session_profit_target_usd": session_profit_target
            }
        })
        
    except Exception as e:
        logger.error(f"Erro no endpoint /api/risk/positions: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "error": str(e),
            "bot_status": "error",
            "positions": []
        }), 500

# ✅ CORREÇÃO 5: Endpoint /risk_status readicionado para compatibilidade
@app.route('/risk_status')
def risk_status_compat():
    """Endpoint de compatibilidade - usa a mesma função do /api/risk/status"""
    return get_risk_status()

# ==========================================
# ENDPOINTS DE TELEMETRIA DE RISCO
# ==========================================

# Endpoints de telemetria de risco
@app.route('/api/risk/telemetry/status')
def risk_telemetry_status():
    p = Path("data/risk/status.json")
    return jsonify(json.loads(p.read_text(encoding='utf-8'))) if p.exists() else jsonify({})

@app.route('/api/risk/telemetry/active')
def risk_telemetry_active_trade():
    p = Path("data/risk/active_trade.json")
    return jsonify(json.loads(p.read_text(encoding='utf-8'))) if p.exists() else jsonify({"active": False})

@app.route('/api/risk/telemetry/history')
def risk_telemetry_history_list():
    td = Path("data/risk/trades")
    if not td.exists():
        return jsonify([])
    files = sorted(td.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:50]
    data = []
    for f in files:
        try:
            data.append(json.loads(f.read_text(encoding='utf-8')))
        except Exception:
            continue
    return jsonify(data)

# ==========================================
# ROTAS DE VOLUME TRACKER (MANTIDAS)
# ==========================================

@app.route('/api/volume/stats')
def api_volume_stats():
    """API: Estatísticas de volume por período"""
    try:
        periods = request.args.get('periods', '1h,24h,7d,14d')
        periods_list = [p.strip() for p in periods.split(',')]
        
        tracker = get_volume_tracker()
        if not tracker:
            return jsonify({
                "error": "VolumeTracker não disponível. Verifique MAIN_PUBLIC_KEY no .env"
            }), 500
        
        stats = tracker.get_volume_stats(periods_list)
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Erro em /api/volume/stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/volume/timeline')
def api_volume_timeline():
    """API: Timeline de volume"""
    try:
        hours_back = request.args.get('hours', 24, type=int)
        interval_minutes = request.args.get('interval', 60, type=int)
        
        tracker = get_volume_tracker()
        if not tracker:
            return jsonify({
                "error": "VolumeTracker não disponível"
            }), 500
        
        timeline = tracker.get_volume_timeline(
            hours_back=hours_back,
            interval_minutes=interval_minutes
        )
        
        return jsonify(timeline)
        
    except Exception as e:
        logger.error(f"Erro em /api/volume/timeline: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/volume/comparison')
def api_volume_comparison():
    """API: Comparação de volume com período anterior"""
    try:
        period = request.args.get('period', '24h')
        
        tracker = get_volume_tracker()
        if not tracker:
            return jsonify({"error": "VolumeTracker não disponível"}), 500
        
        current_stats = tracker.get_volume_stats([period])
        current = current_stats.get(period, {})
        
        period_map = {
            '1h': 1,
            '24h': 24,
            '7d': 168,
            '14d': 336
        }
        
        hours_back = period_map.get(period, 24)
        
        now = datetime.now()
        end_previous = now - timedelta(hours=hours_back)
        start_previous = end_previous - timedelta(hours=hours_back)
        
        previous_trades = tracker.get_trades_history(
            start_time=int(start_previous.timestamp() * 1000),
            end_time=int(end_previous.timestamp() * 1000),
            limit=10000
        )
        
        previous = tracker.calculate_volume(previous_trades)
        
        current_volume = current.get('total_volume', 0)
        previous_volume = previous.get('total_volume', 0)
        
        if previous_volume > 0:
            change_percent = ((current_volume - previous_volume) / previous_volume) * 100
        else:
            change_percent = 0
        
        return jsonify({
            "period": period,
            "current": current,
            "previous": previous,
            "change_percent": round(change_percent, 2),
            "change_absolute": round(current_volume - previous_volume, 2)
        })
        
    except Exception as e:
        logger.error(f"Erro em /api/volume/comparison: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/trades')
def api_trades():
    """API: Histórico de trades"""
    try:
        limit = request.args.get('limit', 50, type=int)
        
        tracker = get_volume_tracker()
        if not tracker:
            logger.warning("⚠️ VolumeTracker não disponível")
            return jsonify([])
        
        now = datetime.now()
        start_time = now - timedelta(days=30)
        
        trades_raw = tracker.get_trades_history(
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(now.timestamp() * 1000),
            limit=10000
        )
        
        if not trades_raw:
            logger.info("📊 Nenhum trade encontrado")
            return jsonify([])
        
        trades_formatted = []
        accumulated_pnl = 0
        
        for trade in trades_raw:
            created_at = trade.get("created_at", 0)
            timestamp = datetime.fromtimestamp(created_at / 1000).isoformat() if created_at else ""
            
            amount = float(trade.get("amount", 0))
            entry_price = float(trade.get("entry_price", 0))
            pnl_raw = trade.get("pnl", "0")
            
            try:
                pnl_usd = float(pnl_raw)
            except (ValueError, TypeError):
                pnl_usd = 0
            
            accumulated_pnl += pnl_usd
            
            invested = amount * entry_price
            pnl_percent = (pnl_usd / invested * 100) if invested > 0 else 0
            
            trades_formatted.append({
                "timestamp": timestamp,
                "symbol": trade.get("symbol", ""),
                "pnl_usd": pnl_usd,
                "pnl_percent": pnl_percent,
                "duration_minutes": 0,
                "reason": trade.get("side", ""),
                "accumulated_pnl": accumulated_pnl
            })
        
        trades_formatted.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return jsonify(trades_formatted[:limit])
        
    except Exception as e:
        logger.error(f"Erro em /api/trades: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/pnl-history')
def api_pnl_history():
    """API: Histórico de PnL do grid"""
    try:
        hours = request.args.get('hours', 24, type=int)
        
        pnl_file = DATA_DIR / "grid_pnl_history.json"
        
        if not pnl_file.exists():
            return jsonify({
                "session_start": None,
                "initial_balance": 0,
                "current_balance": 0,
                "accumulated_pnl": 0,
                "cycles_closed": 0,
                "cycles_history": [],
                "last_update": None
            })
        
        with open(pnl_file, 'r', encoding='utf-8') as f:
            pnl_data = json.load(f)
        
        cycles_history = pnl_data.get('cycles_history', [])
        if hours and cycles_history:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            cutoff_timestamp = cutoff_time.timestamp()
            
            filtered_cycles = [
                cycle for cycle in cycles_history 
                if cycle.get('timestamp', 0) >= cutoff_timestamp
            ]
            pnl_data['cycles_history'] = filtered_cycles
        
        return jsonify(pnl_data)
        
    except Exception as e:
        logger.error(f"Erro em /api/pnl-history: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/export/csv')
def api_export_csv():
    """API: Exportar CSV"""
    try:
        csv_data = export_csv()
        if csv_data:
            return Response(
                csv_data,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=pacifica_bot_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'}
            )
        return jsonify({"error": "Erro ao gerar CSV"}), 500
    except Exception as e:
        logger.error(f"Erro em /api/export/csv: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# ROTAS CSV (MANTIDAS)
# ==========================================

def allowed_file(filename):
    """Verifica se arquivo tem extensão permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_latest_csv_analysis():
    """Obtém a última análise de CSV salva"""
    try:
        analysis_file = DATA_DIR / "csv_trades_analysis.json"
        if analysis_file.exists():
            with open(analysis_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    except Exception as e:
        logger.error(f"Erro ao ler análise CSV: {e}")
        return None

def process_uploaded_csv(file_path: str):
    """Processa arquivo CSV e retorna estatísticas"""
    try:
        parser = PacificaCSVParser(file_path)
        parser.parse_csv()
        stats = parser.get_statistics()
        parser.save_to_json()
        logger.info(f"✅ CSV processado: {Path(file_path).name}")
        return stats
    except Exception as e:
        logger.error(f"❌ Erro ao processar CSV: {e}")
        return None

@app.route('/api/csv/upload', methods=['POST'])
def api_csv_upload():
    """API: Upload e análise de arquivo CSV"""
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "Nenhum arquivo enviado"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "Nenhum arquivo selecionado"}), 400
        
        if not allowed_file(file.filename):
            return jsonify({"status": "error", "message": "Apenas arquivos CSV são permitidos"}), 400
        
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_filename = f"pacifica_{timestamp}_{filename}"
        file_path = Path(app.config['UPLOAD_FOLDER']) / new_filename
        
        file.save(str(file_path))
        logger.info(f"📁 Arquivo salvo: {new_filename}")
        
        stats = process_uploaded_csv(str(file_path))
        
        if stats:
            return jsonify({
                "status": "success",
                "message": f"CSV processado com sucesso: {stats['summary']['total_trades']} trades",
                "filename": new_filename,
                "stats": stats
            })
        else:
            return jsonify({"status": "error", "message": "Erro ao processar CSV"}), 500
    except Exception as e:
        logger.error(f"Erro em /api/csv/upload: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/csv/analysis')
def api_csv_analysis():
    """API: Obter última análise de CSV"""
    try:
        analysis = get_latest_csv_analysis()
        if analysis:
            return jsonify({"status": "success", "data": analysis})
        else:
            return jsonify({"status": "error", "message": "Nenhuma análise disponível"}), 404
    except Exception as e:
        logger.error(f"Erro em /api/csv/analysis: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/csv/list')
def api_csv_list():
    """API: Listar arquivos CSV disponíveis"""
    try:
        data_csvs = list(DATA_DIR.glob("pacifica*.csv"))
        upload_csvs = list(Path(app.config['UPLOAD_FOLDER']).glob("*.csv"))
        all_csvs = data_csvs + upload_csvs
        
        csv_list = []
        for csv_file in sorted(all_csvs, key=lambda p: p.stat().st_mtime, reverse=True):
            stat = csv_file.stat()
            csv_list.append({
                'filename': csv_file.name,
                'path': str(csv_file),
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        
        return jsonify({"status": "success", "files": csv_list, "count": len(csv_list)})
    except Exception as e:
        logger.error(f"Erro em /api/csv/list: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/csv/analyze/<filename>')
def api_csv_analyze_file(filename):
    """API: Analisar arquivo CSV específico"""
    try:
        file_path = None
        data_file = DATA_DIR / filename
        if data_file.exists():
            file_path = data_file
        else:
            upload_file = Path(app.config['UPLOAD_FOLDER']) / filename
            if upload_file.exists():
                file_path = upload_file
        
        if not file_path:
            return jsonify({"status": "error", "message": f"Arquivo não encontrado: {filename}"}), 404
        
        stats = process_uploaded_csv(str(file_path))
        if stats:
            return jsonify({"status": "success", "data": stats})
        else:
            return jsonify({"status": "error", "message": "Erro ao processar CSV"}), 500
    except Exception as e:
        logger.error(f"Erro em /api/csv/analyze/{filename}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/csv/delete/<filename>', methods=['DELETE'])
def api_csv_delete(filename):
    """API: Deletar arquivo CSV"""
    try:
        file_path = Path(app.config['UPLOAD_FOLDER']) / secure_filename(filename)
        if not file_path.exists():
            return jsonify({"status": "error", "message": f"Arquivo não encontrado: {filename}"}), 404
        
        file_path.unlink()
        logger.info(f"🗑️ Arquivo deletado: {filename}")
        return jsonify({"status": "success", "message": f"Arquivo deletado: {filename}"})
    except Exception as e:
        logger.error(f"Erro em /api/csv/delete/{filename}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ========== WEBSOCKET EVENTS ==========

@socketio.on('connect')
def handle_connect():
    """Cliente conectado via WebSocket"""
    try:
        logger.info(f"🔌 Cliente conectado: {request.sid}")
        
        # Enviar status inicial
        status = get_bot_status()
        emit('bot_status_update', status)
        
        metrics = get_metrics()
        emit('metrics_update', metrics)
        
        pnl_history = get_pnl_history(hours=24)
        emit('pnl_history_update', pnl_history)
        
        positions = get_active_positions()
        emit('positions_update', positions)
        
        orders = get_active_orders()
        emit('orders_update', orders)
        
        logs = tail_logs(lines=100)
        emit('logs_update', logs)
        
    except Exception as e:
        logger.error(f"Erro ao conectar cliente WebSocket: {e}")
        emit('error', {'message': 'Erro na conexão'})

@socketio.on('disconnect')
def handle_disconnect():
    """Cliente desconectado"""
    try:
        logger.info(f"🔌 Cliente desconectado: {request.sid}")
    except Exception as e:
        logger.error(f"Erro ao desconectar cliente: {e}")

@socketio.on('request_update')
def handle_request_update():
    """Cliente solicitou atualização manual"""
    try:
        status = get_bot_status()
        emit('bot_status_update', status)
        
        metrics = get_metrics()
        emit('metrics_update', metrics)
        
        pnl_history = get_pnl_history(hours=24)
        emit('pnl_history_update', pnl_history)
        
        positions = get_active_positions()
        emit('positions_update', positions)
        
        orders = get_active_orders()
        emit('orders_update', orders)
        
        logs = tail_logs(lines=100)
        emit('logs_update', logs)
        
    except Exception as e:
        logger.error(f"Erro ao atualizar dados: {e}")
        emit('error', {'message': 'Erro na atualização'})

# ========== ✅ CORREÇÃO 1: INICIALIZAÇÃO NO STARTUP ==========

if __name__ == '__main__':
    print("="*80)
    print("🚀 Interface Web Melhorada v1.2 iniciando...")
    print("="*80)
    print("📊 Dashboard: http://localhost:5000")
    print("🔌 WebSocket: Ativado (polling)")
    print("📜 Logs: Auto-refresh ativado")
    print("📈 Posições: Monitoramento em tempo real")
    print("💹 Volume Tracker: Ativo")
    print("⚙️  Config: Salvamento + Auto-restart")
    print("🛡️  Risk Management: Sistema de fallback robusto")
    print("="*80)
    print(f"🐍 Python: {PYTHON_EXECUTABLE}")
    print("="*80)
    
    # Verificar arquivos necessários
    if not ENV_FILE.exists():
        print(f"⚠️  AVISO: Arquivo {ENV_FILE} não encontrado")
    
    if not Path(BOT_SCRIPT).exists():
        print(f"⚠️  AVISO: Arquivo {BOT_SCRIPT} não encontrado")
    
    # Criar pastas
    LOGS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    
    # ✅ CORREÇÃO 1: Inicializar componentes de risco
    print("="*80)
    print("🔧 Inicializando componentes de gerenciamento de risco...")
    print("="*80)
    
    risk_init_success = initialize_risk_components()
    
    if risk_init_success:
        print("="*80)
        print("✅ SUCESSO: Componentes de risco inicializados")
        print("   Dashboard operará com dados em tempo real")
        print("="*80)
    else:
        print("="*80)
        print("⚠️  AVISO: Componentes de risco não inicializados")
        print("   Dashboard operará com fallback (arquivos JSON)")
        print("   Funcionalidades básicas continuarão funcionando")
        print("="*80)
    
    # Iniciar monitor threads
    monitor_active = True
    monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
    monitor_thread.start()
    
    logs_monitor_thread = threading.Thread(target=monitor_logs, daemon=True)
    logs_monitor_thread.start()
    
    print("="*80)
    print("🛑 Para parar: Ctrl+C")
    print("="*80)
    
    # Rodar app com SocketIO
    try:
        socketio.run(
            app,
            debug=False,
            host='0.0.0.0',
            port=5000,
            allow_unsafe_werkzeug=True,
            use_reloader=False,
            log_output=False
        )
    except KeyboardInterrupt:
        print("\n\n🛑 Encerrando interface web...")
    finally:
        monitor_active = False
        if monitor_thread:
            monitor_thread.join(timeout=5)
        if logs_monitor_thread:
            logs_monitor_thread.join(timeout=5)
        print("👋 Interface web encerrada")
