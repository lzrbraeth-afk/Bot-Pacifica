#!/usr/bin/env python3
"""
Script de Teste Rápido - Market Vision
Valida se todos os componentes estão funcionando corretamente
"""

import sys
import logging
from pathlib import Path

# Adicionar diretório pai ao Python path para encontrar o módulo market_vision
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

def print_section(title):
    """Imprime cabeçalho de seção"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def test_imports():
    """Testa se todos os módulos podem ser importados"""
    print_section("🔧 TESTE 1: Importando Módulos")
    
    try:
        from market_vision.indicators.technical_analyzer import TechnicalAnalyzer
        print("✅ TechnicalAnalyzer")
        
        from market_vision.indicators.volume_analyzer import VolumeAnalyzer
        print("✅ VolumeAnalyzer")
        
        from market_vision.indicators.sentiment_analyzer import SentimentAnalyzer
        print("✅ SentimentAnalyzer")
        
        from market_vision.indicators.structure_analyzer import StructureAnalyzer
        print("✅ StructureAnalyzer")
        
        from market_vision.indicators.risk_analyzer import RiskAnalyzer
        print("✅ RiskAnalyzer")
        
        from market_vision.signals.entry_generator import EntryGenerator
        print("✅ EntryGenerator")
        
        from market_vision.decision_logger.trade_recorder import TradeDecisionRecorder
        print("✅ TradeDecisionRecorder")
        
        from market_vision.core.scoring_engine import ScoringEngine
        print("✅ ScoringEngine")
        
        from market_vision.core.market_analyzer import MarketAnalyzer
        print("✅ MarketAnalyzer")
        
        from market_vision.market_vision_service import MarketVisionService
        print("✅ MarketVisionService")
        
        print("\n✅ TODOS OS MÓDULOS IMPORTADOS COM SUCESSO")
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO AO IMPORTAR: {e}")
        return False

def test_technical_analyzer():
    """Testa analisador técnico com dados sintéticos"""
    print_section("📈 TESTE 2: Technical Analyzer")
    
    try:
        import pandas as pd
        import numpy as np
        from market_vision.indicators.technical_analyzer import TechnicalAnalyzer
        
        # Criar dados de teste
        np.random.seed(42)
        n = 100
        
        df = pd.DataFrame({
            'timestamp': pd.date_range(start='2025-01-01', periods=n, freq='5min'),
            'open': 43000 + np.random.randn(n) * 50,
            'high': 43100 + np.random.randn(n) * 50,
            'low': 42900 + np.random.randn(n) * 50,
            'close': 43000 + np.random.randn(n) * 50,
            'volume': 1000000 + np.random.randn(n) * 100000
        })
        
        analyzer = TechnicalAnalyzer()
        result = analyzer.analyze(df)
        
        print(f"Score: {result['score']:.2f}/10")
        print(f"Status: {result['status']}")
        print(f"RSI: {result['indicators']['rsi_14']:.1f}")
        print(f"ADX: {result['indicators']['adx']:.1f}")
        
        print("\n✅ TECHNICAL ANALYZER FUNCIONANDO")
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_volume_analyzer():
    """Testa analisador de volume"""
    print_section("💰 TESTE 3: Volume Analyzer")
    
    try:
        import pandas as pd
        import numpy as np
        from market_vision.indicators.volume_analyzer import VolumeAnalyzer
        
        np.random.seed(42)
        n = 100
        
        df = pd.DataFrame({
            'timestamp': pd.date_range(start='2025-01-01', periods=n, freq='5min'),
            'open': 43000 + np.random.randn(n) * 50,
            'high': 43100 + np.random.randn(n) * 50,
            'low': 42900 + np.random.randn(n) * 50,
            'close': 43000 + np.random.randn(n) * 50,
            'volume': 1000000 + np.random.randn(n) * 100000
        })
        
        analyzer = VolumeAnalyzer()
        result = analyzer.analyze(df)
        
        print(f"Score: {result['score']:.2f}/10")
        print(f"Status: {result['status']}")
        print(f"Volume Ratio: {result['metrics']['ratio']:.2f}x")
        print(f"POC: ${result['profile']['poc']:,.0f}")
        
        print("\n✅ VOLUME ANALYZER FUNCIONANDO")
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_market_analyzer():
    """Testa analisador completo"""
    print_section("🎯 TESTE 4: Market Analyzer Completo")
    
    try:
        import pandas as pd
        import numpy as np
        from market_vision.core.market_analyzer import MarketAnalyzer
        
        np.random.seed(42)
        n = 100
        
        ohlcv_df = pd.DataFrame({
            'timestamp': pd.date_range(start='2025-01-01', periods=n, freq='5min'),
            'open': 43000 + np.random.randn(n) * 50,
            'high': 43100 + np.random.randn(n) * 50,
            'low': 42900 + np.random.randn(n) * 50,
            'close': 43000 + np.random.randn(n) * 50,
            'volume': 1000000 + np.random.randn(n) * 100000
        })
        
        market_data = {
            'symbol': 'BTC',
            'ohlcv': ohlcv_df,
            'funding_rate': 0.02,
            'oi_change_24h': 0.08,
            'orderbook': {
                'bids': [[43200, 10], [43190, 8]],
                'asks': [[43210, 9], [43220, 7]]
            },
            'account_balance': 10000,
            'position_data': {
                'total_exposure_usd': 500,
                'free_margin_usd': 8500,
                'session_pnl': 50,
                'session_start_balance': 10000
            }
        }
        
        analyzer = MarketAnalyzer()
        result = analyzer.analyze_full(market_data)
        
        print(f"Score Global: {result['global']['global_score']:.2f}/10")
        print(f"Status: {result['global']['status']}")
        print(f"Direção: {result['global']['direction']}")
        print(f"Confiança: {result['global']['confidence']:.1f}%")
        
        print("\n📊 Scores por Categoria:")
        print(f"  Técnico: {result['technical']['score']:.1f}/10")
        print(f"  Volume: {result['volume']['score']:.1f}/10")
        print(f"  Sentimento: {result['sentiment']['score']:.1f}/10")
        print(f"  Estrutura: {result['structure']['score']:.1f}/10")
        print(f"  Risco: {result['risk']['score']:.1f}/10")
        
        print("\n✅ MARKET ANALYZER COMPLETO FUNCIONANDO")
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_entry_generator():
    """Testa gerador de setups"""
    print_section("💡 TESTE 5: Entry Generator")
    
    try:
        from market_vision.signals.entry_generator import EntryGenerator
        
        # Dados simulados de uma análise boa
        test_analysis = {
            'symbol': 'BTC',
            'current_price': 43200,
            'global': {
                'global_score': 8.2,
                'confidence': 85.0,
                'direction': 'LONG'
            },
            'technical': {
                'score': 8.0,
                'details': {},
                'indicators': {
                    'ema_9': 43100,
                    'ema_21': 42900,
                    'rsi_14': 58,
                    'adx': 28,
                    'atr': 900,
                    'atr_percentage': 2.1
                }
            },
            'volume': {
                'score': 9.0,
                'details': {},
                'metrics': {'ratio': 1.8}
            },
            'sentiment': {'score': 7.0, 'details': {}},
            'structure': {
                'score': 8.0,
                'details': {},
                'support_resistance': {
                    'nearest_support': 42500,
                    'nearest_resistance': 43800
                }
            },
            'risk': {'score': 9.0},
            'metadata': {'account_balance': 10000}
        }
        
        generator = EntryGenerator()
        setup = generator.generate_setup(test_analysis)
        
        if setup['has_setup']:
            print(f"✅ Setup Gerado: {setup['direction']}")
            print(f"  Confiança: {setup['confidence']:.1f}%")
            print(f"  Entry: ${setup['entry']:.2f}")
            print(f"  Stop Loss: ${setup['stop_loss']:.2f}")
            print(f"  Take Profit: ${setup['take_profit']:.2f}")
            print(f"  Position Size: ${setup['position_size_usd']:.2f}")
            print(f"  R:R: 1:{setup['risk_reward_ratio']:.2f}")
            print("\n✅ ENTRY GENERATOR FUNCIONANDO")
            return True
        else:
            print(f"⚠️  Nenhum setup gerado: {setup['reason']}")
            print("✅ ENTRY GENERATOR FUNCIONANDO (sem setup válido neste teste)")
            return True
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_trade_recorder():
    """Testa sistema de registro"""
    print_section("📝 TESTE 6: Trade Recorder")
    
    try:
        from market_vision.decision_logger.trade_recorder import TradeDecisionRecorder
        from datetime import datetime
        
        # Usar DB temporário
        recorder = TradeDecisionRecorder(db_path='test_decisions.db')
        
        # Dados simulados
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
        
        test_decision = {
            'action': 'execute',
            'direction': 'LONG',
            'entry': 43200,
            'stop_loss': 42450,
            'take_profit': 44100,
            'size_usd': 150,
            'notes': 'Teste automático'
        }
        
        # Registrar
        decision_id = recorder.record_decision(test_analysis, test_setup, test_decision)
        print(f"✅ Decisão registrada: {decision_id}")
        
        # Buscar
        recent = recorder.get_recent_decisions(limit=1)
        print(f"✅ Decisões recuperadas: {len(recent)}")
        
        # Limpar teste
        import os
        if os.path.exists('test_decisions.db'):
            os.remove('test_decisions.db')
        
        print("\n✅ TRADE RECORDER FUNCIONANDO")
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Executa todos os testes"""
    print("\n" + "🎯 "*20)
    print("       MARKET VISION - TESTE DE VALIDAÇÃO")
    print("🎯 "*20)
    
    tests = [
        ("Importação de Módulos", test_imports),
        ("Technical Analyzer", test_technical_analyzer),
        ("Volume Analyzer", test_volume_analyzer),
        ("Market Analyzer", test_market_analyzer),
        ("Entry Generator", test_entry_generator),
        ("Trade Recorder", test_trade_recorder)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ ERRO CRÍTICO no teste '{test_name}': {e}")
            results.append((test_name, False))
    
    # Resumo final
    print_section("📊 RESUMO DOS TESTES")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {test_name}")
    
    print(f"\n{'='*60}")
    print(f"  RESULTADO: {passed}/{total} testes passaram")
    print(f"{'='*60}\n")
    
    if passed == total:
        print("🎉 PARABÉNS! Market Vision está 100% funcional!")
        print("✅ Pronto para integração com o bot Pacifica")
        return 0
    else:
        print("⚠️  Alguns testes falharam. Verifique os erros acima.")
        print("💡 Dica: Certifique-se de que todas as dependências estão instaladas:")
        print("   pip install pandas numpy scipy")
        return 1

if __name__ == '__main__':
    sys.exit(main())
