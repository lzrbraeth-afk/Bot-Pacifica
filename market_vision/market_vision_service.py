"""
Market Vision Service - Serviço Principal
Orquestra todas as análises e fornece interface unificada
"""

import logging
import json
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

from .core.market_analyzer import MarketAnalyzer
from .signals.entry_generator import EntryGenerator
from .decision_logger.trade_recorder import TradeDecisionRecorder
from .adapters.pacifica_adapter import PacificaAdapter


class MarketVisionService:
    """
    Serviço principal que orquestra Market Vision
    """
    
    def __init__(self, auth_client, position_manager=None,
                 config: Optional[Dict] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Args:
            auth_client: Cliente de autenticação Pacifica
            position_manager: Gerenciador de posições (opcional)
            config: Configurações (opcional)
            logger: Logger customizado (opcional)
        """
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)
        
        # Inicializar componentes
        self.adapter = PacificaAdapter(
            auth_client=auth_client,
            position_manager=position_manager,
            logger=self.logger
        )
        
        self.analyzer = MarketAnalyzer(
            config=self.config.get('analyzer', {}),
            logger=self.logger
        )
        
        self.entry_generator = EntryGenerator(
            config=self.config.get('entry_generator', {}),
            logger=self.logger
        )
        
        self.trade_recorder = TradeDecisionRecorder(
            db_path=self.config.get('db_path', 'data/trade_decisions.db'),
            logger=self.logger
        )
        
        # Cache de última análise
        self._last_analysis = None
        self._last_analysis_time = None
        
        self.logger.info("Market Vision Service inicializado")
    
    def get_market_vision(self, symbol: str = 'BTC',
                         use_cache: bool = True,
                         cache_ttl: int = 30) -> Dict:
        """
        Obtém visão completa do mercado
        
        Args:
            symbol: Símbolo para analisar
            use_cache: Usar cache se disponível
            cache_ttl: TTL do cache em segundos
        
        Returns:
            Dict com análise completa e setup
        """
        
        try:
            # Verificar cache
            if use_cache and self._is_cache_valid(cache_ttl):
                self.logger.debug("Usando análise do cache")
                return self._last_analysis
            
            self.logger.info(f"Gerando nova análise de mercado para {symbol}")
            
            # Coletar dados
            market_data = self.adapter.collect_market_data(
                symbol=symbol,
                timeframe='5m',
                periods=100
            )
            
            if not market_data or 'ohlcv' not in market_data:
                self.logger.error("Dados de mercado insuficientes")
                return self._empty_vision()
            
            # Análise multi-timeframe (opcional)
            multi_tf_data = None
            if self.config.get('use_multi_timeframe', True):
                multi_tf_raw_data = self.adapter.collect_multi_timeframe_data(
                    symbol=symbol,
                    timeframes=['5m', '15m', '1h']
                )
                
                # Analisar cada timeframe
                multi_tf_data = {}
                for tf, tf_data in multi_tf_raw_data.items():
                    try:
                        self.logger.debug(f"Analisando timeframe {tf}...")
                        tf_analysis = self.analyzer.analyze_full(tf_data)
                        multi_tf_data[tf] = tf_analysis
                    except Exception as e:
                        self.logger.warning(f"Erro ao analisar timeframe {tf}: {e}")
                        multi_tf_data[tf] = {'global': {'global_score': 0, 'direction': 'NEUTRO', 'status': ''}}
            
            # Executar análise completa
            analysis_result = self.analyzer.analyze_full(market_data)
            
            # Gerar setup
            setup_result = self.entry_generator.generate_setup(
                analysis_result,
                multi_tf_data
            )
            
            # Gerar resumo
            summary = self.analyzer.get_market_summary(analysis_result)
            
            # Compilar resultado final
            vision = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'analysis': analysis_result,
                'setup': setup_result,
                'summary': summary,
                'multi_timeframe': multi_tf_data
            }
            
            # Atualizar cache
            self._last_analysis = vision
            self._last_analysis_time = datetime.now()
            
            self.logger.info(
                f"Análise concluída - Score: {analysis_result['global']['global_score']:.2f}/10"
            )
            
            return vision
            
        except Exception as e:
            self.logger.error(f"Erro ao gerar market vision: {e}", exc_info=True)
            return self._empty_vision()
    
    def record_user_decision(self, user_decision: Dict) -> str:
        """
        Registra decisão do usuário
        
        Args:
            user_decision: {
                'action': 'execute' | 'skip' | 'modify',
                'direction': 'LONG' | 'SHORT',
                'entry': float,
                'stop_loss': float,
                'take_profit': float,
                'size_usd': float,
                'notes': str
            }
        
        Returns:
            decision_id
        """
        
        try:
            if not self._last_analysis:
                self.logger.warning("Nenhuma análise disponível para registrar")
                return ""
            
            analysis = self._last_analysis.get('analysis', {})
            setup = self._last_analysis.get('setup', {})
            
            decision_id = self.trade_recorder.record_decision(
                analysis=analysis,
                setup=setup,
                user_decision=user_decision
            )
            
            return decision_id
            
        except Exception as e:
            self.logger.error(f"Erro ao registrar decisão: {e}", exc_info=True)
            return ""
    
    def update_trade_outcome(self, decision_id: str, outcome: Dict):
        """
        Atualiza resultado de um trade
        
        Args:
            decision_id: ID da decisão (timestamp)
            outcome: Dados do resultado
        """
        
        try:
            self.trade_recorder.update_outcome(decision_id, outcome)
        except Exception as e:
            self.logger.error(f"Erro ao atualizar outcome: {e}", exc_info=True)
    
    def get_decision_history(self, limit: int = 10) -> list:
        """Retorna histórico de decisões"""
        return self.trade_recorder.get_recent_decisions(limit=limit)
    
    def get_decision_patterns(self) -> Dict:
        """Analisa padrões nas decisões"""
        return self.trade_recorder.get_decision_patterns()
    
    def export_decisions_csv(self, output_path: str, days: int = 30):
        """Exporta decisões para CSV"""
        self.trade_recorder.export_to_csv(output_path, days)
    
    def _is_cache_valid(self, ttl: int) -> bool:
        """Verifica se cache ainda é válido"""
        
        if not self._last_analysis or not self._last_analysis_time:
            return False
        
        age = (datetime.now() - self._last_analysis_time).total_seconds()
        return age < ttl
    
    def _empty_vision(self) -> Dict:
        """Retorna visão vazia"""
        return {
            'timestamp': datetime.now().isoformat(),
            'symbol': 'N/A',
            'analysis': {},
            'setup': {'has_setup': False, 'reason': 'Erro ao coletar dados'},
            'summary': 'Análise indisponível',
            'multi_timeframe': {}
        }
    
    def get_dashboard_data(self, symbol: str = 'BTC', use_cache: bool = True, cache_ttl: int = 30) -> Dict:
        """
        Obtém dados formatados para o dashboard web
        
        Args:
            symbol: Símbolo para analisar
            use_cache: Usar cache se disponível
            cache_ttl: TTL do cache em segundos
        
        Returns:
            Dict pronto para serializar como JSON
        """
        
        try:
            vision = self.get_market_vision(symbol, use_cache=use_cache, cache_ttl=cache_ttl)
            
            analysis = vision.get('analysis', {})
            setup = vision.get('setup', {})
            
            # Função auxiliar para conversão segura de scores
            def safe_score(value, default=0.0):
                if hasattr(value, 'item'):
                    return float(value.item())
                return float(value) if value is not None else default
            
            # Formatar para dashboard
            dashboard_data = {
                'timestamp': str(vision['timestamp']),
                'symbol': str(vision['symbol']),
                
                # Score global
                'global_score': safe_score(analysis.get('global', {}).get('global_score', 0)),
                'global_status': str(analysis.get('global', {}).get('status', '')),
                'global_direction': str(analysis.get('global', {}).get('direction', 'NEUTRO')),
                'global_confidence': safe_score(analysis.get('global', {}).get('confidence', 0)),
                
                # Scores por categoria
                'technical_score': safe_score(analysis.get('technical', {}).get('score', 0)),
                'volume_score': safe_score(analysis.get('volume', {}).get('score', 0)),
                'sentiment_score': safe_score(analysis.get('sentiment', {}).get('score', 0)),
                'structure_score': safe_score(analysis.get('structure', {}).get('score', 0)),
                'risk_score': safe_score(analysis.get('risk', {}).get('score', 0)),
                'volatility_score': safe_score(analysis.get('volatility', {}).get('score', 5.0)),
                
                # Detalhes técnicos
                'technical_details': self._format_technical_details(analysis.get('technical', {})),
                
                # Detalhes de volume
                'volume_details': self._format_volume_details(analysis.get('volume', {})),
                
                # Detalhes de sentimento
                'sentiment_details': self._format_sentiment_details(analysis.get('sentiment', {})),
                
                # Detalhes de volatilidade
                'volatility_details': self._format_volatility_details(analysis.get('volatility', {})),
                
                # Setup
                'has_setup': setup.get('has_setup', False),
                'setup': setup if setup.get('has_setup', False) else None,
                
                # Multi-timeframe
                'mtf_summary': self._format_mtf_summary(vision.get('multi_timeframe', {})),
                
                # Warnings
                'warnings': self._collect_all_warnings(analysis)
            }
            
            return dashboard_data
            
        except Exception as e:
            self.logger.error(f"Erro ao formatar dados do dashboard: {e}", exc_info=True)
            return {}
    
    def _format_technical_details(self, technical: Dict) -> Dict:
        """Formata detalhes técnicos para dashboard"""
        
        indicators = technical.get('indicators', {})
        details = technical.get('details', {})
        
        # Função auxiliar para conversão segura
        def safe_float(value, default=0.0):
            if hasattr(value, 'item'):
                return float(value.item())
            return float(value) if value is not None else default
        
        return {
            'rsi': safe_float(indicators.get('rsi_14', 0)),
            'rsi_status': str(details.get('rsi', {}).get('status', '')),
            'ema9': safe_float(indicators.get('ema_9', 0)),
            'ema21': safe_float(indicators.get('ema_21', 0)),
            'ema_status': str(details.get('ema', {}).get('status', '')),
            'adx': safe_float(indicators.get('adx', 0)),
            'adx_status': str(details.get('adx', {}).get('status', '')),
            'macd': safe_float(indicators.get('macd', 0)),
            'macd_status': str(details.get('macd', {}).get('status', ''))
        }
    
    def _format_volume_details(self, volume: Dict) -> Dict:
        """Formata detalhes de volume para dashboard"""
        
        metrics = volume.get('metrics', {})
        details = volume.get('details', {})
        
        # Função auxiliar para conversão segura
        def safe_float(value, default=0.0):
            if hasattr(value, 'item'):
                return float(value.item())
            return float(value) if value is not None else default
        
        return {
            'current_volume': safe_float(metrics.get('current', 0)),
            'volume_ratio': safe_float(metrics.get('ratio', 0)),
            'volume_status': str(details.get('volume_abs', {}).get('status', '')),
            'delta': safe_float(metrics.get('delta', 0)),
            'delta_status': str(details.get('delta', {}).get('status', '')),
            'poc': safe_float(volume.get('profile', {}).get('poc', 0))
        }
    
    def _format_sentiment_details(self, sentiment: Dict) -> Dict:
        """Formata detalhes de sentimento para dashboard"""
        
        details = sentiment.get('details', {})
        
        # Função auxiliar para conversão segura
        def safe_float(value, default=0.0):
            if hasattr(value, 'item'):
                return float(value.item())
            return float(value) if value is not None else default
        
        return {
            'funding_rate': safe_float(details.get('funding', {}).get('value', 0)),
            'funding_status': str(details.get('funding', {}).get('status', '')),
            'oi_change': safe_float(details.get('open_interest', {}).get('change', 0)),
            'oi_status': str(details.get('open_interest', {}).get('status', '')),
            'bid_ask_ratio': safe_float(details.get('orderbook', {}).get('ratio', 1.0)),
            'orderbook_status': str(details.get('orderbook', {}).get('status', ''))
        }
    
    def _format_mtf_summary(self, mtf_data: Dict) -> Dict:
        """Formata resumo multi-timeframe"""
        
        if not mtf_data:
            return {}
        
        # Função auxiliar para conversão segura
        def safe_score(value, default=0.0):
            if hasattr(value, 'item'):
                return float(value.item())
            return float(value) if value is not None else default
        
        summary = {}
        for tf, data in mtf_data.items():
            global_data = data.get('global', {})
            summary[str(tf)] = {
                'score': safe_score(global_data.get('global_score', 0)),
                'direction': str(global_data.get('direction', 'NEUTRO')),
                'status': str(global_data.get('status', ''))
            }
        
        return summary
    
    def _format_volatility_details(self, volatility: Dict) -> Dict:
        """Formata detalhes de volatilidade para dashboard"""
        
        bbw = volatility.get('bbw', {})
        atr = volatility.get('atr', {})
        state = volatility.get('state', {})
        bb = volatility.get('bollinger_bands', {})
        details = volatility.get('details', {})
        
        # Função auxiliar para garantir conversão de tipos numpy
        def safe_convert(value, default=0):
            if hasattr(value, 'item'):  # numpy scalar
                return value.item()
            elif hasattr(value, 'tolist'):  # numpy array
                return value.tolist() if len(value.shape) > 0 else float(value)
            return value if value is not None else default
        
        return {
            'score': float(safe_convert(volatility.get('score', 5.0))),
            'bbw_current': float(safe_convert(bbw.get('current', 0))),
            'bbw_percentile': float(safe_convert(bbw.get('percentile', 50))),
            'bbw_status': str(bbw.get('status', '⚪ Neutro')),
            'bbw_description': str(bbw.get('description', '')),
            'atr_value': float(safe_convert(atr.get('value', 0))),
            'atr_trend': int(safe_convert(atr.get('trend', 0))),
            'atr_symbol': str(atr.get('symbol', '→')),
            'state_emoji': str(state.get('emoji', '⚪')),
            'state_color': str(state.get('color', 'gray')),
            'state_signal': str(state.get('signal', 'neutral')),
            'recommendation': str(state.get('recommendation', '')),
            'compression_detected': bool(safe_convert(details.get('compression_detected', False))),
            'expansion_detected': bool(safe_convert(details.get('expansion_detected', False))),
            'high_volatility': bool(safe_convert(details.get('high_volatility', False))),
            'bb_upper': float(safe_convert(bb.get('upper', 0))),
            'bb_middle': float(safe_convert(bb.get('middle', 0))),
            'bb_lower': float(safe_convert(bb.get('lower', 0))),
            'bb_position': str(bb.get('position', 'middle'))
        }
    
    def _collect_all_warnings(self, analysis: Dict) -> list:
        """Coleta todos os warnings de todas as categorias"""
        
        all_warnings = []
        
        for category in ['sentiment', 'risk']:
            warnings = analysis.get(category, {}).get('warnings', [])
            all_warnings.extend(warnings)
        
        # Adicionar warnings do setup se houver
        if self._last_analysis and 'setup' in self._last_analysis:
            setup_warnings = self._last_analysis['setup'].get('warnings', [])
            all_warnings.extend(setup_warnings)
        
        return all_warnings


# Uso standalone (teste)
if __name__ == '__main__':
    print("="*60)
    print("Market Vision Service")
    print("="*60)
    print("\nEste serviço deve ser inicializado com:")
    print("- auth_client: Instância de PacificaAuth")
    print("- position_manager: (opcional)")
    print("\nPara integrar com o bot, importe este módulo e inicialize.")
    print("="*60)
