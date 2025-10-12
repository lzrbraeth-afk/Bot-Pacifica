"""
Volume Tracker - Módulo para calcular volume de trading na Pacifica.fi
Usa o endpoint /api/v1/positions/history para buscar histórico de trades
"""
import requests
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from pathlib import Path

# Importar autenticação da Pacifica
try:
    from src.pacifica_auth import sign_message, prepare_message
    from solders.keypair import Keypair
    import base58
except ImportError:
    print("⚠️ Módulos de autenticação não encontrados")

logger = logging.getLogger(__name__)

class VolumeTracker:
    """Calcula volume de trading usando histórico da Pacifica"""
    
    def __init__(self, wallet_address: str, private_key: str = None):
        self.wallet_address = wallet_address
        self.base_url = "https://api.pacifica.fi"
        
        # Inicializar keypair se private_key fornecido
        self.keypair = None
        if private_key:
            try:
                self.keypair = Keypair.from_base58_string(private_key)
            except Exception as e:
                logger.warning(f"Não foi possível inicializar keypair: {e}")
    
    def get_trades_history(
        self, 
        symbol: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Busca histórico de trades do endpoint da Pacifica
        
        Args:
            symbol: Símbolo para filtrar (opcional)
            start_time: Timestamp início em milissegundos
            end_time: Timestamp fim em milissegundos
            limit: Número máximo de registros
            
        Returns:
            Lista de trades
        """
        try:
            # Construir URL
            url = f"{self.base_url}/api/v1/positions/history"
            
            # Parâmetros
            params = {
                "account": self.wallet_address,
                "limit": limit,
                "offset": 0
            }
            
            if symbol:
                params["symbol"] = symbol
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time
            
            # Fazer requisição
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("success") and data.get("data"):
                return data["data"]
            
            return []
            
        except Exception as e:
            logger.error(f"Erro ao buscar histórico de trades: {e}")
            return []
    
    def calculate_volume(self, trades: List[Dict]) -> Dict:
        """
        Calcula volume a partir de lista de trades
        
        Args:
            trades: Lista de trades do endpoint history
            
        Returns:
            Dict com estatísticas de volume
        """
        if not trades:
            return {
                "total_volume": 0,
                "total_trades": 0,
                "total_fees": 0,
                "total_pnl": 0,
                "by_symbol": {},
                "by_side": {
                    "open_long": 0,
                    "open_short": 0,
                    "close_long": 0,
                    "close_short": 0
                }
            }
        
        total_volume = 0
        total_fees = 0
        total_pnl = 0
        by_symbol = {}
        by_side = {
            "open_long": 0,
            "open_short": 0,
            "close_long": 0,
            "close_short": 0
        }
        
        for trade in trades:
            # Volume = amount × price
            amount = float(trade.get("amount", 0))
            price = float(trade.get("entry_price", trade.get("price", 0)))
            volume = amount * price
            
            total_volume += volume
            total_fees += float(trade.get("fee", 0))
            total_pnl += float(trade.get("pnl", 0))
            
            # Por símbolo
            symbol = trade.get("symbol", "UNKNOWN")
            if symbol not in by_symbol:
                by_symbol[symbol] = {"volume": 0, "trades": 0, "pnl": 0}
            
            by_symbol[symbol]["volume"] += volume
            by_symbol[symbol]["trades"] += 1
            by_symbol[symbol]["pnl"] += float(trade.get("pnl", 0))
            
            # Por side
            side = trade.get("side", "unknown")
            if side in by_side:
                by_side[side] += volume
        
        return {
            "total_volume": round(total_volume, 2),
            "total_trades": len(trades),
            "total_fees": round(total_fees, 2),
            "total_pnl": round(total_pnl, 2),
            "by_symbol": by_symbol,
            "by_side": by_side
        }
    
    def get_volume_stats(self, periods: List[str] = None) -> Dict:
        """
        Calcula volume para múltiplos períodos
        
        Args:
            periods: Lista de períodos ['1h', '24h', '7d', '14d']
            
        Returns:
            Dict com volume por período
        """
        if periods is None:
            periods = ['1h', '24h', '7d', '14d']
        
        now = datetime.now()
        results = {}
        
        period_deltas = {
            '1h': timedelta(hours=1),
            '24h': timedelta(hours=24),
            '7d': timedelta(days=7),
            '14d': timedelta(days=14),
            '30d': timedelta(days=30)
        }
        
        for period in periods:
            if period not in period_deltas:
                continue
            
            # Calcular timestamps
            start_time = now - period_deltas[period]
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(now.timestamp() * 1000)
            
            # Buscar trades
            trades = self.get_trades_history(
                start_time=start_ms,
                end_time=end_ms,
                limit=10000  # Aumentar limite para períodos longos
            )
            
            # Calcular volume
            volume_stats = self.calculate_volume(trades)
            
            results[period] = {
                **volume_stats,
                "period": period,
                "start_time": start_time.isoformat(),
                "end_time": now.isoformat()
            }
        
        return results
    
    def get_volume_timeline(
        self, 
        hours_back: int = 24,
        interval_minutes: int = 60
    ) -> List[Dict]:
        """
        Retorna evolução do volume ao longo do tempo
        
        Args:
            hours_back: Quantas horas para trás buscar
            interval_minutes: Intervalo de agregação em minutos
            
        Returns:
            Lista de pontos [{timestamp, volume, trades}]
        """
        now = datetime.now()
        start_time = now - timedelta(hours=hours_back)
        
        # Buscar todos os trades do período
        trades = self.get_trades_history(
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(now.timestamp() * 1000),
            limit=10000
        )
        
        if not trades:
            return []
        
        # Agrupar por intervalo
        interval_delta = timedelta(minutes=interval_minutes)
        timeline = {}
        
        for trade in trades:
            # Timestamp do trade
            trade_time = datetime.fromtimestamp(trade["created_at"] / 1000)
            
            # Arredondar para o intervalo
            interval_start = trade_time - timedelta(
                minutes=trade_time.minute % interval_minutes,
                seconds=trade_time.second,
                microseconds=trade_time.microsecond
            )
            
            interval_key = interval_start.isoformat()
            
            if interval_key not in timeline:
                timeline[interval_key] = {
                    "timestamp": interval_key,
                    "volume": 0,
                    "trades": 0,
                    "pnl": 0
                }
            
            # Calcular volume
            amount = float(trade.get("amount", 0))
            price = float(trade.get("entry_price", trade.get("price", 0)))
            volume = amount * price
            
            timeline[interval_key]["volume"] += volume
            timeline[interval_key]["trades"] += 1
            timeline[interval_key]["pnl"] += float(trade.get("pnl", 0))
        
        # Converter para lista ordenada
        result = sorted(timeline.values(), key=lambda x: x["timestamp"])
        
        return result


def get_volume_tracker() -> Optional[VolumeTracker]:
    """
    Factory function para criar VolumeTracker a partir do .env
    """
    try:
        wallet_address = os.getenv("WALLET_ADDRESS")
        private_key = os.getenv("PRIVATE_KEY")
        
        if not wallet_address:
            logger.warning("WALLET_ADDRESS não encontrado no .env")
            return None
        
        return VolumeTracker(
            wallet_address=wallet_address,
            private_key=private_key
        )
        
    except Exception as e:
        logger.error(f"Erro ao criar VolumeTracker: {e}")
        return None


# Exemplo de uso
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    tracker = get_volume_tracker()
    
    if tracker:
        print("📊 Buscando estatísticas de volume...")
        
        # Volume por períodos
        stats = tracker.get_volume_stats(['1h', '24h', '7d', '14d'])
        
        for period, data in stats.items():
            print(f"\n{period}:")
            print(f"  Volume: ${data['total_volume']:,.2f}")
            print(f"  Trades: {data['total_trades']}")
            print(f"  PNL: ${data['total_pnl']:,.2f}")
            print(f"  Fees: ${data['total_fees']:,.2f}")
        
        # Timeline (últimas 24h)
        print("\n📈 Evolução do volume (últimas 24h):")
        timeline = tracker.get_volume_timeline(hours_back=24, interval_minutes=60)
        
        for point in timeline[-5:]:  # Últimos 5 pontos
            print(f"  {point['timestamp']}: ${point['volume']:,.2f} ({point['trades']} trades)")
