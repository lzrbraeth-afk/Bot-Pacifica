"""
Interface Web Flask Melhorada - Bot Trading Pacifica.fi
Versão 2.1 com Logs Auto-refresh e Visualização de Posições/Ordens
"""
from flask import Flask, render_template, jsonify, request, send_file, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# ===== IMPORTS PARA MÓDULO CSV =====
from werkzeug.utils import secure_filename
import shutil
from src.csv_trade_parser import PacificaCSVParser, analyze_pacifica_csv
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
from io import StringIO, BytesIO

# Configurar logging
logging.basicConfig(level=logging.INFO)
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

# ========== FUNÇÕES DE DADOS (MANTIDAS + NOVAS) ==========

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
    
    if not PNL_HISTORY_FILE.exists():
        return default_metrics
    
    try:
        with open(PNL_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
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
        logger.error(f"Erro ao ler métricas: {e}")
        return default_metrics

def get_pnl_history(hours=24):
    """Obtém histórico de PNL para gráficos"""
    if not PNL_HISTORY_FILE.exists():
        return []
    
    try:
        with open(PNL_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
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
    if not PNL_HISTORY_FILE.exists():
        return []
    
    try:
        with open(PNL_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        cycles = data.get("cycles_history", [])
        trades = sorted(cycles, key=lambda x: x.get("timestamp", ""), reverse=True)
        return trades[:limit]
    except Exception as e:
        logger.error(f"Erro ao obter histórico de trades: {e}")
        return []

# ========== NOVAS FUNÇÕES: POSIÇÕES E ORDENS ==========

def get_active_positions():
    """Obtém posições ativas do arquivo ou API"""
    if not POSITIONS_FILE.exists():
        return []
    
    try:
        with open(POSITIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
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
    if not ORDERS_FILE.exists():
        return []
    
    try:
        with open(ORDERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
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
            
            time.sleep(3)  # Atualizar a cada 3 segundos
        except Exception as e:
            logger.error(f"Erro no logs monitor thread: {e}")
            time.sleep(5)
    
    logger.info("🛑 Logs monitor thread parada")

# ========== ROTAS HTTP ==========


# ===== FUNÇÕES HELPER CSV =====
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


# ========== NOVAS ROTAS: POSIÇÕES E ORDENS ==========

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

@app.route('/api/trades')
def api_trades():
    """API: Histórico de trades da exchange (dados coletados via historical_collector)"""
    try:
        limit = request.args.get('limit', 50, type=int)
        # Ler dados coletados do endpoint /api/v1/positions/history da Pacifica
        file_path = DATA_DIR / "historical_trades.json"
        
        if not file_path.exists():
            logger.warning("⚠️ Arquivo historical_trades.json não encontrado. Execute historical_collector.py")
            return jsonify([])
        
        with open(file_path, "r", encoding="utf-8") as f:
            trades = json.load(f)
        
        if not isinstance(trades, list):
            logger.error(f"❌ Formato inválido em historical_trades.json: {type(trades)}")
            return jsonify([])
        
        # Ordenar por timestamp (mais recente primeiro)
        trades_sorted = sorted(trades, key=lambda x: x.get('timestamp', x.get('closed_at', '')), reverse=True)
        
        # Aplicar limite
        return jsonify(trades_sorted[:limit])
    except Exception as e:
        logger.error(f"Erro em /api/trades: {e}")
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
        
    except Exception as e:
        logger.error(f"Erro ao atualizar dados: {e}")
        emit('error', {'message': 'Erro na atualização'})
    
    logs = tail_logs(lines=100)
    emit('logs_update', logs)

# ========== INICIALIZAÇÃO ==========


# ===== ROTAS API CSV =====
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


if __name__ == '__main__':
    print("="*60)
    print("🚀 Interface Web Melhorada v2.1 iniciando...")
    print("📊 Dashboard: http://localhost:5000")
    print("🔌 WebSocket: Ativado")
    print("📜 Logs: Auto-refresh ativado")
    print("📈 Posições: Monitoramento em tempo real")
    print("🛑 Para parar: Ctrl+C")
    print("="*60)
    print(f"🐍 Python: {PYTHON_EXECUTABLE}")
    print("="*60)
    
    # Verificar arquivos necessários
    if not ENV_FILE.exists():
        print(f"⚠️  AVISO: Arquivo {ENV_FILE} não encontrado")
    
    if not Path(BOT_SCRIPT).exists():
        print(f"⚠️  AVISO: Arquivo {BOT_SCRIPT} não encontrado")
    
    # Criar pastas
    LOGS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    
    # Iniciar monitor threads
    monitor_active = True
    monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
    monitor_thread.start()
    
    logs_monitor_thread = threading.Thread(target=monitor_logs, daemon=True)
    logs_monitor_thread.start()
    
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

# ========== NOVO ENDPOINT HISTÓRICO ==========
@app.route('/api/historical-stats')
def api_historical_stats():
    """API: Estatísticas históricas agregadas"""
    try:
        file_path = DATA_DIR / "historical_trades.json"
        if not file_path.exists():
            return jsonify({"days": [], "pnl": [], "volume": [], "win_rate": []})

        with open(file_path, "r", encoding="utf-8") as f:
            trades = json.load(f)

        if not trades:
            return jsonify({"days": [], "pnl": [], "volume": [], "win_rate": []})

        daily = {}
        for t in trades:
            ts = t.get("timestamp", "")
            if not ts:
                continue
            date = ts[:10]
            pnl = float(t.get("pnl_usd", 0))
            volume = abs(float(t.get("price", 0)) * float(t.get("size", 0)))
            win = pnl > 0

            if date not in daily:
                daily[date] = {"pnl": 0, "volume": 0, "wins": 0, "trades": 0}
            daily[date]["pnl"] += pnl
            daily[date]["volume"] += volume
            daily[date]["wins"] += 1 if win else 0
            daily[date]["trades"] += 1

        days_sorted = sorted(daily.keys())
        pnl_values = [daily[d]["pnl"] for d in days_sorted]
        volume_values = [daily[d]["volume"] for d in days_sorted]
        win_rate_values = [
            round((daily[d]["wins"] / daily[d]["trades"]) * 100, 1) if daily[d]["trades"] else 0
            for d in days_sorted
        ]

        return jsonify({
            "days": days_sorted,
            "pnl": pnl_values,
            "volume": volume_values,
            "win_rate": win_rate_values
        })

    except Exception as e:
        logger.error(f"Erro em /api/historical-stats: {e}")
        return jsonify({"days": [], "pnl": [], "volume": [], "win_rate": []})

# Novo endpoint para PNL não realizado e realizado