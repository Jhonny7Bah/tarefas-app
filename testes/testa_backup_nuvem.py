"""Backup na nuvem + rollback nos 3: testes com servidor falso em memória."""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/umcex/Documents/Projetos/gerenciador_de_tarefas")
import db  # noqa: E402
import sync  # noqa: E402

CFG = {"url": "http://falso", "chave": "falsa"}
REMOTO = {"tarefas": {}, "listas": {}}
BACKUPS = {}
PROXIMO_ID = [1]


def req_falso(cfg, metodo, caminho, corpo=None, prefer=None):
    tabela = caminho.split("?")[0]
    if tabela == "backups":
        if metodo == "POST":
            for linha in corpo:
                BACKUPS[PROXIMO_ID[0]] = {**linha, "id": PROXIMO_ID[0]}
                PROXIMO_ID[0] += 1
            return None
        if metodo == "GET" and "id=eq." in caminho:
            bid = int(caminho.split("id=eq.")[1].split("&")[0])
            return [{"conteudo": BACKUPS[bid]["conteudo"]}] if bid in BACKUPS else []
        if metodo == "GET":
            fotos = sorted(BACKUPS.values(), key=lambda b: b["criado_em"], reverse=True)
            return [
                {k: b[k] for k in ("id", "criado_em", "dispositivo")} for b in fotos
            ]
        if metodo == "DELETE":
            ids = caminho.split("id=in.(")[1].rstrip(")").split(",")
            for i in ids:
                BACKUPS.pop(int(i), None)
            return None
    if metodo == "GET":
        return list(REMOTO[tabela].values())
    if metodo == "POST":
        for linha in corpo:
            REMOTO[tabela][linha["uuid"]] = linha
        return None
    raise AssertionError(f"chamada inesperada: {metodo} {caminho}")


sync._req = req_falso


def linha(sql, *params):
    con = sqlite3.connect(db.DB)
    con.row_factory = sqlite3.Row
    r = con.execute(sql, params).fetchone()
    con.close()
    return r


with tempfile.TemporaryDirectory() as tmp:
    aparelho_a = str(Path(tmp) / "a.db")
    aparelho_b = str(Path(tmp) / "b.db")

    # A: cria t1, sincroniza, tira a foto
    db.DB = aparelho_a
    db.init_db()
    db.adicionar_tarefa("t1 antiga", ["Padrão"])
    sync.sincronizar(CFG)
    sync.salvar_backup_nuvem(CFG, db.exportar_json(), "computador")
    assert len(BACKUPS) == 1, "foto salva"

    # A: cria t2 DEPOIS da foto e sincroniza
    db.adicionar_tarefa("t2 nova demais", ["Padrão"])
    sync.sincronizar(CFG)

    # B: entra na roda e recebe t1 + t2
    db.DB = aparelho_b
    db.init_db()
    sync.sincronizar(CFG)
    assert linha("SELECT COUNT(*) c FROM tarefas")["c"] == 2, "B recebeu as duas"

    # A: restaura a foto (t1 só) e vira estado novo
    db.DB = aparelho_a
    foto_id = sync.listar_backups_nuvem(CFG)[0]["id"]
    conteudo = sync.baixar_backup_nuvem(CFG, foto_id)
    antes = db.uuids_atuais()
    db.importar_json(conteudo)
    db.virar_estado_novo(antes)
    assert linha("SELECT COUNT(*) c FROM tarefas")["c"] == 1, "A voltou pra foto"
    assert linha("SELECT COUNT(*) c FROM exclusoes")["c"] >= 1, "lápide da t2"
    sync.sincronizar(CFG)

    # B: sincroniza e o rollback chega nele (t2 morre, t1 fica)
    db.DB = aparelho_b
    sync.sincronizar(CFG)
    titulos = [
        r[0]
        for r in sqlite3.connect(db.DB).execute("SELECT titulo FROM tarefas").fetchall()
    ]
    assert titulos == ["t1 antiga"], f"B deveria ter só t1: {titulos}"

    # retenção: sobe 25 fotos, ficam as 20 mais novas
    db.DB = aparelho_a
    for i in range(25):
        sync.salvar_backup_nuvem(CFG, db.exportar_json(), f"teste{i}")
    assert len(BACKUPS) == sync.MAX_BACKUPS_NUVEM, f"retencao: {len(BACKUPS)}"

print("backup na nuvem e rollback nos 3: todos os testes passaram")
