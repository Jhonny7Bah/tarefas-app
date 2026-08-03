"""Autoatualização desktop: swap atômico, falhas seguras e download."""

import os
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from atualizacao import baixar_arquivo, instalar_pacote  # noqa: E402


def cria_pacote(caminho_tar, com_executavel=True):
    with tempfile.TemporaryDirectory() as origem:
        origem = Path(origem)
        if com_executavel:
            exe = origem / "tarefas"
            exe.write_text("#!/bin/sh\necho nova\n")
            exe.chmod(0o755)
        (origem / "lib").mkdir()
        (origem / "lib" / "x.so").write_text("lib")
        with tarfile.open(caminho_tar, "w:gz") as tar:
            for item in sorted(origem.rglob("*")):
                tar.add(item, arcname=str(item.relative_to(origem)))


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    inst = tmp / "app"
    inst.mkdir()
    (inst / "tarefas").write_text("#!/bin/sh\necho velha\n")
    (inst / "tarefas").chmod(0o755)
    (inst / "icon.png").write_text("icone")

    # atualização feliz: troca, preserva ícone, sem sobras
    pacote = tmp / "novo.tar.gz"
    cria_pacote(pacote)
    instalar_pacote(pacote, inst)
    assert (inst / "tarefas").read_text().endswith("nova\n")
    assert os.access(inst / "tarefas", os.X_OK), "bit de execução preservado"
    assert (inst / "icon.png").read_text() == "icone", "ícone preservado"
    assert not (tmp / "app.novo").exists() and not (tmp / "app.velho").exists()

    # pacote sem executável: recusa e não toca na instalação
    ruim = tmp / "ruim.tar.gz"
    cria_pacote(ruim, com_executavel=False)
    try:
        instalar_pacote(ruim, inst)
        raise SystemExit("deveria recusar pacote sem executável")
    except ValueError:
        pass
    assert (inst / "tarefas").read_text().endswith("nova\n"), "intocada"

    # arquivo corrompido: idem
    corrompido = tmp / "c.tar.gz"
    corrompido.write_bytes(b"nao sou tar")
    try:
        instalar_pacote(corrompido, inst)
        raise SystemExit("deveria falhar no tar corrompido")
    except tarfile.TarError:
        pass

    # download com progresso via file://
    fonte = tmp / "fonte.bin"
    fonte.write_bytes(b"x" * 100_000)
    destino = tmp / "baixado.bin"
    chamadas = []
    baixar_arquivo(fonte.as_uri(), destino, lambda f, t: chamadas.append(f))
    assert destino.read_bytes() == fonte.read_bytes()
    assert chamadas and chamadas[-1] == 100_000

print("autoatualização: ok")
