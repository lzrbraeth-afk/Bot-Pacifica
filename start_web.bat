@echo off
chcp 65001 >nul
cls

echo ========================================
echo 🌐 INTERFACE WEB - PACIFICA BOT
echo ========================================
echo.

REM Verificar se Python está instalado
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Python não encontrado!
    echo    Instale Python 3.10+ para continuar
    echo.
    echo 📥 Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo 🐍 Python detectado
python --version

REM Verificar se ambiente virtual existe
if not exist ".venv\" if not exist "venv\" (
    echo.
    echo ⚠️  Ambiente virtual não encontrado
    set /p CREATE_VENV="❓ Deseja criar um ambiente virtual? (s/n): "
    
    if /i "%CREATE_VENV%"=="s" (
        echo.
        echo 📦 Criando ambiente virtual...
        python -m venv .venv
        
        if %ERRORLEVEL% EQU 0 (
            echo ✅ Ambiente virtual criado em .venv\
        ) else (
            echo ❌ Erro ao criar ambiente virtual
            pause
            exit /b 1
        )
    )
)

REM Ativar ambiente virtual
if exist ".venv\Scripts\activate.bat" (
    echo.
    echo 🔄 Ativando ambiente virtual (.venv)...
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo.
    echo 🔄 Ativando ambiente virtual (venv)...
    call venv\Scripts\activate.bat
) else (
    echo.
    echo ⚠️  Usando Python global (ambiente virtual não encontrado)
)

REM Verificar dependências
if exist "requirements.txt" (
    echo.
    set /p INSTALL_DEPS="❓ Deseja verificar/instalar dependências? (s/n): "
    
    if /i "%INSTALL_DEPS%"=="s" (
        echo.
        echo 📦 Instalando dependências...
        pip install -r requirements.txt
        
        if %ERRORLEVEL% NEQ 0 (
            echo.
            echo ⚠️  Alguns pacotes podem não ter sido instalados
            echo    Mas vamos tentar iniciar mesmo assim...
            timeout /t 3 >nul
        )
    )
) else (
    echo.
    echo ⚠️  Arquivo requirements.txt não encontrado
    echo    Certifique-se de ter instalado as dependências
)

REM Verificar app.py
if not exist "app.py" (
    echo.
    echo ❌ Arquivo app.py não encontrado!
    echo    Certifique-se de estar no diretório correto
    echo.
    echo 📁 Diretório atual: %CD%
    pause
    exit /b 1
)

REM Verificar .env
if not exist ".env" (
    echo.
    echo ⚠️  Arquivo .env não encontrado!
    echo    A interface pode não funcionar corretamente
    echo.
    echo 💡 Dica: Copie .env.example para .env e configure
    echo.
    set /p CONTINUE="❓ Deseja continuar mesmo assim? (s/n): "
    
    if /i not "%CONTINUE%"=="s" (
        exit /b 1
    )
)

REM Criar diretórios necessários
echo.
echo 📁 Verificando diretórios...
if not exist "templates\" mkdir templates
if not exist "logs\" mkdir logs
if not exist "data\" mkdir data
echo ✅ Diretórios OK

REM Verificar se porta 5000 está livre
netstat -ano | findstr ":5000" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ⚠️  ATENÇÃO: Porta 5000 parece estar em uso
    echo    A interface pode não iniciar corretamente
    echo.
    set /p CONTINUE_PORT="❓ Deseja tentar mesmo assim? (s/n): "
    
    if /i not "%CONTINUE_PORT%"=="s" (
        echo.
        echo 💡 Dica: Feche outros serviços na porta 5000 ou
        echo    edite app.py para usar outra porta
        pause
        exit /b 1
    )
)

REM Iniciar interface web
echo.
echo ========================================
echo 🚀 INICIANDO INTERFACE WEB
echo ========================================
echo.
echo 📊 Dashboard: http://localhost:5000
echo 🔌 WebSocket: Ativado
echo 📈 Gráficos: Chart.js
echo 📥 Export: CSV ^& PDF
echo.
echo 🛑 Para parar: Ctrl+C
echo.
echo ========================================
echo.

REM Aguardar 2 segundos antes de iniciar
timeout /t 2 >nul

REM Executar app.py
python app.py

REM Mensagem de encerramento
echo.
echo.
echo ========================================
echo 👋 Interface web encerrada
echo ========================================
echo.

REM Desativar ambiente virtual se estava ativo
if defined VIRTUAL_ENV (
    deactivate
)

pause