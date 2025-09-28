@echo off
setlocal enabledelayedexpansion

echo =========================================
echo    Bot Pacifica - Instalador/Atualizador
echo =========================================
echo.
echo Escolha uma opcao:
echo 1 - Nova instalacao
echo 2 - Atualizacao
set /p choice="Digite sua opcao (1/2): "

:: Configuracoes
set URL=https://github.com/lzrbraeth-afk/Bot-Pacifica/archive/refs/heads/master.zip
set ZIP=update.zip
set TMPDIR=update_tmp

if "%choice%"=="2" (
    echo.
    echo Movendo o arquivo .env para .env.old...
    if exist .env (
        move /Y .env .env.old >nul
        echo Arquivo .env antigo foi movido para .env.old
    ) else (
        echo Nenhum arquivo .env encontrado para mover.
    )
)

echo.
echo Baixando a ultima versao do Bot Pacifica...
powershell -Command "Invoke-WebRequest -Uri %URL% -OutFile %ZIP%"

if not exist %ZIP% (
    echo Erro: nao foi possivel baixar o pacote.
    pause
    exit /b
)

echo.
echo Extraindo para pasta temporaria...
rmdir /S /Q %TMPDIR% >nul 2>&1
powershell -Command "Expand-Archive -Path %ZIP% -DestinationPath %TMPDIR% -Force"

echo.
echo Copiando arquivos para o diretorio atual...
for /d %%D in (%TMPDIR%\*) do (
    robocopy "%%D" "." /E /NFL /NDL /NJH /NJS /nc /ns /np
)

echo Limpando temporarios...
del %ZIP%
rmdir /S /Q %TMPDIR%

echo.
echo =========================================
echo Instalacao/Atualizacao concluida!
if "%choice%"=="2" (
    echo Lembre-se de:
    echo 1. Copiar os valores da sua API KEY do .env.old
    echo 2. Renomear o novo .env.example para .env
)
echo =========================================
pause
