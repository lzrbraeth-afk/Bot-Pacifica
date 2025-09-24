# Pacifica Trading Bot

Bot de **grid trading** e **scalping** para a corretora **Pacifica** com quatro abordagens: **Pure Grid** (clássica) e **Market-Making Grid** (dinâmica), **multi_asset** (scalping basico compara 3 preços (atual + 2 anteriores) , **multi_asset_enhanced** (SMA, RSI, Momentum, Volatility, Confirmation)
Inclui gerenciamento de risco, métricas de performance e logs detalhados.

> **⚠️ ATENÇÃO: RISCO ELEVADO**

O trading de contratos perpétuos com alavancagem envolve **altos riscos financeiros**, podendo resultar na perda total do capital investido. Este bot é fornecido **"no estado em que se encontra"**, sem garantias de desempenho, precisão ou lucratividade.

### Recomendações Importantes
- **Teste extensivamente**: Antes de usar o bot em um ambiente real, realize testes completos com valores baixos em uma conta de demonstração ou com capital que você está disposto a perder.
- **Use com cautela**: Bots automatizados podem amplificar erros ou reagir de forma inesperada em mercados voláteis.
- **Eduque-se**: Compreenda completamente os riscos do trading alavancado antes de utilizar este software.
- **Gerencie riscos**: Nunca invista mais do que você pode perder. Configure limites rigorosos de perda e monitore o bot regularmente.

**O desenvolvedor não se responsabiliza por perdas financeiras ou danos decorrentes do uso deste bot. Use por sua conta e risco.**

Leia o arquivo [DISCLAIMER](DISCLAIMER.md).



---

## ✨ Principais recursos

- Estratégias: **Pure Grid**, **Market Making Grid** e **Multi-Asset**
- Rebalanceamento automático e deslocamento de grid por limiar
- **Multi-Asset Trading** com gerenciamento individual de risco por símbolo
- Gestão de margem, limite de ordens e tamanho máximo de posição
- **Sistema AUTO_CLOSE** com estratégia híbrida para proteção automática de risco
- **Loss Management** especializado para cenários de alta volatilidade
- Logs estruturados (arquivo e console) e *shutdown* gracioso
- **PerformanceTracker** com métricas como *win rate*, *drawdown*, *Sharpe/Sortino*, *profit factor*
- Arquivo `.env` com configuração declarativa

## 🧱 Arquitetura (alto nível)

```
grid_bot.py            # Orquestração do bot e logging
pacifica_auth.py       # Cliente de API (REST/WebSocket) da Pacifica
grid_calculator.py     # Cálculo de níveis do grid e tamanhos
grid_strategy.py       # Estratégia Pure Grid / Market-Making Grid
position_manager.py    # Saldo, margem, ordens e posições
performance_tracker.py # Métricas e relatórios
.env.example           # Modelo de configuração
```

## 🚀 Instalação

### 1) Pré-requisitos
a. Python 3.10+ (recomendado 3.12) 

. Baixe o instalador no [site oficial](https://www.python.org/downloads/).

. Durante a instalação na primeira tela, selecione todas as opções

![Tela 1 - Selecionar componentes](docs/images/Setup_Python_01.png)

. Na próxima tela, marque **Add Python to PATH**:

![Tela 2 - Add Python to PATH](docs/images/Setup_Python_02.png)

Anote o caminho informado em customize install location ou altere para um caminho mais facil como c:\python3

. Next, Next, Next até o final

. Testar a instalação do python. Abra o Prompt de Comando, Powershell ou Terminal e digite:

```
  python --version
  pip --version
```

Se aparecer a versão está ok ✅

* se não mostrar a versão é porque o PATH ainda não está ativado e precisa de um reboot. Se quiser testar sem o reboot, digite o comando com o caminho completo (exemplo c:\python3\python.exe --version)

b `git` instalado (opcional)

. Baixe em git-scm.com/download/win

. Execute o instalador → Next, Next, Next até o final, só confira estas opções:

    Git from the command line and also from 3rd-party software (adiciona o Git ao PATH).

    Enable Git Credential Manager (facilita login no GitHub, pode deixar marcado).

    O resto pode deixar padrão.

c. Teste no Prompt, Powershell ou Terminal:

```
git --version
```

Se aparecer a versão está ok ✅

### 2) Clonar o repositório (necessário git) ou fazer download

Opção 1) Entrar no repositório, clicar em Code e selecionar a opção download ZIP. Extraia o arquivo ZIP em uma pasta que será usada para a execução do Bot (anote o caminho desta pasta). 

Opção 2) Crie manualmente uma pasta e entre no powershell ou terminal e caminhe até a pasta. Depois execute: 

```bash
git clone https://github.com/lzrbraeth-afk/pacifica-grid-bot.git
cd pacifica-grid-bot
```

### 3) Ambiente virtual

Abra o powershell ou terminal, navegue até a pasta onde está o bot e confirme que os arquivos estão aparecendo. Na lista tem que aparecer principalmente grid_bot.py, .env.example e a pasta src.

Digite um comando de cada vez no **Windows (PowerShell) ou Terminal:**
```
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Ou se estiver usando **Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4) Gerar chave API na corretora

Na corretora entre na página API KEY (https://app.pacifica.fi/apikey), clique em generate e copie o codigo que vai surgir e cole no campo AGENT_PRIVATE_KEY_B58 do arquivo .env (etapa descrita abaixo). Por enquanto pode só copiar esta chave e depois clicar em create para que a chave seja aprovada com sua carteira. Depois de autorizado pode seguir para o próximo passo. 

### 5) Configuração (.env)

Renomeie o arquivo de exemplo e edite os valores. A melhor forma de fazer isto é ir no windows explorer e renomear o arquivo de .env.example para .env

Lembre-se de manter o nome com o ponto no inicio. Depois abra o arquivo e edite-o no notepad ou qualquer outro editor de texto.

Edite **MAIN_PUBLIC_KEY** e **AGENT_PRIVATE_KEY_B58** e demais parâmetros conforme sua preferência (ver seção Configuração).

No campo MAIN_PUBLIC_KEY você inclui o endereço publico da sua carteira usada na corretora e no campo AGENT_PRIVATE_KEY_B58 vai colar a chave API que vai ser gerada na corretora, conforme orientação anterior. 

## ▶️ Como executar

Na raiz da pasta do bot, a mesma que tem o arquivo .env, digite o comando: 

```bash
python grid_bot.py
```

Para encerrar com segurança: `Ctrl + C` (o bot finaliza e imprime um resumo).


## ⚙️ Configuração (.env)

Parâmetros essenciais:

```ini
# API / Segurança
MAIN_PUBLIC_KEY= # Inserir seu endereco da carteira SOL
AGENT_PRIVATE_KEY_B58= # Inserir a chave privada gerada durante a criação da API
API_ADDRESS=https://api.pacifica.fi/api/v1
WS_BASE_URL=wss://ws.pacifica.fi/ws

# Ativo e alavancagem  
SYMBOL=SOL
LEVERAGE=10

# Estratégia (pure_grid | market_making | multi_asset)
STRATEGY_TYPE=multi_asset

# Multi-Asset Trading
SYMBOLS=BTC,ETH,SOL,AVAX  # ou AUTO para todos os símbolos
POSITION_SIZE_USD=20
MAX_CONCURRENT_TRADES=3
PRICE_CHANGE_THRESHOLD=0.3

# TP/SL Avançado
AUTO_CLOSE_ENABLED=true
STOP_LOSS_PERCENT=2.0
TAKE_PROFIT_PERCENT=1.5
USE_API_TP_SL=true
TRAILING_STOP_ENABLED=false
TRAILING_STOP_PERCENT=0.5
MAX_POSITION_TIME_MINUTES=60

# Grid (básico)
GRID_LEVELS=8
GRID_SPACING_PERCENT=0.2
GRID_DISTRIBUTION=symmetric
GRID_MODE=maker

# Risco e Auto-Close
MARGIN_SAFETY_PERCENT=20
MAX_OPEN_ORDERS=20
MAX_POSITION_SIZE_USD=1000

# Sistema AUTO_CLOSE (Proteção Automática)
AUTO_CLOSE_ON_MAX_POSITION=true
AUTO_CLOSE_STRATEGY=hybrid  # hybrid|cancel_orders|force_sell|stop_buy
AUTO_CLOSE_PERCENTAGE=20

# Operação
CHECK_BALANCE_BEFORE_ORDER=true
CLEAN_ORDERS_ON_START=false
LOG_LEVEL=INFO
REBALANCE_INTERVAL_SECONDS=60
```

> **Dica**: Comece conservador (menos níveis, maior espaçamento, ordem menor) e aumente aos poucos.

## Video com passo a passo para instalar o BOT, depois de instalado o PYTHON 

<https://www.youtube.com/watch?v=cKypCQwXctc>

## 🎯 Estratégias Disponíveis

### Multi-Asset Trading (Recomendada)
Trading simultâneo em múltiplos ativos com gerenciamento individual de risco:

```ini
STRATEGY_TYPE=multi_asset
SYMBOLS=BTC,ETH,SOL,AVAX     # Símbolos específicos
# ou SYMBOLS=AUTO            # Busca todos disponíveis

POSITION_SIZE_USD=20         # Tamanho individual por ativo  
MAX_CONCURRENT_TRADES=3      # Máximo de posições simultâneas
PRICE_CHANGE_THRESHOLD=0.3   # % mínima para entrada
```

**Vantagens:**
- Diversificação automática de risco
- Gerenciamento independente por símbolo  
- AUTO_CLOSE individual por posição
- Stop Loss e Take Profit configuráveis

### Pure Grid (Clássica)
Grid tradicional com range fixo de preços:

```ini
STRATEGY_TYPE=pure_grid
RANGE_MIN=48000             # Preço mínimo do range
RANGE_MAX=52000             # Preço máximo do range
GRID_LEVELS=20              # Número de níveis
```

### Market Making Grid (Dinâmica)
Grid que se adapta ao movimento do preço:

```ini  
STRATEGY_TYPE=market_making
GRID_SHIFT_THRESHOLD_PERCENT=1.0  # % para rebalanceamento
REBALANCE_INTERVAL_SECONDS=60     # Intervalo de verificação
```

## 📊 Métricas e logs

- Logs são salvos em `logs/` com timestamp (ex.: `grid_bot_YYYYMMDD_HHMMSS.log`)
- Relatório de performance (win rate, drawdown, Sharpe etc.) é atualizado ao longo da sessão

## 🛡️ Sistema AUTO_CLOSE (Proteção Automática)

O bot inclui um sistema de **proteção automática** que monitora o tamanho da posição e **executa ordens reais** de emergência quando necessário:

> ⚠️ **IMPORTANTE**: AUTO_CLOSE executa **ordens reais** na API (não apenas logs)

### ⚙️ Configuração AUTO_CLOSE

```ini
AUTO_CLOSE_ON_MAX_POSITION=true     # Ativa proteção automática
AUTO_CLOSE_STRATEGY=hybrid          # Estratégia: hybrid|cancel_orders|force_sell|stop_buy
AUTO_CLOSE_PERCENTAGE=20            # % da posição a vender em emergência
MAX_POSITION_SIZE_USD=1000          # Limite máximo da posição em USD
```

### 🎯 Como Funciona

1. **Monitoramento Contínuo**: Calcula `posição = margin_used × leverage`
2. **Detecção**: Se posição > `MAX_POSITION_SIZE_USD`, ativa AUTO_CLOSE
3. **Execução Real**: Cancela/cria ordens via API Pacifica
4. **Estratégia HYBRID** (recomendada):
   - **Step 1**: Cancela ordens SELL distantes (>2% do preço atual)
   - **Step 2**: Se insuficiente, vende `AUTO_CLOSE_PERCENTAGE`% da posição

### 📋 Estratégias Disponíveis

- `hybrid`: Cancela ordens primeiro, depois vende parcialmente (recomendado)
- `cancel_orders`: Apenas cancela ordens distantes  
- `force_sell`: Vende percentual da posição imediatamente
- `stop_buy`: **Loss Management** - cancela apenas ordens de compra

### 🔴 Loss Management (stop_buy)

Estratégia especializada para cenários de alta volatilidade:
- Cancela **apenas ordens de COMPRA**
- **Mantém posição atual** (não vende)
- Evita acúmulo durante quedas de mercado
- Útil quando se espera recuperação

### 🧪 Validação do Sistema

```bash
# Testar se AUTO_CLOSE está funcionando
python validate_auto_close.py

# Simular cenário de emergência (sem executar)
python test_auto_close_simulation.py
```

> 📖 **Documentação AUTO_CLOSE**:
> - [Documentação Técnica Completa](docs/AUTO_CLOSE.md)
> - [Guia de Migração](docs/AUTO_CLOSE_MIGRATION.md) 
> - [Relatório de Validação](docs/AUTO_CLOSE_VALIDATION_REPORT.md)

## 🧪 Troubleshooting e Validação

### Scripts de Validação Automática

```bash
# Validar se AUTO_CLOSE está configurado corretamente
python validate_auto_close.py

# Simular cenário de emergência (sem executar ordens reais)
python test_auto_close_simulation.py

# Testar todas as estratégias individualmente  
python test_final_validation.py
```

### Interpretação dos Resultados

**✅ Sistema Funcionando:**
```
🎯 SCORE DE VALIDAÇÃO: 6/6  
🎉 SISTEMA AUTO_CLOSE HYBRID TOTALMENTE FUNCIONAL!
```

**❌ Problemas Comuns:**

| Erro | Causa Provável | Solução |
|------|----------------|---------|
| Score < 6/6 | Configuração .env incorreta | Verificar variáveis AUTO_CLOSE |
| API Error 401 | Chave privada inválida | Regenerar AGENT_PRIVATE_KEY_B58 |
| "Estratégia desconhecida" | Nome incorreto | Usar: hybrid, cancel_orders, force_sell, stop_buy |
| "Posição não calculada" | Sem posições ativas | Normal se não estiver tradando |

### Troubleshooting Rápido

- **Bot não inicia**: Verifique `.env` - MAIN_PUBLIC_KEY e AGENT_PRIVATE_KEY_B58
- **Ordens não executam**: Cheque margem disponível e configuração de símbolos
- **AUTO_CLOSE não ativa**: Verifique se AUTO_CLOSE_ON_MAX_POSITION=true
- **Multi-asset não funciona**: Confirme SYMBOLS válidos e STRATEGY_TYPE=multi_asset

## 🛡️ Boas práticas de segurança

- **NUNCA** faça commit do arquivo `.env`
- Use uma wallet dedicada com saldo limitado
- Comece em ambiente de **baixa exposição** e monitore os primeiros minutos

## 📜 Licença e responsabilidade

- Licença: [MIT](LICENSE)
- Aviso de risco e isenção de responsabilidade: [DISCLAIMER](DISCLAIMER.md)

## 🤝 Contribuindo

Veja [CONTRIBUTING](CONTRIBUTING.md) e [SECURITY](SECURITY.md).

---

> Feito para a comunidade Coleta Cripto (https://x.com/Coleta_Cripto). Pull Requests são bem-vindos!
