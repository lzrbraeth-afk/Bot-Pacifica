# Pacifica Trading Bot

Bot de **grid trading** e **scalping multi-asset** para a corretora **Pacifica** com **5 estratégias avançadas**: **Pure Grid** (clássica), **Market-Making Grid** (dinâmica), **🚀 Dynamic Grid** (adaptativa), **Multi-Asset Básico** (scalping threshold) e **🧠 Multi-Asset Enhanced** (algoritmo inteligente com 5 indicadores técnicos).

Inclui gerenciamento de risco, métricas de performance, logs específicos por estratégia, sistema AUTO_CLOSE e validação automática.

> **⚠️ ATENÇÃO: RISCO ELEVADO**

O trading de contratos perpétuos com alavancagem envolve **altos riscos financeiros**, podendo resultar na perda total do capital investido. Este bot é fornecido **"no estado em que se encontra"**, sem garantias de desempenho, precisão ou lucratividade.

### Recomendações Importantes
- **Teste extensivamente**: Antes de usar o bot em um ambiente real, realize testes completos com valores baixos em uma conta de demonstração ou com capital que você está disposto a perder.
- **Use com cautela**: Bots automatizados podem amplificar erros ou reagir de forma inesperada em mercados voláteis.
- **Eduque-se**: Compreenda completamente os riscos do trading alavancado antes de utilizar este software.
- **Gerencie riscos**: Nunca invista mais do que você pode perder. Configure limites rigorosos de perda e monitore o bot regularmente.

**O desenvolvedor não se responsabiliza por perdas financeiras ou danos decorrentes do uso deste bot. Use por sua conta e risco.**

Leia o arquivo [DISCLAIMER](DISCLAIMER.md).

## 📑 Índice

- [⚡ Quick Start](#-quick-start)
- [🚀 Principais Funcionalidades](#-principais-funcionalidades)
- [🚀 Instalação](#️-instalação)
- [⚙️ Configuração (.env)](#️-configuração-env)
- [📱 Sistema de Notificações Telegram](#-sistema-de-notificações-telegram)
- [🎯 Estratégias Disponíveis](#-estratégias-disponíveis)
- [🛡️ Sistema AUTO_CLOSE](#️-sistema-auto_close-proteção-automática)
- [🧪 Troubleshooting e Validação](#-troubleshooting-e-validação)
- [🚀 Novidades Recentes](#-novidades-recentes---setembro-2025)

## ⚡ Quick Start

**Para usuários experientes que querem começar rapidamente:**

1. **Instalar Python 3.10+** e **git**
2. **Clonar repositório**: `git clone [URL] && cd Bot-Pacifica`
3. **Ambiente virtual**: `python -m venv .venv && .\.venv\Scripts\Activate.ps1` (Windows)
4. **Dependências**: `pip install -r requirements.txt`
5. **Configurar .env**: Copiar `.env.example` → `.env` e editar:

   **💡 Configuração Mínima (Iniciante):**
   ```ini
   # API Básica
   MAIN_PUBLIC_KEY=sua_carteira_sol
   AGENT_PRIVATE_KEY_B58=sua_chave_api_pacifica
   
   # Estratégia Simples
   STRATEGY_TYPE=market_making
   SYMBOL=SOL
   LEVERAGE=5
   GRID_LEVELS=6
   ORDER_SIZE_USD=25
   
   # Proteção Básica
   STOP_LOSS_PERCENT=1.5
   TAKE_PROFIT_PERCENT=2.0
   
   # Telegram (Opcional)
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=seu_token
   TELEGRAM_CHAT_ID=seu_chat_id
   ```

6. **Executar**: `python grid_bot.py`

> 📋 **Para configuração completa** (71 variáveis), consulte a [seção de Configuração](#️-configuração-env---completa) ou o arquivo [`.env.example`](.env.example).

📹 **[Video Tutorial Completo](https://www.youtube.com/watch?v=cKypCQwXctc)**

---

## 🚀 Principais Funcionalidades

### 📊 5 Estratégias de Trading Avançadas
- **Pure Grid (pure_grid)**: Grid trading clássico com ordens de compra/venda distribuídas em níveis de preço fixos
- **Market-Making Grid (market_making)**: Grid dinâmico que se adapta à volatilidade e spread do mercado  
- **🚀 Dynamic Grid (dynamic_grid)**: Grid adaptativo que reposiciona ordens conforme execuções e tendências de mercado
- **Multi-Asset Básico (multi_asset)**: Scalping threshold com comparação de 3 preços (atual + 2 anteriores)
- **🧠 Multi-Asset Enhanced (multi_asset_enhanced)**: Algoritmo inteligente com 5 indicadores técnicos:
  - **Momentum** (30 pontos): Análise de força do movimento
  - **Trend** (25 pontos): Direção da tendência SMA
  - **RSI** (20 pontos): Índice de força relativa
  - **Volatility** (15 pontos): Análise de volatilidade ATR
  - **Confirmation** (10 pontos): Confirmação de sinal

### 🎯 Sistema de Gerenciamento de Risco
- **Take Profit (TP)** e **Stop Loss (SL)** configuráveis por estratégia
- **Sistema AUTO_CLOSE híbrido**: Combina tempo de vida + condições de mercado
- **Validação automática** de saldos e posições abertas
- **Controle de alavancagem** por ativo

### 📈 Métricas e Monitoramento
- **Performance tracking** em tempo real com ROI, Sharpe Ratio e drawdown
- **Logs específicos por estratégia** com emojis e terminologia adequada
- **📱 Sistema de notificações Telegram** robusto com múltiplos tipos de alerta
- **Relatórios detalhados** de trades e resultados

### ⚙️ Configuração Simplificada
- **STRATEGY_TYPE único**: Seleção simples entre as 5 estratégias
- **Configuração .env** com exemplos para cada estratégia
- **Templates prontos** para diferentes cenários de trading
- **📱 Notificações Telegram** com setup em 3 passos

### 🛠️ Recursos Técnicos
- Rebalanceamento automático e deslocamento de grid por limiar
- **Multi-Asset Trading** com gerenciamento individual de risco por símbolo
- Gestão de margem, limite de ordens e tamanho máximo de posição
- **Sistema AUTO_CLOSE** com estratégia híbrida para proteção automática de risco
- **📱 Notificações Telegram** robustas com fallback e persistência
- **Loss Management** especializado para cenários de alta volatilidade
- Logs estruturados (arquivo e console) e *shutdown* gracioso
- **PerformanceTracker** com métricas como *win rate*, *drawdown*, *Sharpe/Sortino*, *profit factor*
- Arquivo `.env` com configuração declarativa

## 🧱 Arquitetura (alto nível)

### 🏗️ Estrutura Principal
```
grid_bot.py                          # Orquestração principal e seleção de estratégia
src/
├── pacifica_auth.py                 # Cliente de API (REST/WebSocket) da Pacifica
├── grid_calculator.py               # Cálculo de níveis do grid e tamanhos
├── grid_strategy.py                 # Estratégia Pure Grid / Market-Making Grid
├── multi_asset_strategy.py          # Estratégia Multi-Asset Básico
├── multi_asset_enhanced_strategy.py # 🧠 Estratégia Enhanced com 5 indicadores
├── enhanced_signal_detector.py      # Detector de sinais com algoritmo avançado
├── strategy_logger.py               # Sistema de logs específicos por estratégia
├── telegram_notifier.py             # 📱 Sistema de notificações Telegram
├── position_manager.py              # Saldo, margem, ordens e posições
└── performance_tracker.py           # Métricas e relatórios de performance
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


# 🔄 Atualização do Bot Pacifica

O processo de atualização foi simplificado para ser feito em poucos passos, tanto no **Windows** quanto no **Linux/Mac**.

---

## 🟦 Windows

1. Na pasta do **Bot Pacifica**, clique duas vezes no arquivo **`update.bat`**.  
2. Escolha a opção desejada:  
   - `1` → **Nova instalação** (baixa tudo do zero).  
   - `2` → **Atualização** (move seu `.env` para `.env.old`).  
3. Após a atualização (opção 2):  
   - Abra o arquivo `.env.old` → copie sua **API KEY** e demais dados.  
   - Renomeie o novo arquivo **`.env.example`** para **`.env`**.  
   - Cole dentro dele as informações copiadas.  

✅ Seu bot está atualizado e configurado.

---

## 🟩 Linux/Mac

1. No terminal, dentro da pasta do **Bot Pacifica**, rode:  
   ```bash
   chmod +x update.sh
   ./update.sh
```

## ⚙️ Configuração (.env) - COMPLETA

> 📋 **Referência Completa**: Consulte o arquivo [`.env.example`](.env.example) atualizado com **todas as 71 variáveis** disponíveis.

### 🎯 Quick Setup por Perfil de Usuário

#### 🟢 **INICIANTE** (Configuração Conservadora)
```ini
# Básico
STRATEGY_TYPE=market_making
SYMBOL=SOL
LEVERAGE=5
GRID_LEVELS=6
ORDER_SIZE_USD=25
GRID_SPACING_PERCENT=0.3

# Proteção
STOP_LOSS_PERCENT=1.5
TAKE_PROFIT_PERCENT=2.0
MAX_POSITION_SIZE_USD=200
```

#### 🟡 **INTERMEDIÁRIO** (Configuração Equilibrada)
```ini
# Básico  
STRATEGY_TYPE=dynamic_grid
SYMBOL=SOL
LEVERAGE=10
GRID_LEVELS=8
ORDER_SIZE_USD=35
GRID_SPACING_PERCENT=0.2

# Proteção Avançada
ENABLE_CYCLE_PROTECTION=true
GRID_CYCLE_STOP_LOSS_PERCENT=5.0
GRID_SESSION_PROFIT_TARGET_PERCENT=40.0
```

#### 🔴 **AVANÇADO** (Configuração Agressiva)
```ini
# Multi-Asset Enhanced
STRATEGY_TYPE=multi_asset_enhanced
SYMBOLS=AUTO
POSITION_SIZE_USD=50
MAX_CONCURRENT_TRADES=5
LEVERAGE=15

# Sistema de Emergência (Camada 3)
EMERGENCY_SL_PERCENT=3.0
EMERGENCY_TP_PERCENT=5.0
```

### 📋 Configurações Principais

#### 🔐 **API e Autenticação**
```ini
MAIN_PUBLIC_KEY=                    # Seu endereço da carteira SOL
AGENT_PRIVATE_KEY_B58=              # Chave API gerada na Pacifica
API_ADDRESS=https://api.pacifica.fi/api/v1
WS_BASE_URL=wss://ws.pacifica.fi/ws
```

#### 🎯 **Estratégia Principal**
```ini
# Escolha UMA das 5 estratégias:
STRATEGY_TYPE=pure_grid             # Grid clássico com range fixo
# STRATEGY_TYPE=market_making       # Grid dinâmico adaptativo
# STRATEGY_TYPE=dynamic_grid        # 🚀 Grid adaptativo inteligente  
# STRATEGY_TYPE=multi_asset         # Scalping multi-asset básico
# STRATEGY_TYPE=multi_asset_enhanced # 🧠 Enhanced com 5 indicadores
```

#### ⚙️ **Configuração Básica de Trading**
```ini
SYMBOL=SOL                          # Ativo principal (estratégias grid)
LEVERAGE=10                         # Alavancagem
MAX_OPEN_ORDERS=20                  # Ordens simultâneas
CHECK_BALANCE_BEFORE_ORDER=true     # Verificação de saldo
REBALANCE_INTERVAL_SECONDS=60       # Intervalo de rebalanceamento
```

### 🛡️ Sistema de Gestão de Risco (3 Camadas)

#### **Camada 1: TP/SL Automáticos**
```ini
AUTO_CLOSE_ENABLED=true             # Habilitar TP/SL
USE_API_TP_SL=true                  # Via API (recomendado)
STOP_LOSS_PERCENT=1.0               # Stop Loss %
TAKE_PROFIT_PERCENT=1.5             # Take Profit %
TRAILING_STOP_ENABLED=false         # Trailing stop
MAX_POSITION_TIME_MINUTES=60        # Tempo máximo de posição
```

#### **Camada 2: Risk Manager (Ciclos/Sessões)**
```ini
# Proteção por Ciclo
ENABLE_CYCLE_PROTECTION=true
GRID_CYCLE_STOP_LOSS_PERCENT=5.0
GRID_CYCLE_TAKE_PROFIT_PERCENT=8.0

# Proteção de Sessão  
ENABLE_SESSION_PROTECTION=true
GRID_SESSION_MAX_LOSS_USD=80.0
GRID_SESSION_PROFIT_TARGET_PERCENT=40.0

# Ações de Proteção
GRID_ACTION_ON_LIMIT=pause          # pause ou shutdown
GRID_PAUSE_DURATION_MINUTES=120
```

#### **Camada 3: Sistema de Emergência**
```ini
# Proteção de última instância
EMERGENCY_SL_PERCENT=3.0            # Perda crítica
EMERGENCY_TP_PERCENT=5.0            # Lucro extremo
EMERGENCY_MAX_LOSS_TIME_MINUTES=15  # Tempo máximo em perda
EMERGENCY_CHECK_INTERVAL_SECONDS=10 # Frequência de verificação
```

### 🎯 Configurações Específicas por Estratégia

#### **🌐 Multi-Asset (multi_asset e multi_asset_enhanced)**
```ini
SYMBOLS=BTC,ETH,SOL,AVAX           # Símbolos específicos
# SYMBOLS=AUTO                     # Busca todos disponíveis

# Blacklist para filtrar símbolos indesejados
SYMBOLS_USE_BLACKLIST=true
SYMBOLS_BLACKLIST=PUMP,kPEPE,FARTCOIN
SYMBOLS_MAX_COUNT=0                # 0 = sem limite

POSITION_SIZE_USD=20               # Tamanho por posição
MAX_CONCURRENT_TRADES=3            # Trades simultâneos
PRICE_CHANGE_THRESHOLD=0.3         # Threshold de entrada
```

#### **🧠 Enhanced Strategy - Indicadores Técnicos**
```ini
# Configurações de qualidade do sinal (0-100)
ENHANCED_MIN_SIGNAL_QUALITY=65     # Qualidade mínima
ENHANCED_MIN_CONFIDENCE=75         # Confiança mínima
ENHANCED_USE_RSI_FILTER=true       # Filtro RSI
ENHANCED_MAX_VOLATILITY=4.0        # Volatilidade máxima (%)
ENHANCED_MIN_HISTORY=25            # Períodos mínimos
```

#### **🚀 Dynamic Grid - Configurações Avançadas**
```ini
# Ajustes dinâmicos do grid
DYNAMIC_THRESHOLD_PERCENT=1.0      # Threshold para ajustes
MAX_ADJUSTMENT_DISTANCE_PERCENT=5.0 # Distância máxima
VOLUME_BOOST_ENABLED=true          # Boost de volume

# Reset periódico (NOVO!)
ENABLE_PERIODIC_GRID_RESET=true
GRID_RESET_INTERVAL_MINUTES=60
```

#### **📊 Grid Trading (pure_grid, market_making)**
```ini
# Configurações do Grid
GRID_LEVELS=8                      # Níveis do grid
ORDER_SIZE_USD=35                  # Tamanho das ordens
GRID_SPACING_PERCENT=0.2           # Espaçamento %
GRID_DISTRIBUTION=symmetric        # symmetric/bullish/bearish

# Grid Adaptativo
ADAPTIVE_GRID=true
VOLATILITY_WINDOW=20
VOLATILITY_MULT_MIN=0.7
VOLATILITY_MULT_MAX=1.5

# Pure Grid - Range Fixo
RANGE_MIN=90000                    # Apenas para pure_grid
RANGE_MAX=110000
RANGE_EXIT=true
```

### 📱 Sistema Telegram Avançado

#### **Configuração Básica**
```ini
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=                # Token do @BotFather
TELEGRAM_CHAT_ID=                  # Seu Chat ID
```

#### **Configurações de Performance**
```ini
TELEGRAM_TIMEOUT_SECONDS=45        # Timeout das requisições
TELEGRAM_CONNECT_TIMEOUT=20        # Timeout de conexão  
TELEGRAM_MAX_RETRIES=5             # Máximo de tentativas
TELEGRAM_RETRY_DELAY_SECONDS=3.0   # Delay entre tentativas
TELEGRAM_RATE_LIMIT_SECONDS=2.0    # Limite de taxa
```

### � Configurações Avançadas e Debug

```ini
# Logs e Debug
LOG_LEVEL=INFO                     # DEBUG, INFO, WARNING, ERROR
DEBUG_MODE=false
RISK_MANAGER_DEBUG_MODE=false

# Limpeza e Manutenção
CLEAN_ORDERS_ON_START=false        # Limpar ordens ao iniciar
GRID_SAVE_PNL_HISTORY=true        # Salvar histórico P&L
GRID_LOG_PNL_EVERY_MINUTES=15     # Log periódico do P&L
```

> **Dica**: Comece conservador (menos níveis, maior espaçamento, ordem menor) e aumente aos poucos.

## 📱 Sistema de Notificações Telegram

O bot inclui um **sistema robusto de notificações** via Telegram que mantém você informado sobre todas as operações importantes, mesmo quando não está monitorando o bot.

> 📖 **[Guia Completo de Notificações Telegram](docs/telegram_guide.md)** - Documentação detalhada com exemplos e troubleshooting

### 🔧 Configuração Rápida

1. **Criar Bot no Telegram:**
   - Abra o Telegram e busque `@BotFather`
   - Digite: `/newbot`
   - Escolha nome: "Pacifica Grid Monitor"
   - Escolha username: "PacificaGridBot"
   - **Copie o TOKEN** gerado

2. **Obter seu Chat ID:**
   - Busque `@userinfobot` no Telegram
   - Inicie conversa com ele
   - Ele enviará seu **CHAT_ID** (número)

3. **Configurar no .env:**
```ini
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ
TELEGRAM_CHAT_ID=123456789
```

4. **Testar Conexão:**
```bash
python test_telegram.py
```

### 🎯 Tipos de Notificações

O sistema envia notificações específicas para diferentes eventos:

#### 💹 **Notificações de Trading**
- **Trades executados**: Compras/vendas com preço, quantidade e PnL
- **Fechamento de ciclos**: Resultado completo de ciclos de grid
- **Take Profit/Stop Loss**: Alertas quando TP/SL são acionados

#### ⚠️ **Alertas de Risco**
- **Stop Loss**: Quando posições são fechadas por stop loss
- **Limites de margem**: Avisos sobre margem baixa
- **Posições grandes**: Alertas quando posição excede limites

#### 📊 **Status do Bot**
- **Inicialização**: Confirmação de que o bot está ativo
- **Pausas/Retomadas**: Quando bot é pausado ou retomado
- **Heartbeat**: Status periódico opcional (configurável)

### ⚙️ Configurações Avançadas

```ini
# Controle granular de notificações
TELEGRAM_NOTIFY_CYCLE_CLOSE=true         # Fechamento de ciclos
TELEGRAM_NOTIFY_STOP_LOSS=true           # Stop loss acionado
TELEGRAM_NOTIFY_TAKE_PROFIT=true         # Take profit acionado
TELEGRAM_NOTIFY_SESSION_LIMIT=true       # Limites de sessão
TELEGRAM_NOTIFY_PAUSE_RESUME=true        # Pausas e retomadas
TELEGRAM_NOTIFY_HEARTBEAT=false          # Heartbeat periódico

# Configurações de performance
TELEGRAM_TIMEOUT_SECONDS=30              # Timeout de envio
TELEGRAM_MAX_RETRIES=3                   # Tentativas de reenvio
TELEGRAM_RATE_LIMIT_SECONDS=1.0          # Intervalo entre mensagens
```

### 🛡️ Sistema de Fallback

O sistema inclui **múltiplas camadas de proteção**:

- **🔄 Retry Automático**: Tentativas múltiplas em caso de falha
- **📦 Fila de Mensagens**: Mensagens são salvas e reenviadas
- **💾 Backup Local**: Backup em arquivo para mensagens perdidas
- **⏱️ Rate Limiting**: Controle para evitar spam

### 📋 Exemplos de Mensagens

```
✅ Trade Executado (15:30:25)
🟢 COMPRA - SOL
💰 Preço: $150.75
📊 Quantidade: 10.0
📈 PnL: +$25.50

🎯 Ciclo Completo (15:45:12)
Ciclo de Grid Finalizado
💹 Trades: 8
⏱️ Duração: 120min
💰 Resultado: $45.75

⚠️ Risk Manager (16:00:05)
🛑 Alerta de Risco
🔔 Tipo: STOP_LOSS
• symbol: SOL
• current_loss: 15.50
• action: Stop loss ativado
```

### 🧪 Teste e Validação

```bash
# Testar conectividade
python test_telegram.py

# Verificar fila de mensagens
python -c "
from src.telegram_notifier import TelegramNotifier
notifier = TelegramNotifier()
stats = notifier.get_queue_stats()
print(f'Mensagens na fila: {stats[\"total_messages\"]}')
"

# Processar mensagens pendentes
python -c "
from src.telegram_notifier import TelegramNotifier
notifier = TelegramNotifier()
sent = notifier.process_message_queue()
print(f'Mensagens enviadas: {sent}')
"
```

> **💡 Dica**: Mantenha o bot do Telegram ativo e configure apenas as notificações que realmente precisa para evitar spam.

## Video com passo a passo para instalar o BOT, depois de instalado o PYTHON 

<https://www.youtube.com/watch?v=cKypCQwXctc>

## 🎯 Estratégias Disponíveis

### 🧠 Multi-Asset Enhanced (Recomendada)
**Algoritmo inteligente** com 5 indicadores técnicos e sistema de scoring 0-100:

```ini
STRATEGY_TYPE=multi_asset_enhanced
SYMBOLS=BTC,ETH,SOL,AVAX           # Símbolos para análise
POSITION_SIZE_USD=20               # Tamanho por posição
MAX_CONCURRENT_TRADES=3            # Trades simultâneos
ENHANCED_MIN_SCORE=60              # Score mínimo (0-100)
ENHANCED_CONFIDENCE_THRESHOLD=0.7  # Confiança mínima
```

**Indicadores e Pesos:**
- 🚀 **Momentum** (30pts): Força do movimento de preço
- 📈 **Trend** (25pts): Direção da tendência (SMA 20/50)
- ⚡ **RSI** (20pts): Sobrecompra/sobrevenda
- 🌊 **Volatility** (15pts): Análise ATR para timing
- ✅ **Confirmation** (10pts): Confirmação do sinal

**Vantagens:**
- Análise técnica avançada com múltiplos indicadores
- Sistema de scoring inteligente (0-100)
- Adaptação automática às condições de mercado
- Redução significativa de falsos sinais

### 🌐 Multi-Asset Básico
Trading simultâneo com análise threshold simples:

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
- Configuração simples e rápida

### ⚡ Pure Grid (Clássica)
Grid tradicional com range fixo de preços:

```ini
STRATEGY_TYPE=pure_grid
RANGE_MIN=48000             # Preço mínimo do range
RANGE_MAX=52000             # Preço máximo do range
GRID_LEVELS=20              # Número de níveis
```

### 🔄 Market Making Grid (Dinâmica)
Grid que se adapta ao movimento do preço:

```ini  
STRATEGY_TYPE=market_making
GRID_SHIFT_THRESHOLD_PERCENT=1.0  # % para rebalanceamento
REBALANCE_INTERVAL_SECONDS=60     # Intervalo de verificação
```

### 🚀 Dynamic Grid (Adaptativa) - **NOVO!**
Grid inteligente que reposiciona ordens automaticamente conforme execuções e tendências:

```ini
STRATEGY_TYPE=dynamic_grid
SYMBOL=HYPE                       # Símbolo principal
GRID_LEVELS=12                    # Número de níveis
GRID_SPACING_PERCENT=0.5          # Espaçamento percentual
ORDER_SIZE_USD=15                 # Tamanho por ordem
CLEAN_ORDERS_ON_START=true        # Limpar ordens antigas

# 🔄 Reset periódico do grid (OPCIONAL)
ENABLE_PERIODIC_GRID_RESET=true   # Habilitar reset completo
GRID_RESET_INTERVAL_MINUTES=120   # Reset a cada 2 horas
```

**🎯 Funcionalidades Principais:**
- **Detecção automática** de execução de ordens
- **Reposicionamento inteligente** quando preço sai do range
- **Análise de tendência** para ajustar direção do grid
- **Cancelamento automático** de ordens obsoletas
- **Sistema de relocação** de ordens de venda quando preço cai
- **🆕 Reset periódico** - apaga todas ordens e recria grid do zero periodicamente
- **Adaptação dinâmica** à volatilidade do mercado

**⚡ Vantagens:**
- ✅ Ordens sempre seguem o movimento do preço
- ✅ Elimina ordens "órfãs" fora do range útil  
- ✅ Maior aproveitamento de oportunidades
- ✅ Reduz necessidade de intervenção manual
- ✅ Baseado em análise de tendência real

**🔧 Como Funciona:**
1. Monitora execução de ordens continuamente
2. Detecta quando preço sai significativamente do range
3. Cancela ordens obsoletas automaticamente
4. Reposiciona ordens para novo range de preço
5. Adapta estratégia baseado na tendência detectada

## � Sistema de Logs Específicos por Estratégia

O bot possui um **sistema avançado de logs** que adapta mensagens, emojis e terminologia de acordo com a estratégia selecionada:

### 🎨 Personalização por Estratégia

**Pure Grid** 📊
```
📊 [GRID] Configurando grid: 20 níveis entre $48000-$52000
📊 [GRID] Ordem de compra colocada no nível $49500
```

**Market Making** 🔄  
```
🔄 [MARKET_MAKING] Grid rebalanceado: novo centro $51200
🔄 [MARKET_MAKING] Spread adaptado à volatilidade: 0.8%
```

**Multi-Asset Básico** 🌐
```
🌐 [MULTI_ASSET] Analisando 4 ativos: BTC, ETH, SOL, AVAX
🌐 [MULTI_ASSET] SOL: mudança de 2.3% detectada - Executando entrada
```

**Multi-Asset Enhanced** 🧠
```
🧠 [ENHANCED] Score BTC: 75/100 (Momentum:25, Trend:20, RSI:15, Vol:10, Conf:5)
🧠 [ENHANCED] Sinal COMPRA confirmado - Confiança: 82%
```

**Dynamic Grid** 🚀
```
🚀 [DYNAMIC_GRID] Grid inicializado: 12 níveis para HYPE
🚀 [DYNAMIC_GRID] Execução detectada: Ordem #299832423 - Ajustando grid
🚀 [DYNAMIC_GRID] Tendência BAIXA detectada - Reposicionando vendas
🚀 [DYNAMIC_GRID] Ordem cancelada: #299595822 (fora do range)
🚀 [DYNAMIC_GRID] Nova venda criada: $45.20 (seguindo tendência)
```

### �📊 Métricas e Logs

- **Logs específicos**: Salvos em `logs/` com timestamp (ex.: `grid_bot_YYYYMMDD_HHMMSS.log`)
- **Relatórios de performance**: Win rate, drawdown, Sharpe Ratio atualizados em tempo real
- **Filtros automáticos**: Mensagens relevantes para cada estratégia
- **Emojis identificadores**: Facilita identificação visual nos logs

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


## 🧪 Troubleshooting e Validação

### 🔍 Diagnóstico Rápido

**Verificar Configuração Principal:**
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
required = ['MAIN_PUBLIC_KEY', 'AGENT_PRIVATE_KEY_B58', 'STRATEGY_TYPE']
for key in required:
    value = os.getenv(key)
    print(f'{key}: {\"✅ OK\" if value else \"❌ FALTANDO\"}')"
```

**Testar Conectividade:**
```bash
python -c "
from src.pacifica_auth import PacificaAuth
client = PacificaAuth()
result = client.get_account_info()
print('✅ API funcionando!' if result else '❌ Erro de API')"
```

**Validar Todas as 71 Variáveis:**
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

# Categorias principais
api_vars = ['MAIN_PUBLIC_KEY', 'AGENT_PRIVATE_KEY_B58', 'API_ADDRESS', 'WS_BASE_URL']
strategy_vars = ['STRATEGY_TYPE', 'SYMBOL', 'LEVERAGE']
risk_vars = ['EMERGENCY_SL_PERCENT', 'GRID_CYCLE_STOP_LOSS_PERCENT']
telegram_vars = ['TELEGRAM_ENABLED', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']

categories = {
    'API': api_vars,
    'Estratégia': strategy_vars, 
    'Risco': risk_vars,
    'Telegram': telegram_vars
}

for category, vars_list in categories.items():
    print(f'\n📋 {category}:')
    for var in vars_list:
        value = os.getenv(var)
        status = '✅ OK' if value else '❌ FALTANDO'
        print(f'  {var}: {status}')"
```

### 🚨 Problemas Comuns e Soluções

| **Erro** | **Causa Provável** | **Solução** |
|----------|-------------------|-------------|
| `ModuleNotFoundError` | Ambiente virtual não ativado | Execute `.\.venv\Scripts\Activate.ps1` |
| `API Error 401` | Chave privada inválida | Regenerar `AGENT_PRIVATE_KEY_B58` na Pacifica |
| `Estratégia desconhecida` | `STRATEGY_TYPE` incorreto | Use: `pure_grid`, `market_making`, `dynamic_grid`, `multi_asset`, `multi_asset_enhanced` |
| `Sem símbolos válidos` | `SYMBOLS` incorreto | Use `AUTO` ou símbolos válidos: `BTC,ETH,SOL` |
| `Emergency SL não ativa` | Configuração faltando | Adicione `EMERGENCY_SL_PERCENT=3.0` |
| `Risk Manager erro` | Proteção não configurada | Configure `ENABLE_CYCLE_PROTECTION=true` |
| `Grid não se adapta` | Dynamic Grid mal configurado | Use `DYNAMIC_THRESHOLD_PERCENT=1.0` |
| `Enhanced Score baixo` | Configuração muito restritiva | Diminua `ENHANCED_MIN_SIGNAL_QUALITY=50` |

### 📱 Troubleshooting Telegram Avançado

| **Problema** | **Causa Provável** | **Solução** |
|-------------|-------------------|-------------|
| **Rate limit atingido** | Muitas mensagens | Configure `TELEGRAM_RATE_LIMIT_SECONDS=3.0` |
| **Timeout constante** | Conexão instável | Aumente `TELEGRAM_TIMEOUT_SECONDS=60` |
| **Fila de mensagens crescendo** | API Telegram indisponível | Execute: `python -c "from src.telegram_notifier_resilient import TelegramNotifier; TelegramNotifier().process_message_queue()"` |
| **Mensagens cortadas** | Texto muito longo | Sistema limita automaticamente em 4000 caracteres |
| **Bot não responde** | Token/Chat ID incorreto | Refaça configuração com `@BotFather` |

**🧪 Teste Completo do Telegram:**
```bash
python test_telegram.py
```

### � Validação de Estratégias Específicas

**🧠 Enhanced Strategy:**
```bash
python -c "
from src.enhanced_signal_detector import EnhancedSignalDetector
detector = EnhancedSignalDetector()
print('✅ Enhanced Strategy configurada corretamente!')"
```

**🚀 Dynamic Grid:**
```bash
python -c "
from src.dynamic_grid_strategy import DynamicGridStrategy
from src.grid_calculator import GridCalculator
from src.position_manager import PositionManager
from src.pacifica_auth import PacificaAuth

auth = PacificaAuth()
calc = GridCalculator()
pos_mgr = PositionManager(auth)
strategy = DynamicGridStrategy(auth, calc, pos_mgr)
print('✅ Dynamic Grid Strategy configurada!')"
```

**� Multi-Asset:**
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

symbols = os.getenv('SYMBOLS', 'AUTO')
if symbols == 'AUTO':
    print('✅ Configurado para buscar todos os símbolos')
else:
    symbol_list = symbols.split(',')
    print(f'✅ Configurado para {len(symbol_list)} símbolos: {symbol_list}')"
```

### � Diagnóstico Avançado

**Verificar Sistema de Risco Completo:**
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

# Verificar 3 camadas de proteção
layer1 = bool(os.getenv('AUTO_CLOSE_ENABLED', 'false').lower() == 'true')
layer2 = bool(os.getenv('ENABLE_CYCLE_PROTECTION', 'false').lower() == 'true')
layer3 = bool(os.getenv('EMERGENCY_SL_PERCENT'))

print(f'🛡️ Sistema de Proteção:')
print(f'  Camada 1 (TP/SL): {\"✅\" if layer1 else \"❌\"}')
print(f'  Camada 2 (Risk Manager): {\"✅\" if layer2 else \"❌\"}') 
print(f'  Camada 3 (Emergency): {\"✅\" if layer3 else \"❌\"}')
print(f'  Status: {\"🟢 COMPLETO\" if all([layer1, layer2, layer3]) else \"� PARCIAL\"}')"
```

**Verificar Configuração de Performance:**
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

configs = {
    'REBALANCE_INTERVAL_SECONDS': 'Intervalo de rebalanceamento',
    'GRID_CHECK_INTERVAL_SECONDS': 'Verificação do grid',
    'EMERGENCY_CHECK_INTERVAL_SECONDS': 'Verificação de emergência',
    'TELEGRAM_RATE_LIMIT_SECONDS': 'Limite do Telegram'
}

print('⚡ Configurações de Performance:')
for var, desc in configs.items():
    value = os.getenv(var, 'NÃO DEFINIDO')
    print(f'  {desc}: {value}s')"
```

### ✅ Interpretação dos Resultados

**🟢 Sistema Funcionando:**
- Todas as variáveis principais configuradas
- API conectando sem erros
- Estratégia carregada corretamente
- Sistema de risco ativo

**🟡 Atenção Necessária:**
- Algumas configurações opcionais faltando
- Telegram não configurado
- Apenas 1-2 camadas de proteção ativas

**🔴 Problemas Críticos:**
- API não conecta
- Estratégia não reconhecida
- Nenhuma proteção configurada
- Erros de módulo/dependências

### 🛡️ Lista de Verificação Final

- [ ] ✅ Python 3.10+ instalado
- [ ] ✅ Ambiente virtual ativado  
- [ ] ✅ Dependências instaladas
- [ ] ✅ `.env` criado e configurado
- [ ] ✅ API Pacifica funcionando
- [ ] ✅ Estratégia selecionada
- [ ] ✅ Sistema de risco configurado
- [ ] ✅ Telegram testado (opcional)
- [ ] ✅ Primeira execução sem erros

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
