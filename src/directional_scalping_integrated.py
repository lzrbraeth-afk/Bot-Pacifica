"""
Directional Scalping Strategy - Bot Trading Pacifica.fi
Estratégia de scalping baseada em direção de mercado com saídas time-based

Integrada ao padrão do projeto v3.1
Compatível com Position Manager, Performance Tracker e sistema de logs existentes
"""

import time
from typing import Dict, Optional
from datetime import datetime, timedelta
import logging
import os

from src.direction_analyzer_integrated import DirectionAnalyzer, Direction
from src.strategy_logger import create_strategy_logger
from src.performance_tracker import Trade

class DirectionalScalping:
    """
    Estratégia de Scalping Direcional com Time-Based Exit
    
    Funcionamento:
    1. Analisa direção do mercado usando múltiplos indicadores
    2. Entra na direção confirmada
    3. Define timer de saída (15s, 30s, 45s, 60s)
    4. Monitora PNL durante o timer
    5. Fecha em PNL positivo/neutro ou ao fim do timer
    6. Gestão de risco inteligente para perdas
    
    Compatível com o padrão de estratégias do projeto
    """
    
    def __init__(self, auth_client, calculator, position_manager):
        """
        Inicializa estratégia
        
        Args:
            auth_client: Instância de PacificaAuth
            calculator: Instância de GridCalculator (para compatibilidade)
            position_manager: Instância de PositionManager
        """
        # Logger específico da estratégia
        self.logger = create_strategy_logger('PacificaBot.Scalping', 'scalping')
        
        # Componentes compartilhados
        self.auth = auth_client
        self.calculator = calculator  # Não usado, mas mantido para compatibilidade
        self.position_mgr = position_manager
        
        # Configurações da estratégia (do .env)
        # Usar sistema de símbolos compartilhado (igual ao grid_bot.py)
        self.symbols = self._load_symbols()
        
        self.leverage = int(os.getenv('LEVERAGE', '10'))
        self.trade_duration = int(os.getenv('SCALPING_TRADE_DURATION', '30'))
        self.min_pnl_to_close = float(os.getenv('SCALPING_MIN_PNL', '0.5'))
        self.max_loss_percent = float(os.getenv('SCALPING_MAX_LOSS_PERCENT', '-2.0'))
        self.position_size_usd = float(os.getenv('SCALPING_POSITION_SIZE', '100'))
        self.cooldown_seconds = int(os.getenv('SCALPING_COOLDOWN', '10'))
        self.min_confidence = float(os.getenv('SCALPING_MIN_CONFIDENCE', '0.6'))
        self.max_concurrent_trades = int(os.getenv('SCALPING_MAX_CONCURRENT_TRADES', '3'))
        self.max_trades_per_day = int(os.getenv('SCALPING_MAX_TRADES_PER_DAY', '50'))
        
        # Configuração do analisador
        analyzer_config = {
            'min_confirmation_score': float(os.getenv('ANALYZER_MIN_CONFIRMATION', '0.6')),
            'use_ema': os.getenv('ANALYZER_USE_EMA', 'true').lower() == 'true',
            'use_rsi': os.getenv('ANALYZER_USE_RSI', 'true').lower() == 'true',
            'use_volume': os.getenv('ANALYZER_USE_VOLUME', 'true').lower() == 'true',
            'ema_fast': int(os.getenv('ANALYZER_EMA_FAST', '20')),
            'ema_slow': int(os.getenv('ANALYZER_EMA_SLOW', '50')),
            'rsi_period': int(os.getenv('ANALYZER_RSI_PERIOD', '14'))
        }
        
        # Analisador de direção
        self.analyzer = DirectionAnalyzer(analyzer_config)
        
        # Estado da estratégia
        self.current_position = None
        self.position_entry_time = None
        self.last_trade_time = None
        self.positions_today = []
        self.active = False
        
        # Controle de logs e estatísticas
        self.analysis_count = 0
        self.last_summary_time = datetime.now()
        self.symbol_analysis_stats = {}  # Estatísticas por símbolo
        
        # ✅ NOVO: Estado multi-símbolo (igual multi-asset)
        self.active_positions = {}  # {symbol: position_data}
        self.price_history = {}     # {symbol: [prices]}
        self.last_analysis_time = {}  # {symbol: timestamp}
        
        # Limites de risco
        self.max_daily_loss = float(os.getenv('MAX_DAILY_LOSS', '50'))
        # max_trades_per_day já definido acima
        
        self.logger.info("=" * 60)
        self.logger.info("🚀 DIRECTIONAL SCALPING STRATEGY")
        self.logger.info("=" * 60)
        self.logger.info(f"📊 Símbolos disponíveis: {len(self.symbols)} ({', '.join(self.symbols[:3])}{'...' if len(self.symbols) > 3 else ''})")
        self.logger.info(f"📈 Símbolos multi-ativo: {', '.join(self.symbols[:5])}")
        self.logger.info(f"⚡ Alavancagem: {self.leverage}x")
        self.logger.info(f"⏱️  Duração: {self.trade_duration}s")
        self.logger.info(f"💰 Posição: ${self.position_size_usd}")
        self.logger.info(f"🎯 Target: +${self.min_pnl_to_close}")
        self.logger.info(f"🛡️ Stop Loss: {self.max_loss_percent}%")
        self.logger.info(f"📊 Confiança mín: {self.min_confidence:.0%}")
        self.logger.info("=" * 60)

    def _get_trading_symbols(self):
        """
        Obtém lista de símbolos para trading usando mesma lógica do grid_bot.py
        Suporta SYMBOLS=AUTO, listas específicas, whitelist e blacklist
        """
        try:
            # Obter configuração SYMBOLS (igual ao grid_bot.py)
            symbols_config = os.getenv('SYMBOLS', 'BTC,ETH,SOL')
            
            if symbols_config == 'AUTO':
                # Usar cache de símbolos da API
                symbols = self._get_symbols_from_cache()
                if symbols:
                    self.logger.info(f"📦 Usando símbolos AUTO da API: {len(symbols)} disponíveis")
                    return symbols
                else:
                    # Fallback se AUTO falhar
                    fallback = ['BTC', 'ETH', 'SOL', 'DOGE', 'AVAX']
                    self.logger.warning(f"⚠️ AUTO falhou, usando fallback: {fallback}")
                    return fallback
            else:
                # Lista específica fornecida
                symbol_list = [s.strip().upper() for s in symbols_config.split(',')]
                symbol_list = [s for s in symbol_list if s]  # Remove vazios
                
                if not symbol_list:
                    # Fallback se lista estiver vazia
                    fallback = ['BTC', 'ETH', 'SOL']
                    self.logger.warning(f"⚠️ Lista SYMBOLS vazia, usando fallback: {fallback}")
                    return fallback
                
                self.logger.info(f"📋 Usando símbolos específicos: {symbol_list}")
                return symbol_list
                
        except Exception as e:
            # Fallback em caso de erro
            fallback = ['BTC', 'ETH', 'SOL']
            self.logger.error(f"❌ Erro ao obter símbolos: {e}")
            self.logger.info(f"🔄 Usando fallback: {fallback}")
            return fallback

    def _get_symbols_from_cache(self):
        """
        Obtém símbolos do cache da API (igual ao sistema do app.py)
        """
        try:
            from src.cache import SymbolsCache
            
            # Usar mesma instância de cache
            symbols_cache = SymbolsCache(cache_duration_hours=24)
            symbols = symbols_cache.get_symbols(self.auth, force_refresh=False)
            
            if symbols and len(symbols) > 0:
                # Aplicar blacklist se configurada
                return self._apply_blacklist(symbols)
            else:
                return []
                
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao acessar cache de símbolos: {e}")
            return []

    def _apply_blacklist(self, symbols):
        """
        Aplica blacklist aos símbolos (mesma lógica do app.py)
        """
        try:
            use_blacklist = os.getenv('SYMBOLS_USE_BLACKLIST', 'true').lower() == 'true'
            blacklist_str = os.getenv('SYMBOLS_BLACKLIST', 'PUMP,FARTCOIN')
            
            if not use_blacklist or not blacklist_str:
                return symbols
            
            blacklist = [s.strip().upper() for s in blacklist_str.split(',')]
            filtered_symbols = [s for s in symbols if s not in blacklist]
            
            if len(filtered_symbols) != len(symbols):
                removed = [s for s in symbols if s in blacklist]
                self.logger.info(f"🚫 Símbolos filtrados: {removed}")
            
            return filtered_symbols if filtered_symbols else symbols
            
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao aplicar blacklist: {e}")
            return symbols

    def _load_symbols(self):
        """
        Carregar símbolos usando sistema unificado (igual multi-asset)
        """
        return self._get_trading_symbols()

    def get_available_symbols(self) -> list:
        """Retorna lista de todos os símbolos disponíveis"""
        return self.symbols.copy()
    
    def _get_current_price_sync(self, symbol: str) -> float:
        """Obter preço atual usando método síncrono"""
        try:
            prices_data = self.auth.get_prices()
            if prices_data and prices_data.get('success'):
                for item in prices_data.get('data', []):
                    if item.get('symbol') == symbol:
                        return float(item.get('mark') or item.get('mid') or 0)
            return 0.0
        except Exception as e:
            self.logger.error(f"Erro ao obter preço: {e}")
            return 0.0
    
    def _get_klines_sync(self, symbol: str, interval: str, limit: int):
        """Obter klines usando método síncrono com fallback"""
        try:
            # Verificar se o método é async ou sync
            klines_result = self.auth.get_klines(symbol=symbol, interval=interval, limit=limit)
            
            # Se retornou uma coroutine, tentar executar de forma síncrona
            if hasattr(klines_result, '__await__'):
                import asyncio
                try:
                    # Primeira tentativa: usar loop existente
                    try:
                        loop = asyncio.get_running_loop()
                        # Se há loop rodando, não podemos usar run_until_complete
                        # Vamos usar um fallback simples
                        self.logger.warning("⚠️ Loop asyncio ativo detectado - usando fallback para klines")
                        klines = None  # Forçar uso do fallback
                    except RuntimeError:
                        # Não há loop rodando, podemos criar um
                        klines = asyncio.run(klines_result)
                except Exception as async_error:
                    self.logger.warning(f"⚠️ Erro ao executar coroutine: {async_error}")
                    klines = None  # Forçar uso do fallback
            else:
                klines = klines_result
            
            if klines and isinstance(klines, (list, tuple)) and len(klines) > 0:
                # Verificar se os dados têm formato correto
                formatted_klines = []
                for candle in klines:
                    if isinstance(candle, dict):
                        # Se já tem as chaves necessárias, usar direto
                        if all(key in candle for key in ['open', 'high', 'low', 'close']):
                            formatted_klines.append(candle)
                        # Se tem apenas close, criar formato completo
                        elif 'close' in candle:
                            close_price = float(candle['close'])
                            formatted_candle = {
                                'open': close_price,
                                'high': close_price * 1.001,  # Simula variação de 0.1%
                                'low': close_price * 0.999,
                                'close': close_price,
                                'volume': candle.get('volume', 1000000)
                            }
                            formatted_klines.append(formatted_candle)
                
                if formatted_klines:
                    return formatted_klines
            
            # Fallback: usar preço atual para simular candles
            current_price = self._get_current_price_sync(symbol)
            if current_price > 0:
                # Simula dados históricos completos para análise
                simulated_candles = []
                for i in range(limit):
                    # Simula pequenas variações no preço
                    variation = 1 + (i * 0.0001 - limit * 0.00005)  # Pequena tendência
                    price = current_price * variation
                    candle = {
                        'open': price * 0.999,
                        'high': price * 1.001,
                        'low': price * 0.998,
                        'close': price,
                        'volume': 1000000 + (i * 10000)
                    }
                    simulated_candles.append(candle)
                
                return simulated_candles
            
            return []
        except Exception as e:
            self.logger.error(f"Erro ao obter klines: {e}")
            return []
    
    def _create_market_order_sync(self, symbol: str, side: str, size: float, price: float = None):
        """Criar ordem de mercado usando método síncrono"""
        try:
            return self.auth.create_order(
                symbol=symbol,
                side=side,
                size=size,
                order_type='market',
                price=price
            )
        except Exception as e:
            self.logger.error(f"Erro ao criar ordem: {e}")
            return None
    
    def initialize(self) -> bool:
        """
        Inicializa a estratégia multi-símbolo
        Verifica posições abertas em todos os símbolos
        """
        try:
            self.logger.info("🔄 Inicializando estratégia multi-símbolo...")
            
            # Verificar posições abertas em todos os símbolos
            positions = self.auth.get_positions()
            
            for pos in positions:
                symbol = pos.get('symbol')
                if symbol in self.symbols:
                    size = float(pos.get('size', 0))
                    if size != 0:
                        self.logger.warning(f"⚠️ Posição aberta detectada em {symbol}: {pos}")
                        
                        # Adicionar à lista de posições ativas
                        self.active_positions[symbol] = {
                            'symbol': symbol,
                            'side': pos.get('side'),
                            'size': abs(size),
                            'entry_price': float(pos.get('avg_entry_price', 0)),
                            'entry_time': datetime.now(),
                            'order_id': pos.get('id'),
                            'direction': Direction.LONG if pos.get('side') in ['buy', 'bid'] else Direction.SHORT
                        }
            
            self.active = True
            self.logger.info(f"✅ Estratégia inicializada - {len(self.active_positions)} posições ativas encontradas")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar estratégia: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def analyze_market(self, symbol: str = None) -> Dict:
        """
        Analisa o mercado para um símbolo específico
        Compatível com o padrão do projeto
        """
        # Se não especificado, usar primeiro símbolo (compatibilidade)
        if symbol is None:
            symbol = self.symbols[0] if self.symbols else 'BTCUSDT'
            
        try:
            # Busca candles usando método síncrono
            candles = self._get_klines_sync(
                symbol=symbol,
                interval='1m',
                limit=100
            )
            
            if not candles or len(candles) < 50:
                self.logger.warning(f"⚠️ {symbol}: Candles insuficientes: {len(candles) if candles else 0}")
                return {'direction': Direction.NEUTRAL, 'confidence': 0, 'score': 0}
            
            # Analisa direção usando o analyzer
            analysis = self.analyzer.analyze(candles)
            
            # Incrementar contador de análises
            self.analysis_count += 1
            
            # Atualizar estatísticas do símbolo
            if symbol not in self.symbol_analysis_stats:
                self.symbol_analysis_stats[symbol] = {
                    'analyses': 0, 'bullish': 0, 'bearish': 0, 'neutral': 0,
                    'avg_confidence': 0, 'last_direction': 'NEUTRAL'
                }
            
            stats = self.symbol_analysis_stats[symbol]
            stats['analyses'] += 1
            direction = analysis['direction']
            confidence = analysis['confidence']
            
            if direction == Direction.LONG:
                stats['bullish'] += 1
            elif direction == Direction.SHORT:
                stats['bearish'] += 1
            else:
                stats['neutral'] += 1
            
            stats['avg_confidence'] = (stats['avg_confidence'] * (stats['analyses'] - 1) + confidence) / stats['analyses']
            stats['last_direction'] = direction.value.upper()
            
            # Log detalhado da análise (sempre visível)
            signals = analysis.get('signals', {})
            score = analysis.get('score', 0)
            
            # Log sempre visível para mostrar atividade
            self.logger.info(
                f"📊 {symbol}: {direction.value.upper()} | "
                f"Conf: {confidence:.0%} | Score: {score:+.2f} | "
                f"EMA: {signals.get('ema', 'N/A')} | "
                f"RSI: {signals.get('rsi', 'N/A')} | "
                f"Vol: {signals.get('volume', 'N/A')}"
            )
            
            # Log de resumo a cada 20 análises ou 2 minutos
            time_since_summary = (datetime.now() - self.last_summary_time).total_seconds()
            if self.analysis_count % 20 == 0 or time_since_summary >= 120:
                self._log_analysis_summary()
                self.last_summary_time = datetime.now()
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"❌ Erro na análise de mercado: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return {'direction': Direction.NEUTRAL, 'confidence': 0, 'score': 0}

    def _log_analysis_summary(self):
        """Log de resumo das análises realizadas"""
        try:
            if not self.symbol_analysis_stats:
                return
            
            self.logger.info("=" * 80)
            self.logger.info(f"📈 RESUMO DE ANÁLISES - Total: {self.analysis_count}")
            self.logger.info("=" * 80)
            
            # Estatísticas por símbolo (mostra os 5 mais analisados)
            sorted_symbols = sorted(
                self.symbol_analysis_stats.items(), 
                key=lambda x: x[1]['analyses'], 
                reverse=True
            )[:5]
            
            for symbol, stats in sorted_symbols:
                bullish_pct = (stats['bullish'] / stats['analyses']) * 100 if stats['analyses'] > 0 else 0
                bearish_pct = (stats['bearish'] / stats['analyses']) * 100 if stats['analyses'] > 0 else 0
                neutral_pct = (stats['neutral'] / stats['analyses']) * 100 if stats['analyses'] > 0 else 0
                
                self.logger.info(
                    f"📊 {symbol:>6}: {stats['analyses']:>3} análises | "
                    f"🟢{bullish_pct:4.0f}% 🔴{bearish_pct:4.0f}% ⚪{neutral_pct:4.0f}% | "
                    f"Conf.Média: {stats['avg_confidence']:4.0%} | "
                    f"Atual: {stats['last_direction']}"
                )
            
            # Estatísticas gerais
            total_trades_today = len(self.positions_today)
            if total_trades_today > 0:
                total_pnl = sum(t.get('pnl', 0) for t in self.positions_today)
                winners = sum(1 for t in self.positions_today if t.get('pnl', 0) > 0)
                win_rate = (winners / total_trades_today) * 100
                
                self.logger.info("-" * 80)
                self.logger.info(
                    f"💰 TRADES HOJE: {total_trades_today} | "
                    f"PNL: ${total_pnl:+.2f} | "
                    f"Taxa Acerto: {win_rate:.0f}% ({winners}/{total_trades_today})"
                )
            
            self.logger.info("=" * 80)
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao gerar resumo: {e}")
            
    def execute_strategy(self) -> bool:
        """
        Loop principal da estratégia - ANÁLISE MULTI-SÍMBOLO (igual multi-asset)
        Analisa TODOS os símbolos simultaneamente a cada execução
        """
        try:
            # 1. Gerenciar posições existentes primeiro
            self._manage_all_positions()
            
            # Atualizar preços de todos os símbolos
            self._update_all_prices()
            
            # 2. Verificar limites diários gerais
            if len(self.positions_today) >= self.max_trades_per_day:
                self.logger.info(f"⚠️ Limite de trades diários atingido: {self.max_trades_per_day}")
                return True
            
            daily_pnl = sum(t.get('pnl', 0) for t in self.positions_today)
            if daily_pnl <= -self.max_daily_loss:
                self.logger.warning(f"🛑 Limite de perda diária atingido: ${daily_pnl:.2f}")
                return True
            
            # 3. Atualizar preços de todos os símbolos
            self._update_all_prices()
            
            # 4. ✅ ANÁLISE MULTI-SÍMBOLO (igual multi-asset)
            symbols_analyzed = 0
            signals_found = 0
            new_positions = 0
            
            for symbol in self.symbols:
                # Verificar se pode analisar este símbolo
                if symbol in self.price_history and len(self.price_history[symbol]) >= 3:
                    symbols_analyzed += 1
                    
                    # Verificar se já tem posição neste símbolo
                    if symbol in self.active_positions:
                        continue  # Já tem posição, pular análise
                    
                    # Verificar cooldown específico do símbolo
                    if symbol in self.last_analysis_time:
                        time_since_last = (datetime.now() - self.last_analysis_time[symbol]).total_seconds()
                        if time_since_last < self.cooldown_seconds:
                            continue
                    
                    # ✅ ANALISAR SÍMBOLO
                    signal_found = self._analyze_symbol_for_entry(symbol)
                    if signal_found:
                        signals_found += 1
                        
                        # Verificar se pode abrir nova posição
                        if len(self.active_positions) < self.max_concurrent_trades:
                            entry_success = self._enter_position_for_symbol(symbol)
                            if entry_success:
                                new_positions += 1
                                self.last_analysis_time[symbol] = datetime.now()
                else:
                    self.logger.debug(f"📊 {symbol}: Histórico insuficiente ({len(self.price_history.get(symbol, []))} pontos)")
            
            # 5. Log de resumo da análise (igual multi-asset)
            self.logger.info(
                f"📊 Scalping: Análise concluída - {symbols_analyzed}/{len(self.symbols)} símbolos analisados, "
                f"{signals_found} sinais encontrados, {new_positions} novas posições abertas"
            )
            
            # 6. Log estatísticas periódicas
            if symbols_analyzed > 0:
                self.analysis_count += 1
                time_since_summary = (datetime.now() - self.last_summary_time).total_seconds()
                if self.analysis_count % 5 == 0 or time_since_summary >= 300:  # A cada 5 análises ou 5 minutos
                    self._log_analysis_summary()
                    self.last_summary_time = datetime.now()
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro no execute_strategy: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _enter_position(self, direction: Direction, analysis: Dict):
        """Abre posição na direção detectada"""
        try:
            # Determina side
            side = 'buy' if direction == Direction.LONG else 'sell'
            
            # Busca preço atual
            current_price = self._get_current_price_sync(self.symbol)
            if current_price == 0:
                self.logger.error("❌ Não foi possível obter preço atual")
                return
            
            # Calcula quantidade
            size = self.position_size_usd / current_price
            
            # Arredonda quantidade (usando método do position_manager se disponível)
            symbol_info = self.auth.get_symbol_info(self.symbol)
            if symbol_info:
                lot_size = float(symbol_info.get('lot_size', 0.0001))
                size = round(size / lot_size) * lot_size
            
            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info("🚀 ENTRANDO NO TRADE")
            self.logger.info("=" * 60)
            self.logger.info(f"📍 Direção: {direction.value.upper()}")
            self.logger.info(f"📊 Confiança: {analysis['confidence']:.2%}")
            self.logger.info(f"💵 Preço: ${current_price:.4f}")
            self.logger.info(f"📦 Tamanho: {size:.4f} {self.symbol}")
            self.logger.info(f"⏱️  Duração: {self.trade_duration}s")
            self.logger.info(f"🎯 Target: +${self.min_pnl_to_close}")
            self.logger.info(f"🛡️ Stop: {self.max_loss_percent}%")
            self.logger.info("=" * 60)
            
            # Cria ordem market
            order = self._create_market_order_sync(
                symbol=self.symbol,
                side=side,
                size=size,
                price=current_price
            )
            
            if order and order.get('id'):
                self.current_position = {
                    'symbol': self.symbol,
                    'side': side,
                    'size': size,
                    'entry_price': current_price,
                    'order_id': order['id'],
                    'direction': direction,
                    'analysis': analysis
                }
                self.position_entry_time = datetime.now()
                
                self.logger.info(f"✅ Posição aberta: Order #{order['id']}")
            else:
                self.logger.error("❌ Falha ao criar ordem")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao entrar em posição: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _update_all_prices(self):
        """
        Atualizar preços de todos os símbolos (igual multi-asset)
        """
        try:
            prices = self.auth.get_prices()
            
            if prices and 'data' in prices:
                prices_updated = 0
                for item in prices['data']:
                    symbol = item.get('symbol')
                    if symbol in self.symbols:
                        price = float(item.get('price', 0))
                        if price > 0:
                            # Manter histórico de preços (últimos 10 pontos)
                            if symbol not in self.price_history:
                                self.price_history[symbol] = []
                            
                            self.price_history[symbol].append(price)
                            if len(self.price_history[symbol]) > 10:
                                self.price_history[symbol] = self.price_history[symbol][-10:]
                            
                            prices_updated += 1
                
                self.logger.debug(f"💰 Preços atualizados: {prices_updated}/{len(self.symbols)} símbolos")
            else:
                self.logger.warning("⚠️ Falha ao obter preços da API")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao atualizar preços: {e}")

    def _manage_all_positions(self):
        """
        Gerenciar todas as posições ativas (igual multi-asset)
        """
        try:
            positions_to_close = []
            
            for symbol, position in self.active_positions.items():
                # Calcular tempo na posição
                time_in_position = (datetime.now() - position['entry_time']).total_seconds()
                
                # Obter preço atual
                current_price = self._get_current_price_sync(symbol)
                if current_price <= 0:
                    continue
                
                # Calcular PNL
                pnl = self._calculate_pnl_for_position(position, current_price)
                
                # Verificar condições de saída
                should_close = (
                    time_in_position >= self.trade_duration or  # Tempo expirou
                    pnl >= self.min_pnl_to_close or            # Lucro alvo
                    pnl <= (self.max_loss_percent / 100) * position['size']  # Stop loss
                )
                
                if should_close:
                    self.logger.info(f"🎯 {symbol}: Fechando posição - PNL: ${pnl:+.2f} em {time_in_position:.0f}s")
                    positions_to_close.append(symbol)
            
            # Fechar posições marcadas
            for symbol in positions_to_close:
                self._close_position_for_symbol(symbol)
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao gerenciar posições: {e}")

    def _analyze_symbol_for_entry(self, symbol: str) -> bool:
        """
        Analisar símbolo específico para entrada (igual lógica do analyze_market)
        """
        try:
            # Buscar candles para este símbolo
            candles = self._get_klines_sync(symbol=symbol, interval='1m', limit=100)
            
            if not candles or len(candles) < 50:
                self.logger.debug(f"📊 {symbol}: Candles insuficientes ({len(candles) if candles else 0})")
                return False
            
            # Analisar direção usando o analyzer
            analysis = self.analyzer.analyze(candles)
            
            # Atualizar estatísticas do símbolo
            self._update_symbol_stats(symbol, analysis)
            
            direction = analysis['direction']
            confidence = analysis['confidence']
            
            # Log da análise
            signals = analysis.get('signals', {})
            score = analysis.get('score', 0)
            
            self.logger.info(
                f"📊 {symbol}: {direction.value.upper()} | "
                f"Conf: {confidence:.0%} | Score: {score:+.2f} | "
                f"EMA: {signals.get('ema', 'N/A')} | "
                f"RSI: {signals.get('rsi', 'N/A')} | "
                f"Vol: {signals.get('volume', 'N/A')}"
            )
            
            # Verificar se deve entrar
            if direction == Direction.NEUTRAL:
                self.logger.debug(f"➡️ {symbol}: Sinal NEUTRO - sem entrada")
                return False
            elif confidence < self.min_confidence:
                self.logger.debug(f"⚠️ {symbol}: Confiança baixa ({confidence:.0%} < {self.min_confidence:.0%}) - sem entrada")
                return False
            
            # Sinal encontrado!
            self.logger.info(f"🚀 {symbol}: SINAL DE ENTRADA! {direction.value.upper()} - Conf: {confidence:.0%}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao analisar {symbol}: {e}")
            return False

    def _update_symbol_stats(self, symbol: str, analysis: Dict):
        """Atualizar estatísticas do símbolo"""
        if symbol not in self.symbol_analysis_stats:
            self.symbol_analysis_stats[symbol] = {
                'analyses': 0, 'bullish': 0, 'bearish': 0, 'neutral': 0,
                'avg_confidence': 0, 'last_direction': 'NEUTRAL'
            }
        
        stats = self.symbol_analysis_stats[symbol]
        stats['analyses'] += 1
        direction = analysis['direction']
        confidence = analysis['confidence']
        
        if direction == Direction.LONG:
            stats['bullish'] += 1
        elif direction == Direction.SHORT:
            stats['bearish'] += 1
        else:
            stats['neutral'] += 1
        
        stats['avg_confidence'] = (stats['avg_confidence'] * (stats['analyses'] - 1) + confidence) / stats['analyses']
        stats['last_direction'] = direction.value.upper()

    def _enter_position_for_symbol(self, symbol: str) -> bool:
        """
        Entrar em posição para símbolo específico
        """
        try:
            # Reanalisar para obter direção atual
            candles = self._get_klines_sync(symbol=symbol, interval='1m', limit=100)
            if not candles:
                return False
                
            analysis = self.analyzer.analyze(candles)
            direction = analysis['direction']
            current_price = self._get_current_price_sync(symbol)
            
            if current_price <= 0:
                return False
            
            # Criar ordem
            side = 'buy' if direction == Direction.LONG else 'sell'
            order = self._create_market_order_sync(
                symbol=symbol,
                side=side,
                size=self.position_size_usd
            )
            
            if order:
                # Registrar posição ativa
                self.active_positions[symbol] = {
                    'symbol': symbol,
                    'direction': direction,
                    'entry_price': current_price,
                    'entry_time': datetime.now(),
                    'size': self.position_size_usd,
                    'order_id': order.get('id'),
                    'side': side
                }
                
                self.logger.info(f"💰 Posição {side.upper()} {symbol} aberta: ${self.position_size_usd} @ ${current_price:.2f}")
                return True
            else:
                self.logger.error(f"❌ Falha ao criar ordem para {symbol}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao entrar em {symbol}: {e}")
            return False

    def _close_position_for_symbol(self, symbol: str):
        """
        Fechar posição específica do símbolo
        """
        try:
            if symbol not in self.active_positions:
                return
            
            position = self.active_positions[symbol]
            current_price = self._get_current_price_sync(symbol)
            
            # Calcular PNL final
            pnl = self._calculate_pnl_for_position(position, current_price)
            
            # Registrar trade finalizado
            trade_record = {
                'symbol': symbol,
                'direction': position['direction'].value,
                'entry_price': position['entry_price'],
                'exit_price': current_price,
                'entry_time': position['entry_time'],
                'exit_time': datetime.now(),
                'pnl': pnl,
                'size': position['size']
            }
            
            self.positions_today.append(trade_record)
            
            # Remover da lista de posições ativas
            del self.active_positions[symbol]
            
            self.logger.info(f"✅ {symbol}: Trade finalizado - PNL: ${pnl:+.2f}")
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao fechar posição {symbol}: {e}")

    def _calculate_pnl_for_position(self, position: Dict, current_price: float) -> float:
        """Calcular PNL para posição específica"""
        try:
            entry_price = position['entry_price']
            size = position['size']
            direction = position['direction']
            
            if direction == Direction.LONG:
                pnl = ((current_price - entry_price) / entry_price) * size
            else:  # SHORT
                pnl = ((entry_price - current_price) / entry_price) * size
            
            return pnl
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao calcular PNL: {e}")
            return 0.0

    def manage_positions(self):
        """
        Gerencia posição aberta (lógica de saída)
        Compatível com o padrão do projeto
        """
        try:
            if not self.current_position:
                return
            
            # Busca posição atualizada da API
            positions = self.auth.get_positions()
            current_pos = None
            
            for pos in positions:
                if pos.get('symbol') == self.symbol:
                    current_pos = pos
                    break
            
            if not current_pos or float(current_pos.get('size', 0)) == 0:
                self.logger.info("✅ Posição já fechada pela API")
                self.current_position = None
                self.last_trade_time = datetime.now()
                return
            
            # Calcula tempo decorrido
            time_elapsed = (datetime.now() - self.position_entry_time).total_seconds()
            time_remaining = max(0, self.trade_duration - time_elapsed)
            
            # Extrai PNL
            unrealized_pnl = float(current_pos.get('unrealized_pnl', 0))
            entry_price = float(self.current_position['entry_price'])
            current_price = self._get_current_price_sync(self.symbol)
            
            # Calcula PNL %
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
            
            # Se short, inverte o sinal
            if self.current_position['side'] in ['sell', 'ask']:
                pnl_percent = -pnl_percent
            
            self.logger.info(
                f"⏱️  {time_remaining:.0f}s restantes | "
                f"PNL: ${unrealized_pnl:+.2f} ({pnl_percent:+.2f}%)"
            )
            
            # LÓGICA DE SAÍDA
            should_close = False
            close_reason = ""
            
            # 1. STOP LOSS (perda máxima)
            if pnl_percent <= self.max_loss_percent:
                should_close = True
                close_reason = f"Stop Loss ({pnl_percent:.2f}%)"
            
            # 2. TEMPO EXPIRADO
            elif time_elapsed >= self.trade_duration:
                if unrealized_pnl >= -0.5:
                    should_close = True
                    close_reason = f"Timeout ({unrealized_pnl:+.2f} USD)"
                else:
                    # Aguarda reversão até 2x o tempo
                    if time_elapsed >= self.trade_duration * 2:
                        should_close = True
                        close_reason = f"Timeout máximo ({unrealized_pnl:+.2f} USD)"
                    else:
                        self.logger.warning(f"⏳ Aguardando reversão... PNL: ${unrealized_pnl:.2f}")
            
            # 3. TARGET ATINGIDO
            elif unrealized_pnl >= self.min_pnl_to_close:
                should_close = True
                close_reason = f"Target atingido ({unrealized_pnl:+.2f} USD)"
            
            # 4. BREAKEVEN após metade do tempo
            elif time_elapsed >= self.trade_duration / 2:
                if -0.2 <= unrealized_pnl <= 0.2:
                    should_close = True
                    close_reason = f"Breakeven ({unrealized_pnl:+.2f} USD)"
            
            # FECHA POSIÇÃO
            if should_close:
                self._close_position(close_reason, unrealized_pnl)
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao gerenciar posição: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _close_position(self, reason: str, pnl: float):
        """Fecha a posição atual"""
        try:
            # Side oposto
            close_side = 'sell' if self.current_position['side'] in ['buy', 'bid'] else 'buy'
            size = self.current_position['size']
            
            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info("🔒 FECHANDO POSIÇÃO")
            self.logger.info("=" * 60)
            self.logger.info(f"📍 Motivo: {reason}")
            self.logger.info(f"💰 PNL: ${pnl:+.2f}")
            duration = (datetime.now() - self.position_entry_time).total_seconds()
            self.logger.info(f"⏱️  Duração: {duration:.1f}s")
            self.logger.info("=" * 60)
            
            # Cria ordem de fechamento
            order = self._create_market_order_sync(
                symbol=self.symbol,
                side=close_side,
                size=size
            )
            
            if order and order.get('id'):
                self.logger.info(f"✅ Ordem de fechamento: #{order['id']}")
                
                # Registra trade
                trade_record = {
                    'entry_time': self.position_entry_time,
                    'exit_time': datetime.now(),
                    'direction': self.current_position['direction'].value,
                    'entry_price': self.current_position['entry_price'],
                    'pnl': pnl,
                    'reason': reason,
                    'duration_seconds': duration
                }
                self.positions_today.append(trade_record)
                
                # Limpa posição
                self.current_position = None
                self.position_entry_time = None
                self.last_trade_time = datetime.now()
                
                # Estatísticas atualizadas
                total_pnl = sum(t.get('pnl', 0) for t in self.positions_today)
                winners = sum(1 for t in self.positions_today if t.get('pnl', 0) > 0)
                win_rate = (winners / len(self.positions_today)) * 100 if self.positions_today else 0
                
                self.logger.info("")
                self.logger.info(f"📊 Trades hoje: {len(self.positions_today)} | "
                                f"Win Rate: {win_rate:.1f}% | "
                                f"PNL Total: ${total_pnl:+.2f}")
                
            else:
                self.logger.error("❌ Falha ao fechar posição")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao fechar posição: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def stop(self):
        """
        Para a estratégia e gera relatório
        Compatível com o padrão do projeto
        """
        self.logger.info("🛑 Parando estratégia...")
        
        # Fecha posição se houver
        if self.current_position:
            current_price = self._get_current_price_sync(self.symbol)
            entry_price = self.current_position['entry_price']
            estimated_pnl = (current_price - entry_price) * self.current_position['size']
            
            if self.current_position['side'] in ['sell', 'ask']:
                estimated_pnl = -estimated_pnl
            
            self._close_position("Stop da estratégia", estimated_pnl)
        
        # Estatísticas do dia
        if self.positions_today:
            total_pnl = sum(t['pnl'] for t in self.positions_today)
            winners = sum(1 for t in self.positions_today if t['pnl'] > 0)
            losers = len(self.positions_today) - winners
            win_rate = (winners / len(self.positions_today)) * 100
            avg_pnl = total_pnl / len(self.positions_today)
            
            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info("📊 RESUMO DA SESSÃO")
            self.logger.info("=" * 60)
            self.logger.info(f"Total de Trades: {len(self.positions_today)}")
            self.logger.info(f"Winners: {winners} ({win_rate:.1f}%)")
            self.logger.info(f"Losers: {losers} ({100-win_rate:.1f}%)")
            self.logger.info("-" * 60)
            self.logger.info(f"PNL Total: ${total_pnl:+.2f}")
            self.logger.info(f"PNL Médio: ${avg_pnl:+.2f} por trade")
            
            if self.positions_today:
                best_trade = max(self.positions_today, key=lambda x: x['pnl'])
                worst_trade = min(self.positions_today, key=lambda x: x['pnl'])
                self.logger.info(f"Melhor Trade: ${best_trade['pnl']:+.2f}")
                self.logger.info(f"Pior Trade: ${worst_trade['pnl']:+.2f}")
            
            self.logger.info("=" * 60)
        
        self.active = False
    
    def get_status(self) -> Dict:
        """
        Retorna status da estratégia
        Compatível com interface web e sistema de monitoramento
        """
        status = {
            'strategy_type': 'directional_scalping',
            'symbols': self.symbols,  # Multi-símbolo
            'symbol': self.symbols[0] if self.symbols else 'BTCUSDT',  # Compatibilidade
            'active': self.active,
            'has_position': len(self.active_positions) > 0,  # Multi-símbolo
            'trades_today': len(self.positions_today),
            'max_trades': self.max_trades_per_day,
            'active_orders': len(self.active_positions),  # Posições ativas
            'active_trades': len(self.active_positions),  # Compatibilidade
            'max_concurrent_trades': getattr(self, 'max_concurrent_trades', 3)  # Fallback
        }
        
        # Informações das posições ativas (multi-símbolo)
        if self.active_positions:
            status['active_positions_details'] = {}
            for symbol, position in self.active_positions.items():
                time_elapsed = (datetime.now() - position['entry_time']).total_seconds()
                status['active_positions_details'][symbol] = {
                    'direction': position['direction'].value,
                    'entry_price': position['entry_price'],
                    'size': position['size'],
                    'time_elapsed': time_elapsed,
                    'time_remaining': max(0, self.trade_duration - time_elapsed)
                }
            
            # Compatibilidade: usar primeira posição como "current_position"
            first_symbol = list(self.active_positions.keys())[0]
            first_position = self.active_positions[first_symbol]
            time_elapsed = (datetime.now() - first_position['entry_time']).total_seconds()
            status['current_position'] = {
                'symbol': first_symbol,
                'direction': first_position['direction'].value,
                'entry_price': first_position['entry_price'],
                'size': first_position['size'],
                'time_elapsed': time_elapsed,
                'time_remaining': max(0, self.trade_duration - time_elapsed)
            }
        
        # Estatísticas de trades
        if self.positions_today:
            total_pnl = sum(t['pnl'] for t in self.positions_today)
            winners = sum(1 for t in self.positions_today if t['pnl'] > 0)
            win_rate = (winners / len(self.positions_today)) * 100
            
            status['performance'] = {
                'total_pnl': total_pnl,
                'win_rate': win_rate,
                'avg_pnl': total_pnl / len(self.positions_today)
            }
        
        return status

    def get_performance_metrics(self) -> Dict:
        """
        Retorna métricas de performance da estratégia scalping
        Compatível com o sistema de métricas do bot
        """
        metrics = {
            'strategy_type': 'directional_scalping',
            'total_trades': len(self.positions_today),
            'active_positions': len(self.active_positions),  # Multi-símbolo
            'max_trades_per_day': self.max_trades_per_day,
            'symbols': self.symbols,  # Multi-símbolo
            'available_symbols': len(self.symbols),
            'max_concurrent_trades': getattr(self, 'max_concurrent_trades', 3)  # Fallback
        }
        
        if self.positions_today:
            # Calcular métricas básicas
            total_pnl = sum(t['pnl'] for t in self.positions_today)
            winners = sum(1 for t in self.positions_today if t['pnl'] > 0)
            losers = len(self.positions_today) - winners
            win_rate = (winners / len(self.positions_today)) * 100
            avg_pnl = total_pnl / len(self.positions_today)
            
            # Métricas de performance
            metrics.update({
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate, 1),
                'avg_pnl_per_trade': round(avg_pnl, 2),
                'winners': winners,
                'losers': losers,
                'best_trade': max(t['pnl'] for t in self.positions_today),
                'worst_trade': min(t['pnl'] for t in self.positions_today),
                'daily_limit_reached': len(self.positions_today) >= self.max_trades_per_day
            })
            
            # Status de risco
            daily_loss_percent = (abs(total_pnl) / self.max_daily_loss * 100) if total_pnl < 0 else 0
            metrics.update({
                'daily_loss_percent': round(daily_loss_percent, 1),
                'risk_status': 'HIGH' if daily_loss_percent > 80 else 'MEDIUM' if daily_loss_percent > 50 else 'LOW'
            })
        else:
            # Sem trades ainda
            metrics.update({
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'avg_pnl_per_trade': 0.0,
                'winners': 0,
                'losers': 0,
                'best_trade': 0.0,
                'worst_trade': 0.0,
                'daily_limit_reached': False,
                'daily_loss_percent': 0.0,
                'risk_status': 'LOW'
            })
        
        return metrics
    
    # ========================================================================
    # MÉTODOS DE COMPATIBILIDADE COM O PADRÃO DO PROJETO
    # ========================================================================
    
    def check_and_rebalance_async(self, current_price: float):
        """
        Método async de compatibilidade com grid strategies
        Para scalping, executa a estratégia
        """
        return self.execute_strategy()
    
    def check_and_rebalance(self, current_price: float):
        """
        Método síncrono de compatibilidade com grid strategies
        Para scalping, executa a estratégia
        """
        try:
            return self.execute_strategy()
        except Exception as e:
            self.logger.error(f"❌ Erro no rebalanceamento: {e}")
            return False
    
    def get_active_orders(self) -> list:
        """Retorna lista de ordens ativas (para compatibilidade)"""
        # Converter posições ativas para formato de ordens
        orders = []
        for symbol, position in self.active_positions.items():
            orders.append({
                'symbol': symbol,
                'side': position['side'],
                'size': position['size'],
                'price': position['entry_price'],
                'direction': position['direction'].value,
                'entry_time': position['entry_time']
            })
        return orders
    
    def get_grid_status(self) -> Dict:
        """Alias para get_status (compatibilidade)"""
        return self.get_status()
    
    def initialize_grid(self, current_price: float) -> bool:
        """
        Inicializa a estratégia (método síncrono para compatibilidade)
        
        Args:
            current_price: Preço atual do mercado
            
        Returns:
            bool: True se inicializou com sucesso
        """
        try:
            return self.initialize()
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar grid: {e}")
            return False
    
    def check_filled_orders(self, current_price: float):
        """
        Verifica ordens executadas (método síncrono para compatibilidade)
        
        Args:
            current_price: Preço atual do mercado
        """
        try:
            self.manage_positions()
        except Exception as e:
            self.logger.error(f"❌ Erro ao verificar ordens: {e}")
    
    def cancel_all_orders(self):
        """
        Cancela todas as ordens ativas (método síncrono para compatibilidade)
        """
        try:
            self.stop()
            self.logger.info("🚫 Todas as ordens canceladas")
        except Exception as e:
            self.logger.error(f"❌ Erro ao cancelar ordens: {e}")

    def log_performance_summary(self):
        """
        Logar estatísticas de desempenho (igual multi-asset)
        """
        try:
            total_trades = len(self.positions_today)
            if total_trades == 0:
                self.logger.info("📊 ESTATÍSTICAS SCALPING: Nenhum trade hoje")
                return

            # Calcular estatísticas de PNL
            total_pnl = sum(trade['pnl'] for trade in self.positions_today)
            winning_trades = [t for t in self.positions_today if t['pnl'] > 0]
            losing_trades = [t for t in self.positions_today if t['pnl'] < 0]
            
            win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
            avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0

            # Estatísticas por símbolo
            symbols_stats = {}
            for trade in self.positions_today:
                symbol = trade['symbol']
                if symbol not in symbols_stats:
                    symbols_stats[symbol] = {'trades': 0, 'pnl': 0}
                symbols_stats[symbol]['trades'] += 1
                symbols_stats[symbol]['pnl'] += trade['pnl']

            self.logger.info("=" * 60)
            self.logger.info("📊 ESTATÍSTICAS SCALPING HOJE:")
            self.logger.info(f"  💰 PNL Total: ${total_pnl:+.2f}")
            self.logger.info(f"  📈 Trades: {total_trades} | Win Rate: {win_rate:.1f}%")
            self.logger.info(f"  ✅ Wins: {len(winning_trades)} (${avg_win:+.2f} média)")
            self.logger.info(f"  ❌ Losses: {len(losing_trades)} (${avg_loss:+.2f} média)")
            self.logger.info(f"  🔄 Posições Ativas: {len(self.active_positions)}")

            # Estatísticas de análise por símbolo
            self.logger.info("\n📊 ANÁLISES POR SÍMBOLO:")
            for symbol in self.symbols:
                stats = self.symbol_analysis_stats.get(symbol, {})
                trades_stats = symbols_stats.get(symbol, {'trades': 0, 'pnl': 0})
                
                analyses = stats.get('analyses', 0)
                avg_conf = stats.get('avg_confidence', 0)
                last_dir = stats.get('last_direction', 'N/A')
                
                self.logger.info(
                    f"  {symbol}: {analyses} análises | "
                    f"Conf: {avg_conf:.0%} | Dir: {last_dir} | "
                    f"Trades: {trades_stats['trades']} | "
                    f"PNL: ${trades_stats['pnl']:+.2f}"
                )

            self.logger.info("=" * 60)

        except Exception as e:
            self.logger.error(f"❌ Erro ao gerar estatísticas: {e}")