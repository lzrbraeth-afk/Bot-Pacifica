"""
Risk Analyzer - Análise de Risco e Gestão
Analisa: Exposição, Volatilidade (ATR), Margem Livre, Drawdown
"""

import logging
import numpy as np
from typing import Dict, Optional


class RiskAnalyzer:
    """
    Analisa métricas de risco para trading
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def analyze(self, position_data: Dict, volatility_data: Dict, 
                account_balance: float = 10000.0) -> Dict:
        """
        Análise completa de risco
        
        Args:
            position_data: {
                'total_exposure_usd': float,
                'free_margin_usd': float,
                'session_pnl': float,
                'session_start_balance': float
            }
            volatility_data: {
                'atr': float,
                'atr_percentage': float
            }
            account_balance: Saldo total da conta
        
        Returns:
            Dict com score e análise de risco
        """
        try:
            # Calcular score de risco
            score_result = self._calculate_risk_score(
                position_data, volatility_data, account_balance
            )
            
            return score_result
            
        except Exception as e:
            self.logger.error(f"Erro na análise de risco: {e}")
            return self._empty_result()
    
    def _calculate_risk_score(self, position_data: Dict, volatility_data: Dict,
                             account_balance: float) -> Dict:
        """
        Calcula score de risco (0-10)
        Score alto = baixo risco = seguro
        """
        
        score = 0.0
        max_score = 10.0
        details = {}
        
        # ==================
        # Exposição Atual (3 pontos)
        # ==================
        total_exposure = position_data.get('total_exposure_usd', 0)
        exposure_pct = (total_exposure / account_balance) * 100 if account_balance > 0 else 0
        
        if exposure_pct < 5:
            score += 3.0
            details['exposure'] = {
                'value_usd': total_exposure,
                'percentage': exposure_pct,
                'status': f'🟢 Baixa ({exposure_pct:.1f}%)',
                'score': 3.0
            }
        elif exposure_pct < 10:
            score += 2.5
            details['exposure'] = {
                'value_usd': total_exposure,
                'percentage': exposure_pct,
                'status': f'🟡 Moderada ({exposure_pct:.1f}%)',
                'score': 2.5
            }
        elif exposure_pct < 20:
            score += 1.5
            details['exposure'] = {
                'value_usd': total_exposure,
                'percentage': exposure_pct,
                'status': f'🟠 Alta ({exposure_pct:.1f}%)',
                'score': 1.5
            }
        else:
            score += 0.5
            details['exposure'] = {
                'value_usd': total_exposure,
                'percentage': exposure_pct,
                'status': f'🔴 Muito alta ({exposure_pct:.1f}%)',
                'score': 0.5
            }
        
        # ==================
        # Volatilidade (ATR) (3 pontos)
        # ==================
        atr_pct = volatility_data.get('atr_percentage', 0)
        
        if atr_pct < 1.5:
            score += 3.0
            details['volatility'] = {
                'atr_percentage': atr_pct,
                'status': f'🟢 Baixa (ATR: {atr_pct:.2f}%)',
                'score': 3.0
            }
        elif atr_pct < 3.0:
            score += 2.5
            details['volatility'] = {
                'atr_percentage': atr_pct,
                'status': f'🟡 Moderada (ATR: {atr_pct:.2f}%)',
                'score': 2.5
            }
        elif atr_pct < 5.0:
            score += 1.5
            details['volatility'] = {
                'atr_percentage': atr_pct,
                'status': f'🟠 Alta (ATR: {atr_pct:.2f}%)',
                'score': 1.5
            }
        else:
            score += 0.5
            details['volatility'] = {
                'atr_percentage': atr_pct,
                'status': f'🔴 Muito alta (ATR: {atr_pct:.2f}%)',
                'score': 0.5
            }
        
        # ==================
        # Margem Livre (2 pontos)
        # ==================
        free_margin = position_data.get('free_margin_usd', account_balance)
        free_margin_pct = (free_margin / account_balance) * 100 if account_balance > 0 else 100
        
        if free_margin_pct > 80:
            score += 2.0
            details['margin'] = {
                'free_margin_usd': free_margin,
                'percentage': free_margin_pct,
                'status': f'🟢 Muita margem livre ({free_margin_pct:.0f}%)',
                'score': 2.0
            }
        elif free_margin_pct > 60:
            score += 1.5
            details['margin'] = {
                'free_margin_usd': free_margin,
                'percentage': free_margin_pct,
                'status': f'🟡 Margem adequada ({free_margin_pct:.0f}%)',
                'score': 1.5
            }
        elif free_margin_pct > 40:
            score += 1.0
            details['margin'] = {
                'free_margin_usd': free_margin,
                'percentage': free_margin_pct,
                'status': f'🟠 Margem apertada ({free_margin_pct:.0f}%)',
                'score': 1.0
            }
        else:
            score += 0.5
            details['margin'] = {
                'free_margin_usd': free_margin,
                'percentage': free_margin_pct,
                'status': f'🔴 Margem crítica ({free_margin_pct:.0f}%)',
                'score': 0.5
            }
        
        # ==================
        # Drawdown da Sessão (2 pontos)
        # ==================
        session_pnl = position_data.get('session_pnl', 0)
        session_start = position_data.get('session_start_balance', account_balance)
        session_dd_pct = abs((session_pnl / session_start) * 100) if session_start > 0 and session_pnl < 0 else 0
        
        if session_dd_pct < 2:
            score += 2.0
            details['drawdown'] = {
                'session_pnl': session_pnl,
                'drawdown_pct': session_dd_pct,
                'status': f'🟢 Baixo ({session_dd_pct:.1f}%)',
                'score': 2.0
            }
        elif session_dd_pct < 5:
            score += 1.5
            details['drawdown'] = {
                'session_pnl': session_pnl,
                'drawdown_pct': session_dd_pct,
                'status': f'🟡 Moderado ({session_dd_pct:.1f}%)',
                'score': 1.5
            }
        elif session_dd_pct < 10:
            score += 1.0
            details['drawdown'] = {
                'session_pnl': session_pnl,
                'drawdown_pct': session_dd_pct,
                'status': f'🟠 Alto ({session_dd_pct:.1f}%)',
                'score': 1.0
            }
        else:
            score += 0.5
            details['drawdown'] = {
                'session_pnl': session_pnl,
                'drawdown_pct': session_dd_pct,
                'status': f'🔴 Crítico ({session_dd_pct:.1f}%)',
                'score': 0.5
            }
        
        # ==================
        # Análise Adicional
        # ==================
        warnings = []
        
        if exposure_pct > 15:
            warnings.append("Exposição muito alta - considere reduzir posição")
        
        if free_margin_pct < 50:
            warnings.append("Margem livre baixa - risco de liquidação")
        
        if session_dd_pct > 8:
            warnings.append("Drawdown elevado - considere parar de operar")
        
        if atr_pct > 4:
            warnings.append("Volatilidade muito alta - ajustar stop loss")
        
        # Status final
        percentage = (score / max_score) * 100
        
        if score >= 7.5:
            status = '🟢 SEGURO'
        elif score >= 5.0:
            status = '🟡 MODERADO'
        else:
            status = '🔴 ARRISCADO'
        
        return {
            'score': round(score, 2),
            'max_score': max_score,
            'percentage': round(percentage, 1),
            'status': status,
            'details': details,
            'warnings': warnings,
            'account_balance': account_balance
        }
    
    def calculate_position_size(self, account_balance: float, risk_percentage: float,
                               entry_price: float, stop_loss_price: float) -> Dict:
        """
        Calcula tamanho de posição baseado em risco
        
        Args:
            account_balance: Saldo da conta
            risk_percentage: % do capital a arriscar (ex: 1.0 = 1%)
            entry_price: Preço de entrada
            stop_loss_price: Preço do stop loss
        
        Returns:
            Dict com tamanho sugerido e métricas
        """
        
        # Valor em risco
        risk_amount = account_balance * (risk_percentage / 100)
        
        # Distância do stop
        stop_distance = abs(entry_price - stop_loss_price)
        stop_distance_pct = (stop_distance / entry_price) * 100
        
        # Tamanho da posição
        position_size_usd = risk_amount / (stop_distance_pct / 100)
        
        # Garantir que não ultrapasse limites
        max_position = account_balance * 0.15  # Máximo 15% do capital
        position_size_usd = min(position_size_usd, max_position)
        
        return {
            'position_size_usd': round(position_size_usd, 2),
            'risk_amount': round(risk_amount, 2),
            'stop_distance_pct': round(stop_distance_pct, 2),
            'exposure_pct': round((position_size_usd / account_balance) * 100, 2)
        }
    
    def calculate_stop_loss_take_profit(self, entry_price: float, direction: str,
                                       atr: float, risk_reward_ratio: float = 1.5) -> Dict:
        """
        Calcula níveis de stop loss e take profit baseados em ATR
        
        Args:
            entry_price: Preço de entrada
            direction: 'LONG' ou 'SHORT'
            atr: Valor do ATR
            risk_reward_ratio: Ratio de risco/recompensa (ex: 1.5)
        
        Returns:
            Dict com SL, TP e distâncias
        """
        
        # Stop loss: 0.75 ATR
        sl_distance = atr * 0.75
        
        # Take profit: SL distance * R:R ratio
        tp_distance = sl_distance * risk_reward_ratio
        
        if direction.upper() == 'LONG':
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:  # SHORT
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance
        
        return {
            'entry': round(entry_price, 2),
            'stop_loss': round(stop_loss, 2),
            'take_profit': round(take_profit, 2),
            'sl_distance_pct': round((sl_distance / entry_price) * 100, 2),
            'tp_distance_pct': round((tp_distance / entry_price) * 100, 2),
            'risk_reward': risk_reward_ratio
        }
    
    def _empty_result(self) -> Dict:
        """Retorna resultado vazio em caso de erro"""
        return {
            'score': 0.0,
            'max_score': 10.0,
            'percentage': 0.0,
            'status': '🔴 ERRO',
            'details': {},
            'warnings': [],
            'account_balance': 0.0
        }


# Teste unitário
if __name__ == '__main__':
    # Dados de teste
    test_position_data = {
        'total_exposure_usd': 500,  # 5% de 10000
        'free_margin_usd': 8500,
        'session_pnl': -80,
        'session_start_balance': 10000
    }
    
    test_volatility_data = {
        'atr': 900,  # $900
        'atr_percentage': 2.1  # 2.1%
    }
    
    analyzer = RiskAnalyzer()
    result = analyzer.analyze(test_position_data, test_volatility_data, account_balance=10000)
    
    print("="*60)
    print("TESTE: Risk Analyzer")
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
    
    print("\n" + "="*60)
    print("TESTE: Cálculo de Position Sizing")
    print("="*60)
    
    pos_size = analyzer.calculate_position_size(
        account_balance=10000,
        risk_percentage=1.0,  # 1% de risco
        entry_price=43200,
        stop_loss_price=42450
    )
    
    print(f"Tamanho da Posição: ${pos_size['position_size_usd']}")
    print(f"Risco: ${pos_size['risk_amount']}")
    print(f"Stop Distance: {pos_size['stop_distance_pct']}%")
    print(f"Exposição: {pos_size['exposure_pct']}%")
    
    print("\n" + "="*60)
    print("TESTE: Cálculo de SL/TP")
    print("="*60)
    
    levels = analyzer.calculate_stop_loss_take_profit(
        entry_price=43200,
        direction='LONG',
        atr=900,
        risk_reward_ratio=1.5
    )
    
    print(f"Entry: ${levels['entry']}")
    print(f"Stop Loss: ${levels['stop_loss']} ({levels['sl_distance_pct']}%)")
    print(f"Take Profit: ${levels['take_profit']} ({levels['tp_distance_pct']}%)")
    print(f"R:R Ratio: 1:{levels['risk_reward']}")
    print("="*60)
