"""
Strategy Logger - Sistema de Logs Específicos por Estratégia
Filtra e personaliza logs baseado no tipo de estratégia ativa
"""

import logging
import os
from typing import Dict, Any, Optional


class StrategyLogger:
    """Logger que adapta mensagens baseado na estratégia ativa"""
    
    def __init__(self, base_logger: logging.Logger, strategy_type: str):
        self.base_logger = base_logger
        self.strategy_type = strategy_type.lower()
        
        # Definir filtros de mensagens por estratégia
        self.setup_filters()
    
    def setup_filters(self):
        """Configurar filtros específicos por estratégia"""
        
        # Palavras/frases que devem ser filtradas para multi_asset e multi_asset_enhanced
        self.multi_asset_filters = [
            'grid', 'Grid', 'GRID',
            'níveis', 'níveis', 'levels',
            'spacing', 'espaçamento',
            'range', 'Range', 'RANGE',
            'rebalanceamento', 'rebalancing'
        ]
        
        # Substituições específicas para scalping
        self.scalping_replacements = {
            'Grid': 'Scalping',
            'grid': 'análise direcional',
            'níveis': 'sinais de entrada',
            'levels': 'entry signals',
            'rebalanceamento': 'análise de direção',
            'rebalancing': 'direction analysis',
            'ordens': 'trades',
            'orders': 'trades'
        }
        
        # Substituições específicas para multi_asset
        self.multi_asset_replacements = {
            'Grid': 'Multi-Asset',
            'grid': 'estratégia',
            'níveis': 'posições',
            'levels': 'positions',
            'rebalanceamento': 'análise de mercado',
            'rebalancing': 'market analysis'
        }
        
        # Substituições específicas para multi_asset_enhanced
        self.enhanced_replacements = {
            'Grid': 'Enhanced Multi-Asset',
            'grid': 'algoritmo inteligente',
            'níveis': 'sinais detectados',
            'levels': 'detected signals',
            'rebalanceamento': 'análise técnica avançada',
            'rebalancing': 'advanced technical analysis'
        }
        
        # Palavras que devem ser filtradas para grid strategies
        self.grid_filters = [
            'multi-asset', 'Multi-Asset', 'MULTI-ASSET',
            'scalping', 'Scalping', 'SCALPING'
        ]
        
        # Palavras que devem ser filtradas para scalping strategy
        self.scalping_filters = [
            'grid', 'Grid', 'GRID',
            'multi-asset', 'Multi-Asset', 'MULTI-ASSET'
        ]
        
    def _should_filter_message(self, message: str) -> bool:
        """Determinar se uma mensagem deve ser filtrada"""
        
        # Mensagens críticas sempre passam
        critical_keywords = ['erro', 'error', 'falhou', 'failed', 'crítico', 'critical']
        if any(word in message.lower() for word in critical_keywords):
            return True
            
        # Mensagens de inicialização sempre passam
        init_keywords = ['inicializando', 'initializing', 'carregados', 'loaded', 'pronto', 'ready']
        if any(word in message.lower() for word in init_keywords):
            return True
        
        if self.strategy_type == 'scalping':
            # Para scalping, filtrar mensagens relacionadas ao grid e multi-asset
            for filter_word in self.scalping_filters:
                if filter_word.lower() in message.lower():
                    return False  # Filtrar (não mostrar)
                    
        elif self.strategy_type in ['multi_asset', 'multi_asset_enhanced']:
            # Para multi_asset e enhanced, filtrar mensagens relacionadas ao grid tradicional
            for filter_word in self.multi_asset_filters:
                if filter_word.lower() in message.lower():
                    return False  # Filtrar (não mostrar)
                    
        elif self.strategy_type in ['grid', 'pure_grid', 'market_making', 'dynamic_grid']:
            # Para grid strategies, filtrar mensagens de multi-asset e scalping
            for filter_word in self.grid_filters:
                if filter_word.lower() in message.lower():
                    return False  # Filtrar (não mostrar)
                    
        return True  # Não filtrar
        
    def _adapt_message(self, message: str) -> str:
        """Adaptar mensagem para a estratégia ativa"""
        
        adapted_message = message
        
        if self.strategy_type == 'scalping':
            # Substituir termos específicos para scalping direcional
            for old_term, new_term in self.scalping_replacements.items():
                adapted_message = adapted_message.replace(old_term, new_term)
        elif self.strategy_type == 'multi_asset':
            # Substituir termos específicos do grid para multi_asset básico
            for old_term, new_term in self.multi_asset_replacements.items():
                adapted_message = adapted_message.replace(old_term, new_term)
        elif self.strategy_type == 'multi_asset_enhanced':
            # Substituir termos específicos para enhanced strategy
            for old_term, new_term in self.enhanced_replacements.items():
                adapted_message = adapted_message.replace(old_term, new_term)
                
        return adapted_message
    
    def _get_strategy_prefix(self) -> str:
        """Obter prefixo específico da estratégia"""
        
        prefixes = {
            'scalping': '🚀',           # Foguete para velocidade do scalping
            'multi_asset': '🌐',        # Globo para múltiplos mercados
            'multi_asset_enhanced': '🧠', # Cérebro para IA avançada
            'grid': '📊',               # Gráfico para grid genérico
            'pure_grid': '�',          # Régua para grid fixo/preciso
            'market_making': '🎯',      # Alvo para market making
            'dynamic_grid': '⚡'        # Raio para grid dinâmico/adaptativo
        }
        
        return prefixes.get(self.strategy_type, '🤖')
    
    def info(self, message: str, force: bool = False):
        """Log INFO com filtragem por estratégia"""
        
        if not force and not self._should_filter_message(message):
            return
            
        adapted_message = self._adapt_message(message)
        self.base_logger.info(adapted_message)
    
    def debug(self, message: str, force: bool = False):
        """Log DEBUG com filtragem por estratégia"""
        
        if not force and not self._should_filter_message(message):
            return
            
        adapted_message = self._adapt_message(message)
        self.base_logger.debug(adapted_message)
    
    def warning(self, message: str, force: bool = False):
        """Log WARNING - sempre mostrar avisos importantes"""
        
        adapted_message = self._adapt_message(message)
        self.base_logger.warning(adapted_message)
    
    def error(self, message: str, force: bool = False):
        """Log ERROR - sempre mostrar erros"""
        
        adapted_message = self._adapt_message(message)
        self.base_logger.error(adapted_message)
    
    # Métodos específicos para Enhanced Strategy
    def enhanced_signal(self, symbol: str, score: int, confidence: float, action: str):
        """Log específico para sinais Enhanced"""
        if self.strategy_type == 'multi_asset_enhanced':
            message = f"🧠 {symbol} - Score: {score}/100, Conf: {confidence:.1%} → {action.upper()}"
            self.base_logger.info(message)
    
    def enhanced_analysis(self, symbol: str, indicators: dict):
        """Log análise detalhada dos indicadores"""
        if self.strategy_type == 'multi_asset_enhanced':
            details = []
            for indicator, value in indicators.items():
                details.append(f"{indicator}: {value}")
            message = f"🔍 {symbol} - {', '.join(details)}"
            self.base_logger.debug(message)
    
    def strategy_info(self, message: str):
        """Info específico da estratégia com emoji correto"""
        prefix = self._get_strategy_prefix()
        adapted_message = self._adapt_message(f"{prefix} {message}")
        self.base_logger.info(adapted_message)
    
    def strategy_info(self, message: str):
        """Log específico da estratégia com prefixo"""
        
        prefix = self._get_strategy_prefix()
        adapted_message = f"{prefix} {self._adapt_message(message)}"
        self.base_logger.info(adapted_message)
    
    # Métodos de passthrough para compatibilidade
    def __getattr__(self, name):
        """Repassar outros métodos para o logger base"""
        return getattr(self.base_logger, name)


def create_strategy_logger(name: str, strategy_type: str) -> StrategyLogger:
    """Factory function para criar logger específico da estratégia"""
    
    base_logger = logging.getLogger(name)
    return StrategyLogger(base_logger, strategy_type)

def get_strategy_specific_messages(strategy_type: str) -> Dict[str, str]:
    """Obter mensagens específicas por estratégia"""
    
    messages = {
        'scalping': {
            'initialization': '🚀 Inicializando estratégia Directional Scalping...',
            'ready': '✅ Estratégia de Scalping Direcional ativa',
            'monitoring': '⚡ Analisando direção do mercado para scalping',
            'position_opened': '🚀 Posição de scalping aberta',
            'position_closed': '🔒 Posição de scalping fechada',
            'target_reached': '🎯 Target de scalping atingido',
            'stop_loss_hit': '🛡️ Stop loss de scalping acionado',
            'analysis_complete': '📊 Análise de direção completa',
            'signal_detected': '🔔 Sinal de entrada detectado',
            'no_signal': '⏸️ Aguardando sinal de entrada válido',
            'cooldown_active': '⏳ Cooldown entre trades ativo',
            'no_opportunities': '🔍 Aguardando oportunidades de scalping...'
        },
        'multi_asset': {
            'initialization': '🌐 Inicializando estratégia Multi-Asset Scalping...',
            'ready': '✅ Estratégia Multi-Asset pronta para trading',
            'monitoring': '👀 Monitorando oportunidades em múltiplos ativos',
            'position_opened': '📈 Nova posição aberta',
            'position_closed': '💰 Posição fechada com',
            'signal_detected': '🔔 Sinal detectado em múltiplos ativos',
            'no_opportunities': '⏳ Aguardando oportunidades de mercado...'
        },
        'multi_asset_enhanced': {
            'initialization': '🧠 Inicializando Enhanced Multi-Asset Strategy...',
            'ready': '✅ Algoritmo inteligente com 5 indicadores ativo',
            'monitoring': '🔍 Analisando mercado com algoritmo avançado',
            'signal_detected': '⚡ Sinal detectado - Score:',
            'position_opened': '🚀 Posição Enhanced aberta',
            'position_closed': '💎 Posição Enhanced fechada com',
            'no_opportunities': '🤔 Aguardando sinais de alta qualidade...',
            'analyzing': '📊 Analisando 5 indicadores técnicos...'
        },
        'grid': {
            'initialization': '📊 Inicializando estratégia Grid Trading...',
            'ready': '✅ Grid Trading configurado e operacional',
            'monitoring': '🔍 Monitorando execuções do grid',
            'grid_executed': '🎯 Ordem do grid executada',
            'grid_rebalanced': '⚖️ Grid rebalanceado',
            'out_of_range': '⚠️ Preço saiu do range do grid',
            'no_opportunities': '⏳ Aguardando condições para criar grid...'
        },
        'pure_grid': {
            'initialization': '📊 Inicializando estratégia Pure Grid...',
            'ready': '✅ Grid fixo configurado e operacional',
            'monitoring': '🔍 Monitorando execuções no grid fixo',
            'grid_executed': '🎯 Ordem do grid executada',
            'grid_rebalanced': '⚖️ Grid rebalanceado',
            'out_of_range': '⚠️ Preço saiu do range configurado',
            'no_opportunities': '⏳ Aguardando margem para grid fixo...'
        },
        'market_making': {
            'initialization': '🎯 Inicializando estratégia Market Making...',
            'ready': '✅ Grid dinâmico ativo e adaptativo',
            'monitoring': '📈 Monitorando mercado para ajustes dinâmicos',
            'grid_shifted': '🔄 Grid reposicionado por movimento de mercado',
            'spread_adjusted': '📏 Spread ajustado por volatilidade',
            'grid_executed': '🎯 Ordem de market making executada',
            'no_opportunities': '⏳ Aguardando condições de mercado...'
        },
        'dynamic_grid': {
            'initialization': '⚡ Inicializando estratégia Dynamic Grid...',
            'ready': '✅ Grid dinâmico com ajustes automáticos ativo',
            'monitoring': '🔄 Monitorando volatilidade para ajustes do grid',
            'grid_adjusted': '⚡ Grid ajustado dinamicamente',
            'threshold_reached': '🎯 Threshold de ajuste atingido',
            'grid_executed': '🎯 Ordem do grid dinâmico executada',
            'volatility_change': '📊 Mudança de volatilidade detectada',
            'no_opportunities': '⏳ Aguardando condições para grid dinâmico...'
        }
    }
    
    return messages.get(strategy_type.lower(), messages['grid'])