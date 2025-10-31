"""
Entry Generator - Gerador de Setups de Entrada
Transforma análise de mercado em setups concretos de trade
Baseado nas regras específicas do usuário
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime


class EntryGenerator:
    """
    Gera setups de entrada baseados na análise de mercado
    """
    
    def __init__(self, config: Optional[Dict] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Args:
            config: Configurações de setup (opcional)
            logger: Logger customizado (opcional)
        """
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)
        
        # Configurações padrão
        self.min_global_score = self.config.get('min_global_score', 7.0)
        self.min_confidence = self.config.get('min_confidence', 70.0)
        
        self.logger.info("Entry Generator inicializado")
    
    def generate_setup(self, analysis_result: Dict, 
                      multi_tf_data: Optional[Dict] = None) -> Dict:
        """
        Gera setup de entrada baseado na análise
        
        Args:
            analysis_result: Resultado do MarketAnalyzer.analyze_full()
            multi_tf_data: Dados multi-timeframe (opcional)
        
        Returns:
            Dict com setup completo ou None se não houver setup válido
        """
        
        try:
            self.logger.debug("Gerando setup de entrada...")
            
            # Verificar se há setup válido
            if not self._has_valid_conditions(analysis_result):
                return self._no_setup_result("Condições mínimas não atendidas")
            
            # Determinar direção
            direction = self._determine_direction(analysis_result, multi_tf_data)
            
            if direction == 'NEUTRO':
                return self._no_setup_result("Direção neutra - sem sinal claro")
            
            # Verificar regras específicas
            setup_type, conditions_met = self._check_entry_rules(
                analysis_result, direction, multi_tf_data
            )
            
            if not conditions_met:
                return self._no_setup_result("Regras de entrada não satisfeitas")
            
            # Calcular níveis de entrada, SL, TP
            levels = self._calculate_trade_levels(analysis_result, direction)
            
            # Calcular tamanho de posição
            position_size = self._calculate_position_size(analysis_result, levels)
            
            # Calcular confiança do setup
            confidence = self._calculate_setup_confidence(
                analysis_result, conditions_met, multi_tf_data
            )
            
            # Montar setup final
            setup = {
                'has_setup': True,
                'timestamp': datetime.now().isoformat(),
                'setup_type': setup_type,
                'direction': direction,
                'confidence': round(confidence, 1),
                
                # Níveis
                'entry': levels['entry'],
                'stop_loss': levels['stop_loss'],
                'take_profit': levels['take_profit'],
                
                # Position sizing
                'position_size_usd': position_size['size_usd'],
                'risk_amount_usd': position_size['risk_usd'],
                'exposure_pct': position_size['exposure_pct'],
                
                # Risk/Reward
                'risk_reward_ratio': levels['risk_reward'],
                'sl_distance_pct': levels['sl_distance_pct'],
                'tp_distance_pct': levels['tp_distance_pct'],
                
                # Condições atendidas
                'conditions_met': conditions_met,
                'reasoning': self._format_reasoning(conditions_met, setup_type),
                
                # Scores de referência
                'global_score': analysis_result.get('global', {}).get('global_score', 0),
                'technical_score': analysis_result.get('technical', {}).get('score', 0),
                'volume_score': analysis_result.get('volume', {}).get('score', 0),
                
                # Multi-timeframe alignment
                'mtf_alignment': self._check_mtf_alignment(multi_tf_data, direction) if multi_tf_data else None,
                
                # Warnings
                'warnings': self._generate_warnings(analysis_result, levels)
            }
            
            self.logger.info(
                f"Setup gerado: {direction} - Confiança: {confidence:.1f}% - "
                f"Entry: {levels['entry']:.2f} - R:R: 1:{levels['risk_reward']:.2f}"
            )
            
            return setup
            
        except Exception as e:
            self.logger.error(f"Erro ao gerar setup: {e}", exc_info=True)
            return self._no_setup_result("Erro ao gerar setup")
    
    def _has_valid_conditions(self, analysis: Dict) -> bool:
        """Verifica condições mínimas para setup"""
        
        global_data = analysis.get('global', {})
        
        # Score mínimo
        if global_data.get('global_score', 0) < self.min_global_score:
            return False
        
        # Confiança mínima
        if global_data.get('confidence', 0) < self.min_confidence:
            return False
        
        # Direção definida
        if global_data.get('direction', 'NEUTRO') == 'NEUTRO':
            return False
        
        return True
    
    def _determine_direction(self, analysis: Dict, multi_tf_data: Optional[Dict]) -> str:
        """Determina direção final considerando múltiplos timeframes"""
        
        # Direção da análise principal
        primary_direction = analysis.get('global', {}).get('direction', 'NEUTRO')
        
        # Se não houver multi-TF, usar direção primária
        if not multi_tf_data:
            return primary_direction
        
        # Verificar alinhamento multi-TF
        mtf_directions = []
        for tf, data in multi_tf_data.items():
            direction = data.get('global', {}).get('direction', 'NEUTRO')
            if direction != 'NEUTRO':
                mtf_directions.append(direction)
        
        if not mtf_directions:
            return primary_direction
        
        # Contar votos
        long_votes = mtf_directions.count('LONG')
        short_votes = mtf_directions.count('SHORT')
        
        # Requer maioria clara (>= 60%)
        total_votes = len(mtf_directions)
        if long_votes / total_votes >= 0.6:
            return 'LONG'
        elif short_votes / total_votes >= 0.6:
            return 'SHORT'
        else:
            return 'NEUTRO'
    
    def _check_entry_rules(self, analysis: Dict, direction: str,
                          multi_tf_data: Optional[Dict]) -> tuple:
        """
        Verifica regras de entrada baseadas nas especificações do usuário
        
        Returns:
            (setup_type, conditions_met)
        """
        
        tech = analysis.get('technical', {})
        volume = analysis.get('volume', {})
        sentiment = analysis.get('sentiment', {})
        structure = analysis.get('structure', {})
        
        tech_details = tech.get('details', {})
        volume_details = volume.get('details', {})
        sentiment_details = sentiment.get('details', {})
        
        # Extrair indicadores
        indicators = tech.get('indicators', {})
        ema9 = indicators.get('ema_9', 0)
        ema21 = indicators.get('ema_21', 0)
        ema20 = indicators.get('ema_20', 0)
        ema50 = indicators.get('ema_50', 0)
        rsi = indicators.get('rsi_14', 50)
        adx = indicators.get('adx', 0)
        
        volume_ratio = volume.get('metrics', {}).get('ratio', 1.0)
        
        conditions_met = []
        
        # =====================
        # REGRA 1: SETUP TREND FOLLOWING (Principal)
        # =====================
        if direction == 'LONG':
            # EMA 9 > EMA 21 (5m/15m) E Price > EMA 9
            if ema9 > ema21:
                conditions_met.append("✅ EMA 9 > EMA 21 (tendência bullish)")
            
            # RSI entre 50-70
            if 50 < rsi < 70:
                conditions_met.append(f"✅ RSI = {rsi:.1f} (zona favorável)")
            
            # ADX > 25
            if adx > 25:
                conditions_met.append(f"✅ ADX = {adx:.1f} (tendência forte)")
            
            # Volume > média
            if volume_ratio > 1.0:
                conditions_met.append(f"✅ Volume {volume_ratio:.2f}x a média")
            
            # Scores técnico e volume favoráveis
            if tech.get('score', 0) >= 7.0 and volume.get('score', 0) >= 7.0:
                conditions_met.append("✅ Scores técnico e volume favoráveis")
            
            # Contar condições
            if len(conditions_met) >= 3:  # Mínimo 3 condições
                return ('trend_following_long', conditions_met)
        
        elif direction == 'SHORT':
            # EMA 9 < EMA 21
            if ema9 < ema21:
                conditions_met.append("✅ EMA 9 < EMA 21 (tendência bearish)")
            
            # RSI entre 30-50
            if 30 < rsi < 50:
                conditions_met.append(f"✅ RSI = {rsi:.1f} (zona favorável)")
            
            # ADX > 25
            if adx > 25:
                conditions_met.append(f"✅ ADX = {adx:.1f} (tendência forte)")
            
            # Volume > média
            if volume_ratio > 1.0:
                conditions_met.append(f"✅ Volume {volume_ratio:.2f}x a média")
            
            # Scores técnico e volume favoráveis
            if tech.get('score', 0) >= 7.0 and volume.get('score', 0) >= 7.0:
                conditions_met.append("✅ Scores técnico e volume favoráveis")
            
            if len(conditions_met) >= 3:
                return ('trend_following_short', conditions_met)
        
        # =====================
        # REGRA 2: REVERSÃO (Secundário)
        # =====================
        if direction == 'LONG':
            reversal_conditions = []
            
            # RSI oversold
            if rsi < 30:
                reversal_conditions.append(f"✅ RSI oversold ({rsi:.1f})")
            
            # Funding negativo
            funding = sentiment_details.get('funding', {}).get('value', 0)
            if funding < -0.01:
                reversal_conditions.append(f"✅ Funding negativo ({funding:.4f}%)")
            
            # Volume delta positivo
            delta = volume_details.get('delta', {}).get('value', 0)
            if delta > 0 and volume_ratio > 1.0:
                reversal_conditions.append("✅ Volume delta positivo com volume alto")
            
            # Divergência bullish
            divergence = structure.get('details', {}).get('divergence', {}).get('type')
            if divergence == 'bullish':
                reversal_conditions.append("✅ Divergência bullish detectada")
            
            if len(reversal_conditions) >= 3:
                return ('reversal_long', reversal_conditions)
        
        # Se nenhuma regra satisfeita
        return ('none', [])
    
    def _calculate_trade_levels(self, analysis: Dict, direction: str) -> Dict:
        """Calcula níveis de entrada, SL e TP"""
        
        current_price = analysis.get('current_price', 0)
        
        # Pegar ATR
        atr = analysis.get('technical', {}).get('indicators', {}).get('atr', 0)
        if atr == 0:
            atr = current_price * 0.02  # 2% como fallback
        
        # Suporte e resistência
        sr = analysis.get('structure', {}).get('support_resistance', {})
        nearest_support = sr.get('nearest_support', current_price * 0.98)
        nearest_resistance = sr.get('nearest_resistance', current_price * 1.02)
        
        if direction == 'LONG':
            entry = current_price
            stop_loss = max(nearest_support - (atr * 0.5), current_price - (atr * 0.75))
            take_profit = min(nearest_resistance, current_price + (atr * 1.5))
        
        else:  # SHORT
            entry = current_price
            stop_loss = min(nearest_resistance + (atr * 0.5), current_price + (atr * 0.75))
            take_profit = max(nearest_support, current_price - (atr * 1.5))
        
        # Calcular distâncias
        sl_distance = abs(entry - stop_loss)
        tp_distance = abs(entry - take_profit)
        
        sl_distance_pct = (sl_distance / entry) * 100
        tp_distance_pct = (tp_distance / entry) * 100
        
        risk_reward = tp_distance / sl_distance if sl_distance > 0 else 0
        
        return {
            'entry': round(entry, 2),
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'sl_distance_pct': round(sl_distance_pct, 2),
            'tp_distance_pct': round(tp_distance_pct, 2),
            'risk_reward': round(risk_reward, 2)
        }
    
    def _calculate_position_size(self, analysis: Dict, levels: Dict) -> Dict:
        """Calcula tamanho de posição (1% de risco)"""
        
        account_balance = analysis.get('metadata', {}).get('account_balance', 10000)
        
        # Risco de 1% do capital
        risk_pct = 1.0
        risk_usd = account_balance * (risk_pct / 100)
        
        # Distância do stop
        sl_distance_pct = levels['sl_distance_pct']
        
        # Tamanho da posição
        if sl_distance_pct > 0:
            size_usd = risk_usd / (sl_distance_pct / 100)
        else:
            size_usd = account_balance * 0.05  # 5% default
        
        # Limitar a 15% do capital
        max_size = account_balance * 0.15
        size_usd = min(size_usd, max_size)
        
        exposure_pct = (size_usd / account_balance) * 100
        
        return {
            'size_usd': round(size_usd, 2),
            'risk_usd': round(risk_usd, 2),
            'exposure_pct': round(exposure_pct, 2)
        }
    
    def _calculate_setup_confidence(self, analysis: Dict, conditions_met: List,
                                    multi_tf_data: Optional[Dict]) -> float:
        """Calcula confiança do setup"""
        
        # Base: confiança da análise
        base_confidence = analysis.get('global', {}).get('confidence', 0)
        
        # Ajuste por número de condições atendidas
        conditions_factor = min(len(conditions_met) / 5, 1.0)  # Máximo 5 condições
        
        # Ajuste por alinhamento multi-TF
        mtf_factor = 1.0
        if multi_tf_data:
            alignment = self._check_mtf_alignment(
                multi_tf_data,
                analysis.get('global', {}).get('direction', 'NEUTRO')
            )
            mtf_factor = alignment / 100
        
        confidence = base_confidence * conditions_factor * mtf_factor
        
        return min(confidence, 95.0)  # Máximo 95%
    
    def _check_mtf_alignment(self, multi_tf_data: Dict, direction: str) -> float:
        """
        Verifica alinhamento entre timeframes
        Returns: percentage (0-100)
        """
        
        if not multi_tf_data:
            return 100.0
        
        aligned = 0
        total = 0
        
        for tf, data in multi_tf_data.items():
            tf_direction = data.get('global', {}).get('direction', 'NEUTRO')
            if tf_direction != 'NEUTRO':
                total += 1
                if tf_direction == direction:
                    aligned += 1
        
        if total == 0:
            return 50.0
        
        return (aligned / total) * 100
    
    def _format_reasoning(self, conditions: List, setup_type: str) -> str:
        """Formata texto de reasoning"""
        
        lines = [f"Setup tipo: {setup_type.replace('_', ' ').title()}"]
        lines.append("")
        lines.append("Condições atendidas:")
        lines.extend(conditions)
        
        return "\n".join(lines)
    
    def _generate_warnings(self, analysis: Dict, levels: Dict) -> List[str]:
        """Gera warnings sobre o setup"""
        
        warnings = []
        
        # Verificar se R:R é bom
        if levels['risk_reward'] < 1.0:
            warnings.append("⚠️ Risk/Reward abaixo de 1:1")
        
        # Verificar volatilidade
        atr_pct = analysis.get('technical', {}).get('indicators', {}).get('atr_percentage', 0)
        if atr_pct > 3.5:
            warnings.append("⚠️ Volatilidade alta - considere SL mais amplo")
        
        # Verificar proximidade de S/R
        sr = analysis.get('structure', {}).get('support_resistance', {})
        current_price = analysis.get('current_price', 0)
        nearest_resistance = sr.get('nearest_resistance', 0)
        
        if nearest_resistance > 0:
            dist_to_resistance = abs(current_price - nearest_resistance) / current_price
            if dist_to_resistance < 0.005:  # < 0.5%
                warnings.append("⚠️ Muito próximo da resistência - considere parcial")
        
        return warnings
    
    def _no_setup_result(self, reason: str) -> Dict:
        """Retorna resultado sem setup"""
        
        self.logger.debug(f"Sem setup: {reason}")
        
        return {
            'has_setup': False,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }


# Teste
if __name__ == '__main__':
    import pandas as pd
    import numpy as np
    
    # Simular análise completa
    test_analysis = {
        'symbol': 'BTC',
        'current_price': 43200,
        'global': {
            'global_score': 8.2,
            'confidence': 85.0,
            'direction': 'LONG'
        },
        'technical': {
            'score': 8.0,
            'details': {},
            'indicators': {
                'ema_9': 43100,
                'ema_21': 42900,
                'rsi_14': 58,
                'adx': 28,
                'atr': 900,
                'atr_percentage': 2.1
            }
        },
        'volume': {
            'score': 9.0,
            'details': {},
            'metrics': {'ratio': 1.8}
        },
        'sentiment': {
            'score': 7.0,
            'details': {}
        },
        'structure': {
            'score': 8.0,
            'details': {},
            'support_resistance': {
                'nearest_support': 42500,
                'nearest_resistance': 43800
            }
        },
        'risk': {
            'score': 9.0
        },
        'metadata': {
            'account_balance': 10000
        }
    }
    
    generator = EntryGenerator()
    setup = generator.generate_setup(test_analysis)
    
    if setup['has_setup']:
        print("="*60)
        print("TESTE: Entry Generator")
        print("="*60)
        print(f"Setup Type: {setup['setup_type']}")
        print(f"Direction: {setup['direction']}")
        print(f"Confidence: {setup['confidence']}%")
        print(f"\nEntry: ${setup['entry']}")
        print(f"Stop Loss: ${setup['stop_loss']} ({setup['sl_distance_pct']}%)")
        print(f"Take Profit: ${setup['take_profit']} ({setup['tp_distance_pct']}%)")
        print(f"\nPosition Size: ${setup['position_size_usd']}")
        print(f"Risk Amount: ${setup['risk_amount_usd']}")
        print(f"R:R Ratio: 1:{setup['risk_reward_ratio']}")
        print(f"\n{setup['reasoning']}")
        
        if setup['warnings']:
            print("\nWarnings:")
            for w in setup['warnings']:
                print(f"  {w}")
        print("="*60)
    else:
        print(f"Sem setup: {setup['reason']}")
