#!/bin/bash
set -e

echo "========================================="
echo "   Bot Pacifica - Instalador/Atualizador "
echo "========================================="
echo
echo "Escolha uma opcao:"
echo "1 - Nova instalacao"
echo "2 - Atualizacao"
read -p "Digite sua opcao (1/2): " choice

URL="https://github.com/lzrbraeth-afk/Bot-Pacifica/archive/refs/heads/master.zip"
ZIP="update.zip"
TMPDIR="update_tmp"

if [ "$choice" = "2" ]; then
    echo
    echo "Movendo o arquivo .env para .env.old..."
    if [ -f ".env" ]; then
        mv -f .env .env.old
        echo "Arquivo .env antigo foi movido para .env.old"
    else
        echo "Nenhum arquivo .env encontrado para mover."
    fi
fi

echo
echo "Baixando a ultima versao do Bot Pacifica..."
curl -L -o "$ZIP" "$URL"

if [ ! -f "$ZIP" ]; then
    echo "Erro: nao foi possivel baixar o pacote."
    exit 1
fi

echo
echo "Extraindo para pasta temporaria..."
rm -rf "$TMPDIR"
unzip -q "$ZIP" -d "$TMPDIR"

echo
echo "Copiando arquivos para o diretorio atual..."
TOPDIR=$(ls "$TMPDIR")
rsync -a "$TMPDIR/$TOPDIR/" ./

echo "Limpando temporarios..."
rm -rf "$ZIP" "$TMPDIR"

echo
echo "========================================="
echo "Instalacao/Atualizacao concluida!"
if [ "$choice" = "2" ]; then
    echo "Lembre-se de:"
    echo "1. Copiar sua API KEY do .env.old"
    echo "2. Renomear o novo .env.example para .env"
fi
echo "========================================="
