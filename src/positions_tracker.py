"""
Positions & Orders Tracker - Pacifica.fi Bot
Módulo para salvar posições ativas e ordens abertas em arquivos JSON
para visualização em tempo real na interface web
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class PositionsTracker:
    """Rastreador de posições e ordens para interface web"""
    
    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)
        
        self.positions_file = self.data_dir / "active_positions.json"
        self.orders_file = self.data_dir / "active_orders.json"
        
        logger.info("📊 PositionsTracker inicializado")
    
    def update_positions(self, positions: List[Dict[str, Any]], current_price: float = None):
        """
        Atualiza arquivo de posições ativas
        
        Args:
            positions: Lista de posições no formato:
                [
                    {
                        "symbol": "SOL",
                        "side": "long" ou "short",
                        "size": 0.5,
                        "entry_price": 150.00,
                        "open_time": "2024-01-01T12:00:00"
                    }
                ]
            current_price: Preço atual para calcular PNL em tempo real
        """
        try:
            # Enriquecer posições com dados calculados
            enriched_positions = []
            
            for pos in positions:
                enriched = pos.copy()
                
                # Adicionar preço atual se fornecido
                if current_price:
                    enriched["current_price"] = current_price
                    
                    # Calcular PNL
                    entry = float(pos.get("entry_price", 0))
                    size = float(pos.get("size", 0))
                    side = pos.get("side", "long").lower()
                    
                    if side in ["long", "buy"]:
                        pnl = (current_price - entry) * size
                    else:
                        pnl = (entry - current_price) * size
                    
                    enriched["pnl_usd"] = round(pnl, 2)
                    enriched["pnl_percent"] = round((pnl / (entry * size)) * 100, 2) if entry > 0 else 0
                
                # Garantir que open_time está em formato ISO
                if "open_time" not in enriched:
                    enriched["open_time"] = datetime.now().isoformat()
                
                enriched_positions.append(enriched)
            
            # Salvar arquivo
            data = {
                "last_update": datetime.now().isoformat(),
                "positions_count": len(enriched_positions),
                "positions": enriched_positions
            }
            
            with open(self.positions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"✅ Posições atualizadas: {len(enriched_positions)} ativas")
            
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar posições: {e}")
    
    def update_orders(self, orders: List[Dict[str, Any]]):
        """
        Atualiza arquivo de ordens abertas
        
        Args:
            orders: Lista de ordens no formato:
                [
                    {
                        "order_id": "123456",
                        "symbol": "SOL",
                        "side": "buy" ou "sell",
                        "price": 150.00,
                        "size": 0.1,
                        "create_time": "2024-01-01T12:00:00"
                    }
                ]
        """
        try:
            # Enriquecer ordens com dados calculados
            enriched_orders = []
            
            for order in orders:
                enriched = order.copy()
                
                # Garantir que create_time está em formato ISO
                if "create_time" not in enriched:
                    enriched["create_time"] = datetime.now().isoformat()
                
                # Calcular valor da ordem
                price = float(order.get("price", 0))
                size = float(order.get("size", 0))
                enriched["value_usd"] = round(price * size, 2)
                
                enriched_orders.append(enriched)
            
            # Salvar arquivo
            data = {
                "last_update": datetime.now().isoformat(),
                "orders_count": len(enriched_orders),
                "orders": enriched_orders
            }
            
            with open(self.orders_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"✅ Ordens atualizadas: {len(enriched_orders)} abertas")
            
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar ordens: {e}")
    
    def clear_positions(self):
        """Limpa arquivo de posições (quando não há posições ativas)"""
        try:
            data = {
                "last_update": datetime.now().isoformat(),
                "positions_count": 0,
                "positions": []
            }
            
            with open(self.positions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug("✅ Posições limpas")
            
        except Exception as e:
            logger.error(f"❌ Erro ao limpar posições: {e}")
    
    def clear_orders(self):
        """Limpa arquivo de ordens (quando não há ordens abertas)"""
        try:
            data = {
                "last_update": datetime.now().isoformat(),
                "orders_count": 0,
                "orders": []
            }
            
            with open(self.orders_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug("✅ Ordens limpas")
            
        except Exception as e:
            logger.error(f"❌ Erro ao limpar ordens: {e}")


# ========== FUNÇÕES AUXILIARES PARA INTEGRAÇÃO COM O BOT ==========

def save_bot_positions_snapshot(
    active_positions: List[Dict],
    open_orders: List[Dict],
    current_price: float = None
):
    """
    Função helper para ser chamada pelo bot principal
    Salva snapshot das posições e ordens atuais
    
    Exemplo de uso no bot:
        from positions_tracker import save_bot_positions_snapshot
        
        # No loop principal do bot:
        save_bot_positions_snapshot(
            active_positions=my_positions_list,
            open_orders=my_orders_list,
            current_price=current_sol_price
        )
    """
    tracker = PositionsTracker()
    tracker.update_positions(active_positions, current_price)
    tracker.update_orders(open_orders)


def extract_positions_from_api_response(api_positions: List[Dict]) -> List[Dict]:
    """
    Converte resposta da API Pacifica.fi para formato do tracker
    
    Args:
        api_positions: Resposta da API get_positions()
    
    Returns:
        Lista formatada para o tracker
    """
    formatted = []
    
    for pos in api_positions:
        formatted.append({
            "symbol": pos.get("symbol", ""),
            "side": pos.get("side", "").lower(),  # long/short
            "size": float(pos.get("size", 0)),
            "entry_price": float(pos.get("avg_entry_price", 0) or pos.get("entry_price", 0)),
            "open_time": pos.get("created_at", datetime.now().isoformat()),
            "leverage": pos.get("leverage", 1)
        })
    
    return formatted


def extract_orders_from_api_response(api_orders: List[Dict]) -> List[Dict]:
    """
    Converte resposta da API Pacifica.fi para formato do tracker
    
    Args:
        api_orders: Resposta da API get_open_orders()
    
    Returns:
        Lista formatada para o tracker
    """
    formatted = []
    
    for order in api_orders:
        # Normalizar side (bid/ask -> buy/sell)
        side = order.get("side", "").lower()
        if side == "bid":
            side = "buy"
        elif side == "ask":
            side = "sell"
        
        formatted.append({
            "order_id": order.get("order_id", "") or order.get("id", ""),
            "symbol": order.get("symbol", ""),
            "side": side,
            "price": float(order.get("price", 0)),
            "size": float(order.get("size", 0)),
            "create_time": order.get("created_at", datetime.now().isoformat()),
            "type": order.get("type", "limit")
        })
    
    return formatted


# ========== EXEMPLO DE INTEGRAÇÃO COM O BOT ==========

if __name__ == "__main__":
    """
    Exemplo de como usar o PositionsTracker
    """
    import time
    
    print("🧪 Testando PositionsTracker...")
    
    tracker = PositionsTracker()
    
    # Exemplo 1: Posição Long ativa
    test_positions = [
        {
            "symbol": "SOL",
            "side": "long",
            "size": 0.5,
            "entry_price": 150.00,
            "open_time": "2024-01-01T12:00:00",
            "leverage": 10
        }
    ]
    
    # Exemplo 2: Ordens no grid
    test_orders = [
        {
            "order_id": "order_1",
            "symbol": "SOL",
            "side": "buy",
            "price": 148.00,
            "size": 0.1,
            "create_time": "2024-01-01T12:05:00"
        },
        {
            "order_id": "order_2",
            "symbol": "SOL",
            "side": "sell",
            "price": 152.00,
            "size": 0.1,
            "create_time": "2024-01-01T12:05:00"
        }
    ]
    
    # Simular atualizações com preço variando
    print("\n📊 Simulando 5 atualizações com preço variando...\n")
    
    prices = [150.00, 151.50, 149.00, 152.50, 150.50]
    
    for i, current_price in enumerate(prices, 1):
        print(f"Atualização {i}/5 - Preço: ${current_price:.2f}")
        
        tracker.update_positions(test_positions, current_price)
        tracker.update_orders(test_orders)
        
        # Calcular PNL para mostrar
        pnl = (current_price - test_positions[0]["entry_price"]) * test_positions[0]["size"]
        print(f"  PNL: ${pnl:.2f}")
        
        time.sleep(1)
    
    print("\n✅ Teste concluído!")
    print(f"📁 Arquivos criados em: {tracker.data_dir}/")
    print(f"  - {tracker.positions_file.name}")
    print(f"  - {tracker.orders_file.name}")
    print("\n💡 Agora você pode abrir a interface web e ver os dados na aba 'Posições & Ordens'")