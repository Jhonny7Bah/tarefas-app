"""Verificação de atualização via releases do GitHub e autoatualização
do app desktop (baixar o pacote, trocar a instalação e reiniciar)."""

import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

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


def dir_instalacao_atual():
    """Pasta do app empacotado no Linux; None quando roda do código."""
    try:
        exe = Path("/proc/self/exe").resolve()
    except OSError:
        return None
    return exe.parent if exe.name == "tarefas" else None


def baixar_arquivo(url, destino, progresso=None):
    """Baixa ``url`` pra ``destino``, chamando progresso(baixado, total)."""
    req = urllib.request.Request(url, headers={"User-Agent": "tarefas-app"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        baixado = 0
        with open(destino, "wb") as arq:
            while bloco := resp.read(64 * 1024):
                arq.write(bloco)
                baixado += len(bloco)
                if progresso:
                    progresso(baixado, total)


def instalar_pacote(caminho_tar, dir_instalacao):
    """Troca o conteúdo da instalação pelo do tar.gz, com swap atômico.

    Extrai numa pasta irmã, valida, e só então renomeia velha -> .velho e
    nova -> instalação: se qualquer passo falhar, a versão em uso fica
    intocada. Apagar os arquivos da versão em execução é seguro no Linux
    (o unlink não derruba o processo que os mantém abertos).
    """
    dir_instalacao = Path(dir_instalacao)
    dir_novo = dir_instalacao.with_name(dir_instalacao.name + ".novo")
    dir_velho = dir_instalacao.with_name(dir_instalacao.name + ".velho")
    shutil.rmtree(dir_novo, ignore_errors=True)
    shutil.rmtree(dir_velho, ignore_errors=True)
    dir_novo.mkdir(parents=True)
    try:
        with tarfile.open(caminho_tar) as tar:
            tar.extractall(dir_novo, filter="data")
        if not (dir_novo / "tarefas").is_file():
            raise ValueError("pacote sem o executável 'tarefas'")
        # o atalho da gaveta aponta pro icon.png da instalação; não deixar sumir
        icone = dir_instalacao / "icon.png"
        if icone.is_file() and not (dir_novo / "icon.png").exists():
            shutil.copy2(icone, dir_novo / "icon.png")
    except BaseException:
        shutil.rmtree(dir_novo, ignore_errors=True)
        raise
    os.rename(dir_instalacao, dir_velho)
    os.rename(dir_novo, dir_instalacao)
    shutil.rmtree(dir_velho, ignore_errors=True)


def reiniciar(dir_instalacao):
    """Abre a versão recém-instalada e encerra este processo.

    Dois cuidados, os dois aprendidos com crash real pós-atualização:
    o sleep dá tempo deste processo morrer antes do novo motor subir, e
    o ambiente vai LIMPO das variáveis do runtime (FLET_*): o filho as
    herdaria apontando pra sockets/caminhos do processo morto. O log em
    reinicio.log guarda a saída do boot pra diagnóstico.
    """
    exe = Path(dir_instalacao) / "tarefas"
    ambiente = {
        chave: valor
        for chave, valor in os.environ.items()
        if not chave.startswith("FLET_")
    }
    destino_log = os.getenv("FLET_APP_STORAGE_DATA") or str(dir_instalacao)
    log = open(os.path.join(destino_log, "reinicio.log"), "wb")
    subprocess.Popen(
        ["/bin/sh", "-c", f'sleep 2; exec "{exe}"'],
        cwd=str(dir_instalacao),
        start_new_session=True,
        env=ambiente,
        stdout=log,
        stderr=log,
    )
    os._exit(0)
