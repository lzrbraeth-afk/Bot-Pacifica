"""
Volume Analyzer - Análise de Volume e Order Flow
Calcula: Volume absoluto, Delta, Volume Profile, POC (Point of Control)
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class VolumeAnalyzer:
    """
    Analisa volume, delta e volume profile
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def analyze(self, ohlcv_data: pd.DataFrame, trades_data: Optional[List[Dict]] = None) -> Dict:
        """
        Análise completa de volume
        
        Args:
            ohlcv_data: DataFrame com OHLCV
            trades_data: Lista de trades individuais (opcional, para delta preciso)
        
        Returns:
            Dict com score e análise de volume
        """
        try:
            # Calcular métricas de volume
            volume_metrics = self._calculate_volume_metrics(ohlcv_data)
            
            # Calcular delta (se houver trades data)
            if trades_data:
                volume_metrics['delta'] = self._calculate_volume_delta(trades_data)
            else:
                # Estimativa do delta baseado em OHLC
                volume_metrics['delta'] = self._estimate_volume_delta(ohlcv_data)
            
            # Calcular Volume Profile
            volume_profile = self._calculate_volume_profile(ohlcv_data)
            volume_metrics['profile'] = volume_profile
            
            # Calcular score
            score_result = self._calculate_volume_score(volume_metrics, volume_profile)
            
            return score_result
            
        except Exception as e:
            self.logger.error(f"Erro na análise de volume: {e}")
            return self._empty_result()
    
    def _calculate_volume_metrics(self, df: pd.DataFrame) -> Dict:
        """Calcula métricas básicas de volume"""
        
        volume = df['volume'].values
        
        # Volume atual
        current_volume = volume[-1]
        
        # Média móvel de volume (20 períodos)
        if len(volume) >= 20:
            volume_ma_20 = np.mean(volume[-20:])
        else:
            volume_ma_20 = np.mean(volume)
        
        # Ratio do volume atual vs média
        volume_ratio = current_volume / volume_ma_20 if volume_ma_20 > 0 else 1.0
        
        # Volume das últimas N candles
        volume_1h = np.sum(volume[-12:]) if len(volume) >= 12 else np.sum(volume)  # 12x5min = 1h
        volume_4h = np.sum(volume[-48:]) if len(volume) >= 48 else np.sum(volume)
        volume_24h = np.sum(volume[-288:]) if len(volume) >= 288 else np.sum(volume)
        
        return {
            'current': float(current_volume),
            'ma_20': float(volume_ma_20),
            'ratio': float(volume_ratio),
            'volume_1h': float(volume_1h),
            'volume_4h': float(volume_4h),
            'volume_24h': float(volume_24h)
        }
    
    def _calculate_volume_delta(self, trades: List[Dict]) -> float:
        """
        Calcula delta de volume (compras - vendas) de trades reais
        
        Args:
            trades: Lista com {'side': 'buy'|'sell', 'size': float}
        """
        
        buy_volume = sum(t['size'] for t in trades if t.get('side') == 'buy')
        sell_volume = sum(t['size'] for t in trades if t.get('side') == 'sell')
        
        delta = buy_volume - sell_volume
        
        return float(delta)
    
    def _estimate_volume_delta(self, df: pd.DataFrame) -> float:
        """
        Estima delta de volume baseado em OHLC
        Método simplificado quando não há dados de trades
        """
        
        if len(df) < 2:
            return 0.0
        
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        
        # Se fechou acima da abertura = mais compra
        # Se fechou abaixo da abertura = mais venda
        
        close_change = last_candle['close'] - last_candle['open']
        volume = last_candle['volume']
        
        # Proporção bullish/bearish
        candle_range = last_candle['high'] - last_candle['low']
        if candle_range > 0:
            bullish_ratio = (last_candle['close'] - last_candle['low']) / candle_range
        else:
            bullish_ratio = 0.5
        
        # Estimativa do delta
        estimated_delta = volume * (bullish_ratio - 0.5) * 2
        
        return float(estimated_delta)
    
    def _calculate_volume_profile(self, df: pd.DataFrame, num_levels: int = 30) -> Dict:
        """
        Calcula Volume Profile
        Identifica POC (Point of Control), VAH (Value Area High), VAL (Value Area Low)
        """
        
        if len(df) < 2:
            return {
                'poc': df['close'].iloc[-1] if len(df) > 0 else 0,
                'vah': 0,
                'val': 0,
                'levels': []
            }
        
        # Determinar range de preços
        all_highs = df['high'].values
        all_lows = df['low'].values
        all_volumes = df['volume'].values
        
        price_min = np.min(all_lows)
        price_max = np.max(all_highs)
        
        # Criar bins de preço
        price_bins = np.linspace(price_min, price_max, num_levels + 1)
        
        # Distribuir volume por nível de preço
        volume_per_level = defaultdict(float)
        
        for i in range(len(df)):
            candle_low = all_lows[i]
            candle_high = all_highs[i]
            candle_volume = all_volumes[i]
            
            # Distribuir volume desta candle pelos bins que ela toca
            for j in range(len(price_bins) - 1):
                level_low = price_bins[j]
                level_high = price_bins[j + 1]
                level_mid = (level_low + level_high) / 2
                
                # Verificar se a candle toca este nível
                if candle_low <= level_high and candle_high >= level_low:
                    # Proporção do volume que vai para este nível
                    overlap_low = max(candle_low, level_low)
                    overlap_high = min(candle_high, level_high)
                    overlap_range = overlap_high - overlap_low
                    candle_range = candle_high - candle_low
                    
                    if candle_range > 0:
                        proportion = overlap_range / candle_range
                    else:
                        proportion = 1.0
                    
                    volume_per_level[level_mid] += candle_volume * proportion
        
        # Encontrar POC (Point of Control) - preço com maior volume
        if volume_per_level:
            poc_price = max(volume_per_level, key=volume_per_level.get)
            poc_volume = volume_per_level[poc_price]
        else:
            poc_price = (price_min + price_max) / 2
            poc_volume = 0
        
        # Calcular Value Area (70% do volume)
        sorted_levels = sorted(volume_per_level.items(), key=lambda x: x[1], reverse=True)
        total_volume = sum(volume_per_level.values())
        value_area_volume = total_volume * 0.70
        
        cumulative_volume = 0
        value_area_prices = []
        
        for price, volume in sorted_levels:
            cumulative_volume += volume
            value_area_prices.append(price)
            if cumulative_volume >= value_area_volume:
                break
        
        vah = max(value_area_prices) if value_area_prices else price_max
        val = min(value_area_prices) if value_area_prices else price_min
        
        # Formatar níveis para retorno
        levels = [
            {'price': float(price), 'volume': float(volume)}
            for price, volume in sorted(volume_per_level.items())
        ]
        
        return {
            'poc': float(poc_price),
            'poc_volume': float(poc_volume),
            'vah': float(vah),
            'val': float(val),
            'total_volume': float(total_volume),
            'levels': levels
        }
    
    def _calculate_volume_score(self, volume_metrics: Dict, volume_profile: Dict) -> Dict:
        """
        Calcula score de volume (0-10)
        """
        
        score = 0.0
        max_score = 10.0
        details = {}
        
        # ==================
        # Volume Absoluto vs Média (3 pontos)
        # ==================
        volume_ratio = volume_metrics['ratio']
        
        if volume_ratio >= 1.5:
            score += 3.0
            details['volume_abs'] = {
                'ratio': volume_ratio,
                'status': f'🟢 Alto ({volume_ratio:.2f}x média)',
                'score': 3.0
            }
        elif volume_ratio >= 1.2:
            score += 2.5
            details['volume_abs'] = {
                'ratio': volume_ratio,
                'status': f'🟡 Acima da média ({volume_ratio:.2f}x)',
                'score': 2.5
            }
        elif volume_ratio >= 0.8:
            score += 1.5
            details['volume_abs'] = {
                'ratio': volume_ratio,
                'status': f'🟠 Normal ({volume_ratio:.2f}x)',
                'score': 1.5
            }
        else:
            score += 0.5
            details['volume_abs'] = {
                'ratio': volume_ratio,
                'status': f'🔴 Baixo ({volume_ratio:.2f}x)',
                'score': 0.5
            }
        
        # ==================
        # Delta Volume (3 pontos)
        # ==================
        volume_delta = volume_metrics['delta']
        current_volume = volume_metrics['current']
        
        delta_ratio = abs(volume_delta) / current_volume if current_volume > 0 else 0
        
        if delta_ratio > 0.3:
            score += 3.0
            if volume_delta > 0:
                details['delta'] = {
                    'value': volume_delta,
                    'status': f'🟢 Comprador forte (+{volume_delta:,.0f})',
                    'score': 3.0
                }
            else:
                details['delta'] = {
                    'value': volume_delta,
                    'status': f'🟢 Vendedor forte ({volume_delta:,.0f})',
                    'score': 3.0
                }
        elif delta_ratio > 0.15:
            score += 2.0
            details['delta'] = {
                'value': volume_delta,
                'status': f'🟡 Moderado ({volume_delta:+,.0f})',
                'score': 2.0
            }
        else:
            score += 1.0
            details['delta'] = {
                'value': volume_delta,
                'status': f'🟠 Neutro ({volume_delta:+,.0f})',
                'score': 1.0
            }
        
        # ==================
        # Volume Profile - Posição do Preço (2.5 pontos)
        # ==================
        # Assumir que teremos o preço atual do contexto
        # Por enquanto usar o POC como referência
        
        poc = volume_profile['poc']
        vah = volume_profile['vah']
        val = volume_profile['val']
        
        # Sem preço atual, assumir score médio
        score += 2.0
        details['profile'] = {
            'poc': poc,
            'vah': vah,
            'val': val,
            'status': f'🟡 POC: ${poc:,.0f}',
            'score': 2.0
        }
        
        # ==================
        # Confirmação de Rompimento (1.5 pontos)
        # ==================
        if volume_ratio > 1.3 and delta_ratio > 0.2:
            score += 1.5
            details['breakout'] = {
                'status': '🟢 Volume confirma rompimento',
                'score': 1.5
            }
        else:
            score += 0.5
            details['breakout'] = {
                'status': '🟠 Sem confirmação de rompimento',
                'score': 0.5
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
            'metrics': volume_metrics,
            'profile': volume_profile
        }
    
    def _empty_result(self) -> Dict:
        """Retorna resultado vazio em caso de erro"""
        return {
            'score': 0.0,
            'max_score': 10.0,
            'percentage': 0.0,
            'status': '🔴 ERRO',
            'details': {},
            'metrics': {},
            'profile': {}
        }


# Teste unitário
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
    
    analyzer = VolumeAnalyzer()
    result = analyzer.analyze(test_df)
    
    print("="*60)
    print("TESTE: Volume Analyzer")
    print("="*60)
    print(f"Score: {result['score']}/{result['max_score']}")
    print(f"Percentual: {result['percentage']}%")
    print(f"Status: {result['status']}")
    print("\nDetalhes:")
    for key, value in result['details'].items():
        print(f"  {key}: {value}")
    print("\nVolume Profile:")
    print(f"  POC: ${result['profile']['poc']:,.2f}")
    print(f"  VAH: ${result['profile']['vah']:,.2f}")
    print(f"  VAL: ${result['profile']['val']:,.2f}")
    print("="*60)
