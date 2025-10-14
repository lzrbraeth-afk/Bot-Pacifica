"""
Grid Performance Analyzer - Análise Específica para Estratégias Grid
Autor: Bot Trading Pacifica.fi
Versão: 1.0

Script para analisar dados de estratégias Grid (Pure, Market Making, Dynamic).
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from collections import defaultdict

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

class GridPerformanceAnalyzer:
    """Analisa dados específicos de estratégias Grid"""
    
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
        filename = self.file.stem
        parts = filename.split('_')
        return '_'.join(parts[:-2])
    
    # ========================================================================
    # ANÁLISES ESPECÍFICAS PARA GRID
    # ========================================================================
    
    def analyze_grid_executions(self) -> Dict:
        """
        Analisa execuções das ordens do grid
        
        Returns:
            Dict com estatísticas de execuções
        """
        executions = [e for e in self.data if e['event_type'] == 'grid_execution']
        
        if not executions:
            return {'message': 'Nenhuma execução registrada ainda'}
        
        # Estatísticas gerais
        buy_orders = [e for e in executions if e['data']['side'] == 'buy']
        sell_orders = [e for e in executions if e['data']['side'] == 'sell']
        
        # Análise por nível
        level_activity = defaultdict(lambda: {'buy': 0, 'sell': 0, 'total': 0})
        
        for exe in executions:
            level = exe['data'].get('level', 0)
            side = exe['data']['side']
            level_activity[level][side] += 1
            level_activity[level]['total'] += 1
        
        # Top níveis mais ativos
        top_levels = sorted(
            level_activity.items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )[:10]
        
        # Análise de preços
        prices = [e['data']['price'] for e in executions]
        
        return {
            'total_executions': len(executions),
            'buy_orders': len(buy_orders),
            'sell_orders': len(sell_orders),
            'ratio_buy_sell': f"{len(buy_orders)}/{len(sell_orders)}",
            'unique_levels': len(level_activity),
            'top_active_levels': [
                {
                    'level': level,
                    'buys': data['buy'],
                    'sells': data['sell'],
                    'total': data['total']
                }
                for level, data in top_levels
            ],
            'price_range': {
                'min': f"${min(prices):.2f}",
                'max': f"${max(prices):.2f}",
                'range': f"${max(prices) - min(prices):.2f}"
            }
        }
    
    def analyze_rebalances(self) -> Dict:
        """
        Analisa rebalanceamentos do grid
        """
        rebalances = [e for e in self.data if e['event_type'] == 'grid_rebalance']
        
        if not rebalances:
            return {'message': 'Nenhum rebalanceamento registrado'}
        
        # Agrupar por motivo
        by_reason = defaultdict(lambda: {
            'count': 0,
            'avg_orders_cancelled': 0,
            'avg_orders_created': 0,
            'total_cancelled': 0,
            'total_created': 0
        })
        
        for reb in rebalances:
            reason = reb['data']['reason']
            cancelled = reb['data'].get('orders_cancelled', 0)
            created = reb['data'].get('orders_created', 0)
            
            by_reason[reason]['count'] += 1
            by_reason[reason]['total_cancelled'] += cancelled
            by_reason[reason]['total_created'] += created
        
        # Calcular médias
        for reason, data in by_reason.items():
            count = data['count']
            data['avg_orders_cancelled'] = data['total_cancelled'] / count
            data['avg_orders_created'] = data['total_created'] / count
        
        # Análise temporal
        if len(rebalances) > 1:
            first_time = datetime.fromisoformat(rebalances[0]['timestamp'])
            last_time = datetime.fromisoformat(rebalances[-1]['timestamp'])
            duration_hours = (last_time - first_time).total_seconds() / 3600
            frequency = len(rebalances) / duration_hours if duration_hours > 0 else 0
        else:
            frequency = 0
        
        return {
            'total_rebalances': len(rebalances),
            'by_reason': {
                reason: {
                    'count': data['count'],
                    'percentage': f"{data['count'] / len(rebalances) * 100:.1f}%",
                    'avg_cancelled': f"{data['avg_orders_cancelled']:.1f}",
                    'avg_created': f"{data['avg_orders_created']:.1f}"
                }
                for reason, data in sorted(by_reason.items(), key=lambda x: x[1]['count'], reverse=True)
            },
            'frequency_per_hour': f"{frequency:.2f}"
        }
    
    def analyze_grid_efficiency(self) -> Dict:
        """
        Analisa eficiência do grid (execuções vs rebalanceamentos)
        """
        executions = [e for e in self.data if e['event_type'] == 'grid_execution']
        rebalances = [e for e in self.data if e['event_type'] == 'grid_rebalance']
        
        if not executions or not rebalances:
            return {'message': 'Dados insuficientes'}
        
        # Razão execuções/rebalanceamentos
        ratio = len(executions) / len(rebalances)
        
        # Análise temporal
        first_exe = datetime.fromisoformat(executions[0]['timestamp'])
        last_exe = datetime.fromisoformat(executions[-1]['timestamp'])
        duration_hours = (last_exe - first_exe).total_seconds() / 3600
        
        executions_per_hour = len(executions) / duration_hours if duration_hours > 0 else 0
        
        # Distribuição temporal
        hourly_distribution = defaultdict(int)
        for exe in executions:
            hour = datetime.fromisoformat(exe['timestamp']).hour
            hourly_distribution[hour] += 1
        
        # Hora mais ativa
        most_active_hour = max(hourly_distribution.items(), key=lambda x: x[1]) if hourly_distribution else (0, 0)
        
        return {
            'execution_rebalance_ratio': f"{ratio:.2f}",
            'executions_per_hour': f"{executions_per_hour:.2f}",
            'most_active_hour': f"{most_active_hour[0]}:00 ({most_active_hour[1]} execuções)",
            'interpretation': self._interpret_efficiency(ratio, executions_per_hour)
        }
    
    def _interpret_efficiency(self, ratio: float, exe_per_hour: float) -> str:
        """Interpreta métricas de eficiência"""
        
        interpretations = []
        
        # Análise da razão
        if ratio > 10:
            interpretations.append("✅ Grid muito eficiente - poucas reorganizações")
        elif ratio > 5:
            interpretations.append("✅ Grid eficiente")
        elif ratio > 2:
            interpretations.append("⚠️ Grid médio - considere ajustar parâmetros")
        else:
            interpretations.append("❌ Muitos rebalanceamentos - grid instável")
        
        # Análise de atividade
        if exe_per_hour > 10:
            interpretations.append("Alta atividade de trading")
        elif exe_per_hour > 5:
            interpretations.append("Atividade moderada")
        else:
            interpretations.append("Baixa atividade - considere ajustar spacing")
        
        return " | ".join(interpretations)
    
    def analyze_dynamic_adjustments(self) -> Dict:
        """
        Analisa ajustes dinâmicos (específico para Dynamic Grid)
        """
        dynamic_rebalances = [
            e for e in self.data
            if e['event_type'] == 'grid_rebalance'
            and 'dynamic_adjustment' in e['data'].get('reason', '')
        ]
        
        if not dynamic_rebalances:
            return {'message': 'Nenhum ajuste dinâmico (estratégia não é Dynamic Grid?)'}
        
        # Separar por tipo de tendência
        uptrend_adjustments = [
            r for r in dynamic_rebalances
            if 'uptrend' in r['data']['reason']
        ]
        
        downtrend_adjustments = [
            r for r in dynamic_rebalances
            if 'downtrend' in r['data']['reason']
        ]
        
        # Calcular movimentos de preço
        price_shifts = []
        for adj in dynamic_rebalances:
            old_center = adj['data'].get('old_center')
            new_center = adj['data'].get('new_center')
            
            if old_center and new_center and old_center > 0:
                shift_pct = ((new_center - old_center) / old_center) * 100
                price_shifts.append(shift_pct)
        
        avg_shift = sum(price_shifts) / len(price_shifts) if price_shifts else 0
        
        return {
            'total_dynamic_adjustments': len(dynamic_rebalances),
            'uptrend_adjustments': len(uptrend_adjustments),
            'downtrend_adjustments': len(downtrend_adjustments),
            'ratio_up_down': f"{len(uptrend_adjustments)}/{len(downtrend_adjustments)}",
            'avg_price_shift': f"{avg_shift:+.2f}%",
            'interpretation': self._interpret_dynamic(len(uptrend_adjustments), len(downtrend_adjustments))
        }
    
    def _interpret_dynamic(self, up_count: int, down_count: int) -> str:
        """Interpreta ajustes dinâmicos"""
        
        if up_count == 0 and down_count == 0:
            return "Sem ajustes dinâmicos"
        
        total = up_count + down_count
        up_pct = (up_count / total) * 100 if total > 0 else 0
        
        if up_pct > 60:
            return "📈 Mercado em tendência altista predominante"
        elif up_pct > 40:
            return "↔️ Mercado lateral - tendências equilibradas"
        else:
            return "📉 Mercado em tendência baixista predominante"
    
    # ========================================================================
    # GERAÇÃO DE RELATÓRIOS
    # ========================================================================
    
    def generate_full_report(self) -> str:
        """Gera relatório completo para estratégias Grid"""
        
        report = []
        report.append("=" * 80)
        report.append(f"📊 RELATÓRIO GRID PERFORMANCE - {self.strategy_name.upper()}")
        report.append("=" * 80)
        report.append(f"\n📁 Arquivo: {self.file.name}")
        report.append(f"📅 Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"📊 Total de eventos: {len(self.data)}")
        
        # 1. Análise de Execuções
        report.append("\n" + "="*80)
        report.append("1️⃣  ANÁLISE DE EXECUÇÕES DO GRID")
        report.append("="*80)
        
        executions = self.analyze_grid_executions()
        if 'message' not in executions:
            report.append(f"\nTotal de execuções: {executions['total_executions']}")
            report.append(f"Buy/Sell: {executions['ratio_buy_sell']}")
            report.append(f"Níveis únicos operados: {executions['unique_levels']}")
            report.append(f"Range de preços: {executions['price_range']['range']} "
                        f"({executions['price_range']['min']} - {executions['price_range']['max']})")
            
            report.append("\nTop 10 Níveis Mais Ativos:")
            report.append("Nível | Buys | Sells | Total")
            report.append("-" * 40)
            for level_data in executions['top_active_levels']:
                report.append(
                    f"{level_data['level']:5} | {level_data['buys']:4} | "
                    f"{level_data['sells']:5} | {level_data['total']:5}"
                )
        else:
            report.append(f"\n⚠️  {executions['message']}")
        
        # 2. Análise de Rebalanceamentos
        report.append("\n" + "="*80)
        report.append("2️⃣  ANÁLISE DE REBALANCEAMENTOS")
        report.append("="*80)
        
        rebalances = self.analyze_rebalances()
        if 'message' not in rebalances:
            report.append(f"\nTotal de rebalanceamentos: {rebalances['total_rebalances']}")
            report.append(f"Frequência: {rebalances['frequency_per_hour']} por hora")
            
            report.append("\nPor Motivo:")
            report.append("Motivo                      | Quantidade | %     | Méd Cancel | Méd Criadas")
            report.append("-" * 80)
            for reason, data in rebalances['by_reason'].items():
                report.append(
                    f"{reason:27} | {data['count']:10} | {data['percentage']:5} | "
                    f"{data['avg_cancelled']:10} | {data['avg_created']:11}"
                )
        else:
            report.append(f"\n⚠️  {rebalances['message']}")
        
        # 3. Análise de Eficiência
        report.append("\n" + "="*80)
        report.append("3️⃣  EFICIÊNCIA DO GRID")
        report.append("="*80)
        
        efficiency = self.analyze_grid_efficiency()
        if 'message' not in efficiency:
            report.append(f"\nRazão Execuções/Rebalanceamentos: {efficiency['execution_rebalance_ratio']}")
            report.append(f"Execuções por hora: {efficiency['executions_per_hour']}")
            report.append(f"Hora mais ativa: {efficiency['most_active_hour']}")
            report.append(f"\n💡 Interpretação: {efficiency['interpretation']}")
        else:
            report.append(f"\n⚠️  {efficiency['message']}")
        
        # 4. Ajustes Dinâmicos (se aplicável)
        report.append("\n" + "="*80)
        report.append("4️⃣  AJUSTES DINÂMICOS")
        report.append("="*80)
        
        dynamic = self.analyze_dynamic_adjustments()
        if 'message' not in dynamic:
            report.append(f"\nTotal de ajustes dinâmicos: {dynamic['total_dynamic_adjustments']}")
            report.append(f"Ajustes de alta: {dynamic['uptrend_adjustments']}")
            report.append(f"Ajustes de baixa: {dynamic['downtrend_adjustments']}")
            report.append(f"Razão Up/Down: {dynamic['ratio_up_down']}")
            report.append(f"Shift médio de preço: {dynamic['avg_price_shift']}")
            report.append(f"\n💡 Interpretação: {dynamic['interpretation']}")
        else:
            report.append(f"\n✅ {dynamic['message']}")
        
        # 5. Recomendações
        report.append("\n" + "="*80)
        report.append("5️⃣  RECOMENDAÇÕES")
        report.append("="*80)
        
        recommendations = self._generate_grid_recommendations(executions, rebalances, efficiency)
        for rec in recommendations:
            report.append(f"\n{rec}")
        
        report.append("\n" + "="*80)
        
        return "\n".join(report)
    
    def _generate_grid_recommendations(self, executions, rebalances, efficiency) -> List[str]:
        """Gera recomendações específicas para Grid"""
        
        recs = []
        
        # Baseado em eficiência
        if 'execution_rebalance_ratio' in efficiency:
            ratio = float(efficiency['execution_rebalance_ratio'])
            if ratio < 2:
                recs.append(
                    "⚠️  GRID INSTÁVEL: Muitos rebalanceamentos. "
                    "Considere aumentar GRID_SPACING ou GRID_SHIFT_THRESHOLD."
                )
            elif ratio > 15:
                recs.append(
                    "💡 GRID MUITO ESTÁVEL: Poucas reorganizações. "
                    "Considere reduzir GRID_SPACING para mais oportunidades."
                )
        
        # Baseado em atividade
        if 'executions_per_hour' in efficiency:
            exe_per_hour = float(efficiency['executions_per_hour'])
            if exe_per_hour < 2:
                recs.append(
                    "📊 BAIXA ATIVIDADE: Menos de 2 execuções/hora. "
                    "Considere reduzir GRID_SPACING_PERCENT para mais trades."
                )
        
        # Baseado em buy/sell
        if 'ratio_buy_sell' in executions:
            ratio_str = executions['ratio_buy_sell']
            buy, sell = map(int, ratio_str.split('/'))
            
            if buy > sell * 1.5:
                recs.append(
                    "📈 DESBALANCEAMENTO: Mais buys que sells. "
                    "Grid está acumulando posição long - monitorar."
                )
            elif sell > buy * 1.5:
                recs.append(
                    "📉 DESBALANCEAMENTO: Mais sells que buys. "
                    "Grid está reduzindo exposição - verificar se intencional."
                )
        
        if not recs:
            recs.append("✅ Grid operando dentro dos parâmetros esperados.")
        
        return recs
    
    def save_report(self, output_file: str = None):
        """Salva relatório em arquivo"""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"data/analytics/report_grid_{self.strategy_name}_{timestamp}.txt"
        
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
    print("📊 GRID PERFORMANCE ANALYZER - Bot Trading Pacifica.fi")
    print("="*80 + "\n")
    
    # Buscar arquivos de analytics
    analytics_dir = Path('data/analytics')
    
    if not analytics_dir.exists():
        print("❌ Diretório data/analytics não encontrado!")
        print("💡 Execute o bot com ANALYTICS_ENABLED=true primeiro.\n")
        return
    
    # Listar arquivos JSON de grid
    json_files = [
        f for f in analytics_dir.glob('*.json')
        if any(strategy in f.name for strategy in ['grid', 'dynamic_grid', 'pure_grid', 'market_making'])
    ]
    
    if not json_files:
        print("❌ Nenhum arquivo de analytics de Grid encontrado!")
        print("💡 Este script é específico para estratégias Grid.\n")
        print("📋 Arquivos disponíveis:")
        for f in analytics_dir.glob('*.json'):
            print(f"   - {f.name}")
        return
    
    print(f"📁 Arquivos de analytics Grid disponíveis:\n")
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
    analyzer = GridPerformanceAnalyzer(selected_file)
    report = analyzer.generate_full_report()
    
    # Exibir relatório
    print(report)
    
    # Salvar relatório
    analyzer.save_report()


if __name__ == '__main__':
    main()
