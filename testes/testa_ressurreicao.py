"""Testes do bug da ressurreição: relógio adiantado + pendente sagrado.

Servidor FALSO em memória (monkeypatch em sync._req): nenhum byte sai
da máquina; os dados reais do usuário ficam intocados.
"""

import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/home/umcex/Documents/Projetos/gerenciador_de_tarefas")
import db  # noqa: E402
import sync  # noqa: E402

CFG = {"url": "http://falso", "chave": "falsa"}
REMOTO = {"tarefas": {}, "listas": {}}
UPSERTS = []


def req_falso(cfg, metodo, caminho, corpo=None, prefer=None):
    tabela = caminho.split("?")[0]
    if metodo == "GET":
        return list(REMOTO[tabela].values())
    if metodo == "POST":
        UPSERTS.append((tabela, corpo))
        for linha in corpo:
            REMOTO[tabela][linha["uuid"]] = linha
        return None
    raise AssertionError(f"metodo inesperado: {metodo}")


sync._req = req_falso


def agora_mais(segundos):
    return (datetime.now() + timedelta(seconds=segundos)).isoformat(
        sep=" ", timespec="seconds"
    )


def linha(sql, *params):
    con = sqlite3.connect(db.DB)
    con.row_factory = sqlite3.Row
    r = con.execute(sql, params).fetchone()
    con.close()
    return r


with tempfile.TemporaryDirectory() as tmp:
    db.DB = str(Path(tmp) / "aparelho.db")
    db.init_db()

    # --- cenário do crime: conclusão local x remoto "do futuro" ---------
    db.adicionar_tarefa("pagar boleto", ["Padrão"])
    t = linha("SELECT * FROM tarefas WHERE titulo = 'pagar boleto'")
    uid = t["uuid"]
    # primeiro sync: sobe a tarefa; remoto fica com ela pendente
    sync.sincronizar(CFG)
    assert uid in REMOTO["tarefas"], "tarefa subiu pro servidor falso"

    # outro aparelho (relógio 2 min adiantado) mexeu nela: versão PENDENTE
    # com carimbo no futuro
    REMOTO["tarefas"][uid] = {
        "uuid": uid,
        "dados": {**REMOTO["tarefas"][uid]["dados"], "concluida": False},
        "modificado_em": agora_mais(120),
        "excluida": False,
    }
    carimbo_futuro = REMOTO["tarefas"][uid]["modificado_em"]

    # usuário conclui AGORA (carimbo local < carimbo remoto futuro)
    tid = linha("SELECT id FROM tarefas WHERE uuid = ?", uid)["id"]
    db.marcar_concluida(tid, True)
    assert linha("SELECT concluida c FROM tarefas WHERE uuid = ?", uid)["c"] == 1

    # o sync que ANTES ressuscitava a tarefa
    sync.sincronizar(CFG)
    t = linha("SELECT * FROM tarefas WHERE uuid = ?", uid)
    assert t["concluida"] == 1, "BUG: a conclusão foi atropelada pelo pull!"
    assert t["modificado_em"] > carimbo_futuro, "carimbo local venceu o futuro"
    assert t["sync_pendente"] == 0, "conclusão foi enviada e marcada"
    assert REMOTO["tarefas"][uid]["dados"]["concluida"] is True, (
        "servidor recebeu a conclusão vencedora"
    )

    # segunda rodada: nada muda (estável, sem ping-pong)
    r = sync.sincronizar(CFG)
    assert r == {"recebidas": 0, "enviadas": 0}, f"deveria estar estável: {r}"
    assert linha("SELECT concluida c FROM tarefas WHERE uuid = ?", uid)["c"] == 1

    # --- exclusão remota "do futuro" x edição local pendente ------------
    db.adicionar_tarefa("rascunho importante", ["Padrão"])
    t2 = linha("SELECT * FROM tarefas WHERE titulo = 'rascunho importante'")
    sync.sincronizar(CFG)
    REMOTO["tarefas"][t2["uuid"]] = {
        "uuid": t2["uuid"],
        "dados": {},
        "modificado_em": agora_mais(90),
        "excluida": True,
    }
    tid2 = linha("SELECT id FROM tarefas WHERE uuid = ?", t2["uuid"])["id"]
    db.atualizar_tarefa(tid2, "rascunho editado", ["Padrão"], 2, None)
    sync.sincronizar(CFG)
    t2b = linha("SELECT * FROM tarefas WHERE uuid = ?", t2["uuid"])
    assert t2b is not None and t2b["titulo"] == "rascunho editado", (
        "edição pendente sobreviveu à exclusão remota do futuro"
    )
    assert REMOTO["tarefas"][t2["uuid"]]["excluida"] is False, "e reviveu no servidor"

    # --- pull normal continua funcionando (local NÃO pendente) ----------
    REMOTO["tarefas"][uid] = {
        "uuid": uid,
        "dados": {**REMOTO["tarefas"][uid]["dados"], "titulo": "pagar boleto v2"},
        "modificado_em": agora_mais(180),
        "excluida": False,
    }
    sync.sincronizar(CFG)
    assert linha("SELECT titulo t FROM tarefas WHERE uuid = ?", uid)["t"] == (
        "pagar boleto v2"
    ), "remoto mais novo aplica quando não há pendência local"

    # --- marcar_enviadas só limpa se o carimbo não mudou ----------------
    con = sqlite3.connect(db.DB)
    con.execute(
        "UPDATE tarefas SET sync_pendente = 1, modificado_em = '2026-08-02 10:00:00'"
        " WHERE uuid = ?",
        (uid,),
    )
    con.commit()
    con.close()
    db.marcar_enviadas([(uid, "2026-08-02 09:59:59")], [])  # carimbo VELHO
    assert linha("SELECT sync_pendente s FROM tarefas WHERE uuid = ?", uid)["s"] == 1, (
        "carimbo divergente: flag fica de pé (mudança no meio do envio)"
    )
    db.marcar_enviadas([(uid, "2026-08-02 10:00:00")], [])  # carimbo certo
    assert linha("SELECT sync_pendente s FROM tarefas WHERE uuid = ?", uid)["s"] == 0

    # --- limite novo de subtarefas ---------------------------------------
    db.adicionar_tarefa("muitas subtarefas", ["Padrão"])
    tid3 = linha("SELECT id FROM tarefas WHERE titulo = 'muitas subtarefas'")["id"]
    criadas = sum(1 for i in range(25) if db.adicionar_subtarefa(tid3, f"sub {i}"))
    assert criadas == 20, f"limite deveria ser 20, criou {criadas}"

print("ressurreição e corridas: todos os testes passaram")
