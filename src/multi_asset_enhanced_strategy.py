"""
Multi-Asset Enhanced Strategy - Versão com Algoritmo de Sinais Melhorado
Estratégia separada que usa análise técnica avançada para identificar oportunidades
"""

import os
import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional
from src.performance_tracker import PerformanceTracker
from src.strategy_logger import create_strategy_logger
from src.enhanced_signal_detector import EnhancedSignalDetector
from src.emergency_sl_system import EmergencyStopLoss

class MultiAssetEnhancedStrategy:
    def __init__(self, auth_client, calculator, position_manager):
        """Inicializa estratégia multi-asset com algoritmo de sinais melhorado"""
        self.logger = create_strategy_logger('PacificaBot.MultiAssetEnhanced', 'multi_asset_enhanced')
        
        self.auth = auth_client
        self.calculator = calculator
        self.position_mgr = position_manager
        
        # Configurações específicas do multi-asset
        self.symbols = self._parse_symbols()
        self.position_size_usd = float(os.getenv('POSITION_SIZE_USD', '20'))
        self.leverage = int(os.getenv('LEVERAGE', '10'))
        self.max_concurrent_trades = int(os.getenv('MAX_CONCURRENT_TRADES', '3'))
        self.allow_multiple_per_symbol = os.getenv('ALLOW_MULTIPLE_PER_SYMBOL', 'false').lower() == 'true'
        self.price_change_threshold = float(os.getenv('PRICE_CHANGE_THRESHOLD', '0.3'))
        
        # Configurações de TP/SL
        self.auto_close_enabled = os.getenv('AUTO_CLOSE_ENABLED', 'true').lower() == 'true'
        self.use_api_tp_sl = os.getenv('USE_API_TP_SL', 'true').lower() == 'true'
        self.stop_loss_percent = float(os.getenv('STOP_LOSS_PERCENT', '1.5'))   # ✅ Limite de perda menor
        self.take_profit_percent = float(os.getenv('TAKE_PROFIT_PERCENT', '2.0')) # ✅ Meta de lucro maior
        self.trailing_stop_enabled = os.getenv('TRAILING_STOP_ENABLED', 'false').lower() == 'true'
        self.trailing_stop_percent = float(os.getenv('TRAILING_STOP_PERCENT', '0.5'))
        self.max_position_time_minutes = int(os.getenv('MAX_POSITION_TIME_MINUTES', '60'))
        
        # 🆕 CONFIGURAÇÕES ESPECÍFICAS DO ALGORITMO MELHORADO
        self.enhanced_min_signal_quality = int(os.getenv('ENHANCED_MIN_SIGNAL_QUALITY', '60'))  # 0-100
        self.enhanced_min_confidence = int(os.getenv('ENHANCED_MIN_CONFIDENCE', '70'))  # 0-100
        self.enhanced_use_rsi_filter = os.getenv('ENHANCED_USE_RSI_FILTER', 'true').lower() == 'true'
        self.enhanced_max_volatility = float(os.getenv('ENHANCED_MAX_VOLATILITY', '5.0'))  # %
        self.enhanced_min_history = int(os.getenv('ENHANCED_MIN_HISTORY', '20'))  # períodos
        
        # Estado interno
        self.price_history = {}  # {symbol: [prices]} - Histórico expandido
        self.lot_sizes = {}     # {symbol: lot_size}
        self.active_positions = {}  # {position_id: position_data}
        self.symbol_positions = {}  # {symbol: count}
        
        # 🆕 DETECTOR DE SINAIS MELHORADO
        self.signal_detector = EnhancedSignalDetector(self.logger)
        self.signal_detector.min_signal_quality = self.enhanced_min_signal_quality
        
        # Estatísticas da estratégia
        self.signals_detected = 0
        self.signals_executed = 0
        self.signals_rejected_quality = 0
        self.signals_rejected_limits = 0
        
        # TP/SL tracking
        self.position_max_profit = {}
        self.position_trailing_stops = {}
        
        # Performance tracking
        self.performance_tracker = PerformanceTracker(
            symbols=self.symbols if len(self.symbols) <= 5 else self.symbols[:5]
        )
        
        # 🔧 CACHE PARA SYMBOL_INFO (precisa existir antes de _initialize_symbols)
        self.symbol_info_cache = {}

        # INICIALIZAR ESTRUTURAS PARA CADA SÍMBOLO COM VALIDAÇÃO
        self._initialize_symbols()
        
        self.logger.strategy_info(f"Enhanced Multi-Asset inicializada com {len(self.symbols)} símbolos")
        self.logger.info(f"🧠 Algoritmo melhorado: Quality ≥ {self.enhanced_min_signal_quality}, Confidence ≥ {self.enhanced_min_confidence}")
        
        self._tp_sl_check_counter = 0

        # CAMADA 3: Emergency Stop Loss
        self.emergency_sl = EmergencyStopLoss(
            auth_client=self.auth,
            position_manager=self.position_mgr,
            logger=self.logger
        )
        
        self.logger.info("✅ Sistema de 3 camadas ativado:")
        self.logger.info("  Camada 1: TP/SL da API (criado com ordem)")
        self.logger.info("  Camada 2: Shadow SL (monitoramento interno)")
        self.logger.info("  Camada 3: Emergency SL (fail-safe)")


    def get_symbol_info_cached(self, symbol: str):
        """Obtém symbol_info com cache para evitar requisições duplicadas"""
        if symbol not in self.symbol_info_cache:
            symbol_info = self.auth.get_symbol_info(symbol)
            if symbol_info:
                self.symbol_info_cache[symbol] = symbol_info
            else:
                return None
        return self.symbol_info_cache[symbol]
    
    def _initialize_symbols(self):
        """Inicializar estruturas para cada símbolo com validação"""
        for symbol in self.symbols:
            self.price_history[symbol] = []
            
            # ✅ Preencher cache e validar
            symbol_info = self.get_symbol_info_cached(symbol)
            if symbol_info:
                tick_size = symbol_info.get('tick_size')
                lot_size = symbol_info.get('lot_size')
                self.logger.info(f"✅ {symbol}: tick_size={tick_size}, lot_size={lot_size}")
            else:
                self.logger.warning(f"⚠️ {symbol}: Não foi possível obter symbol_info")
            
            self.lot_sizes[symbol] = self.get_lot_size(symbol)
            self.symbol_positions[symbol] = 0   

    def _parse_symbols(self) -> List[str]:
        """Parse dos símbolos do .env"""
        symbols_str = os.getenv('SYMBOLS', 'BTC,ETH,SOL')
        
        self.logger.info(f"📋 SYMBOLS configurado: {symbols_str}")
        
        if symbols_str.upper() == 'AUTO':
            self.logger.info("🔍 Modo AUTO detectado - buscando símbolos da API...")
            result = self._get_all_available_symbols()
            self.logger.info(f"✅ Símbolos retornados pelo AUTO: {result}")
            return result
        else:
            # ✅ CRÍTICO: Adicionar .upper() aqui!
            symbols = [s.strip().upper() for s in symbols_str.split(',')]
            self.logger.info(f"✅ Símbolos manuais configurados: {symbols}")
            return symbols
    
    def _get_all_available_symbols(self) -> List[str]:
        """Busca todos os símbolos disponíveis com blacklist configurável"""
        try:
            prices_data = self.auth.get_prices()
            
            # Validar resposta
            if not prices_data:
                self.logger.warning("⚠️ API não retornou dados de preços")
                return ['BTC', 'ETH', 'SOL']
            
            # Extrair dados (suporta diferentes estruturas)
            if isinstance(prices_data, dict):
                data_list = prices_data.get('data', [])
            elif isinstance(prices_data, list):
                data_list = prices_data
            else:
                self.logger.error(f"❌ Formato inesperado da API: {type(prices_data)}")
                return ['BTC', 'ETH', 'SOL']
            
            if not data_list:
                self.logger.warning("⚠️ Lista de dados vazia na resposta da API")
                return ['BTC', 'ETH', 'SOL']
            
            # Extrair todos os símbolos
            all_symbols = []
            for item in data_list:
                symbol = item.get('symbol')
                if symbol:
                    all_symbols.append(symbol)
            
            if not all_symbols:
                self.logger.warning("⚠️ Nenhum símbolo encontrado nos dados")
                return ['BTC', 'ETH', 'SOL']
            
            self.logger.info(f"✅ Total de símbolos na exchange: {len(all_symbols)}")
            self.logger.info(f"📋 Todos os símbolos: {all_symbols}")
            
            # 🆕 LER BLACKLIST DO .ENV
            use_blacklist = os.getenv('SYMBOLS_USE_BLACKLIST', 'true').lower() == 'true'
            blacklist_str = os.getenv('SYMBOLS_BLACKLIST', 'PUMP,kPEPE,FARTCOIN')
            max_symbols = int(os.getenv('SYMBOLS_MAX_COUNT', '0'))
            
            # Aplicar blacklist se configurado
            if use_blacklist and blacklist_str:
                blacklist = [s.strip().upper() for s in blacklist_str.split(',')]
                filtered_symbols = [s for s in all_symbols if s not in blacklist]
                
                removed_count = len(all_symbols) - len(filtered_symbols)
                if removed_count > 0:
                    removed_list = [s for s in all_symbols if s in blacklist]
                    self.logger.info(f"🚫 Blacklist removeu {removed_count} símbolos: {removed_list}")
                else:
                    self.logger.info("ℹ️ Nenhum símbolo na blacklist foi encontrado")
                
                symbols = filtered_symbols
            else:
                symbols = all_symbols
                self.logger.info("ℹ️ Blacklist desativada - usando todos os símbolos")
            
            # Aplicar limite se configurado
            if max_symbols > 0 and len(symbols) > max_symbols:
                self.logger.info(f"📊 Limitando de {len(symbols)} para {max_symbols} símbolos")
                symbols = symbols[:max_symbols]
            
            self.logger.info(f"🎯 Símbolos finais selecionados: {len(symbols)}")
            self.logger.info(f"📋 Lista final: {symbols}")
            
            return symbols
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao buscar símbolos: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
        
        # Fallback final
        self.logger.warning("⚠️ Usando fallback padrão: BTC, ETH, SOL")
        return ['BTC', 'ETH', 'SOL']
    
    def get_lot_size(self, symbol: str) -> float:
        """Obtém lot size para o símbolo com validação detalhada"""
        try:
            # Usar info com cache para evitar requisições duplicadas e logs repetidos
            info = self.get_symbol_info_cached(symbol)
            if info and 'lot_size' in info:
                lot_size = float(info['lot_size'])
                tick_size = float(info.get('tick_size', 0.01))
                
                # Não logar novamente aqui para evitar duplicidade; o log ocorre quando o cache é preenchido
                return lot_size
        except Exception as e:
            self.logger.warning(f"Erro ao obter lot_size para {symbol}: {e}")
        
        # Fallback baseado no símbolo
        lot_sizes = {
            'BTC': 0.00001, 'ETH': 0.0001, 'SOL': 0.01, 'AVAX': 0.01,
            'DOGE': 1, 'ADA': 1, 'MATIC': 0.1, 'DOT': 0.1,
            'LINK': 0.1, 'UNI': 0.1, 'AAVE': 0.01, 'ATOM': 0.01
        }
        fallback = lot_sizes.get(symbol, 0.001)
        self.logger.warning(f"⚠️ {symbol}: usando fallback lot_size={fallback}")
        return fallback
    
    def initialize_grid(self, current_price: float) -> bool:
        """Método compatível com o bot principal - inicializa estratégia"""
        self.logger.strategy_info("Inicializando Enhanced Multi-Asset Strategy...")
        
        try:
            # 1. Inicializar histórico de preços expandido
            prices = self.auth.get_prices()
            if prices and 'data' in prices:
                for item in prices['data']:
                    symbol = item.get('symbol')
                    price = item.get('mark') or item.get('mid')
                    if symbol in self.symbols and price:
                        self.price_history[symbol] = [float(price)]
                        
            self.logger.info(f"✅ Preços iniciais carregados para {len(self.price_history)} símbolos")
            
            # 2. Sincronizar posições existentes na API
            self.logger.info("🔄 Sincronizando com posições existentes na API...")
            self._sync_positions_with_api()
            
            if self.active_positions:
                self.logger.warning(f"⚠️ {len(self.active_positions)} posições existentes encontradas na API")
                for pos_id, pos in self.active_positions.items():
                    self.logger.info(f"  - {pos['symbol']}: {pos['quantity']} @ ${pos['price']:.2f}")
            else:
                self.logger.info("✅ Nenhuma posição existente - começando do zero")
            
            # 3. Executar Emergency SL imediatamente se houver posições
            if self.active_positions:
                self.logger.warning("🚨 Executando Emergency SL inicial nas posições existentes...")
                self.emergency_sl.check_all_positions(self.active_positions)
                
                # Aguardar alguns segundos para processar
                time.sleep(2)
                
                # Verificar se alguma posição foi fechada
                remaining = len(self.active_positions)
                self.logger.info(f"✅ Verificação inicial concluída - {remaining} posições ativas")
            
            # 4. Log das configurações melhoradas
            status = self.signal_detector.get_algorithm_status()
            self.logger.info(f"🧠 Algoritmo: {status['version']} com {len(status['indicators'])} indicadores")
            self.logger.info(f"🎯 Pesos: Momentum={status['weights']['momentum']}% | Trend={status['weights']['trend']}% | RSI={status['weights']['rsi']}%")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar Enhanced Strategy: {e}")
            return False
        
    def check_filled_orders(self, current_price: float):
        """Verifica ordens executadas e analisa sinais - método compatível"""
        try:
            # 1. Verificar ordens preenchidas (mesmo processo da versão original)
            self._check_filled_orders_internal()
            
            # 2. Atualizar histórico de preços
            self._update_price_history()
            
            # 3. 🆕 ANÁLISE DE SINAIS MELHORADA
            self._analyze_market_signals()
            
            # 4. Verificar TP/SL manual se habilitado
            if not self.use_api_tp_sl:
                self._check_all_tp_sl()
                
        except Exception as e:
            self.logger.error(f"❌ Erro no check_filled_orders: {e}")
    
    def _check_filled_orders_internal(self):
        """Lógica interna de verificação de ordens preenchidas"""
        # Implementar verificação de ordens preenchidas
        # (mesmo processo da estratégia original)
        pass
    
    def _update_price_history(self):
        """Atualiza histórico de preços para análise técnica"""
        try:
            prices_data = self.auth.get_prices()
            if not prices_data or not prices_data.get('success'):
                return
                
            for item in prices_data.get('data', []):
                symbol = item.get('symbol')
                price = item.get('mark') or item.get('mid')
                
                if symbol in self.symbols and price:
                    current_price = float(price)
                    
                    if symbol not in self.price_history:
                        self.price_history[symbol] = []
                    
                    # Adicionar novo preço
                    self.price_history[symbol].append(current_price)
                    
                    # 🔧 NOVA ADIÇÃO: Limitar tamanho do histórico para evitar memory leak
                    MAX_HISTORY_SIZE = 100  # Manter apenas 100 últimos preços
                    if len(self.price_history[symbol]) > MAX_HISTORY_SIZE:
                        # Remove 50% quando atinge limite (otimização de performance)
                        self.price_history[symbol] = self.price_history[symbol][-50:]
                        self.logger.debug(f"🧹 Histórico {symbol} limitado a 50 entradas para evitar memory leak")
                        
        except Exception as e:
            self.logger.error(f"❌ Erro ao atualizar histórico de preços: {e}")
    
    def _analyze_market_signals(self):
        """🆕 ANÁLISE DE SINAIS COM ALGORITMO MELHORADO + HISTÓRICO DA API"""
        
        self.logger.info(f"🔍 Enhanced: Analisando sinais em {len(self.symbols)} símbolos...")
    
        signals_found = 0
        for i, symbol in enumerate(self.symbols):
            if symbol not in self.price_history:
                continue
                
            try:
                # 🔧 DELAY ENTRE SÍMBOLOS PARA REDUZIR CARGA NA API
                if i > 0:  # Não aplicar delay no primeiro símbolo
                    delay = 0.6  # 600ms entre símbolos
                    time.sleep(delay)
                
                current_price = self.price_history[symbol][-1]
                price_history = self.price_history[symbol]
                
                # 🔥 VERIFICAR SE PRECISA DE HISTÓRICO DA API
                if len(price_history) < self.enhanced_min_history:
                    self.logger.debug(f"🔄 {symbol}: Histórico insuficiente ({len(price_history)} < {self.enhanced_min_history}), buscando na API...")
                    
                    # Buscar histórico da API
                    api_history = self.auth.get_historical_data(
                        symbol=symbol, 
                        interval="1m", 
                        periods=self.enhanced_min_history + 5  # Pegar alguns extras
                    )
                    
                    if api_history and len(api_history) >= self.enhanced_min_history:
                        self.logger.info(f"✅ {symbol}: Histórico obtido da API - {len(api_history)} preços")
                        # Combinar histórico da API + cache atual
                        combined_history = api_history[:-1] + price_history  # Remove último da API para evitar duplicata
                        price_history = combined_history
                    else:
                        self.logger.warning(f"⚠️ {symbol}: Histórico insuficiente na API também, pulando análise")
                        continue
                
                # 🧠 USAR DETECTOR MELHORADO
                signal = self.signal_detector.detect_signal(
                    symbol=symbol,
                    price_history=price_history,
                    current_price=current_price,
                    price_change_threshold=self.price_change_threshold
                )
                
                if signal:
                    signals_found += 1
                    self.signals_detected += 1
                    
                    # 🎯 LOG MELHORADO COM INFORMAÇÕES DO SINAL
                    quality_score = signal.get('quality_score', 0)
                    confidence = signal.get('confidence', 0)
                    side = signal.get('side', 'N/A')
                    
                    self.logger.info(f"⚡ {symbol}: Sinal {side} detectado - Qualidade: {quality_score:.1f}/100, Confiança: {confidence:.1f}/100")
                    
                    # Log dos indicadores
                    momentum = signal.get('momentum', 0)
                    trend = signal.get('trend', 'N/A')
                    rsi = signal.get('rsi', 0)
                    volatility = signal.get('volatility', 0)
                    
                    self.logger.debug(f"   📊 Indicadores: Momentum={momentum:.2f}%, Trend={trend}, RSI={rsi:.1f}, Vol={volatility:.2f}%")
                    
                    # Verificar confiança mínima
                    if confidence >= self.enhanced_min_confidence:
                        
                        # Verificar se pode executar
                        if self._can_execute_enhanced_signal(symbol, signal):
                            self.logger.info(f"🚀 {symbol}: Executando sinal Enhanced...")
                            self._execute_enhanced_signal(symbol, signal)
                            self.signals_executed += 1
                        else:
                            self.signals_rejected_limits += 1
                            self.logger.debug(f"🚫 {symbol}: Sinal rejeitado - Limites de execução")
                    else:
                        self.signals_rejected_quality += 1
                        self.logger.debug(f"📊 {symbol}: Sinal rejeitado - Confiança {confidence:.1f} < {self.enhanced_min_confidence}")
                        
            except Exception as e:
                self.logger.error(f"❌ Erro ao analisar {symbol}: {e}")
                import traceback
                self.logger.debug(f"📋 Stack trace: {traceback.format_exc()}")
        
        # 📊 LOG FINAL DA ANÁLISE COM ESTATÍSTICAS
        if signals_found > 0:
            execution_rate = (self.signals_executed / self.signals_detected * 100) if self.signals_detected > 0 else 0
            self.logger.info(f"📊 Enhanced: {signals_found} sinais encontrados | Executados: {self.signals_executed} | Taxa: {execution_rate:.1f}%")
        else:
            self.logger.info(f"📊 Enhanced: Nenhum sinal encontrado nos {len(self.symbols)} símbolos analisados")
    
    def _can_execute_enhanced_signal(self, symbol: str, signal: Dict) -> bool:
        """Verifica se pode executar sinal com validações adicionais"""
        
        # 1. Verificações básicas (mesmo da versão original)
        if len(self.active_positions) >= self.max_concurrent_trades:
            self.logger.info(f"📊 {symbol}: Rejeitado - limite de trades ({len(self.active_positions)} >= {self.max_concurrent_trades})")
            return False
        
        if not self.allow_multiple_per_symbol:
            if self.symbol_positions.get(symbol, 0) > 0:
                self.logger.info(f"📊 {symbol}: Rejeitado - já tem posição ativa")
                return False
        
        # 2. Verificar margem
        margin_needed = self.position_size_usd / self.leverage
        can_place, msg = self.position_mgr.can_place_order(self.position_size_usd)
        
        if not can_place:
            self.logger.info(f"📊 {symbol}: Rejeitado - margem insuficiente ({msg})")
            return False
        
        # 3. 🆕 FILTROS ADICIONAIS PARA ALGORITMO MELHORADO
        
        # Filtro de volatilidade extrema
        if signal['volatility'] > self.enhanced_max_volatility:
            self.logger.info(f"📊 {symbol}: Rejeitado - volatilidade alta ({signal['volatility']:.2f}% > {self.enhanced_max_volatility}%)")
            return False
        
        # Filtro RSI se habilitado
        if self.enhanced_use_rsi_filter:
            rsi = signal['rsi']
            side = signal['side']
            
            # Evitar comprar em overbought ou vender em oversold
            if (side == 'LONG' and rsi > 80) or (side == 'SHORT' and rsi < 20):
                self.logger.info(f"📊 {symbol}: Rejeitado - RSI extremo ({rsi:.1f}) para {side}")
                return False
        
        # 🎯 LOG DE APROVAÇÃO
        self.logger.info(f"📊 {symbol}: Sinal APROVADO - todas validações passaram")
        return True
    
    def _execute_enhanced_signal(self, symbol: str, signal: Dict):
        """EXECUTA SINAL COM CORREÇÕES DE TIPO E CACHE"""
        
        try:
            side = signal['side']
            current_price = float(self.price_history[symbol][-1])
            quality_score = float(signal['quality_score'])
            confidence = float(signal['confidence'])
            
            # Log melhorado
            self.logger.enhanced_signal(symbol, quality_score, confidence/100, side)
            
            # Detalhes técnicos
            indicators = {
                'Momentum': f"{signal['momentum']:.2f}%",
                'Trend': signal['trend'],
                'RSI': f"{signal['rsi']:.1f}",
                'Volatility': f"{signal['volatility']:.2f}%"
            }
            self.logger.enhanced_analysis(symbol, indicators)
            
            # 🔧 USAR CACHE PARA SYMBOL_INFO
            symbol_info = self.get_symbol_info_cached(symbol)
            if not symbol_info:
                self.logger.error(f"❌ Não foi possível obter informações do símbolo {symbol}")
                return
                
            tick_size = float(symbol_info.get('tick_size', 0.01))
            
            # Calcular quantidade
            base_quantity = self.position_size_usd / current_price
            lot_size = self.get_lot_size(symbol)

            confidence_multiplier = min(1.2, confidence / 100 + 0.2)
            adjusted_quantity = base_quantity * confidence_multiplier

            # Usar Decimal para evitar erro de precisão
            quantity_decimal = Decimal(str(adjusted_quantity))
            lot_size_decimal = Decimal(str(lot_size))

            multiplier = int(quantity_decimal / lot_size_decimal)
            quantity = float(multiplier * lot_size_decimal)

            if quantity < lot_size:
                quantity = lot_size

            # Formatar baseado no lot_size
            if lot_size >= 1:
                quantity = round(quantity, 0)
            elif lot_size >= 0.01:
                quantity = round(quantity, 2)
            elif lot_size >= 0.001:
                quantity = round(quantity, 3)
            else:
                quantity = round(quantity, 8)
            
            self.logger.info(f"   💰 Quantity: {quantity} (ajustada por confidence: {confidence_multiplier:.2f}x)")
            
            # Determinar lado da ordem
            order_side = 'bid' if side == 'LONG' else 'ask'
            
            # Arredondar preço principal
            current_price_rounded = self.auth._round_to_tick_size(current_price, tick_size)
            
            # Preparar TP/SL com arredondamento
            take_profit_config = None
            stop_loss_config = None
            
            if self.auto_close_enabled and self.use_api_tp_sl:
                if side == 'LONG':
                    tp_stop_price = current_price * (1 + self.take_profit_percent / 100)
                    tp_limit_price = tp_stop_price * 0.999
                    sl_stop_price = current_price * (1 - self.stop_loss_percent / 100)
                    sl_limit_price = sl_stop_price * 1.001
                else:  # SHORT
                    tp_stop_price = current_price * (1 - self.take_profit_percent / 100)
                    tp_limit_price = tp_stop_price * 1.001
                    sl_stop_price = current_price * (1 + self.stop_loss_percent / 100)
                    sl_limit_price = sl_stop_price * 0.999
                
                # Arredondar todos os preços
                tp_stop_price_rounded = self.auth._round_to_tick_size(tp_stop_price, tick_size)
                tp_limit_price_rounded = self.auth._round_to_tick_size(tp_limit_price, tick_size)
                sl_stop_price_rounded = self.auth._round_to_tick_size(sl_stop_price, tick_size)
                sl_limit_price_rounded = self.auth._round_to_tick_size(sl_limit_price, tick_size)
                
                take_profit_config = {
                    "stop_price": tp_stop_price_rounded,
                    "limit_price": tp_limit_price_rounded
                }
                
                stop_loss_config = {
                    "stop_price": sl_stop_price_rounded,
                    "limit_price": sl_limit_price_rounded
                }
                
                self.logger.info(f"🎯 TP/SL: TP@${tp_stop_price_rounded}, SL@${sl_stop_price_rounded}")
            
            # Executar ordem
            result = self.auth.create_order(
                symbol=symbol,
                side=order_side,
                amount=str(quantity),
                price=str(current_price_rounded),
                order_type='GTC',
                take_profit=take_profit_config,
                stop_loss=stop_loss_config
            )
            
            if result and result.get('success'):
                order_data = result.get('data', {})
                order_id = order_data.get('order_id')
                position_id = f"{symbol}_{int(time.time())}"
                
                # 🔍 LOG DETALHADO DO QUE A API RETORNA
                self.logger.info("=" * 60)
                self.logger.info(f"DEBUG: Resposta da API para {symbol}")
                self.logger.info(f"Campos disponíveis: {list(order_data.keys())}")
                self.logger.info(f"Dados completos: {order_data}")
                self.logger.info("=" * 60)
                
                # Procurar IDs de TP/SL em diferentes formatos possíveis
                tp_id = None
                sl_id = None
                
                # Formato 1: Campos diretos
                tp_id = order_data.get('take_profit_order_id')
                sl_id = order_data.get('stop_loss_order_id')
                
                # Formato 2: Campos alternativos
                if not tp_id:
                    tp_id = order_data.get('tp_order_id') or order_data.get('takeProfitOrderId')
                if not sl_id:
                    sl_id = order_data.get('sl_order_id') or order_data.get('stopLossOrderId')
                
                # Formato 3: Dentro de sub-objetos
                if not tp_id and 'take_profit' in order_data:
                    tp_id = order_data['take_profit'].get('order_id')
                if not sl_id and 'stop_loss' in order_data:
                    sl_id = order_data['stop_loss'].get('order_id')
                
                self.logger.info(f"IDs encontrados: TP={tp_id}, SL={sl_id}")

                # Salvar posição
                position_info = {
                    'symbol': symbol,
                    'side': order_side,  # 'bid' ou 'ask' conforme API
                    'quantity': quantity,
                    'price': current_price_rounded,
                    'order_id': order_id,
                    'timestamp': datetime.now(),
                    'signal_quality': quality_score,
                    'signal_confidence': confidence,
                    'signal_momentum': signal['momentum'],
                    'signal_trend': signal['trend'],
                    'signal_rsi': signal['rsi'],
                    'signal_volatility': signal['volatility']
                }
                
                # ✅ SALVAR IDs DE TP/SL SE CRIADOS JUNTO COM A ORDEM
                if 'take_profit_order_id' in order_data:
                    position_info['take_profit_order_id'] = order_data['take_profit_order_id']
                    self.logger.info(f"🎯 TP ID salvo: {order_data['take_profit_order_id']}")
                    
                if 'stop_loss_order_id' in order_data:
                    position_info['stop_loss_order_id'] = order_data['stop_loss_order_id']
                    self.logger.info(f"🛡️ SL ID salvo: {order_data['stop_loss_order_id']}")
                
                self.active_positions[position_id] = position_info
                
                self.symbol_positions[symbol] = self.symbol_positions.get(symbol, 0) + 1
                
                self.logger.strategy_info(f"✅ Posição Enhanced aberta: {symbol} {side} {quantity} @ ${current_price_rounded:.4f}")
                
            else:
                self.logger.error(f"❌ Falha ao executar sinal Enhanced: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao executar sinal Enhanced: {e}")
            import traceback
            self.logger.debug(f"Stack trace: {traceback.format_exc()}")

    def _check_all_tp_sl(self):
        """Verificar TP/SL de todas as posições ativas (Enhanced)"""
        if self.use_api_tp_sl:
            # Verificar se posições têm TP/SL via API
            self._verify_api_tp_sl()
        else:
            # Monitoramento manual de TP/SL
            self._check_manual_tp_sl()
    
    def _verify_api_tp_sl(self):
        """Verificar se todas as posições têm TP/SL via API (Enhanced)"""
        if not self.active_positions:
            return
        
        missing_tp_sl = []
        
        for position_id, position in self.active_positions.items():
            has_tp = 'take_profit_order_id' in position and position['take_profit_order_id']
            has_sl = 'stop_loss_order_id' in position and position['stop_loss_order_id']
            
            if not has_tp or not has_sl:
                missing_tp_sl.append({
                    'position_id': position_id,
                    'symbol': position['symbol'],
                    'side': position['side'],
                    'price': position['price'],
                    'quantity': position['quantity'],
                    'has_tp': has_tp,
                    'has_sl': has_sl
                })
        
        if missing_tp_sl:
            self.logger.warning(f"🧠 Enhanced: {len(missing_tp_sl)} posições sem TP/SL completo")
            for pos in missing_tp_sl:
                self.logger.warning(f"⚠️ Enhanced: {pos['symbol']} sem TP/SL - monitoramento interno ativo")
                # Não tenta adicionar via API - depende do monitoramento interno
    
    def _find_tpsl_orders_for_position(self, symbol: str, side: str) -> dict:
        """
        Busca IDs de ordens TP/SL para uma posição específica
        
        Args:
            symbol: Símbolo da posição
            side: Side da posição ('bid' para long, 'ask' para short)
            
        Returns:
            Dict com take_profit_order_id e stop_loss_order_id
        """
        try:
            # Buscar todas as ordens abertas
            all_orders = self.auth.get_open_orders()
            
            if not all_orders:
                return {}
            
            tp_id = None
            sl_id = None
            current_price = self._get_current_price(symbol)
            
            if current_price <= 0:
                self.logger.warning(f"⚠️ Preço atual inválido para {symbol}")
                return {}
            
            # Procurar ordens TP/SL deste símbolo
            for order in all_orders:
                # Filtrar por símbolo
                if order.get('symbol') != symbol:
                    continue
                
                # Identificar se é ordem stop
                stop_price = order.get('stop_price')
                if stop_price is None:
                    continue  # Não é ordem stop
                
                stop_price_float = float(stop_price)
                order_id = order.get('order_id')
                
                # Determinar se é TP ou SL baseado na posição do stop_price
                if side == 'bid':  # Long position
                    # TP está acima do preço atual, SL abaixo
                    if stop_price_float > current_price:
                        tp_id = order_id
                        self.logger.debug(f"   TP encontrado: {order_id} @ ${stop_price_float}")
                    else:
                        sl_id = order_id
                        self.logger.debug(f"   SL encontrado: {order_id} @ ${stop_price_float}")
                else:  # Short position (side == 'ask')
                    # TP está abaixo do preço atual, SL acima
                    if stop_price_float < current_price:
                        tp_id = order_id
                        self.logger.debug(f"   TP encontrado: {order_id} @ ${stop_price_float}")
                    else:
                        sl_id = order_id
                        self.logger.debug(f"   SL encontrado: {order_id} @ ${stop_price_float}")
            
            result = {
                'take_profit_order_id': tp_id,
                'stop_loss_order_id': sl_id
            }
            
            if tp_id or sl_id:
                self.logger.info(f"🔍 IDs encontrados para {symbol}: TP={tp_id}, SL={sl_id}")
            else:
                self.logger.warning(f"⚠️ Nenhuma ordem TP/SL encontrada para {symbol}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao buscar IDs TP/SL: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return {}
    
    def _sync_positions_with_api(self):
        """
        Sincroniza posições internas com API
        Detecta posições que estão na API mas não no tracking
        """
        try:
            api_positions = self.auth.get_positions()
            
            if not api_positions:
                return
            
            current_symbols = set(pos['symbol'] for pos in self.active_positions.values())
            api_symbols = set(pos.get('symbol') for pos in api_positions)
            
            # Detectar posições que estão na API mas NÃO no tracking
            missing_in_tracking = api_symbols - current_symbols
            
            if missing_in_tracking:
                self.logger.warning(f"⚠️ Posições na API mas SEM tracking: {missing_in_tracking}")
                
                # Adicionar ao tracking
                for api_pos in api_positions:
                    symbol = api_pos.get('symbol')
                    if symbol in missing_in_tracking:
                        self._add_orphan_position(api_pos)
            
            # Detectar posições que estão no tracking mas NÃO na API
            missing_in_api = current_symbols - api_symbols
            
            if missing_in_api:
                self.logger.warning(f"⚠️ Posições no tracking mas NÃO na API: {missing_in_api}")
                
                # Remover do tracking
                positions_to_remove = [
                    pid for pid, pos in self.active_positions.items() 
                    if pos['symbol'] in missing_in_api
                ]
                for pid in positions_to_remove:
                    self.logger.info(f"🗑️ Removendo tracking órfão: {pid}")
                    del self.active_positions[pid]
                    
        except Exception as e:
            self.logger.error(f"Erro ao sincronizar posições: {e}")

    def _add_orphan_position(self, api_position):
        """Adiciona posição órfã com entry price CORRETO da API"""
        try:
            symbol = api_position.get('symbol')
            side = api_position.get('side')
            amount = abs(float(api_position.get('amount', 0)))
            
            # ✅ USAR ENTRY PRICE DA API, NÃO O PREÇO ATUAL
            entry_price = float(api_position.get('entry_price', 0))
            
            # Se API não retornar entry_price, tentar outros campos
            if entry_price <= 0:
                entry_price = float(api_position.get('avg_entry_price', 0))
            
            if entry_price <= 0:
                # Último recurso: usar preço atual MAS logar warning
                entry_price = self._get_current_price(symbol)
                self.logger.warning(f"⚠️ {symbol}: API não retornou entry_price, usando preço atual ${entry_price}")
            
            position_id = f"{symbol}_orphan_{int(time.time())}"
            
            self.active_positions[position_id] = {
                'symbol': symbol,
                'side': side,
                'quantity': amount,
                'price': entry_price,  # ✅ Entry real da API
                'order_id': 'unknown',
                'timestamp': datetime.now(),
                'orphan': True
            }
            
            self.logger.warning(f"➕ Posição órfã adicionada: {symbol} {side} @ ${entry_price:.6f}")
            
        except Exception as e:
            self.logger.error(f"Erro ao adicionar posição órfã: {e}")
    
    def _check_manual_tp_sl(self):
        """Monitoramento manual de TP/SL Enhanced (quando USE_API_TP_SL=false)"""
        if not self.active_positions:
            return
        
        positions_to_close = []
        
        for position_id, position in self.active_positions.items():
            try:
                symbol = position['symbol']
                entry_price = position['price']
                side = position['side']
                quantity = position['quantity']
                
                # Obter preço atual
                current_price = self._get_current_price(symbol)
                if not current_price:
                    continue
                
                # Calcular PNL
                if side == 'bid':  # Long position (compramos)
                    pnl_percent = ((current_price - entry_price) / entry_price) * 100
                else:  # Short position (vendemos) - side == 'ask'
                    pnl_percent = ((entry_price - current_price) / entry_price) * 100
                
                # Enhanced: Verificar condições com lógica melhorada
                should_close = False
                close_reason = ""
                
                # Stop Loss
                if pnl_percent <= -self.stop_loss_percent:
                    should_close = True
                    close_reason = f"STOP LOSS: {pnl_percent:.2f}%"
                
                # Take Profit
                elif pnl_percent >= self.take_profit_percent:
                    should_close = True
                    close_reason = f"TAKE PROFIT: {pnl_percent:.2f}%"
                
                # Enhanced: Trailing Stop (se habilitado)
                elif self.trailing_stop_enabled:
                    trailing_result = self._check_trailing_stop(position_id, position, current_price, pnl_percent)
                    if trailing_result:
                        should_close = True
                        close_reason = trailing_result
                
                if should_close:
                    positions_to_close.append({
                        'position_id': position_id,
                        'symbol': symbol,
                        'side': side,
                        'quantity': quantity,
                        'current_price': current_price,
                        'reason': close_reason
                    })
                    
            except Exception as e:
                self.logger.error(f"❌ Enhanced: Erro ao verificar TP/SL manual para {position_id}: {e}")
        
        # Fechar posições que atingiram TP/SL
        for pos in positions_to_close:
            self._close_position_manual(pos)
    
    def _check_trailing_stop(self, position_id: str, position: dict, current_price: float, pnl_percent: float) -> str:
        """Verificar trailing stop Enhanced"""
        try:
            # Inicializar tracking se não existir
            if not hasattr(self, 'position_max_profit'):
                self.position_max_profit = {}
            if not hasattr(self, 'position_trailing_stops'):
                self.position_trailing_stops = {}
            
            # Atualizar máximo lucro visto
            if position_id not in self.position_max_profit:
                self.position_max_profit[position_id] = pnl_percent
            else:
                self.position_max_profit[position_id] = max(self.position_max_profit[position_id], pnl_percent)
            
            max_profit = self.position_max_profit[position_id]
            
            # Se lucro atual está trailing_stop_percent abaixo do máximo
            if max_profit > 0 and (max_profit - pnl_percent) >= self.trailing_stop_percent:
                return f"TRAILING STOP: Max:{max_profit:.2f}% Current:{pnl_percent:.2f}%"
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Erro no trailing stop: {e}")
            return None
    
    def _close_position_manual(self, position_data):
        """Fechar posição manualmente por TP/SL (Enhanced)"""
        try:
            symbol = position_data['symbol']
            side = position_data['side']
            quantity = position_data['quantity']
            current_price = position_data['current_price']
            reason = position_data['reason']
            
            # Determinar lado da ordem de fechamento
            close_side = 'ask' if side == 'bid' else 'bid'
            
            self.logger.info(f"🧠 Enhanced: Fechando posição {symbol} - {reason}")
            
            # Criar ordem de fechamento
            result = self.auth.create_order(
                symbol=symbol,
                side=close_side,
                amount=str(quantity),
                price=str(current_price),
                order_type="GTC",
                reduce_only=True
            )
            
            if result:
                self.logger.info(f"✅ Enhanced: Ordem de fechamento criada para {symbol}")
                # Remover da lista de posições ativas
                position_id = position_data['position_id']
                if position_id in self.active_positions:
                    del self.active_positions[position_id]
                
                # Limpar tracking de trailing stop
                if hasattr(self, 'position_max_profit') and position_id in self.position_max_profit:
                    del self.position_max_profit[position_id]
                if hasattr(self, 'position_trailing_stops') and position_id in self.position_trailing_stops:
                    del self.position_trailing_stops[position_id]
            else:
                self.logger.error(f"❌ Enhanced: Falha ao criar ordem de fechamento para {symbol}")
                
        except Exception as e:
            self.logger.error(f"❌ Enhanced: Erro ao fechar posição manual: {e}")
    
    def _get_current_price(self, symbol: str) -> float:
        """Obter preço atual de um símbolo (Enhanced)"""
        try:
            # Tentar usar histórico primeiro (mais eficiente)
            if hasattr(self, 'price_history') and symbol in self.price_history:
                if self.price_history[symbol]:
                    return float(self.price_history[symbol][-1])
            
            # Fallback para API
            prices_data = self.auth.get_prices()
            if prices_data and prices_data.get('success'):
                for item in prices_data.get('data', []):
                    if item.get('symbol') == symbol:
                        return float(item.get('mark') or item.get('mid') or 0)
            return 0.0
        except Exception as e:
            self.logger.error(f"❌ Enhanced: Erro ao obter preço de {symbol}: {e}")
            return 0.0
    
    def check_and_rebalance(self, current_price: float):
        """🆕 MÉTODO ESSENCIAL - Rebalancear estratégia Enhanced (compatível com bot principal)"""
        self.logger.debug(f"🧠 Enhanced: Iniciando check_and_rebalance - {len(self.symbols)} símbolos para análise")
        try:
            # 1. Atualizar histórico de preços de todos os símbolos
            self._update_price_history()
            self.logger.debug(f"📈 Enhanced: Histórico atualizado para {len(self.price_history)} símbolos")
            
            # 2. Analisar sinais de mercado com algoritmo melhorado
            self._analyze_market_signals()
            
            # 3. Verificação periódica de TP/SL (camada 2)
            self._tp_sl_check_counter += 1

            if self._tp_sl_check_counter >= 1:
                self.logger.debug("🔍 Enhanced: Verificação periódica de TP/SL...")
                self._check_all_tp_sl()
                self._tp_sl_check_counter = 0

            # CAMADA 3: Emergency SL (verificação independente)
            self.emergency_sl.check_all_positions(self.active_positions)

            # 🔍 LOG PERIÓDICO DE STATUS (a cada 10 verificações)
            if not hasattr(self, '_emergency_log_counter'):
                self._emergency_log_counter = 0
            self._emergency_log_counter += 1

            if self._emergency_log_counter >= 10:
                stats = self.emergency_sl.get_statistics()
                self.logger.info("=" * 60)
                self.logger.info("🚨 EMERGENCY SL STATUS (Camada 3)")
                self.logger.info(f"  Total emergency closures: {stats['total_emergency_closures']}")
                self.logger.info(f"  Posições em loss monitoradas: {stats['positions_currently_in_loss']}")
                self.logger.info("=" * 60)
                self._emergency_log_counter = 0
            
            # 4. Log periódico de performance
            if hasattr(self, 'signals_detected') and self.signals_detected > 0:
                execution_rate = (self.signals_executed / self.signals_detected) * 100
                self.logger.debug(f"📊 Enhanced: {self.signals_executed}/{self.signals_detected} sinais executados ({execution_rate:.1f}%)")

            # Sincronizar com API a cada 5 ciclos
            if not hasattr(self, '_sync_counter'):
                self._sync_counter = 0
            self._sync_counter += 1
            
            if self._sync_counter >= 5:
                self.logger.debug("🔄 Sincronizando posições com API...")
                self._sync_positions_with_api()
                self._sync_counter = 0

        except Exception as e:
            self.logger.error(f"❌ Erro no rebalanceamento Enhanced: {e}")
    
    def get_grid_status(self) -> Dict:
        """Retornar status compatível com o bot principal"""
        return {
            'active': len(self.active_positions) > 0,
            'center_price': 0,
            'active_orders': len(self.active_positions)
        }
    
    def get_enhanced_statistics(self) -> Dict:
        """🆕 ESTATÍSTICAS ESPECÍFICAS DA VERSÃO MELHORADA"""
        
        total_signals = self.signals_detected
        success_rate = (self.signals_executed / total_signals * 100) if total_signals > 0 else 0
        
        return {
            'algorithm_version': 'enhanced_v2.0',
            'signals_detected': self.signals_detected,
            'signals_executed': self.signals_executed,
            'signals_rejected_quality': self.signals_rejected_quality,
            'signals_rejected_limits': self.signals_rejected_limits,
            'execution_rate': f"{success_rate:.1f}%",
            'active_positions': len(self.active_positions),
            'symbols_monitored': len(self.price_history),
            'min_signal_quality': self.enhanced_min_signal_quality,
            'min_confidence': self.enhanced_min_confidence,
            'history_length': {symbol: len(prices) for symbol, prices in self.price_history.items()}
        }
    
    def get_performance_metrics(self) -> Dict:
        """Compatibilidade com grid_bot.py - métricas básicas de performance"""
        
        # Usar performance_tracker se disponível
        if hasattr(self, 'performance_tracker') and self.performance_tracker:
            try:
                # Tentar usar métricas do performance_tracker
                total_trades = len(self.performance_tracker.trades)
                win_rate = 0
                total_return = 0
                
                if total_trades > 0:
                    wins = sum(1 for trade in self.performance_tracker.trades if trade.pnl > 0)
                    win_rate = (wins / total_trades) * 100
                    total_return = sum(trade.pnl for trade in self.performance_tracker.trades)
                
                return {
                    'total_trades': total_trades,
                    'win_rate': win_rate,
                    'total_return': total_return,
                    'sharpe_ratio': 0.0,  # Não implementado ainda
                    'max_drawdown_percent': 0.0,  # Não implementado ainda
                    # Métricas específicas Enhanced
                    'signals_detected': self.signals_detected,
                    'signals_executed': self.signals_executed,
                    'execution_rate': (self.signals_executed / self.signals_detected * 100) if self.signals_detected > 0 else 0,
                    'algorithm_version': 'enhanced_v2.0'
                }
            except Exception as e:
                self.logger.error(f"Erro ao calcular métricas do performance_tracker: {e}")
        
        # Fallback para métricas básicas Enhanced
        return {
            'total_trades': len(self.active_positions),
            'win_rate': 0.0,  # Sem dados históricos ainda
            'total_return': 0.0,  # Sem dados históricos ainda  
            'sharpe_ratio': 0.0,
            'max_drawdown_percent': 0.0,
            # Métricas específicas Enhanced
            'signals_detected': self.signals_detected,
            'signals_executed': self.signals_executed,
            'execution_rate': (self.signals_executed / self.signals_detected * 100) if self.signals_detected > 0 else 0,
            'algorithm_version': 'enhanced_v2.0'
        }
    
    def log_performance_summary(self):
        """Log resumo de performance da estratégia melhorada"""
        
        stats = self.get_enhanced_statistics()
        
        self.logger.info("📊 ENHANCED MULTI-ASSET PERFORMANCE:")
        self.logger.info(f"   🎯 Sinais detectados: {stats['signals_detected']}")
        self.logger.info(f"   ✅ Sinais executados: {stats['signals_executed']}")
        self.logger.info(f"   📈 Taxa de execução: {stats['execution_rate']}")
        self.logger.info(f"   🔍 Qualidade mínima: {stats['min_signal_quality']}/100")
        self.logger.info(f"   💪 Confiança mínima: {stats['min_confidence']}/100")
    
    def print_performance_summary(self):
        """Compatibilidade com grid_bot.py - imprimir resumo de performance"""
        
        # Usar performance_tracker se disponível  
        if hasattr(self, 'performance_tracker') and self.performance_tracker:
            try:
                summary = self.performance_tracker.get_performance_summary(include_advanced=True)
                self.logger.info("📊 PERFORMANCE TRACKER:")
                self.logger.info(summary)
            except Exception as e:
                self.logger.error(f"Erro ao gerar resumo do performance_tracker: {e}")
        
        # Sempre mostrar métricas Enhanced específicas
        self.log_performance_summary()