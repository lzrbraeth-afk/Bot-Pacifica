# src/risk_health_reporter.py
from __future__ import annotations
import json, time, threading
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime

def _now_iso() -> str:
    return datetime.now().isoformat()

def _atomic_write(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

@dataclass
class ActiveTrade:
    trade_id: str
    symbol: str
    side: str
    size: float
    entry_price: float
    entry_time: str
    tp_percent: Optional[float] = None
    sl_percent: Optional[float] = None
    pnl_usd: float = 0.0
    pnl_percent: float = 0.0
    time_in_trade_sec: int = 0
    current_price: Optional[float] = None
    liquidation_price: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

class RiskHealthReporter:
    """
    Escreve artefatos JSON estáveis para a interface:
      - data/risk/status.json          (estado de sessão/geral)
      - data/risk/active_trade.json    (telemetria do trade atual)
      - data/risk/active_trade_log.jsonl  (linha por checagem/ação)
      - data/risk/trades/{trade_id}.json  (snapshot final ao encerrar)
    """
    def __init__(self, strategy_name: str):
        self.strategy = strategy_name
        self.base_dir = Path("data/risk")
        self.lock = threading.Lock()
        self.active: Optional[ActiveTrade] = None
        self.status_file = self.base_dir / "status.json"
        self.active_file = self.base_dir / "active_trade.json"
        self.log_file = self.base_dir / "active_trade_log.jsonl"
        self.trades_dir = self.base_dir / "trades"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.trades_dir.mkdir(parents=True, exist_ok=True)

        # cria status inicial
        self.update_status({"strategy": self.strategy, "online": True})

    # ---------- STATUS DE SESSÃO ----------
    def update_status(self, payload: Dict[str, Any]):
        with self.lock:
            payload = {"timestamp": _now_iso(), **payload}
            _atomic_write(self.status_file, payload)

    # ---------- CICLO DE TRADE ----------
    def start_trade(self, trade_id: str, *, symbol: str, side: str, size: float,
                    entry_price: float, entry_time: Optional[str] = None,
                    tp_percent: Optional[float] = None, sl_percent: Optional[float] = None,
                    extra: Optional[Dict[str, Any]] = None):
        with self.lock:
            self.active = ActiveTrade(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                size=size,
                entry_price=float(entry_price),
                entry_time=entry_time or _now_iso(),
                tp_percent=tp_percent,
                sl_percent=sl_percent,
                extra=extra or {}
            )
            self._flush_active()

    def update_trade(self, *, current_price: Optional[float] = None,
                     pnl_usd: Optional[float] = None, pnl_percent: Optional[float] = None,
                     time_in_trade_sec: Optional[int] = None,
                     liquidation_price: Optional[float] = None,
                     extra: Optional[Dict[str, Any]] = None):
        with self.lock:
            if not self.active:
                return
            if current_price is not None:
                self.active.current_price = float(current_price)
            if pnl_usd is not None:
                self.active.pnl_usd = float(pnl_usd)
            if pnl_percent is not None:
                self.active.pnl_percent = float(pnl_percent)
            if time_in_trade_sec is not None:
                self.active.time_in_trade_sec = int(time_in_trade_sec)
            if liquidation_price is not None:
                self.active.liquidation_price = float(liquidation_price)
            if extra:
                self.active.extra.update(extra)
            self._flush_active()

    def end_trade(self, *, reason: str, result: str, final_snapshot: Optional[Dict[str, Any]] = None):
        with self.lock:
            if not self.active:
                return
            snapshot = asdict(self.active)
            snapshot.update({
                "ended_at": _now_iso(),
                "reason": reason,
                "result": result,  # "tp" | "sl" | "emergency" | "manual" | "session_limit" | ...
                "strategy": self.strategy
            })
            if final_snapshot:
                snapshot.update(final_snapshot)
            _atomic_write(self.trades_dir / f"{self.active.trade_id}.json", snapshot)
            # limpar ativo
            self.active = None
            _atomic_write(self.active_file, {"timestamp": _now_iso(), "active": False})

    # ---------- LOG DE CHECAGENS ----------
    def log_check(self, event_type: str, details: Dict[str, Any]):
        line = {"timestamp": _now_iso(), "event": event_type, **details}
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with self.lock:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

    # ---------- INTERNOS ----------
    def _flush_active(self):
        if not self.active:
            return
        payload = {"timestamp": _now_iso(), "active": True, "trade": asdict(self.active), "strategy": self.strategy}
        _atomic_write(self.active_file, payload)
