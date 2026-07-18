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
    """Última release do repositório: tag, notas e links de download.

    ``url`` é o APK do Android (compatibilidade com o fluxo original);
    ``url_linux`` é o pacote desktop, quando a release tiver um. Os dois
    caem pra ``url_pagina`` (a página da release) quando o asset não existe.
    """
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO_ATUALIZACAO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "tarefas-app"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        dados = json.load(resp)
    url_pagina = dados.get("html_url")
    url_apk = None
    url_linux = None
    for asset in dados.get("assets", []):
        nome = asset.get("name", "")
        if "arm64" in nome:
            url_apk = asset["browser_download_url"]
        elif "linux" in nome:
            url_linux = asset["browser_download_url"]
    return {
        "tag": dados.get("tag_name", ""),
        "notas": dados.get("body") or "",
        "url": url_apk or url_pagina,
        "url_linux": url_linux or url_pagina,
        "url_pagina": url_pagina,
    }
