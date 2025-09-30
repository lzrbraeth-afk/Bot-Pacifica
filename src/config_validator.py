"""
Sistema de Validações de Configuração - Bot Pacifica
Valida configurações sem alterar funcionalidade principal

IMPORTANTE: Este módulo apenas VALIDA e AVISA sobre configurações.
Não altera o comportamento do bot, apenas informa sobre possíveis problemas.
"""

import os
import logging
from typing import List, Tuple, Dict, Any

def validate_strategy_config(strategy_type: str) -> Tuple[List[str], List[str]]:
    """
    Valida configurações específicas por estratégia
    
    Args:
        strategy_type: Tipo da estratégia ('grid', 'multi_asset', etc.)
        
    Returns:
        Tuple[errors, warnings]: Lista de erros críticos e avisos
    """
    errors = []
    warnings = []
    
    if strategy_type in ['multi_asset', 'multi_asset_enhanced']:
        # Validar TP/SL para multi-asset
        try:
            tp_percent = float(os.getenv('TAKE_PROFIT_PERCENT', '1.5'))
            sl_percent = float(os.getenv('STOP_LOSS_PERCENT', '2.0'))
            
            # Validações de range
            if tp_percent <= 0 or tp_percent > 10:
                errors.append("TAKE_PROFIT_PERCENT deve estar entre 0.1 e 10")
            if sl_percent <= 0 or sl_percent > 20:
                errors.append("STOP_LOSS_PERCENT deve estar entre 0.1 e 20")
                
            # Validação lógica: SL deve ser maior que TP
            if sl_percent <= tp_percent:
                errors.append("STOP_LOSS_PERCENT deve ser maior que TAKE_PROFIT_PERCENT")
                
            # Avisos de configuração
            if tp_percent > 5:
                warnings.append(f"TAKE_PROFIT_PERCENT={tp_percent}% é muito alto - considere valores menores")
            if sl_percent > 10:
                warnings.append(f"STOP_LOSS_PERCENT={sl_percent}% é muito alto - risco elevado")
                
        except (ValueError, TypeError):
            errors.append("TAKE_PROFIT_PERCENT e STOP_LOSS_PERCENT devem ser números válidos")
            
        # Validar outras configurações multi-asset
        try:
            max_trades = int(os.getenv('MAX_CONCURRENT_TRADES', '3'))
            if max_trades < 1 or max_trades > 20:
                errors.append("MAX_CONCURRENT_TRADES deve estar entre 1 e 20")
            elif max_trades > 10:
                warnings.append(f"MAX_CONCURRENT_TRADES={max_trades} é alto - considere começar com 3-5")
        except (ValueError, TypeError):
            errors.append("MAX_CONCURRENT_TRADES deve ser um número inteiro")
            
    elif strategy_type in ['pure_grid', 'market_making', 'dynamic_grid', 'grid']:
        # Avisar se TP/SL configurado para grid (será ignorado)
        if os.getenv('TAKE_PROFIT_PERCENT') or os.getenv('STOP_LOSS_PERCENT'):
            warnings.append("TP/SL configurado mas será IGNORADO para estratégias de Grid")
            warnings.append("Grid strategies usam apenas ordens limit no sistema de grid")
            
        # Validar configurações específicas do grid
        try:
            grid_levels = int(os.getenv('GRID_LEVELS', '8'))
            if grid_levels < 2 or grid_levels > 100:
                errors.append("GRID_LEVELS deve estar entre 2 e 100")
            elif grid_levels > 50:
                warnings.append(f"GRID_LEVELS={grid_levels} é muito alto - muitas ordens simultâneas")
        except (ValueError, TypeError):
            errors.append("GRID_LEVELS deve ser um número inteiro")
    
    return errors, warnings

def validate_trading_params() -> Tuple[List[str], List[str]]:
    """
    Valida parâmetros gerais de trading
    
    Returns:
        Tuple[errors, warnings]: Lista de erros críticos e avisos
    """
    errors = []
    warnings = []
    
    try:
        # Validação de alavancagem
        leverage = int(os.getenv('LEVERAGE', '10'))
        if leverage < 1 or leverage > 50:
            errors.append("LEVERAGE deve estar entre 1 e 50")
        elif leverage > 20:
            warnings.append(f"LEVERAGE={leverage} é alto - risco elevado, considere 5-15")
        elif leverage == 1:
            warnings.append("LEVERAGE=1 significa sem alavancagem - lucros serão menores")
            
    except (ValueError, TypeError):
        errors.append("LEVERAGE deve ser um número inteiro")
    
    try:
        # Validação de tamanho de posição
        order_size = float(os.getenv('ORDER_SIZE_USD', '35'))
        if order_size < 1 or order_size > 1000:
            errors.append("ORDER_SIZE_USD deve estar entre 1 e 1000")
        elif order_size > 500:
            warnings.append(f"ORDER_SIZE_USD={order_size} é alto - recomendado começar com 20-50")
        elif order_size < 10:
            warnings.append(f"ORDER_SIZE_USD={order_size} é baixo - lucros podem ser mínimos")
            
    except (ValueError, TypeError):
        errors.append("ORDER_SIZE_USD deve ser um número válido")
        
    try:
        # Validação de espaçamento do grid
        spacing = float(os.getenv('GRID_SPACING_PERCENT', '0.2'))
        if spacing < 0.01 or spacing > 5:
            errors.append("GRID_SPACING_PERCENT deve estar entre 0.01 e 5")
        elif spacing < 0.1:
            warnings.append(f"GRID_SPACING_PERCENT={spacing}% muito baixo - muitas ordens próximas")
        elif spacing > 2:
            warnings.append(f"GRID_SPACING_PERCENT={spacing}% alto - grid pode ser menos eficiente")
            
    except (ValueError, TypeError):
        errors.append("GRID_SPACING_PERCENT deve ser um número válido")
        
    try:
        # Validação de intervalo de rebalanceamento
        rebalance_interval = int(os.getenv('REBALANCE_INTERVAL_SECONDS', '60'))
        if rebalance_interval < 10 or rebalance_interval > 3600:
            errors.append("REBALANCE_INTERVAL_SECONDS deve estar entre 10 e 3600")
        elif rebalance_interval < 30:
            warnings.append(f"REBALANCE_INTERVAL_SECONDS={rebalance_interval}s muito baixo - pode sobrecarregar API")
            
    except (ValueError, TypeError):
        errors.append("REBALANCE_INTERVAL_SECONDS deve ser um número inteiro")
    
    return errors, warnings

def validate_api_credentials() -> Tuple[List[str], List[str]]:
    """
    Valida credenciais de API necessárias
    
    Returns:
        Tuple[errors, warnings]: Lista de erros críticos e avisos
    """
    errors = []
    warnings = []
    
    # Validar chaves principais
    main_key = os.getenv('MAIN_PUBLIC_KEY', '').strip()
    agent_key = os.getenv('AGENT_PRIVATE_KEY_B58', '').strip()
    
    if not main_key:
        errors.append("MAIN_PUBLIC_KEY não configurada - bot não poderá operar")
    elif len(main_key) < 32:
        errors.append("MAIN_PUBLIC_KEY muito curta - deve ter pelo menos 32 caracteres")
        
    if not agent_key:
        errors.append("AGENT_PRIVATE_KEY_B58 não configurada - bot não poderá operar")
    elif len(agent_key) < 32:
        errors.append("AGENT_PRIVATE_KEY_B58 muito curta - deve ter pelo menos 32 caracteres")
        
    # Validar endpoints
    api_address = os.getenv('API_ADDRESS', '')
    if not api_address:
        errors.append("API_ADDRESS não configurado")
    elif not api_address.startswith('https://'):
        warnings.append("API_ADDRESS não usa HTTPS - conexão pode ser insegura")
        
    ws_base_url = os.getenv('WS_BASE_URL', '')
    if not ws_base_url:
        warnings.append("WS_BASE_URL não configurado - funcionalidades WebSocket indisponíveis")
    elif not ws_base_url.startswith('wss://'):
        warnings.append("WS_BASE_URL não usa WSS - conexão pode ser insegura")
        
    return errors, warnings

def validate_symbol_config(strategy_type: str) -> Tuple[List[str], List[str]]:
    """
    Valida configurações de símbolos baseado na estratégia
    
    Args:
        strategy_type: Tipo da estratégia
        
    Returns:
        Tuple[errors, warnings]: Lista de erros críticos e avisos
    """
    errors = []
    warnings = []
    
    if strategy_type in ['pure_grid', 'market_making', 'dynamic_grid', 'grid']:
        # Grid strategies usam um símbolo único
        symbol = os.getenv('SYMBOL', 'BTC').upper()
        if not symbol:
            errors.append("SYMBOL não configurado para estratégia de Grid")
        elif len(symbol) < 2:
            errors.append("SYMBOL deve ter pelo menos 2 caracteres")
            
    elif strategy_type in ['multi_asset', 'multi_asset_enhanced']:
        # Multi-asset strategies usam múltiplos símbolos
        symbols_config = os.getenv('SYMBOLS', 'AUTO')
        if symbols_config == 'AUTO':
            warnings.append("SYMBOLS=AUTO - bot detectará símbolos automaticamente")
        elif not symbols_config:
            errors.append("SYMBOLS não configurado para estratégia Multi-Asset")
        else:
            # Validar lista de símbolos
            symbols = [s.strip().upper() for s in symbols_config.split(',') if s.strip()]
            if len(symbols) == 0:
                errors.append("Lista SYMBOLS está vazia")
            elif len(symbols) > 50:
                warnings.append(f"SYMBOLS={len(symbols)} símbolos - considere reduzir para 10-20")
                
    return errors, warnings

def run_all_validations(strategy_type: str) -> Dict[str, Any]:
    """
    Executa todas as validações e retorna relatório consolidado
    
    Args:
        strategy_type: Tipo da estratégia a ser validada
        
    Returns:
        Dict com resultados das validações
    """
    all_errors = []
    all_warnings = []
    
    # Executar todas as validações
    validation_functions = [
        lambda: validate_strategy_config(strategy_type),
        validate_trading_params,
        validate_api_credentials,
        lambda: validate_symbol_config(strategy_type)
    ]
    
    for validation_func in validation_functions:
        try:
            errors, warnings = validation_func()
            all_errors.extend(errors)
            all_warnings.extend(warnings)
        except Exception as e:
            all_warnings.append(f"Erro durante validação: {str(e)}")
    
    # Gerar relatório
    return {
        'strategy_type': strategy_type,
        'errors': all_errors,
        'warnings': all_warnings,
        'has_critical_errors': len(all_errors) > 0,
        'total_issues': len(all_errors) + len(all_warnings),
        'validation_passed': len(all_errors) == 0
    }

def print_validation_report(validation_result: Dict[str, Any], logger=None) -> None:
    """
    Imprime relatório de validação formatado
    
    Args:
        validation_result: Resultado das validações
        logger: Logger para output (opcional, usa print se None)
    """
    def log_message(level: str, message: str):
        if logger:
            getattr(logger, level.lower())(message)
        else:
            print(f"[{level.upper()}] {message}")
    
    strategy = validation_result['strategy_type']
    errors = validation_result['errors']
    warnings = validation_result['warnings']
    
    log_message('info', "=" * 60)
    log_message('info', f"🔧 RELATÓRIO DE VALIDAÇÃO - {strategy.upper()}")
    log_message('info', "=" * 60)
    
    if validation_result['validation_passed']:
        log_message('info', "✅ TODAS as validações passaram!")
    else:
        log_message('error', f"❌ {len(errors)} ERRO(S) CRÍTICO(S) encontrado(s)")
        
    if warnings:
        log_message('warning', f"⚠️ {len(warnings)} AVISO(S) encontrado(s)")
        
    # Mostrar erros críticos
    if errors:
        log_message('error', "\n🚨 PROBLEMAS CRÍTICOS:")
        for i, error in enumerate(errors, 1):
            log_message('error', f"  {i}. {error}")
            
    # Mostrar avisos
    if warnings:
        log_message('warning', "\n⚠️ AVISOS:")
        for i, warning in enumerate(warnings, 1):
            log_message('warning', f"  {i}. {warning}")
            
    log_message('info', "=" * 60)
    
    if errors:
        log_message('error', "❌ Bot pode não funcionar corretamente com estas configurações")
    else:
        log_message('info', "✅ Configurações validadas - bot pronto para executar")

# Funções utilitárias para integração
def validate_config_and_warn(strategy_type: str, logger=None) -> bool:
    """
    Executa validações e exibe relatório - função de conveniência
    
    Args:
        strategy_type: Tipo da estratégia
        logger: Logger para output
        
    Returns:
        True se não há erros críticos, False caso contrário
    """
    try:
        result = run_all_validations(strategy_type)
        print_validation_report(result, logger)
        return result['validation_passed']
    except Exception as e:
        if logger:
            logger.error(f"Erro durante validação: {e}")
        else:
            print(f"[ERROR] Erro durante validação: {e}")
        return True  # Não bloquear execução por erro de validação

if __name__ == "__main__":
    # Teste das validações
    import sys
    strategy = sys.argv[1] if len(sys.argv) > 1 else 'market_making'
    
    print("🔧 Testando Sistema de Validações")
    print(f"Estratégia: {strategy}")
    print("-" * 40)
    
    result = run_all_validations(strategy)
    print_validation_report(result)