"""
Scoring Engine - Sistema de Pontuação Global
Combina scores de todas as categorias em um score final ponderado
"""

import logging
from typing import Dict, Optional


class ScoringEngine:
    """
    Sistema de pontuação que combina múltiplas análises
    """
    
    # Pesos padrão para cada categoria (devem somar 1.0)
    DEFAULT_WEIGHTS = {
        'technical': 0.25,      # 25% - Indicadores técnicos
        'volume': 0.20,         # 20% - Volume e order flow
        'sentiment': 0.15,      # 15% - Sentiment (funding, OI, orderbook)
        'structure': 0.15,      # 15% - Estrutura e padrões
        'risk': 0.15,           # 15% - Gestão de risco
        'volatility': 0.10      # 10% - Análise de volatilidade
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Args:
            weights: Dict customizado de pesos (opcional)
            logger: Logger customizado (opcional)
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.logger = logger or logging.getLogger(__name__)
        
        # Validar pesos
        self._validate_weights()
    
    def _validate_weights(self):
        """Valida se os pesos somam 1.0"""
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            self.logger.warning(f"Pesos não somam 1.0 (total: {total}). Normalizando...")
            # Normalizar
            for key in self.weights:
                self.weights[key] = self.weights[key] / total
    
    def calculate_global_score(self, analysis_results: Dict) -> Dict:
        """
        Calcula score global combinando todas as análises
        
        Args:
            analysis_results: {
                'technical': {...},
                'volume': {...},
                'sentiment': {...},
                'structure': {...},
                'risk': {...}
            }
        
        Returns:
            Dict com score global e breakdown detalhado
        """
        
        try:
            # Extrair scores individuais
            scores = {}
            for category in self.weights.keys():
                if category in analysis_results:
                    scores[category] = analysis_results[category].get('score', 0.0)
                else:
                    scores[category] = 0.0
                    self.logger.warning(f"Categoria '{category}' não encontrada nos resultados")
            
            # Calcular score ponderado
            weighted_score = sum(
                scores[category] * self.weights[category]
                for category in scores
            )
            
            # Score global normalizado (0-10)
            global_score = weighted_score
            
            # Determinar status geral
            status = self._determine_status(global_score, scores)
            
            # Determinar direção sugerida
            direction = self._determine_direction(analysis_results)
            
            # Calcular confiança
            confidence = self._calculate_confidence(global_score, scores)
            
            # Identificar pontos fortes e fracos
            strengths, weaknesses = self._identify_strengths_weaknesses(scores)
            
            return {
                'global_score': round(global_score, 2),
                'max_score': 10.0,
                'percentage': round((global_score / 10.0) * 100, 1),
                'status': status,
                'direction': direction,
                'confidence': round(confidence, 1),
                'category_scores': {
                    category: {
                        'score': round(scores[category], 2),
                        'weight': self.weights[category],
                        'weighted_contribution': round(scores[category] * self.weights[category], 2)
                    }
                    for category in scores
                },
                'strengths': strengths,
                'weaknesses': weaknesses,
                'breakdown': self._create_breakdown(scores, self.weights)
            }
            
        except Exception as e:
            self.logger.error(f"Erro ao calcular score global: {e}")
            return self._empty_result()
    
    def _determine_status(self, global_score: float, category_scores: Dict) -> str:
        """Determina status geral baseado no score global"""
        
        if global_score >= 8.0:
            return '🟢 MUITO FAVORÁVEL'
        elif global_score >= 7.0:
            return '🟢 FAVORÁVEL'
        elif global_score >= 5.5:
            return '🟡 NEUTRO'
        elif global_score >= 4.0:
            return '🟠 DESFAVORÁVEL'
        else:
            return '🔴 MUITO DESFAVORÁVEL'
    
    def _determine_direction(self, analysis_results: Dict) -> str:
        """
        Determina direção sugerida baseado nas análises
        """
        
        bullish_signals = 0
        bearish_signals = 0
        
        # Analisar indicadores técnicos
        if 'technical' in analysis_results:
            tech_details = analysis_results['technical'].get('details', {})
            
            # EMA
            if 'ema' in tech_details:
                ema_status = tech_details['ema'].get('status', '')
                if 'Bullish' in ema_status:
                    bullish_signals += 2
                elif 'Bearish' in ema_status:
                    bearish_signals += 2
            
            # RSI
            if 'rsi' in tech_details:
                rsi_value = tech_details['rsi'].get('value', 50)
                if rsi_value < 40:
                    bullish_signals += 1  # Oversold = oportunidade de compra
                elif rsi_value > 60:
                    bearish_signals += 1
        
        # Analisar volume
        if 'volume' in analysis_results:
            vol_details = analysis_results['volume'].get('details', {})
            
            if 'delta' in vol_details:
                delta_value = vol_details['delta'].get('value', 0)
                if delta_value > 0:
                    bullish_signals += 1
                else:
                    bearish_signals += 1
        
        # Analisar estrutura
        if 'structure' in analysis_results:
            pattern = analysis_results['structure'].get('pattern', '')
            if pattern == 'HH_HL':
                bullish_signals += 2
            elif pattern == 'LH_LL':
                bearish_signals += 2
        
        # Analisar sentimento
        if 'sentiment' in analysis_results:
            sent_details = analysis_results['sentiment'].get('details', {})
            
            if 'orderbook' in sent_details:
                ratio = sent_details['orderbook'].get('ratio', 1.0)
                if ratio > 1.2:
                    bullish_signals += 1
                elif ratio < 0.8:
                    bearish_signals += 1
        
        # Decidir direção
        if bullish_signals > bearish_signals + 1:
            return 'LONG'
        elif bearish_signals > bullish_signals + 1:
            return 'SHORT'
        else:
            return 'NEUTRO'
    
    def _calculate_confidence(self, global_score: float, category_scores: Dict) -> float:
        """
        Calcula nível de confiança (0-100%)
        Baseado no score global e na consistência entre categorias
        """
        
        # Base: score global
        base_confidence = (global_score / 10.0) * 100
        
        # Ajuste pela consistência entre categorias
        scores_list = list(category_scores.values())
        if len(scores_list) > 1:
            std_dev = np.std(scores_list) if 'np' in dir() else 0
            # Penalizar se há muita variação entre categorias
            consistency_factor = max(0, 1 - (std_dev / 5.0))
        else:
            consistency_factor = 1.0
        
        confidence = base_confidence * consistency_factor
        
        return min(confidence, 95.0)  # Máximo 95% de confiança
    
    def _identify_strengths_weaknesses(self, scores: Dict) -> tuple:
        """
        Identifica pontos fortes e fracos da análise
        
        Returns:
            (strengths, weaknesses) - listas de categorias
        """
        
        strengths = []
        weaknesses = []
        
        for category, score in scores.items():
            if score >= 7.5:
                strengths.append({
                    'category': category,
                    'score': score,
                    'label': self._get_category_label(category)
                })
            elif score < 5.0:
                weaknesses.append({
                    'category': category,
                    'score': score,
                    'label': self._get_category_label(category)
                })
        
        # Ordenar por score
        strengths.sort(key=lambda x: x['score'], reverse=True)
        weaknesses.sort(key=lambda x: x['score'])
        
        return strengths, weaknesses
    
    def _get_category_label(self, category: str) -> str:
        """Retorna label amigável para categoria"""
        labels = {
            'technical': 'Indicadores Técnicos',
            'volume': 'Volume e Order Flow',
            'sentiment': 'Sentimento de Mercado',
            'structure': 'Estrutura e Padrões',
            'risk': 'Gestão de Risco',
            'volatility': 'Análise de Volatilidade'
        }
        return labels.get(category, category.title())
    
    def _create_breakdown(self, scores: Dict, weights: Dict) -> str:
        """
        Cria texto descritivo do breakdown do score
        """
        
        lines = []
        for category in ['technical', 'volume', 'sentiment', 'structure', 'risk', 'volatility']:
            if category in scores:
                score = scores[category]
                weight = weights[category]
                contribution = score * weight
                
                emoji = '🟢' if score >= 7.5 else '🟡' if score >= 5.0 else '🔴'
                label = self._get_category_label(category)
                
                lines.append(
                    f"{emoji} {label}: {score:.1f}/10 "
                    f"(peso: {weight*100:.0f}%, contribuição: {contribution:.2f})"
                )
        
        return '\n'.join(lines)
    
    def _empty_result(self) -> Dict:
        """Retorna resultado vazio em caso de erro"""
        return {
            'global_score': 0.0,
            'max_score': 10.0,
            'percentage': 0.0,
            'status': '🔴 ERRO',
            'direction': 'NEUTRO',
            'confidence': 0.0,
            'category_scores': {},
            'strengths': [],
            'weaknesses': [],
            'breakdown': ''
        }


# Testes
if __name__ == '__main__':
    import numpy as np
    
    # Dados de teste
    test_analysis = {
        'technical': {'score': 8.0},
        'volume': {'score': 9.0},
        'sentiment': {'score': 7.0},
        'structure': {'score': 8.0},
        'risk': {'score': 9.0}
    }
    
    engine = ScoringEngine()
    result = engine.calculate_global_score(test_analysis)
    
    print("="*60)
    print("TESTE: Scoring Engine")
    print("="*60)
    print(f"Score Global: {result['global_score']}/10")
    print(f"Percentual: {result['percentage']}%")
    print(f"Status: {result['status']}")
    print(f"Direção: {result['direction']}")
    print(f"Confiança: {result['confidence']}%")
    
    print("\nBreakdown:")
    print(result['breakdown'])
    
    print("\nPontos Fortes:")
    for strength in result['strengths']:
        print(f"  • {strength['label']}: {strength['score']:.1f}/10")
    
    print("\nPontos Fracos:")
    for weakness in result['weaknesses']:
        print(f"  • {weakness['label']}: {weakness['score']:.1f}/10")
    
    print("="*60)
