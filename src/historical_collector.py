"""
Historical Collector - Bot Pacifica
-----------------------------------
Faz coleta inicial e incremental de histórico de trades e PNL
salvando localmente em JSON, e expondo dados agregados.
"""

import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from pacifica_auth import PacificaAuth

DATA_DIR = Path("data")
HISTORICAL_FILE = DATA_DIR / "historical_trades.json"

def load_existing_data():
    if not HISTORICAL_FILE.exists():
        return []
    try:
        with open(HISTORICAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print("⚠️ Erro ao ler histórico existente — recriando arquivo.")
        return []

def save_data(data):
    DATA_DIR.mkdir(exist_ok=True)
    with open(HISTORICAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"💾 Histórico atualizado: {len(data)} registros salvos.")

def get_last_timestamp(trades):
    if not trades:
        return None
    timestamps = [t.get("timestamp") for t in trades if t.get("timestamp")]
    if not timestamps:
        return None
    try:
        return max(datetime.fromisoformat(ts) for ts in timestamps)
    except Exception:
        return None

def collect_historical_trades(days=30):
    """Executa coleta incremental de trades"""
    print("=" * 80)
    print("📊 Coletando histórico de trades da Pacifica...")
    auth = PacificaAuth()

    existing = load_existing_data()
    last_ts = get_last_timestamp(existing)
    if last_ts:
        start_time = int(last_ts.timestamp())
        print(f"🔁 Coleta incremental desde {last_ts.isoformat()}")
    else:
        start_time = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        print(f"🕒 Coleta inicial (últimos {days} dias)")

    end_time = int(datetime.utcnow().timestamp())

    try:
        # Endpoint fictício (adaptar conforme API real)
        # Exemplo: /api/v1/trades?start_time=...&end_time=...
        new_trades = auth.get_trade_history(start_time=start_time, end_time=end_time, limit=1000)
        if not new_trades:
            print("ℹ️ Nenhum novo trade encontrado.")
            return

        # Remover duplicados
        existing_ids = {t.get("id") for t in existing if "id" in t}
        merged = existing + [t for t in new_trades if t.get("id") not in existing_ids]

        save_data(sorted(merged, key=lambda x: x.get("timestamp", "")))
        print(f"✅ {len(new_trades)} novos registros adicionados ({len(merged)} total).")

    except Exception as e:
        print(f"❌ Erro na coleta histórica: {e}")

def run_collector(interval_minutes=60):
    """Loop contínuo"""
    while True:
        collect_historical_trades()
        print(f"⏳ Aguardando {interval_minutes} min para próxima atualização...")
        time.sleep(interval_minutes * 60)

if __name__ == "__main__":
    run_collector()
