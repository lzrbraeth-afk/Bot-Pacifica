"""
Grid Strategy - Implementação da estratégia de Grid Trading
"""
import os
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from src.performance_tracker import PerformanceTracker, Trade, GridExecution
import uuid

class GridStrategy:
    def __init__(self, auth_client, calculator, position_manager):
        self.logger = logging.getLogger('PacificaBot.GridStrategy')
        
        self.auth = auth_client
        self.calculator = calculator
        self.position_mgr = position_manager
        
        # Configurações
        self.symbol = os.getenv('SYMBOL', 'BTC')
        self.strategy_type = os.getenv('STRATEGY_TYPE', 'market_making')
        self.grid_mode = os.getenv('GRID_MODE', 'maker')
        self.range_exit = os.getenv('RANGE_EXIT', 'true').lower() == 'true'
        
        # Estado do grid
        self.grid_center = 0
        self.active_grid = {'buy_levels': [], 'sell_levels': []}
        self.placed_orders = {}  # {price: order_id}
        self.grid_active = False
       
        # Sistema de métricas
        self.performance_tracker = PerformanceTracker(self.symbol)
        
        self.logger.info(f"GridStrategy inicializada - {self.strategy_type} mode com métricas ativas")
        
    
    def initialize_grid(self, current_price: float) -> bool:
        """Inicializa o grid baseado no preço atual"""
        
        try:
            self.logger.info(f"🔧 Inicializando grid em ${current_price}")
            
            # Validar parâmetros
            valid, errors = self.calculator.validate_grid_parameters()
            if not valid:
                self.logger.error(f"❌ Parâmetros inválidos: {errors}")
                return False
            
            # VERIFICAR ORDENS EXISTENTES PRIMEIRO
            self.logger.info(f"🔍 Verificando ordens existentes para {self.symbol}...")
            existing_orders = self.auth.get_open_orders(self.symbol)
            
            if existing_orders and len(existing_orders) > 0:
                self.logger.info(f"✅ Encontradas {len(existing_orders)} ordens existentes para {self.symbol}")
                
                # Carregar ordens existentes no tracking
                for order in existing_orders:
                    # Filtrar TP/SL para não carregá-las como ordens do grid
                    order_type = order.get('type', '')
                    order_subtype = order.get('subType', '')
                    order_label = str(order.get('label', '')).lower()
                    if (order_type in ['TAKE_PROFIT', 'STOP_LOSS'] or
                        order_subtype in ['take_profit', 'stop_loss'] or
                        'tp' in order_label or 'sl' in order_label):
                        self.logger.debug(f"🔕 Pulando ordem TP/SL: {order.get('order_id')} @ {order.get('price')}")
                        continue

                    order_id = order.get('order_id')
                    price = float(order.get('price', 0))
                    side = order.get('side')
                    quantity = float(order.get('quantity', 0))
                    
                    # 🔧 NORMALIZAR side para 'buy' ou 'sell'
                    if side == 'bid':
                        side = 'buy'
                    elif side == 'ask':
                        side = 'sell'

                    # Adicionar ao tracking principal (apenas ordens do grid)
                    self.placed_orders[price] = order_id
                    self.position_mgr.add_order(order_id, {
                        'price': price,
                        'quantity': quantity,
                        'side': side,
                        'symbol': self.symbol
                    })
                    self.logger.debug(f"  📌 Carregada: {side} @ ${price} (ID: {order_id})")
                
                # Reconstruir grid baseado nas ordens existentes
                self._reconstruct_grid_from_orders(existing_orders, current_price)
                
                self.grid_active = True
                self.grid_center = current_price
                
                self.logger.info(f"✅ Grid retomado com {len(existing_orders)} ordens existentes")
                self.logger.info(f"⏭️ Pulando criação de novas ordens - usando ordens existentes")
                return True  # ✅ Retorna True para continuar o loop
            
            # Se não há ordens, calcular novos níveis
            self.logger.info(f"📊 Nenhuma ordem existente - criando novo grid...")
            self.active_grid = self.calculator.calculate_grid_levels(current_price)

            # Atualizar tracker com saldo inicial
            if hasattr(self.position_mgr, 'account_balance') and self.position_mgr.account_balance > 0:
                self.performance_tracker.update_balance(self.position_mgr.account_balance)

            self.grid_center = current_price
            
            # LIMPAR ORDENS ANTERIORES
            self.placed_orders.clear()

            # Colocar ordens iniciais
            # Durante a inicialização precisamos permitir que _place_single_order
            # execute mesmo com grid_active inicialmente False. Definimos o
            # grid_active temporariamente para True para permitir a criação
            # das ordens iniciais; se falhar, reverteremos para False.
            self.logger.debug("🔧 Temporariamente ativando grid para criação de ordens iniciais")
            self.grid_active = True
            success = self._place_grid_orders()

            if success:
                # grid_active já está True
                self.logger.info(f"✅ Grid ativo com {len(self.placed_orders)} ordens")
                return True  # ✅ Retorna True para continuar
            else:
                # Reverter para estado inativo se falhou
                self.grid_active = False
                self.logger.error(f"❌ Falha ao criar ordens do grid")
                return False  # ❌ Retorna False para encerrar
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao inicializar grid: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _reconstruct_grid_from_orders(self, existing_orders: List, current_price: float) -> None:
        """Reconstrói a estrutura do grid baseado em ordens existentes"""
        
        buy_levels = []
        sell_levels = []
        
        for order in existing_orders:
            price = float(order.get('price', 0))
            side = order.get('side')
            
            # 🔧 CORREÇÃO: Aceitar 'bid' OU 'buy'
            if side in ['buy', 'bid']:
                buy_levels.append(price)
            # 🔧 CORREÇÃO: Aceitar 'ask' OU 'sell'
            elif side in ['sell', 'ask']:
                sell_levels.append(price)
        
        # Ordenar níveis
        buy_levels.sort(reverse=True)  # Maiores primeiro (mais próximos)
        sell_levels.sort()  # Menores primeiro (mais próximos)
        
        # Reconstruir estrutura do grid
        self.active_grid = {
            'buy_levels': buy_levels,
            'sell_levels': sell_levels,
            'current_price': current_price
        }
        
        self.logger.info(f"📊 Grid reconstruído: {len(buy_levels)} buy levels, {len(sell_levels)} sell levels")
    
    def _place_grid_orders(self) -> bool:
        """Coloca ordens do grid"""

            # 🔍 DEBUG: Verificar estado antes de criar ordens
        self.logger.debug(f"🔍 === _place_grid_orders DEBUG ===")
        self.logger.debug(f"🔍 Active grid buy levels: {len(self.active_grid.get('buy_levels', []))}")
        self.logger.debug(f"🔍 Active grid sell levels: {len(self.active_grid.get('sell_levels', []))}")
        self.logger.debug(f"🔍 Placed orders count: {len(self.placed_orders)}")
        
        orders_placed = 0
        
        # Buscar ordens abertas primeiro
        open_orders = self.auth.get_open_orders(self.symbol)
        
        # Criar set com preços que já têm ordens (SEMPRE inicializar)
        existing_prices = {}  # 🔧 SEMPRE criar o dicionário
        
        if open_orders:  # Só preencher se houver ordens
            for order in open_orders:
                if order.get('symbol') == self.symbol:
                    price = float(order.get('price', 0))
                    raw_side = order.get('side')
                    # NORMALIZAR side para 'buy'/'sell' para casar com as keys usadas abaixo
                    if raw_side in ['bid', 'buy']:
                        side_norm = 'buy'
                    elif raw_side in ['ask', 'sell']:
                        side_norm = 'sell'
                    else:
                        side_norm = str(raw_side)
                    existing_prices[f"{price}_{side_norm}"] = order.get('order_id')
        
        # Ordens de compra
        for price in self.active_grid['buy_levels']:
            key = f"{price}_buy"
            # Verificar se já existe ordem nesse preço
            if key not in existing_prices:
                if self._place_single_order(price, 'buy'):
                    orders_placed += 1
            else:
                self.logger.warning(f"⏭️ Pulando ordem buy em ${price} - já existe (ID: {existing_prices[key]})")
        
        # Ordens de venda
        for price in self.active_grid['sell_levels']:
            key = f"{price}_sell"
            if key not in existing_prices:
                if self._place_single_order(price, 'sell'):
                    orders_placed += 1
            else:
                self.logger.warning(f"⏭️ Pulando ordem sell em ${price} - já existe (ID: {existing_prices[key]})")

        self.logger.info(f"📊 {orders_placed} novas ordens colocadas no grid")
        return orders_placed > 0

    def _place_single_order(self, price: float, side: str, quantity: float = None) -> bool:
        """Coloca uma ordem individual"""
        
        if not self.grid_active:
            return False

        try:
            # Calcular quantidade
            if quantity is None:
                quantity = self.calculator.calculate_quantity(price)
            
            order_value = price * quantity
            
            # Verificar se pode colocar ordem
            can_place, reason = self.position_mgr.can_place_order(order_value)
            if not can_place:
                if "Máximo de ordens atingido" in reason:
                    self.logger.info(f"📊 {reason} - aguardando execução de ordens existentes")
                    return False
                else:  # ← ADICIONAR else AQUI
                    self.logger.warning(f"⚠️ Não pode colocar ordem: {reason}")
                    return False

            # Preparar ordem
            order_data = self.calculator.format_order_for_api(price, quantity, side, self.symbol)
            
            # Enviar ordem
            self.logger.debug(f"📤 Enviando ordem: {side} {quantity} {self.symbol} @ ${price}")
            
            result = self.auth.create_order(
                symbol=order_data['symbol'],
                side=order_data['side'],
                amount=order_data['amount'],
                price=order_data['price'],
                order_type=order_data['tif'],
                reduce_only=order_data['reduce_only']
            )
            
            if result and 'success' in result and result['success']:
                if 'data' in result and 'order_id' in result['data']:
                    order_id = result['data']['order_id']
                
                # Registrar ordem (usar preço normalizado como chave)
                key = self._price_key(price)
                self.placed_orders[key] = order_id
                self.position_mgr.add_order(order_id, {
                    'price': price,
                    'quantity': quantity,
                    'side': side,
                    'symbol': self.symbol
                })
                
                # Registrar no performance tracker
                grid_execution = GridExecution(
                    order_id=order_id,
                    symbol=self.symbol,
                    side=side,
                    price=price,
                    quantity=quantity,
                    timestamp=datetime.now(),
                    executed=False
                )
                self.performance_tracker.record_grid_execution(grid_execution)

                self.logger.info(f"✅ Ordem colocada: {order_id} - {side} @ ${price}")
                return True
            else:
                self.logger.error(f"❌ Falha ao criar ordem em ${price}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao colocar ordem em ${price}: {e}")
            return False
    
    def check_and_rebalance(self, current_price: float) -> None:
        """Verifica se precisa rebalancear o grid"""
        
        if not self.grid_active:
            self.logger.warning("⚠️ Grid não está ativo")
            return
        
        # Para Pure Grid - verificar se saiu do range
        if self.strategy_type == 'pure_grid' and self.range_exit:
            if not self._check_price_in_range(current_price):
                self.logger.warning(f"⚠️ Preço fora do range - pausando grid")
                self.pause_grid()
                return
        
        # Verificar se precisa adicionar ordens faltantes
        self.rebalance_grid_orders(current_price)
        
        # Para Market Making - verificar se precisa deslocar grid
        if self.strategy_type == 'market_making':
            if self.calculator.should_shift_grid(current_price, self.grid_center):
                self.logger.info(f"🔄 Deslocando grid de ${self.grid_center} para ${current_price}")
                self.shift_grid(current_price)  # Função para deslocar (próximo passo)
    
    def check_filled_orders(self, current_price: float) -> None:
        """Verifica ordens executadas e cria ordens opostas COM CORREÇÃO"""
        
        try:
            # 🔧 CORREÇÃO: Buscar TODAS as ordens abertas e filtrar corretamente
            all_open_orders = self.auth.get_open_orders()
            
            if all_open_orders is None:
                self.logger.warning("⚠️ Não foi possível buscar ordens abertas")
                return
            
            # FILTRAR APENAS ORDENS PRINCIPAIS (não TP/SL)
            open_orders = []
            tp_sl_orders = []
            
            for order in all_open_orders:
                symbol = order.get('symbol')
                
                if symbol == self.symbol:
                    order_type = order.get('type', '')
                    order_subtype = order.get('subType', '')
                    order_label = order.get('label', '').lower()
                    
                    # Identificar ordens TP/SL
                    if (order_type in ['TAKE_PROFIT', 'STOP_LOSS'] or 
                        order_subtype in ['take_profit', 'stop_loss'] or
                        'tp' in order_label or 'sl' in order_label):
                        tp_sl_orders.append(order)
                    else:
                        open_orders.append(order)
            
            # Log da classificação
            total_symbol_orders = len([o for o in all_open_orders if o.get('symbol') == self.symbol])
            main_count = len(open_orders)
            tp_sl_count = len(tp_sl_orders)
            
            self.logger.debug(f"📋 {self.symbol}: {total_symbol_orders} total | {main_count} principais | {tp_sl_count} TP/SL")
            
            # 🔧 USAR APENAS ORDENS PRINCIPAIS para detecção de fills
            open_order_ids = set()
            for order in open_orders:
                order_id = order.get('order_id')
                if order_id:
                    open_order_ids.add(str(order_id))
            
            self.logger.debug(f"📋 {len(open_order_ids)} ordens principais abertas de {self.symbol}")
            
            # Verificar quais ordens foram executadas
            filled_orders = []
            for price, order_id in list(self.placed_orders.items()):
                if str(order_id) not in open_order_ids:
                    filled_orders.append((price, order_id))
                    self.logger.info(f"🎯 Ordem EXECUTADA detectada: {order_id} @ ${price}")
            
            # Processar cada ordem executada
            for fill_price, order_id in filled_orders:
                # Remover do tracking
                del self.placed_orders[fill_price]
                order_data = self.position_mgr.remove_order(str(order_id))
                
                if order_data:
                    side = order_data.get('side', 'unknown')
                    quantity = order_data.get('quantity', 0)
                    symbol = order_data.get('symbol', self.symbol)
                    
                    self.logger.info(f"💰 Trade executado: {side.upper()} {quantity} {symbol} @ ${fill_price}")
                    
                    # Atualizar posição
                    self.position_mgr.update_position(symbol, side, quantity, fill_price)
                    
                    # Criar ordem oposta para realizar lucro
                    self._create_opposite_order(fill_price, side, quantity)
                else:
                    self.logger.warning(f"⚠️ Dados da ordem {order_id} não encontrados")
            
            if filled_orders:
                self.logger.info(f"✅ Processadas {len(filled_orders)} ordens executadas")
                
                # Atualizar resumo de posições
                summary = self.position_mgr.get_active_positions_summary()
                self.logger.info(f"📊 Posições: {summary['total_longs']} longs, {summary['total_shorts']} shorts")
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao verificar fills: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

    def rebalance_grid_orders(self, current_price: float) -> None:
        """Rebalanceia o grid adicionando ordens faltantes COM CORREÇÃO"""
        
        try:
            self.logger.info(f"🔄 Iniciando rebalanceamento do grid...")
            
            # 1. Buscar ordens abertas atuais
            all_open_orders = self.auth.get_open_orders()
            if all_open_orders is None:
                self.logger.warning("⚠️ Não foi possível buscar ordens para rebalanceamento")
                return
            
            # FILTRAR APENAS ORDENS PRINCIPAIS
            main_orders = []
            
            for order in all_open_orders:
                if order.get('symbol') == self.symbol:
                    order_type = order.get('type', '')
                    order_subtype = order.get('subType', '')
                    order_label = order.get('label', '').lower()
                    
                    # Filtrar TP/SL
                    if not (order_type in ['TAKE_PROFIT', 'STOP_LOSS'] or 
                        order_subtype in ['take_profit', 'stop_loss'] or
                        'tp' in order_label or 'sl' in order_label):
                        main_orders.append(order)
            
            # 2. Separar por tipo e coletar preços existentes
            existing_buy_prices = set()
            existing_sell_prices = set()
            
            for order in main_orders:
                price = float(order.get('price', 0))
                side = order.get('side')
                order_id = order.get('order_id')
                
                # Aceitar tanto 'bid'/'buy' quanto 'ask'/'sell'
                if side in ['buy', 'bid']:
                    existing_buy_prices.add(price)
                    if price not in self.placed_orders:
                        self.placed_orders[price] = order_id
                elif side in ['sell', 'ask']:
                    existing_sell_prices.add(price)
                    if price not in self.placed_orders:
                        self.placed_orders[price] = order_id
            
            total_existing = len(existing_buy_prices) + len(existing_sell_prices)
            self.logger.info(f"📊 Ordens PRINCIPAIS existentes: {len(existing_buy_prices)} buy, {len(existing_sell_prices)} sell (Total: {total_existing})")
            
            # 3. Calcular quantas ordens FALTAM para completar o grid original
            total_grid_size = self.calculator.grid_levels
            target_per_side = total_grid_size // 2
            
            buy_needed = target_per_side - len(existing_buy_prices)
            sell_needed = target_per_side - len(existing_sell_prices)
            
            self.logger.info(f"🎯 Target: {target_per_side} por lado")
            self.logger.info(f"📝 Faltam: {buy_needed} buy, {sell_needed} sell")
            
            # 4. Se não precisa criar ordens, sair
            if buy_needed <= 0 and sell_needed <= 0:
                self.logger.info(f"✅ Grid completo - sem necessidade de rebalanceamento")
                return
            
            # 5. Criar APENAS as ordens faltantes baseado nos níveis do grid
            orders_created = 0
            
            # Criar ordens BUY faltantes
            if buy_needed > 0:
                self.logger.info(f"➕ Criando {buy_needed} ordens BUY...")
                
                buy_count = 0
                level = 1
                while buy_count < buy_needed:
                    # Calcular preço do nível
                    price_offset = (self.calculator.spacing_percent / 100) * level
                    price = current_price * (1 - price_offset)
                    price = self.calculator.round_price(price)
                    
                    # Verificar se já existe ordem nesse preço
                    if price not in existing_buy_prices and price not in self.placed_orders:
                        if self._place_single_order(price, 'buy'):
                            orders_created += 1
                            buy_count += 1
                            existing_buy_prices.add(price)
                        time.sleep(0.3)
                    
                    level += 1
                    
                    # Segurança: não criar mais que o necessário
                    if level > target_per_side * 2:
                        break
            
            # Criar ordens SELL faltantes
            if sell_needed > 0:
                self.logger.info(f"➕ Criando {sell_needed} ordens SELL...")
                
                sell_count = 0
                level = 1
                while sell_count < sell_needed:
                    # Calcular preço do nível
                    price_offset = (self.calculator.spacing_percent / 100) * level
                    price = current_price * (1 + price_offset)
                    price = self.calculator.round_price(price)
                    
                    # Verificar se já existe ordem nesse preço
                    if price not in existing_sell_prices and price not in self.placed_orders:
                        if self._place_single_order(price, 'sell'):
                            orders_created += 1
                            sell_count += 1
                            existing_sell_prices.add(price)
                        time.sleep(0.3)
                    
                    level += 1
                    
                    # Segurança: não criar mais que o necessário
                    if level > target_per_side * 2:
                        break
            
            # 6. Resumo final
            final_buy = len(existing_buy_prices)
            final_sell = len(existing_sell_prices)
            
            if orders_created > 0:
                self.logger.info(f"✅ Rebalanceamento concluído: {orders_created} ordens criadas")
            else:
                self.logger.info(f"✅ Rebalanceamento concluído: nenhuma ordem criada")
                
            self.logger.info(f"📊 Grid final: {final_buy} buy, {final_sell} sell (Total: {final_buy + final_sell})")
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao rebalancear grid: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

    def _create_opposite_order(self, entry_price: float, entry_side: str, quantity: float) -> None:
        """Cria ordem oposta para realizar lucro"""
        
        # Calcular preço alvo (próximo nível do grid)
        target_price = self.calculator.calculate_profit_target(entry_price, entry_side)
        
        # Lado oposto
        opposite_side = 'sell' if entry_side == 'buy' else 'buy'
        
        self.logger.info(f"📝 Criando ordem de LUCRO: {opposite_side.upper()} @ ${target_price}")
        
        # Verificar se já existe ordem nesse preço e cancelar
        key = self._price_key(target_price)
        if key in self.placed_orders:
            self.logger.warning(f"⚠️ Já existe ordem em ${target_price} - cancelando antiga")
            old_order_id = self.placed_orders[key]
            self.auth.cancel_order(str(old_order_id))
            del self.placed_orders[key]
            time.sleep(0.5)  # Aguardar cancelamento
        
        # Criar nova ordem com mesma quantidade
        success = self._place_single_order(target_price, opposite_side, quantity)
        
        if success:

            self.logger.info(f"✅ Ordem de lucro criada: {opposite_side.upper()} {quantity} @ ${target_price}")
            
            # Calcular e mostrar lucro esperado
            if entry_side == 'buy':
                expected_profit = (target_price - entry_price) * quantity
            else:
                expected_profit = (entry_price - target_price) * quantity
            
            self.logger.info(f"💵 Lucro esperado: ${expected_profit:.2f}")
  
        else:
            self.logger.error(f"❌ Falha ao criar ordem de lucro em ${target_price}")

    def _check_price_in_range(self, price: float) -> bool:
        """Verifica se preço está dentro do range do Pure Grid"""
        
        range_min = float(os.getenv('RANGE_MIN', '0'))
        range_max = float(os.getenv('RANGE_MAX', '0'))
        
        if range_min > 0 and range_max > 0:
            in_range = range_min <= price <= range_max
            if not in_range:
                self.logger.warning(f"❌ Preço ${price} fora do range ${range_min}-${range_max}")
            return in_range
        
        return True
    
    def rebalance_grid(self, new_price: float) -> None:
        """Rebalanceia o grid para novo preço central"""
        
        self.logger.info("🔄 Iniciando rebalanceamento do grid")
        
        # Cancelar ordens antigas
        self.cancel_all_orders()
        
        # Aguardar processamento dos cancelamentos na exchange (poll curto)
        timeout = 5.0
        poll_interval = 0.5
        elapsed = 0.0
        while elapsed < timeout:
            current_open = self.auth.get_open_orders(self.symbol)
            if not current_open or len(current_open) == 0:
                break
            time.sleep(poll_interval)
            elapsed += poll_interval
        if elapsed >= timeout:
            self.logger.warning("⚠️ Timeout aguardando cancelamentos na exchange; prosseguindo...")
        
        # Recalcular grid
        self.active_grid = self.calculator.calculate_grid_levels(new_price)
        self.grid_center = new_price
        
        # Colocar novas ordens
        self._place_grid_orders()
        
        self.logger.info(f"✅ Grid rebalanceado para ${new_price}")
    
    def handle_order_fill(self, order_id: str, fill_price: float, fill_quantity: float, side: str) -> None:
        """Processa execução de ordem"""
        
        self.logger.info(f"🎯 Ordem executada: {order_id} - {side} {fill_quantity} @ ${fill_price}")
        
        # Atualizar posição
        self.position_mgr.update_position(self.symbol, side, fill_quantity, fill_price)
        
        # Remover ordem do tracking
        self.position_mgr.remove_order(order_id)
        
        # Remover do grid
        if fill_price in self.placed_orders:
            del self.placed_orders[fill_price]
        
        # Colocar ordem oposta (para realizar lucro)
        opposite_side = 'sell' if side == 'buy' else 'buy'
        target_price = self.calculator.calculate_profit_target(fill_price, side)
        
        self.logger.info(f"🎯 Colocando ordem oposta em ${target_price}")
        self._place_single_order(target_price, opposite_side)
    
    def cancel_all_orders(self) -> None:
        """Cancela todas as ordens ativas"""
        
        self.logger.info(f"🚫 Cancelando {len(self.placed_orders)} ordens")
        
        for price, order_id in list(self.placed_orders.items()):
            try:
                # Tentar cancelar na API e garantir remoção do estado local
                try:
                    result = self.auth.cancel_order(str(order_id))
                    if result and isinstance(result, dict) and result.get('success'):
                        self.logger.debug(f"✅ Ordem cancelada na API: {order_id}")
                    else:
                        self.logger.warning(f"⚠️ API cancel returned for {order_id}: {result}")
                except Exception as e:
                    self.logger.warning(f"⚠️ Falha ao cancelar na API {order_id}: {e}")
                
                # Remover do position manager (caso esteja registrado)
                removed = self.position_mgr.remove_order(str(order_id))
                if removed:
                    self.logger.debug(f"🔄 Ordem removida do position_mgr: {order_id}")
                else:
                    self.logger.debug(f"ℹ️ Ordem {order_id} não estava no position_mgr")
                
            except Exception as e:
                self.logger.error(f"Erro ao cancelar ordem {order_id}: {e}")
        
        self.placed_orders.clear()
    
    def pause_grid(self) -> None:
        """Pausa o grid (cancela todas as ordens)"""
        
        self.logger.warning("⏸️ Pausando grid")
        self.cancel_all_orders()
        self.grid_active = False
    
    def resume_grid(self, current_price: float) -> None:
        """Resume o grid"""
        
        self.logger.info("▶️ Resumindo grid")
        self.initialize_grid(current_price)
    
    def get_grid_status(self) -> Dict:
        """Retorna status atual do grid"""
        
        return {
            'active': self.grid_active,
            'center_price': self.grid_center,
            'strategy_type': self.strategy_type,
            'buy_levels': len(self.active_grid.get('buy_levels', [])),
            'sell_levels': len(self.active_grid.get('sell_levels', [])),
            'active_orders': len(self.placed_orders),
            'placed_orders': self.placed_orders
        }
    
    def _is_closing_trade(self, side: str, symbol: str) -> bool:
        """Verifica se é um trade de fechamento (simplificado)"""
        # Por enquanto, considerar que sell após buy é fechamento
        # Em implementação real, verificar posição atual
        return side == 'sell'

    def _get_entry_data(self, symbol: str, side: str) -> Optional[Dict]:
        """Obtém dados de entrada do trade (simplificado)"""
        # Em implementação real, buscar da base de dados de trades abertos
        # Por enquanto, simular
        return {
            'side': 'buy' if side == 'sell' else 'sell',
            'price': 50000.0,  # Preço de exemplo - implementar busca real
            'time': datetime.now() - timedelta(minutes=30)  # Tempo de exemplo
        }

    def _calculate_trade_pnl(self, entry_data: Dict, exit_price: float, quantity: float, exit_side: str) -> float:
        """Calcula PNL do trade"""
        entry_price = entry_data['price']
        
        if exit_side == 'sell':  # Fechando posição long
            return (exit_price - entry_price) * quantity
        else:  # Fechando posição short
            return (entry_price - exit_price) * quantity

    def _get_grid_level(self, price: float) -> int:
        """Determina nível do grid baseado no preço"""
        # Implementação simplificada
        return 1

    def get_performance_metrics(self) -> Dict:
        """Retorna métricas de performance"""
        # Para status regular, usar métricas básicas
        metrics = self.performance_tracker.calculate_metrics(include_advanced=False)
        
        # Adicionar métricas específicas do grid
        volatility_status = self.calculator.get_volatility_status()
        metrics.update(volatility_status)
        
        return metrics

    def print_performance_summary(self) -> None:
        """Imprime resumo de performance"""
        # Para relatório completo, usar métricas avançadas
        summary = self.performance_tracker.get_performance_summary(include_advanced=True)
        
        # Adicionar informações específicas do grid
        volatility_status = self.calculator.get_volatility_status()
        
        grid_info = f"""
    🔧 GRID STATUS
    Current Spacing: {volatility_status.get('current_spacing', 0):.3f}%
    Volatility: {volatility_status.get('current_volatility', 0):.4f}
    Adaptive Mode: {'ON' if volatility_status.get('adaptive_mode') else 'OFF'}
    """
        
        self.logger.info(summary + grid_info)

    def get_grid_status_detailed(self) -> Dict:
        """Retorna status detalhado do grid incluindo limitações"""
        
        try:
            # Status básico
            status = self.get_grid_status()
            
            # Verificar se está no limite
            position_status = self.position_mgr.get_status_summary()
            orders_count = position_status.get('open_orders_count', 0)
            max_orders = position_status.get('max_orders', 20)
            
            # Calcular % de uso
            usage_percent = (orders_count / max_orders) * 100 if max_orders > 0 else 0
            
            # Adicionar informações extras
            status.update({
                'orders_usage_percent': usage_percent,
                'is_at_limit': usage_percent >= 95,
                'can_create_new_orders': usage_percent < 90,
                'pending_executions': orders_count > 0,
                'grid_health': 'healthy' if usage_percent < 80 else 'near_limit' if usage_percent < 95 else 'at_limit'
            })
            
            return status
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao obter status detalhado: {e}")
            return self.get_grid_status()  # Fallback para status básico
    
    def shift_grid(self, new_center_price: float) -> None:
        """Desloca o grid para um novo preço central (Market Making)"""
        
        try:
            self.logger.info(f"🔄 Iniciando deslocamento do grid para ${new_center_price}")
            
            # 1. Cancelar ordens existentes
            cancelled_orders = 0
            for price, order_id in list(self.placed_orders.items()):
                try:
                    result = self.auth.cancel_order(str(order_id))
                    if result and isinstance(result, dict) and result.get('success'):
                        cancelled_orders += 1
                        self.logger.debug(f"✅ Ordem cancelada: {order_id} @ ${price}")
                    else:
                        self.logger.warning(f"⚠️ Falha ao cancelar ordem {order_id} (API retornou: {result})")
                except Exception as e:
                    self.logger.error(f"❌ Erro ao cancelar ordem {order_id}: {e}")
                
                # Garantir remoção do estado local também
                try:
                    removed = self.position_mgr.remove_order(str(order_id))
                    if removed:
                        self.logger.debug(f"🔄 Removida do position_mgr: {order_id}")
                except Exception as e:
                    self.logger.debug(f"⚠️ Falha ao remover do position_mgr {order_id}: {e}")
                
                time.sleep(0.2)  # Delay entre cancelamentos
            
            self.logger.info(f"🚫 {cancelled_orders} ordens canceladas")
            
            # 2. Limpar tracking de ordens
            self.placed_orders.clear()
            
            # 3. Aguardar processamento dos cancelamentos
            time.sleep(1.0)
            
            # 4. Recalcular grid com novo centro
            self.active_grid = self.calculator.calculate_grid_levels(new_center_price)
            self.grid_center = new_center_price
            
            # 5. Colocar novas ordens
            success = self._place_grid_orders()
            
            if success:
                self.logger.info(f"✅ Grid deslocado com sucesso para ${new_center_price}")
                self.logger.info(f"📊 Novas ordens: {len(self.placed_orders)} total")
            else:
                self.logger.error(f"❌ Falha ao colocar ordens do novo grid")
                
        except Exception as e:
            self.logger.error(f"❌ Erro ao deslocar grid: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())

    def _price_key(self, price: float) -> float:
        """Retorna preço normalizado (usado como chave em placed_orders)"""
        try:
            return float(self.calculator.round_price(price))
        except Exception:
            return float(round(price, 8))