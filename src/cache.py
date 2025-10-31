# symbols_cache.py - NOVO ARQUIVO

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class SymbolsCache:
    """Gerenciador de cache de símbolos disponíveis"""
    
    def __init__(self, cache_duration_hours: int = 24):
        self.cache_file = Path('data/symbols_cache.json')
        self.cache_file.parent.mkdir(exist_ok=True)
        self.cache_duration = timedelta(hours=cache_duration_hours)
    
    def get_symbols(self, api_client=None, force_refresh: bool = False) -> List[str]:
        """
        Retorna lista de símbolos disponíveis da corretora Pacifica.fi
        
        PRIORIDADE:
        1. API Pacifica.fi (símbolos reais disponíveis para trade)
        2. Cache válido (< 24h) da última consulta à API
        3. Cache expirado (ainda é melhor que lista padrão)
        4. Lista padrão (fallback final apenas se API nunca funcionou)
        
        Args:
            api_client: Cliente da API Pacifica (obrigatório para busca real)
            force_refresh: Força nova consulta à API ignorando cache
        
        Returns:
            Lista de símbolos disponíveis para trade na Pacifica.fi
        """
        # 1. PRIORIDADE: Buscar da API (símbolos reais da corretora)
        if api_client:
            try:
                if force_refresh:
                    logger.info("🔄 Forçando atualização da API Pacifica.fi")
                else:
                    logger.info("🔍 Buscando símbolos da API Pacifica.fi")
                    
                symbols = self._fetch_from_api(api_client)
                self._save_to_cache(symbols)
                logger.info(f"✅ {len(symbols)} símbolos obtidos da API e salvos no cache")
                return symbols
                
            except Exception as e:
                logger.error(f"❌ Erro ao buscar da API: {e}")
                logger.info("🔄 Tentando usar cache como fallback...")
        
        # 2. Cache válido (dados da API salvos anteriormente)
        if not force_refresh and self._is_cache_valid():
            logger.info("📦 Usando símbolos do cache (dados da API)")
            return self._load_from_cache()
        
        # 3. Cache expirado (melhor que lista padrão)
        if self.cache_file.exists():
            logger.warning("⚠️ Usando cache expirado (última consulta à API)")
            return self._load_from_cache()
        
        # 4. FALLBACK FINAL: Lista padrão (apenas se API nunca funcionou)
        logger.warning("⚠️ API indisponível e sem cache - usando lista padrão")
        logger.warning("💡 Configure credenciais para usar símbolos reais da Pacifica.fi")
        return self._get_default_symbols()
    
    def _fetch_from_api(self, api_client) -> List[str]:
        """
        Busca símbolos disponíveis para trade da API Pacifica.fi
        
        Usa o endpoint GET /api/v1/info que retorna todos os mercados ativos
        """
        try:
            logger.info("📡 Consultando API Pacifica.fi: GET /api/v1/info")
            
            # Busca informações de todos os mercados da Pacifica.fi
            markets_info = api_client.get_symbol_info()
            
            if not markets_info:
                raise Exception("API retornou resposta vazia")
            
            logger.info(f"📊 Resposta da API recebida: {type(markets_info)}")
            
            # Processar resposta da API
            symbols = []
            
            if isinstance(markets_info, list):
                # Formato: [{"symbol": "BTC", ...}, {"symbol": "ETH", ...}]
                logger.info(f"📋 Processando {len(markets_info)} mercados...")
                
                for market in markets_info:
                    if isinstance(market, dict):
                        symbol = market.get('symbol')
                        if symbol:
                            symbols.append(symbol.upper())  # Padronizar maiúscula
                            
            elif isinstance(markets_info, dict):
                # Formato aninhado: {"data": [...]} ou similar
                if 'data' in markets_info and isinstance(markets_info['data'], list):
                    logger.info(f"📋 Processando {len(markets_info['data'])} mercados (formato aninhado)...")
                    
                    for market in markets_info['data']:
                        if isinstance(market, dict):
                            symbol = market.get('symbol')
                            if symbol:
                                symbols.append(symbol.upper())
                else:
                    logger.error(f"❌ Formato de resposta não reconhecido: {markets_info}")
                    raise Exception(f"Formato inesperado da API: {type(markets_info)}")
            
            if not symbols:
                logger.error("❌ Nenhum símbolo válido encontrado na resposta da API")
                raise Exception("Nenhum símbolo encontrado na resposta da API")
            
            # Limpar, remover duplicatas e ordenar alfabeticamente
            unique_symbols = sorted(list(set(symbols)))
            
            logger.info(f"✅ Símbolos extraídos da Pacifica.fi: {len(unique_symbols)}")
            logger.info(f"📋 Amostra: {unique_symbols[:10]}...")
            
            return unique_symbols
        
        except Exception as e:
            logger.error(f"❌ Erro ao buscar símbolos da API: {e}")
            raise
    
    def _is_cache_valid(self) -> bool:
        """Verifica se cache ainda é válido"""
        if not self.cache_file.exists():
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            cache_time = datetime.fromisoformat(data.get('updated_at'))
            is_valid = datetime.now() - cache_time < self.cache_duration
            
            if is_valid:
                logger.debug(f"✅ Cache válido (atualizado em {cache_time})")
            else:
                logger.debug(f"⏰ Cache expirado (atualizado em {cache_time})")
            
            return is_valid
        
        except Exception as e:
            logger.error(f"❌ Erro ao validar cache: {e}")
            return False
    
    def _load_from_cache(self) -> List[str]:
        """Carrega símbolos do cache"""
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            return data.get('symbols', [])
        except Exception as e:
            logger.error(f"❌ Erro ao ler cache: {e}")
            return []
    
    def _save_to_cache(self, symbols: List[str]):
        """Salva símbolos no cache"""
        try:
            cache_data = {
                'updated_at': datetime.now().isoformat(),
                'symbols': symbols,
                'count': len(symbols)
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            logger.info(f"💾 Cache salvo: {len(symbols)} símbolos")
        
        except Exception as e:
            logger.error(f"❌ Erro ao salvar cache: {e}")
    
    def _get_default_symbols(self) -> List[str]:
        """
        ⚠️ FALLBACK EMERGENCIAL: Lista manual de símbolos populares
        
        IMPORTANTE: Esta lista NÃO representa os símbolos disponíveis na Pacifica.fi!
        É apenas um fallback para quando:
        - API está indisponível
        - Credenciais não configuradas  
        - Cache nunca foi criado
        
        Para ter os símbolos REAIS da corretora, configure as credenciais
        e o sistema buscará automaticamente da API.
        """
        symbols = [
            # 🥇 Top Cryptocurrencies
            'BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'AVAX', 'DOT', 'MATIC', 'LINK',
            'UNI', 'ATOM', 'LTC', 'BCH', 'XLM', 'ALGO', 'ICP', 'NEAR', 'FIL', 'MANA',
            'SAND', 'AXS', 'CRV', 'SUSHI', 'COMP', 'AAVE', 'MKR', 'SNX', '1INCH', 'YFI',
            
            # 💰 Stablecoins
            'USDT', 'USDC', 'BUSD', 'DAI', 'FRAX', 'TUSD', 'USDP', 'LUSD', 'USDD', 'GUSD',
            
            # 🐕 Memecoins e Trending
            'DOGE', 'SHIB', 'PEPE', 'FLOKI', 'BONK', 'WIF', 'BRETT', 'POPCAT', 'DEGEN', 'MEME',
            'WOJAK', 'PEPE2', 'TURBO', 'LADYS', 'BABYDOGE', 'DOGELON',
            
            # 🏗️ DeFi e Web3
            'CAKE', 'GMT', 'APE', 'BLUR', 'LDO', 'ARB', 'OP', 'IMX', 'GALA', 'ENJ',
            'ROSE', 'LOOKS', 'MAGIC', 'GMX', 'GRT', 'OCEAN', 'FET', 'AGIX', 'REN', 'CVX',
            
            # ⛓️ Layer 1 & 2
            'FTM', 'ONE', 'HBAR', 'ETC', 'XTZ', 'ZIL', 'VET', 'THETA', 'EGLD', 'FLOW',
            'KLAY', 'CFX', 'CELO', 'HARMONY', 'AURORA', 'METIS', 'BOBA', 'MOONBEAM', 'MOONRIVER',
            
            # 🎮 Gaming & NFTs  
            'ALICE', 'TLM', 'MOBOX', 'SKILL', 'PYR', 'STARL', 'REVV', 'TOWER', 'NFTB', 'SUPER',
            
            # 💼 Exchange Tokens
            'CRO', 'LEO', 'OKB', 'HT', 'KCS', 'GT', 'WBT', 'MX', 'NEXO', 'CEL',
            
            # 🔮 Outros Populares
            'TRX', 'EOS', 'XMR', 'ZEC', 'DASH', 'NEO', 'QTUM', 'WAVES', 'ZRX', 'BAT',
            'IOTA', 'XEM', 'LSK', 'SC', 'DCR', 'DGB', 'RVN', 'NANO', 'HOT', 'WIN'
        ]
        
        # Remover duplicatas e ordenar alfabeticamente
        return sorted(list(set(symbols)))
    
    def get_cache_info(self) -> Dict:
        """Retorna informações sobre o cache"""
        if not self.cache_file.exists():
            return {
                'exists': False,
                'message': 'Cache não existe'
            }
        
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            updated_at = datetime.fromisoformat(data.get('updated_at'))
            age = datetime.now() - updated_at
            is_valid = age < self.cache_duration
            
            return {
                'exists': True,
                'valid': is_valid,
                'updated_at': data.get('updated_at'),
                'age_hours': age.total_seconds() / 3600,
                'count': data.get('count', 0),
                'symbols': data.get('symbols', [])
            }
        
        except Exception as e:
            return {
                'exists': True,
                'error': str(e)
            }
    
    def update_cache(self, api_client=None) -> Dict:
        """
        Método específico para atualizar cache de símbolos
        
        Usado pelo:
        - Bot na inicialização
        - Interface web no botão "Atualizar Símbolos"
        - Chamadas programáticas
        
        Returns:
            Dict com resultado da operação
        """
        try:
            if not api_client:
                logger.warning("⚠️ API client não fornecido para atualização")
                return {
                    'success': False,
                    'message': 'API client necessário para buscar símbolos reais',
                    'symbols_count': 0,
                    'source': 'error'
                }
            
            # Forçar busca da API
            symbols = self.get_symbols(api_client, force_refresh=True)
            
            # Determinar fonte dos dados
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    if len(symbols) == cache_data.get('count', 0):
                        source = 'api_cached'
                    else:
                        source = 'api_fresh'
            else:
                source = 'api_fresh'
            
            return {
                'success': True,
                'message': f'✅ Cache atualizado: {len(symbols)} símbolos da Pacifica.fi',
                'symbols_count': len(symbols),
                'symbols': symbols,
                'source': source,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar cache: {e}")
            
            # Tentar usar cache existente como fallback
            if self.cache_file.exists():
                try:
                    symbols = self._load_from_cache()
                    return {
                        'success': False,
                        'message': f'⚠️ Erro na API, usando cache: {len(symbols)} símbolos',
                        'symbols_count': len(symbols),
                        'symbols': symbols,
                        'source': 'cache_fallback',
                        'error': str(e)
                    }
                except:
                    pass
            
            # Usar lista padrão como último recurso
            symbols = self._get_default_symbols()
            return {
                'success': False,
                'message': f'❌ API indisponível, usando lista padrão: {len(symbols)} símbolos',
                'symbols_count': len(symbols),
                'symbols': symbols,
                'source': 'default_fallback',
                'error': str(e)
            }