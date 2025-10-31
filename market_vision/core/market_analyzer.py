"""
Market Analyzer - Orquestrador Principal
Coordena todas as análises e gera visão completa do mercado
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime

from ..indicators.technical_analyzer import TechnicalAnalyzer
from ..indicators.volume_analyzer import VolumeAnalyzer
from ..indicators.sentiment_analyzer import SentimentAnalyzer
from ..indicators.structure_analyzer import StructureAnalyzer
from ..indicators.risk_analyzer import RiskAnalyzer
from .scoring_engine import ScoringEngine


class MarketAnalyzer:
    """
    Orquestrador principal que coordena todas as análises
    """
    
    def __init__(self, config: Optional[Dict] = None, 
                 logger: Optional[logging.Logger] = None):
        """
        Args:
            config: Configurações customizadas (opcional)
            logger: Logger customizado (opcional)
        """
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)
        
        # Inicializar analisadores
        self.technical_analyzer = TechnicalAnalyzer(logger=self.logger)
        self.volume_analyzer = VolumeAnalyzer(logger=self.logger)
        self.sentiment_analyzer = SentimentAnalyzer(logger=self.logger)
        self.structure_analyzer = StructureAnalyzer(logger=self.logger)
        self.risk_analyzer = RiskAnalyzer(logger=self.logger)
        
        # Scoring engine
        weights = self.config.get('scoring_weights', None)
        self.scoring_engine = ScoringEngine(weights=weights, logger=self.logger)
        
        self.logger.info("Market Analyzer inicializado")
    
    def analyze_full(self, market_data: Dict) -> Dict:
        """
        Análise completa do mercado
        
        Args:
            market_data: {
                'ohlcv': pd.DataFrame,  # OHLCV data
                'funding_rate': float,
                'oi_change_24h': float,
                'orderbook': {'bids': [...], 'asks': [...]},
                'trades': [...],  # opcional
                'account_balance': float,
                'position_data': {...},
                'long_short_ratio': float  # opcional
            }
        
        Returns:
            Dict com análise completa e score global
        """
        
        try:
            timestamp = datetime.now()
            self.logger.info("Iniciando análise completa do mercado")
            
            ohlcv_df = market_data.get('ohlcv')
            if ohlcv_df is None or len(ohlcv_df) == 0:
                self.logger.error("Dados OHLCV ausentes ou vazios")
                return self._empty_result()
            
            # ==================
            # 1. ANÁLISE TÉCNICA
            # ==================
            self.logger.debug("Executando análise técnica...")
            technical_result = self.technical_analyzer.analyze(ohlcv_df)
            
            # ==================
            # 2. ANÁLISE DE VOLUME
            # ==================
            self.logger.debug("Executando análise de volume...")
            trades_data = market_data.get('trades')
            volume_result = self.volume_analyzer.analyze(ohlcv_df, trades_data)
            
            # ==================
            # 3. ANÁLISE DE SENTIMENTO
            # ==================
            self.logger.debug("Executando análise de sentimento...")
            sentiment_data = {
                'funding_rate': market_data.get('funding_rate', 0.0),
                'oi_change_24h': market_data.get('oi_change_24h', 0.0),
                'orderbook': market_data.get('orderbook', {}),
                'long_short_ratio': market_data.get('long_short_ratio')
            }
            sentiment_result = self.sentiment_analyzer.analyze(sentiment_data)
            
            # ==================
            # 4. ANÁLISE DE ESTRUTURA
            # ==================
            self.logger.debug("Executando análise de estrutura...")
            # Pegar RSI da análise técnica para divergências
            rsi_values = None
            if 'indicators' in technical_result and 'rsi_14' in technical_result['indicators']:
                # Criar array de RSI para todas as candles (simplificado)
                rsi_value = technical_result['indicators']['rsi_14']
                rsi_values = np.full(len(ohlcv_df), rsi_value)
            
            structure_result = self.structure_analyzer.analyze(ohlcv_df, rsi_values)
            
            # ==================
            # 5. ANÁLISE DE RISCO
            # ==================
            self.logger.debug("Executando análise de risco...")
            position_data = market_data.get('position_data', {})
            account_balance = market_data.get('account_balance', 10000.0)
            
            # Pegar ATR da análise técnica
            volatility_data = {
                'atr': technical_result.get('indicators', {}).get('atr', 0),
                'atr_percentage': technical_result.get('indicators', {}).get('atr_percentage', 0)
            }
            
            risk_result = self.risk_analyzer.analyze(
                position_data, volatility_data, account_balance
            )
            
            # ==================
            # 6. SCORE GLOBAL
            # ==================
            self.logger.debug("Calculando score global...")
            
            analysis_results = {
                'technical': technical_result,
                'volume': volume_result,
                'sentiment': sentiment_result,
                'structure': structure_result,
                'risk': risk_result
            }
            
            global_result = self.scoring_engine.calculate_global_score(analysis_results)
            
            # ==================
            # 7. COMPILAR RESULTADO FINAL
            # ==================
            
            current_price = float(ohlcv_df['close'].iloc[-1])
            
            final_result = {
                'timestamp': timestamp.isoformat(),
                'symbol': market_data.get('symbol', 'BTC'),
                'current_price': current_price,
                
                # Score global
                'global': global_result,
                
                # Análises individuais
                'technical': technical_result,
                'volume': volume_result,
                'sentiment': sentiment_result,
                'structure': structure_result,
                'risk': risk_result,
                
                # Metadados
                'metadata': {
                    'candles_analyzed': len(ohlcv_df),
                    'timeframe': market_data.get('timeframe', '5m'),
                    'account_balance': account_balance
                }
            }
            
            self.logger.info(
                f"Análise completa finalizada - Score: {global_result['global_score']:.2f}/10 "
                f"({global_result['status']})"
            )
            
            return final_result
            
        except Exception as e:
            self.logger.error(f"Erro na análise completa: {e}", exc_info=True)
            return self._empty_result()
    
    def analyze_multi_timeframe(self, market_data_by_tf: Dict) -> Dict:
        """
        Análise multi-timeframe
        
        Args:
            market_data_by_tf: {
                '5m': {...},
                '15m': {...},
                '1h': {...}
            }
        
        Returns:
            Dict com análises por timeframe e consolidada
        """
        
        try:
            self.logger.info("Iniciando análise multi-timeframe")
            
            results_by_tf = {}
            
            # Analisar cada timeframe
            for tf, data in market_data_by_tf.items():
                self.logger.debug(f"Analisando timeframe: {tf}")
                results_by_tf[tf] = self.analyze_full(data)
            
            # Consolidar resultados
            consolidated = self._consolidate_multi_tf_analysis(results_by_tf)
            
            return {
                'by_timeframe': results_by_tf,
                'consolidated': consolidated
            }
            
        except Exception as e:
            self.logger.error(f"Erro na análise multi-timeframe: {e}", exc_info=True)
            return {'by_timeframe': {}, 'consolidated': {}}
    
    def _consolidate_multi_tf_analysis(self, results_by_tf: Dict) -> Dict:
        """
        Consolida análises de múltiplos timeframes
        Dá mais peso para timeframes maiores
        """
        
        tf_weights = {
            '1m': 0.10,
            '5m': 0.20,
            '15m': 0.30,
            '1h': 0.25,
            '4h': 0.15
        }
        
        # Scores ponderados
        weighted_scores = []
        
        for tf, result in results_by_tf.items():
            weight = tf_weights.get(tf, 0.20)  # Default 20%
            score = result.get('global', {}).get('global_score', 0)
            weighted_scores.append(score * weight)
        
        consolidated_score = sum(weighted_scores)
        
        # Determinar direção predominante
        directions = [
            result.get('global', {}).get('direction', 'NEUTRO')
            for result in results_by_tf.values()
        ]
        
        long_count = directions.count('LONG')
        short_count = directions.count('SHORT')
        
        if long_count > short_count:
            direction = 'LONG'
            agreement = (long_count / len(directions)) * 100
        elif short_count > long_count:
            direction = 'SHORT'
            agreement = (short_count / len(directions)) * 100
        else:
            direction = 'NEUTRO'
            agreement = 0
        
        return {
            'consolidated_score': round(consolidated_score, 2),
            'direction': direction,
            'timeframe_agreement': round(agreement, 1),
            'timeframes_analyzed': list(results_by_tf.keys())
        }
    
    def get_market_summary(self, analysis_result: Dict) -> str:
        """
        Gera resumo textual da análise de mercado
        
        Args:
            analysis_result: Resultado do analyze_full()
        
        Returns:
            String com resumo
        """
        
        global_data = analysis_result.get('global', {})
        
        summary_lines = [
            f"📊 RESUMO DA ANÁLISE DE MERCADO",
            f"=" * 60,
            f"Símbolo: {analysis_result.get('symbol', 'N/A')}",
            f"Preço Atual: ${analysis_result.get('current_price', 0):,.2f}",
            f"Timestamp: {analysis_result.get('timestamp', 'N/A')}",
            "",
            f"🎯 SCORE GLOBAL: {global_data.get('global_score', 0):.2f}/10",
            f"Status: {global_data.get('status', 'N/A')}",
            f"Direção Sugerida: {global_data.get('direction', 'N/A')}",
            f"Confiança: {global_data.get('confidence', 0):.1f}%",
            "",
            "📈 BREAKDOWN POR CATEGORIA:",
            global_data.get('breakdown', ''),
            ""
        ]
        
        # Pontos fortes
        strengths = global_data.get('strengths', [])
        if strengths:
            summary_lines.append("✅ PONTOS FORTES:")
            for s in strengths:
                summary_lines.append(f"  • {s['label']}: {s['score']:.1f}/10")
            summary_lines.append("")
        
        # Pontos fracos
        weaknesses = global_data.get('weaknesses', [])
        if weaknesses:
            summary_lines.append("⚠️ PONTOS FRACOS:")
            for w in weaknesses:
                summary_lines.append(f"  • {w['label']}: {w['score']:.1f}/10")
            summary_lines.append("")
        
        # Avisos
        warnings = []
        for category in ['sentiment', 'risk']:
            cat_warnings = analysis_result.get(category, {}).get('warnings', [])
            warnings.extend(cat_warnings)
        
        if warnings:
            summary_lines.append("🚨 AVISOS:")
            for warning in warnings:
                summary_lines.append(f"  • {warning}")
            summary_lines.append("")
        
        summary_lines.append("=" * 60)
        
        return "\n".join(summary_lines)
    
    def _empty_result(self) -> Dict:
        """Retorna resultado vazio em caso de erro"""
        return {
            'timestamp': datetime.now().isoformat(),
            'symbol': 'N/A',
            'current_price': 0.0,
            'global': {
                'global_score': 0.0,
                'status': '🔴 ERRO',
                'direction': 'NEUTRO',
                'confidence': 0.0
            },
            'technical': {},
            'volume': {},
            'sentiment': {},
            'structure': {},
            'risk': {},
            'metadata': {}
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
    
    test_market_data = {
        'symbol': 'BTC',
        'ohlcv': test_ohlcv,
        'funding_rate': 0.02,
        'oi_change_24h': 0.08,
        'orderbook': {
            'bids': [[43200, 10], [43190, 8]],
            'asks': [[43210, 9], [43220, 7]]
        },
        'account_balance': 10000,
        'position_data': {
            'total_exposure_usd': 500,
            'free_margin_usd': 8500,
            'session_pnl': 50,
            'session_start_balance': 10000
        }
    }
    
    analyzer = MarketAnalyzer()
    result = analyzer.analyze_full(test_market_data)
    
    print("\n" + analyzer.get_market_summary(result))
