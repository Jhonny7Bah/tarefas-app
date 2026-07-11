"""
App de Tarefas — em Flet (compatível com Flet 0.85)
---------------------------------------------------
Baseado no documento "Ideia de App Tarefa":
- Tarefas agrupadas por situação: Atrasada / Hoje / Próximas / Sem data
- Prioridade (alta/média/baixa) ordena sozinha; prazo desempata
- Registro de criação e conclusão de cada tarefa
- Adicionar em lote (uma tarefa por linha)
- Desfazer a última conclusão
- Persistência local com SQLite (roda offline)

Rodar no desktop:   flet run main.py
Rodar no navegador: flet run --web main.py
Empacotar Android:  flet build apk
"""

from datetime import datetime, date

import sqlite3
import flet as ft

DB = "tarefas.db"

LISTAS = ["Padrão", "Financeiro", "Pessoal", "Compras", "Trabalho", "Tech"]

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
    # Migração: colunas novas em bancos criados pela versão anterior
    existentes = {r[1] for r in con.execute("PRAGMA table_info(tarefas)")}
    if "prioridade" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN prioridade INTEGER NOT NULL DEFAULT 1")
    if "prazo" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN prazo TEXT")
    if "concluida_em" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN concluida_em TEXT")
    con.commit()
    con.close()


def listar_pendentes():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    # Prioridade manda; prazo desempata (sem prazo vai pro fim do empate)
    linhas = con.execute(
        """
        SELECT * FROM tarefas
        WHERE concluida = 0
        ORDER BY prioridade DESC, (prazo IS NULL), prazo ASC, id DESC
        """
    ).fetchall()
    con.close()
    return linhas


def adicionar_tarefa(titulo, categoria, prioridade=1, prazo=None):
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO tarefas (titulo, categoria, prioridade, prazo) VALUES (?, ?, ?, ?)",
        (titulo, categoria, prioridade, prazo),
    )
    con.commit()
    con.close()


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

    # --- Render ----------------------------------------------------------
    ORDEM_GRUPOS = ["Atrasada", "Hoje", "Próximas", "Sem data"]

    def render_tarefas():
        lista_tarefas.controls.clear()
        linhas = listar_pendentes()

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

    # --- Tela de adicionar (bottom sheet) --------------------------------
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
        options=[ft.dropdown.Option(c) for c in LISTAS],
        border_color=COR_AZUL,
    )
    dropdown_prioridade = ft.Dropdown(
        label="Prioridade",
        value="Média",
        options=[ft.dropdown.Option(p) for p in PRIORIDADES],
        border_color=COR_AZUL,
    )

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
        page.show_dialog(folha_adicionar)

    # --- Estrutura da página ----------------------------------------------
    page.appbar = ft.AppBar(
        title=ft.Column(
            [ft.Text("Tarefas", size=18, weight=ft.FontWeight.BOLD), ft.Text("Todas", size=12)],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        center_title=True,
        bgcolor=COR_AZUL,
        color="white",
    )
    page.floating_action_button = ft.FloatingActionButton(
        icon=ft.Icons.ADD, bgcolor=COR_AZUL, on_click=abrir_adicionar
    )
    page.add(ft.Container(lista_tarefas, padding=12, expand=True))

    render_tarefas()


ft.run(main)
