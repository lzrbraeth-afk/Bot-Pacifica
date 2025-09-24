"""
Grid Calculator - Cálculos de níveis, quantidades e validações
"""

import os
from typing import List, Dict, Tuple, Optional
from decimal import Decimal, ROUND_DOWN
import logging
import math
import time
import statistics
from collections import deque

class GridCalculator:
    def __init__(self, auth_client=None):
        self.logger = logging.getLogger('PacificaBot.GridCalculator')
        
        # Configurações do ENV
        self.leverage = int(os.getenv('LEVERAGE', '10'))
        self.grid_levels = int(os.getenv('GRID_LEVELS', '20'))
        self.spacing_percent = float(os.getenv('GRID_SPACING_PERCENT', '0.5'))
        self.order_size_usd = float(os.getenv('ORDER_SIZE_USD', '100'))
        self.grid_distribution = os.getenv('GRID_DISTRIBUTION', 'symmetric')
        self.strategy_type = os.getenv('STRATEGY_TYPE', 'market_making')
        self.symbol = os.getenv('SYMBOL', 'BTC')

        # Configurações para grid adaptativo
        self.adaptive_mode = os.getenv('ADAPTIVE_GRID', 'true').lower() == 'true'
        self.volatility_window = int(os.getenv('VOLATILITY_WINDOW', '20'))
        self.volatility_multiplier_min = float(os.getenv('VOLATILITY_MULT_MIN', '0.5'))
        self.volatility_multiplier_max = float(os.getenv('VOLATILITY_MULT_MAX', '2.0'))
        
        # Histórico de preços para cálculo de volatilidade
        self.price_history = deque(maxlen=self.volatility_window)
        self.last_volatility = 0.0

         # Informações do mercado
        self.tick_size = 1.0  # Default para BTC
        self.lot_size = 0.00001  # Default
        self.min_order_size = 10  # USD
        
        # Buscar info do mercado se auth fornecido
        if auth_client:
            self._load_market_info(auth_client)
        
        # Para Pure Grid
        self.range_min = float(os.getenv('RANGE_MIN', '0'))
        self.range_max = float(os.getenv('RANGE_MAX', '0'))
        
        self.logger.info(f"Grid adaptativo: {'ATIVO' if self.adaptive_mode else 'INATIVO'}")
        self.logger.info(f"GridCalculator inicializado: {self.grid_levels} níveis, {self.spacing_percent}% spacing, tick_size={self.tick_size}")
    
    def calculate_grid_levels(self, current_price: float) -> Dict[str, List[float]]:
        """Calcula os níveis do grid baseado na estratégia"""
        
        if self.strategy_type == 'pure_grid' and self.range_min > 0 and self.range_max > 0:
            return self._calculate_pure_grid_levels(current_price)
        else:
            return self._calculate_market_making_levels(current_price)
    
    def _calculate_pure_grid_levels(self, current_price: float) -> Dict[str, List[float]]:
        """Calcula níveis para Pure Grid (range fixo)"""
        
        price_range = self.range_max - self.range_min
        level_spacing = price_range / (self.grid_levels - 1)
        
        buy_levels = []
        sell_levels = []
        
        for i in range(self.grid_levels):
                price = self.range_min + (i * level_spacing)
                
                if price < current_price:
                    buy_levels.append(round(price))  # SEM decimais
                elif price > current_price:
                    sell_levels.append(round(price))  # SEM decimais
        
        self.logger.info(f"Pure Grid: {len(buy_levels)} buy levels, {len(sell_levels)} sell levels")
        
        return {
            'buy_levels': buy_levels,
            'sell_levels': sell_levels,
            'current_price': current_price
        }
    
    def _calculate_market_making_levels(self, current_price: float) -> Dict[str, List[float]]:
        """Calcula níveis para Market Making (dinâmico) com espaçamento adaptativo"""
        
        # 🆕 USAR ESPAÇAMENTO ADAPTATIVO
        effective_spacing = self.calculate_adaptive_spacing(current_price)
        
        # Distribuir níveis
        if self.grid_distribution == 'bullish':
            buy_count = int(self.grid_levels * 0.6)
            sell_count = self.grid_levels - buy_count
        elif self.grid_distribution == 'bearish':
            sell_count = int(self.grid_levels * 0.6)
            buy_count = self.grid_levels - sell_count
        else:  # symmetric
            buy_count = self.grid_levels // 2
            sell_count = self.grid_levels // 2
        
        buy_levels = []
        sell_levels = []
        
        # Log do espaçamento sendo usado
        self.logger.info(f"Calculando grid: {buy_count} buy + {sell_count} sell = {buy_count + sell_count} total")
        self.logger.info(f"📊 Espaçamento efetivo: {effective_spacing:.3f}% (base: {self.spacing_percent:.3f}%)")

        # Calcular níveis de compra (abaixo do preço) - USAR effective_spacing
        for i in range(1, buy_count + 1):
            price_offset = (effective_spacing / 100) * i
            price = current_price * (1 - price_offset)
            buy_levels.append(self.round_price(price))
        
        # Calcular níveis de venda (acima do preço) - USAR effective_spacing
        for i in range(1, sell_count + 1):
            price_offset = (effective_spacing / 100) * i
            price = current_price * (1 + price_offset)
            sell_levels.append(self.round_price(price))
        
        self.logger.info(f"Market Making: {len(buy_levels)} buy, {len(sell_levels)} sell levels")
        
        return {
            'buy_levels': sorted(buy_levels, reverse=True),  # mais próximos primeiro
            'sell_levels': sorted(sell_levels),  # mais próximos primeiro
            'current_price': current_price,
            'effective_spacing': effective_spacing  # 🆕 ADICIONAR para tracking
        }
        
    def calculate_volatility(self, prices: List[float]) -> float:
        """Calcula volatilidade baseada em preços históricos (usando ATR simplificado)"""
        
        if len(prices) < 2:
            return 0.01  # Volatilidade padrão baixa
        
        # 🔧 FILTRAR PREÇOS INVÁLIDOS ANTES DE CALCULAR VOLATILIDADE
        valid_prices = [p for p in prices if p > 0]
        
        if len(valid_prices) < 2:
            self.logger.warning("⚠️ Preços válidos insuficientes para calcular volatilidade")
            return 0.01
        
        # Calcular retornos logarítmicos
        returns = []
        for i in range(1, len(valid_prices)):
            prev_price = valid_prices[i-1]
            curr_price = valid_prices[i]
            
            # 🔧 VERIFICAÇÃO ADICIONAL DE SEGURANÇA
            if prev_price > 0 and curr_price > 0:
                return_pct = (curr_price - prev_price) / prev_price
                returns.append(return_pct)
        
        if not returns:
            return 0.01
        
        # Volatilidade = desvio padrão dos retornos
        volatility = statistics.stdev(returns) if len(returns) > 1 else abs(returns[0])
        
        # Normalizar para evitar valores extremos
        volatility = max(0.001, min(0.1, volatility))  # Entre 0.1% e 10%
        
        self.logger.debug(f"📊 Volatilidade calculada: {volatility:.4f} ({len(returns)} retornos)")
        
        return volatility

    def calculate_adaptive_spacing(self, current_price: float) -> float:
        """Calcula espaçamento adaptativo baseado na volatilidade recente"""
        
        if not self.adaptive_mode:
            return self.spacing_percent
        
        # 🔧 VERIFICAR PREÇO VÁLIDO
        if current_price <= 0:
            self.logger.warning(f"⚠️ Preço inválido para spacing adaptativo: {current_price}")
            return self.spacing_percent
        
        # Adicionar preço atual ao histórico
        self.price_history.append(current_price)
        
        # Precisa de pelo menos 5 preços para calcular volatilidade
        if len(self.price_history) < 5:
            self.logger.debug("📊 Histórico insuficiente - usando espaçamento base")
            return self.spacing_percent
        
        # Calcular volatilidade atual
        current_volatility = self.calculate_volatility(list(self.price_history))
        self.last_volatility = current_volatility
        
        # Definir volatilidade de referência (média do que consideramos "normal")
        reference_volatility = 0.005  # 0.5% - ajustar baseado no ativo
        
        # 🔧 VERIFICAÇÃO ADICIONAL DE SEGURANÇA  
        if reference_volatility <= 0:
            self.logger.error("❌ Volatilidade de referência inválida!")
            return self.spacing_percent
        
        # Calcular multiplicador baseado na volatilidade
        volatility_ratio = current_volatility / reference_volatility
        
        # Aplicar limites ao multiplicador
        multiplier = max(
            self.volatility_multiplier_min,
            min(self.volatility_multiplier_max, volatility_ratio)
        )
        
        # Calcular novo espaçamento
        adaptive_spacing = self.spacing_percent * multiplier
        
        # 🔧 GARANTIR QUE SPACING NUNCA SEJA ZERO OU NEGATIVO
        if adaptive_spacing <= 0:
            self.logger.warning(f"⚠️ Spacing adaptativo inválido: {adaptive_spacing} - usando base")
            adaptive_spacing = self.spacing_percent
        
        self.logger.info(f"📊 Grid adaptativo: volatilidade={current_volatility:.4f}, "
                        f"multiplicador={multiplier:.2f}, spacing={adaptive_spacing:.3f}%")
        
        return adaptive_spacing

    def get_volatility_status(self) -> Dict:
        """Retorna status da volatilidade para monitoramento"""
        
        return {
            'adaptive_mode': self.adaptive_mode,
            'current_volatility': self.last_volatility,
            'price_history_count': len(self.price_history),
            'base_spacing': self.spacing_percent,
            'current_spacing': self.calculate_adaptive_spacing(
                self.price_history[-1] if self.price_history else 0
            ) if self.price_history else self.spacing_percent
        }
  
    def calculate_quantity(self, price: float, order_size_usd: Optional[float] = None) -> float:
        """Calcula quantidade de tokens baseado no valor USD e alavancagem"""
        
        if order_size_usd is None:
            order_size_usd = self.order_size_usd
        
        # 🔧 VERIFICAR PREÇO VÁLIDO
        if price <= 0:
            self.logger.error(f"❌ Preço inválido para cálculo de quantidade: ${price}")
            return 0.0
        
        # Calcular quantidade bruta
        quantity = order_size_usd / price
        
        # Arredondar para lot_size
        quantity = self.round_quantity(quantity)
        
        # Garantir quantidade mínima
        min_qty = self.min_order_size / price
        if quantity < min_qty:
            quantity = self.round_quantity(min_qty)
        
        return quantity
    
    def _load_market_info(self, auth_client):
        """Carrega informações do mercado (tick_size, lot_size, etc)"""
        try:
            self.logger.info(f"🔍 Buscando market info para {self.symbol}...")
            
            info = auth_client.get_symbol_info(self.symbol)
            
            if info:
                self.tick_size = float(info.get('tick_size', 1))
                self.lot_size = float(info.get('lot_size', 0.00001))
                self.min_order_size = float(info.get('min_order_size', 10))
                
                self.logger.info(f"✅ Market info carregado para {self.symbol}:")
                self.logger.info(f"   tick_size: {self.tick_size}")
                self.logger.info(f"   lot_size: {self.lot_size}")
                self.logger.info(f"   min_order_size: {self.min_order_size}")
                return True
            else:
                self.logger.warning(f"⚠️ Market info não encontrado para {self.symbol}")
                self.logger.warning(f"⚠️ Usando valores padrão: tick={self.tick_size}, lot={self.lot_size}")
                return False
                
        except Exception as e:
            self.logger.error(f"⚠️ Erro ao carregar market info: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False
    
    def round_price(self, price: float) -> float:
        """Arredonda preço para múltiplo de tick_size"""
        
        if self.tick_size >= 1:
            return float(round(price))
        
        # Usar Decimal para evitar erros de precisão
        from decimal import Decimal, ROUND_HALF_UP
        
        price_dec = Decimal(str(price))
        tick_dec = Decimal(str(self.tick_size))
        
        # Arredondar para múltiplo mais próximo
        multiple = (price_dec / tick_dec).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        result = float(multiple * tick_dec)
        
        # Forçar casas decimais corretas
        if self.tick_size == 0.01:
            return round(result, 2)
        elif self.tick_size == 0.001:
            return round(result, 3)
        elif self.tick_size == 0.0001:
            return round(result, 4)
        else:
            return round(result, 5)
    
    def round_quantity(self, quantity: float) -> float:
        """Arredonda quantidade para múltiplo de lot_size"""
        import math
        
        if self.lot_size == 0:
            return quantity
        
        # Arredondar para baixo (floor) para o múltiplo válido
        multiples = math.floor(quantity / self.lot_size)
        
        # Calcular resultado
        result = multiples * self.lot_size
        
        # Determinar precisão decimal baseado no lot_size
        lot_str = str(self.lot_size)
        if '.' in lot_str:
            decimals = len(lot_str.split('.')[1].rstrip('0'))
        else:
            decimals = 0
        
        # Retornar com precisão correta
        return round(result, max(decimals, 2))  # Mínimo 2 decimais para segurança

    
    def calculate_required_margin(self, orders: List[Dict]) -> float:
        """Calcula margem total necessária para lista de ordens"""
        
        total_margin = 0
        for order in orders:
            order_value = order['price'] * order['quantity']
            margin = order_value / self.leverage
            total_margin += margin
        
        return total_margin
    
    def validate_grid_parameters(self) -> Tuple[bool, List[str]]:
        """Valida parâmetros do grid"""
        
        errors = []
        
        if self.grid_levels < 2:
            errors.append("GRID_LEVELS deve ser >= 2")
        
        if self.spacing_percent <= 0:
            errors.append("GRID_SPACING_PERCENT deve ser > 0")
        
        if self.order_size_usd <= 0:
            errors.append("ORDER_SIZE_USD deve ser > 0")
        
        if self.leverage < 1:
            errors.append("LEVERAGE deve ser >= 1")
        
        if self.strategy_type == 'pure_grid':
            if self.range_min >= self.range_max:
                errors.append("RANGE_MIN deve ser < RANGE_MAX")
            if self.range_min <= 0:
                errors.append("RANGE_MIN deve ser > 0")
        
        if errors:
            return False, errors
        
        return True, []
    
    def should_shift_grid(self, current_price: float, grid_center: float) -> bool:
        """Verifica se deve deslocar o grid baseado no threshold"""
        
        threshold = float(os.getenv('GRID_SHIFT_THRESHOLD_PERCENT', '1'))
        
        price_change_percent = abs((current_price - grid_center) / grid_center * 100)
        
        if price_change_percent >= threshold:
            self.logger.info(f"Grid shift necessário: {price_change_percent:.2f}% > {threshold}%")
            return True
        
        return False
    
    def calculate_profit_target(self, entry_price: float, side: str) -> float:
        """Calcula preço alvo de lucro baseado no próximo nível do grid"""
        
        if side == 'buy':
            # Se comprou, vender no próximo nível acima
            target_price = entry_price * (1 + self.spacing_percent / 100)
            # 🆕 NEW: Log debug para rastreamento
            self.logger.debug(f"Target para BUY: ${entry_price} -> ${target_price} (+{self.spacing_percent}%)")
            # 🆕 END NEW
        else:  # sell
            # Se vendeu, comprar no próximo nível abaixo
            target_price = entry_price * (1 - self.spacing_percent / 100)
            # 🆕 NEW: Log debug para rastreamento
            self.logger.debug(f"Target para SELL: ${entry_price} -> ${target_price} (-{self.spacing_percent}%)")
            # 🆕 END NEW
        
        # 🆕 NEW: Arredondar para tick_size válido
        target_price = self.round_price(target_price)
        # 🆕 END NEW
        
        # 🔧 MODIFIED: Retornar preço arredondado
        # ANTES: return round(target_price)
        return target_price
        # 🔧 END MODIFIED

    def format_order_for_api(self, price: float, quantity: float, side: str, symbol: str = None) -> Dict:
        """Formata ordem para enviar à API"""
        
        if symbol is None:
            symbol = os.getenv('SYMBOL', 'BTC')
        
        return {
            'symbol': symbol,
            'price': str(price),
            'amount': str(quantity),
            'side': 'bid' if side == 'buy' else 'ask',
            'tif': 'GTC',  # Good Till Cancel
            'reduce_only': False
        }