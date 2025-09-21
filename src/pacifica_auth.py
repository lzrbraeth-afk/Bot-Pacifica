"""
Pacifica API - Sistema de Autenticação com Logging Completo
Baseado no método funcional do create_order.py
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
# FUNÇÕES AUXILIARES DE ASSINATURA (baseadas em create_order.py)
# ============================================================================

def sort_json_keys(value):
    """Ordena as chaves JSON recursivamente"""
    if isinstance(value, dict):
        sorted_dict = {}
        for key in sorted(value.keys()):
            sorted_dict[key] = sort_json_keys(value[key])
        return sorted_dict
    elif isinstance(value, list):
        return [sort_json_keys(item) for item in value]
    else:
        return value

def prepare_message(header, payload):
    """Prepara a mensagem para assinatura"""
    if (
        "type" not in header
        or "timestamp" not in header
        or "expiry_window" not in header
    ):
        raise ValueError("Header must have type, timestamp, and expiry_window")

    data = {
        **header,
        "data": payload,
    }

    message = sort_json_keys(data)
    # Specifying the separators is important because the JSON message is expected to be compact.
    message = json.dumps(message, separators=(",", ":"))
    return message

def sign_message(header, payload, keypair):
    """Assina a mensagem usando o método correto do Solders"""
    message = prepare_message(header, payload)
    message_bytes = message.encode("utf-8")
    signature = keypair.sign_message(message_bytes)
    return (message, base58.b58encode(bytes(signature)).decode("ascii"))

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
    file_handler.setLevel(logging.DEBUG)  # sempre detalhado no arquivo
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)  # nível do .env no console
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
    logger.info("Sistema de logging inicializado")
    logger.info(f"Arquivo de log principal: {log_file}")
    logger.info(f"Arquivo de debug: {debug_file}")
    logger.info(f"Nível de log: {env_level}")
    logger.info("=" * 80)

    return logger

# ============================================================================
# CLASSE DE AUTENTICAÇÃO
# ============================================================================

class PacificaAuth:
    def __init__(self):
        self.logger = setup_logging()
        self.debug_logger = logging.getLogger('PacificaBot.Debug')

        self.base_url = os.getenv('API_ADDRESS', 'https://api.pacifica.fi/api/v1')
        self.ws_url = os.getenv('WS_BASE_URL', 'wss://ws.pacifica.fi/ws')

        self.wallet_address = os.getenv('WALLET_ADDRESS')    
        self.logger.info(f"✅ Wallet address: {self.wallet_address}")

        # Usar PRIVATE_KEY como no create_order.py que funciona
        self.private_key_hex = os.getenv('PRIVATE_KEY')
        if not self.private_key_hex:
            raise ValueError("PRIVATE_KEY é obrigatória no .env")

        # Configurar keypair usando método do create_order.py
        try:
            key_bytes = bytes.fromhex(self.private_key_hex)
            self.keypair = Keypair.from_bytes(key_bytes)
            self.public_key = str(self.keypair.pubkey())
            self.wallet_address = self.public_key  # Para compatibilidade
            self.logger.info(f"✅ Keypair configurado com sucesso: {self.public_key}")
        except Exception as e:
            self.logger.error(f"❌ Erro ao configurar keypair: {e}")
            raise

        self.logger.info("✅ PacificaAuth inicializado com sucesso")

    def create_order(self, symbol: str, side: str, amount: str, price: str, 
                     order_type: str = "GTC", reduce_only: bool = False) -> Optional[Dict]:
        """Cria uma ordem usando o método correto baseado em create_order.py"""
        
        # Scaffold the signature header
        timestamp = int(time.time() * 1_000)
        
        signature_header = {
            "timestamp": timestamp,
            "expiry_window": 5_000,
            "type": "create_order",
        }

        # Construct the signature payload
        signature_payload = {
            "symbol": symbol,
            "price": str(price),
            "reduce_only": reduce_only,
            "amount": str(amount),
            "side": side,  # "bid" ou "ask"
            "tif": order_type,  # "GTC", "IOC", etc
            "client_order_id": str(uuid.uuid4()),
        }

        # Use the helper function to sign the message
        message, signature = sign_message(signature_header, signature_payload, self.keypair)

        # Construct the request reusing the payload and constructing common request fields
        request_header = {
            "account": self.public_key,
            "signature": signature,
            "timestamp": signature_header["timestamp"],
            "expiry_window": signature_header["expiry_window"],
        }

        # Send the request
        url = f"{self.base_url}/orders/create"
        headers = {"Content-Type": "application/json"}

        request_data = {
            **request_header,
            **signature_payload,
        }

        self.logger.info(f"🔄 Criando ordem {side} {amount} {symbol} @ {price}")
        self.debug_logger.debug(f"Request data: {json.dumps(request_data, indent=2)}")
        self.debug_logger.debug(f"Message: {message}")
        self.debug_logger.debug(f"Signature: {signature}")

        try:
            response = requests.post(url, json=request_data, headers=headers, timeout=10)
            self.logger.info(f"📥 POST {url} -> {response.status_code}")
            self.debug_logger.debug(f"Response: {response.text}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    self.logger.info("✅ Ordem criada com sucesso!")
                    self.logger.info(json.dumps(data, indent=2))
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

    def test_connection(self) -> bool:
        """Testa a conexão usando get_funding_history (endpoint que sabemos que funciona)"""
        try:
            self.logger.info("🔐 Testando conexão com API...")
            
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
        """Busca histórico de funding rate"""
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
        """Busca preços atuais usando endpoint oficial da documentação"""
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

    def get_account_info(self) -> Optional[Dict]:
        """Busca informações da conta (saldo, margem, etc)"""
        url = f"{self.base_url}/account"
        params = {'account': self.public_key}  # usar o public_key da wallet
        
        try:
            response = requests.get(url, params=params, timeout=10)
            self.logger.info(f"💰 GET /account -> {response.status_code}")
            self.debug_logger.debug(f"Response: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                self.logger.info("✅ Informações da conta obtidas!")
                return data
            else:
                self.logger.error(f"❌ Erro ao buscar conta - Status: {response.status_code}")
                self.logger.error(f"Response: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"❌ Erro ao buscar conta: {e}")
            return None

    def get_symbol_info(self, symbol: str = None) -> Optional[Dict]:
        """Busca informações específicas de um símbolo"""
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

    def get_open_orders(self, symbol: str = None) -> Optional[List]:
        """Busca ordens abertas da conta"""
        
        account = os.getenv('WALLET_ADDRESS')
        
        # Montar URL completa manualmente
        url = f"{self.base_url}/orders?account={account}"
        
        self.logger.debug(f"🔍 Buscando ordens abertas para account: {account}")
        
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
                
                self.logger.info(f"✅ {len(orders)} ordens abertas encontradas (TOTAL)")

                symbols_count = {}
                for order in orders:
                    sym = order.get('symbol', 'N/A')
                    symbols_count[sym] = symbols_count.get(sym, 0) + 1
            
                if symbols_count:
                    self.logger.debug(f"📊 Ordens por símbolo: {symbols_count}")
                return orders
            else:
                self.logger.error(f"Erro {response.status_code}: {response.text[:200]}")
                return None
        
        except Exception as e:
            self.logger.error(f"Erro: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancela uma ordem específica"""
        url = f"{self.base_url}/orders/cancel"
        
        timestamp = int(time.time() * 1_000)
        
        signature_header = {
            "timestamp": timestamp,
            "expiry_window": 5_000,
            "type": "cancel_order",
        }
        
        signature_payload = {
            "order_id": str(order_id),
        }
        
        message, signature = sign_message(signature_header, signature_payload, self.keypair)
        
        request_data = {
            "account": self.public_key,
            "signature": signature,
            "timestamp": timestamp,
            "expiry_window": 5_000,
            "order_id": str(order_id),
        }
        
        try:
            response = requests.post(url, json=request_data, timeout=10)
            self.logger.info(f"🚫 Cancel order {order_id} -> {response.status_code}")
            
            if response.status_code == 200:
                self.logger.info(f"✅ Ordem {order_id} cancelada")
                return True
            else:
                self.logger.error(f"Falha ao cancelar: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Erro ao cancelar: {e}")
            return False
    
    def get_market_info(self, symbol: str = "BTC") -> Optional[Dict]:
        """Busca informações do mercado usando endpoint oficial da documentação"""
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
# FUNÇÃO PRINCIPAL DE TESTE
# ============================================================================

def main():
    print("=" * 80)
    print("🤖 PACIFICA API - TESTE DE AUTENTICAÇÃO")
    print("=" * 80)

    try:
        # Inicializar autenticação
        auth = PacificaAuth()
        
        print("\n🔐 Testando conexão...")
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
                
        else:
            print("❌ Falha no teste de conexão")

    except Exception as e:
        print(f"❌ Erro na inicialização: {e}")

    print("\n" + "=" * 80)
    print("🏁 Teste concluído!")
    print("=" * 80)

if __name__ == "__main__":
    main()