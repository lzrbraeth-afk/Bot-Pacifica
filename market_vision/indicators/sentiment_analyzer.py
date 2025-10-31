"""
Sentiment Analyzer - Análise de Sentimento de Mercado
Analisa: Funding Rate, Open Interest, Orderbook Imbalance, Long/Short Ratio
"""

import logging
import numpy as np
from typing import Dict, Optional


class SentimentAnalyzer:
    """
    Analisa indicadores de sentimento do mercado
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def analyze(self, market_data: Dict) -> Dict:
        """
        Análise completa de sentimento
        
        Args:
            market_data: Dict com {
                'funding_rate': float,
                'oi_change_24h': float,
                'orderbook': {'bids': [...], 'asks': [...]},
                'long_short_ratio': float (opcional)
            }
        
        Returns:
            Dict com score e análise de sentimento
        """
        try:
            # Calcular score de sentimento
            score_result = self._calculate_sentiment_score(market_data)
            
            return score_result
            
        except Exception as e:
            self.logger.error(f"Erro na análise de sentimento: {e}")
            return self._empty_result()
    
    def _calculate_bid_ask_ratio(self, orderbook: Dict, depth_levels: int = 10) -> float:
        """
        Calcula ratio Bid/Ask baseado no orderbook
        
        Args:
            orderbook: {'bids': [[price, size], ...], 'asks': [[price, size], ...]}
            depth_levels: Quantos níveis considerar
        
        Returns:
            Ratio Bid/Ask (volume de compra / volume de venda)
        """
        
        if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
            return 1.0  # Neutro se não houver dados
        
        bids = orderbook['bids'][:depth_levels]
        asks = orderbook['asks'][:depth_levels]
        
        # Somar volumes com tratamento de erro
        bid_volume = 0.0
        ask_volume = 0.0
        
        try:
            for bid in bids:
                if len(bid) >= 2 and bid[1] is not None:
                    bid_volume += float(bid[1])
        except (ValueError, TypeError):
            pass
            
        try:
            for ask in asks:
                if len(ask) >= 2 and ask[1] is not None:
                    ask_volume += float(ask[1])
        except (ValueError, TypeError):
            pass
        
        if ask_volume == 0:
            return 2.0 if bid_volume > 0 else 1.0  # Muito bullish ou neutro
        
        ratio = bid_volume / ask_volume
        
        return float(ratio)
    
    def _calculate_sentiment_score(self, market_data: Dict) -> Dict:
        """
        Calcula score de sentimento (0-10)
        """
        
        score = 0.0
        max_score = 10.0
        details = {}
        
        # ==================
        # Funding Rate (3 pontos)
        # ==================
        funding = market_data.get('funding_rate', 0.0)
        
        # Garantir que funding não seja None e seja convertido para float
        if funding is None:
            funding = 0.0
        try:
            funding = float(funding)
        except (ValueError, TypeError):
            funding = 0.0
        
        if -0.01 <= funding <= 0.01:
            score += 3.0
            details['funding'] = {
                'value': funding,
                'status': f'🟢 Neutro ({funding:.4f}%)',
                'score': 3.0
            }
        elif 0.01 < funding <= 0.05:
            score += 2.0
            details['funding'] = {
                'value': funding,
                'status': f'🟡 Bullish moderado ({funding:.4f}%)',
                'score': 2.0
            }
        elif -0.05 <= funding < -0.01:
            score += 2.0
            details['funding'] = {
                'value': funding,
                'status': f'🟡 Bearish moderado ({funding:.4f}%)',
                'score': 2.0
            }
        elif funding > 0.05:
            score += 1.0
            details['funding'] = {
                'value': funding,
                'status': f'🔴 Muito bullish - reversão? ({funding:.4f}%)',
                'score': 1.0
            }
        else:
            score += 1.0
            details['funding'] = {
                'value': funding,
                'status': f'🔴 Muito bearish - reversão? ({funding:.4f}%)',
                'score': 1.0
            }
        
        # ==================
        # Open Interest (2.5 pontos)
        # ==================
        oi_change = market_data.get('oi_change_24h', 0.0)
        
        # Garantir que oi_change não seja None e seja convertido para float
        if oi_change is None:
            oi_change = 0.0
        try:
            oi_change = float(oi_change)
        except (ValueError, TypeError):
            oi_change = 0.0
        
        if oi_change > 0.1:  # +10%
            score += 2.5
            details['open_interest'] = {
                'change': oi_change,
                'status': f'🟢 Crescendo forte (+{oi_change*100:.1f}%)',
                'score': 2.5
            }
        elif oi_change > 0.05:
            score += 2.0
            details['open_interest'] = {
                'change': oi_change,
                'status': f'🟡 Crescendo (+{oi_change*100:.1f}%)',
                'score': 2.0
            }
        elif oi_change > -0.05:
            score += 1.5
            details['open_interest'] = {
                'change': oi_change,
                'status': f'🟠 Estável ({oi_change*100:+.1f}%)',
                'score': 1.5
            }
        else:
            score += 1.0
            details['open_interest'] = {
                'change': oi_change,
                'status': f'🔴 Caindo ({oi_change*100:.1f}%)',
                'score': 1.0
            }
        
        # ==================
        # Orderbook Imbalance (3 pontos)
        # ==================
        orderbook = market_data.get('orderbook', {})
        bid_ask_ratio = self._calculate_bid_ask_ratio(orderbook)
        
        if 0.9 <= bid_ask_ratio <= 1.1:
            score += 3.0
            details['orderbook'] = {
                'ratio': bid_ask_ratio,
                'status': f'🟢 Equilibrado ({bid_ask_ratio:.2f})',
                'score': 3.0
            }
        elif bid_ask_ratio > 1.3:
            score += 2.5
            details['orderbook'] = {
                'ratio': bid_ask_ratio,
                'status': f'🟢 Pressão compradora ({bid_ask_ratio:.2f})',
                'score': 2.5
            }
        elif bid_ask_ratio < 0.7:
            score += 2.5
            details['orderbook'] = {
                'ratio': bid_ask_ratio,
                'status': f'🟢 Pressão vendedora ({bid_ask_ratio:.2f})',
                'score': 2.5
            }
        elif bid_ask_ratio > 1.1:
            score += 2.0
            details['orderbook'] = {
                'ratio': bid_ask_ratio,
                'status': f'🟡 Leve pressão compradora ({bid_ask_ratio:.2f})',
                'score': 2.0
            }
        else:
            score += 2.0
            details['orderbook'] = {
                'ratio': bid_ask_ratio,
                'status': f'🟡 Leve pressão vendedora ({bid_ask_ratio:.2f})',
                'score': 2.0
            }
        
        # ==================
        # Long/Short Ratio (1.5 pontos) - Opcional
        # ==================
        if 'long_short_ratio' in market_data:
            ls_ratio = market_data['long_short_ratio']
            
            # Garantir que ls_ratio não seja None e seja convertido para float
            if ls_ratio is None:
                ls_ratio = 0.5  # Neutro
            try:
                ls_ratio = float(ls_ratio)
            except (ValueError, TypeError):
                ls_ratio = 0.5  # Neutro
            
            if 0.45 <= ls_ratio <= 0.55:
                score += 1.5
                details['long_short'] = {
                    'ratio': ls_ratio,
                    'status': f'🟢 Equilibrado ({ls_ratio:.2f})',
                    'score': 1.5
                }
            elif ls_ratio > 0.6:
                score += 1.0
                details['long_short'] = {
                    'ratio': ls_ratio,
                    'status': f'🟡 Maioria long ({ls_ratio:.2f}) - risco',
                    'score': 1.0
                }
            else:
                score += 1.0
                details['long_short'] = {
                    'ratio': ls_ratio,
                    'status': f'🟡 Maioria short ({ls_ratio:.2f}) - risco',
                    'score': 1.0
                }
        else:
            # Se não houver L/S ratio, ajustar max_score
            max_score = 8.5
        
        # ==================
        # Análise Combinada
        # ==================
        
        # Detectar condições extremas
        warnings = []
        
        if abs(funding) > 0.05:
            warnings.append("Funding extremo - possível reversão")
        
        if oi_change < -0.1:
            warnings.append("OI caindo forte - possível fim de movimento")
        
        if bid_ask_ratio > 2.0 or bid_ask_ratio < 0.5:
            warnings.append("Orderbook muito desequilibrado")
        
        # Status final
        percentage = (score / max_score) * 100
        
        if score >= 7.0:
            status = '🟢 FAVORÁVEL'
        elif score >= 4.5:
            status = '🟡 NEUTRO'
        else:
            status = '🔴 DESFAVORÁVEL'
        
        return {
            'score': round(score, 2),
            'max_score': max_score,
            'percentage': round(percentage, 1),
            'status': status,
            'details': details,
            'warnings': warnings
        }
    
    def _empty_result(self) -> Dict:
        """Retorna resultado vazio em caso de erro"""
        return {
            'score': 0.0,
            'max_score': 10.0,
            'percentage': 0.0,
            'status': '🔴 ERRO',
            'details': {},
            'warnings': []
        }


# Teste unitário
if __name__ == '__main__':
    # Dados de teste
    test_market_data = {
        'funding_rate': 0.02,  # 0.02% = bullish moderado
        'oi_change_24h': 0.08,  # +8% = crescendo
        'orderbook': {
            'bids': [[43200, 10], [43190, 8], [43180, 12]],
            'asks': [[43210, 9], [43220, 7], [43230, 11]]
        },
        'long_short_ratio': 0.52  # 52% long, 48% short
    }
    
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze(test_market_data)
    
    print("="*60)
    print("TESTE: Sentiment Analyzer")
    print("="*60)
    print(f"Score: {result['score']}/{result['max_score']}")
    print(f"Percentual: {result['percentage']}%")
    print(f"Status: {result['status']}")
    print("\nDetalhes:")
    for key, value in result['details'].items():
        print(f"  {key}: {value}")
    
    if result['warnings']:
        print("\nAvisos:")
        for warning in result['warnings']:
            print(f"  ⚠️ {warning}")
    
    print("="*60)
