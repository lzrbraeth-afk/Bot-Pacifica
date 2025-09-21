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
- `git` instalado

### 2) Clonar o repositório
```bash
git clone https://github.com/SEU_USUARIO/pacifica-grid-bot.git
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

> Se você já tiver um arquivo `requirements.tx`, renomeie para `requirements.txt` antes do comando acima.

### 4) Configuração (.env)

Copie o arquivo de exemplo e edite os valores:

```bash
cp .env.example .env   # no Windows use: copy .env.example .env
```

Edite **PRIVATE_KEY**, **SYMBOL** e demais parâmetros conforme sua preferência (ver seção Configuração).

## ⚙️ Configuração (.env)

Parâmetros essenciais:

```ini
# API / Segurança
PRIVATE_KEY=SEU_PRIVKEY_WALLET
WALLET_ADDRESS=COLOQUE_SUA_SOL_WALLET_ADDRESS
REST_URL=https://api.pacifica.fi/api/v1
WS_URL=wss://ws.pacifica.fi/ws


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

## ▶️ Como executar

```bash
python grid_bot.py
```

Primeira execução:
```bash
python pacifica_auth.py      # testa credenciais/conexão
python grid_bot.py | tee -a bot_output.log   # roda com log espelhado
```

Para encerrar com segurança: `Ctrl + C` (o bot finaliza e imprime um resumo).

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