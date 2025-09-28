"""
🚀 ALGORITMO DE SINAIS MELHORADO - MULTI-ASSET
Versão aprimorada com análise técnica e filtros de qualidade
"""

import os
import math
from typing import Dict, Optional, List
from datetime import datetime, timedelta

class EnhancedSignalDetector:
    """Detector de sinais melhorado com múltiplos indicadores"""
    
    def __init__(self, logger):
        self.logger = logger
        
        # Configurações do algoritmo
        self.min_history_length = 20
        self.sma_short_period = 5
        self.sma_long_period = 20
        self.rsi_period = 14
        self.min_signal_quality = 60
        
        # Pesos dos indicadores (total = 100)
        self.momentum_weight = 30
        self.trend_weight = 25
        self.rsi_weight = 20
        self.volatility_weight = 15
        self.price_confirmation_weight = 10
        
        # Filtros
        self.max_volatility = 5.0  # %
        self.min_volatility = 0.2  # %
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        
    def detect_signal(self, symbol: str, price_history: List[float], 
                     current_price: float, price_change_threshold: float) -> Optional[Dict]:
        """
        Detecta sinais de trading com análise técnica avançada
        
        Returns:
            Dict com informações do sinal ou None se não há sinal válido
        """
        
        if len(price_history) < self.min_history_length:
            self.logger.debug(f"📊 {symbol}: Histórico insuficiente ({len(price_history)} < {self.min_history_length})")
            return None
        
        try:
            # 1. ANÁLISE DE TENDÊNCIA
            trend_data = self._analyze_trend(price_history, current_price)
            
            # 2. ANÁLISE DE MOMENTUM
            momentum_data = self._analyze_momentum(price_history, current_price)
            
            # 3. RSI (Índice de Força Relativa)
            rsi_data = self._calculate_rsi(price_history)
            
            # 4. ANÁLISE DE VOLATILIDADE
            volatility_data = self._analyze_volatility(price_history)
            
            # 5. CONFIRMAÇÃO DE PREÇO
            price_confirmation = self._check_price_confirmation(price_history, current_price, price_change_threshold)
            
            # 6. CALCULAR SCORE DE QUALIDADE
            signal_quality = self._calculate_signal_quality(
                trend_data, momentum_data, rsi_data, 
                volatility_data, price_confirmation, price_change_threshold
            )
            
            # 7. VALIDAR SINAL
            if signal_quality['total_score'] >= self.min_signal_quality:
                
                # Determinar direção
                side = 'LONG' if momentum_data['momentum'] > 0 else 'SHORT'
                
                # Calcular confiança
                confidence = min(100, signal_quality['total_score'] + abs(momentum_data['momentum']) * 5)
                
                signal_info = {
                    'symbol': symbol,
                    'side': side,
                    'quality_score': signal_quality['total_score'],
                    'confidence': confidence,
                    'momentum': momentum_data['momentum'],
                    'momentum_strength': abs(momentum_data['momentum']),
                    'trend': trend_data['trend'],
                    'trend_strength': trend_data['strength'],
                    'rsi': rsi_data['rsi'],
                    'volatility': volatility_data['volatility'],
                    'price_change': momentum_data['price_change'],
                    'components': signal_quality['components'],
                    'timestamp': datetime.now()
                }
                
                self._log_signal_details(signal_info)
                return signal_info
            
            else:
                self.logger.debug(f"📊 {symbol}: Sinal rejeitado - Score {signal_quality['total_score']} < {self.min_signal_quality}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Erro na detecção de sinal para {symbol}: {e}")
            return None
    
    def _analyze_trend(self, prices: List[float], current_price: float) -> Dict:
        """Analisa tendência usando médias móveis"""
        
        # Média móvel curta
        sma_short = sum(prices[-self.sma_short_period:]) / self.sma_short_period
        
        # Média móvel longa
        sma_long = sum(prices[-self.sma_long_period:]) / self.sma_long_period
        
        # Determinar tendência
        if sma_short > sma_long:
            trend = "BULLISH"
            strength = (sma_short - sma_long) / sma_long * 100
        else:
            trend = "BEARISH"
            strength = (sma_long - sma_short) / sma_long * 100
        
        return {
            'trend': trend,
            'strength': strength,
            'sma_short': sma_short,
            'sma_long': sma_long,
            'current_vs_sma_short': (current_price - sma_short) / sma_short * 100
        }
    
    def _analyze_momentum(self, prices: List[float], current_price: float) -> Dict:
        """Analisa momentum comparando com períodos anteriores"""
        
        # Momentum de 10 períodos
        momentum_10 = (current_price - prices[-11]) / prices[-11] * 100 if len(prices) >= 11 else 0
        
        # Momentum de 5 períodos
        momentum_5 = (current_price - prices[-6]) / prices[-6] * 100 if len(prices) >= 6 else 0
        
        # Momentum de 3 períodos (original)
        momentum_3 = (current_price - prices[-4]) / prices[-4] * 100 if len(prices) >= 4 else 0
        
        # Momentum médio ponderado
        momentum = (momentum_3 * 0.5 + momentum_5 * 0.3 + momentum_10 * 0.2)
        
        return {
            'momentum': momentum,
            'momentum_3': momentum_3,
            'momentum_5': momentum_5,
            'momentum_10': momentum_10,
            'price_change': momentum_3  # Para compatibilidade
        }
    
    def _calculate_rsi(self, prices: List[float]) -> Dict:
        """Calcula RSI (Relative Strength Index)"""
        
        if len(prices) < self.rsi_period + 1:
            return {'rsi': 50, 'condition': 'NEUTRAL'}  # Valor neutro por padrão
        
        # Calcular ganhos e perdas
        gains = []
        losses = []
        
        for i in range(len(prices) - self.rsi_period, len(prices)):
            diff = prices[i] - prices[i-1]
            if diff > 0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(diff))
        
        # Média dos ganhos e perdas
        avg_gain = sum(gains) / len(gains) if gains else 0.01
        avg_loss = sum(losses) / len(losses) if losses else 0.01
        
        # Calcular RSI
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        # Determinar condição
        if rsi <= self.rsi_oversold:
            condition = 'OVERSOLD'
        elif rsi >= self.rsi_overbought:
            condition = 'OVERBOUGHT'
        else:
            condition = 'NEUTRAL'
        
        return {
            'rsi': rsi,
            'condition': condition,
            'avg_gain': avg_gain,
            'avg_loss': avg_loss
        }
    
    def _analyze_volatility(self, prices: List[float]) -> Dict:
        """Analisa volatilidade dos preços"""
        
        recent_prices = prices[-10:] if len(prices) >= 10 else prices
        
        # Calcular média
        avg_price = sum(recent_prices) / len(recent_prices)
        
        # Calcular desvio padrão
        variance = sum((p - avg_price) ** 2 for p in recent_prices) / len(recent_prices)
        std_dev = math.sqrt(variance)
        
        # Volatilidade percentual
        volatility = (std_dev / avg_price) * 100 if avg_price > 0 else 0
        
        # Classificar volatilidade
        if volatility < self.min_volatility:
            classification = 'LOW'
        elif volatility > self.max_volatility:
            classification = 'HIGH'
        else:
            classification = 'NORMAL'
        
        return {
            'volatility': volatility,
            'classification': classification,
            'std_dev': std_dev,
            'avg_price': avg_price
        }
    
    def _check_price_confirmation(self, prices: List[float], current_price: float, threshold: float) -> Dict:
        """Verifica confirmação do movimento de preço"""
        
        if len(prices) < 2:
            return {'confirmation': 0, 'meets_threshold': False}
        
        # Mudança em relação ao último preço
        last_price_change = abs(current_price - prices[-1]) / prices[-1] * 100
        
        # Mudança em relação a 2 períodos atrás
        if len(prices) >= 2:
            two_period_change = abs(current_price - prices[-2]) / prices[-2] * 100
        else:
            two_period_change = 0
        
        # Confirmação média
        confirmation = (last_price_change + two_period_change) / 2
        
        # Verifica se atende ao threshold
        meets_threshold = confirmation >= threshold * 0.5
        
        return {
            'confirmation': confirmation,
            'last_price_change': last_price_change,
            'two_period_change': two_period_change,
            'meets_threshold': meets_threshold
        }
    
    def _calculate_signal_quality(self, trend_data: Dict, momentum_data: Dict, 
                                 rsi_data: Dict, volatility_data: Dict, 
                                 price_confirmation: Dict, threshold: float) -> Dict:
        """Calcula score de qualidade do sinal (0-100)"""
        
        components = {}
        total_score = 0
        
        # 1. MOMENTUM (30 pontos)
        momentum_score = 0
        if abs(momentum_data['momentum']) >= threshold * 2:
            momentum_score = self.momentum_weight
        elif abs(momentum_data['momentum']) >= threshold:
            momentum_score = self.momentum_weight * 0.7
        elif abs(momentum_data['momentum']) >= threshold * 0.5:
            momentum_score = self.momentum_weight * 0.4
        
        components['momentum'] = momentum_score
        total_score += momentum_score
        
        # 2. TENDÊNCIA (25 pontos) 
        trend_score = 0
        momentum_direction = 1 if momentum_data['momentum'] > 0 else -1
        trend_direction = 1 if trend_data['trend'] == 'BULLISH' else -1
        
        if momentum_direction == trend_direction:
            trend_score = self.trend_weight  # Tendência confirma momentum
        elif trend_data['strength'] < 0.1:  # Tendência fraca
            trend_score = self.trend_weight * 0.5
        
        components['trend'] = trend_score
        total_score += trend_score
        
        # 3. RSI (20 pontos)
        rsi_score = 0
        rsi_value = rsi_data['rsi']
        
        if rsi_data['condition'] == 'NEUTRAL':
            rsi_score = self.rsi_weight  # RSI não em extremo é bom
        elif rsi_data['condition'] == 'OVERSOLD' and momentum_data['momentum'] > 0:
            rsi_score = self.rsi_weight * 1.2  # Oversold + momentum up = excelente
        elif rsi_data['condition'] == 'OVERBOUGHT' and momentum_data['momentum'] < 0:
            rsi_score = self.rsi_weight * 1.2  # Overbought + momentum down = excelente
        else:
            rsi_score = self.rsi_weight * 0.3  # RSI contra o momentum
        
        components['rsi'] = min(rsi_score, self.rsi_weight)  # Cap no peso máximo
        total_score += components['rsi']
        
        # 4. VOLATILIDADE (15 pontos)
        volatility_score = 0
        if volatility_data['classification'] == 'NORMAL':
            volatility_score = self.volatility_weight
        elif volatility_data['classification'] == 'LOW':
            volatility_score = self.volatility_weight * 0.6
        else:  # HIGH
            volatility_score = self.volatility_weight * 0.3
        
        components['volatility'] = volatility_score
        total_score += volatility_score
        
        # 5. CONFIRMAÇÃO DE PREÇO (10 pontos)
        price_score = 0
        if price_confirmation['meets_threshold']:
            price_score = self.price_confirmation_weight
        elif price_confirmation['confirmation'] >= threshold * 0.25:
            price_score = self.price_confirmation_weight * 0.5
        
        components['price_confirmation'] = price_score
        total_score += price_score
        
        return {
            'total_score': round(total_score, 1),
            'components': components
        }
    
    def _log_signal_details(self, signal_info: Dict):
        """Log detalhado do sinal detectado"""
        
        symbol = signal_info['symbol']
        side = signal_info['side']
        quality = signal_info['quality_score']
        confidence = signal_info['confidence']
        
        self.logger.info(f"🎯 SINAL {side} {symbol} - Quality: {quality}/100, Confidence: {confidence}/100")
        self.logger.info(f"   📈 Momentum: {signal_info['momentum']:.2f}%, Trend: {signal_info['trend']}")
        self.logger.info(f"   📊 RSI: {signal_info['rsi']:.1f}, Volatility: {signal_info['volatility']:.2f}%")
        
        # Log dos componentes
        components = signal_info['components']
        self.logger.debug(f"   🔍 Components: M:{components['momentum']:.1f} T:{components['trend']:.1f} R:{components['rsi']:.1f} V:{components['volatility']:.1f} P:{components['price_confirmation']:.1f}")
    
    def get_algorithm_status(self) -> Dict:
        """Retorna status do algoritmo"""
        
        return {
            'version': '2.0_enhanced',
            'min_signal_quality': self.min_signal_quality,
            'indicators': ['SMA', 'RSI', 'Momentum', 'Volatility', 'Price Confirmation'],
            'weights': {
                'momentum': self.momentum_weight,
                'trend': self.trend_weight,
                'rsi': self.rsi_weight,
                'volatility': self.volatility_weight,
                'price_confirmation': self.price_confirmation_weight
            }
        }

    def detect_signal_with_api_history(self, symbol: str, auth_client, 
                                    current_price: float, price_change_threshold: float) -> Optional[Dict]:
        """
        🆕 VERSÃO MELHORADA: Usa histórico da API se não tiver dados suficientes
        """
        
        # Verificar se temos histórico suficiente no cache
        price_history = getattr(self, 'price_cache', {}).get(symbol, [])
        
        if len(price_history) < self.min_history_length:
            self.logger.info(f"🔄 {symbol}: Buscando histórico da API ({len(price_history)} < {self.min_history_length})")
            
            # 🔥 BUSCAR HISTÓRICO DA API
            api_history = auth_client.get_historical_data(
                symbol=symbol, 
                interval="1m", 
                periods=self.min_history_length + 5  # Pegar alguns a mais
            )
            
            if api_history and len(api_history) >= self.min_history_length:
                self.logger.info(f"✅ {symbol}: Histórico obtido da API - {len(api_history)} preços")
                
                # Usar histórico da API + preço atual
                combined_history = api_history + [current_price]
                return self.detect_signal(symbol, combined_history, current_price, price_change_threshold)
            else:
                self.logger.warning(f"⚠️ {symbol}: Histórico insuficiente na API também")
                return None
        
        # Se temos histórico suficiente, usar método normal
        return self.detect_signal(symbol, price_history, current_price, price_change_threshold)