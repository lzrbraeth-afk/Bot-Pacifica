"""
Volatility Analyzer - Análise de Volatilidade com Bollinger Bands
Calcula: BBW (Bollinger Band Width), Compressão/Expansão, ATR, Status
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Optional


class VolatilityAnalyzer:
    """
    Analisa volatilidade usando Bollinger Bands e ATR
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        
    def analyze(self, ohlcv_data: pd.DataFrame, atr: float = None) -> Dict:
        """
        Análise completa de volatilidade
        
        Args:
            ohlcv_data: DataFrame com OHLCV
            atr: ATR já calculado (opcional)
        
        Returns:
            Dict com score e análise de volatilidade
        """
        try:
            if len(ohlcv_data) < 20:
                self.logger.warning("Dados insuficientes para análise de volatilidade")
                return self._empty_result()
            
            # Calcular Bollinger Bands
            bb_data = self._calculate_bollinger_bands(ohlcv_data)
            
            # Calcular BBW (Bollinger Band Width)
            bbw = self._calculate_bbw(bb_data)
            
            # Calcular histórico de BBW para detectar compressão
            bbw_history = self._calculate_bbw_history(ohlcv_data)
            
            # Detectar estado de volatilidade
            volatility_state = self._detect_volatility_state(bbw, bbw_history)
            
            # Calcular ATR se não fornecido
            if atr is None:
                atr = self._calculate_atr(ohlcv_data)
            
            # Detectar tendência do ATR
            atr_trend = self._calculate_atr_trend(ohlcv_data)
            
            # Calcular score de volatilidade
            score = self._calculate_volatility_score(volatility_state, bbw, atr)
            
            # Compilar resultado
            result = {
                'score': round(score, 1),
                'bollinger_bands': {
                    'upper': round(bb_data['upper'], 2),
                    'middle': round(bb_data['middle'], 2),
                    'lower': round(bb_data['lower'], 2),
                    'current_price': round(bb_data['current_price'], 2),
                    'position': bb_data['position']  # 'upper', 'middle', 'lower'
                },
                'bbw': {
                    'current': round(bbw, 4),
                    'percentile': round(volatility_state['bbw_percentile'], 1),
                    'status': volatility_state['status'],
                    'description': volatility_state['description']
                },
                'atr': {
                    'value': round(atr, 2),
                    'trend': atr_trend,
                    'symbol': '↑' if atr_trend > 0 else '↓' if atr_trend < 0 else '→'
                },
                'state': {
                    'emoji': volatility_state['emoji'],
                    'color': volatility_state['color'],
                    'signal': volatility_state['signal'],
                    'recommendation': volatility_state['recommendation']
                },
                'details': {
                    'compression_detected': volatility_state['compression'],
                    'expansion_detected': volatility_state['expansion'],
                    'high_volatility': volatility_state['high_vol']
                }
            }
            
            self.logger.debug(
                f"Volatilidade: {volatility_state['status']} - "
                f"BBW: {bbw:.4f} - ATR: {atr:.2f}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Erro na análise de volatilidade: {e}", exc_info=True)
            return self._empty_result()
    
    def _calculate_bollinger_bands(self, ohlcv_data: pd.DataFrame, 
                                   period: int = 20, std_dev: float = 2.0) -> Dict:
        """Calcula Bollinger Bands"""
        closes = ohlcv_data['close'].values
        
        # SMA (middle band)
        sma = np.mean(closes[-period:])
        
        # Standard deviation
        std = np.std(closes[-period:])
        
        # Upper e Lower bands
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        current_price = closes[-1]
        
        # Determinar posição do preço
        if current_price > upper:
            position = 'upper'
        elif current_price < lower:
            position = 'lower'
        else:
            position = 'middle'
        
        return {
            'upper': upper,
            'middle': sma,
            'lower': lower,
            'current_price': current_price,
            'position': position,
            'std': std
        }
    
    def _calculate_bbw(self, bb_data: Dict) -> float:
        """
        Calcula Bollinger Band Width (BBW)
        BBW = (Upper Band - Lower Band) / Middle Band
        """
        bbw = (bb_data['upper'] - bb_data['lower']) / bb_data['middle']
        return bbw
    
    def _calculate_bbw_history(self, ohlcv_data: pd.DataFrame, 
                               lookback: int = 100) -> np.ndarray:
        """Calcula histórico de BBW para comparação"""
        closes = ohlcv_data['close'].values
        period = 20
        
        if len(closes) < lookback + period:
            lookback = len(closes) - period
        
        bbw_values = []
        for i in range(lookback):
            window = closes[-(lookback-i+period):-(lookback-i) if lookback-i > 0 else None]
            if len(window) >= period:
                sma = np.mean(window[-period:])
                std = np.std(window[-period:])
                upper = sma + (2.0 * std)
                lower = sma - (2.0 * std)
                bbw = (upper - lower) / sma
                bbw_values.append(bbw)
        
        return np.array(bbw_values) if bbw_values else np.array([0.05])
    
    def _detect_volatility_state(self, current_bbw: float, 
                                 bbw_history: np.ndarray) -> Dict:
        """Detecta estado atual da volatilidade"""
        
        # Calcular percentil do BBW atual
        percentile = (np.sum(bbw_history < current_bbw) / len(bbw_history)) * 100
        
        # Estados de volatilidade
        compression = percentile < 20  # BBW nos 20% mais baixos
        expansion = percentile > 80     # BBW nos 20% mais altos
        high_vol = percentile > 90      # BBW extremamente alto
        
        # Determinar status
        if high_vol:
            status = "🔴 Alta"
            emoji = "🔴"
            color = "red"
            signal = "risk"
            description = "Volatilidade extrema - Risco elevado"
            recommendation = "Aguarde redução da volatilidade ou use SL mais amplo"
        elif expansion:
            status = "🟢 Expansão"
            emoji = "🟢"
            color = "green"
            signal = "opportunity"
            description = "Expansão de volatilidade - Oportunidade"
            recommendation = "Condições favoráveis para entrada em rompimentos"
        elif compression:
            status = "🟡 Compressão"
            emoji = "🟡"
            color = "yellow"
            signal = "potential"
            description = "Compressão detectada - Possível expansão futura"
            recommendation = "Prepare-se para possível movimento forte"
        else:
            status = "⚪ Neutro"
            emoji = "⚪"
            color = "gray"
            signal = "neutral"
            description = "Volatilidade normal"
            recommendation = "Aguarde sinais mais claros"
        
        return {
            'status': status,
            'emoji': emoji,
            'color': color,
            'signal': signal,
            'description': description,
            'recommendation': recommendation,
            'bbw_percentile': percentile,
            'compression': compression,
            'expansion': expansion,
            'high_vol': high_vol
        }
    
    def _calculate_atr(self, ohlcv_data: pd.DataFrame, period: int = 14) -> float:
        """Calcula ATR (Average True Range)"""
        high = ohlcv_data['high'].values
        low = ohlcv_data['low'].values
        close = ohlcv_data['close'].values
        
        if len(high) < period + 1:
            return 0.0
        
        # True Range
        tr_list = []
        for i in range(1, len(high)):
            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
            tr_list.append(tr)
        
        # ATR = média dos últimos N True Ranges
        atr = np.mean(tr_list[-period:])
        return atr
    
    def _calculate_atr_trend(self, ohlcv_data: pd.DataFrame, period: int = 14) -> int:
        """
        Calcula tendência do ATR
        Returns: 1 (subindo), -1 (descendo), 0 (estável)
        """
        high = ohlcv_data['high'].values
        low = ohlcv_data['low'].values
        close = ohlcv_data['close'].values
        
        if len(high) < period * 2:
            return 0
        
        # Calcular ATR atual e anterior
        atr_current = self._calculate_atr(ohlcv_data, period)
        
        # ATR de 5 períodos atrás
        ohlcv_prev = ohlcv_data.iloc[:-5]
        atr_previous = self._calculate_atr(ohlcv_prev, period) if len(ohlcv_prev) >= period else atr_current
        
        # Comparar
        if atr_current > atr_previous * 1.05:  # 5% maior
            return 1
        elif atr_current < atr_previous * 0.95:  # 5% menor
            return -1
        else:
            return 0
    
    def _calculate_volatility_score(self, volatility_state: Dict, 
                                    bbw: float, atr: float) -> float:
        """
        Calcula score de volatilidade (0-10)
        Volatilidade ideal: nem muito alta (risco), nem muito baixa (sem movimento)
        """
        
        score = 5.0  # Base neutra
        
        # Ajustar por estado
        if volatility_state['signal'] == 'opportunity':
            score += 3.0  # Expansão é bom
        elif volatility_state['signal'] == 'potential':
            score += 1.5  # Compressão tem potencial
        elif volatility_state['signal'] == 'risk':
            score -= 3.0  # Alta volatilidade = risco
        
        # Ajustar por BBW percentil
        percentile = volatility_state['bbw_percentile']
        if 30 < percentile < 70:
            score += 1.0  # Faixa ideal
        
        # Limitar entre 0 e 10
        score = max(0.0, min(10.0, score))
        
        return score
    
    def _empty_result(self) -> Dict:
        """Retorna resultado vazio em caso de erro"""
        return {
            'score': 5.0,
            'bollinger_bands': {},
            'bbw': {},
            'atr': {},
            'state': {
                'emoji': '⚪',
                'color': 'gray',
                'signal': 'neutral',
                'recommendation': 'Dados insuficientes'
            },
            'details': {}
        }


# Teste
if __name__ == '__main__':
    # Dados de teste
    np.random.seed(42)
    n_candles = 100
    
    test_ohlcv = pd.DataFrame({
        'timestamp': pd.date_range(start='2025-01-01', periods=n_candles, freq='5min'),
        'open': 43000 + np.random.randn(n_candles) * 100,
        'high': 43100 + np.random.randn(n_candles) * 100,
        'low': 42900 + np.random.randn(n_candles) * 100,
        'close': 43000 + np.random.randn(n_candles) * 100,
        'volume': 1000000 + np.random.randn(n_candles) * 100000
    })
    
    analyzer = VolatilityAnalyzer()
    result = analyzer.analyze(test_ohlcv)
    
    print("="*60)
    print("TESTE: Volatility Analyzer")
    print("="*60)
    print(f"Score: {result['score']}/10")
    print(f"Status: {result['state']['emoji']} {result['bbw']['status']}")
    print(f"BBW: {result['bbw']['current']:.4f} (Percentil {result['bbw']['percentile']:.1f}%)")
    print(f"ATR: {result['atr']['value']:.2f} {result['atr']['symbol']}")
    print(f"Descrição: {result['bbw']['description']}")
    print(f"Recomendação: {result['state']['recommendation']}")
    print("="*60)
