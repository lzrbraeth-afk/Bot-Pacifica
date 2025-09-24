# 🛡️ Sistema AUTO_CLOSE - Documentação Técnica

## Visão Geral

O sistema **AUTO_CLOSE** é uma funcionalidade crítica de **gestão de risco** que monitora continuamente o tamanho da posição e executa ações automáticas de proteção quando limites são excedidos.

## ⚙️ Configuração

### Variáveis de Ambiente (.env)

```ini
# Ativação do sistema
AUTO_CLOSE_ON_MAX_POSITION=true

# Estratégia de execução
AUTO_CLOSE_STRATEGY=hybrid  # hybrid|cancel_orders|force_sell|stop_buy

# Limites e percentuais
MAX_POSITION_SIZE_USD=1000  # Limite máximo da posição em USD
AUTO_CLOSE_PERCENTAGE=20    # Percentual da posição a vender em emergência

# Parâmetros relacionados
LEVERAGE=10                 # Usado no cálculo: posição = margin_used × leverage
```

### Valores Recomendados

| Parâmetro | Valor Sugerido | Explicação |
|-----------|----------------|------------|
| `AUTO_CLOSE_ON_MAX_POSITION` | `true` | Sempre ativar para proteção |
| `AUTO_CLOSE_STRATEGY` | `hybrid` | Estratégia balanceada e inteligente |
| `MAX_POSITION_SIZE_USD` | `1000` | Ajuste conforme capital e tolerância ao risco |
| `AUTO_CLOSE_PERCENTAGE` | `20` | 20% é suficiente para maioria dos casos |

## 🔄 Funcionamento

### 1. Monitoramento Contínuo

O sistema monitora a posição a cada atualização de estado:

```python
def _check_position_size_and_auto_close(self):
    position_value = self.margin_used * self.leverage
    
    if self.auto_close_on_limit and position_value > self.max_position_size:
        self.logger.warning(f"🚨 POSIÇÃO EXCEDEU LIMITE: ${position_value:.2f} > ${self.max_position_size:.2f}")
        self._auto_close_positions()
```

### 2. Cálculo da Posição

```
Posição USD = Margem Utilizada × Alavancagem
```

**Exemplo**:
- Margem utilizada: $120
- Alavancagem: 10x
- **Posição calculada: $1.200**

### 3. Detecção e Ativação

Quando `Posição USD > MAX_POSITION_SIZE_USD`, o sistema:

1. Registra alerta nos logs
2. Executa a estratégia configurada
3. Monitora resultado da ação
4. Registra auditoria completa

## 🎯 Estratégias AUTO_CLOSE

### HYBRID (Recomendada) 🏆

Estratégia inteligente que combina cancelamento conservador com venda assertiva:

```python
def _auto_close_positions(self):
    if self.auto_close_strategy == 'hybrid':
        # STEP 1: Cancelar ordens SELL distantes
        canceled_value = self._cancel_distant_sell_orders()
        
        # STEP 2: Se insuficiente, vender % da posição
        excess = self._calculate_position_excess()
        if canceled_value < excess:
            self._force_partial_sell()
```

**Fluxo HYBRID**:
1. **Fase Conservadora**: Cancela ordens SELL >2% do preço atual
2. **Fase Assertiva**: Se ainda excede limite, vende percentual definido
3. **Resultado**: Redução eficiente com mínimo impacto no mercado

### CANCEL_ORDERS

Estratégia conservadora que apenas cancela ordens:

- ✅ **Vantagem**: Não impacta posição diretamente
- ⚠️ **Limitação**: Pode ser insuficiente em situações críticas
- 🎯 **Uso**: Para traders que preferem intervenção manual

### FORCE_SELL

Estratégia assertiva que vende imediatamente:

- ✅ **Vantagem**: Ação imediata e eficaz
- ⚠️ **Limitação**: Pode causar slippage em mercados voláteis
- 🎯 **Uso**: Para situações de alta volatilidade

### STOP_BUY

Estratégia preventiva que para novas compras:

- ✅ **Vantagem**: Evita aumento da posição
- ⚠️ **Limitação**: Não reduz posição existente
- 🎯 **Uso**: Complementar a outras estratégias

## 📊 Cenários de Uso

### Cenário 1: Posição Gradual
```
Posição: $800 → $1.050 (limite $1.000)
Ação: HYBRID cancela ordens distantes
Resultado: Posição reduz para $980
```

### Cenário 2: Spike de Volatilidade
```
Posição: $800 → $1.300 (limite $1.000)
Ação: HYBRID falha ao cancelar → vende 20%
Resultado: Posição reduz para $1.040
```

### Cenário 3: Mercado Lateral
```
Posição: $950 → $1.020 (limite $1.000)
Ação: HYBRID cancela 2 ordens SELL distantes
Resultado: Posição volta para $980
```

## 🔧 Implementação Técnica

### Principais Funções

#### _check_position_size_and_auto_close()
- **Propósito**: Monitora e detecta excesso de posição
- **Frequência**: A cada `update_account_state()`
- **Ação**: Chama `_auto_close_positions()` se necessário

#### _auto_close_positions()
- **Propósito**: Orquestra estratégia de auto-close
- **Parâmetros**: Usa configurações do `.env`
- **Estratégias**: Delega para funções específicas

#### _cancel_distant_sell_orders()
- **Propósito**: Cancela ordens SELL >2% do preço atual
- **Retorno**: Valor total cancelado em USD
- **Uso**: Primeira fase da estratégia HYBRID

#### _force_partial_sell()
- **Propósito**: Cria ordem de venda de % da posição
- **Cálculo**: `quantidade = posição × (AUTO_CLOSE_PERCENTAGE / 100)`
- **Uso**: Segunda fase da estratégia HYBRID

### Integração com Position Manager

```python
class PositionManager:
    def __init__(self, auth_client):
        # Configurações AUTO_CLOSE
        self.auto_close_on_limit = os.getenv('AUTO_CLOSE_ON_MAX_POSITION', 'false').lower() == 'true'
        self.auto_close_strategy = os.getenv('AUTO_CLOSE_STRATEGY', 'hybrid')
        self.auto_close_percentage = float(os.getenv('AUTO_CLOSE_PERCENTAGE', 20))
        self.max_position_size = float(os.getenv('MAX_POSITION_SIZE_USD', 1000))
    
    def update_account_state(self):
        # ... atualizar dados da conta ...
        
        # Verificar auto-close após atualização
        if self.auto_close_on_limit:
            self._check_position_size_and_auto_close()
```

## 📋 Logs e Auditoria

### Logs de Monitoramento
```
2025-09-24 09:26:50 | INFO | 🔍 Verificando tamanho da posição: $68.53 vs limite $1000.00
2025-09-24 09:26:50 | INFO | 💡 Debug cálculo posição: margin_used=$6.85 * leverage=10 = $68.53
```

### Logs de Ativação
```
2025-09-24 12:15:30 | WARNING | 🚨 POSIÇÃO EXCEDEU LIMITE: $1200.00 > $1000.00
2025-09-24 12:15:30 | INFO | 🔧 Executando AUTO_CLOSE estratégia: hybrid
2025-09-24 12:15:31 | INFO | 📋 HYBRID Step 1: Cancelando ordens SELL distantes
2025-09-24 12:15:32 | INFO | ✅ Canceladas 3 ordens SELL, valor total: $180.00
2025-09-24 12:15:32 | INFO | 📋 HYBRID Step 2: Executando venda parcial de 20%
2025-09-24 12:15:33 | INFO | ✅ Ordem de venda criada: $240.00
```

### Logs de Resultado
```
2025-09-24 12:15:35 | INFO | 🎯 AUTO_CLOSE concluído: posição $1200→$980 (redução $220)
```

## ⚡ Validação e Testes

### Teste de Configuração
```bash
python validate_auto_close.py
```

### Teste de Simulação
```bash
python test_auto_close_simulation.py
```

### Verificações Automáticas
- ✅ Configuração válida no `.env`
- ✅ Funções implementadas corretamente
- ✅ Integração com API funcional
- ✅ Logs estruturados ativos

## 🚨 Alertas e Considerações

### ⚠️ Importantes
- Sistema é **preventivo**, não substitui monitoramento ativo
- Em mercados muito voláteis, pode ser insuficiente
- Teste sempre com posições pequenas primeiro
- Monitore logs para ajustar parâmetros

### 🎯 Boas Práticas
1. **Limite Conservador**: Configure `MAX_POSITION_SIZE_USD` abaixo do capital total
2. **Percentual Adequado**: `AUTO_CLOSE_PERCENTAGE` entre 15-25%
3. **Estratégia HYBRID**: Recomendada para maioria dos casos
4. **Monitoramento**: Acompanhe logs regularmente
5. **Backtesting**: Teste configurações antes de usar em produção

## 🔄 Roadmap

### Versão Atual (v1.0)
- ✅ Monitoramento automático
- ✅ 4 estratégias disponíveis
- ✅ Logs detalhados
- ✅ Integração completa

### Próximas Versões
- 🔄 **v1.1**: Alertas via webhook/email
- 🔄 **v1.2**: Machine Learning para otimização de parâmetros
- 🔄 **v1.3**: Interface web para monitoramento
- 🔄 **v1.4**: Integração com múltiplas exchanges

---

## 📞 Suporte

- **Issues**: [GitHub Issues](https://github.com/lzrbraeth-afk/Bot-Pacifica/issues)
- **Discussões**: [GitHub Discussions](https://github.com/lzrbraeth-afk/Bot-Pacifica/discussions)
- **Comunidade**: [Coleta Cripto](https://x.com/Coleta_Cripto)

---

*Documentação atualizada em 24/09/2025 - Sistema AUTO_CLOSE v1.0*