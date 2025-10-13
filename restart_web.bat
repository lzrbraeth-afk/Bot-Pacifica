@echo off
chcp 65001 >nul
cls

echo ========================================
echo 🔄 REINICIAR INTERFACE WEB
echo ========================================
echo.

REM Verificar se há processo Python usando porta 5000
echo 🔍 Verificando processos na porta 5000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000.*LISTENING"') do (
    set PID=%%a
    echo 🛑 Finalizando processo PID: %%a
    taskkill /pid %%a /f >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo ✅ Processo finalizado com sucesso
    ) else (
        echo ⚠️  Não foi possível finalizar o processo
    )
)

REM Aguardar um pouco para porta liberar
echo.
echo ⏳ Aguardando 3 segundos para liberar porta...
timeout /t 3 /nobreak >nul

REM Ativar ambiente virtual se existir
if exist ".venv\Scripts\activate.bat" (
    echo.
    echo � Ativando ambiente virtual...
    call .venv\Scripts\activate.bat
)

echo.
echo ========================================
echo 🚀 INICIANDO INTERFACE WEB
echo ========================================
echo.
echo 📊 Dashboard: http://localhost:5000
echo 🛑 Para parar: Ctrl+C
echo.

python app.py

echo.
echo.
echo ========================================
echo 👋 Interface web encerrada
echo ========================================
pause