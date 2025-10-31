"""
Structure Analyzer - Análise de Estrutura de Mercado
Identifica: Padrões HH/HL/LH/LL, Suporte/Resistência, Divergências
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from scipy.signal import find_peaks


class StructureAnalyzer:
    """
    Analisa estrutura de mercado e padrões
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def analyze(self, ohlcv_data: pd.DataFrame, rsi_values: Optional[np.ndarray] = None) -> Dict:
        """
        Análise completa de estrutura
        
        Args:
            ohlcv_data: DataFrame com OHLCV
            rsi_values: Array com valores de RSI (para divergências)
        
        Returns:
            Dict com score e análise de estrutura
        """
        try:
            # Identificar swing points (topos e fundos)
            swings = self._identify_swing_points(ohlcv_data)
            
            # Determinar padrão de mercado
            pattern = self._identify_market_pattern(swings)
            
            # Calcular suporte e resistência
            support_resistance = self._calculate_support_resistance(ohlcv_data, swings)
            
            # Verificar divergências (se tiver RSI)
            divergence = None
            if rsi_values is not None and len(rsi_values) >= len(ohlcv_data):
                divergence = self._check_divergence(ohlcv_data, rsi_values, swings)
            
            # Calcular score
            score_result = self._calculate_structure_score(
                ohlcv_data, pattern, support_resistance, divergence
            )
            
            return score_result
            
        except Exception as e:
            self.logger.error(f"Erro na análise de estrutura: {e}")
            return self._empty_result()
    
    def _identify_swing_points(self, df: pd.DataFrame, 
                               prominence: float = 50) -> Dict:
        """
        Identifica pontos de swing (topos e fundos)
        
        Returns:
            Dict com {'highs': [...], 'lows': [...]}
        """
        
        highs = df['high'].values
        lows = df['low'].values
        
        # Encontrar topos (peaks)
        peak_indices, _ = find_peaks(highs, prominence=prominence)
        
        # Encontrar fundos (troughs) - inverter o sinal
        trough_indices, _ = find_peaks(-lows, prominence=prominence)
        
        swing_highs = [
            {'index': int(i), 'price': float(highs[i]), 'timestamp': df.iloc[i]['timestamp']}
            for i in peak_indices
        ]
        
        swing_lows = [
            {'index': int(i), 'price': float(lows[i]), 'timestamp': df.iloc[i]['timestamp']}
            for i in trough_indices
        ]
        
        return {
            'highs': swing_highs,
            'lows': swing_lows
        }
    
    def _identify_market_pattern(self, swings: Dict) -> str:
        """
        Identifica padrão de mercado: HH/HL (uptrend), LH/LL (downtrend), consolidation
        """
        
        highs = swings['highs']
        lows = swings['lows']
        
        if len(highs) < 2 or len(lows) < 2:
            return 'indefinido'
        
        # Pegar últimos 3 topos e 3 fundos
        recent_highs = highs[-3:] if len(highs) >= 3 else highs
        recent_lows = lows[-3:] if len(lows) >= 3 else lows
        
        # Verificar Higher Highs (HH)
        hh = all(
            recent_highs[i]['price'] > recent_highs[i-1]['price']
            for i in range(1, len(recent_highs))
        )
        
        # Verificar Higher Lows (HL)
        hl = all(
            recent_lows[i]['price'] > recent_lows[i-1]['price']
            for i in range(1, len(recent_lows))
        )
        
        # Verificar Lower Highs (LH)
        lh = all(
            recent_highs[i]['price'] < recent_highs[i-1]['price']
            for i in range(1, len(recent_highs))
        )
        
        # Verificar Lower Lows (LL)
        ll = all(
            recent_lows[i]['price'] < recent_lows[i-1]['price']
            for i in range(1, len(recent_lows))
        )
        
        # Determinar padrão
        if hh and hl:
            return 'HH_HL'  # Uptrend
        elif lh and ll:
            return 'LH_LL'  # Downtrend
        elif not hh and not lh:
            return 'consolidation'
        else:
            return 'indefinido'
    
    def _calculate_support_resistance(self, df: pd.DataFrame, swings: Dict) -> Dict:
        """
        Calcula níveis de suporte e resistência baseados em swing points
        """
        
        current_price = df['close'].iloc[-1]
        
        highs = swings['highs']
        lows = swings['lows']
        
        # Extrair preços
        high_prices = [h['price'] for h in highs]
        low_prices = [l['price'] for l in lows]
        
        # Suportes: fundos abaixo do preço atual
        supports = [p for p in low_prices if p < current_price]
        supports_sorted = sorted(supports, reverse=True)  # Mais próximos primeiro
        
        # Resistências: topos acima do preço atual
        resistances = [p for p in high_prices if p > current_price]
        resistances_sorted = sorted(resistances)  # Mais próximos primeiro
        
        # Pegar os mais relevantes
        nearest_support = supports_sorted[0] if supports_sorted else current_price * 0.98
        nearest_resistance = resistances_sorted[0] if resistances_sorted else current_price * 1.02
        
        # Calcular "força" do S/R baseado em quantas vezes foi testado
        support_strength = self._calculate_level_strength(df, nearest_support)
        resistance_strength = self._calculate_level_strength(df, nearest_resistance)
        
        return {
            'nearest_support': float(nearest_support),
            'support_strength': support_strength,
            'all_supports': [float(s) for s in supports_sorted[:5]],
            'nearest_resistance': float(nearest_resistance),
            'resistance_strength': resistance_strength,
            'all_resistances': [float(r) for r in resistances_sorted[:5]]
        }
    
    def _calculate_level_strength(self, df: pd.DataFrame, level: float, 
                                  tolerance: float = 0.005) -> str:
        """
        Calcula força de um nível S/R baseado em quantas vezes foi testado
        """
        
        touches = 0
        
        for _, row in df.iterrows():
            # Verificar se high ou low tocou o nível
            if abs(row['high'] - level) / level <= tolerance:
                touches += 1
            elif abs(row['low'] - level) / level <= tolerance:
                touches += 1
        
        if touches >= 3:
            return 'forte'
        elif touches >= 2:
            return 'moderado'
        else:
            return 'fraco'
    
    def _check_divergence(self, df: pd.DataFrame, rsi_values: np.ndarray, 
                         swings: Dict) -> Optional[str]:
        """
        Verifica divergências entre preço e RSI
        
        Returns:
            'bullish', 'bearish', 'hidden_bullish', 'hidden_bearish', ou None
        """
        
        if len(swings['highs']) < 2 or len(swings['lows']) < 2:
            return None
        
        # Pegar últimos 2 swing highs e lows
        last_2_highs = swings['highs'][-2:]
        last_2_lows = swings['lows'][-2:]
        
        # Divergência Bullish: preço faz LL mas RSI faz HL
        if len(last_2_lows) >= 2:
            price_ll = last_2_lows[1]['price'] < last_2_lows[0]['price']
            
            idx1 = last_2_lows[0]['index']
            idx2 = last_2_lows[1]['index']
            
            if idx2 < len(rsi_values):
                rsi_hl = rsi_values[idx2] > rsi_values[idx1]
                
                if price_ll and rsi_hl:
                    return 'bullish'
        
        # Divergência Bearish: preço faz HH mas RSI faz LH
        if len(last_2_highs) >= 2:
            price_hh = last_2_highs[1]['price'] > last_2_highs[0]['price']
            
            idx1 = last_2_highs[0]['index']
            idx2 = last_2_highs[1]['index']
            
            if idx2 < len(rsi_values):
                rsi_lh = rsi_values[idx2] < rsi_values[idx1]
                
                if price_hh and rsi_lh:
                    return 'bearish'
        
        # TODO: Implementar divergências ocultas
        
        return None
    
    def _calculate_structure_score(self, df: pd.DataFrame, pattern: str,
                                   sr: Dict, divergence: Optional[str]) -> Dict:
        """
        Calcula score de estrutura (0-10)
        """
        
        score = 0.0
        max_score = 10.0
        details = {}
        
        current_price = df['close'].iloc[-1]
        
        # ==================
        # Proximidade de S/R (4 pontos)
        # ==================
        nearest_support = sr['nearest_support']
        nearest_resistance = sr['nearest_resistance']
        
        dist_support = abs(current_price - nearest_support) / current_price
        dist_resistance = abs(current_price - nearest_resistance) / current_price
        
        if dist_support < 0.005:  # < 0.5%
            score += 4.0
            details['sr_proximity'] = {
                'support': nearest_support,
                'resistance': nearest_resistance,
                'status': f'🟢 Próximo suporte forte (${nearest_support:,.0f})',
                'score': 4.0
            }
        elif dist_resistance < 0.005:
            score += 4.0
            details['sr_proximity'] = {
                'support': nearest_support,
                'resistance': nearest_resistance,
                'status': f'🟢 Próximo resistência forte (${nearest_resistance:,.0f})',
                'score': 4.0
            }
        elif dist_support < 0.01:
            score += 3.0
            details['sr_proximity'] = {
                'support': nearest_support,
                'resistance': nearest_resistance,
                'status': f'🟡 Próximo suporte (${nearest_support:,.0f})',
                'score': 3.0
            }
        elif dist_resistance < 0.01:
            score += 3.0
            details['sr_proximity'] = {
                'support': nearest_support,
                'resistance': nearest_resistance,
                'status': f'🟡 Próximo resistência (${nearest_resistance:,.0f})',
                'score': 3.0
            }
        else:
            score += 2.0
            details['sr_proximity'] = {
                'support': nearest_support,
                'resistance': nearest_resistance,
                'status': '🟠 Longe de níveis chave',
                'score': 2.0
            }
        
        # ==================
        # Padrão HH/HL/LH/LL (3 pontos)
        # ==================
        if pattern == 'HH_HL':
            score += 3.0
            details['pattern'] = {
                'type': pattern,
                'status': '🟢 Uptrend (HH/HL)',
                'score': 3.0
            }
        elif pattern == 'LH_LL':
            score += 3.0
            details['pattern'] = {
                'type': pattern,
                'status': '🟢 Downtrend (LH/LL)',
                'score': 3.0
            }
        elif pattern == 'consolidation':
            score += 2.0
            details['pattern'] = {
                'type': pattern,
                'status': '🟡 Consolidação',
                'score': 2.0
            }
        else:
            score += 1.0
            details['pattern'] = {
                'type': pattern,
                'status': '🟠 Indefinido',
                'score': 1.0
            }
        
        # ==================
        # Divergência RSI (3 pontos)
        # ==================
        if divergence == 'bullish':
            score += 3.0
            details['divergence'] = {
                'type': divergence,
                'status': '🟢 Divergência bullish detectada',
                'score': 3.0
            }
        elif divergence == 'bearish':
            score += 3.0
            details['divergence'] = {
                'type': divergence,
                'status': '🟢 Divergência bearish detectada',
                'score': 3.0
            }
        elif divergence in ['hidden_bullish', 'hidden_bearish']:
            score += 2.0
            details['divergence'] = {
                'type': divergence,
                'status': f'🟡 Divergência oculta {divergence}',
                'score': 2.0
            }
        else:
            score += 1.5
            details['divergence'] = {
                'type': None,
                'status': '🟠 Sem divergência',
                'score': 1.5
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
            'pattern': pattern,
            'support_resistance': sr
        }
    
    def _empty_result(self) -> Dict:
        """Retorna resultado vazio em caso de erro"""
        return {
            'score': 0.0,
            'max_score': 10.0,
            'percentage': 0.0,
            'status': '🔴 ERRO',
            'details': {},
            'pattern': 'indefinido',
            'support_resistance': {}
        }


# Teste unitário
if __name__ == '__main__':
    # Criar dados de teste com uptrend
    np.random.seed(42)
    n_candles = 100
    
    # Simular uptrend
    base_price = 43000
    trend = np.linspace(0, 500, n_candles)
    noise = np.random.randn(n_candles) * 50
    
    closes = base_price + trend + noise
    
    test_df = pd.DataFrame({
        'timestamp': pd.date_range(start='2025-01-01', periods=n_candles, freq='5min'),
        'open': closes - 20,
        'high': closes + 50,
        'low': closes - 50,
        'close': closes,
        'volume': 1000000 + np.random.randn(n_candles) * 100000
    })
    
    # RSI simulado
    rsi_values = 50 + np.random.randn(n_candles) * 10
    
    analyzer = StructureAnalyzer()
    result = analyzer.analyze(test_df, rsi_values)
    
    print("="*60)
    print("TESTE: Structure Analyzer")
    print("="*60)
    print(f"Score: {result['score']}/{result['max_score']}")
    print(f"Percentual: {result['percentage']}%")
    print(f"Status: {result['status']}")
    print(f"Padrão: {result['pattern']}")
    print("\nDetalhes:")
    for key, value in result['details'].items():
        print(f"  {key}: {value}")
    print("\nSuportes:")
    print(f"  {result['support_resistance'].get('all_supports', [])[:3]}")
    print("Resistências:")
    print(f"  {result['support_resistance'].get('all_resistances', [])[:3]}")
    print("="*60)
