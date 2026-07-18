"""App de Tarefas em Flet (compatível com Flet 0.85).

Este módulo contém só a interface; a camada de dados vive em ``db.py``,
a checagem de atualização em ``atualizacao.py`` e o tema/constantes em
``constantes.py``.

Rodar no desktop:   flet run main.py
Rodar no navegador: flet run --web main.py
Empacotar Android:  flet build apk --split-per-abi
"""

import asyncio
import os
from datetime import datetime

import flet as ft

import db
from atualizacao import buscar_ultima_release, parse_versao
from constantes import (
    COR_ACENTO,
    COR_ATRASADA,
    COR_BOLINHA_PRIORIDADE,
    COR_CARD,
    COR_FUNDO,
    COR_TEXTO_SUAVE,
    JANELA_ALTURA,
    JANELA_ALTURA_MIN,
    JANELA_LARGURA,
    JANELA_LARGURA_MIN,
    LARGURA_CONTEUDO_DESKTOP,
    MAX_SUBTAREFAS,
    NOMES_PRIORIDADE,
    NOMES_REPETICAO,
    PRIORIDADES,
    REPETICOES,
)

ETIQUETA_BRANCA = ft.TextStyle(color="white")

VERSAO = "1.6.6"  # manter em sincronia com [project] version no pyproject.toml

ORDEM_GRUPOS = ["Atrasada", "Hoje", "Próximas", "Sem data"]


def main(page: ft.Page):
    db.init_db()
    page.title = "Tarefas"
    page.bgcolor = COR_FUNDO
    page.theme_mode = ft.ThemeMode.DARK
    # Semente verde: diálogos, snackbars e afins seguem o tema do app.
    # A barra de status do Android ganha uma faixa própria num verde mais
    # escuro (em vez do app desenhar embaixo do relógio/bateria), e a barra
    # de navegação inferior segue o fundo do app
    page.theme = ft.Theme(
        color_scheme_seed=COR_ACENTO,
        snackbar_theme=ft.SnackBarTheme(action_text_color="#34d399"),
        system_overlay_style=ft.SystemOverlayStyle(
            status_bar_color="#059669",
            status_bar_icon_brightness=ft.Brightness.LIGHT,
            system_navigation_bar_color=COR_FUNDO,
            system_navigation_bar_icon_brightness=ft.Brightness.LIGHT,
        ),
    )
    page.padding = 0

    # No computador o app mantém a cara de celular: janela em proporção de
    # celular e conteúdo numa coluna central de largura limitada
    eh_desktop = page.platform in (
        ft.PagePlatform.LINUX,
        ft.PagePlatform.MACOS,
        ft.PagePlatform.WINDOWS,
    )
    if eh_desktop:
        page.window.width = JANELA_LARGURA
        page.window.height = JANELA_ALTURA
        page.window.min_width = JANELA_LARGURA_MIN
        page.window.min_height = JANELA_ALTURA_MIN

    # A rolagem fica na vista externa; o recuo à direita impede a barra de
    # rolagem de cobrir a borda dos cards
    lista_tarefas = ft.Column(spacing=8)
    vista_lista = ft.Column(
        [
            ft.Container(
                lista_tarefas,
                padding=ft.Padding(left=0, top=0, right=14, bottom=8),
            )
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    # Troca animada entre a lista e a tela de nova tarefa (nada de corte seco)
    area_conteudo = ft.AnimatedSwitcher(
        content=vista_lista,
        transition=ft.AnimatedSwitcherTransition.FADE,
        duration=300,
        reverse_duration=300,
        switch_in_curve=ft.AnimationCurve.EASE_OUT,
        switch_out_curve=ft.AnimationCurve.EASE_IN,
        expand=True,
    )
    # pro botão de desfazer (id da tarefa e da ocorrência criada pelo repetir)
    ultima_concluida: dict[str, int | None] = {"id": None, "clone": None}
    filtro = {"lista": None, "modo": "pendentes"}  # lista None = Todas
    fab = ft.FloatingActionButton(icon=ft.Icons.ADD, bgcolor=COR_ACENTO)

    subtitulo_appbar = ft.Text("Todas", size=12)
    # Botões da barra; os handlers são ligados no fim do main()
    botao_menu = ft.IconButton(icon=ft.Icons.MENU, icon_color="white")
    botao_voltar = ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color="white")
    botao_busca = ft.IconButton(icon=ft.Icons.SEARCH, icon_color="white")
    appbar = ft.AppBar(
        leading=botao_menu,
        title=ft.Column(
            [ft.Text("Tarefas", size=18, weight=ft.FontWeight.BOLD), subtitulo_appbar],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        ),
        center_title=False,
        bgcolor=COR_ACENTO,
        color="white",
        actions=[botao_busca],
    )

    # --- Render ----------------------------------------------------------
    # Aviso próprio (o SnackBar do Flet não anima o fechamento manual):
    # sobe suave, e após 4 segundos desliza pra baixo com fade
    aviso_texto = ft.Text("", color="white", size=14, expand=True)
    aviso_botao = ft.TextButton(
        "", visible=False, style=ft.ButtonStyle(color="#34d399")
    )
    aviso_container = ft.Container(
        content=ft.Row([aviso_texto, aviso_botao], spacing=8),
        bgcolor=COR_CARD,
        border_radius=12,
        padding=ft.Padding(left=16, top=6, right=8, bottom=6),
        left=16,
        right=16,
        bottom=16,
        offset=ft.Offset(0, 2),
        animate_offset=250,
        opacity=0,
        animate_opacity=250,
    )
    aviso_estado = {"seq": 0}

    def esconder_aviso():
        aviso_container.offset = ft.Offset(0, 2)
        aviso_container.opacity = 0
        page.update()

    def avisar(texto, acao=None, on_action=None):
        """Aviso nas cores do app; some sozinho em 4 segundos."""
        aviso_estado["seq"] += 1
        seq = aviso_estado["seq"]
        # flutua acima do "+" quando ele está na tela, pra não cobrir
        aviso_container.bottom = 88 if fab.visible else 16
        aviso_texto.value = texto
        if acao and on_action:

            def clique(e, handler=on_action):
                esconder_aviso()
                handler(e)

            aviso_botao.content = acao
            aviso_botao.on_click = clique
            aviso_botao.visible = True
        else:
            aviso_botao.visible = False
        aviso_container.offset = ft.Offset(0, 0)
        aviso_container.opacity = 1
        page.update()

        async def sumir_depois():
            await asyncio.sleep(4)
            if aviso_estado["seq"] == seq:  # nenhum aviso mais novo por cima
                esconder_aviso()

        page.run_task(sumir_depois)

    # Botões com fonte branca (o tema deixaria verde) pros diálogos e formulários
    def botao_texto(rotulo, on_click):
        return ft.TextButton(
            rotulo, on_click=on_click, style=ft.ButtonStyle(color="white")
        )

    def botao_cheio(rotulo, on_click, icone=None):
        return ft.FilledButton(
            rotulo,
            icon=icone,
            on_click=on_click,
            style=ft.ButtonStyle(color="white", bgcolor=COR_ACENTO),
        )

    def render_tarefas():
        # barra e conteúdo padrão; o modo "nova" troca pelos dele em seguida
        appbar.leading = botao_menu
        botao_busca.visible = True
        area_conteudo.content = vista_lista
        if filtro["modo"] == "nova":
            render_nova_tarefa()
            return
        if filtro["modo"] == "editar":
            render_editar_tarefa()
            return
        if filtro["modo"] == "concluidas":
            render_concluidas()
            return
        if filtro["modo"] == "listas":
            render_listas()
            return
        if filtro["modo"] == "busca":
            render_busca()
            return
        fab.visible = True
        subtitulo_appbar.value = filtro["lista"] or "Todas"
        lista_tarefas.controls.clear()
        linhas = db.listar_pendentes(filtro["lista"])

        if not linhas:
            vazio: list[ft.Control] = [
                ft.Icon(ft.Icons.TASK_ALT, size=48, color=COR_ACENTO),
                ft.Text("Tudo em dia por aqui!", color=COR_TEXTO_SUAVE, size=16),
            ]
            lista_tarefas.controls.append(
                ft.Container(
                    ft.Column(
                        vazio,
                        spacing=12,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    alignment=ft.Alignment(0, 0),
                    padding=40,
                )
            )
        else:
            grupos = {g: [] for g in ORDEM_GRUPOS}
            for t in linhas:
                grupos[db.grupo_da_tarefa(t)].append(t)

            for nome in ORDEM_GRUPOS:
                if not grupos[nome]:
                    continue
                cor_titulo = COR_ATRASADA if nome == "Atrasada" else COR_TEXTO_SUAVE
                lista_tarefas.controls.append(
                    ft.Container(
                        ft.Text(
                            nome, color=cor_titulo, size=13, weight=ft.FontWeight.BOLD
                        ),
                        padding=ft.Padding(left=4, top=8, right=0, bottom=0),
                    )
                )
                for t in grupos[nome]:
                    lista_tarefas.controls.append(
                        criar_card(t, atrasada=(nome == "Atrasada"))
                    )
        page.update()

    def chip(texto, cor):
        """Pílula colorida com fonte sempre branca."""
        return ft.Container(
            ft.Text(texto, size=10, color="white"),
            bgcolor=cor,
            border_radius=999,
            padding=ft.Padding(left=9, top=2, right=9, bottom=2),
        )

    def chips_do_card(t):
        """Prioridade (vermelho/âmbar/verde) + listas (sempre cinza)."""
        chips: list[ft.Control] = [
            chip(
                NOMES_PRIORIDADE.get(t["prioridade"], "Média"),
                COR_BOLINHA_PRIORIDADE.get(t["prioridade"], "#d97706"),
            )
        ]
        chips += [chip(nome, "#4b5563") for nome in db.rotulo_listas(t).split(" · ")]
        return ft.Row(chips, spacing=6, wrap=True)

    def criar_card(t, atrasada=False):
        def on_check(e, tid=t["id"]):
            if e.control.value:
                clone = db.marcar_concluida(tid, True)
                ultima_concluida["id"] = tid
                ultima_concluida["clone"] = clone
                mostrar_desfazer(t["titulo"])
            else:
                db.marcar_concluida(tid, False)
            render_tarefas()

        linha_prazo = None
        if t["prazo"]:
            texto_prazo = db.formatar_prazo(t["prazo"])
            if t["repetir"]:
                texto_prazo += "  ·  🔁"
            linha_prazo = ft.Text(
                texto_prazo,
                size=12,
                color=COR_ATRASADA if atrasada else COR_TEXTO_SUAVE,
            )

        corpo: list[ft.Control] = [ft.Text(t["titulo"], color="white", size=15)]
        if linha_prazo:
            corpo.append(linha_prazo)
        feitas, total_subs = db.progresso_subtarefas(t["id"])
        if total_subs:
            corpo.append(
                ft.Text(
                    f"Subtarefas: {feitas}/{total_subs}",
                    size=12,
                    color=COR_TEXTO_SUAVE,
                )
            )
        corpo.append(chips_do_card(t))

        def on_tap(e, tid=t["id"]):
            abrir_editar(tid)

        linha_principal: list[ft.Control] = [
            ft.Checkbox(value=False, on_change=on_check),
            ft.Column(corpo, spacing=4, expand=True),
        ]
        return ft.Container(
            content=ft.Row(
                linha_principal,
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COR_CARD,
            border_radius=16,
            padding=ft.Padding(left=12, top=10, right=12, bottom=10),
            on_click=on_tap,
            ink=True,
        )

    # --- Busca -------------------------------------------------------------
    resultados_busca = ft.Column(spacing=8)
    campo_busca = ft.TextField(
        label="Buscar tarefas",
        label_style=ETIQUETA_BRANCA,
        prefix_icon=ft.Icons.SEARCH,
        border_color=COR_ACENTO,
        autofocus=True,
    )

    def atualizar_resultados_busca(e=None):
        resultados_busca.controls.clear()
        termo = (campo_busca.value or "").strip()
        if termo:
            linhas = db.buscar_tarefas(termo)
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
                    ft.Text(
                        "Pendentes",
                        color=COR_TEXTO_SUAVE,
                        size=13,
                        weight=ft.FontWeight.BOLD,
                    )
                )
                for t in pendentes:
                    resultados_busca.controls.append(
                        criar_card(t, atrasada=(db.grupo_da_tarefa(t) == "Atrasada"))
                    )
            if concluidas:
                resultados_busca.controls.append(
                    ft.Text(
                        "Concluídas",
                        color=COR_TEXTO_SUAVE,
                        size=13,
                        weight=ft.FontWeight.BOLD,
                    )
                )
                for t in concluidas:
                    resultados_busca.controls.append(criar_card_concluida(t))
        page.update()

    campo_busca.on_change = atualizar_resultados_busca

    def render_busca():
        fab.visible = False
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
        fab.visible = True
        subtitulo_appbar.value = "Gerenciar listas"
        lista_tarefas.controls.clear()
        totais = db.contar_por_lista_total()
        for lst in db.listar_listas():
            n = totais.get(lst["nome"], 0)
            legenda = f"Tarefas: {n}" if n else "Sem tarefas"
            if lst["oculta"]:
                legenda += '  ·  oculta do "Todas"'

            acoes = []
            if lst["nome"] != "Padrão":

                def ao_editar(e, lid=lst["id"], nome=lst["nome"], oc=lst["oculta"]):
                    abrir_editar_lista(lid, nome, oc)

                def ao_excluir(e, lid=lst["id"], nome=lst["nome"]):
                    confirmar_exclusao_lista(lid, nome)

                acoes = [
                    ft.IconButton(
                        icon=ft.Icons.EDIT_OUTLINED,
                        icon_color=COR_TEXTO_SUAVE,
                        tooltip="Editar",
                        on_click=ao_editar,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=COR_ATRASADA,
                        tooltip="Excluir",
                        on_click=ao_excluir,
                    ),
                ]

            lista_tarefas.controls.append(
                ft.Container(
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(lst["nome"], color="white", size=16),
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
                    border_radius=16,
                    padding=ft.Padding(left=16, top=10, right=8, bottom=10),
                )
            )
        page.update()

    campo_edit_nome_lista = ft.TextField(
        label="Nome da lista", label_style=ETIQUETA_BRANCA, autofocus=True
    )
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
        db.renomear_lista(dialogo_editar_lista.data, nome, switch_edit_oculta.value)
        if filtro["lista"] is not None:
            filtro["lista"] = None  # o nome pode ter mudado; volta pro Todas
        page.pop_dialog()
        render_tarefas()

    dialogo_editar_lista = ft.AlertDialog(
        title=ft.Text("Editar lista"),
        content=ft.Column(
            [campo_edit_nome_lista, switch_edit_oculta], tight=True, spacing=14
        ),
        actions=[
            botao_texto("Cancelar", lambda e: page.pop_dialog()),
            botao_cheio("Salvar", salvar_edicao_lista),
        ],
        bgcolor=COR_FUNDO,
    )

    def confirmar_exclusao_lista(lid, nome):
        dialogo_excluir_lista.data = lid
        dialogo_excluir_lista.content = ft.Text(
            f'Tarefa de "{nome}" que não estiver em outra lista vai pra Padrão.'
            " Nada se perde."
        )
        page.show_dialog(dialogo_excluir_lista)

    def excluir_lista_confirmada(e):
        db.excluir_lista(dialogo_excluir_lista.data)
        filtro["lista"] = None
        page.pop_dialog()
        render_tarefas()

    dialogo_excluir_lista = ft.AlertDialog(
        title=ft.Text("Excluir lista?"),
        content=ft.Text(""),
        actions=[
            botao_texto("Cancelar", lambda e: page.pop_dialog()),
            botao_cheio("Excluir", excluir_lista_confirmada),
        ],
        bgcolor=COR_FUNDO,
    )

    # --- Tela de Concluídas --------------------------------------------------
    def render_concluidas():
        fab.visible = False
        subtitulo_appbar.value = "Concluídas"
        lista_tarefas.controls.clear()
        linhas = db.listar_concluidas()
        if not linhas:
            lista_tarefas.controls.append(
                ft.Container(
                    ft.Text(
                        "Nada concluído por enquanto",
                        color=COR_TEXTO_SUAVE,
                        size=16,
                    ),
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
                db.marcar_concluida(tid, False)  # volta pra pendentes
                render_tarefas()

        def editar_descricao(e, tid=t["id"], atual=t["descricao_conclusao"]):
            campo_descricao.value = atual or ""
            dialogo_descricao.data = tid
            page.show_dialog(dialogo_descricao)

        def ao_excluir(e, tid=t["id"]):
            confirmar_exclusao(tid)

        corpo: list[ft.Control] = [
            ft.Text(t["titulo"], color="white", size=15),
            ft.Text(
                f"Concluída em {db.formatar_prazo(t['concluida_em'])}",
                size=12,
                color=COR_TEXTO_SUAVE,
            ),
        ]
        if t["descricao_conclusao"]:
            corpo.append(
                ft.Text(t["descricao_conclusao"], size=13, color="#d1d5db", italic=True)
            )
        corpo.append(chips_do_card(t))

        linha_principal: list[ft.Control] = [
            ft.Checkbox(value=True, on_change=on_uncheck),
            ft.Column(corpo, spacing=4, expand=True),
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
                on_click=ao_excluir,
            ),
        ]
        return ft.Container(
            content=ft.Row(
                linha_principal,
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COR_CARD,
            border_radius=16,
            padding=ft.Padding(left=12, top=10, right=12, bottom=10),
        )

    campo_descricao = ft.TextField(
        label="Como a tarefa foi concluída?",
        label_style=ETIQUETA_BRANCA,
        multiline=True,
        min_lines=2,
        autofocus=True,
    )

    def salvar_descricao(e):
        db.salvar_descricao_conclusao(
            dialogo_descricao.data, campo_descricao.value or ""
        )
        page.pop_dialog()
        render_tarefas()

    dialogo_descricao = ft.AlertDialog(
        title=ft.Text("Descrição da conclusão"),
        content=campo_descricao,
        actions=[
            botao_texto("Cancelar", lambda e: page.pop_dialog()),
            botao_cheio("Salvar", salvar_descricao),
        ],
        bgcolor=COR_FUNDO,
    )

    def mostrar_desfazer(titulo):
        def desfazer(e):
            if ultima_concluida["id"] is not None:
                # Se a conclusão agendou a próxima ocorrência, remove ela junto
                if ultima_concluida.get("clone"):
                    db.excluir_tarefa(ultima_concluida["clone"])
                db.marcar_concluida(ultima_concluida["id"], False)
                ultima_concluida["id"] = None
                ultima_concluida["clone"] = None
                render_tarefas()

        avisar(f'Concluída: "{titulo}"', acao="Desfazer", on_action=desfazer)

    # --- Gaveta lateral (listas + contadores) --------------------------------
    def construir_drawer():
        cont = db.contagens()

        def badge(n):
            if not n:
                return None
            return ft.Container(
                ft.Text(str(n), size=11, color="white"),
                bgcolor=COR_ACENTO,
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
                ft.Text("MINHAS LISTAS", size=12, color=COR_TEXTO_SUAVE),
                padding=ft.Padding(left=16, top=16, right=16, bottom=4),
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.HOME_OUTLINED),
                title=ft.Text("Todas"),
                trailing=badge(cont["todas"]),
                on_click=ir_para,
            ),
        ]
        for lst in db.listar_listas():
            if lst["oculta"]:
                icone = ft.Icons.VISIBILITY_OFF_OUTLINED
            else:
                icone = ft.Icons.LIST_ALT_OUTLINED

            async def ir(e, nome=lst["nome"]):
                await ir_para(e, nome)

            itens.append(
                ft.ListTile(
                    leading=ft.Icon(icone),
                    title=ft.Text(lst["nome"]),
                    trailing=badge(cont["por_lista"].get(lst["nome"], 0)),
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
            ft.ListTile(
                leading=ft.Icon(ft.Icons.UPLOAD_FILE),
                title=ft.Text("Exportar backup"),
                on_click=abrir_exportar,
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.SETTINGS_BACKUP_RESTORE),
                title=ft.Text("Restaurar backup"),
                on_click=abrir_restaurar,
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT),
                title=ft.Text("Verificar atualização"),
                on_click=verificar_atualizacao,
            ),
            ft.Divider(),
            ft.Container(
                ft.Column(
                    [
                        ft.Text(f"Tarefas v{VERSAO}", size=12, color=COR_TEXTO_SUAVE),
                        ft.Text(
                            spans=[
                                ft.TextSpan(
                                    "desenvolvido por ",
                                    style=ft.TextStyle(color=COR_TEXTO_SUAVE, size=10),
                                ),
                                ft.TextSpan(
                                    "jhon7bah",
                                    style=ft.TextStyle(
                                        color=COR_ACENTO,
                                        size=10,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                ),
                            ]
                        ),
                    ],
                    spacing=2,
                ),
                padding=ft.Padding(left=16, top=4, right=16, bottom=12),
            ),
        ]
        return ft.NavigationDrawer(
            controls=itens, bgcolor=COR_FUNDO, on_dismiss=ao_fechar_gaveta
        )

    # Rastreio manual: o NavigationDrawer não expõe se está aberto
    gaveta_aberta = {"valor": False}

    def ao_fechar_gaveta(e):
        gaveta_aberta["valor"] = False

    async def abrir_gaveta(e):
        page.drawer = construir_drawer()  # reconstrói pra atualizar contadores
        await page.show_drawer()
        gaveta_aberta["valor"] = True

    # --- Verificar atualização ------------------------------------------------
    async def verificar_atualizacao(e):
        await page.close_drawer()
        avisar("Verificando atualização…")
        try:
            rel = await asyncio.to_thread(buscar_ultima_release)
        except Exception:
            avisar("Não deu pra verificar. Sem internet?")
            return

        if parse_versao(rel["tag"]) > parse_versao(VERSAO):
            notas = rel["notas"].strip()
            if len(notas) > 500:
                notas = notas[:500] + "…"
            conteudo: list[ft.Control] = [
                ft.Text(f"Instalada: v{VERSAO}   →   Nova: {rel['tag']}")
            ]
            if notas:
                conteudo.append(ft.Text(notas, size=12, color=COR_TEXTO_SUAVE))

            url_download = rel["url_linux"] if eh_desktop else rel["url"]

            async def baixar(ev, url=url_download):
                page.pop_dialog()
                await page.launch_url(url)

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Atualização disponível!"),
                    content=ft.Column(
                        conteudo, tight=True, spacing=10, scroll=ft.ScrollMode.AUTO
                    ),
                    actions=[
                        botao_texto("Depois", lambda ev: page.pop_dialog()),
                        botao_cheio("Baixar", baixar, icone=ft.Icons.DOWNLOAD),
                    ],
                    bgcolor=COR_FUNDO,
                )
            )
        else:
            avisar(f"Você já está na última versão (v{VERSAO})")

    # --- Backup: exportar e restaurar ---------------------------------------
    seletor_arquivos = ft.FilePicker()

    async def abrir_exportar(e):
        await page.close_drawer()
        page.show_dialog(dialogo_exportar)

    async def exportar_backup(formato):
        page.pop_dialog()
        hoje = datetime.now().strftime("%Y-%m-%d")
        if formato == "json":
            conteudo = db.exportar_json().encode("utf-8")
            nome = f"tarefas-backup-{hoje}.json"
        else:
            conteudo = db.exportar_db_bytes()
            nome = f"tarefas-backup-{hoje}.db"
        caminho = await seletor_arquivos.save_file(
            dialog_title="Salvar backup", file_name=nome, src_bytes=conteudo
        )
        if caminho:
            avisar("Backup salvo!")

    async def exportar_como_json(e):
        await exportar_backup("json")

    async def exportar_como_db(e):
        await exportar_backup("db")

    dialogo_exportar = ft.AlertDialog(
        title=ft.Text("Exportar backup"),
        content=ft.Text(
            "JSON é legível e aguenta restaurar em versões futuras do app. "
            "O arquivo .db é a cópia fiel do banco."
        ),
        actions=[
            botao_texto("Cancelar", lambda e: page.pop_dialog()),
            botao_texto("Arquivo .db", exportar_como_db),
            botao_cheio("JSON", exportar_como_json),
        ],
        bgcolor=COR_FUNDO,
    )

    async def abrir_restaurar(e):
        await page.close_drawer()
        page.show_dialog(dialogo_restaurar)

    async def escolher_backup(e):
        page.pop_dialog()
        arquivos = await seletor_arquivos.pick_files(
            dialog_title="Escolher backup", allow_multiple=False
        )
        if not arquivos:
            return
        arquivo = arquivos[0]
        dados = arquivo.bytes
        if dados is None and arquivo.path:
            with open(arquivo.path, "rb") as origem:
                dados = origem.read()
        if not dados:
            avisar("Não consegui ler o arquivo escolhido.")
            return
        try:
            if dados.startswith(b"SQLite format 3\x00"):
                total = db.importar_db_bytes(dados)
            else:
                total = db.importar_json(dados.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as erro:
            avisar(str(erro))
            return
        filtro["lista"] = None
        filtro["modo"] = "pendentes"
        render_tarefas()
        avisar(f"Backup restaurado: {total} tarefas.")

    dialogo_restaurar = ft.AlertDialog(
        title=ft.Text("Restaurar backup?"),
        content=ft.Text(
            "As tarefas e listas atuais serão SUBSTITUÍDAS pelas do arquivo. "
            "Essa ação não pode ser desfeita."
        ),
        actions=[
            botao_texto("Cancelar", lambda e: page.pop_dialog()),
            botao_cheio("Escolher arquivo", escolher_backup),
        ],
        bgcolor=COR_FUNDO,
    )

    # --- Diálogo de nova lista --------------------------------------------
    campo_nome_lista = ft.TextField(
        label="Nome da lista", label_style=ETIQUETA_BRANCA, autofocus=True
    )
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
        db.criar_lista(nome, switch_oculta.value)
        page.pop_dialog()
        render_tarefas()

    dialogo_nova_lista = ft.AlertDialog(
        title=ft.Text("Nova lista"),
        content=ft.Column([campo_nome_lista, switch_oculta], tight=True, spacing=14),
        actions=[
            botao_texto("Cancelar", lambda e: page.pop_dialog()),
            botao_cheio("Salvar", salvar_lista),
        ],
        bgcolor=COR_FUNDO,
    )

    # --- Edição e exclusão de tarefa ---------------------------------------
    tarefa_em_edicao: dict[str, int | None] = {"id": None}
    campo_edit_titulo = ft.TextField(
        label="O que precisa ser feito?",
        label_style=ETIQUETA_BRANCA,
        border_color=COR_ACENTO,
    )
    campo_edit_prazo = ft.TextField(
        label="Prazo (opcional)",
        label_style=ETIQUETA_BRANCA,
        hint_text="dd/mm/aaaa ou dd/mm/aaaa hh:mm",
        border_color=COR_ACENTO,
    )
    selecao_listas_edit = ft.Column(spacing=0)
    dropdown_edit_prioridade = ft.Dropdown(
        expand=True,
        label="Prioridade",
        label_style=ETIQUETA_BRANCA,
        options=[ft.dropdown.Option(p) for p in PRIORIDADES],
        border_color=COR_ACENTO,
    )
    dropdown_edit_repetir = ft.Dropdown(
        expand=True,
        label="Repetir",
        label_style=ETIQUETA_BRANCA,
        options=[ft.dropdown.Option(r) for r in REPETICOES],
        border_color=COR_ACENTO,
    )

    texto_detalhes = ft.Text("", size=12, color=COR_TEXTO_SUAVE)

    def montar_selecao_listas(coluna, marcadas):
        coluna.controls = [
            ft.Checkbox(label=lst["nome"], value=(lst["nome"] in marcadas))
            for lst in db.listar_listas()
        ]

    def listas_marcadas(coluna):
        return [c.label for c in coluna.controls if c.value]

    # Subtarefas dentro da tela de edição
    titulo_subtarefas = ft.Text(
        "Subtarefas", size=14, weight=ft.FontWeight.BOLD, color=COR_TEXTO_SUAVE
    )
    subtarefas_coluna = ft.Column(spacing=0)
    campo_nova_subtarefa = ft.TextField(
        label="Nova subtarefa",
        label_style=ETIQUETA_BRANCA,
        border_color=COR_ACENTO,
        expand=True,
    )

    def montar_subtarefas():
        tid = tarefa_em_edicao["id"]
        subs = db.listar_subtarefas(tid)
        titulo_subtarefas.value = f"Subtarefas ({len(subs)}/{MAX_SUBTAREFAS})"
        linha_add_subtarefa.visible = len(subs) < MAX_SUBTAREFAS

        def linha(s):
            def on_check(e, sid=s["id"]):
                db.marcar_subtarefa(sid, e.control.value)
                montar_subtarefas()
                page.update()

            def on_del(e, sid=s["id"]):
                db.excluir_subtarefa(sid)
                montar_subtarefas()
                page.update()

            if s["concluida"]:
                estilo = ft.TextStyle(
                    decoration=ft.TextDecoration.LINE_THROUGH, color=COR_TEXTO_SUAVE
                )
            else:
                estilo = None
            datas = f"Criada {db.formatar_prazo(s['criada_em'])}"
            if s["concluida_em"]:
                datas += f"  ·  Concluída {db.formatar_prazo(s['concluida_em'])}"
            return ft.Row(
                [
                    ft.Checkbox(value=bool(s["concluida"]), on_change=on_check),
                    ft.Column(
                        [
                            ft.Text(s["titulo"], size=14, style=estilo),
                            ft.Text(datas, size=10, color=COR_TEXTO_SUAVE),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=16,
                        icon_color=COR_TEXTO_SUAVE,
                        on_click=on_del,
                    ),
                ],
                spacing=4,
            )

        subtarefas_coluna.controls = [linha(s) for s in subs]

    def add_subtarefa(e):
        titulo = (campo_nova_subtarefa.value or "").strip()
        if not titulo:
            return
        if not db.adicionar_subtarefa(tarefa_em_edicao["id"], titulo):
            avisar(f"Limite de {MAX_SUBTAREFAS} subtarefas por tarefa")
            return
        campo_nova_subtarefa.value = ""
        montar_subtarefas()
        page.update()

    campo_nova_subtarefa.on_submit = add_subtarefa
    linha_add_subtarefa = ft.Row(
        [
            campo_nova_subtarefa,
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                icon_color=COR_ACENTO,
                on_click=add_subtarefa,
            ),
        ],
        spacing=4,
    )

    async def voltar_para_lista(e=None):
        # Em duas fases: troca a tela, espera o fade, e SÓ ENTÃO reconstrói
        # a lista. Trocar e reconstruir no mesmo lote duplica cards na tela
        filtro["modo"] = filtro.get("retorno") or "pendentes"
        area_conteudo.content = vista_lista
        appbar.leading = botao_menu
        botao_busca.visible = True
        page.update()
        await asyncio.sleep(0.35)
        render_tarefas()

    def abrir_editar(tid):
        t = db.buscar_tarefa(tid)
        if t is None:
            return
        campo_edit_titulo.value = t["titulo"]
        campo_edit_prazo.value = db.formatar_prazo(t["prazo"]) if t["prazo"] else ""
        montar_selecao_listas(selecao_listas_edit, set(db.listas_da_tarefa(tid)))
        dropdown_edit_prioridade.value = NOMES_PRIORIDADE.get(t["prioridade"], "Média")
        dropdown_edit_repetir.value = NOMES_REPETICAO.get(t["repetir"], "Não repete")
        campo_nova_subtarefa.value = ""
        detalhes = f"Criada em {db.formatar_prazo(t['criada_em'])}"
        if t["concluida_em"]:
            detalhes += f"  ·  Concluída em {db.formatar_prazo(t['concluida_em'])}"
        texto_detalhes.value = detalhes
        tarefa_em_edicao["id"] = tid
        montar_subtarefas()
        # de onde veio (lista ou busca), pra devolver no lugar certo
        filtro["retorno"] = filtro["modo"]
        filtro["modo"] = "editar"
        render_tarefas()

    async def salvar_edicao(e):
        titulo = (campo_edit_titulo.value or "").strip()
        if not titulo:
            return
        db.atualizar_tarefa(
            tarefa_em_edicao["id"],
            titulo,
            listas_marcadas(selecao_listas_edit),
            PRIORIDADES[dropdown_edit_prioridade.value or "Média"],
            db.parse_prazo(campo_edit_prazo.value or ""),
            REPETICOES[dropdown_edit_repetir.value or "Não repete"],
        )
        await voltar_para_lista()

    def excluir_da_edicao(e):
        # O diálogo abre por cima da edição; Cancelar mantém o usuário nela
        confirmar_exclusao(tarefa_em_edicao["id"])

    # A edição também ocupa a página inteira, como a nova tarefa
    form_editar_tarefa = ft.Column(
        [
            ft.Container(height=16),
            texto_detalhes,
            campo_edit_titulo,
            campo_edit_prazo,
            ft.Text(
                "Listas", size=14, weight=ft.FontWeight.BOLD, color=COR_TEXTO_SUAVE
            ),
            selecao_listas_edit,
            ft.Row([dropdown_edit_prioridade]),
            ft.Row([dropdown_edit_repetir]),
            titulo_subtarefas,
            subtarefas_coluna,
            linha_add_subtarefa,
            ft.Row(
                [
                    ft.OutlinedButton(
                        "Excluir",
                        icon=ft.Icons.DELETE_OUTLINE,
                        on_click=excluir_da_edicao,
                        style=ft.ButtonStyle(color="white"),
                    ),
                    ft.FilledButton(
                        "Salvar",
                        icon=ft.Icons.CHECK,
                        on_click=salvar_edicao,
                        style=ft.ButtonStyle(color="white", bgcolor=COR_ACENTO),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        ],
        spacing=14,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    vista_editar_tarefa = ft.Column(
        [
            ft.Container(
                form_editar_tarefa,
                padding=ft.Padding(left=4, top=0, right=14, bottom=8),
            )
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    def render_editar_tarefa():
        fab.visible = False
        appbar.leading = botao_voltar
        botao_busca.visible = False
        subtitulo_appbar.value = "Editar tarefa"
        area_conteudo.content = vista_editar_tarefa
        page.update()

    def confirmar_exclusao(tid):
        dialogo_excluir.data = tid
        page.show_dialog(dialogo_excluir)

    async def excluir_confirmado(e):
        tid = dialogo_excluir.data
        # 1) fecha o diálogo e deixa o fechamento terminar (misturar o pop
        #    com a troca de tela no mesmo lote congela o lado gráfico)
        page.pop_dialog()
        page.update()
        if filtro["modo"] == "editar":
            await asyncio.sleep(0.2)
            # 2) joga o usuário na tela inicial ANTES de excluir de fato
            await voltar_para_lista()
        # 3) agora sim, exclui (guardando a foto pro desfazer) e atualiza
        foto = db.snapshot_tarefa(tid)
        db.excluir_tarefa(tid)
        render_tarefas()

        def desfazer_exclusao(ev, foto=foto):
            if foto is not None:
                db.restaurar_tarefa(foto)
                render_tarefas()

        if foto is not None:
            avisar(
                f'Excluída: "{foto["tarefa"]["titulo"]}"',
                acao="Desfazer",
                on_action=desfazer_exclusao,
            )

    dialogo_excluir = ft.AlertDialog(
        title=ft.Text("Excluir tarefa?"),
        content=ft.Text("Essa ação não pode ser desfeita."),
        actions=[
            botao_texto("Cancelar", lambda e: page.pop_dialog()),
            botao_cheio("Excluir", excluir_confirmado),
        ],
        bgcolor=COR_FUNDO,
    )

    # --- Tela de adicionar tarefa (página inteira) --------------------------
    # Sem autofocus: o teclado só sobe quando a pessoa tocar no campo
    campo_titulo = ft.TextField(
        label="O que precisa ser feito?",
        label_style=ETIQUETA_BRANCA,
        border_color=COR_ACENTO,
    )
    switch_lote = ft.Switch(label="Criar várias de uma vez", value=False)

    def alternar_lote(e):
        campo_titulo.multiline = switch_lote.value
        campo_titulo.min_lines = 3 if switch_lote.value else 1
        campo_titulo.hint_text = "Uma tarefa por linha" if switch_lote.value else None
        page.update()

    switch_lote.on_change = alternar_lote

    campo_prazo = ft.TextField(
        label="Prazo (opcional)",
        label_style=ETIQUETA_BRANCA,
        hint_text="dd/mm/aaaa ou dd/mm/aaaa hh:mm",
        border_color=COR_ACENTO,
    )
    selecao_listas_add = ft.Column(spacing=0)
    dropdown_prioridade = ft.Dropdown(
        expand=True,
        label="Prioridade",
        label_style=ETIQUETA_BRANCA,
        value="Média",
        options=[ft.dropdown.Option(p) for p in PRIORIDADES],
        border_color=COR_ACENTO,
    )
    dropdown_repetir = ft.Dropdown(
        expand=True,
        label="Repetir",
        label_style=ETIQUETA_BRANCA,
        value="Não repete",
        options=[ft.dropdown.Option(r) for r in REPETICOES],
        border_color=COR_ACENTO,
    )

    async def salvar(e):
        texto = (campo_titulo.value or "").strip()
        if not texto:
            return
        prazo = db.parse_prazo(campo_prazo.value or "")
        prioridade = PRIORIDADES[dropdown_prioridade.value or "Média"]
        # Em lote: uma tarefa por linha; senão, uma só
        if switch_lote.value:
            titulos = [t.strip() for t in texto.split("\n") if t.strip()]
        else:
            titulos = [texto]
        repetir = REPETICOES[dropdown_repetir.value or "Não repete"]
        listas = listas_marcadas(selecao_listas_add) or ["Padrão"]
        for titulo in titulos:
            db.adicionar_tarefa(titulo, listas, prioridade, prazo, repetir)
        await voltar_para_lista()

    # A tela de nova tarefa ocupa a página inteira (nada de meia tela).
    # O respiro no topo evita a label flutuante ser cortada quando o teclado
    # sobe ou quando o campo vira multilinha no modo "criar várias"
    form_nova_tarefa: list[ft.Control] = [
        ft.Container(height=16),
        campo_titulo,
        switch_lote,
        campo_prazo,
        ft.Text("Listas", size=14, weight=ft.FontWeight.BOLD, color=COR_TEXTO_SUAVE),
        selecao_listas_add,
        ft.Row([dropdown_prioridade]),
        ft.Row([dropdown_repetir]),
        ft.Container(
            ft.Row(
                [
                    ft.TextButton(
                        "Cancelar",
                        on_click=voltar_para_lista,
                        style=ft.ButtonStyle(color="white"),
                    ),
                    ft.FilledButton(
                        "Salvar tarefa",
                        icon=ft.Icons.CHECK,
                        on_click=salvar,
                        style=ft.ButtonStyle(color="white", bgcolor=COR_ACENTO),
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
                spacing=12,
            ),
            padding=ft.Padding(left=0, top=8, right=0, bottom=0),
        ),
    ]

    # O Container interno dá respiro nas laterais: a barra de rolagem fica
    # no trilho dela, sem cobrir a borda dos campos
    vista_nova_tarefa = ft.Column(
        [
            ft.Container(
                ft.Column(
                    form_nova_tarefa,
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                padding=ft.Padding(left=4, top=0, right=14, bottom=8),
            )
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    def render_nova_tarefa():
        fab.visible = False
        appbar.leading = botao_voltar
        botao_busca.visible = False
        subtitulo_appbar.value = "Nova tarefa"
        area_conteudo.content = vista_nova_tarefa
        page.update()

    def abrir_adicionar(e):
        # Na tela de gerenciamento, o "+" cria uma lista; nas demais, uma tarefa
        if filtro["modo"] == "listas":
            campo_nome_lista.value = ""
            switch_oculta.value = False
            page.show_dialog(dialogo_nova_lista)
            return
        # Formulário sempre abre limpo, com a lista do filtro atual marcada
        campo_titulo.value = ""
        campo_prazo.value = ""
        switch_lote.value = False
        campo_titulo.multiline = False
        campo_titulo.min_lines = 1
        campo_titulo.hint_text = None
        dropdown_prioridade.value = "Média"
        dropdown_repetir.value = "Não repete"
        montar_selecao_listas(selecao_listas_add, {filtro["lista"] or "Padrão"})
        filtro["retorno"] = "pendentes"
        filtro["modo"] = "nova"
        render_tarefas()

    # --- Botão voltar do Android --------------------------------------------
    async def ao_tentar_voltar(e):
        """Back do sistema: volta uma tela; na raiz, confirma antes de sair."""
        if gaveta_aberta["valor"]:
            gaveta_aberta["valor"] = False
            await page.close_drawer()
        elif filtro["modo"] in ("nova", "editar"):
            await voltar_para_lista()
        elif filtro["modo"] != "pendentes":
            filtro["modo"] = "pendentes"
            render_tarefas()
        elif filtro["lista"] is not None:
            filtro["lista"] = None
            render_tarefas()
        else:
            page.show_dialog(dialogo_sair)
        await e.control.confirm_pop(False)

    def sair_do_app(e):
        os._exit(0)  # encerra o processo; é o jeito de fechar o app no Android

    dialogo_sair = ft.AlertDialog(
        title=ft.Text("Sair do app?"),
        content=ft.Text("Suas tarefas ficam salvas."),
        actions=[
            botao_texto("Cancelar", lambda e: page.pop_dialog()),
            botao_cheio("Sair", sair_do_app),
        ],
        bgcolor=COR_FUNDO,
    )

    # --- Estrutura da página ----------------------------------------------
    # O voltar do sistema é interceptado na View raiz (o Page não tem
    # property proxy pra can_pop, diferente do appbar)
    vista_raiz = page.views[0]
    vista_raiz.can_pop = False
    vista_raiz.on_confirm_pop = ao_tentar_voltar
    botao_menu.on_click = abrir_gaveta
    botao_busca.on_click = alternar_busca
    botao_voltar.on_click = voltar_para_lista
    page.services.append(seletor_arquivos)
    page.overlay.append(aviso_container)
    page.appbar = appbar
    fab.on_click = abrir_adicionar
    page.floating_action_button = fab
    coluna_central = ft.Container(area_conteudo, padding=12, expand=True)
    if eh_desktop:
        # Coluna central de largura limitada; o aviso flutuante acompanha
        def ajustar_largura():
            largura = page.width or LARGURA_CONTEUDO_DESKTOP
            coluna_central.width = min(LARGURA_CONTEUDO_DESKTOP, largura)
            margem = max(16.0, (largura - LARGURA_CONTEUDO_DESKTOP) / 2 + 16)
            aviso_container.left = margem
            aviso_container.right = margem

        def ao_redimensionar(e):
            ajustar_largura()
            page.update()

        coluna_central.expand = False
        ajustar_largura()
        page.on_resize = ao_redimensionar
        page.add(
            ft.Row(
                [coluna_central],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                expand=True,
            )
        )
    else:
        page.add(coluna_central)

    render_tarefas()


ft.run(main)
