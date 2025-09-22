"""
Pacifica API - Sistema de Autenticação com AGENT WALLET (SEM PRIVATE KEY)
Baseado no método funcional do test_agent_wallet_withoutkey.py
🔒 SEGURANÇA: Não requer mais private key da wallet principal
"""

import os
import time
import json
import base58
import requests
import logging
import traceback
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from solders.keypair import Keypair

# Carregar variáveis de ambiente
load_dotenv()

# ============================================================================
# FUNÇÕES AUXILIARES DE ASSINATURA PARA AGENT WALLET
# ============================================================================

def sort_json_keys(value):
    """Ordena as chaves JSON recursivamente"""
    if isinstance(value, dict):
        return {k: sort_json_keys(value[k]) for k in sorted(value.keys())}
    elif isinstance(value, list):
        return [sort_json_keys(item) for item in value]
    else:
        return value

def prepare_message(header, payload):
    """Prepara a mensagem para assinatura"""
    if not all(k in header for k in ("type", "timestamp", "expiry_window")):
        raise ValueError("Header must have type, timestamp, and expiry_window")
    data = {**header, "data": payload}
    sorted_data = sort_json_keys(data)
    return json.dumps(sorted_data, separators=(",", ":"))

def sign_message(message: str, keypair: Keypair) -> str:
    """Assina a mensagem usando a chave privada do agent"""
    signature = keypair.sign_message(message.encode("utf-8"))
    return base58.b58encode(bytes(signature)).decode("utf-8")

# ============================================================================
# CONFIGURAÇÃO DO SISTEMA DE LOGGING
# ============================================================================

def setup_logging() -> logging.Logger:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"pacifica_bot_{timestamp}.log"
    debug_file = log_dir / f"pacifica_debug_{timestamp}.log"

    # Nível vem do .env (default = INFO)
    env_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, env_level, logging.INFO)

    log_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logger = logging.getLogger('PacificaBot')
    logger.setLevel(log_level)
    logger.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    simple_format = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(simple_format)
    logger.addHandler(console_handler)

    debug_handler = logging.FileHandler(debug_file, encoding='utf-8')
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(log_format)

    debug_logger = logging.getLogger('PacificaBot.Debug')
    debug_logger.setLevel(logging.DEBUG)
    debug_logger.handlers.clear()
    debug_logger.addHandler(debug_handler)
    debug_logger.propagate = False

    logger.info("=" * 80)
    logger.info("🔒 Sistema de Agent Wallet inicializado (SEM PRIVATE KEY)")
    logger.info(f"Arquivo de log principal: {log_file}")
    logger.info(f"Arquivo de debug: {debug_file}")
    logger.info(f"Nível de log: {env_level}")
    logger.info("=" * 80)

    return logger

# ============================================================================
# CLASSE DE AUTENTICAÇÃO COM AGENT WALLET
# ============================================================================

class PacificaAuth:
    def __init__(self):
        self.logger = setup_logging()
        self.debug_logger = logging.getLogger('PacificaBot.Debug')

        self.base_url = os.getenv('API_ADDRESS', 'https://api.pacifica.fi/api/v1')
        self.ws_url = os.getenv('WS_BASE_URL', 'wss://ws.pacifica.fi/ws')

        # 🔒 CONFIGURAR AGENT WALLET (para assinatura)
        self.setup_agent_wallet()
        
        # 🔒 CONFIGURAR MAIN WALLET (apenas public key)
        self.setup_main_wallet()

        self.logger.info("✅ PacificaAuth inicializado com Agent Wallet (SEGURO)")

    def setup_agent_wallet(self):
        """Configura Agent Wallet para assinatura (SEM expor private key principal)"""
        key_b58 = os.getenv("AGENT_PRIVATE_KEY_B58") or os.getenv("AGENT_PRIVATE_KEY")
        if not key_b58:
            raise ValueError("🔑 Defina AGENT_PRIVATE_KEY_B58 no .env")
        
        try:
            raw = base58.b58decode(key_b58)
            if len(raw) == 32:
                self.agent_keypair = Keypair.from_seed(raw)
            elif len(raw) == 64:
                self.agent_keypair = Keypair.from_bytes(raw)
            else:
                raise ValueError(f"❌ Tamanho inválido da chave agent (len={len(raw)})")
            
            self.agent_public_key = str(self.agent_keypair.pubkey())
            self.logger.info(f"✅ Agent Wallet configurado: {self.agent_public_key}")
            
        except Exception as e:
            self.logger.error(f"❌ Erro ao configurar Agent Wallet: {e}")
            raise

    def setup_main_wallet(self):
        """Configura Main Wallet (apenas public key - SEM private key)"""
        self.main_public_key = os.getenv("MAIN_PUBLIC_KEY")
        if not self.main_public_key:
            raise ValueError("🔑 Defina MAIN_PUBLIC_KEY no .env")
        
        # Para compatibilidade com código existente
        self.public_key = self.main_public_key
        self.wallet_address = self.main_public_key
        
        self.logger.info(f"✅ Main Wallet (public): {self.main_public_key}")

    def create_order(self, symbol: str, side: str, amount: str, price: str, 
                     order_type: str = "GTC", reduce_only: bool = False,
                     take_profit: Dict = None, stop_loss: Dict = None) -> Optional[Dict]:
        """
        Cria uma ordem com TP/SL opcionais usando Agent Wallet
        🔒 SEGURO: Não requer private key da wallet principal
        """
        
        timestamp = int(time.time() * 1_000)
        
        signature_header = {
            "timestamp": timestamp,
            "expiry_window": 30000,
            "type": "create_order",
        }

        # Construct the signature payload (base)
        signature_payload = {
            "symbol": symbol,
            "price": str(price),
            "reduce_only": reduce_only,
            "amount": str(amount),
            "side": side,  # "bid" ou "ask"
            "tif": order_type,  # "GTC", "IOC", etc
            "client_order_id": str(uuid.uuid4()),
        }
        
        # 🆕 ADICIONAR TP/SL SE FORNECIDOS
        if take_profit:
            signature_payload["take_profit"] = {
                "stop_price": str(take_profit["stop_price"]),
                "limit_price": str(take_profit["limit_price"]),
                "client_order_id": str(uuid.uuid4())
            }
            self.logger.info(f"🎯 Take Profit: stop=${take_profit['stop_price']}, limit=${take_profit['limit_price']}")
        
        if stop_loss:
            signature_payload["stop_loss"] = {
                "stop_price": str(stop_loss["stop_price"]),
                "limit_price": str(stop_loss["limit_price"]),
                "client_order_id": str(uuid.uuid4())
            }
            self.logger.info(f"🛡️ Stop Loss: stop=${stop_loss['stop_price']}, limit=${stop_loss['limit_price']}")

        # 🔒 ASSINATURA COM AGENT WALLET
        message = prepare_message(signature_header, signature_payload)
        signature = sign_message(message, self.agent_keypair)

        # 🔒 REQUEST COM AGENT WALLET
        request_data = {
            "account": self.main_public_key,           # 🔒 Main wallet (public)
            "agent_wallet": self.agent_public_key,    # 🔒 Agent wallet (public)
            "signature": signature,                   # 🔒 Assinado pelo agent
            "timestamp": signature_header["timestamp"],
            "expiry_window": signature_header["expiry_window"],
            **signature_payload,
        }

        order_desc = f"{side} {amount} {symbol} @ {price}"
        if take_profit or stop_loss:
            order_desc += " com TP/SL"
            
        self.logger.info(f"📄 Criando ordem: {order_desc}")
        self.debug_logger.debug(f"Request data: {json.dumps(request_data, indent=2)}")
        self.debug_logger.debug(f"Message: {message}")
        self.debug_logger.debug(f"Signature: {signature}")

        try:
            url = f"{self.base_url}/orders/create"
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(url, json=request_data, headers=headers, timeout=15)
            self.logger.info(f"🔥 POST {url} -> {response.status_code}")
            self.debug_logger.debug(f"Response: {response.text}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    self.logger.info("✅ Ordem criada com sucesso!")
                    
                    # Log detalhado do resultado
                    if 'data' in data:
                        order_data = data['data']
                        main_order_id = order_data.get('order_id', 'N/A')
                        self.logger.info(f"📋 Ordem principal ID: {main_order_id}")
                        
                        # Log IDs de TP/SL se criados
                        if 'take_profit_order_id' in order_data:
                            tp_id = order_data['take_profit_order_id']
                            self.logger.info(f"🎯 Take Profit ID: {tp_id}")
                            
                        if 'stop_loss_order_id' in order_data:
                            sl_id = order_data['stop_loss_order_id']
                            self.logger.info(f"🛡️ Stop Loss ID: {sl_id}")
                    
                    self.debug_logger.debug(json.dumps(data, indent=2))
                    return data
                except json.JSONDecodeError:
                    self.logger.error("❌ Falha ao decodificar JSON da resposta")
            else:
                self.logger.error(f"❌ Falha ao criar ordem - Status: {response.status_code}")
                self.logger.error(f"Response: {response.text}")

        except Exception as e:
            self.logger.error(f"❌ Erro na requisição: {e}")
            self.debug_logger.error(traceback.format_exc())

        return None

    def create_order_with_auto_tpsl(self, symbol: str, side: str, amount: str, price: str,
                                   tp_percent: float = None, sl_percent: float = None,
                                   order_type: str = "GTC", reduce_only: bool = False) -> Optional[Dict]:
        """
        Cria ordem com TP/SL calculados automaticamente usando Agent Wallet
        🔒 SEGURO: Não requer private key da wallet principal
        """
        
        entry_price = float(price)
        take_profit = None
        stop_loss = None
        
        # 🆕 OBTER TICK_SIZE DO SÍMBOLO
        tick_size = self._get_tick_size(symbol)
        
        if tp_percent:
            if side == 'bid':  # Comprando - TP acima do preço
                tp_stop = entry_price * (1 + tp_percent / 100)
                tp_limit = tp_stop * 0.999
            else:  # Vendendo - TP abaixo do preço
                tp_stop = entry_price * (1 - tp_percent / 100)
                tp_limit = tp_stop * 1.001
            
            # 🔧 ARREDONDAR PARA TICK_SIZE
            tp_stop_rounded = self._round_to_tick_size(tp_stop, tick_size)
            tp_limit_rounded = self._round_to_tick_size(tp_limit, tick_size)
                
            take_profit = {
                "stop_price": f"{tp_stop_rounded}",
                "limit_price": f"{tp_limit_rounded}"
            }
            
            self.logger.debug(f"🎯 TP calculado: {tp_stop:.6f} -> {tp_stop_rounded} (tick_size: {tick_size})")
        
        if sl_percent:
            if side == 'bid':  # Comprando - SL abaixo do preço
                sl_stop = entry_price * (1 - sl_percent / 100)
                sl_limit = sl_stop * 0.999
            else:  # Vendendo - SL acima do preço
                sl_stop = entry_price * (1 + sl_percent / 100)
                sl_limit = sl_stop * 1.001
            
            # 🔧 ARREDONDAR PARA TICK_SIZE
            sl_stop_rounded = self._round_to_tick_size(sl_stop, tick_size)
            sl_limit_rounded = self._round_to_tick_size(sl_limit, tick_size)
                
            stop_loss = {
                "stop_price": f"{sl_stop_rounded}",
                "limit_price": f"{sl_limit_rounded}"
            }
            
            self.logger.debug(f"🛡️ SL calculado: {sl_stop:.6f} -> {sl_stop_rounded} (tick_size: {tick_size})")
        
        return self.create_order(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            order_type=order_type,
            reduce_only=reduce_only,
            take_profit=take_profit,
            stop_loss=stop_loss
        )

    def cancel_order(self, order_id: str, symbol: str = None) -> bool:
        """
        Cancela uma ordem específica usando Agent Wallet
        🔒 SEGURO: Não requer private key da wallet principal
        """
        
        timestamp = int(time.time() * 1_000)
        
        signature_header = {
            "timestamp": timestamp,
            "expiry_window": 30000,
            "type": "cancel_order",
        }
        
        signature_payload = {
            "order_id": str(order_id),
        }
        
        # Adicionar símbolo se fornecido (algumas APIs exigem)
        if symbol:
            signature_payload["symbol"] = symbol
        
        # 🔒 ASSINATURA COM AGENT WALLET
        message = prepare_message(signature_header, signature_payload)
        signature = sign_message(message, self.agent_keypair)
        
        # 🔒 REQUEST COM AGENT WALLET
        request_data = {
            "account": self.main_public_key,           # 🔒 Main wallet (public)
            "agent_wallet": self.agent_public_key,    # 🔒 Agent wallet (public)
            "signature": signature,                   # 🔒 Assinado pelo agent
            "timestamp": timestamp,
            "expiry_window": 30000,
            **signature_payload,
        }
        
        try:
            url = f"{self.base_url}/orders/cancel"
            response = requests.post(url, json=request_data, timeout=10)
            self.logger.info(f"🚫 Cancel order {order_id} -> {response.status_code}")
            
            if response.status_code == 200:
                self.logger.info(f"✅ Ordem {order_id} cancelada")
                return True
            else:
                self.logger.error(f"❌ Falha ao cancelar: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"❌ Erro ao cancelar: {e}")
            return False

    def get_account_info(self) -> Optional[Dict]:
        """
        Busca informações da conta usando Agent Wallet
        🔒 SEGURO: Se precisar de autenticação, usa Agent Wallet
        """
        
        # Primeiro tentar sem autenticação (endpoint público)
        url = f"{self.base_url}/account"
        params = {'account': self.main_public_key}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            self.logger.info(f"💰 GET /account -> {response.status_code}")
            self.debug_logger.debug(f"Response: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                self.logger.info("✅ Informações da conta obtidas!")
                return data
            elif response.status_code == 401:
                # Se precisar de autenticação, usar Agent Wallet
                self.logger.info("🔒 Endpoint requer autenticação - usando Agent Wallet")
                return self._get_account_info_authenticated()
            else:
                self.logger.error(f"❌ Erro ao buscar conta - Status: {response.status_code}")
                self.logger.error(f"Response: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"❌ Erro ao buscar conta: {e}")
            return None

    def _get_account_info_authenticated(self) -> Optional[Dict]:
        """
        Busca informações da conta com autenticação Agent Wallet
        """
        
        timestamp = int(time.time() * 1_000)
        
        signature_header = {
            "timestamp": timestamp,
            "expiry_window": 30000,
            "type": "get_account",
        }
        
        signature_payload = {
            "account": self.main_public_key,
        }
        
        # 🔒 ASSINATURA COM AGENT WALLET
        message = prepare_message(signature_header, signature_payload)
        signature = sign_message(message, self.agent_keypair)
        
        # 🔒 REQUEST COM AGENT WALLET
        request_data = {
            "account": self.main_public_key,
            "agent_wallet": self.agent_public_key,
            "signature": signature,
            "timestamp": timestamp,
            "expiry_window": 30000,
        }
        
        try:
            url = f"{self.base_url}/account"
            response = requests.post(url, json=request_data, timeout=10)
            self.logger.info(f"💰 POST /account (auth) -> {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                self.logger.info("✅ Informações da conta obtidas (autenticado)!")
                return data
            else:
                self.logger.error(f"❌ Erro na busca autenticada: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"❌ Erro na requisição autenticada: {e}")
            return None

    def get_open_orders(self, symbol: str = None) -> Optional[List]:
        """
        Busca ordens abertas da conta usando Agent Wallet se necessário
        🔒 SEGURO: Tenta público primeiro, depois Agent Wallet se precisar
        """
        
        # Primeiro tentar sem autenticação
        url = f"{self.base_url}/orders?account={self.main_public_key}"
        
        self.logger.debug(f"🔍 Buscando ordens abertas para account: {self.main_public_key}")
        
        try:
            response = requests.get(url, timeout=10)
            self.logger.info(f"📋 GET {url} -> {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Processar resposta
                if isinstance(data, dict) and 'data' in data:
                    orders = data.get('data', [])
                elif isinstance(data, list):
                    orders = data
                else:
                    orders = []
                
                self.logger.info(f"✅ {len(orders)} ordens abertas encontradas")
                
                # Filtrar por símbolo se especificado
                if symbol and orders:
                    filtered_orders = [o for o in orders if o.get('symbol') == symbol]
                    self.logger.info(f"📊 {len(filtered_orders)} ordens para {symbol}")
                    return filtered_orders
                
                return orders
                
            elif response.status_code == 401:
                # Se precisar de autenticação, usar Agent Wallet
                self.logger.info("🔒 Endpoint requer autenticação - usando Agent Wallet")
                return self._get_open_orders_authenticated(symbol)
            else:
                self.logger.error(f"❌ Erro {response.status_code}: {response.text[:200]}")
                return None
        
        except Exception as e:
            self.logger.error(f"❌ Erro: {e}")
            return None

    def _get_open_orders_authenticated(self, symbol: str = None) -> Optional[List]:
        """
        Busca ordens abertas com autenticação Agent Wallet
        """
        
        timestamp = int(time.time() * 1_000)
        
        signature_header = {
            "timestamp": timestamp,
            "expiry_window": 30000,
            "type": "get_orders",
        }
        
        signature_payload = {
            "account": self.main_public_key,
        }
        
        if symbol:
            signature_payload["symbol"] = symbol
        
        # 🔒 ASSINATURA COM AGENT WALLET
        message = prepare_message(signature_header, signature_payload)
        signature = sign_message(message, self.agent_keypair)
        
        # 🔒 REQUEST COM AGENT WALLET
        request_data = {
            "account": self.main_public_key,
            "agent_wallet": self.agent_public_key,
            "signature": signature,
            "timestamp": timestamp,
            "expiry_window": 30000,
        }
        
        try:
            url = f"{self.base_url}/orders"
            response = requests.post(url, json=request_data, timeout=10)
            self.logger.info(f"📋 POST /orders (auth) -> {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                orders = data.get('data', []) if isinstance(data, dict) else data
                self.logger.info(f"✅ {len(orders)} ordens obtidas (autenticado)")
                return orders
            else:
                self.logger.error(f"❌ Erro na busca autenticada: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"❌ Erro na requisição autenticada: {e}")
            return None

    # ============================================================================
    # FUNÇÕES PÚBLICAS (NÃO PRECISAM DE AUTENTICAÇÃO)
    # ============================================================================

    def test_connection(self) -> bool:
        """Testa a conexão usando get_funding_history (endpoint público)"""
        try:
            self.logger.info("🔍 Testando conexão com API...")
            
            # Usar endpoint público que funciona
            result = self.get_funding_history("BTC")
            
            if result:
                self.logger.info("✅ Conexão com API funcionando!")
                return True
            else:
                self.logger.error("❌ Falha no teste de conexão")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Erro no teste de conexão: {e}")
            return False

    def get_funding_history(self, symbol: str = "BTC", limit: int = 10, offset: int = 0) -> Optional[Dict]:
        """Busca histórico de funding rate (endpoint público)"""
        url = f"{self.base_url}/funding_rate/history"
        params = {'symbol': symbol, 'limit': limit, 'offset': offset}
        try:
            response = requests.get(url, params=params, timeout=10)
            self.logger.info(f"📊 GET /funding_rate/history -> {response.status_code}")
            self.debug_logger.debug(response.text[:500])
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            self.logger.error(f"❌ Erro ao buscar funding history: {e}")
            return None

    def get_prices(self) -> Optional[Dict]:
        """Busca preços atuais (endpoint público)"""
        url = f"{self.base_url}/info/prices"
        try:
            response = requests.get(url, timeout=10)
            self.logger.info(f"📈 GET /info/prices -> {response.status_code}")
            self.debug_logger.debug(f"Response: {response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                self.logger.info("✅ Preços obtidos com sucesso!")
                return data
            else:
                self.logger.error(f"❌ Erro ao buscar preços - Status: {response.status_code}")
                self.logger.error(f"Response: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"❌ Erro na requisição de preços: {e}")
            return None

    def get_symbol_info(self, symbol: str = None) -> Optional[Dict]:
        """Busca informações específicas de um símbolo (endpoint público)"""
        url = f"{self.base_url}/info"
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # API retorna {"success": true, "data": [...]}
                if isinstance(data, dict) and 'data' in data:
                    items = data['data']
                elif isinstance(data, list):
                    items = data
                else:
                    self.logger.error(f"Formato inesperado da API: {type(data)}")
                    return None
                
                if symbol and isinstance(items, list):
                    for item in items:
                        if item.get('symbol') == symbol:
                            tick = item.get('tick_size')
                            lot = item.get('lot_size')
                            self.logger.info(f"✅ {symbol} encontrado: tick_size={tick}, lot_size={lot}")
                            return item
                    
                    # Se não encontrou
                    available = [x.get('symbol') for x in items[:5]]
                    self.logger.error(f"❌ Símbolo '{symbol}' não encontrado. Primeiros: {available}")
                    return None
                
                return items if isinstance(items, list) else None
                
        except Exception as e:
            self.logger.error(f"Erro ao buscar symbol info: {e}")
            return None

    def get_market_info(self, symbol: str = "BTC") -> Optional[Dict]:
        """Busca informações do mercado (endpoint público)"""
        url = f"{self.base_url}/info"
        try:
            response = requests.get(url, timeout=10)
            self.logger.info(f"📈 GET /info -> {response.status_code}")
            self.debug_logger.debug(f"Response: {response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                self.logger.info("✅ Informações do mercado obtidas com sucesso!")
                
                # Se um símbolo específico foi solicitado, filtrar apenas esse símbolo
                if symbol and isinstance(data, list):
                    for item in data:
                        if item.get('symbol') == symbol:
                            return item
                    self.logger.warning(f"❌ Símbolo {symbol} não encontrado nos dados do mercado")
                    return None
                
                return data
            else:
                self.logger.error(f"❌ Erro ao buscar informações do mercado - Status: {response.status_code}")
                self.logger.error(f"Response: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"❌ Erro na requisição de market info: {e}")
            return None

    # ============================================================================
    # FUNÇÕES AUXILIARES (MANTIDAS DO CÓDIGO ORIGINAL)
    # ============================================================================

    def _get_tick_size(self, symbol: str) -> float:
        """Obtém tick_size específico do símbolo"""
        try:
            info = self.get_symbol_info(symbol)
            if info and 'tick_size' in info:
                tick_size = float(info['tick_size'])
                self.logger.debug(f"🔍 {symbol} tick_size: {tick_size}")
                return tick_size
        except Exception as e:
            self.logger.warning(f"⚠️ Erro ao obter tick_size para {symbol}: {e}")
        
        # Fallback para valores conhecidos
        tick_sizes = {
            'BTC': 0.00001,
            'ETH': 0.0001, 
            'SOL': 0.01,
            'BNB': 0.001,
            'AVAX': 0.001,
            'LTC': 0.001
        }
        fallback = tick_sizes.get(symbol, 0.00001)
        self.logger.warning(f"⚠️ Usando tick_size fallback para {symbol}: {fallback}")
        return fallback

    def _round_to_tick_size(self, price: float, tick_size: float) -> float:
        """
        Arredonda preço para múltiplo válido do tick_size
        🔧 BASEADO NO grid_calculator.py que já funciona
        """
        
        if tick_size >= 1:
            return float(round(price))
        
        # Usar Decimal para evitar erros de precisão
        from decimal import Decimal, ROUND_HALF_UP
        
        price_dec = Decimal(str(price))
        tick_dec = Decimal(str(tick_size))
        
        # Arredondar para múltiplo mais próximo
        multiple = (price_dec / tick_dec).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        result = float(multiple * tick_dec)
        
        # Forçar casas decimais corretas baseado no tick_size
        if tick_size == 0.01:
            return round(result, 2)
        elif tick_size == 0.001:
            return round(result, 3)
        elif tick_size == 0.0001:
            return round(result, 4)
        elif tick_size == 0.00001:
            return round(result, 5)
        else:
            return round(result, 8)  # Máximo de 8 decimais para crypto

    # ============================================================================
    # FUNCIONALIDADES AVANÇADAS (TP/SL PARA POSIÇÕES EXISTENTES)
    # ============================================================================

    def create_position_tp_sl(self, symbol: str, side: str, 
                            take_profit_stop: str, take_profit_limit: str,
                            stop_loss_stop: str, stop_loss_limit: str) -> Optional[Dict]:
        """
        Cria TP/SL para posição existente usando Agent Wallet
        🔒 SEGURO: Não requer private key da wallet principal
        """
        
        self.logger.info(f"🎯 Criando TP/SL para {symbol} {side}")
        self.logger.info(f"   TP: stop={take_profit_stop}, limit={take_profit_limit}")
        self.logger.info(f"   SL: stop={stop_loss_stop}, limit={stop_loss_limit}")
        
        timestamp = int(time.time() * 1_000)
        
        signature_header = {
            "timestamp": timestamp,
            "expiry_window": 30000,
            "type": "create_position_tpsl",
        }

        # Payload conforme documentação oficial
        signature_payload = {
            "symbol": symbol,
            "side": side,
            "take_profit": {
                "stop_price": str(take_profit_stop),
                "limit_price": str(take_profit_limit)
            },
            "stop_loss": {
                "stop_price": str(stop_loss_stop),
                "limit_price": str(stop_loss_limit)
            }
        }

        try:
            # 🔒 ASSINATURA COM AGENT WALLET
            message = prepare_message(signature_header, signature_payload)
            signature = sign_message(message, self.agent_keypair)

            # 🔒 REQUEST COM AGENT WALLET
            request_data = {
                "account": self.main_public_key,
                "agent_wallet": self.agent_public_key,
                "signature": signature,
                "timestamp": timestamp,
                "expiry_window": 30000,
                **signature_payload
            }

            # Enviar para endpoint correto
            url = f"{self.base_url}/positions/tpsl"
            headers = {"Content-Type": "application/json"}

            self.debug_logger.debug(f"TP/SL Request data: {json.dumps(request_data, indent=2)}")
            self.debug_logger.debug(f"TP/SL Message: {message}")
            
            response = requests.post(url, json=request_data, headers=headers, timeout=10)
            
            self.logger.info(f"🔥 POST {url} -> {response.status_code}")
            self.debug_logger.debug(f"TP/SL Response: {response.text}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    self.logger.info("✅ TP/SL criado com sucesso!")
                    self.debug_logger.debug(json.dumps(data, indent=2))
                    return data
                except json.JSONDecodeError:
                    self.logger.error("❌ Falha ao decodificar JSON da resposta TP/SL")
                    return None
            else:
                self.logger.error(f"❌ Falha ao criar TP/SL - Status: {response.status_code}")
                self.logger.error(f"Response: {response.text}")
                return None

        except Exception as e:
            self.logger.error(f"❌ Erro ao criar TP/SL: {e}")
            self.debug_logger.error(traceback.format_exc())
            return None

    def create_position_tp_sl_simple(self, tp_sl_data: Dict) -> Optional[Dict]:
        """
        Método simplificado para compatibilidade com código existente
        🔒 SEGURO: Usa Agent Wallet
        """
        
        symbol = tp_sl_data.get('symbol', 'BTC')
        side = tp_sl_data.get('side', 'bid')
        
        # Extrair preços
        tp_stop = tp_sl_data.get('take_profit_price', '0')
        sl_stop = tp_sl_data.get('stop_loss_price', '0')
        
        # Para simplificar, usar mesmo preço para stop e limit (pode ser ajustado)
        tp_limit = str(float(tp_stop) * 0.999) if side == 'bid' else str(float(tp_stop) * 1.001)
        sl_limit = str(float(sl_stop) * 0.999) if side == 'ask' else str(float(sl_stop) * 1.001)
        
        return self.create_position_tp_sl(
            symbol=symbol,
            side=side,
            take_profit_stop=tp_stop,
            take_profit_limit=tp_limit,
            stop_loss_stop=sl_stop,
            stop_loss_limit=sl_limit
        )

# ============================================================================
# FUNÇÃO PRINCIPAL DE TESTE
# ============================================================================

def main():
    print("=" * 80)
    print("🔒 PACIFICA API - AGENT WALLET (SEM PRIVATE KEY)")
    print("=" * 80)

    try:
        # Inicializar autenticação com Agent Wallet
        auth = PacificaAuth()
        
        print("\n🔍 Testando conexão...")
        if auth.test_connection():
            print("✅ Teste de conexão bem-sucedido!")
            
            print("\n📊 Buscando preços atuais...")
            prices = auth.get_prices()
            if prices:
                print("✅ Preços obtidos com sucesso!")
                print(json.dumps(prices, indent=2)[:500])
            
            print("\n📈 Buscando informações do mercado BTC...")
            market_info = auth.get_market_info("BTC")
            if market_info:
                print("✅ Informações do mercado obtidas!")
                print(json.dumps(market_info, indent=2)[:500])
            
            print("\n💰 Testando informações da conta...")
            account_info = auth.get_account_info()
            if account_info:
                print("✅ Informações da conta obtidas!")
                print(json.dumps(account_info, indent=2)[:500])
            
            print("\n📋 Testando ordens abertas...")
            orders = auth.get_open_orders()
            if orders is not None:
                print(f"✅ {len(orders)} ordens abertas encontradas!")
                
        else:
            print("❌ Falha no teste de conexão")

    except Exception as e:
        print(f"❌ Erro na inicialização: {e}")
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("🔒 Teste Agent Wallet concluído!")
    print("=" * 80)

if __name__ == "__main__":
    main()