"""
App de Tarefas — em Flet (compatível com Flet 0.85)
---------------------------------------------------
Baseado no documento "Ideia de App Tarefa":
- Tarefas agrupadas por situação: Atrasada / Hoje / Próximas / Sem data
- Prioridade (alta/média/baixa) ordena sozinha; prazo desempata
- Registro de criação e conclusão de cada tarefa
- Adicionar em lote (uma tarefa por linha)
- Desfazer a última conclusão
- Gaveta lateral com listas, contadores e filtro
- Listas dinâmicas, com opção de ocultar do "Todas"
- Persistência local com SQLite (roda offline)

Rodar no desktop:   flet run main.py
Rodar no navegador: flet run --web main.py
Empacotar Android:  flet build apk
"""

from datetime import datetime, date

import sqlite3
import flet as ft

DB = "tarefas.db"

LISTAS_INICIAIS = ["Padrão", "Financeiro", "Pessoal", "Compras", "Trabalho", "Tech"]

# prioridade: 2 = alta, 1 = média, 0 = baixa
PRIORIDADES = {"Alta": 2, "Média": 1, "Baixa": 0}
COR_PRIORIDADE = {2: "#ef4444", 1: "#f59e0b", 0: "#475569"}

COR_FUNDO = "#0f2540"
COR_CARD = "#16335c"
COR_AZUL = "#1e6fd0"
COR_TEXTO_SUAVE = "#94a3b8"
COR_ATRASADA = "#f87171"


# ---------------------------------------------------------------------------
# Camada de dados (SQLite)
# ---------------------------------------------------------------------------
def init_db():
    con = sqlite3.connect(DB)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS tarefas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo       TEXT NOT NULL,
            categoria    TEXT NOT NULL DEFAULT 'Padrão',
            concluida    INTEGER NOT NULL DEFAULT 0,
            criada_em    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS listas (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            nome   TEXT NOT NULL UNIQUE,
            oculta INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    # Migração: colunas novas em bancos criados por versões anteriores
    existentes = {r[1] for r in con.execute("PRAGMA table_info(tarefas)")}
    if "prioridade" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN prioridade INTEGER NOT NULL DEFAULT 1")
    if "prazo" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN prazo TEXT")
    if "concluida_em" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN concluida_em TEXT")
    if "descricao_conclusao" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN descricao_conclusao TEXT")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS subtarefas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tarefa_id    INTEGER NOT NULL,
            titulo       TEXT NOT NULL,
            concluida    INTEGER NOT NULL DEFAULT 0,
            criada_em    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            concluida_em TEXT
        )
        """
    )
    # Semeia as listas padrão + qualquer categoria que já exista nas tarefas
    for nome in LISTAS_INICIAIS:
        con.execute("INSERT OR IGNORE INTO listas (nome) VALUES (?)", (nome,))
    con.execute(
        "INSERT OR IGNORE INTO listas (nome) SELECT DISTINCT categoria FROM tarefas"
    )
    con.commit()
    con.close()


def listar_listas():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    linhas = con.execute("SELECT * FROM listas ORDER BY nome").fetchall()
    con.close()
    return linhas


def criar_lista(nome, oculta=False):
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT OR IGNORE INTO listas (nome, oculta) VALUES (?, ?)",
        (nome, 1 if oculta else 0),
    )
    con.commit()
    con.close()


def buscar_tarefas(termo):
    """Busca por título ou descrição de conclusão, pendentes e concluídas."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    padrao = "%" + termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    linhas = con.execute(
        r"""
        SELECT * FROM tarefas
        WHERE titulo LIKE ? ESCAPE '\' OR descricao_conclusao LIKE ? ESCAPE '\'
        ORDER BY concluida ASC, prioridade DESC, (prazo IS NULL), prazo ASC, id DESC
        """,
        (padrao, padrao),
    ).fetchall()
    con.close()
    return linhas


def renomear_lista(lid, novo_nome, oculta):
    """Renomeia/alterna oculta e propaga o novo nome pras tarefas."""
    con = sqlite3.connect(DB)
    antigo = con.execute("SELECT nome FROM listas WHERE id = ?", (lid,)).fetchone()
    if antigo:
        con.execute(
            "UPDATE listas SET nome = ?, oculta = ? WHERE id = ?",
            (novo_nome, 1 if oculta else 0, lid),
        )
        con.execute(
            "UPDATE tarefas SET categoria = ? WHERE categoria = ?",
            (novo_nome, antigo[0]),
        )
        con.commit()
    con.close()


def excluir_lista(lid):
    """Apaga a lista; as tarefas dela vão pra 'Padrão' (nada se perde)."""
    con = sqlite3.connect(DB)
    nome = con.execute("SELECT nome FROM listas WHERE id = ?", (lid,)).fetchone()
    if nome and nome[0] != "Padrão":
        con.execute("UPDATE tarefas SET categoria = 'Padrão' WHERE categoria = ?", (nome[0],))
        con.execute("DELETE FROM listas WHERE id = ?", (lid,))
        con.commit()
    con.close()


def contar_por_lista_total():
    """Total de tarefas (pendentes + concluídas) por lista, pra tela de gerenciamento."""
    con = sqlite3.connect(DB)
    linhas = dict(
        con.execute("SELECT categoria, COUNT(*) FROM tarefas GROUP BY categoria").fetchall()
    )
    con.close()
    return linhas


def listar_pendentes(lista=None):
    """Pendentes de uma lista, ou de todas (excluindo listas ocultas)."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    base = """
        SELECT t.* FROM tarefas t
        WHERE t.concluida = 0 {filtro}
        ORDER BY t.prioridade DESC, (t.prazo IS NULL), t.prazo ASC, t.id DESC
    """
    if lista is None:
        # "Todas": esconde tarefas de listas marcadas como ocultas
        q = base.format(
            filtro="AND t.categoria NOT IN (SELECT nome FROM listas WHERE oculta = 1)"
        )
        linhas = con.execute(q).fetchall()
    else:
        q = base.format(filtro="AND t.categoria = ?")
        linhas = con.execute(q, (lista,)).fetchall()
    con.close()
    return linhas


def listar_concluidas(lista=None):
    """Concluídas, mais recentes primeiro. Sempre mostra todas as listas."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    q = "SELECT * FROM tarefas WHERE concluida = 1"
    params = ()
    if lista is not None:
        q += " AND categoria = ?"
        params = (lista,)
    q += " ORDER BY concluida_em DESC, id DESC"
    linhas = con.execute(q, params).fetchall()
    con.close()
    return linhas


def salvar_descricao_conclusao(tid, texto):
    con = sqlite3.connect(DB)
    con.execute(
        "UPDATE tarefas SET descricao_conclusao = ? WHERE id = ?",
        (texto.strip() or None, tid),
    )
    con.commit()
    con.close()


def contagens():
    """Contadores pra gaveta: pendentes por lista, total 'Todas' e concluídas."""
    con = sqlite3.connect(DB)
    por_lista = dict(
        con.execute(
            "SELECT categoria, COUNT(*) FROM tarefas WHERE concluida = 0 GROUP BY categoria"
        ).fetchall()
    )
    todas = con.execute(
        """
        SELECT COUNT(*) FROM tarefas
        WHERE concluida = 0
          AND categoria NOT IN (SELECT nome FROM listas WHERE oculta = 1)
        """
    ).fetchone()[0]
    concluidas = con.execute(
        "SELECT COUNT(*) FROM tarefas WHERE concluida = 1"
    ).fetchone()[0]
    con.close()
    return {"por_lista": por_lista, "todas": todas, "concluidas": concluidas}


def adicionar_tarefa(titulo, categoria, prioridade=1, prazo=None):
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO tarefas (titulo, categoria, prioridade, prazo) VALUES (?, ?, ?, ?)",
        (titulo, categoria, prioridade, prazo),
    )
    con.commit()
    con.close()


def atualizar_tarefa(tid, titulo, categoria, prioridade, prazo):
    con = sqlite3.connect(DB)
    con.execute(
        "UPDATE tarefas SET titulo = ?, categoria = ?, prioridade = ?, prazo = ? WHERE id = ?",
        (titulo, categoria, prioridade, prazo, tid),
    )
    con.commit()
    con.close()


def excluir_tarefa(tid):
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM subtarefas WHERE tarefa_id = ?", (tid,))
    con.execute("DELETE FROM tarefas WHERE id = ?", (tid,))
    con.commit()
    con.close()


MAX_SUBTAREFAS = 10


def listar_subtarefas(tarefa_id):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    linhas = con.execute(
        "SELECT * FROM subtarefas WHERE tarefa_id = ? ORDER BY id", (tarefa_id,)
    ).fetchall()
    con.close()
    return linhas


def adicionar_subtarefa(tarefa_id, titulo):
    """Respeita o limite do documento: até 10 subtarefas por tarefa."""
    con = sqlite3.connect(DB)
    total = con.execute(
        "SELECT COUNT(*) FROM subtarefas WHERE tarefa_id = ?", (tarefa_id,)
    ).fetchone()[0]
    if total >= MAX_SUBTAREFAS:
        con.close()
        return False
    con.execute(
        "INSERT INTO subtarefas (tarefa_id, titulo) VALUES (?, ?)", (tarefa_id, titulo)
    )
    con.commit()
    con.close()
    return True


def marcar_subtarefa(sid, valor):
    con = sqlite3.connect(DB)
    if valor:
        con.execute(
            "UPDATE subtarefas SET concluida = 1, concluida_em = datetime('now','localtime') WHERE id = ?",
            (sid,),
        )
    else:
        con.execute(
            "UPDATE subtarefas SET concluida = 0, concluida_em = NULL WHERE id = ?", (sid,)
        )
    con.commit()
    con.close()


def excluir_subtarefa(sid):
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM subtarefas WHERE id = ?", (sid,))
    con.commit()
    con.close()


def progresso_subtarefas(tarefa_id):
    """(feitas, total) pra mostrar no card."""
    con = sqlite3.connect(DB)
    total, feitas = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(concluida), 0) FROM subtarefas WHERE tarefa_id = ?",
        (tarefa_id,),
    ).fetchone()
    con.close()
    return feitas, total


def buscar_tarefa(tid):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    t = con.execute("SELECT * FROM tarefas WHERE id = ?", (tid,)).fetchone()
    con.close()
    return t


def marcar_concluida(tid, valor):
    con = sqlite3.connect(DB)
    if valor:
        con.execute(
            "UPDATE tarefas SET concluida = 1, concluida_em = datetime('now','localtime') WHERE id = ?",
            (tid,),
        )
    else:
        con.execute(
            "UPDATE tarefas SET concluida = 0, concluida_em = NULL WHERE id = ?",
            (tid,),
        )
    con.commit()
    con.close()


def grupo_da_tarefa(t):
    """Classifica em Atrasada / Hoje / Próximas / Sem data pelo prazo."""
    if not t["prazo"]:
        return "Sem data"
    try:
        prazo = datetime.fromisoformat(t["prazo"])
    except ValueError:
        return "Sem data"
    hoje = date.today()
    if prazo.date() < hoje or (prazo.date() == hoje and prazo <= datetime.now()):
        return "Atrasada"
    if prazo.date() == hoje:
        return "Hoje"
    return "Próximas"


def parse_prazo(texto):
    """Aceita 'dd/mm/aaaa' ou 'dd/mm/aaaa hh:mm'. Retorna ISO ou None."""
    texto = texto.strip()
    if not texto:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).isoformat(sep=" ", timespec="minutes")
        except ValueError:
            pass
    return None


def formatar_prazo(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M").replace(" 00:00", "")
    except (ValueError, TypeError):
        return iso or ""


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
def main(page: ft.Page):
    init_db()
    page.title = "Tarefas"
    page.bgcolor = COR_FUNDO
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    lista_tarefas = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
    ultima_concluida = {"id": None}  # pro botão de desfazer
    filtro = {"lista": None, "modo": "pendentes"}  # lista None = Todas

    subtitulo_appbar = ft.Text("Todas", size=12)

    # --- Render ----------------------------------------------------------
    ORDEM_GRUPOS = ["Atrasada", "Hoje", "Próximas", "Sem data"]

    def render_tarefas():
        if filtro["modo"] == "concluidas":
            render_concluidas()
            return
        if filtro["modo"] == "listas":
            render_listas()
            return
        if filtro["modo"] == "busca":
            render_busca()
            return
        page.floating_action_button.visible = True
        subtitulo_appbar.value = filtro["lista"] or "Todas"
        lista_tarefas.controls.clear()
        linhas = listar_pendentes(filtro["lista"])

        if not linhas:
            lista_tarefas.controls.append(
                ft.Container(
                    ft.Text("Nada a fazer 🌴", color=COR_TEXTO_SUAVE, size=16),
                    alignment=ft.Alignment(0, 0),
                    padding=40,
                )
            )
        else:
            grupos = {g: [] for g in ORDEM_GRUPOS}
            for t in linhas:
                grupos[grupo_da_tarefa(t)].append(t)

            for nome in ORDEM_GRUPOS:
                if not grupos[nome]:
                    continue
                cor_titulo = COR_ATRASADA if nome == "Atrasada" else COR_TEXTO_SUAVE
                lista_tarefas.controls.append(
                    ft.Container(
                        ft.Text(nome, color=cor_titulo, size=13, weight=ft.FontWeight.BOLD),
                        padding=ft.Padding(left=4, top=8, right=0, bottom=0),
                    )
                )
                for t in grupos[nome]:
                    lista_tarefas.controls.append(criar_card(t, atrasada=(nome == "Atrasada")))
        page.update()

    def criar_card(t, atrasada=False):
        cor_prio = COR_PRIORIDADE.get(t["prioridade"], "#475569")

        def on_check(e, tid=t["id"]):
            marcar_concluida(tid, e.control.value)
            if e.control.value:
                ultima_concluida["id"] = tid
                mostrar_desfazer(t["titulo"])
            render_tarefas()

        # Etiqueta da lista no canto, como no app de referência
        etiqueta = ft.Container(
            ft.Text(t["categoria"], size=11, color=COR_TEXTO_SUAVE),
            alignment=ft.Alignment(1, -1),
        )

        linha_prazo = None
        if t["prazo"]:
            linha_prazo = ft.Text(
                formatar_prazo(t["prazo"]),
                size=12,
                color=COR_ATRASADA if atrasada else COR_TEXTO_SUAVE,
            )

        corpo = [ft.Text(t["titulo"], color="white", size=15)]
        if linha_prazo:
            corpo.append(linha_prazo)
        feitas, total_subs = progresso_subtarefas(t["id"])
        if total_subs:
            corpo.append(
                ft.Text(f"Subtarefas: {feitas}/{total_subs}", size=12, color=COR_TEXTO_SUAVE)
            )

        def on_tap(e, tid=t["id"]):
            abrir_editar(tid)

        return ft.Container(
            content=ft.Column(
                [
                    etiqueta,
                    ft.Row(
                        [
                            ft.Checkbox(value=False, on_change=on_check, fill_color=cor_prio),
                            ft.Column(corpo, spacing=2, expand=True),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                ],
                spacing=0,
            ),
            bgcolor=COR_CARD,
            border_radius=10,
            padding=ft.Padding(left=12, top=4, right=12, bottom=10),
            border=ft.Border(left=ft.BorderSide(width=4, color=cor_prio)),
            on_click=on_tap,
            ink=True,
        )

    # --- Busca ---------------------------------------------------------------
    resultados_busca = ft.Column(spacing=8)
    campo_busca = ft.TextField(
        label="Buscar tarefas",
        prefix_icon=ft.Icons.SEARCH,
        border_color=COR_AZUL,
        autofocus=True,
    )

    def atualizar_resultados_busca(e=None):
        resultados_busca.controls.clear()
        termo = (campo_busca.value or "").strip()
        if termo:
            linhas = buscar_tarefas(termo)
            pendentes = [t for t in linhas if not t["concluida"]]
            concluidas = [t for t in linhas if t["concluida"]]
            if not linhas:
                resultados_busca.controls.append(
                    ft.Container(
                        ft.Text("Nada encontrado", color=COR_TEXTO_SUAVE, size=14),
                        alignment=ft.Alignment(0, 0),
                        padding=20,
                    )
                )
            if pendentes:
                resultados_busca.controls.append(
                    ft.Text("Pendentes", color=COR_TEXTO_SUAVE, size=13, weight=ft.FontWeight.BOLD)
                )
                for t in pendentes:
                    resultados_busca.controls.append(
                        criar_card(t, atrasada=(grupo_da_tarefa(t) == "Atrasada"))
                    )
            if concluidas:
                resultados_busca.controls.append(
                    ft.Text("Concluídas", color=COR_TEXTO_SUAVE, size=13, weight=ft.FontWeight.BOLD)
                )
                for t in concluidas:
                    resultados_busca.controls.append(criar_card_concluida(t))
        page.update()

    campo_busca.on_change = atualizar_resultados_busca

    def render_busca():
        page.floating_action_button.visible = False
        subtitulo_appbar.value = "Busca"
        lista_tarefas.controls.clear()
        lista_tarefas.controls.append(campo_busca)
        lista_tarefas.controls.append(resultados_busca)
        atualizar_resultados_busca()

    def alternar_busca(e):
        if filtro["modo"] == "busca":
            filtro["modo"] = "pendentes"
        else:
            filtro["modo"] = "busca"
            campo_busca.value = ""
        render_tarefas()

    # --- Tela de gerenciamento de listas ------------------------------------
    def render_listas():
        page.floating_action_button.visible = True
        subtitulo_appbar.value = "Listas de tarefas"
        lista_tarefas.controls.clear()
        totais = contar_por_lista_total()
        for l in listar_listas():
            n = totais.get(l["nome"], 0)
            legenda = f"Tarefas: {n}" if n else "Sem tarefas"
            if l["oculta"]:
                legenda += '  ·  oculta do "Todas"'

            acoes = []
            if l["nome"] != "Padrão":
                acoes = [
                    ft.IconButton(
                        icon=ft.Icons.EDIT_OUTLINED,
                        icon_color=COR_TEXTO_SUAVE,
                        tooltip="Editar",
                        on_click=lambda e, lid=l["id"], nome=l["nome"], oc=l["oculta"]: abrir_editar_lista(lid, nome, oc),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=COR_ATRASADA,
                        tooltip="Excluir",
                        on_click=lambda e, lid=l["id"], nome=l["nome"]: confirmar_exclusao_lista(lid, nome),
                    ),
                ]

            lista_tarefas.controls.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(l["nome"], color="white", size=16),
                                    ft.Text(legenda, color=COR_TEXTO_SUAVE, size=12),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            *acoes,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=COR_CARD,
                    border_radius=10,
                    padding=ft.Padding(left=16, top=10, right=8, bottom=10),
                )
            )
        page.update()

    campo_edit_nome_lista = ft.TextField(label="Nome da lista", autofocus=True)
    switch_edit_oculta = ft.Switch(label='Ocultar do "Todas"', value=False)

    def abrir_editar_lista(lid, nome, oculta):
        campo_edit_nome_lista.value = nome
        switch_edit_oculta.value = bool(oculta)
        dialogo_editar_lista.data = lid
        page.show_dialog(dialogo_editar_lista)

    def salvar_edicao_lista(e):
        nome = (campo_edit_nome_lista.value or "").strip()
        if not nome:
            return
        renomear_lista(dialogo_editar_lista.data, nome, switch_edit_oculta.value)
        if filtro["lista"] is not None:
            filtro["lista"] = None  # o nome pode ter mudado; volta pro Todas
        atualizar_opcoes_listas()
        page.pop_dialog()
        render_tarefas()

    dialogo_editar_lista = ft.AlertDialog(
        title=ft.Text("Editar lista"),
        content=ft.Column([campo_edit_nome_lista, switch_edit_oculta], tight=True, spacing=14),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
            ft.FilledButton("Salvar", on_click=salvar_edicao_lista),
        ],
        bgcolor=COR_FUNDO,
    )

    def confirmar_exclusao_lista(lid, nome):
        dialogo_excluir_lista.data = lid
        dialogo_excluir_lista.content = ft.Text(
            f'As tarefas de "{nome}" vão pra lista Padrão. Nada se perde.'
        )
        page.show_dialog(dialogo_excluir_lista)

    def excluir_lista_confirmada(e):
        excluir_lista(dialogo_excluir_lista.data)
        filtro["lista"] = None
        atualizar_opcoes_listas()
        page.pop_dialog()
        render_tarefas()

    dialogo_excluir_lista = ft.AlertDialog(
        title=ft.Text("Excluir lista?"),
        content=ft.Text(""),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
            ft.FilledButton("Excluir", on_click=excluir_lista_confirmada),
        ],
        bgcolor=COR_FUNDO,
    )

    # --- Tela de Concluídas ------------------------------------------------
    def render_concluidas():
        page.floating_action_button.visible = False
        subtitulo_appbar.value = "Concluídas"
        lista_tarefas.controls.clear()
        linhas = listar_concluidas()
        if not linhas:
            lista_tarefas.controls.append(
                ft.Container(
                    ft.Text("Nenhuma tarefa concluída ainda", color=COR_TEXTO_SUAVE, size=16),
                    alignment=ft.Alignment(0, 0),
                    padding=40,
                )
            )
        for t in linhas:
            lista_tarefas.controls.append(criar_card_concluida(t))
        page.update()

    def criar_card_concluida(t):
        def on_uncheck(e, tid=t["id"]):
            if not e.control.value:
                marcar_concluida(tid, False)  # volta pra pendentes
                render_tarefas()

        def editar_descricao(e, tid=t["id"], atual=t["descricao_conclusao"]):
            campo_descricao.value = atual or ""
            dialogo_descricao.data = tid
            page.show_dialog(dialogo_descricao)

        corpo = [
            ft.Text(t["titulo"], color="white", size=15),
            ft.Text(
                f"Concluída em {formatar_prazo(t['concluida_em'])}",
                size=12,
                color=COR_TEXTO_SUAVE,
            ),
        ]
        if t["descricao_conclusao"]:
            corpo.append(
                ft.Text(t["descricao_conclusao"], size=13, color="#cbd5e1", italic=True)
            )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        ft.Text(t["categoria"], size=11, color=COR_TEXTO_SUAVE),
                        alignment=ft.Alignment(1, -1),
                    ),
                    ft.Row(
                        [
                            ft.Checkbox(value=True, on_change=on_uncheck, fill_color=COR_AZUL),
                            ft.Column(corpo, spacing=2, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.EDIT_NOTE,
                                icon_color=COR_TEXTO_SUAVE,
                                tooltip="Como foi concluída?",
                                on_click=editar_descricao,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color=COR_ATRASADA,
                                tooltip="Excluir",
                                on_click=lambda e, tid=t["id"]: confirmar_exclusao(tid),
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                ],
                spacing=0,
            ),
            bgcolor=COR_CARD,
            border_radius=10,
            padding=ft.Padding(left=12, top=4, right=12, bottom=10),
        )

    campo_descricao = ft.TextField(
        label="Como a tarefa foi concluída?",
        multiline=True,
        min_lines=2,
        autofocus=True,
    )

    def salvar_descricao(e):
        salvar_descricao_conclusao(dialogo_descricao.data, campo_descricao.value or "")
        page.pop_dialog()
        render_tarefas()

    dialogo_descricao = ft.AlertDialog(
        title=ft.Text("Descrição da conclusão"),
        content=campo_descricao,
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
            ft.FilledButton("Salvar", on_click=salvar_descricao),
        ],
        bgcolor=COR_FUNDO,
    )

    def mostrar_desfazer(titulo):
        def desfazer(e):
            if ultima_concluida["id"] is not None:
                marcar_concluida(ultima_concluida["id"], False)
                ultima_concluida["id"] = None
                render_tarefas()

        page.show_dialog(
            ft.SnackBar(
                content=ft.Text(f'Concluída: "{titulo}"'),
                action="Desfazer",
                on_action=desfazer,
            )
        )

    # --- Gaveta lateral (listas + contadores) -----------------------------
    def construir_drawer():
        cont = contagens()

        def badge(n):
            if not n:
                return None
            return ft.Container(
                ft.Text(str(n), size=11, color="white"),
                bgcolor=COR_AZUL,
                border_radius=20,
                padding=ft.Padding(left=8, top=2, right=8, bottom=2),
            )

        async def ir_para(e, nome=None):
            filtro["lista"] = nome
            filtro["modo"] = "pendentes"
            await page.close_drawer()
            render_tarefas()

        async def ir_concluidas(e):
            filtro["modo"] = "concluidas"
            await page.close_drawer()
            render_tarefas()

        async def ir_listas(e):
            filtro["modo"] = "listas"
            await page.close_drawer()
            render_tarefas()

        itens = [
            ft.Container(
                ft.Text("LISTAS DE TAREFAS", size=12, color=COR_TEXTO_SUAVE),
                padding=ft.Padding(left=16, top=16, right=16, bottom=4),
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.HOME_OUTLINED),
                title=ft.Text("Todas"),
                trailing=badge(cont["todas"]),
                on_click=ir_para,
            ),
        ]
        for l in listar_listas():
            icone = ft.Icons.VISIBILITY_OFF_OUTLINED if l["oculta"] else ft.Icons.LIST_ALT_OUTLINED

            async def ir(e, nome=l["nome"]):
                await ir_para(e, nome)

            itens.append(
                ft.ListTile(
                    leading=ft.Icon(icone),
                    title=ft.Text(l["nome"]),
                    trailing=badge(cont["por_lista"].get(l["nome"], 0)),
                    on_click=ir,
                )
            )
        itens += [
            ft.Divider(),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.CHECKLIST),
                title=ft.Text("Concluídas"),
                trailing=badge(cont["concluidas"]),
                on_click=ir_concluidas,
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.ADD),
                title=ft.Text("Nova lista"),
                on_click=abrir_nova_lista,
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.EDIT_OUTLINED),
                title=ft.Text("Gerenciar listas"),
                on_click=ir_listas,
            ),
        ]
        return ft.NavigationDrawer(controls=itens, bgcolor=COR_FUNDO)

    async def abrir_gaveta(e):
        page.drawer = construir_drawer()  # reconstrói pra atualizar contadores
        await page.show_drawer()

    # --- Diálogo de nova lista --------------------------------------------
    campo_nome_lista = ft.TextField(label="Nome da lista", autofocus=True)
    switch_oculta = ft.Switch(label='Ocultar do "Todas"', value=False)

    async def abrir_nova_lista(e):
        campo_nome_lista.value = ""
        switch_oculta.value = False
        await page.close_drawer()
        page.show_dialog(dialogo_nova_lista)

    def salvar_lista(e):
        nome = (campo_nome_lista.value or "").strip()
        if not nome:
            return
        criar_lista(nome, switch_oculta.value)
        atualizar_opcoes_listas()
        page.pop_dialog()
        render_tarefas()

    dialogo_nova_lista = ft.AlertDialog(
        title=ft.Text("Nova lista"),
        content=ft.Column([campo_nome_lista, switch_oculta], tight=True, spacing=14),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
            ft.FilledButton("Salvar", on_click=salvar_lista),
        ],
        bgcolor=COR_FUNDO,
    )

    # --- Edição e exclusão de tarefa ---------------------------------------
    NOMES_PRIORIDADE = {v: k for k, v in PRIORIDADES.items()}

    campo_edit_titulo = ft.TextField(label="O que há para fazer?", border_color=COR_AZUL)
    campo_edit_prazo = ft.TextField(
        label="Notificação / prazo (opcional)",
        hint_text="dd/mm/aaaa ou dd/mm/aaaa hh:mm",
        border_color=COR_AZUL,
    )
    dropdown_edit_lista = ft.Dropdown(label="Lista de tarefas", options=[], border_color=COR_AZUL)
    dropdown_edit_prioridade = ft.Dropdown(
        label="Prioridade",
        options=[ft.dropdown.Option(p) for p in PRIORIDADES],
        border_color=COR_AZUL,
    )

    # Subtarefas dentro da folha de edição
    titulo_subtarefas = ft.Text("Subtarefas", size=14, weight=ft.FontWeight.BOLD, color=COR_TEXTO_SUAVE)
    subtarefas_coluna = ft.Column(spacing=0)
    campo_nova_subtarefa = ft.TextField(label="Nova subtarefa", border_color=COR_AZUL, expand=True)

    def montar_subtarefas():
        tid = folha_editar.data
        subs = listar_subtarefas(tid)
        titulo_subtarefas.value = f"Subtarefas ({len(subs)}/{MAX_SUBTAREFAS})"
        linha_add_subtarefa.visible = len(subs) < MAX_SUBTAREFAS

        def linha(s):
            def on_check(e, sid=s["id"]):
                marcar_subtarefa(sid, e.control.value)
                montar_subtarefas()
                page.update()

            def on_del(e, sid=s["id"]):
                excluir_subtarefa(sid)
                montar_subtarefas()
                page.update()

            estilo = (
                ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH, color=COR_TEXTO_SUAVE)
                if s["concluida"]
                else None
            )
            return ft.Row(
                [
                    ft.Checkbox(value=bool(s["concluida"]), on_change=on_check),
                    ft.Text(s["titulo"], size=14, expand=True, style=estilo),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE, icon_size=16, icon_color=COR_TEXTO_SUAVE, on_click=on_del
                    ),
                ],
                spacing=4,
            )

        subtarefas_coluna.controls = [linha(s) for s in subs]

    def add_subtarefa(e):
        titulo = (campo_nova_subtarefa.value or "").strip()
        if not titulo:
            return
        if not adicionar_subtarefa(folha_editar.data, titulo):
            page.show_dialog(
                ft.SnackBar(content=ft.Text(f"Limite de {MAX_SUBTAREFAS} subtarefas por tarefa"))
            )
            return
        campo_nova_subtarefa.value = ""
        montar_subtarefas()
        page.update()

    campo_nova_subtarefa.on_submit = add_subtarefa
    linha_add_subtarefa = ft.Row(
        [
            campo_nova_subtarefa,
            ft.IconButton(icon=ft.Icons.ADD_CIRCLE_OUTLINE, icon_color=COR_AZUL, on_click=add_subtarefa),
        ],
        spacing=4,
    )

    def abrir_editar(tid):
        t = buscar_tarefa(tid)
        if t is None:
            return
        campo_edit_titulo.value = t["titulo"]
        campo_edit_prazo.value = formatar_prazo(t["prazo"]) if t["prazo"] else ""
        dropdown_edit_lista.options = [ft.dropdown.Option(l["nome"]) for l in listar_listas()]
        dropdown_edit_lista.value = t["categoria"]
        dropdown_edit_prioridade.value = NOMES_PRIORIDADE.get(t["prioridade"], "Média")
        campo_nova_subtarefa.value = ""
        folha_editar.data = tid
        montar_subtarefas()
        page.show_dialog(folha_editar)

    def salvar_edicao(e):
        titulo = (campo_edit_titulo.value or "").strip()
        if not titulo:
            return
        atualizar_tarefa(
            folha_editar.data,
            titulo,
            dropdown_edit_lista.value,
            PRIORIDADES[dropdown_edit_prioridade.value],
            parse_prazo(campo_edit_prazo.value or ""),
        )
        page.pop_dialog()
        render_tarefas()

    def excluir_da_edicao(e):
        page.pop_dialog()
        confirmar_exclusao(folha_editar.data)

    folha_editar = ft.BottomSheet(
        ft.Container(
            ft.Column(
                [
                    ft.Text("Editar tarefa", size=18, weight=ft.FontWeight.BOLD),
                    campo_edit_titulo,
                    campo_edit_prazo,
                    dropdown_edit_lista,
                    dropdown_edit_prioridade,
                    titulo_subtarefas,
                    subtarefas_coluna,
                    linha_add_subtarefa,
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Excluir", icon=ft.Icons.DELETE_OUTLINE, on_click=excluir_da_edicao
                            ),
                            ft.FilledButton("Salvar", icon=ft.Icons.CHECK, on_click=salvar_edicao),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                tight=True,
                spacing=14,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=20,
            bgcolor=COR_FUNDO,
        ),
    )

    def confirmar_exclusao(tid):
        dialogo_excluir.data = tid
        page.show_dialog(dialogo_excluir)

    def excluir_confirmado(e):
        excluir_tarefa(dialogo_excluir.data)
        page.pop_dialog()
        render_tarefas()

    dialogo_excluir = ft.AlertDialog(
        title=ft.Text("Excluir tarefa?"),
        content=ft.Text("Essa ação não pode ser desfeita."),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
            ft.FilledButton("Excluir", on_click=excluir_confirmado),
        ],
        bgcolor=COR_FUNDO,
    )

    # --- Tela de adicionar tarefa (bottom sheet) ---------------------------
    campo_titulo = ft.TextField(
        label="O que há para fazer?",
        autofocus=True,
        border_color=COR_AZUL,
    )
    switch_lote = ft.Switch(label="Adicionar em lote", value=False)

    def alternar_lote(e):
        campo_titulo.multiline = switch_lote.value
        campo_titulo.min_lines = 3 if switch_lote.value else 1
        campo_titulo.hint_text = "Uma tarefa por linha" if switch_lote.value else None
        page.update()

    switch_lote.on_change = alternar_lote

    campo_prazo = ft.TextField(
        label="Notificação / prazo (opcional)",
        hint_text="dd/mm/aaaa ou dd/mm/aaaa hh:mm",
        border_color=COR_AZUL,
    )
    dropdown_lista = ft.Dropdown(
        label="Lista de tarefas",
        value="Padrão",
        options=[],
        border_color=COR_AZUL,
    )
    dropdown_prioridade = ft.Dropdown(
        label="Prioridade",
        value="Média",
        options=[ft.dropdown.Option(p) for p in PRIORIDADES],
        border_color=COR_AZUL,
    )

    def atualizar_opcoes_listas():
        dropdown_lista.options = [ft.dropdown.Option(l["nome"]) for l in listar_listas()]

    def salvar(e):
        texto = (campo_titulo.value or "").strip()
        if not texto:
            return
        prazo = parse_prazo(campo_prazo.value or "")
        prioridade = PRIORIDADES[dropdown_prioridade.value]
        # Em lote: uma tarefa por linha; senão, uma só
        titulos = [l.strip() for l in texto.split("\n") if l.strip()] if switch_lote.value else [texto]
        for titulo in titulos:
            adicionar_tarefa(titulo, dropdown_lista.value, prioridade, prazo)
        campo_titulo.value = ""
        campo_prazo.value = ""
        page.pop_dialog()
        render_tarefas()

    folha_adicionar = ft.BottomSheet(
        ft.Container(
            ft.Column(
                [
                    ft.Text("Nova tarefa", size=18, weight=ft.FontWeight.BOLD),
                    campo_titulo,
                    switch_lote,
                    campo_prazo,
                    dropdown_lista,
                    dropdown_prioridade,
                    ft.FilledButton("Salvar", icon=ft.Icons.CHECK, on_click=salvar),
                ],
                tight=True,
                spacing=14,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=20,
            bgcolor=COR_FUNDO,
        ),
    )

    def abrir_adicionar(e):
        # Na tela de gerenciamento, o "+" cria uma lista; nas demais, uma tarefa
        if filtro["modo"] == "listas":
            campo_nome_lista.value = ""
            switch_oculta.value = False
            page.show_dialog(dialogo_nova_lista)
            return
        atualizar_opcoes_listas()
        # Pré-seleciona a lista do filtro atual, como no app de referência
        if filtro["lista"]:
            dropdown_lista.value = filtro["lista"]
        page.show_dialog(folha_adicionar)

    # --- Estrutura da página ----------------------------------------------
    page.appbar = ft.AppBar(
        leading=ft.IconButton(icon=ft.Icons.MENU, icon_color="white", on_click=abrir_gaveta),
        title=ft.Column(
            [ft.Text("Tarefas", size=18, weight=ft.FontWeight.BOLD), subtitulo_appbar],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        center_title=True,
        bgcolor=COR_AZUL,
        color="white",
        actions=[
            ft.IconButton(icon=ft.Icons.SEARCH, icon_color="white", on_click=alternar_busca)
        ],
    )
    page.floating_action_button = ft.FloatingActionButton(
        icon=ft.Icons.ADD, bgcolor=COR_AZUL, on_click=abrir_adicionar
    )
    page.add(ft.Container(lista_tarefas, padding=12, expand=True))

    atualizar_opcoes_listas()
    render_tarefas()


ft.run(main)
