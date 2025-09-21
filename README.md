# Pacifica Grid Trading Bot

Bot de **grid trading** para a corretora **Pacifica** com duas abordagens: **Pure Grid** (clássica) e **Market-Making Grid** (dinâmica). Inclui gerenciamento de risco, métricas de performance e logs detalhados.

> ⚠️ **Risco**: Trading alavancado envolve alto risco. Este projeto é fornecido *no estado em que se encontra*, sem garantias. Leia o arquivo [DISCLAIMER](DISCLAIMER.md).

---

## ✨ Principais recursos

- Estratégias: **Pure Grid** e **Market Making Grid**
- Rebalanceamento automático e deslocamento de grid por limiar
- Gestão de margem, limite de ordens e tamanho máximo de posição
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
- Python 3.10+ (recomendado 3.12) 

a. Baixe o instalador no [site oficial](https://www.python.org/downloads/).

b. Durante a instalação na primeira tela, selecione todas as opções

![Tela 1 - Selecionar componentes](docs/images/Setup_Python_01.png)

c. Na próxima tela, marque **Add Python to PATH**:

![Tela 2 - Add Python to PATH](docs/images/Setup_Python_02.png)
Anote o caminho informado em customize install location ou altere para um caminho mais facil como c:\python3

d. Next, Next, Next até o final

e. Testar a instalação do python. Abra o Prompt de Comando e digite:

python --version
pip --version

Se aparecer a versão está ok ✅

* se não mostrar a versão é porque o PATH ainda não está ativado e precisa de um reboot. Se quiser testar sem o reboot, digite o comando com o caminho completo (exemplo c:\python3\python)

- `git` instalado

a. Baixe em git-scm.com/download/win

b. Execute o instalador → Next, Next, Next até o final, só confira estas opções:

    Git from the command line and also from 3rd-party software (adiciona o Git ao PATH).

    Enable Git Credential Manager (facilita login no GitHub, pode deixar marcado).

    O resto pode deixar padrão.

c. Teste no terminal:

git --version

Se aparecer a versão está ok ✅

### 2) Clonar o repositório

Entre na pasta onde vai fazer o download dos arquivos do bot, como exemplo crie uma pasta dentro do C: chamada Bot e entre nela c:\bot.

cd\
mkdir Bot
cd Bot

```bash
git clone https://github.com/lzrbraeth-afk/pacifica-grid-bot.git
cd pacifica-grid-bot
```

### 3) Ambiente virtual
**Windows (PowerShell):**
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4) Configuração (.env)

Copie o arquivo de exemplo e edite os valores:

```bash
cp .env.example .env   # no Windows use: copy .env.example .env
```

Edite **PRIVATE_KEY**, **SYMBOL**, **WALLET_ADDRESS** e demais parâmetros conforme sua preferência (ver seção Configuração).

## ▶️ Como executar

Iniciar o bot:

```bash
python grid_bot.py
```

Primeiro teste (checar API/credenciais):

```bash
python pacifica_auth.py      # testa credenciais/conexão
```
Para encerrar com segurança: `Ctrl + C` (o bot finaliza e imprime um resumo).


## ⚙️ Configuração (.env)

Parâmetros essenciais:

```ini
# API / Segurança
PRIVATE_KEY=SEU_PRIVATE_KEY_WALLET # Aqui vocë vai inserir a chave privada da sua carteira.
WALLET_ADDRESS=COLOQUE_SUA_SOL_WALLET_ADDRESS
REST_URL=https://api.pacifica.fi/api/v1
WS_URL=wss://ws.pacifica.fi/ws

 Recomendavel, para sua segurança usar uma carteira com fundos somente para esta corretora, pois será colocado no arquivo .env a chave privada da carteira. Esta chave não é exposta na conexão com a API, mas ela fica armazenada em um arquivo no computador. Proteja-o igual protege suas chaves privadas! 

 Se ainda não adota segurança em seu computador como criptografia do disco, antivirus eficiente, plugins de proteção para a carteira, pense em fazer isto para a sua proteção futura, não somente sobre este bot, mas sobre sua segurança on chain.

# Ativo e alavancagem
SYMBOL=BTC
LEVERAGE=10
ORDER_SIZE_USD=100

# Estratégia (pure_grid | market_making)
STRATEGY_TYPE=market_making

# Grid (básico)
GRID_LEVELS=20
GRID_SPACING_PERCENT=0.5
GRID_DISTRIBUTION=symmetric  # symmetric|asymmetric

# Market-Making Grid
GRID_SHIFT_THRESHOLD_PERCENT=1.0
REBALANCE_INTERVAL_SECONDS=60

# Pure Grid (usar quando STRATEGY_TYPE=pure_grid)
RANGE_MIN=90000
RANGE_MAX=110000
RANGE_EXIT=true

# Risco
MARGIN_SAFETY_PERCENT=20
MAX_OPEN_ORDERS=20
MAX_POSITION_SIZE_USD=1000
AUTO_REDUCE_ON_LOW_MARGIN=true

# Operação
CHECK_BALANCE_BEFORE_ORDER=true
CLEAN_ORDERS_ON_START=false
LOG_LEVEL=INFO
```

> **Dica**: Comece conservador (menos níveis, maior espaçamento, ordem menor) e aumente aos poucos.

## 📊 Métricas e logs

- Logs são salvos em `logs/` com timestamp (ex.: `grid_bot_YYYYMMDD_HHMMSS.log`)
- Relatório de performance (win rate, drawdown, Sharpe etc.) é atualizado ao longo da sessão

## 🧪 Troubleshooting (rápido)

- **Bot não inicia**: verifique `.env` e `PRIVATE_KEY`; teste `pacifica_auth.py`
- **Ordens não executam**: cheque margem disponível, grid dentro do range e *REST_URL*
- **Margem crítica**: aumente `MARGIN_SAFETY_PERCENT`, reduza `ORDER_SIZE_USD` ou `GRID_LEVELS`

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

> Feito para a comunidade Pacifica. Pull Requests são bem-vindos!