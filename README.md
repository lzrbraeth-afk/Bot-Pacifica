# Pacifica Grid Trading Bot

Bot de **grid trading** para a corretora **Pacifica** com duas abordagens: **Pure Grid** (clássica) e **Market-Making Grid** (dinâmica). 
Inclui gerenciamento de risco, métricas de performance e logs detalhados.

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

## Video com passo a passo para instalar o BOT, depois de instalado o PYTHON 

<https://www.youtube.com/watch?v=cKypCQwXctc>

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

> Feito para a comunidade Coleta Cripto (https://x.com/Coleta_Cripto). Pull Requests são bem-vindos!
