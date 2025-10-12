"""
CSV Trade Parser - Pacifica.fi
Processa arquivos CSV exportados da Pacifica para análise de performance

Features:
    - Parse automático de arquivos CSV da Pacifica
    - Cálculo de estatísticas completas de trading
    - Análise por símbolo e diária
    - Exportação para JSON
    - Suporte a múltiplos formatos de data
    
Uso:
    from src.csv_trade_parser import PacificaCSVParser, analyze_pacifica_csv
    
    # Análise rápida
    stats = analyze_pacifica_csv('data/trades.csv')
    
    # Ou usar classe diretamente
    parser = PacificaCSVParser('data/trades.csv')
    parser.parse_csv()
    stats = parser.get_statistics()
"""
import csv
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PacificaCSVParser:
    """Parser para arquivos CSV exportados da Pacifica"""
    
    def __init__(self, csv_path: str = None):
        """
        Inicializa o parser
        
        Args:
            csv_path: Caminho para o arquivo CSV (opcional)
                     Se não fornecido, procura na pasta data/
        """
        self.csv_path = csv_path
        self.trades = []
        
        # Se não foi fornecido caminho, procurar na pasta data/
        if not self.csv_path:
            self.csv_path = self._find_latest_csv()
    
    def _find_latest_csv(self) -> Optional[str]:
        """Procura o CSV mais recente na pasta data/"""
        data_dir = Path("data")
        
        if not data_dir.exists():
            data_dir.mkdir(exist_ok=True)
            return None
        
        # Procurar por arquivos CSV da Pacifica
        csv_files = list(data_dir.glob("pacifica*.csv"))
        
        if not csv_files:
            logger.warning("⚠️ Nenhum CSV da Pacifica encontrado em data/")
            return None
        
        # Retornar o mais recente
        latest = max(csv_files, key=lambda p: p.stat().st_mtime)
        logger.info(f"📁 CSV encontrado: {latest.name}")
        return str(latest)
    
    def parse_csv(self) -> List[Dict]:
        """
        Processa o arquivo CSV e retorna lista de trades
        
        Returns:
            Lista de dicionários com dados dos trades
        """
        if not self.csv_path or not Path(self.csv_path).exists():
            logger.error(f"❌ Arquivo não encontrado: {self.csv_path}")
            return []
        
        trades = []
        
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        # Parsear cada linha
                        trade = self._parse_trade_row(row)
                        if trade:
                            trades.append(trade)
                    except Exception as e:
                        logger.warning(f"⚠️ Erro ao processar linha: {e}")
                        continue
            
            self.trades = trades
            logger.info(f"✅ {len(trades)} trades processados de {Path(self.csv_path).name}")
            return trades
            
        except Exception as e:
            logger.error(f"❌ Erro ao ler CSV: {e}")
            return []
    
    def _parse_trade_row(self, row: Dict) -> Optional[Dict]:
        """
        Converte uma linha do CSV em dicionário estruturado
        
        Args:
            row: Linha do CSV como dicionário
            
        Returns:
            Dicionário com dados do trade ou None se inválido
        """
        try:
            # Extrair e limpar dados
            time_str = row.get('Time', '').strip()
            symbol = row.get('Symbol', '').strip()
            side = row.get('Side', '').strip().lower()
            trade_type = row.get('Type', '').strip()
            
            # Converter valores numéricos com tratamento de erros
            try:
                size = float(row.get('Size', '0').replace(',', '').replace('$', ''))
            except (ValueError, AttributeError):
                size = 0.0
                
            try:
                price = float(row.get('Price', '0').replace(',', '').replace('$', ''))
            except (ValueError, AttributeError):
                price = 0.0
                
            try:
                trade_value = float(row.get('Trade Value', '0').replace(',', '').replace('$', ''))
            except (ValueError, AttributeError):
                trade_value = 0.0
                
            try:
                fee = float(row.get('Fee', '0').replace(',', '').replace('$', ''))
            except (ValueError, AttributeError):
                fee = 0.0
                
            try:
                pnl = float(row.get('Realized PnL', '0').replace(',', '').replace('$', ''))
            except (ValueError, AttributeError):
                pnl = 0.0
            
            # Validar dados essenciais
            if not time_str or not symbol:
                logger.debug(f"Trade inválido: faltando timestamp ou símbolo")
                return None
            
            # Parsear timestamp
            # Formato esperado: "2024-10-12 14:30:45" ou similar
            try:
                # Tentar vários formatos comuns
                for fmt in ['%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%m/%d/%Y %H:%M:%S',
                           '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                    try:
                        timestamp = datetime.strptime(time_str, fmt).isoformat()
                        break
                    except ValueError:
                        continue
                else:
                    # Se nenhum formato funcionou, usar string original
                    timestamp = time_str
            except Exception as e:
                logger.debug(f"Erro ao parsear timestamp '{time_str}': {e}")
                timestamp = time_str
            
            # Calcular PNL líquido (após fees)
            net_pnl = pnl - fee
            
            # Criar dicionário estruturado
            trade = {
                'timestamp': timestamp,
                'symbol': symbol,
                'side': side,  # buy/sell
                'type': trade_type,
                'size': size,
                'price': price,
                'trade_value': trade_value,
                'fee': fee,
                'realized_pnl': pnl,
                'net_pnl': net_pnl,  # PNL após fees
                'is_winner': net_pnl > 0
            }
            
            return trade
            
        except Exception as e:
            logger.debug(f"Erro ao parsear linha: {e}")
            return None
    
    def get_statistics(self) -> Dict:
        """
        Calcula estatísticas completas dos trades
        
        Returns:
            Dicionário com todas as métricas
        """
        if not self.trades:
            return self._empty_stats()
        
        # Separar winners e losers
        winners = [t for t in self.trades if t['net_pnl'] > 0]
        losers = [t for t in self.trades if t['net_pnl'] < 0]
        breakeven = [t for t in self.trades if t['net_pnl'] == 0]
        
        # Métricas básicas
        total_trades = len(self.trades)
        total_pnl = sum(t['net_pnl'] for t in self.trades)
        total_fees = sum(t['fee'] for t in self.trades)
        total_volume = sum(t['trade_value'] for t in self.trades)
        
        # Win rate
        win_rate = (len(winners) / total_trades * 100) if total_trades > 0 else 0
        
        # Médias
        avg_win = sum(t['net_pnl'] for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t['net_pnl'] for t in losers) / len(losers) if losers else 0
        avg_trade = total_pnl / total_trades if total_trades > 0 else 0
        
        # Extremos
        best_trade = max(self.trades, key=lambda t: t['net_pnl']) if self.trades else None
        worst_trade = min(self.trades, key=lambda t: t['net_pnl']) if self.trades else None
        
        # Profit Factor
        total_wins = sum(t['net_pnl'] for t in winners)
        total_losses = abs(sum(t['net_pnl'] for t in losers))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Por símbolo
        symbols_stats = self._calculate_symbol_stats()
        
        # Timeline (por dia)
        daily_stats = self._calculate_daily_stats()
        
        return {
            'summary': {
                'total_trades': total_trades,
                'winning_trades': len(winners),
                'losing_trades': len(losers),
                'breakeven_trades': len(breakeven),
                'win_rate': round(win_rate, 2),
                'total_pnl': round(total_pnl, 2),
                'total_fees': round(total_fees, 2),
                'total_volume': round(total_volume, 2),
                'net_profit': round(total_pnl, 2),
                'avg_trade': round(avg_trade, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'profit_factor': round(profit_factor, 2),
                'best_trade': {
                    'pnl': round(best_trade['net_pnl'], 2),
                    'symbol': best_trade['symbol'],
                    'timestamp': best_trade['timestamp']
                } if best_trade else None,
                'worst_trade': {
                    'pnl': round(worst_trade['net_pnl'], 2),
                    'symbol': worst_trade['symbol'],
                    'timestamp': worst_trade['timestamp']
                } if worst_trade else None
            },
            'by_symbol': symbols_stats,
            'daily': daily_stats,
            'raw_trades': self.trades  # Para usar em gráficos
        }
    
    def _calculate_symbol_stats(self) -> Dict:
        """Calcula estatísticas por símbolo"""
        symbols = {}
        
        for trade in self.trades:
            symbol = trade['symbol']
            
            if symbol not in symbols:
                symbols[symbol] = {
                    'trades': 0,
                    'pnl': 0,
                    'fees': 0,
                    'volume': 0,
                    'winners': 0,
                    'losers': 0
                }
            
            symbols[symbol]['trades'] += 1
            symbols[symbol]['pnl'] += trade['net_pnl']
            symbols[symbol]['fees'] += trade['fee']
            symbols[symbol]['volume'] += trade['trade_value']
            
            if trade['net_pnl'] > 0:
                symbols[symbol]['winners'] += 1
            elif trade['net_pnl'] < 0:
                symbols[symbol]['losers'] += 1
        
        # Calcular win rate por símbolo
        for symbol, stats in symbols.items():
            total = stats['trades']
            stats['win_rate'] = round((stats['winners'] / total * 100), 2) if total > 0 else 0
            stats['pnl'] = round(stats['pnl'], 2)
            stats['fees'] = round(stats['fees'], 2)
            stats['volume'] = round(stats['volume'], 2)
        
        return symbols
    
    def _calculate_daily_stats(self) -> Dict:
        """Calcula estatísticas diárias"""
        daily = {}
        
        for trade in self.trades:
            try:
                # Extrair data (sem hora)
                timestamp = trade['timestamp']
                if isinstance(timestamp, str):
                    date = timestamp.split('T')[0] if 'T' in timestamp else timestamp.split(' ')[0]
                else:
                    date = str(timestamp)[:10]
                
                if date not in daily:
                    daily[date] = {
                        'trades': 0,
                        'pnl': 0,
                        'fees': 0,
                        'volume': 0,
                        'winners': 0,
                        'losers': 0
                    }
                
                daily[date]['trades'] += 1
                daily[date]['pnl'] += trade['net_pnl']
                daily[date]['fees'] += trade['fee']
                daily[date]['volume'] += trade['trade_value']
                
                if trade['net_pnl'] > 0:
                    daily[date]['winners'] += 1
                elif trade['net_pnl'] < 0:
                    daily[date]['losers'] += 1
                    
            except Exception as e:
                logger.debug(f"Erro ao processar data: {e}")
                continue
        
        # Arredondar valores
        for date, stats in daily.items():
            stats['pnl'] = round(stats['pnl'], 2)
            stats['fees'] = round(stats['fees'], 2)
            stats['volume'] = round(stats['volume'], 2)
            total = stats['trades']
            stats['win_rate'] = round((stats['winners'] / total * 100), 2) if total > 0 else 0
        
        return daily
    
    def _empty_stats(self) -> Dict:
        """Retorna estrutura vazia de estatísticas"""
        return {
            'summary': {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'breakeven_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'total_fees': 0,
                'total_volume': 0,
                'net_profit': 0,
                'avg_trade': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'best_trade': None,
                'worst_trade': None
            },
            'by_symbol': {},
            'daily': {},
            'raw_trades': []
        }
    
    def save_to_json(self, output_path: str = "data/csv_trades_analysis.json"):
        """
        Salva análise completa em JSON
        
        Args:
            output_path: Caminho do arquivo de saída
            
        Returns:
            bool: True se salvou com sucesso, False caso contrário
        """
        try:
            stats = self.get_statistics()
            
            # Garantir que o diretório existe
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Análise salva em: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao salvar JSON: {e}")
            return False
    
    def print_summary(self):
        """Imprime um resumo formatado das estatísticas"""
        stats = self.get_statistics()
        summary = stats['summary']
        
        print("\n" + "=" * 80)
        print("📈 RESUMO DA ANÁLISE")
        print("=" * 80)
        print(f"Total de Trades: {summary['total_trades']}")
        print(f"Trades Ganhos: {summary['winning_trades']} ({summary['win_rate']}%)")
        print(f"Trades Perdidos: {summary['losing_trades']}")
        print(f"\n💰 PNL Total: ${summary['total_pnl']:,.2f}")
        print(f"💵 Fees Totais: ${summary['total_fees']:,.2f}")
        print(f"📊 Volume Total: ${summary['total_volume']:,.2f}")
        print(f"\n📈 Média por Trade: ${summary['avg_trade']:,.2f}")
        print(f"✅ Média de Ganho: ${summary['avg_win']:,.2f}")
        print(f"❌ Média de Perda: ${summary['avg_loss']:,.2f}")
        print(f"⚖️  Profit Factor: {summary['profit_factor']:.2f}")
        
        if summary['best_trade']:
            print(f"\n🏆 Melhor Trade: ${summary['best_trade']['pnl']:,.2f} ({summary['best_trade']['symbol']})")
        
        if summary['worst_trade']:
            print(f"💥 Pior Trade: ${summary['worst_trade']['pnl']:,.2f} ({summary['worst_trade']['symbol']})")
        
        # Por símbolo
        if stats['by_symbol']:
            print("\n" + "=" * 80)
            print("📊 POR SÍMBOLO")
            print("=" * 80)
            
            for symbol, data in stats['by_symbol'].items():
                print(f"\n{symbol}:")
                print(f"  Trades: {data['trades']} | Win Rate: {data['win_rate']}%")
                print(f"  PNL: ${data['pnl']:,.2f} | Fees: ${data['fees']:,.2f}")
        
        print("\n" + "=" * 80)


# ============================================================================
# FUNÇÃO HELPER PARA USAR NA INTERFACE
# ============================================================================

def analyze_pacifica_csv(csv_path: str = None) -> Dict:
    """
    Função helper para análise rápida de CSV
    
    Args:
        csv_path: Caminho do CSV (opcional, procura automaticamente)
    
    Returns:
        Dicionário com estatísticas completas
        
    Example:
        >>> stats = analyze_pacifica_csv('data/trades.csv')
        >>> print(f"PNL Total: ${stats['summary']['total_pnl']}")
    """
    parser = PacificaCSVParser(csv_path)
    parser.parse_csv()
    stats = parser.get_statistics()
    
    # Salvar análise
    parser.save_to_json()
    
    return stats


# ============================================================================
# SCRIPT DE LINHA DE COMANDO
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Configurar logging para console
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )
    
    print("=" * 80)
    print("📊 Pacifica CSV Trade Analyzer")
    print("=" * 80)
    
    # Verificar se foi passado caminho do CSV
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    if csv_path:
        print(f"📁 Analisando: {csv_path}")
    else:
        print("🔍 Procurando CSV mais recente em data/...")
    
    # Analisar
    parser = PacificaCSVParser(csv_path)
    parser.parse_csv()
    
    # Mostrar resumo
    parser.print_summary()
    
    # Salvar JSON
    parser.save_to_json()
    
    print(f"✅ Análise completa salva em: data/csv_trades_analysis.json")
    print("=" * 80)
