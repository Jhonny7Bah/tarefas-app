"""Regra da contaminação: uma lista oculta esconde a tarefa inteira."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/umcex/Documents/Projetos/gerenciador_de_tarefas")
import db  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    db.DB = str(Path(tmp) / "t.db")
    db.init_db()
    db.criar_lista("Visivel")
    db.criar_lista("Oculta", oculta=True)

    db.adicionar_tarefa("só visível", ["Visivel"])
    db.adicionar_tarefa("só oculta", ["Oculta"])
    db.adicionar_tarefa("contaminada", ["Visivel", "Oculta"])

    todas = {t["titulo"] for t in db.listar_pendentes(None)}
    assert todas == {"só visível"}, f"Todas mostrou: {todas}"

    visivel = {t["titulo"] for t in db.listar_pendentes("Visivel")}
    assert visivel == {"só visível"}, f"filtro Visivel mostrou: {visivel}"

    oculta = {t["titulo"] for t in db.listar_pendentes("Oculta")}
    assert oculta == {"só oculta", "contaminada"}, f"filtro Oculta mostrou: {oculta}"

    cont = db.contagens()
    assert cont["todas"] == 1, f"contador Todas: {cont['todas']}"
    assert cont["por_lista"].get("Visivel") == 1, f"contador Visivel: {cont}"
    assert cont["por_lista"].get("Oculta") == 2, f"contador Oculta: {cont}"

    # desocultar a lista devolve tudo ao Todas
    lid = next(r["id"] for r in db.listar_listas() if r["nome"] == "Oculta")
    db.renomear_lista(lid, "Oculta", False)
    todas = {t["titulo"] for t in db.listar_pendentes(None)}
    assert todas == {"só visível", "só oculta", "contaminada"}, (
        f"apos desocultar: {todas}"
    )

print("regra da contaminação: todos os testes passaram")
