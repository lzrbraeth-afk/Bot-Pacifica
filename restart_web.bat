@echo off
echo 🔄 Reiniciando interface web com correções WebSocket...

REM Matar processo da interface web se estiver rodando
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python.exe" /fo csv ^| findstr app.py') do (
    echo 🛑 Finalizando processo Python anterior...
    taskkill /pid %%a /f >nul 2>&1
)

REM Aguardar um pouco
timeout /t 2 /nobreak >nul

echo 🚀 Iniciando interface web corrigida...
python app.py

pause