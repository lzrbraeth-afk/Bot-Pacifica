"""
Direction Analyzer - Análise de Direção de Mercado
Determina se o mercado está em tendência LONG ou SHORT
Integrado ao Bot Trading Pacifica.fi v3.1
"""

import numpy as np
from typing import Dict, List, Optional
from enum import Enum
import logging

class Direction(Enum):
    """Enum para direções de mercado"""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"

class DirectionAnalyzer:
    """
    Analisa direção do mercado usando múltiplos indicadores
    
    Compatível com o padrão de estratégias do bot Pacifica.fi
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Configurações de análise
        self.min_confirmation_score = config.get('min_confirmation_score', 0.6)
        self.use_ema = config.get('use_ema', True)
        self.use_rsi = config.get('use_rsi', True)
        self.use_volume = config.get('use_volume', True)
        
        # Períodos dos indicadores
        self.ema_fast = config.get('ema_fast', 20)
        self.ema_slow = config.get('ema_slow', 50)
        self.rsi_period = config.get('rsi_period', 14)
        
        self.logger.debug(f"DirectionAnalyzer inicializado: min_score={self.min_confirmation_score}")
    
    def analyze(self, candles: List[Dict]) -> Dict:
        """
        Analisa direção baseado em múltiplos fatores
        
        Args:
            candles: Lista de candles no formato:
                [{'timestamp': int, 'open': str, 'high': str, 'low': str, 'close': str, 'volume': str}, ...]
        
        Returns:
            {
                'direction': Direction.LONG/SHORT/NEUTRAL,
                'confidence': float (0-1),
                'signals': {
                    'ema': 'bullish'/'bearish'/'neutral',
                    'rsi': 'bullish'/'bearish'/'neutral',
                    'volume': 'bullish'/'bearish'/'neutral',
                    'price_action': 'bullish'/'bearish'/'neutral'
                },
                'score': float (-1 to 1),
                'indicators': {
                    'ema_20': float,
                    'ema_50': float,
                    'rsi': float
                }
            }
        """
        if len(candles) < 50:
            self.logger.warning(f"⚠️ Candles insuficientes para análise confiável: {len(candles)} < 50")
            return self._neutral_response()
        
        signals = {}
        scores = []
        indicators = {}
        
        # 1. Análise de EMAs (20, 50)
        if self.use_ema:
            ema_signal, ema_score, ema_values = self._analyze_ema(candles)
            signals['ema'] = ema_signal
            scores.append(ema_score)
            indicators['ema_20'] = ema_values['ema_20']
            indicators['ema_50'] = ema_values['ema_50']
        
        # 2. RSI (14 períodos)
        if self.use_rsi:
            rsi_signal, rsi_score, rsi_value = self._analyze_rsi(candles)
            signals['rsi'] = rsi_signal
            scores.append(rsi_score)
            indicators['rsi'] = rsi_value
        
        # 3. Volume Profile
        if self.use_volume:
            volume_signal, volume_score = self._analyze_volume(candles)
            signals['volume'] = volume_signal
            scores.append(volume_score)
        
        # 4. Price Action (últimos 5 candles)
        pa_signal, pa_score = self._analyze_price_action(candles[-5:])
        signals['price_action'] = pa_signal
        scores.append(pa_score)
        
        # Calcula score final (média ponderada)
        final_score = np.mean(scores) if scores else 0
        confidence = abs(final_score)
        
        # Determina direção
        if final_score > self.min_confirmation_score:
            direction = Direction.LONG
        elif final_score < -self.min_confirmation_score:
            direction = Direction.SHORT
        else:
            direction = Direction.NEUTRAL
        
        result = {
            'direction': direction,
            'confidence': confidence,
            'signals': signals,
            'score': final_score,
            'indicators': indicators
        }
        
        self.logger.debug(
            f"📊 Análise: {direction.value.upper()} | "
            f"Confiança: {confidence:.2%} | Score: {final_score:.2f}"
        )
        
        return result
    
    def _analyze_ema(self, candles: List[Dict]) -> tuple:
        """Analisa cruzamento de EMAs"""
        closes = np.array([float(c['close']) for c in candles])
        
        ema_20 = self._calculate_ema(closes, self.ema_fast)
        ema_50 = self._calculate_ema(closes, self.ema_slow)
        
        current_diff = ema_20[-1] - ema_50[-1]
        prev_diff = ema_20[-2] - ema_50[-2]
        
        # Força da tendência
        trend_strength = (current_diff / ema_50[-1]) * 100
        
        if current_diff > 0 and prev_diff > 0:
            # EMA 20 acima de 50 (bullish)
            signal = 'bullish'
            score = min(trend_strength / 2, 0.3)  # Max 0.3
        elif current_diff < 0 and prev_diff < 0:
            # EMA 20 abaixo de 50 (bearish)
            signal = 'bearish'
            score = max(trend_strength / 2, -0.3)  # Min -0.3
        else:
            # Cruzamento ou lateral
            signal = 'neutral'
            score = 0
        
        ema_values = {
            'ema_20': float(ema_20[-1]),
            'ema_50': float(ema_50[-1])
        }
        
        return signal, score, ema_values
    
    def _analyze_rsi(self, candles: List[Dict]) -> tuple:
        """Analisa RSI para detectar força"""
        closes = np.array([float(c['close']) for c in candles])
        rsi = self._calculate_rsi(closes, self.rsi_period)
        
        current_rsi = rsi[-1]
        
        if current_rsi > 70:
            signal = 'bearish'  # Sobrecompra
            score = -0.2
        elif current_rsi > 55:
            signal = 'bullish'  # Força compradora
            score = 0.25
        elif current_rsi < 30:
            signal = 'bullish'  # Sobrevenda
            score = 0.2
        elif current_rsi < 45:
            signal = 'bearish'  # Força vendedora
            score = -0.25
        else:
            signal = 'neutral'
            score = 0
        
        return signal, score, float(current_rsi)
    
    def _analyze_volume(self, candles: List[Dict]) -> tuple:
        """Analisa volume para confirmar tendência"""
        volumes = np.array([float(c['volume']) for c in candles[-20:]])
        closes = np.array([float(c['close']) for c in candles[-20:]])
        
        avg_volume = np.mean(volumes[:-1])
        current_volume = volumes[-1]
        
        # Volume atual vs média
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        # Direção do preço
        price_change = (closes[-1] - closes[-2]) / closes[-2] if closes[-2] > 0 else 0
        
        if volume_ratio > 1.5 and price_change > 0:
            signal = 'bullish'
            score = 0.2
        elif volume_ratio > 1.5 and price_change < 0:
            signal = 'bearish'
            score = -0.2
        else:
            signal = 'neutral'
            score = 0
        
        return signal, score
    
    def _analyze_price_action(self, candles: List[Dict]) -> tuple:
        """Analisa price action recente"""
        closes = [float(c['close']) for c in candles]
        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        
        # Sequência de candles
        bullish_candles = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i-1])
        bearish_candles = len(closes) - 1 - bullish_candles
        
        # Higher highs / Lower lows
        higher_highs = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
        lower_lows = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i-1])
        
        score = 0
        if bullish_candles >= 3 and higher_highs >= 2:
            signal = 'bullish'
            score = 0.25
        elif bearish_candles >= 3 and lower_lows >= 2:
            signal = 'bearish'
            score = -0.25
        else:
            signal = 'neutral'
            score = 0
        
        return signal, score
    
    def _calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calcula EMA (Exponential Moving Average)"""
        ema = np.zeros_like(data)
        ema[0] = data[0]
        multiplier = 2 / (period + 1)
        
        for i in range(1, len(data)):
            ema[i] = (data[i] * multiplier) + (ema[i-1] * (1 - multiplier))
        
        return ema
    
    def _calculate_rsi(self, data: np.ndarray, period: int = 14) -> np.ndarray:
        """Calcula RSI (Relative Strength Index)"""
        deltas = np.diff(data)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.zeros(len(data))
        avg_loss = np.zeros(len(data))
        
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])
        
        for i in range(period + 1, len(data)):
            avg_gain[i] = (avg_gain[i-1] * (period - 1) + gains[i-1]) / period
            avg_loss[i] = (avg_loss[i-1] * (period - 1) + losses[i-1]) / period
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _neutral_response(self) -> Dict:
        """Resposta neutra quando não há dados suficientes"""
        return {
            'direction': Direction.NEUTRAL,
            'confidence': 0.0,
            'signals': {},
            'score': 0.0,
            'indicators': {}
        }