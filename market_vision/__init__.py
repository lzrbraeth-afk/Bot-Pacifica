"""
Market Vision - Sistema de Análise e Decisão de Trading
Fornece análise multi-dimensional do mercado para tomada de decisão manual e automática
"""

__version__ = '1.0.0'

# Import apenas quando necessário para evitar problemas circulares
def get_market_analyzer():
    from .core.market_analyzer import MarketAnalyzer
    return MarketAnalyzer

def get_scoring_engine():
    from .core.scoring_engine import ScoringEngine
    return ScoringEngine
