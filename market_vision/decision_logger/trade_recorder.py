"""
Trade Recorder - Sistema de Registro de Decisões
Registra decisões manuais para análise e aprendizado futuro
"""

import json
import sqlite3
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path


class TradeDecisionRecorder:
    """
    Registra e analisa decisões de trading manuais
    """
    
    def __init__(self, db_path: str = 'data/trade_decisions.db',
                 logger: Optional[logging.Logger] = None):
        """
        Args:
            db_path: Caminho para banco de dados SQLite
            logger: Logger customizado (opcional)
        """
        self.db_path = Path(db_path)
        self.logger = logger or logging.getLogger(__name__)
        
        # Criar diretório se não existir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Inicializar banco de dados
        self._init_database()
        
        self.logger.info(f"Trade Recorder inicializado: {self.db_path}")
    
    def _init_database(self):
        """Inicializa estrutura do banco de dados"""
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Tabela de decisões
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                
                -- Preço e mercado
                price REAL NOT NULL,
                
                -- Scores
                global_score REAL,
                technical_score REAL,
                volume_score REAL,
                sentiment_score REAL,
                structure_score REAL,
                risk_score REAL,
                
                -- Indicadores chave
                rsi_15m REAL,
                adx_15m REAL,
                ema9 REAL,
                ema21 REAL,
                volume_ratio REAL,
                funding_rate REAL,
                volume_delta REAL,
                
                -- Setup sugerido
                suggested_direction TEXT,
                suggested_entry REAL,
                suggested_sl REAL,
                suggested_tp REAL,
                suggested_size REAL,
                setup_confidence REAL,
                setup_type TEXT,
                
                -- Decisão do usuário
                user_action TEXT NOT NULL,  -- 'execute', 'skip', 'modify'
                user_executed INTEGER NOT NULL,  -- 0 ou 1
                user_direction TEXT,
                user_entry REAL,
                user_sl REAL,
                user_tp REAL,
                user_size REAL,
                user_notes TEXT,
                
                -- Resultado (preenchido depois)
                outcome_pnl REAL,
                outcome_pnl_pct REAL,
                outcome_success INTEGER,
                outcome_exit_price REAL,
                outcome_exit_timestamp TEXT,
                outcome_duration_minutes INTEGER,
                outcome_max_drawdown REAL
            )
        ''')
        
        # Índices para queries rápidas
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON trade_decisions(timestamp)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_symbol 
            ON trade_decisions(symbol)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_action 
            ON trade_decisions(user_action)
        ''')
        
        conn.commit()
        conn.close()
        
        self.logger.info("Database schema inicializada")
    
    def record_decision(self, analysis: Dict, setup: Dict, 
                       user_decision: Dict) -> str:
        """
        Registra uma decisão de trade
        
        Args:
            analysis: Resultado do MarketAnalyzer
            setup: Resultado do EntryGenerator
            user_decision: {
                'action': 'execute' | 'skip' | 'modify',
                'direction': 'LONG' | 'SHORT',
                'entry': float,
                'stop_loss': float,
                'take_profit': float,
                'size_usd': float,
                'notes': str
            }
        
        Returns:
            decision_id (timestamp)
        """
        
        try:
            timestamp = datetime.now().isoformat()
            
            # Extrair dados
            global_data = analysis.get('global', {})
            tech_data = analysis.get('technical', {})
            volume_data = analysis.get('volume', {})
            sentiment_data = analysis.get('sentiment', {})
            structure_data = analysis.get('structure', {})
            risk_data = analysis.get('risk', {})
            
            indicators = tech_data.get('indicators', {})
            volume_metrics = volume_data.get('metrics', {})
            sentiment_details = sentiment_data.get('details', {})
            volume_details = volume_data.get('details', {})
            
            # Montar registro
            decision_record = {
                'timestamp': timestamp,
                'symbol': analysis.get('symbol', 'BTC'),
                'price': analysis.get('current_price', 0),
                
                # Scores
                'global_score': global_data.get('global_score', 0),
                'technical_score': tech_data.get('score', 0),
                'volume_score': volume_data.get('score', 0),
                'sentiment_score': sentiment_data.get('score', 0),
                'structure_score': structure_data.get('score', 0),
                'risk_score': risk_data.get('score', 0),
                
                # Indicadores
                'rsi_15m': indicators.get('rsi_14', 0),
                'adx_15m': indicators.get('adx', 0),
                'ema9': indicators.get('ema_9', 0),
                'ema21': indicators.get('ema_21', 0),
                'volume_ratio': volume_metrics.get('ratio', 0),
                'funding_rate': sentiment_details.get('funding', {}).get('value', 0),
                'volume_delta': volume_details.get('delta', {}).get('value', 0),
                
                # Setup sugerido
                'suggested_direction': setup.get('direction', ''),
                'suggested_entry': setup.get('entry', 0),
                'suggested_sl': setup.get('stop_loss', 0),
                'suggested_tp': setup.get('take_profit', 0),
                'suggested_size': setup.get('position_size_usd', 0),
                'setup_confidence': setup.get('confidence', 0),
                'setup_type': setup.get('setup_type', ''),
                
                # Decisão do usuário
                'user_action': user_decision.get('action', 'skip'),
                'user_executed': 1 if user_decision.get('action') == 'execute' else 0,
                'user_direction': user_decision.get('direction', ''),
                'user_entry': user_decision.get('entry', 0),
                'user_sl': user_decision.get('stop_loss', 0),
                'user_tp': user_decision.get('take_profit', 0),
                'user_size': user_decision.get('size_usd', 0),
                'user_notes': user_decision.get('notes', ''),
                
                # Outcome (NULL por enquanto)
                'outcome_pnl': None,
                'outcome_pnl_pct': None,
                'outcome_success': None,
                'outcome_exit_price': None,
                'outcome_exit_timestamp': None,
                'outcome_duration_minutes': None,
                'outcome_max_drawdown': None
            }
            
            # Salvar no banco
            self._save_to_database(decision_record)
            
            self.logger.info(
                f"Decisão registrada: {timestamp} - "
                f"{user_decision.get('action')} - {setup.get('direction', 'N/A')}"
            )
            
            return timestamp
            
        except Exception as e:
            self.logger.error(f"Erro ao registrar decisão: {e}", exc_info=True)
            return ""
    
    def _save_to_database(self, record: Dict):
        """Salva registro no banco de dados"""
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        columns = ', '.join(record.keys())
        placeholders = ', '.join(['?' for _ in record])
        
        cursor.execute(
            f'INSERT INTO trade_decisions ({columns}) VALUES ({placeholders})',
            list(record.values())
        )
        
        conn.commit()
        conn.close()
    
    def update_outcome(self, decision_timestamp: str, outcome: Dict):
        """
        Atualiza o resultado de um trade
        
        Args:
            decision_timestamp: ID da decisão (timestamp)
            outcome: {
                'pnl_usd': float,
                'pnl_pct': float,
                'success': bool,
                'exit_price': float,
                'exit_timestamp': str,
                'duration_minutes': int,
                'max_drawdown_pct': float
            }
        """
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE trade_decisions
                SET outcome_pnl = ?,
                    outcome_pnl_pct = ?,
                    outcome_success = ?,
                    outcome_exit_price = ?,
                    outcome_exit_timestamp = ?,
                    outcome_duration_minutes = ?,
                    outcome_max_drawdown = ?
                WHERE timestamp = ?
            ''', (
                outcome.get('pnl_usd', 0),
                outcome.get('pnl_pct', 0),
                1 if outcome.get('success', False) else 0,
                outcome.get('exit_price', 0),
                outcome.get('exit_timestamp', ''),
                outcome.get('duration_minutes', 0),
                outcome.get('max_drawdown_pct', 0),
                decision_timestamp
            ))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Outcome atualizado para decisão: {decision_timestamp}")
            
        except Exception as e:
            self.logger.error(f"Erro ao atualizar outcome: {e}", exc_info=True)
    
    def get_decision_patterns(self, min_confidence: float = 0.7,
                             min_samples: int = 20) -> Dict:
        """
        Analisa padrões nas decisões do usuário
        
        Args:
            min_confidence: Confiança mínima para considerar padrão
            min_samples: Número mínimo de amostras
        
        Returns:
            Dict com padrões identificados
        """
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Query decisões executadas
            cursor.execute('''
                SELECT 
                    global_score, technical_score, volume_score,
                    rsi_15m, adx_15m, volume_ratio,
                    user_action, outcome_success
                FROM trade_decisions
                WHERE user_executed = 1
                AND outcome_success IS NOT NULL
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            if len(rows) < min_samples:
                return {
                    'insufficient_data': True,
                    'message': f'Apenas {len(rows)} trades registrados. Mínimo: {min_samples}'
                }
            
            # Análise de padrões
            patterns = {
                'total_trades': len(rows),
                'successful_trades': sum(1 for r in rows if r[7] == 1),
                'win_rate': sum(1 for r in rows if r[7] == 1) / len(rows) * 100,
                
                # Padrões identificados
                'patterns': []
            }
            
            # Exemplo: "Usuário tende a entrar quando global_score > X"
            successful = [r for r in rows if r[7] == 1]
            if successful:
                avg_global_score_success = sum(r[0] for r in successful) / len(successful)
                patterns['patterns'].append({
                    'pattern': 'high_global_score',
                    'description': f'Trades de sucesso têm score global médio de {avg_global_score_success:.1f}',
                    'recommendation': f'Considere entrar apenas quando score > {avg_global_score_success - 0.5:.1f}'
                })
            
            # TODO: Análise mais sofisticada com ML
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"Erro ao analisar padrões: {e}", exc_info=True)
            return {}
    
    def export_to_csv(self, output_path: str, days: int = 30):
        """
        Exporta decisões para CSV
        
        Args:
            output_path: Caminho do arquivo CSV
            days: Últimos N dias
        """
        
        try:
            import pandas as pd
            
            conn = sqlite3.connect(str(self.db_path))
            
            query = f'''
                SELECT *
                FROM trade_decisions
                WHERE timestamp >= datetime('now', '-{days} days')
                ORDER BY timestamp DESC
            '''
            
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            df.to_csv(output_path, index=False)
            
            self.logger.info(f"Decisões exportadas para: {output_path}")
            
        except Exception as e:
            self.logger.error(f"Erro ao exportar CSV: {e}", exc_info=True)
    
    def get_recent_decisions(self, limit: int = 10) -> List[Dict]:
        """Retorna últimas N decisões"""
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row  # Para acessar por nome
            cursor = conn.cursor()
            
            cursor.execute(f'''
                SELECT *
                FROM trade_decisions
                ORDER BY timestamp DESC
                LIMIT {limit}
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Erro ao buscar decisões: {e}", exc_info=True)
            return []


# Teste
if __name__ == '__main__':
    # Criar recorder
    recorder = TradeDecisionRecorder(db_path='test_trade_decisions.db')
    
    # Simular análise e setup
    test_analysis = {
        'symbol': 'BTC',
        'current_price': 43200,
        'global': {'global_score': 8.2},
        'technical': {'score': 8.0, 'indicators': {'rsi_14': 58, 'adx': 28}},
        'volume': {'score': 9.0, 'metrics': {'ratio': 1.8}},
        'sentiment': {'score': 7.0, 'details': {}},
        'structure': {'score': 8.0},
        'risk': {'score': 9.0}
    }
    
    test_setup = {
        'direction': 'LONG',
        'entry': 43200,
        'stop_loss': 42450,
        'take_profit': 44100,
        'position_size_usd': 150,
        'confidence': 85,
        'setup_type': 'trend_following'
    }
    
    test_user_decision = {
        'action': 'execute',
        'direction': 'LONG',
        'entry': 43200,
        'stop_loss': 42450,
        'take_profit': 44100,
        'size_usd': 150,
        'notes': 'Teste de registro'
    }
    
    # Registrar decisão
    decision_id = recorder.record_decision(test_analysis, test_setup, test_user_decision)
    print(f"Decisão registrada: {decision_id}")
    
    # Simular outcome
    test_outcome = {
        'pnl_usd': 25.50,
        'pnl_pct': 17.0,
        'success': True,
        'exit_price': 43950,
        'exit_timestamp': datetime.now().isoformat(),
        'duration_minutes': 45,
        'max_drawdown_pct': -0.5
    }
    
    recorder.update_outcome(decision_id, test_outcome)
    
    # Buscar decisões recentes
    recent = recorder.get_recent_decisions(limit=5)
    print(f"\nÚltimas {len(recent)} decisões registradas")
    
    print("="*60)
    print("Trade Recorder testado com sucesso!")
    print("="*60)
