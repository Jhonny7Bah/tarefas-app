"""Fundação do sync: migração de banco antigo, carimbos, lápides, backup."""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402


def banco_antigo(caminho):
    """Schema como era antes da fundação do sync (v1.7.x)."""
    con = sqlite3.connect(caminho)
    con.executescript(
        """
        CREATE TABLE tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            categoria TEXT NOT NULL DEFAULT 'Padrão',
            concluida INTEGER NOT NULL DEFAULT 0,
            criada_em TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            prioridade INTEGER NOT NULL DEFAULT 1,
            prazo TEXT, concluida_em TEXT, descricao_conclusao TEXT,
            repetir TEXT, aparece_em TEXT
        );
        CREATE TABLE listas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            oculta INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE subtarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarefa_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            concluida INTEGER NOT NULL DEFAULT 0,
            criada_em TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            concluida_em TEXT
        );
        CREATE TABLE tarefa_listas (
            tarefa_id INTEGER NOT NULL, lista TEXT NOT NULL,
            UNIQUE (tarefa_id, lista)
        );
        INSERT INTO tarefas (titulo, criada_em) VALUES ('antiga', '2026-07-01 10:00');
        INSERT INTO tarefa_listas VALUES (1, 'Padrão');
        """
    )
    con.commit()
    con.close()


def linha(sql, *params):
    con = sqlite3.connect(db.DB)
    con.row_factory = sqlite3.Row
    r = con.execute(sql, params).fetchone()
    con.close()
    return r


with tempfile.TemporaryDirectory() as tmp:
    db.DB = str(Path(tmp) / "t.db")

    # migração de banco antigo: colunas novas + backfill
    banco_antigo(db.DB)
    db.init_db()
    t = linha("SELECT * FROM tarefas WHERE id = 1")
    assert t["uuid"] and t["modificado_em"] == "2026-07-01 10:00"
    assert t["sync_pendente"] == 1, "banco pré-sync começa pendente"

    # mutadores carimbam
    db.adicionar_tarefa("nova", ["Padrão"])
    tid = linha("SELECT id FROM tarefas WHERE titulo = 'nova'")["id"]
    con = sqlite3.connect(db.DB)
    con.execute("UPDATE tarefas SET sync_pendente = 0")
    con.commit()
    con.close()
    db.marcar_concluida(tid, True)
    assert linha("SELECT sync_pendente s FROM tarefas WHERE id = ?", tid)["s"] == 1

    # lápide na exclusão; desfazer reusa uuid e remove a lápide
    uid = linha("SELECT uuid FROM tarefas WHERE id = ?", tid)["uuid"]
    snap = db.snapshot_tarefa(tid)
    db.excluir_tarefa(tid)
    assert linha("SELECT tipo FROM exclusoes WHERE uuid = ?", uid)["tipo"] == "tarefa"
    novo_id = db.restaurar_tarefa(snap)
    assert linha("SELECT uuid FROM tarefas WHERE id = ?", novo_id)["uuid"] == uid
    assert linha("SELECT COUNT(*) c FROM exclusoes WHERE uuid = ?", uid)["c"] == 0

    # backup schema 2: uuid sobrevive à ida e volta
    dados = json.loads(db.exportar_json())
    assert dados["schema"] == 2 and all(x["uuid"] for x in dados["tarefas"])
    db.importar_json(json.dumps(dados))
    assert linha("SELECT COUNT(*) c FROM tarefas WHERE uuid = ?", uid)["c"] == 1

    # virar_estado_novo: recarimba tudo e deixa lápide pro que sumiu
    antes = db.uuids_atuais()
    con = sqlite3.connect(db.DB)
    con.execute("DELETE FROM tarefas WHERE uuid = ?", (uid,))
    con.commit()
    con.close()
    db.virar_estado_novo(antes)
    assert linha("SELECT COUNT(*) c FROM exclusoes WHERE uuid = ?", uid)["c"] == 1
    assert linha("SELECT COUNT(*) c FROM tarefas WHERE sync_pendente = 0")["c"] == 0

print("fundação do sync: ok")
