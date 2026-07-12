#!/usr/bin/env bash
# Builda o APK e publica a release no GitHub — o botão "Verificar
# atualização" do app passa a oferecer essa versão.
#
# Uso:   ./release.sh "o que mudou nessa versão"
#
# Antes de rodar, bumpar a versão nos DOIS lugares:
#   - VERSAO no main.py
#   - version no pyproject.toml
set -euo pipefail
cd "$(dirname "$0")"

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

echo "==> Buildando v$VERSAO_PYPROJECT..."
flet build apk --split-per-abi

echo "==> Publicando release v$VERSAO_PYPROJECT no GitHub..."
gh release create "v$VERSAO_PYPROJECT" build/apk/tarefas-arm64-v8a.apk \
    --title "v$VERSAO_PYPROJECT" --notes "$NOTAS"

echo "==> Pronto! No celular: gaveta -> Verificar atualização -> Baixar"
