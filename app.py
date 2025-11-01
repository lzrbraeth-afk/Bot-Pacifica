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

# ===== IMPORTS PARA MARKET VISION =====
from market_vision.market_vision_service import MarketVisionService

# ===== IMPORT VOLUME TRACKER =====
from src.volume_tracker import get_volume_tracker

# ===== IMPORT SYMBOLS CACHE =====
from src.cache import SymbolsCache

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
import shutil
import re
import signal
import threading
import time
import traceback
from io import StringIO, BytesIO
from dotenv import load_dotenv

# importas de credenciais seguras
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import json
import secrets
import hashlib

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

# Criar diretório de backups se não existir
Path('backups').mkdir(exist_ok=True)

# Inicializar bot_manager (será implementado se necessário)
bot_manager = None

# ===== INICIALIZAR CACHE DE SÍMBOLOS =====
symbols_cache = SymbolsCache(cache_duration_hours=24)

# ===== MARKET VISION SERVICE =====
market_vision_service = None

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

# ========== ✅ MARKET VISION: FUNÇÃO DE INICIALIZAÇÃO ==========

def init_market_vision():
    """Inicializa o Market Vision Service"""
    global market_vision_service
    
    try:
        # Importar componentes do bot
        from src.pacifica_auth import PacificaAuth
        from src.position_manager import PositionManager
        
        # Inicializar (usar credenciais já configuradas)
        logger.info("🎯 Inicializando Market Vision Service...")
        auth = PacificaAuth()
        pos_mgr = PositionManager(auth)
        
        market_vision_service = MarketVisionService(
            auth_client=auth,
            position_manager=pos_mgr,
            config={
                'use_multi_timeframe': True,  # Análise 5m, 15m, 1h
                'db_path': 'data/trade_decisions.db'
            }
        )
        
        logger.info("✅ Market Vision Service inicializado com sucesso")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar Market Vision: {e}")
        logger.debug(traceback.format_exc())
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

# Thread para atualizar Market Vision
def market_vision_update_loop():
    """Loop que atualiza análise do Market Vision a cada 30 segundos"""
    global monitor_active, market_vision_service
    logger.info("🎯 Market Vision update thread iniciada")
    
    while monitor_active:
        try:
            if market_vision_service:
                data = market_vision_service.get_dashboard_data('BTC')
                socketio.emit('market_vision_update', data)
            
            time.sleep(30)  # Atualizar a cada 30s
            
        except Exception as e:
            logger.error(f"Erro no market vision loop: {e}")
            time.sleep(60)
    
    logger.info("🛑 Market Vision update thread parada")

# ========== ROTAS HTTP BÁSICAS ==========

# ========== 1. GERAÇÃO E GERENCIAMENTO DE CHAVE DE CRIPTOGRAFIA ==========

def get_or_create_encryption_key():
    """Obtém ou cria chave mestra de criptografia"""
    key_file = Path('.encryption_key')
    
    if key_file.exists():
        with open(key_file, 'rb') as f:
            return f.read()
    
    # Gerar nova chave
    key = Fernet.generate_key()
    
    # Salvar com permissões restritas
    with open(key_file, 'wb') as f:
        f.write(key)
    
    # Definir permissões 600 (somente owner)
    key_file.chmod(0o600)
    
    logger.info("🔐 Nova chave de criptografia gerada")
    return key


def derive_key_from_password(password: str, salt: bytes = None) -> tuple:
    """Deriva chave de criptografia a partir de senha"""
    if salt is None:
        salt = secrets.token_bytes(32)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt


# ========== 2. FUNÇÕES DE CRIPTOGRAFIA ==========

def encrypt_credential(plaintext: str) -> str:
    """Criptografa credencial sensível"""
    try:
        key = get_or_create_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"❌ Erro ao criptografar: {e}")
        raise


def decrypt_credential(encrypted_text: str) -> str:
    """Descriptografa credencial"""
    try:
        key = get_or_create_encryption_key()
        f = Fernet(key)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_text.encode())
        decrypted = f.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"❌ Erro ao descriptografar: {e}")
        raise


# ========== 3. GERENCIAMENTO DE CREDENCIAIS ==========

def save_credentials_secure(credentials: dict) -> dict:
    """Salva credenciais de forma segura"""
    try:
        credentials_file = Path('.credentials_secure.json')
        
        # Campos sensíveis para criptografar
        sensitive_fields = ['PRIVATE_KEY', 'AGENT_PRIVATE_KEY_B58', 'API_SECRET']
        
        encrypted_data = {}
        
        for key, value in credentials.items():
            if key in sensitive_fields and value:
                # Criptografar campos sensíveis
                encrypted_data[key] = {
                    'encrypted': True,
                    'value': encrypt_credential(value)
                }
            else:
                # Campos não sensíveis (endereço público, etc)
                encrypted_data[key] = {
                    'encrypted': False,
                    'value': value
                }
        
        # Adicionar metadados
        encrypted_data['_metadata'] = {
            'created_at': datetime.now().isoformat(),
            'version': '1.0',
            'algorithm': 'Fernet-AES256'
        }
        
        # Salvar com permissões restritas
        with open(credentials_file, 'w') as f:
            json.dump(encrypted_data, f, indent=2)
        
        credentials_file.chmod(0o600)
        
        logger.info("✅ Credenciais salvas com segurança")
        
        return {
            'status': 'success',
            'message': 'Credenciais criptografadas e salvas',
            'fields_encrypted': len([k for k, v in encrypted_data.items() 
                                    if isinstance(v, dict) and v.get('encrypted')])
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao salvar credenciais: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }


def load_credentials_secure() -> dict:
    """Carrega credenciais descriptografadas"""
    try:
        credentials_file = Path('.credentials_secure.json')
        
        if not credentials_file.exists():
            return {
                'status': 'not_configured',
                'credentials': {}
            }
        
        with open(credentials_file, 'r') as f:
            encrypted_data = json.load(f)
        
        # Remover metadados
        metadata = encrypted_data.pop('_metadata', {})
        
        decrypted_credentials = {}
        
        for key, data in encrypted_data.items():
            if isinstance(data, dict):
                if data.get('encrypted'):
                    # Descriptografar campos sensíveis
                    try:
                        decrypted_credentials[key] = decrypt_credential(data['value'])
                    except Exception as e:
                        logger.error(f"❌ Erro ao descriptografar {key}: {e}")
                        decrypted_credentials[key] = None
                else:
                    decrypted_credentials[key] = data['value']
        
        return {
            'status': 'success',
            'credentials': decrypted_credentials,
            'metadata': metadata
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao carregar credenciais: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'credentials': {}
        }


def get_credentials_masked() -> dict:
    """Retorna credenciais com campos sensíveis mascarados"""
    result = load_credentials_secure()
    
    if result['status'] != 'success':
        return result
    
    credentials = result['credentials']
    
    # Mascarar campos sensíveis
    sensitive_fields = ['PRIVATE_KEY', 'AGENT_PRIVATE_KEY_B58', 'API_SECRET']
    
    masked = {}
    for key, value in credentials.items():
        if key in sensitive_fields and value:
            # Mostrar apenas primeiros 4 e últimos 4 caracteres
            if len(value) > 8:
                masked[key] = f"{value[:4]}...{value[-4:]}"
            else:
                masked[key] = "***CONFIGURED***"
        else:
            masked[key] = value
    
    return {
        'status': 'success',
        'credentials': masked,
        'is_configured': bool(credentials)
    }


def check_credentials_configured() -> bool:
    """Verifica se credenciais já foram configuradas"""
    credentials_file = Path('.credentials_secure.json')
    return credentials_file.exists()


# ========== 4. VALIDAÇÃO DE CREDENCIAIS ==========

def validate_wallet_address(address: str) -> dict:
    """Valida endereço de carteira Solana"""
    try:
        # Endereço Solana tem 32-44 caracteres base58
        if not address or len(address) < 32 or len(address) > 44:
            return {
                'valid': False,
                'error': 'Endereço inválido: tamanho incorreto'
            }
        
        # Verificar se é base58 válido
        import base58
        try:
            decoded = base58.b58decode(address)
            if len(decoded) != 32:
                return {
                    'valid': False,
                    'error': 'Endereço inválido: decodificação incorreta'
                }
        except Exception:
            return {
                'valid': False,
                'error': 'Endereço inválido: não é base58 válido'
            }
        
        return {'valid': True}
        
    except Exception as e:
        return {
            'valid': False,
            'error': f'Erro na validação: {str(e)}'
        }


def validate_private_key(private_key: str) -> dict:
    """Valida chave privada - Compatível com pacifica_auth.py"""
    try:
        if not private_key:
            return {
                'valid': False,
                'error': 'Chave privada é obrigatória'
            }
        
        # Tentar decodificar base58
        import base58
        try:
            raw = base58.b58decode(private_key)
            
            # Aceitar tanto chaves seed (32 bytes) quanto keypair (64 bytes)
            # Compatível com setup_agent_wallet() do pacifica_auth.py
            if len(raw) == 32:
                return {
                    'valid': True,
                    'type': 'seed',
                    'message': 'Chave seed válida (32 bytes)'
                }
            elif len(raw) == 64:
                return {
                    'valid': True,
                    'type': 'keypair',
                    'message': 'Chave keypair válida (64 bytes)'
                }
            else:
                return {
                    'valid': False,
                    'error': f'Tamanho da chave inválido: {len(raw)} bytes (esperado: 32 ou 64 bytes)'
                }
                
        except Exception as decode_error:
            return {
                'valid': False,
                'error': f'Chave privada inválida: não é base58 válido ({str(decode_error)})'
            }
        
    except Exception as e:
        return {
            'valid': False,
            'error': f'Erro na validação: {str(e)}'
        }


def test_api_connection(wallet_address: str, private_key: str) -> dict:
    """Testa conexão com API usando credenciais"""
    try:
        # Salvar valores originais das variáveis de ambiente
        original_main_key = os.environ.get('MAIN_PUBLIC_KEY')
        original_private_key = os.environ.get('AGENT_PRIVATE_KEY_B58')
        original_api_address = os.environ.get('API_ADDRESS')
        
        # Definir credenciais temporárias no ambiente
        os.environ['MAIN_PUBLIC_KEY'] = wallet_address
        os.environ['AGENT_PRIVATE_KEY_B58'] = private_key
        if not os.environ.get('API_ADDRESS'):
            os.environ['API_ADDRESS'] = 'https://api.pacifica.fi/api/v1'
        
        try:
            # Importar PacificaAuth
            from src.pacifica_auth import PacificaAuth
            
            # Criar instância (agora vai usar as variáveis de ambiente que definimos)
            auth = PacificaAuth()
            
            # Tentar buscar informações da conta (operação simples para validar)
            account_info = auth.get_account_info()
            
            if account_info is not None:
                # Extrair balance da resposta
                balance = 0.0  # Default para 0.0
                if 'data' in account_info:
                    data = account_info['data']
                    if isinstance(data, list) and len(data) > 0:
                        raw_balance = data[0].get('balance')
                    elif isinstance(data, dict):
                        raw_balance = data.get('balance')
                    else:
                        raw_balance = None
                        
                    # Converter balance para float de forma segura
                    if raw_balance is not None:
                        try:
                            balance = float(raw_balance)
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ Não foi possível converter balance para número: {raw_balance}")
                            balance = 0.0
                
                return {
                    'valid': True,
                    'message': 'Conexão estabelecida com sucesso',
                    'balance': balance,
                    'account_info': account_info
                }
            else:
                return {
                    'valid': False,
                    'error': 'Não foi possível obter informações da conta. Verifique as credenciais.'
                }
                
        finally:
            # Restaurar valores originais das variáveis de ambiente
            if original_main_key is not None:
                os.environ['MAIN_PUBLIC_KEY'] = original_main_key
            elif 'MAIN_PUBLIC_KEY' in os.environ:
                del os.environ['MAIN_PUBLIC_KEY']
                
            if original_private_key is not None:
                os.environ['AGENT_PRIVATE_KEY_B58'] = original_private_key
            elif 'AGENT_PRIVATE_KEY_B58' in os.environ:
                del os.environ['AGENT_PRIVATE_KEY_B58']
                
            if original_api_address is not None:
                os.environ['API_ADDRESS'] = original_api_address
            elif 'API_ADDRESS' in os.environ:
                del os.environ['API_ADDRESS']
        
    except Exception as e:
        logger.error(f"❌ Erro ao testar API: {e}")
        return {
            'valid': False,
            'error': f'Erro na conexão: {str(e)}'
        }

# ========== 4.5. FUNÇÕES AUXILIARES DE CREDENCIAIS ==========

def update_env_with_credentials(credentials: dict):
    """Atualiza .env com credenciais (mantém compatibilidade)"""
    try:
        env_path = Path('.env')
        
        # Ler conteúdo atual
        lines = []
        if env_path.exists():
            with open(env_path, 'r') as f:
                lines = f.readlines()
        
        # Atualizar ou adicionar credenciais
        keys_to_update = set(credentials.keys())
        updated_keys = set()
        
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and '=' in stripped:
                key = stripped.split('=', 1)[0].strip()
                if key in keys_to_update:
                    new_lines.append(f"{key}={credentials[key]}\n")
                    updated_keys.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        # Adicionar chaves que não existiam
        if updated_keys != keys_to_update:
            new_lines.append("\n# Credenciais de API\n")
            for key in keys_to_update - updated_keys:
                new_lines.append(f"{key}={credentials[key]}\n")
        
        # Salvar
        with open(env_path, 'w') as f:
            f.writelines(new_lines)
        
        env_path.chmod(0o600)
        
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar .env: {e}")


def backup_credentials():
    """Cria backup das credenciais antes de modificar"""
    try:
        credentials_file = Path('.credentials_secure.json')
        
        if not credentials_file.exists():
            return
        
        backup_dir = Path('backups/credentials')
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'credentials_backup_{timestamp}.json'
        
        shutil.copy2(credentials_file, backup_path)
        backup_path.chmod(0o600)
        
        logger.info(f"📦 Backup de credenciais criado: {backup_path}")
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar backup: {e}")

# ========== 5. ENDPOINTS DA API ==========# 

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
    """API: Atualizar configurações com reload automático opcional"""
    try:
        data = request.json
        updates = data if isinstance(data, dict) and 'updates' not in data else data.get('updates', data)
        auto_restart = data.get('auto_restart', False)  # False por padrão para compatibilidade
        
        result = update_env(updates)
        
        if result["status"] == "success":
            # ✅ NOVIDADE: Recarregar .env se atualização foi bem-sucedida
            load_dotenv(override=True)
            
            # ✅ MELHORIA: Reinício opcional do bot
            if auto_restart:
                try:
                    bot_was_running = is_bot_running()
                    
                    if bot_was_running:
                        logger.info("🔄 Reiniciando bot após atualização de configuração...")
                        
                        stop_result = stop_bot()
                        if stop_result.get("status") == "error":
                            logger.warning(f"Aviso ao parar bot: {stop_result.get('message')}")
                        
                        time.sleep(2)
                        
                        start_result = start_bot()
                        
                        if start_result.get("status") == "success":
                            result["bot_restarted"] = True
                            result["message"] += " - Bot reiniciado automaticamente"
                        else:
                            result["status"] = "warning"
                            result["message"] += " - Erro ao reiniciar bot"
                            result["bot_restart_error"] = start_result.get('message')
                    else:
                        result["bot_restarted"] = False
                        result["message"] += " (bot não estava rodando)"
                        
                except Exception as restart_error:
                    logger.error(f"Erro durante reinício: {restart_error}")
                    result["status"] = "warning"
                    result["message"] += f" - Erro ao reiniciar: {str(restart_error)}"
        
        status_code = 200 if result["status"] in ["success", "warning"] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Erro em /api/config/update: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# NOVOS ENDPOINTS PARA CONFIG V2
# ==========================================

@app.route('/api/config/schema', methods=['GET'])
def get_config_schema():
    """Retorna estrutura de configuração organizada por estratégia"""
    try:
        schema = {
            "dynamic_grid": {
                "label": "� Dynamic Grid",
                "description": "Grid adaptativo inteligente com algoritmo avançado",
                "sections": {
                    "basics": {
                        "label": "Configurações Básicas",
                        "fields": {
                            "SYMBOL": {
                                "type": "text",
                                "label": "Símbolo",
                                "default": "BTC",
                                "required": True,
                                "help": "Par de trading (ex: BTC, ETH, SOL)"
                            },
                            "LEVERAGE": {
                                "type": "number",
                                "label": "Alavancagem",
                                "default": 10,
                                "min": 1,
                                "max": 20,
                                "required": True,
                                "help": "Multiplicador de capital (1-20x)"
                            },
                            "ORDER_SIZE_USD": {
                                "type": "number",
                                "label": "Tamanho da Ordem (USD)",
                                "default": 250,
                                "min": 10,
                                "required": True,
                                "help": "Valor em USD por ordem"
                            }
                        }
                    },
                    "grid": {
                        "label": "Configurações do Grid",
                        "fields": {
                            "GRID_LEVELS": {
                                "type": "number",
                                "label": "Níveis do Grid",
                                "default": 10,
                                "min": 2,
                                "max": 50,
                                "required": True,
                                "help": "Número de níveis do grid (2-50)"
                            },
                            "GRID_SPACING_PERCENT": {
                                "type": "number",
                                "label": "Espaçamento (%)",
                                "default": 0.15,
                                "min": 0.01,
                                "max": 5.0,
                                "step": 0.01,
                                "required": True,
                                "help": "Distância entre níveis (0.01-5%)"
                            },
                            "GRID_DISTRIBUTION": {
                                "type": "select",
                                "label": "Distribuição do Grid",
                                "default": "symmetric",
                                "options": [
                                    {"value": "symmetric", "label": "Simétrico (50/50)"},
                                    {"value": "bullish", "label": "Otimista (60% buy)"},
                                    {"value": "bearish", "label": "Pessimista (60% sell)"}
                                ],
                                "help": "Como distribuir ordens buy/sell"
                            }
                        }
                    }
                }
            },
            "multi_asset_enhanced": {
                "label": "🧠 Multi-Asset Enhanced",
                "description": "Algoritmo avançado com 5 indicadores técnicos",
                "sections": {
                    "assets": {
                        "label": "Configuração de Ativos",
                        "fields": {
                            "SYMBOLS": {
                                "type": "text",
                                "label": "Símbolos",
                                "default": "AUTO",
                                "required": True,
                                "help": "AUTO para todos ou BTC,ETH,SOL"
                            },
                            "SYMBOLS_USE_BLACKLIST": {
                                "type": "boolean",
                                "label": "Usar Blacklist",
                                "default": True,
                                "help": "Filtrar símbolos indesejados"
                            },
                            "SYMBOLS_BLACKLIST": {
                                "type": "text",
                                "label": "Blacklist",
                                "default": "PUMP,kPEPE,FARTCOIN",
                                "help": "Símbolos para excluir (separados por vírgula)"
                            },
                            "SYMBOLS_MAX_COUNT": {
                                "type": "number",
                                "label": "Máximo de Símbolos (0 = sem limite)",
                                "default": 0,
                                "min": 0,
                                "help": "Limitar quantidade total de símbolos"
                            }
                        }
                    },
                    "strategy": {
                        "label": "Configurações de Trading",
                        "fields": {
                            "POSITION_SIZE_USD": {
                                "type": "number",
                                "label": "Tamanho da Posição (USD)",
                                "default": 100,
                                "min": 10,
                                "required": True,
                                "help": "Valor em USD por posição"
                            },
                            "MAX_CONCURRENT_TRADES": {
                                "type": "number",
                                "label": "Máximo de trades simultâneos",
                                "default": 5,
                                "min": 1,
                                "max": 20,
                                "required": True,
                                "help": "Máximo de posições abertas"
                            },
                            "LEVERAGE": {
                                "type": "number",
                                "label": "Alavancagem",
                                "default": 10,
                                "min": 1,
                                "max": 20,
                                "required": True,
                                "help": "Multiplicador de capital"
                            }
                        }
                    },
                    "protection": {
                        "label": "Proteções",
                        "fields": {
                            "STOP_LOSS_PERCENT": {
                                "type": "number",
                                "label": "Stop Loss (%)",
                                "default": 1.0,
                                "min": 0.1,
                                "max": 10.0,
                                "step": 0.1,
                                "required": True,
                                "help": "Perda máxima por trade"
                            },
                            "TAKE_PROFIT_PERCENT": {
                                "type": "number",
                                "label": "Take Profit (%)",
                                "default": 1.5,
                                "min": 0.1,
                                "max": 20.0,
                                "step": 0.1,
                                "required": True,
                                "help": "Meta de lucro por trade"
                            },
                            "AUTO_CLOSE_ENABLED": {
                                "type": "boolean",
                                "label": "Auto Close Habilitado",
                                "default": True,
                                "help": "Sistema automático de TP/SL"
                            },
                            "USE_API_TP_SL": {
                                "type": "boolean",
                                "label": "Usar TP/SL via API",
                                "default": True,
                                "help": "Usar ordens TP/SL da corretora"
                            }
                        }
                    },
                    "enhanced": {
                        "label": "Configurações Avançadas",
                        "fields": {
                            "ENHANCED_MIN_SIGNAL_QUALITY": {
                                "type": "number",
                                "label": "Qualidade Mínima do Sinal",
                                "default": 65,
                                "min": 0,
                                "max": 100,
                                "help": "Qualidade mínima do sinal (0-100)"
                            },
                            "ENHANCED_MIN_CONFIDENCE": {
                                "type": "number",
                                "label": "Confiança Mínima",
                                "default": 75,
                                "min": 0,
                                "max": 100,
                                "help": "Confiança mínima (0-100)"
                            },
                            "ENHANCED_USE_RSI_FILTER": {
                                "type": "boolean",
                                "label": "Filtrar RSI Extremos",
                                "default": True,
                                "help": "Usar filtro RSI para melhor entrada"
                            },
                            "ENHANCED_MAX_VOLATILITY": {
                                "type": "number",
                                "label": "Máx Volatilidade Permitida (%)",
                                "default": 4.0,
                                "min": 0.1,
                                "max": 20.0,
                                "step": 0.1,
                                "help": "Máxima volatilidade aceita"
                            },
                            "ENHANCED_MIN_HISTORY": {
                                "type": "number",
                                "label": "Min Períodos para Análise",
                                "default": 25,
                                "min": 10,
                                "max": 100,
                                "help": "Mínimo de períodos para análise"
                            }
                        }
                    }
                }
            },
            "pure_grid": {
                "label": "🔹 Pure Grid Trading",
                "description": "Grid trading clássico com níveis fixos",
                "sections": {
                    "basics": {
                        "label": "Configurações Básicas",
                        "fields": {
                            "SYMBOL": {
                                "type": "text",
                                "label": "Símbolo",
                                "default": "BTC",
                                "required": True,
                                "help": "Par de trading (ex: BTC, ETH, SOL)"
                            },
                            "LEVERAGE": {
                                "type": "number",
                                "label": "Alavancagem",
                                "default": 10,
                                "min": 1,
                                "max": 100,
                                "required": True,
                                "help": "Multiplicador de capital (1-100x)"
                            }
                        }
                    },
                    "grid": {
                        "label": "Parâmetros do Grid",
                        "fields": {
                            "GRID_LEVELS": {
                                "type": "number",
                                "label": "Níveis do Grid",
                                "default": 10,
                                "min": 3,
                                "max": 20,
                                "required": True,
                                "help": "Número de ordens buy/sell (3-20)"
                            },
                            "GRID_SPACING_PERCENT": {
                                "type": "number",
                                "label": "Espaçamento (%)",
                                "default": 0.15,
                                "min": 0.1,
                                "max": 5.0,
                                "step": 0.1,
                                "required": True,
                                "help": "Distância entre níveis (0.1-5%)"
                            },
                            "ORDER_SIZE_USD": {
                                "type": "number",
                                "label": "Tamanho da Ordem (USD)",
                                "default": 250,
                                "min": 1,
                                "required": True,
                                "help": "Valor em USD por ordem"
                            }
                        }
                    },
                    "risk": {
                        "label": "Gestão de Risco",
                        "fields": {
                            "RANGE_MIN": {
                                "type": "number",
                                "label": "Range Mínimo",
                                "default": 90000,
                                "min": 0,
                                "help": "Preço mínimo para operação"
                            },
                            "RANGE_MAX": {
                                "type": "number",
                                "label": "Range Máximo", 
                                "default": 110000,
                                "min": 0,
                                "help": "Preço máximo para operação"
                            }
                        }
                    }
                }
            },
            "market_making": {
                "label": "📊 Market Making",
                "description": "Grid dinâmico adaptativo ao mercado",
                "sections": {
                    "basics": {
                        "label": "Configurações Básicas",
                        "fields": {
                            "SYMBOL": {
                                "type": "text",
                                "label": "Símbolo",
                                "default": "BTC",
                                "required": True
                            },
                            "LEVERAGE": {
                                "type": "number",
                                "label": "Alavancagem",
                                "default": 10,
                                "min": 1,
                                "max": 100,
                                "required": True
                            }
                        }
                    },
                    "grid": {
                        "label": "Grid Dinâmico",
                        "fields": {
                            "GRID_LEVELS": {
                                "type": "number",
                                "label": "Níveis do Grid",
                                "default": 10,
                                "min": 3,
                                "max": 20,
                                "required": True
                            },
                            "GRID_SPACING_PERCENT": {
                                "type": "number",
                                "label": "Espaçamento Base (%)",
                                "default": 0.15,
                                "min": 0.1,
                                "max": 5.0,
                                "step": 0.1,
                                "required": True
                            },
                            "ORDER_SIZE_USD": {
                                "type": "number",
                                "label": "Tamanho da Ordem (USD)",
                                "default": 250,
                                "min": 1,
                                "required": True
                            }
                        }
                    }
                }
            },
            "multi_asset": {
                "label": "🌍 Multi-Asset Trading",
                "description": "Trading simultâneo em múltiplos ativos",
                "sections": {
                    "assets": {
                        "label": "Ativos e Exposição",
                        "fields": {
                            "SYMBOLS": {
                                "type": "text",
                                "label": "Símbolos",
                                "default": "AUTO",
                                "required": True,
                                "help": "Lista separada por vírgula ou AUTO"
                            },
                            "POSITION_SIZE_USD": {
                                "type": "number",
                                "label": "Tamanho por Posição (USD)",
                                "default": 100,
                                "min": 1,
                                "required": True,
                                "help": "Valor em USD por trade"
                            },
                            "MAX_CONCURRENT_TRADES": {
                                "type": "number",
                                "label": "Trades Simultâneos",
                                "default": 5,
                                "min": 1,
                                "max": 10,
                                "required": True,
                                "help": "Máximo de posições abertas"
                            }
                        }
                    },
                    "strategy": {
                        "label": "Estratégia de Trading",
                        "fields": {
                            "PRICE_CHANGE_THRESHOLD": {
                                "type": "number",
                                "label": "Limite de Variação de Preço (%)",
                                "default": 0.3,
                                "min": 0.1,
                                "max": 5.0,
                                "step": 0.1,
                                "required": True,
                                "help": "Mudança de preço para gerar sinal"
                            }
                        }
                    },
                    "protection": {
                        "label": "Proteção Automática",
                        "fields": {
                            "AUTO_CLOSE_ENABLED": {
                                "type": "boolean",
                                "label": "Habilitar AUTO_CLOSE",
                                "default": True,
                                "help": "Sistema de TP/SL automático"
                            },
                            "STOP_LOSS_PERCENT": {
                                "type": "number",
                                "label": "Stop Loss (%)",
                                "default": 1.0,
                                "min": 0.5,
                                "max": 10.0,
                                "step": 0.1,
                                "help": "Perda máxima por trade"
                            },
                            "TAKE_PROFIT_PERCENT": {
                                "type": "number",
                                "label": "Take Profit (%)",
                                "default": 1.5,
                                "min": 0.5,
                                "max": 10.0,
                                "step": 0.1,
                                "help": "Meta de lucro por trade"
                            }
                        }
                    }
                }
            }
        }
        
        return jsonify({
            "status": "success",
            "schema": schema
        })
        
    except Exception as e:
        logger.error(f"Erro ao carregar schema: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/config/validate', methods=['POST'])
def validate_config():
    """Valida configurações antes de salvar"""
    try:
        data = request.json
        strategy = data.get('strategy')
        config = data.get('config', {})
        
        errors = []
        warnings = []
        
        # Validações básicas
        if not strategy:
            errors.append("Estratégia não especificada")
        
        # Validar campos obrigatórios
        required_fields = {
            'dynamic_grid': ['SYMBOL', 'LEVERAGE', 'GRID_LEVELS', 'GRID_SPACING_PERCENT', 'ORDER_SIZE_USD'],
            'multi_asset_enhanced': ['SYMBOLS', 'POSITION_SIZE_USD', 'MAX_CONCURRENT_TRADES', 'LEVERAGE'],
            'pure_grid': ['SYMBOL', 'LEVERAGE', 'GRID_LEVELS', 'GRID_SPACING_PERCENT'],
            'market_making': ['SYMBOL', 'LEVERAGE', 'GRID_LEVELS'],
            'multi_asset': ['SYMBOLS', 'POSITION_SIZE_USD', 'MAX_CONCURRENT_TRADES']
        }
        
        if strategy in required_fields:
            for field in required_fields[strategy]:
                if field not in config or config[field] == '':
                    errors.append(f"Campo obrigatório: {field}")
        
        # Validar tipos e ranges
        if 'LEVERAGE' in config:
            try:
                leverage = float(config['LEVERAGE'])
                if leverage < 1 or leverage > 100:
                    errors.append("Alavancagem deve estar entre 1 e 100")
            except (ValueError, TypeError):
                errors.append("Alavancagem deve ser um número válido")
        
        if 'GRID_LEVELS' in config:
            try:
                levels = int(config['GRID_LEVELS'])
                if levels < 3 or levels > 20:
                    errors.append("Níveis do grid devem estar entre 3 e 20")
            except (ValueError, TypeError):
                errors.append("Níveis do grid deve ser um número inteiro")
        
        if 'GRID_SPACING_PERCENT' in config:
            try:
                spacing = float(config['GRID_SPACING_PERCENT'])
                if spacing < 0.1:
                    warnings.append("Espaçamento muito pequeno pode causar muitas ordens")
                if spacing > 5.0:
                    warnings.append("Espaçamento grande pode perder oportunidades")
            except (ValueError, TypeError):
                errors.append("Espaçamento deve ser um número válido")
        
        # Validar símbolos
        if 'SYMBOLS' in config:
            symbols = config['SYMBOLS']
            if symbols != 'AUTO':
                symbol_list = [s.strip() for s in symbols.split(',')]
                if len(symbol_list) == 0:
                    errors.append("Lista de símbolos não pode estar vazia")
                for symbol in symbol_list:
                    if not symbol or len(symbol) < 2:
                        errors.append(f"Símbolo inválido: {symbol}")
        
        # Validar capital suficiente
        if 'POSITION_SIZE_USD' in config and 'MAX_CONCURRENT_TRADES' in config:
            try:
                total_exposure = float(config['POSITION_SIZE_USD']) * int(config['MAX_CONCURRENT_TRADES'])
                if total_exposure > 10000:  # Ajustar conforme seu capital
                    warnings.append(f"Exposição total alta: ${total_exposure:.2f}")
            except (ValueError, TypeError):
                pass  # Erro já capturado acima
        
        return jsonify({
            "status": "success" if len(errors) == 0 else "error",
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        })
        
    except Exception as e:
        logger.error(f"Erro na validação: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/config/backup', methods=['POST'])
def create_config_backup():
    """Cria backup da configuração atual"""
    try:
        env_path = Path('.env')
        if not env_path.exists():
            return jsonify({
                "status": "error",
                "message": "Arquivo .env não encontrado"
            }), 404
        
        # Criar diretório de backups
        backup_dir = Path('backups')
        backup_dir.mkdir(exist_ok=True)
        
        # Nome do backup com timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'.env.backup_{timestamp}'
        
        # Copiar arquivo
        shutil.copy2(env_path, backup_path)
        
        # Manter apenas últimos 5 backups
        backups = sorted(backup_dir.glob('.env.backup_*'))
        if len(backups) > 5:
            for old_backup in backups[:-5]:
                old_backup.unlink()
        
        return jsonify({
            "status": "success",
            "message": "Backup criado com sucesso",
            "backup_file": str(backup_path)
        })
        
    except Exception as e:
        logger.error(f"Erro ao criar backup: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/config/restore', methods=['POST'])
def restore_config_backup():
    """Restaura backup de configuração com reinício automático do bot"""
    try:
        data = request.json
        backup_file = data.get('backup_file')
        auto_restart = data.get('auto_restart', True)
        
        if not backup_file:
            return jsonify({
                "status": "error",
                "message": "Arquivo de backup não especificado"
            }), 400
        
        backup_path = Path(backup_file)
        if not backup_path.exists():
            return jsonify({
                "status": "error",
                "message": "Backup não encontrado"
            }), 404
        
        env_path = Path('.env')
        
        # Criar backup do atual antes de restaurar
        if env_path.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy2(env_path, f'.env.before_restore_{timestamp}')
        
        # Restaurar backup
        shutil.copy2(backup_path, env_path)
        
        # ✅ NOVIDADE: Recarregar .env no processo atual
        load_dotenv(override=True)
        
        response_data = {
            "status": "success",
            "message": "Configuração restaurada com sucesso"
        }
        
        # ✅ MELHORIA: Sistema inteligente de reinício do bot após restore
        if auto_restart:
            try:
                # Verificar se bot está rodando
                bot_was_running = is_bot_running()
                
                if bot_was_running:
                    logger.info("🔄 Reiniciando bot após restauração de configuração...")
                    
                    # Parar o bot atual
                    stop_result = stop_bot()
                    if stop_result.get("status") == "error":
                        logger.warning(f"Aviso ao parar bot: {stop_result.get('message')}")
                    
                    # Aguardar cleanup completo
                    time.sleep(2)
                    
                    # Iniciar bot com configuração restaurada
                    start_result = start_bot()
                    
                    if start_result.get("status") == "success":
                        response_data["bot_restarted"] = True
                        response_data["message"] = "✅ Configuração restaurada e bot reiniciado automaticamente"
                        
                        # Emitir notificação via WebSocket
                        socketio.emit('alert', {
                            'type': 'success',
                            'message': '🔄 Bot reiniciado com sucesso após restauração!',
                            'timestamp': datetime.now().isoformat()
                        })
                        
                    else:
                        response_data["status"] = "warning"
                        response_data["message"] = "✅ Configuração restaurada, mas erro ao reiniciar bot"
                        response_data["bot_restart_error"] = start_result.get('message')
                        
                        # Emitir alerta via WebSocket
                        socketio.emit('alert', {
                            'type': 'warning',
                            'message': f'⚠️ Bot não pôde ser reiniciado: {start_result.get("message")}',
                            'timestamp': datetime.now().isoformat()
                        })
                else:
                    response_data["bot_restarted"] = False
                    response_data["message"] += " (bot não estava rodando)"
                    
            except Exception as restart_error:
                logger.error(f"Erro durante reinício após restore: {restart_error}")
                response_data["status"] = "warning"
                response_data["message"] += ", mas erro durante reinício automático"
                response_data["bot_restart_error"] = str(restart_error)
                
                # Emitir alerta de erro via WebSocket
                socketio.emit('alert', {
                    'type': 'error',
                    'message': f'❌ Erro ao reiniciar bot após restore: {str(restart_error)}',
                    'timestamp': datetime.now().isoformat()
                })
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Erro ao restaurar backup: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/config/save', methods=['POST'])
def save_config_advanced():
    """Salva configurações com validação, backup automático e reinício inteligente do bot"""
    try:
        data = request.json
        config = data.get('config', {})
        strategy = data.get('strategy')
        auto_restart = data.get('auto_restart', True)
        
        # 1. Validar antes de salvar
        validation_data = {
            'strategy': strategy,
            'config': config
        }
        
        # Fazer validação inline para evitar problemas de contexto
        errors = []
        warnings = []
        
        # Validações básicas
        if not strategy:
            errors.append("Estratégia não especificada")
        
        # Validar campos obrigatórios
        required_fields = {
            'pure_grid': ['SYMBOL', 'LEVERAGE', 'GRID_LEVELS', 'GRID_SPACING_PERCENT'],
            'market_making': ['SYMBOL', 'LEVERAGE', 'GRID_LEVELS'],
            'multi_asset': ['SYMBOLS', 'POSITION_SIZE_USD', 'MAX_CONCURRENT_TRADES']
        }
        
        if strategy in required_fields:
            for field in required_fields[strategy]:
                if field not in config or config[field] == '':
                    errors.append(f"Campo obrigatório: {field}")
        
        if errors:
            return jsonify({
                "status": "error",
                "message": "Configuração inválida",
                "errors": errors
            }), 400
        
        # 2. Criar backup automático
        try:
            env_path = Path('.env')
            if env_path.exists():
                backup_dir = Path('backups')
                backup_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = backup_dir / f'.env.backup_{timestamp}'
                shutil.copy2(env_path, backup_path)
                
                # Manter apenas últimos 5 backups
                backups = sorted(backup_dir.glob('.env.backup_*'))
                if len(backups) > 5:
                    for old_backup in backups[:-5]:
                        old_backup.unlink()
                        
                backup_created = True
            else:
                backup_created = False
        except Exception as backup_error:
            logger.warning(f"Falha ao criar backup: {backup_error}")
            backup_created = False
        
        # 3. Atualizar STRATEGY_TYPE
        config['STRATEGY_TYPE'] = strategy
        
        # 4. Salvar no .env
        env_path = Path('.env')
        
        # Ler conteúdo atual preservando comentários
        current_lines = []
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                current_lines = f.readlines()
        
        # Criar novo conteúdo
        new_lines = []
        updated_keys = set()
        
        for line in current_lines:
            stripped = line.strip()
            
            # Preservar comentários e linhas vazias
            if not stripped or stripped.startswith('#'):
                new_lines.append(line)
                continue
            
            if '=' in stripped:
                key = stripped.split('=', 1)[0].strip()
                
                # Atualizar valor se foi modificado
                if key in config:
                    new_lines.append(f"{key}={config[key]}\n")
                    updated_keys.add(key)
                else:
                    new_lines.append(line)
        
        # Adicionar novas chaves
        if updated_keys != set(config.keys()):
            new_lines.append("\n# Novas configurações adicionadas via web\n")
            for key, value in config.items():
                if key not in updated_keys:
                    new_lines.append(f"{key}={value}\n")
        
        # Escrever arquivo
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        # ✅ NOVIDADE: Recarregar .env no processo atual
        load_dotenv(override=True)
        
        response_data = {
            "status": "success",
            "message": "Configurações salvas com sucesso",
            "backup_created": backup_created
        }
        
        # ✅ MELHORIA: Sistema inteligente de reinício do bot
        if auto_restart:
            try:
                # Verificar se bot está rodando usando as funções existentes
                bot_was_running = is_bot_running()
                
                if bot_was_running:
                    logger.info("🔄 Reiniciando bot com novas configurações...")
                    
                    # Parar o bot atual
                    stop_result = stop_bot()
                    if stop_result.get("status") == "error":
                        logger.warning(f"Aviso ao parar bot: {stop_result.get('message')}")
                    
                    # Aguardar cleanup completo
                    time.sleep(2)
                    
                    # Iniciar bot com novas configurações
                    start_result = start_bot()
                    
                    if start_result.get("status") == "success":
                        response_data["bot_restarted"] = True
                        response_data["message"] = "✅ Configuração salva e bot reiniciado automaticamente"
                        
                        # Emitir notificação via WebSocket
                        socketio.emit('alert', {
                            'type': 'success',
                            'message': '🔄 Bot reiniciado com sucesso após mudança de configuração!',
                            'timestamp': datetime.now().isoformat()
                        })
                        
                    else:
                        response_data["status"] = "warning"
                        response_data["message"] = "✅ Configuração salva, mas erro ao reiniciar bot automaticamente"
                        response_data["bot_restart_error"] = start_result.get('message')
                        
                        # Emitir alerta via WebSocket
                        socketio.emit('alert', {
                            'type': 'warning',
                            'message': f'⚠️ Bot não pôde ser reiniciado: {start_result.get("message")}',
                            'timestamp': datetime.now().isoformat()
                        })
                else:
                    response_data["bot_restarted"] = False
                    response_data["message"] = "✅ Configuração salva (bot não estava rodando)"
                    
            except Exception as restart_error:
                logger.error(f"Erro durante reinício automático do bot: {restart_error}")
                response_data["status"] = "warning"
                response_data["message"] = "✅ Configuração salva, mas erro durante reinício automático"
                response_data["bot_restart_error"] = str(restart_error)
                
                # Emitir alerta de erro via WebSocket
                socketio.emit('alert', {
                    'type': 'error',
                    'message': f'❌ Erro ao reiniciar bot: {str(restart_error)}',
                    'timestamp': datetime.now().isoformat()
                })
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Erro ao salvar configuração: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/config/backups', methods=['GET'])
def list_config_backups():
    """Lista backups disponíveis"""
    try:
        backup_dir = Path('backups')
        if not backup_dir.exists():
            return jsonify({
                "status": "success",
                "backups": []
            })
        
        backups = []
        for backup_file in sorted(backup_dir.glob('.env.backup_*'), reverse=True):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "modified_str": datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M:%S')
            })
        
        return jsonify({
            "status": "success",
            "backups": backups
        })
        
    except Exception as e:
        logger.error(f"Erro ao listar backups: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ==========================================
# ENDPOINTS PARA SÍMBOLOS (CACHE)
# ==========================================

@app.route('/api/symbols/available', methods=['GET'])
def get_available_symbols():
    """Retorna símbolos disponíveis (usa cache se válido)"""
    try:
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        # Tentar usar API client se credenciais configuradas
        api_client = None
        try:
            creds = load_credentials_secure()
            if creds['status'] == 'configured':
                from src.pacifica_auth import PacificaAuth
                api_client = PacificaAuth(
                    creds['credentials']['PRIVATE_KEY'],
                    creds['credentials']['WALLET_ADDRESS']
                )
        except Exception as e:
            logger.warning(f"⚠️ Não foi possível criar API client: {e}")
        
        # Buscar símbolos
        symbols = symbols_cache.get_symbols(api_client, force_refresh)
        cache_info = symbols_cache.get_cache_info()
        
        return jsonify({
            'status': 'success',
            'symbols': symbols,
            'cache_info': cache_info
        })
    
    except Exception as e:
        logger.error(f"❌ Erro ao buscar símbolos: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/symbols/refresh', methods=['POST'])
def refresh_symbols():
    """Força atualização dos símbolos usando a mesma lógica do bot"""
    try:
        # ✅ USAR A MESMA LÓGICA QUE O BOT USA (sem cache, direto da API)
        from src.pacifica_auth import PacificaAuth
        import os
        
        # Criar um client temporário para buscar símbolos
        # get_prices() é endpoint público, não precisa de credenciais
        temp_auth = PacificaAuth()
        
        # Buscar preços/símbolos da API (mesmo que o bot faz)
        data = temp_auth.get_prices()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'Falha ao conectar com API da Pacifica.fi',
                'symbols': ['BTC', 'ETH', 'SOL', 'DOGE', 'AVAX'],  # Fallback básico
                'symbols_count': 5,
                'source': 'fallback'
            }), 200  # 200 mesmo com erro pois tem fallback
        
        # Extrair símbolos (mesma lógica do MultiAssetEnhanced)
        data_list = data.get('data', [])
        if not data_list:
            return jsonify({
                'status': 'warning', 
                'message': 'Lista de dados vazia na API',
                'symbols': ['BTC', 'ETH', 'SOL'],
                'symbols_count': 3,
                'source': 'fallback_empty'
            }), 200
        
        # Extrair símbolos dos dados
        all_symbols = []
        for item in data_list:
            symbol = item.get('symbol')
            if symbol:
                all_symbols.append(symbol)
        
        if not all_symbols:
            return jsonify({
                'status': 'warning',
                'message': 'Nenhum símbolo encontrado nos dados da API', 
                'symbols': ['BTC', 'ETH', 'SOL'],
                'symbols_count': 3,
                'source': 'fallback_no_symbols'
            }), 200
        
        # ✅ Aplicar blacklist (mesma lógica do bot)
        use_blacklist = os.getenv('SYMBOLS_USE_BLACKLIST', 'true').lower() == 'true'
        blacklist_str = os.getenv('SYMBOLS_BLACKLIST', 'PUMP,FARTCOIN')
        
        final_symbols = all_symbols.copy()
        removed_symbols = []
        
        if use_blacklist and blacklist_str:
            blacklist = [s.strip().upper() for s in blacklist_str.split(',')]
            final_symbols = [s for s in all_symbols if s not in blacklist]
            removed_symbols = [s for s in all_symbols if s in blacklist]
        
        logger.info(f"✅ Símbolos obtidos da API: {len(all_symbols)} total, {len(final_symbols)} após filtros")
        if removed_symbols:
            logger.info(f"🚫 Símbolos removidos: {removed_symbols}")
        
        return jsonify({
            'status': 'success',
            'message': f'Símbolos atualizados com sucesso da API Pacifica.fi',
            'symbols': final_symbols,
            'symbols_count': len(final_symbols),
            'total_from_api': len(all_symbols),
            'blacklisted': removed_symbols,
            'source': 'pacifica_api',
            'timestamp': datetime.now().isoformat()
        }), 200
    
    except Exception as e:
        logger.error(f"❌ Erro ao buscar símbolos: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Erro interno: {str(e)}',
            'symbols': ['BTC', 'ETH', 'SOL', 'DOGE', 'AVAX'],  # Fallback em caso de erro
            'symbols_count': 5,
            'source': 'error_fallback'
        }), 200  # 200 mesmo com erro pois tem fallback

@app.route('/api/symbols/cache-info', methods=['GET'])
def get_symbols_cache_info():
    """Retorna informações sobre o cache"""
    try:
        info = symbols_cache.get_cache_info()
        return jsonify({
            'status': 'success',
            'cache': info
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ==========================================
# ENDPOINTS DE POSIÇÕES E ORDENS
# ==========================================

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

# ==========================================
# MARKET VISION - ROTAS
# ==========================================

def sanitize_for_json(obj):
    """Converte numpy types para tipos Python nativos para serialização JSON"""
    import numpy as np
    
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(sanitize_for_json(item) for item in obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif hasattr(obj, 'item'):  # numpy scalars
        return obj.item()
    else:
        return obj

@app.route('/api/market-vision', methods=['GET'])
def get_market_vision_api():
    """Retorna análise completa do mercado"""
    try:
        if market_vision_service is None:
            return jsonify({'error': 'Market Vision não inicializado'}), 500
        
        symbol = request.args.get('symbol', 'BTC')
        
        # Verificar se é para forçar dados frescos
        force_fresh = request.args.get('fresh', 'true').lower() == 'true'
        
        if force_fresh:
            # Limpar cache manualmente
            market_vision_service._last_analysis = None
            market_vision_service._last_analysis_time = None
            logger.debug("Cache do Market Vision limpo manualmente")
        
        # Forçar dados frescos para API (sem cache)
        data = market_vision_service.get_dashboard_data(symbol, use_cache=False)
        
        # Sanitizar dados para JSON
        sanitized_data = sanitize_for_json(data)
        
        return jsonify(sanitized_data)
        
    except Exception as e:
        logger.error(f"Erro em /api/market-vision: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/record-decision', methods=['POST'])
def record_decision_api():
    """Registra decisão manual do usuário"""
    try:
        if market_vision_service is None:
            return jsonify({'error': 'Market Vision não inicializado'}), 500
        
        user_decision = request.json
        decision_id = market_vision_service.record_user_decision(user_decision)
        
        return jsonify({
            'success': True,
            'decision_id': decision_id
        })
        
    except Exception as e:
        logger.error(f"Erro em /api/record-decision: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/decision-history', methods=['GET'])
def get_decision_history_api():
    """Retorna histórico de decisões"""
    try:
        if market_vision_service is None:
            return jsonify({'error': 'Market Vision não inicializado'}), 500
        
        limit = int(request.args.get('limit', 10))
        history = market_vision_service.get_decision_history(limit)
        
        return jsonify(history)
        
    except Exception as e:
        logger.error(f"Erro em /api/decision-history: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/decision-patterns', methods=['GET'])
def get_decision_patterns_api():
    """Analisa padrões nas decisões"""
    try:
        if market_vision_service is None:
            return jsonify({'error': 'Market Vision não inicializado'}), 500
        
        patterns = market_vision_service.get_decision_patterns()
        
        return jsonify(patterns)
        
    except Exception as e:
        logger.error(f"Erro em /api/decision-patterns: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

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

# ========== 7. MIDDLEWARE PARA CARREGAR CREDENCIAIS ==========

def load_credentials_to_env():
    """Carrega credenciais descriptografadas para variáveis de ambiente"""
    try:
        result = load_credentials_secure()
        
        if result['status'] == 'success':
            for key, value in result['credentials'].items():
                if value:
                    os.environ[key] = str(value)
            
            logger.info("✅ Credenciais carregadas em memória")
        
    except Exception as e:
        logger.error(f"❌ Erro ao carregar credenciais: {e}")

# ========== ENDPOINTS DE CREDENCIAIS SEGURAS ==========

@app.route('/api/credentials/check', methods=['GET'])
def check_credentials():
    """Verifica se credenciais estão configuradas"""
    try:
        is_configured = check_credentials_configured()
        
        if is_configured:
            masked = get_credentials_masked()
            return jsonify({
                'status': 'success',
                'configured': True,
                'credentials': masked.get('credentials', {})
            })
        else:
            return jsonify({
                'status': 'success',
                'configured': False,
                'credentials': {}
            })
        
    except Exception as e:
        logger.error(f"❌ Erro ao verificar credenciais: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/credentials/save', methods=['POST'])
def save_credentials():
    """Salva credenciais com criptografia"""
    try:
        data = request.json
        
        # Extrair credenciais
        credentials = {
            'MAIN_PUBLIC_KEY': data.get('wallet_address'),
            'AGENT_PRIVATE_KEY_B58': data.get('private_key'),
            'API_ADDRESS': data.get('api_address', 'https://api.pacifica.fi/api/v1')
        }
        
        # Validar campos obrigatórios
        if not credentials['MAIN_PUBLIC_KEY']:
            return jsonify({
                'status': 'error',
                'message': 'Endereço da carteira é obrigatório'
            }), 400
        
        if not credentials['AGENT_PRIVATE_KEY_B58']:
            return jsonify({
                'status': 'error',
                'message': 'Chave privada é obrigatória'
            }), 400
        
        # Validar endereço
        wallet_validation = validate_wallet_address(credentials['MAIN_PUBLIC_KEY'])
        if not wallet_validation['valid']:
            return jsonify({
                'status': 'error',
                'message': wallet_validation['error']
            }), 400
        
        # Validar chave privada
        key_validation = validate_private_key(credentials['AGENT_PRIVATE_KEY_B58'])
        if not key_validation['valid']:
            return jsonify({
                'status': 'error',
                'message': key_validation['error']
            }), 400
        
        # Testar conexão (opcional, pode ser lento)
        test_connection = data.get('test_connection', True)
        if test_connection:
            api_test = test_api_connection(
                credentials['MAIN_PUBLIC_KEY'],
                credentials['AGENT_PRIVATE_KEY_B58']
            )
            
            if not api_test['valid']:
                return jsonify({
                    'status': 'error',
                    'message': api_test['error']
                }), 400
        
        # Salvar credenciais criptografadas
        result = save_credentials_secure(credentials)
        
        if result['status'] == 'success':
            # Também salvar no .env (sem criptografia, mas protegido por permissões)
            update_env_with_credentials(credentials)
            
            return jsonify({
                'status': 'success',
                'message': 'Credenciais salvas com segurança',
                'fields_encrypted': result.get('fields_encrypted', 0)
            })
        else:
            return jsonify(result), 500
        
    except Exception as e:
        logger.error(f"❌ Erro ao salvar credenciais: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/credentials/update', methods=['POST'])
def update_credentials():
    """Atualiza credenciais existentes (requer confirmação)"""
    try:
        data = request.json
        
        # Verificar se usuário confirmou
        if not data.get('confirmed'):
            return jsonify({
                'status': 'error',
                'message': 'Atualização de credenciais requer confirmação'
            }), 400
        
        # Criar backup das credenciais antigas
        backup_credentials()
        
        # Salvar novas credenciais
        return save_credentials()
        
    except Exception as e:
        logger.error(f"❌ Erro ao atualizar credenciais: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/credentials/validate', methods=['POST'])
def validate_credentials_endpoint():
    """Valida credenciais sem salvar"""
    try:
        data = request.json
        
        wallet_address = data.get('wallet_address')
        private_key = data.get('private_key')
        
        errors = []
        validation_details = {}
        
        # Validar endereço
        if wallet_address:
            wallet_validation = validate_wallet_address(wallet_address)
            if not wallet_validation['valid']:
                errors.append(wallet_validation['error'])
            else:
                validation_details['wallet'] = 'Endereço da carteira válido'
        else:
            errors.append('Endereço da carteira é obrigatório')
        
        # Validar chave privada
        if private_key:
            key_validation = validate_private_key(private_key)
            if not key_validation['valid']:
                errors.append(key_validation['error'])
            else:
                # Adicionar informações sobre o tipo de chave detectado
                key_type = key_validation.get('type', 'unknown')
                key_message = key_validation.get('message', 'Chave privada válida')
                validation_details['private_key'] = key_message
                
                logger.info(f"✅ Chave privada válida - Tipo: {key_type}")
        else:
            errors.append('Chave privada é obrigatória')
        
        # Se não houver erros, testar conexão
        if not errors:
            logger.info("🔗 Testando conexão com API...")
            api_test = test_api_connection(wallet_address, private_key)
            if not api_test['valid']:
                errors.append(api_test['error'])
            else:
                logger.info("✅ Conexão com API estabelecida com sucesso")
                return jsonify({
                    'status': 'success',
                    'valid': True,
                    'message': 'Credenciais válidas',
                    'balance': api_test.get('balance'),
                    'details': validation_details
                })
        
        logger.warning(f"❌ Validação falhou: {errors}")
        return jsonify({
            'status': 'error',
            'valid': False,
            'errors': errors
        }), 400
        
    except Exception as e:
        logger.error(f"❌ Erro na validação: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/credentials/delete', methods=['POST'])
def delete_credentials():
    """Remove credenciais (requer confirmação)"""
    try:
        data = request.json
        
        if not data.get('confirmed'):
            return jsonify({
                'status': 'error',
                'message': 'Exclusão de credenciais requer confirmação'
            }), 400
        
        credentials_file = Path('.credentials_secure.json')
        
        if credentials_file.exists():
            # Criar backup antes de deletar
            backup_credentials()
            
            # Deletar arquivo
            credentials_file.unlink()
            
            logger.warning("⚠️ Credenciais deletadas pelo usuário")
            
            return jsonify({
                'status': 'success',
                'message': 'Credenciais removidas com sucesso'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Nenhuma credencial configurada'
            }), 404
        
    except Exception as e:
        logger.error(f"❌ Erro ao deletar credenciais: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# ==========================================
# ENDPOINTS PARA CONFIGURAÇÃO V2 - HIERÁRQUICA
# ==========================================

@app.route('/api/config/schema/v2', methods=['GET'])
def get_config_schema_v2():
    """Retorna estrutura hierárquica completa de configuração"""
    try:
        schema_file = Path('config_schema.json')
        
        if not schema_file.exists():
            return jsonify({
                'status': 'error',
                'message': 'Arquivo config_schema.json não encontrado'
            }), 404
        
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        # Carregar valores atuais do .env
        current_config = read_env()
        
        return jsonify({
            'status': 'success',
            'schema': schema,
            'current_values': current_config,
            'current_strategy': current_config.get('STRATEGY_TYPE', 'pure_grid')
        })
        
    except Exception as e:
        logger.error(f"❌ Erro ao carregar schema v2: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/config/validate-field', methods=['POST'])
def validate_config_field():
    """Valida um campo individual em tempo real"""
    try:
        data = request.json
        field_name = data.get('field')
        field_value = data.get('value')
        strategy = data.get('strategy', 'pure_grid')
        
        if not field_name:
            return jsonify({
                'valid': False,
                'message': 'Campo não especificado'
            }), 400
        
        # Carregar schema
        schema_file = Path('config_schema.json')
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        field_config = schema['fields'].get(field_name)
        
        if not field_config:
            return jsonify({
                'valid': True,
                'message': 'Campo não requer validação específica'
            })
        
        # Validações por tipo
        field_type = field_config.get('type')
        validation_result = {
            'valid': True,
            'message': '✅ Valor válido',
            'warning': None
        }
        
        # Validação numérica
        if field_type == 'number':
            try:
                num_value = float(field_value)
                min_val = field_config.get('min')
                max_val = field_config.get('max')
                
                if min_val is not None and num_value < min_val:
                    validation_result['valid'] = False
                    validation_result['message'] = f'❌ Valor deve ser ≥ {min_val}'
                elif max_val is not None and num_value > max_val:
                    validation_result['valid'] = False
                    validation_result['message'] = f'❌ Valor deve ser ≤ {max_val}'
                else:
                    # Avisos baseados em recomendações
                    if field_name == 'LEVERAGE' and num_value > 10:
                        validation_result['warning'] = '⚠️ Leverage alto aumenta risco de liquidação'
                    elif field_name == 'STOP_LOSS_PERCENT' and num_value < 1:
                        validation_result['warning'] = '⚠️ Stop Loss muito apertado pode gerar stops falsos'
                    elif field_name == 'TAKE_PROFIT_PERCENT' and num_value < field_config.get('default', 0):
                        validation_result['warning'] = '⚠️ Take Profit abaixo do recomendado'
                        
            except ValueError:
                validation_result['valid'] = False
                validation_result['message'] = '❌ Valor deve ser numérico'
        
        # Validação de toggle/boolean
        elif field_type == 'toggle':
            if not isinstance(field_value, bool) and field_value not in ['true', 'false', 'True', 'False']:
                validation_result['valid'] = False
                validation_result['message'] = '❌ Valor deve ser true/false'
        
        return jsonify(validation_result)
        
    except Exception as e:
        logger.error(f"❌ Erro na validação: {e}")
        return jsonify({
            'valid': False,
            'message': f'Erro: {str(e)}'
        }), 500


@app.route('/api/config/get-defaults', methods=['POST'])
def get_config_defaults():
    """Retorna valores padrão para uma estratégia específica"""
    try:
        data = request.json
        strategy = data.get('strategy', 'pure_grid')
        
        # Carregar schema
        schema_file = Path('config_schema.json')
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        # Coletar defaults relevantes para a estratégia
        defaults = {}
        
        # Sempre incluir configurações comuns
        common_fields = schema['config_sections']['common']['fields']
        for field in common_fields:
            if field in schema['fields']:
                defaults[field] = schema['fields'][field].get('default')
        
        # Adicionar configurações específicas da estratégia
        strategy_category = schema['strategies'][strategy]['category']
        
        if strategy_category == 'grid':
            basic_fields = schema['config_sections']['basic_grid']['fields']
        else:
            basic_fields = schema['config_sections']['basic_multi_asset']['fields']
        
        for field in basic_fields:
            if field in schema['fields']:
                defaults[field] = schema['fields'][field].get('default')
        
        # Configurações de auto-close (comum a todas)
        autoclose_fields = schema['config_sections']['auto_close']['fields']
        for field in autoclose_fields:
            if field in schema['fields']:
                defaults[field] = schema['fields'][field].get('default')
        
        # Risk management (comum a todas)
        risk_fields = schema['config_sections']['risk_management']['fields']
        for field in risk_fields:
            if field in schema['fields']:
                defaults[field] = schema['fields'][field].get('default')
        
        # Enhanced (apenas se aplicável)
        if strategy == 'multi_asset_enhanced':
            enhanced_fields = schema['config_sections']['enhanced_advanced']['fields']
            for field in enhanced_fields:
                if field in schema['fields']:
                    defaults[field] = schema['fields'][field].get('default')
        
        # Adicionar STRATEGY_TYPE
        defaults['STRATEGY_TYPE'] = strategy
        
        return jsonify({
            'status': 'success',
            'strategy': strategy,
            'defaults': defaults
        })
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar defaults: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/config/preview-changes', methods=['POST'])
def preview_config_changes():
    """Preview das mudanças antes de salvar"""
    try:
        new_config = request.json.get('config', {})
        
        # Carregar config atual
        current_config = read_env()
        
        # Comparar mudanças
        changes = {
            'added': {},
            'modified': {},
            'removed': {},
            'unchanged': {}
        }
        
        # Detectar mudanças
        all_keys = set(list(current_config.keys()) + list(new_config.keys()))
        
        for key in all_keys:
            current_val = current_config.get(key)
            new_val = new_config.get(key)
            
            if current_val is None and new_val is not None:
                changes['added'][key] = new_val
            elif current_val is not None and new_val is None:
                changes['removed'][key] = current_val
            elif str(current_val) != str(new_val):
                changes['modified'][key] = {
                    'from': current_val,
                    'to': new_val
                }
            else:
                changes['unchanged'][key] = current_val
        
        # Avaliar impacto
        impact_level = 'low'
        warnings = []
        
        # Mudanças críticas
        critical_changes = ['LEVERAGE', 'STRATEGY_TYPE', 'STOP_LOSS_PERCENT']
        for key in critical_changes:
            if key in changes['modified']:
                impact_level = 'high'
                warnings.append(f"⚠️ {key} foi alterado - Bot será reiniciado")
        
        # Mudanças médias
        moderate_changes = ['GRID_LEVELS', 'MAX_CONCURRENT_TRADES', 'ORDER_SIZE_USD']
        for key in moderate_changes:
            if key in changes['modified'] and impact_level == 'low':
                impact_level = 'medium'
        
        return jsonify({
            'status': 'success',
            'changes': changes,
            'impact_level': impact_level,
            'warnings': warnings,
            'total_changes': len(changes['added']) + len(changes['modified']) + len(changes['removed'])
        })
        
    except Exception as e:
        logger.error(f"❌ Erro no preview: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

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
    
    # Chamar ao iniciar a aplicação
    load_credentials_to_env()
    
    print("="*80)
    print("✅ Sistema de credenciais seguras carregado")
    print("   - Criptografia AES-256 (Fernet)")
    
    # ✅ Inicializar Market Vision
    print("="*80)
    print("🎯 Inicializando Market Vision...")
    print("="*80)
    
    mv_init_success = init_market_vision()
    
    if mv_init_success:
        print("="*80)
        print("✅ SUCESSO: Market Vision inicializado")
        print("   Análise multi-dimensional do mercado ativada")
        print("   Dashboard com sistema de tomada de decisão")
        print("="*80)
    else:
        print("="*80)
        print("⚠️  AVISO: Market Vision não inicializado")
        print("   Funcionalidades básicas continuarão funcionando")
        print("="*80)
    print("   - Validação de wallet Solana")
    print("   - Teste de conexão API")
    print("   - Backup automático")
    print("="*80)
    
    # Iniciar monitor threads
    monitor_active = True
    monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
    monitor_thread.start()
    
    logs_monitor_thread = threading.Thread(target=monitor_logs, daemon=True)
    logs_monitor_thread.start()
    
    # Iniciar Market Vision thread (se inicializado com sucesso)
    market_vision_thread = None
    if mv_init_success:
        market_vision_thread = threading.Thread(target=market_vision_update_loop, daemon=True)
        market_vision_thread.start()
        print("🎯 Market Vision update thread iniciada")
    
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
        if market_vision_thread:
            market_vision_thread.join(timeout=5)
        print("👋 Interface web encerrada")

