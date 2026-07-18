#!/usr/bin/env bash
# Builda o APK e o pacote desktop Linux e publica a release no GitHub —
# o botão "Verificar atualização" do app passa a oferecer essa versão
# (o Android baixa o .apk, o desktop baixa o .tar.gz).
#
# Uso:   ./release.sh "o que mudou nessa versão"
#
# Antes de rodar, bumpar a versão nos DOIS lugares:
#   - VERSAO no main.py
#   - version no pyproject.toml
set -euo pipefail
cd "$(dirname "$0")"

FLET=.venv/bin/flet
export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"

VERSAO_PYPROJECT=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
VERSAO_MAIN=$(grep -m1 '^VERSAO' main.py | cut -d'"' -f2)

if [[ "$VERSAO_PYPROJECT" != "$VERSAO_MAIN" ]]; then
    echo "ERRO: versões dessincronizadas — pyproject.toml=$VERSAO_PYPROJECT, main.py=$VERSAO_MAIN"
    exit 1
fi

if gh release view "v$VERSAO_PYPROJECT" &>/dev/null; then
    echo "ERRO: a release v$VERSAO_PYPROJECT já existe. Bumpa a versão primeiro."
    exit 1
fi

NOTAS="${1:-Atualização v$VERSAO_PYPROJECT}"

echo "==> Buildando APK v$VERSAO_PYPROJECT..."
$FLET build apk --split-per-abi

echo "==> Buildando desktop Linux v$VERSAO_PYPROJECT..."
# As flags contornam o -Werror do runner do Flutter em cima dos headers
# do Python do serious_python (macro redefinida vira erro no clang novo)
CFLAGS="-Wno-macro-redefined" CXXFLAGS="-Wno-macro-redefined" $FLET build linux

echo "==> Empacotando tarefas-linux-x64.tar.gz..."
# Conteúdo na raiz do tar: extrair direto por cima de ~/.local/opt/tarefas.
# O icon.png vai junto porque o atalho .desktop da gaveta aponta pra ele
cp assets/icon.png build/linux/icon.png
tar -czf build/tarefas-linux-x64.tar.gz -C build/linux .

echo "==> Publicando release v$VERSAO_PYPROJECT no GitHub..."
gh release create "v$VERSAO_PYPROJECT" \
    build/apk/tarefas-arm64-v8a.apk \
    build/tarefas-linux-x64.tar.gz \
    --title "v$VERSAO_PYPROJECT" --notes "$NOTAS"

echo "==> Pronto! No celular: gaveta -> Verificar atualização -> Baixar"
echo "    No PC: baixar o tar.gz e extrair em ~/.local/opt/tarefas"
