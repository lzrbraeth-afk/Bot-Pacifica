"""
Technical Analyzer - Análise de Indicadores Técnicos
Calcula e analisa: RSI, EMA, ADX, MACD, Bollinger Bands, ATR
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class TechnicalAnalyzer:
    """
    Analisa indicadores técnicos e gera scores
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def analyze(self, ohlcv_data: pd.DataFrame) -> Dict:
        """
        Análise técnica completa
        
        Args:
            ohlcv_data: DataFrame com colunas ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        Returns:
            Dict com score e detalhes dos indicadores
        """
        try:
            # Calcular todos os indicadores
            indicators = self._calculate_all_indicators(ohlcv_data)
            
            # Calcular score baseado nos indicadores
            score_result = self._calculate_technical_score(indicators)
            
            return score_result
            
        except Exception as e:
            self.logger.error(f"Erro na análise técnica: {e}")
            return self._empty_result()
    
    def _calculate_all_indicators(self, df: pd.DataFrame) -> Dict:
        """Calcula todos os indicadores técnicos"""
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        indicators = {}
        
        # RSI (14)
        indicators['rsi_14'] = self._calculate_rsi(close, period=14)
        
        # EMAs
        indicators['ema_9'] = self._calculate_ema(close, period=9)
        indicators['ema_21'] = self._calculate_ema(close, period=21)
        indicators['ema_20'] = self._calculate_ema(close, period=20)
        indicators['ema_50'] = self._calculate_ema(close, period=50)
        
        # ADX (14)
        indicators['adx'] = self._calculate_adx(high, low, close, period=14)
        
        # MACD (12, 26, 9)
        macd_result = self._calculate_macd(close)
        indicators['macd'] = macd_result['macd']
        indicators['macd_signal'] = macd_result['signal']
        indicators['macd_histogram'] = macd_result['histogram']
        
        # Bollinger Bands (20, 2)
        bb_result = self._calculate_bollinger_bands(close, period=20, std_dev=2)
        indicators['bb_upper'] = bb_result['upper']
        indicators['bb_middle'] = bb_result['middle']
        indicators['bb_lower'] = bb_result['lower']
        indicators['bb_width'] = bb_result['width']
        
        # ATR (14)
        indicators['atr'] = self._calculate_atr(high, low, close, period=14)
        indicators['atr_percentage'] = (indicators['atr'] / close[-1]) * 100
        
        # Preço atual
        indicators['current_price'] = close[-1]
        
        return indicators
    
    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calcula RSI (Relative Strength Index)"""
        
        if len(prices) < period + 1:
            return 50.0  # Neutro se não houver dados suficientes
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """Calcula EMA (Exponential Moving Average)"""
        
        if len(prices) < period:
            return float(np.mean(prices))
        
        multiplier = 2 / (period + 1)
        ema = np.mean(prices[:period])  # SMA inicial
        
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return float(ema)
    
    def _calculate_adx(self, high: np.ndarray, low: np.ndarray, close: np.ndarray, 
                       period: int = 14) -> float:
        """
        Calcula ADX (Average Directional Index)
        Mede a força da tendência
        """
        
        if len(high) < period + 1:
            return 0.0
        
        # True Range
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        
        # Directional Movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Smoothed
        atr = np.mean(tr[-period:])
        plus_di = (np.mean(plus_dm[-period:]) / atr) * 100 if atr > 0 else 0
        minus_di = (np.mean(minus_dm[-period:]) / atr) * 100 if atr > 0 else 0
        
        # ADX
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100 if (plus_di + minus_di) > 0 else 0
        
        return float(dx)
    
    def _calculate_macd(self, prices: np.ndarray, 
                       fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """Calcula MACD (Moving Average Convergence Divergence)"""
        
        if len(prices) < slow:
            return {'macd': 0.0, 'signal': 0.0, 'histogram': 0.0}
        
        ema_fast = self._calculate_ema(prices, fast)
        ema_slow = self._calculate_ema(prices, slow)
        
        macd = ema_fast - ema_slow
        
        # Signal line (EMA do MACD)
        # Simplificado: usando apenas o valor final
        signal_line = macd * 0.9  # Aproximação
        
        histogram = macd - signal_line
        
        return {
            'macd': float(macd),
            'signal': float(signal_line),
            'histogram': float(histogram)
        }
    
    def _calculate_bollinger_bands(self, prices: np.ndarray, 
                                   period: int = 20, std_dev: int = 2) -> Dict:
        """Calcula Bandas de Bollinger"""
        
        if len(prices) < period:
            middle = float(np.mean(prices))
            return {
                'upper': middle * 1.02,
                'middle': middle,
                'lower': middle * 0.98,
                'width': 0.04
            }
        
        middle = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        width = (upper - lower) / middle
        
        return {
            'upper': float(upper),
            'middle': float(middle),
            'lower': float(lower),
            'width': float(width)
        }
    
    def _calculate_atr(self, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                      period: int = 14) -> float:
        """Calcula ATR (Average True Range)"""
        
        if len(high) < period + 1:
            return float(np.mean(high - low))
        
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = np.mean(tr[-period:])
        
        return float(atr)
    
    def _calculate_technical_score(self, indicators: Dict) -> Dict:
        """
        Calcula score técnico baseado nos indicadores
        Score: 0-10
        """
        
        score = 0.0
        max_score = 10.0
        details = {}
        
        # ==================
        # RSI (2 pontos)
        # ==================
        rsi = indicators['rsi_14']
        
        if 40 <= rsi <= 60:
            score += 2.0
            details['rsi'] = {'value': rsi, 'status': '🟢 Neutro', 'score': 2.0}
        elif 30 <= rsi < 40:
            score += 1.5
            details['rsi'] = {'value': rsi, 'status': '🟡 Oversold (oportunidade)', 'score': 1.5}
        elif 60 < rsi <= 70:
            score += 1.5
            details['rsi'] = {'value': rsi, 'status': '🟡 Overbought (cautela)', 'score': 1.5}
        elif rsi < 30:
            score += 1.0
            details['rsi'] = {'value': rsi, 'status': '🟠 Muito oversold', 'score': 1.0}
        else:
            score += 1.0
            details['rsi'] = {'value': rsi, 'status': '🔴 Muito overbought', 'score': 1.0}
        
        # ==================
        # EMA Crossover (2.5 pontos)
        # ==================
        ema9 = indicators['ema_9']
        ema21 = indicators['ema_21']
        price = indicators['current_price']
        
        if ema9 > ema21 and price > ema9:
            score += 2.5
            details['ema'] = {
                'ema9': ema9, 'ema21': ema21, 'price': price,
                'status': '🟢 Bullish (9>21, price>9)', 'score': 2.5
            }
        elif ema9 < ema21 and price < ema9:
            score += 2.5
            details['ema'] = {
                'ema9': ema9, 'ema21': ema21, 'price': price,
                'status': '🟢 Bearish (9<21, price<9)', 'score': 2.5
            }
        elif ema9 > ema21:
            score += 1.5
            details['ema'] = {
                'ema9': ema9, 'ema21': ema21, 'price': price,
                'status': '🟡 Bullish mas price abaixo', 'score': 1.5
            }
        else:
            score += 0.5
            details['ema'] = {
                'ema9': ema9, 'ema21': ema21, 'price': price,
                'status': '🔴 Indefinido', 'score': 0.5
            }
        
        # ==================
        # ADX (2.5 pontos)
        # ==================
        adx = indicators['adx']
        
        if adx >= 35:
            score += 2.5
            details['adx'] = {'value': adx, 'status': f'🟢 Tendência forte', 'score': 2.5}
        elif adx >= 25:
            score += 2.0
            details['adx'] = {'value': adx, 'status': f'🟡 Tendência moderada', 'score': 2.0}
        elif adx >= 20:
            score += 1.0
            details['adx'] = {'value': adx, 'status': f'🟠 Tendência fraca', 'score': 1.0}
        else:
            score += 0.5
            details['adx'] = {'value': adx, 'status': f'🔴 Sem tendência', 'score': 0.5}
        
        # ==================
        # MACD (1.5 pontos)
        # ==================
        macd = indicators['macd']
        macd_signal = indicators['macd_signal']
        
        if macd > macd_signal and macd > 0:
            score += 1.5
            details['macd'] = {
                'macd': macd, 'signal': macd_signal,
                'status': '🟢 Bullish confirmado', 'score': 1.5
            }
        elif macd < macd_signal and macd < 0:
            score += 1.5
            details['macd'] = {
                'macd': macd, 'signal': macd_signal,
                'status': '🟢 Bearish confirmado', 'score': 1.5
            }
        elif macd > macd_signal:
            score += 1.0
            details['macd'] = {
                'macd': macd, 'signal': macd_signal,
                'status': '🟡 Bullish fraco', 'score': 1.0
            }
        else:
            score += 1.0
            details['macd'] = {
                'macd': macd, 'signal': macd_signal,
                'status': '🟡 Bearish fraco', 'score': 1.0
            }
        
        # ==================
        # Bollinger Bands (1.5 pontos)
        # ==================
        bb_upper = indicators['bb_upper']
        bb_lower = indicators['bb_lower']
        bb_middle = indicators['bb_middle']
        
        price_position = (price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
        
        if price < bb_lower:
            score += 1.5
            details['bollinger'] = {
                'upper': bb_upper, 'middle': bb_middle, 'lower': bb_lower,
                'status': '🟢 Oversold (price < lower)', 'score': 1.5
            }
        elif price > bb_upper:
            score += 1.5
            details['bollinger'] = {
                'upper': bb_upper, 'middle': bb_middle, 'lower': bb_lower,
                'status': '🟢 Overbought (price > upper)', 'score': 1.5
            }
        elif indicators['bb_width'] < 0.02:
            score += 1.0
            details['bollinger'] = {
                'upper': bb_upper, 'middle': bb_middle, 'lower': bb_lower,
                'status': '🟡 Squeeze (baixa volatilidade)', 'score': 1.0
            }
        else:
            score += 1.2
            details['bollinger'] = {
                'upper': bb_upper, 'middle': bb_middle, 'lower': bb_lower,
                'status': '🟢 Normal', 'score': 1.2
            }
        
        # Status final
        percentage = (score / max_score) * 100
        
        if score >= 7.5:
            status = '🟢 FAVORÁVEL'
        elif score >= 5.0:
            status = '🟡 NEUTRO'
        else:
            status = '🔴 DESFAVORÁVEL'
        
        return {
            'score': round(score, 2),
            'max_score': max_score,
            'percentage': round(percentage, 1),
            'status': status,
            'details': details,
            'indicators': indicators
        }
    
    def _empty_result(self) -> Dict:
        """Retorna resultado vazio em caso de erro"""
        return {
            'score': 0.0,
            'max_score': 10.0,
            'percentage': 0.0,
            'status': '🔴 ERRO',
            'details': {},
            'indicators': {}
        }


# Testes unitários básicos
if __name__ == '__main__':
    # Criar dados de teste
    np.random.seed(42)
    n_candles = 100
    
    test_df = pd.DataFrame({
        'timestamp': pd.date_range(start='2025-01-01', periods=n_candles, freq='5min'),
        'open': 43000 + np.random.randn(n_candles) * 100,
        'high': 43100 + np.random.randn(n_candles) * 100,
        'low': 42900 + np.random.randn(n_candles) * 100,
        'close': 43000 + np.random.randn(n_candles) * 100,
        'volume': 1000000 + np.random.randn(n_candles) * 100000
    })
    
    analyzer = TechnicalAnalyzer()
    result = analyzer.analyze(test_df)
    
    print("="*60)
    print("TESTE: Technical Analyzer")
    print("="*60)
    print(f"Score: {result['score']}/{result['max_score']}")
    print(f"Percentual: {result['percentage']}%")
    print(f"Status: {result['status']}")
    print("\nDetalhes:")
    for key, value in result['details'].items():
        print(f"  {key}: {value}")
    print("="*60)
