"""
Analytics Tracker - Sistema Modular de Coleta de Métricas
Autor: Bot Trading Pacifica.fi
Versão: 1.0
Data: 12/10/2025

Sistema de analytics reutilizável por todas as estratégias.
Armazena dados em JSON para análise posterior.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

class AnalyticsTracker:
    """
    Sistema de analytics modular e reutilizável.
    Cada estratégia pode usar para registrar seus próprios eventos.
    
    Características:
    - Armazenamento em JSON (fácil debug)
    - Arquivos separados por mês
    - Métodos genéricos e específicos
    - Opcional via configuração
    - Zero impacto na performance
    """
    
    def __init__(self, strategy_name: str, enabled: bool = True):
        """
        Inicializa o tracker de analytics
        
        Args:
            strategy_name: Nome da estratégia (ex: 'multi_asset_enhanced')
            enabled: Se False, todos os métodos são no-op
        """
        self.strategy_name = strategy_name
        self.enabled = enabled
        self.logger = logging.getLogger(f'PacificaBot.Analytics.{strategy_name}')
        
        if not self.enabled:
            self.logger.info("📊 Analytics DESATIVADO")
            return
        
        # Estrutura de dados em memória
        self.events = []
        self.session_start = datetime.now()
        
        # Configurar diretório
        self.data_dir = Path('data/analytics')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Nome do arquivo por mês (rotação automática)
        month_year = datetime.now().strftime('%Y_%m')
        self.current_file = self.data_dir / f"{strategy_name}_{month_year}.json"
        
        # Carregar dados existentes do mês
        self._load_existing_data()
        
        self.logger.info(f"📊 Analytics ATIVO - Arquivo: {self.current_file.name}")
        self.logger.info(f"📊 Eventos já registrados este mês: {len(self.events)}")
    
    def _load_existing_data(self):
        """Carrega dados existentes do arquivo do mês atual"""
        if self.current_file.exists():
            try:
                with open(self.current_file, 'r', encoding='utf-8') as f:
                    self.events = json.load(f)
                self.logger.debug(f"✅ Carregados {len(self.events)} eventos existentes")
            except Exception as e:
                self.logger.error(f"❌ Erro ao carregar analytics: {e}")
                self.events = []
    
    def _save(self):
        """Salva dados no arquivo JSON"""
        if not self.enabled:
            return
        
        try:
            with open(self.current_file, 'w', encoding='utf-8') as f:
                json.dump(self.events, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"❌ Erro ao salvar analytics: {e}")
    
    def _check_file_rotation(self):
        """Verifica se precisa rotacionar arquivo (novo mês)"""
        month_year = datetime.now().strftime('%Y_%m')
        expected_file = self.data_dir / f"{self.strategy_name}_{month_year}.json"
        
        if expected_file != self.current_file:
            # Novo mês - rotacionar arquivo
            self.logger.info(f"📅 Rotação de arquivo: {self.current_file.name} → {expected_file.name}")
            self.current_file = expected_file
            self.events = []
            self._load_existing_data()
    
    # ========================================================================
    # MÉTODOS GENÉRICOS - Qualquer estratégia pode usar
    # ========================================================================
    
    def log_event(self, event_type: str, data: Dict):
        """
        Método genérico - qualquer estratégia pode usar
        
        Args:
            event_type: Tipo do evento (ex: 'signal_analysis', 'grid_execution')
            data: Dados específicos do evento (Dict flexível)
        """
        if not self.enabled:
            return
        
        # Verificar rotação de arquivo
        self._check_file_rotation()
        
        event = {
            'id': len(self.events) + 1,
            'timestamp': datetime.now().isoformat(),
            'strategy': self.strategy_name,
            'event_type': event_type,
            'data': data
        }
        
        self.events.append(event)
        self._save()
        
        self.logger.debug(f"📝 Evento registrado: {event_type}")
    
    # ========================================================================
    # MÉTODOS ESPECÍFICOS PARA ESTRATÉGIAS MULTI-ASSET
    # ========================================================================
    
    def log_signal_analysis(self, symbol: str, signal_data: Dict, decision: str, rejection_reason: str = None):
        """
        Registra análise de sinal (executado ou rejeitado)
        
        Args:
            symbol: Símbolo analisado (BTC, ETH, etc)
            signal_data: Dados do sinal (score, indicadores, etc)
            decision: 'EXECUTED' ou 'REJECTED'
            rejection_reason: Motivo da rejeição (se aplicável)
        """
        self.log_event('signal_analysis', {
            'symbol': symbol,
            'score': signal_data.get('quality_score'),
            'confidence': signal_data.get('confidence'),
            'indicators': {
                'momentum': signal_data.get('momentum'),
                'trend': signal_data.get('trend'),
                'rsi': signal_data.get('rsi'),
                'volatility': signal_data.get('volatility'),
                'confirmation': signal_data.get('confirmation')
            },
            'side': signal_data.get('side'),
            'decision': decision,
            'rejection_reason': rejection_reason
        })
    
    def log_trade_execution(self, symbol: str, side: str, price: float, quantity: float, 
                           order_id: str = None, tp_price: float = None, sl_price: float = None):
        """
        Registra execução de trade
        
        Args:
            symbol: Símbolo tradado
            side: 'LONG' ou 'SHORT'
            price: Preço de entrada
            quantity: Quantidade
            order_id: ID da ordem (opcional)
            tp_price: Preço do take profit (opcional)
            sl_price: Preço do stop loss (opcional)
        """
        self.log_event('trade_execution', {
            'symbol': symbol,
            'side': side,
            'price': price,
            'quantity': quantity,
            'order_id': order_id,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'position_size_usd': price * quantity
        })
    
    def log_trade_close(self, symbol: str, order_id: str, exit_price: float, 
                       exit_reason: str, pnl_usd: float, pnl_percent: float, 
                       duration_minutes: int = None):
        """
        Registra fechamento de trade
        
        Args:
            symbol: Símbolo
            order_id: ID da ordem
            exit_price: Preço de saída
            exit_reason: Motivo (TP/SL/TIME/MANUAL)
            pnl_usd: Lucro/prejuízo em USD
            pnl_percent: Lucro/prejuízo em %
            duration_minutes: Duração em minutos
        """
        self.log_event('trade_close', {
            'symbol': symbol,
            'order_id': order_id,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'pnl_usd': pnl_usd,
            'pnl_percent': pnl_percent,
            'duration_minutes': duration_minutes,
            'result': 'WIN' if pnl_usd > 0 else 'LOSS'
        })
    
    # ========================================================================
    # MÉTODOS ESPECÍFICOS PARA ESTRATÉGIAS GRID
    # ========================================================================
    
    def log_grid_execution(self, symbol: str, level: int, price: float, 
                          side: str, quantity: float):
        """
        Registra execução de ordem do grid
        
        Args:
            symbol: Símbolo
            level: Nível do grid
            price: Preço da ordem
            side: 'buy' ou 'sell'
            quantity: Quantidade
        """
        self.log_event('grid_execution', {
            'symbol': symbol,
            'level': level,
            'price': price,
            'side': side,
            'quantity': quantity
        })
    
    def log_grid_rebalance(self, symbol: str, reason: str, old_center: float = None,
                          new_center: float = None, orders_cancelled: int = 0,
                          orders_created: int = 0):
        """
        Registra rebalanceamento do grid
        
        Args:
            symbol: Símbolo
            reason: Motivo do rebalance
            old_center: Centro antigo do grid
            new_center: Novo centro do grid
            orders_cancelled: Quantidade de ordens canceladas
            orders_created: Quantidade de ordens criadas
        """
        self.log_event('grid_rebalance', {
            'symbol': symbol,
            'reason': reason,
            'old_center': old_center,
            'new_center': new_center,
            'orders_cancelled': orders_cancelled,
            'orders_created': orders_created,
            'price_shift_percent': ((new_center - old_center) / old_center * 100) if old_center and new_center else None
        })
    
    # ========================================================================
    # MÉTODOS DE CONSULTA E ANÁLISE
    # ========================================================================
    
    def get_events_by_type(self, event_type: str) -> List[Dict]:
        """Retorna todos eventos de um tipo específico"""
        return [e for e in self.events if e['event_type'] == event_type]
    
    def get_events_by_symbol(self, symbol: str) -> List[Dict]:
        """Retorna todos eventos relacionados a um símbolo"""
        return [e for e in self.events if e['data'].get('symbol') == symbol]
    
    def get_events_by_decision(self, decision: str) -> List[Dict]:
        """Retorna sinais por decisão (EXECUTED ou REJECTED)"""
        signals = self.get_events_by_type('signal_analysis')
        return [s for s in signals if s['data'].get('decision') == decision]
    
    def get_summary(self) -> Dict:
        """
        Retorna resumo completo dos dados coletados
        
        Returns:
            Dict com estatísticas gerais
        """
        if not self.events:
            return {
                'strategy': self.strategy_name,
                'total_events': 0,
                'message': 'Nenhum evento registrado ainda'
            }
        
        # Contar tipos de eventos
        event_types = {}
        for event in self.events:
            et = event['event_type']
            event_types[et] = event_types.get(et, 0) + 1
        
        # Período de coleta
        timestamps = [datetime.fromisoformat(e['timestamp']) for e in self.events]
        start_time = min(timestamps)
        end_time = max(timestamps)
        duration_hours = (end_time - start_time).total_seconds() / 3600
        
        # Estatísticas de sinais (se aplicável)
        signals = self.get_events_by_type('signal_analysis')
        signal_stats = None
        if signals:
            executed = len([s for s in signals if s['data']['decision'] == 'EXECUTED'])
            rejected = len([s for s in signals if s['data']['decision'] == 'REJECTED'])
            signal_stats = {
                'total': len(signals),
                'executed': executed,
                'rejected': rejected,
                'execution_rate': f"{executed / len(signals) * 100:.1f}%"
            }
        
        # Estatísticas de trades (se aplicável)
        trades = self.get_events_by_type('trade_close')
        trade_stats = None
        if trades:
            wins = len([t for t in trades if t['data']['result'] == 'WIN'])
            losses = len([t for t in trades if t['data']['result'] == 'LOSS'])
            total_pnl = sum(t['data']['pnl_usd'] for t in trades)
            trade_stats = {
                'total': len(trades),
                'wins': wins,
                'losses': losses,
                'win_rate': f"{wins / len(trades) * 100:.1f}%",
                'total_pnl_usd': f"${total_pnl:.2f}"
            }
        
        return {
            'strategy': self.strategy_name,
            'file': self.current_file.name,
            'total_events': len(self.events),
            'event_types': event_types,
            'period': {
                'start': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                'duration_hours': f"{duration_hours:.1f}h"
            },
            'signal_stats': signal_stats,
            'trade_stats': trade_stats
        }
    
    def print_summary(self):
        """Imprime resumo formatado no console"""
        summary = self.get_summary()
        
        print("\n" + "="*70)
        print(f"📊 ANALYTICS SUMMARY - {summary['strategy'].upper()}")
        print("="*70)
        
        if summary['total_events'] == 0:
            print("⚠️  Nenhum evento registrado ainda")
            print("="*70 + "\n")
            return
        
        print(f"\n📁 Arquivo: {summary['file']}")
        print(f"📅 Período: {summary['period']['start']} → {summary['period']['end']}")
        print(f"⏱️  Duração: {summary['period']['duration_hours']}")
        
        print(f"\n📊 Total de Eventos: {summary['total_events']}")
        print("\nTipos de Eventos:")
        for event_type, count in summary['event_types'].items():
            print(f"   • {event_type}: {count}")
        
        if summary['signal_stats']:
            stats = summary['signal_stats']
            print(f"\n🎯 Estatísticas de Sinais:")
            print(f"   Total analisados: {stats['total']}")
            print(f"   ✅ Executados: {stats['executed']}")
            print(f"   ❌ Rejeitados: {stats['rejected']}")
            print(f"   📊 Taxa de execução: {stats['execution_rate']}")
        
        if summary['trade_stats']:
            stats = summary['trade_stats']
            print(f"\n💰 Estatísticas de Trades:")
            print(f"   Total fechados: {stats['total']}")
            print(f"   ✅ Vitórias: {stats['wins']}")
            print(f"   ❌ Derrotas: {stats['losses']}")
            print(f"   📊 Win Rate: {stats['win_rate']}")
            print(f"   💵 PnL Total: {stats['total_pnl_usd']}")
        
        print("\n" + "="*70 + "\n")
    
    def export_to_csv(self, output_file: str = None):
        """
        Exporta eventos para CSV (para análise em Excel/Google Sheets)
        
        Args:
            output_file: Nome do arquivo de saída (opcional)
        """
        if not self.enabled or not self.events:
            self.logger.warning("❌ Nenhum evento para exportar")
            return None
        
        import csv
        
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"data/analytics/{self.strategy_name}_export_{timestamp}.csv"
        
        try:
            # Flatten data structure for CSV
            rows = []
            for event in self.events:
                row = {
                    'id': event['id'],
                    'timestamp': event['timestamp'],
                    'strategy': event['strategy'],
                    'event_type': event['event_type']
                }
                
                # Adicionar campos do data (flatten)
                for key, value in event['data'].items():
                    if isinstance(value, dict):
                        # Nested dict - flatten
                        for sub_key, sub_value in value.items():
                            row[f"{key}_{sub_key}"] = sub_value
                    else:
                        row[key] = value
                
                rows.append(row)
            
            # Escrever CSV
            if rows:
                keys = rows[0].keys()
                with open(output_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(rows)
                
                self.logger.info(f"✅ Exportado para: {output_file}")
                return output_file
        
        except Exception as e:
            self.logger.error(f"❌ Erro ao exportar CSV: {e}")
            return None
