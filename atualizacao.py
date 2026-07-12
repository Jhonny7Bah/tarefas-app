"""Verificação de atualização via releases do GitHub."""

import json
import urllib.request

REPO_ATUALIZACAO = "Jhonny7Bah/tarefas-app"


def parse_versao(v):
    """'v1.2.3' -> (1, 2, 3); qualquer coisa inválida -> (0,)."""
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except (ValueError, AttributeError):
        return (0,)


def buscar_ultima_release():
    """Última release do repositório: tag, notas e link de download do APK."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO_ATUALIZACAO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "tarefas-app"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        dados = json.load(resp)
    url = dados.get("html_url")  # página da release, caso não ache o APK
    for asset in dados.get("assets", []):
        if "arm64" in asset.get("name", ""):
            url = asset["browser_download_url"]
            break
    return {
        "tag": dados.get("tag_name", ""),
        "notas": dados.get("body") or "",
        "url": url,
    }
