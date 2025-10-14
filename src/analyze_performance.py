"""
Performance Analyzer - Análise de Dados do Analytics
Autor: Bot Trading Pacifica.fi
Versão: 1.0
Data: 12/10/2025

Script para analisar dados coletados e gerar insights acionáveis.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from collections import defaultdict

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

class PerformanceAnalyzer:
    """Analisa dados do analytics e gera insights"""
    
    def __init__(self, analytics_file: Path):
        self.file = analytics_file
        self.data = self._load_data()
        self.strategy_name = self._extract_strategy_name()
    
    def _load_data(self) -> List[Dict]:
        """Carrega dados do arquivo JSON"""
        try:
            with open(self.file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Erro ao carregar {self.file}: {e}")
            return []
    
    def _extract_strategy_name(self) -> str:
        """Extrai nome da estratégia do nome do arquivo"""
        # Formato: strategy_name_YYYY_MM.json
        filename = self.file.stem  # Remove .json
        parts = filename.split('_')
        # Remove ano e mês (últimos 2 elementos)
        return '_'.join(parts[:-2])
    
    # ========================================================================
    # ANÁLISES PARA ESTRATÉGIAS MULTI-ASSET
    # ========================================================================
    
    def analyze_signal_quality(self) -> Dict:
        """
        Analisa correlação entre score do sinal e resultado
        
        Returns:
            Dict com análise por faixa de score
        """
        signals = [e for e in self.data if e['event_type'] == 'signal_analysis']
        trades = [e for e in self.data if e['event_type'] == 'trade_close']
        
        if not signals or not trades:
            return {'error': 'Dados insuficientes'}
        
        # Mapear trades por ordem
        trades_map = {t['data']['order_id']: t for t in trades}
        
        # Agrupar por faixas de score
        score_ranges = {
            '90-100': [],
            '80-89': [],
            '70-79': [],
            '65-69': [],
            '60-64': []
        }
        
        for signal in signals:
            if signal['data']['decision'] != 'EXECUTED':
                continue
            
            score = signal['data'].get('score', 0)
            
            # Encontrar faixa
            if score >= 90:
                range_key = '90-100'
            elif score >= 80:
                range_key = '80-89'
            elif score >= 70:
                range_key = '70-79'
            elif score >= 65:
                range_key = '65-69'
            else:
                range_key = '60-64'
            
            score_ranges[range_key].append(signal)
        
        # Calcular estatísticas por faixa
        results = {}
        for range_key, signals_in_range in score_ranges.items():
            if not signals_in_range:
                continue
            
            # Encontrar trades correspondentes (aproximação por tempo)
            wins = 0
            losses = 0
            total_pnl = 0
            
            for signal in signals_in_range:
                signal_time = datetime.fromisoformat(signal['timestamp'])
                
                # Buscar trade mais próximo (dentro de 2 minutos)
                for trade in trades:
                    trade_time = datetime.fromisoformat(trade['timestamp'])
                    time_diff = abs((trade_time - signal_time).total_seconds())
                    
                    if time_diff < 120:  # 2 minutos
                        if trade['data']['result'] == 'WIN':
                            wins += 1
                        else:
                            losses += 1
                        total_pnl += trade['data']['pnl_usd']
                        break
            
            total = wins + losses
            if total > 0:
                results[range_key] = {
                    'total_signals': len(signals_in_range),
                    'total_trades': total,
                    'wins': wins,
                    'losses': losses,
                    'win_rate': f"{wins / total * 100:.1f}%",
                    'avg_pnl': f"${total_pnl / total:.2f}",
                    'total_pnl': f"${total_pnl:.2f}"
                }
        
        return results
    
    def analyze_rejection_reasons(self) -> Dict:
        """Analisa motivos de rejeição de sinais"""
        signals = [e for e in self.data if e['event_type'] == 'signal_analysis']
        rejected = [s for s in signals if s['data']['decision'] == 'REJECTED']
        
        if not rejected:
            return {'message': 'Nenhum sinal rejeitado'}
        
        # Contar por motivo
        reasons = defaultdict(int)
        for signal in rejected:
            reason = signal['data'].get('rejection_reason', 'unknown')
            reasons[reason] += 1
        
        total = len(rejected)
        return {
            'total_rejected': total,
            'reasons': {
                reason: {
                    'count': count,
                    'percentage': f"{count / total * 100:.1f}%"
                }
                for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True)
            }
        }
    
    def analyze_indicators(self) -> Dict:
        """
        Analisa quais indicadores têm mais correlação com sucesso
        """
        signals = [e for e in self.data if e['event_type'] == 'signal_analysis' 
                  and e['data']['decision'] == 'EXECUTED']
        trades = [e for e in self.data if e['event_type'] == 'trade_close']
        
        if not signals or not trades:
            return {'error': 'Dados insuficientes'}
        
        # Separar sinais vencedores e perdedores
        winning_signals = []
        losing_signals = []
        
        for signal in signals:
            signal_time = datetime.fromisoformat(signal['timestamp'])
            
            # Buscar trade correspondente
            for trade in trades:
                trade_time = datetime.fromisoformat(trade['timestamp'])
                time_diff = abs((trade_time - signal_time).total_seconds())
                
                if time_diff < 120:  # 2 minutos
                    if trade['data']['result'] == 'WIN':
                        winning_signals.append(signal)
                    else:
                        losing_signals.append(signal)
                    break
        
        if not winning_signals or not losing_signals:
            return {'error': 'Precisa de trades WIN e LOSS'}
        
        # Calcular médias dos indicadores
        indicators = ['momentum', 'trend', 'rsi', 'volatility', 'confirmation']
        comparison = {}
        
        for ind in indicators:
            win_values = [s['data']['indicators'].get(ind, 0) for s in winning_signals]
            loss_values = [s['data']['indicators'].get(ind, 0) for s in losing_signals]
            
            if win_values and loss_values:
                win_avg = sum(win_values) / len(win_values)
                loss_avg = sum(loss_values) / len(loss_values)
                difference = win_avg - loss_avg
                
                comparison[ind] = {
                    'win_avg': f"{win_avg:.2f}",
                    'loss_avg': f"{loss_avg:.2f}",
                    'difference': f"{difference:+.2f}",
                    'relevance': 'HIGH' if abs(difference) > 3 else 'MEDIUM' if abs(difference) > 1.5 else 'LOW'
                }
        
        return comparison
    
    def analyze_exit_reasons(self) -> Dict:
        """Analisa como os trades estão sendo fechados"""
        trades = [e for e in self.data if e['event_type'] == 'trade_close']
        
        if not trades:
            return {'message': 'Nenhum trade fechado ainda'}
        
        # Agrupar por motivo de saída
        by_reason = defaultdict(lambda: {'count': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0})
        
        for trade in trades:
            reason = trade['data']['exit_reason']
            by_reason[reason]['count'] += 1
            
            if trade['data']['result'] == 'WIN':
                by_reason[reason]['wins'] += 1
            else:
                by_reason[reason]['losses'] += 1
            
            by_reason[reason]['total_pnl'] += trade['data']['pnl_usd']
        
        # Calcular estatísticas
        results = {}
        for reason, data in by_reason.items():
            total = data['count']
            results[reason] = {
                'count': total,
                'percentage': f"{total / len(trades) * 100:.1f}%",
                'win_rate': f"{data['wins'] / total * 100:.1f}%",
                'avg_pnl': f"${data['total_pnl'] / total:.2f}",
                'total_pnl': f"${data['total_pnl']:.2f}"
            }
        
        return results
    
    def analyze_by_symbol(self) -> Dict:
        """Analisa performance por símbolo"""
        trades = [e for e in self.data if e['event_type'] == 'trade_close']
        
        if not trades:
            return {'message': 'Nenhum trade fechado ainda'}
        
        # Agrupar por símbolo
        by_symbol = defaultdict(lambda: {'trades': 0, 'wins': 0, 'losses': 0, 'total_pnl': 0})
        
        for trade in trades:
            symbol = trade['data']['symbol']
            by_symbol[symbol]['trades'] += 1
            
            if trade['data']['result'] == 'WIN':
                by_symbol[symbol]['wins'] += 1
            else:
                by_symbol[symbol]['losses'] += 1
            
            by_symbol[symbol]['total_pnl'] += trade['data']['pnl_usd']
        
        # Calcular estatísticas
        results = {}
        for symbol, data in sorted(by_symbol.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
            total = data['trades']
            results[symbol] = {
                'trades': total,
                'wins': data['wins'],
                'losses': data['losses'],
                'win_rate': f"{data['wins'] / total * 100:.1f}%",
                'avg_pnl': f"${data['total_pnl'] / total:.2f}",
                'total_pnl': f"${data['total_pnl']:.2f}"
            }
        
        return results
    
    # ========================================================================
    # GERAÇÃO DE RELATÓRIOS
    # ========================================================================
    
    def generate_full_report(self) -> str:
        """Gera relatório completo com todas as análises"""
        
        report = []
        report.append("=" * 80)
        report.append(f"📊 RELATÓRIO DE PERFORMANCE - {self.strategy_name.upper()}")
        report.append("=" * 80)
        report.append(f"\n📁 Arquivo: {self.file.name}")
        report.append(f"📅 Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"📊 Total de eventos: {len(self.data)}")
        
        # 1. Análise de Qualidade de Sinais
        report.append("\n" + "="*80)
        report.append("1️⃣  ANÁLISE DE QUALIDADE DE SINAIS")
        report.append("="*80)
        
        signal_quality = self.analyze_signal_quality()
        if 'error' not in signal_quality:
            report.append("\nScore    | Trades | Win Rate | PnL Médio | PnL Total")
            report.append("-" * 60)
            for score_range, data in sorted(signal_quality.items(), reverse=True):
                report.append(
                    f"{score_range:8} | {data['total_trades']:6} | {data['win_rate']:8} | "
                    f"{data['avg_pnl']:9} | {data['total_pnl']:9}"
                )
        else:
            report.append(f"\n⚠️  {signal_quality['error']}")
        
        # 2. Motivos de Rejeição
        report.append("\n" + "="*80)
        report.append("2️⃣  MOTIVOS DE REJEIÇÃO DE SINAIS")
        report.append("="*80)
        
        rejections = self.analyze_rejection_reasons()
        if 'message' not in rejections:
            report.append(f"\nTotal de sinais rejeitados: {rejections['total_rejected']}")
            report.append("\nMotivo                          | Quantidade | %")
            report.append("-" * 60)
            for reason, data in rejections['reasons'].items():
                report.append(f"{reason:30} | {data['count']:10} | {data['percentage']:6}")
        else:
            report.append(f"\n✅ {rejections['message']}")
        
        # 3. Análise de Indicadores
        report.append("\n" + "="*80)
        report.append("3️⃣  CORRELAÇÃO DOS INDICADORES COM SUCESSO")
        report.append("="*80)
        
        indicators = self.analyze_indicators()
        if 'error' not in indicators:
            report.append("\nIndicador    | Média WIN | Média LOSS | Diferença | Relevância")
            report.append("-" * 70)
            for ind, data in indicators.items():
                report.append(
                    f"{ind:12} | {data['win_avg']:9} | {data['loss_avg']:10} | "
                    f"{data['difference']:9} | {data['relevance']:10}"
                )
        else:
            report.append(f"\n⚠️  {indicators['error']}")
        
        # 4. Motivos de Saída
        report.append("\n" + "="*80)
        report.append("4️⃣  ANÁLISE POR MOTIVO DE SAÍDA")
        report.append("="*80)
        
        exits = self.analyze_exit_reasons()
        if 'message' not in exits:
            report.append("\nMotivo | Quantidade | %     | Win Rate | PnL Médio | PnL Total")
            report.append("-" * 75)
            for reason, data in exits.items():
                report.append(
                    f"{reason:6} | {data['count']:10} | {data['percentage']:5} | "
                    f"{data['win_rate']:8} | {data['avg_pnl']:9} | {data['total_pnl']:9}"
                )
        else:
            report.append(f"\n⚠️  {exits['message']}")
        
        # 5. Performance por Símbolo
        report.append("\n" + "="*80)
        report.append("5️⃣  PERFORMANCE POR SÍMBOLO")
        report.append("="*80)
        
        by_symbol = self.analyze_by_symbol()
        if 'message' not in by_symbol:
            report.append("\nSímbolo | Trades | Wins | Losses | Win Rate | PnL Médio | PnL Total")
            report.append("-" * 75)
            for symbol, data in by_symbol.items():
                report.append(
                    f"{symbol:7} | {data['trades']:6} | {data['wins']:4} | {data['losses']:6} | "
                    f"{data['win_rate']:8} | {data['avg_pnl']:9} | {data['total_pnl']:9}"
                )
        else:
            report.append(f"\n⚠️  {by_symbol['message']}")
        
        # 6. Recomendações
        report.append("\n" + "="*80)
        report.append("6️⃣  RECOMENDAÇÕES BASEADAS EM DADOS")
        report.append("="*80)
        
        recommendations = self._generate_recommendations(signal_quality, indicators, exits)
        for rec in recommendations:
            report.append(f"\n{rec}")
        
        report.append("\n" + "="*80)
        
        return "\n".join(report)
    
    def _generate_recommendations(self, signal_quality, indicators, exits) -> List[str]:
        """Gera recomendações baseadas nas análises"""
        recs = []
        
        # Recomendações baseadas em score
        if 'error' not in signal_quality:
            for score_range, data in signal_quality.items():
                win_rate = float(data['win_rate'].rstrip('%'))
                if win_rate < 40 and score_range in ['60-64', '65-69']:
                    recs.append(
                        f"⚠️  AUMENTAR THRESHOLD: Score {score_range} tem win rate de apenas "
                        f"{data['win_rate']}. Considere aumentar ENHANCED_MIN_SCORE."
                    )
        
        # Recomendações baseadas em indicadores
        if 'error' not in indicators:
            for ind, data in indicators.items():
                if data['relevance'] == 'LOW':
                    recs.append(
                        f"💡 REVISAR PESO: Indicador '{ind}' tem baixa correlação com sucesso "
                        f"(diferença: {data['difference']}). Considere reduzir peso."
                    )
        
        # Recomendações baseadas em saídas
        if 'message' not in exits:
            for reason, data in exits.items():
                percentage = float(data['percentage'].rstrip('%'))
                if reason == 'TIME' and percentage > 30:
                    recs.append(
                        f"⏱️  TEMPO MÁXIMO: {data['percentage']} dos trades fecham por tempo. "
                        f"Considere ajustar MAX_POSITION_TIME_MINUTES."
                    )
        
        if not recs:
            recs.append("✅ Nenhuma recomendação crítica no momento.")
        
        return recs
    
    def save_report(self, output_file: str = None):
        """Salva relatório em arquivo"""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"data/analytics/report_{self.strategy_name}_{timestamp}.txt"
        
        report = self.generate_full_report()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n✅ Relatório salvo em: {output_file}\n")
        return output_file


# ============================================================================
# SCRIPT PRINCIPAL
# ============================================================================

def main():
    """Função principal do script"""
    
    print("\n" + "="*80)
    print("📊 PERFORMANCE ANALYZER - Bot Trading Pacifica.fi")
    print("="*80 + "\n")
    
    # Buscar arquivos de analytics
    analytics_dir = Path('data/analytics')
    
    if not analytics_dir.exists():
        print("❌ Diretório data/analytics não encontrado!")
        print("💡 Execute o bot com ANALYTICS_ENABLED=true primeiro.\n")
        return
    
    # Listar arquivos JSON disponíveis
    json_files = list(analytics_dir.glob('*.json'))
    
    if not json_files:
        print("❌ Nenhum arquivo de analytics encontrado!")
        print("💡 Execute o bot com ANALYTICS_ENABLED=true primeiro.\n")
        return
    
    print(f"📁 Arquivos de analytics disponíveis:\n")
    for i, file in enumerate(json_files, 1):
        print(f"   {i}. {file.name}")
    
    # Selecionar arquivo
    if len(json_files) == 1:
        selected_file = json_files[0]
        print(f"\n✅ Analisando: {selected_file.name}\n")
    else:
        try:
            choice = int(input(f"\nEscolha um arquivo (1-{len(json_files)}): "))
            selected_file = json_files[choice - 1]
        except (ValueError, IndexError):
            print("❌ Escolha inválida!")
            return
    
    # Análise
    analyzer = PerformanceAnalyzer(selected_file)
    report = analyzer.generate_full_report()
    
    # Exibir relatório
    print(report)
    
    # Salvar relatório
    output_file = analyzer.save_report()
    
    # Opção de exportar CSV
    export = input("\n📊 Exportar dados para CSV? (s/n): ").lower()
    if export == 's':
        csv_file = analyzer.file.stem + '_export.csv'
        # Implementar exportação se necessário
        print(f"💡 Use analytics.export_to_csv() no código para exportar")


if __name__ == '__main__':
    main()
