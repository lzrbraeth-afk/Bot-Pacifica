"""
Multi-Asset PNL Strategy
Versão experimental do Multi-Asset com Motor de PNL Inteligente.
Base: multi_asset_enhanced_strategy.py
Autor: Luiz Rocha
"""

import time
from datetime import datetime
from multi_asset_enhanced_strategy import EnhancedSignalDetector
from performance_tracker import PerformanceTracker
from position_manager import PositionManager
from pacifica_auth import PacificaAuth

class MultiAssetPNLStrategy:
    def __init__(self, config):
        self.config = config
        self.auth = PacificaAuth()
        self.signal_detector = EnhancedSignalDetector()
        self.performance_tracker = PerformanceTracker()
        self.position_mgr = PositionManager()

        self.symbols = config.get('SYMBOLS', ['BTC', 'ETH', 'SOL', 'LINK', 'AVAX'])
        self.take_profit_percent = float(config.get('TAKE_PROFIT_PERCENT', 1.8))
        self.stop_loss_percent = float(config.get('STOP_LOSS_PERCENT', 1.0))
        self.position_size_usd = float(config.get('POSITION_SIZE_USD', 25))
        self.leverage = int(config.get('LEVERAGE', 5))

        self.price_history = {}
        self.active_positions = {}
        self._last_trade_time = {}
        self._filter_whitelist()

    # ====================================================================================
    # BLOCOS DE LÓGICA DE PNL
    # ====================================================================================

    def _get_market_regime(self, symbol: str) -> str:
        """Determina regime de volatilidade"""
        prices = self.price_history.get(symbol, [])
        if len(prices) < 10:
            return "NORMAL"
        vol = self.signal_detector._analyze_volatility(prices).get("volatility", 1.0)
        if vol < 0.5:
            return "LOW"
        elif vol > 4.0:
            return "HIGH"
        return "NORMAL"

    def _daily_risk_check(self) -> bool:
        """Pausa o bot se drawdown diário exceder limite"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        daily_pnl = self.performance_tracker.daily_pnl.get(today, 0)
        current_balance = self.performance_tracker.current_balance
        if daily_pnl < -0.04 * current_balance:
            print("🚨 Limite de perda diária atingido — pausando por hoje.")
            return False
        return True

    def _filter_whitelist(self):
        """Filtra símbolos operáveis"""
        whitelist = ['BTC', 'ETH', 'SOL', 'LINK', 'AVAX']
        self.symbols = [s for s in self.symbols if s in whitelist]
        print(f"🧾 Whitelist ativa: {', '.join(self.symbols)}")

    def _can_trade_symbol(self, symbol: str) -> bool:
        """Cooldown entre trades do mesmo ativo"""
        now = time.time()
        cooldown = 300  # 5 minutos
        last = self._last_trade_time.get(symbol, 0)
        if now - last < cooldown:
            print(f"⏸️ Cooldown ativo para {symbol}")
            return False
        self._last_trade_time[symbol] = now
        return True

    # ====================================================================================
    # MOTOR DE DECISÃO E EXECUÇÃO
    # ====================================================================================

    def analyze_and_trade(self):
        """Loop principal de análise e execução"""
        if not self._daily_risk_check():
            return

        for symbol in self.symbols:
            prices = self.auth.get_historical_data(symbol, interval="5m", periods=30)
            if not prices:
                continue
            self.price_history[symbol] = prices

            signal = self.signal_detector.analyze(prices)
            if not signal or signal['quality_score'] < 65:
                continue

            regime = self._get_market_regime(symbol)
            confidence = signal['confidence']

            if regime == "HIGH" and confidence < 85:
                print(f"⚠️ {symbol}: vol alta ({regime}), ignorando sinal fraco ({confidence})")
                continue
            if not self._can_trade_symbol(symbol):
                continue

            side = signal['side']
            current_price = prices[-1]
            base_qty = self.position_size_usd / current_price
            lot_size = 0.001

            # Dimensionamento adaptativo
            vol_mult = 1.0
            if regime == "HIGH":
                vol_mult = 0.8
            elif regime == "LOW":
                vol_mult = 1.1

            conf_mult = min(1.2, confidence / 100 + 0.2)
            qty = max(lot_size, round(base_qty * vol_mult * conf_mult, 3))

            # TP/SL dinâmicos
            tp_adj = self.take_profit_percent
            sl_adj = self.stop_loss_percent
            if signal['quality_score'] >= 80 and confidence >= 85:
                tp_adj *= 1.3
                sl_adj *= 0.9
            elif signal['quality_score'] < 65:
                tp_adj *= 0.8
                sl_adj *= 1.1

            print(f"🧠 {symbol} | {side} | {qty} @ {current_price} | TP={tp_adj:.2f}% SL={sl_adj:.2f}%")

            result = self.auth.create_order_with_auto_tpsl(
                symbol=symbol,
                side='bid' if side == 'LONG' else 'ask',
                amount=qty,
                price=current_price,
                tp_percent=tp_adj,
                sl_percent=sl_adj
            )

            if result and result.get('success'):
                print(f"✅ {symbol}: ordem executada com sucesso ({side})")
            else:
                print(f"⚠️ {symbol}: falha ao executar ordem ({result})")
