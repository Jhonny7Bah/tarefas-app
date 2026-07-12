"""Camada de dados do app: SQLite e as regras de domínio das tarefas.

Sem nada de interface aqui: todas as funções são chamáveis (e testáveis)
sem o Flet. O ``init_db()`` faz migração incremental, então bancos criados
por versões antigas do app ganham as colunas/tabelas novas sem perder dados.
"""

import calendar
import json
import os
import sqlite3
from datetime import date, datetime, timedelta

from constantes import LISTAS_INICIAIS, MAX_SUBTAREFAS

# No Android, FLET_APP_STORAGE_DATA aponta pro diretório de dados persistente
# do app (sobrevive a atualizações). No desktop a variável não existe e o
# banco fica na pasta atual, como sempre.
DB = os.path.join(os.getenv("FLET_APP_STORAGE_DATA") or ".", "tarefas.db")

# Subconsulta usada nos SELECTs pra montar a etiqueta "Financeiro · Pessoal"
_AGG_LISTAS = (
    "(SELECT GROUP_CONCAT(lista, ' · ') FROM tarefa_listas"
    " WHERE tarefa_id = t.id) AS listas"
)

# Quantos dias antes do prazo a próxima ocorrência de uma recorrente aparece
ANTECEDENCIA_REPETICAO = timedelta(days=1)


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
        con.execute(
            "ALTER TABLE tarefas ADD COLUMN prioridade INTEGER NOT NULL DEFAULT 1"
        )
    if "prazo" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN prazo TEXT")
    if "concluida_em" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN concluida_em TEXT")
    if "descricao_conclusao" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN descricao_conclusao TEXT")
    if "repetir" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN repetir TEXT")
    if "aparece_em" not in existentes:
        con.execute("ALTER TABLE tarefas ADD COLUMN aparece_em TEXT")
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
    # Associação N:N: uma tarefa pode estar em várias listas
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS tarefa_listas (
            tarefa_id INTEGER NOT NULL,
            lista     TEXT NOT NULL,
            UNIQUE (tarefa_id, lista)
        )
        """
    )
    # Semeia as listas padrão + qualquer categoria que já exista nas tarefas
    for nome in LISTAS_INICIAIS:
        con.execute("INSERT OR IGNORE INTO listas (nome) VALUES (?)", (nome,))
    con.execute(
        "INSERT OR IGNORE INTO listas (nome) SELECT DISTINCT categoria FROM tarefas"
    )
    # Migração: tarefas antigas entram no N:N com a lista da coluna categoria
    con.execute(
        "INSERT OR IGNORE INTO tarefa_listas (tarefa_id, lista)"
        " SELECT id, categoria FROM tarefas"
    )
    con.commit()
    con.close()


def rotulo_listas(t):
    """Nome(s) de lista pra etiqueta do card."""
    try:
        return t["listas"] or t["categoria"]
    except IndexError:
        return t["categoria"]


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
    padrao = (
        "%" + termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    )
    linhas = con.execute(
        rf"""
        SELECT t.*, {_AGG_LISTAS} FROM tarefas t
        WHERE t.titulo LIKE ? ESCAPE '\' OR t.descricao_conclusao LIKE ? ESCAPE '\'
        ORDER BY t.concluida ASC, t.prioridade DESC,
                 (t.prazo IS NULL), t.prazo ASC, t.id DESC
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
        con.execute(
            "UPDATE OR IGNORE tarefa_listas SET lista = ? WHERE lista = ?",
            (novo_nome, antigo[0]),
        )
        # se alguma tarefa já estava nas duas listas, remove a duplicada antiga
        con.execute("DELETE FROM tarefa_listas WHERE lista = ?", (antigo[0],))
        con.commit()
    con.close()


def excluir_lista(lid):
    """Apaga a lista; tarefa que ficaria sem lista vai pra 'Padrão'."""
    con = sqlite3.connect(DB)
    nome = con.execute("SELECT nome FROM listas WHERE id = ?", (lid,)).fetchone()
    if nome and nome[0] != "Padrão":
        con.execute("DELETE FROM tarefa_listas WHERE lista = ?", (nome[0],))
        # órfãs (não estão em mais nenhuma lista) vão pra Padrão
        con.execute(
            """
            INSERT OR IGNORE INTO tarefa_listas (tarefa_id, lista)
            SELECT id, 'Padrão' FROM tarefas
            WHERE id NOT IN (SELECT tarefa_id FROM tarefa_listas)
            """
        )
        con.execute(
            "UPDATE tarefas SET categoria = 'Padrão' WHERE categoria = ?", (nome[0],)
        )
        con.execute("DELETE FROM listas WHERE id = ?", (lid,))
        con.commit()
    con.close()


def contar_por_lista_total():
    """Total de tarefas (pendentes + concluídas) por lista, pro gerenciamento."""
    con = sqlite3.connect(DB)
    linhas = dict(
        con.execute(
            "SELECT lista, COUNT(*) FROM tarefa_listas GROUP BY lista"
        ).fetchall()
    )
    con.close()
    return linhas


def listar_pendentes(lista=None):
    """Pendentes de uma lista, ou de todas (excluindo listas ocultas)."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    base = f"""
        SELECT t.*, {_AGG_LISTAS} FROM tarefas t
        WHERE t.concluida = 0
          AND (t.aparece_em IS NULL OR t.aparece_em <= datetime('now','localtime'))
          {{filtro}}
        ORDER BY t.prioridade DESC, (t.prazo IS NULL), t.prazo ASC, t.id DESC
    """
    if lista is None:
        # "Todas": aparece se estiver em pelo menos uma lista não oculta
        q = base.format(
            filtro="""AND EXISTS (
                SELECT 1 FROM tarefa_listas tl JOIN listas l ON l.nome = tl.lista
                WHERE tl.tarefa_id = t.id AND l.oculta = 0
            )"""
        )
        linhas = con.execute(q).fetchall()
    else:
        q = base.format(
            filtro=(
                "AND EXISTS (SELECT 1 FROM tarefa_listas"
                " WHERE tarefa_id = t.id AND lista = ?)"
            )
        )
        linhas = con.execute(q, (lista,)).fetchall()
    con.close()
    return linhas


def listas_da_tarefa(tid):
    con = sqlite3.connect(DB)
    nomes = [
        r[0]
        for r in con.execute(
            "SELECT lista FROM tarefa_listas WHERE tarefa_id = ? ORDER BY lista",
            (tid,),
        )
    ]
    con.close()
    return nomes


def _definir_listas(con, tid, listas):
    con.execute("DELETE FROM tarefa_listas WHERE tarefa_id = ?", (tid,))
    for nome in listas:
        con.execute(
            "INSERT OR IGNORE INTO tarefa_listas (tarefa_id, lista) VALUES (?, ?)",
            (tid, nome),
        )
    # coluna legada continua apontando pra primeira lista
    con.execute("UPDATE tarefas SET categoria = ? WHERE id = ?", (listas[0], tid))


def listar_concluidas(lista=None):
    """Concluídas, mais recentes primeiro. Sempre mostra todas as listas."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    q = f"SELECT t.*, {_AGG_LISTAS} FROM tarefas t WHERE t.concluida = 1"
    params = ()
    if lista is not None:
        q += (
            " AND EXISTS (SELECT 1 FROM tarefa_listas"
            " WHERE tarefa_id = t.id AND lista = ?)"
        )
        params = (lista,)
    q += " ORDER BY t.concluida_em DESC, t.id DESC"
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
            """
            SELECT tl.lista, COUNT(*) FROM tarefa_listas tl
            JOIN tarefas t ON t.id = tl.tarefa_id
            WHERE t.concluida = 0
              AND (t.aparece_em IS NULL OR t.aparece_em <= datetime('now','localtime'))
            GROUP BY tl.lista
            """
        ).fetchall()
    )
    todas = con.execute(
        """
        SELECT COUNT(*) FROM tarefas t
        WHERE t.concluida = 0
          AND (t.aparece_em IS NULL OR t.aparece_em <= datetime('now','localtime'))
          AND EXISTS (
              SELECT 1 FROM tarefa_listas tl JOIN listas l ON l.nome = tl.lista
              WHERE tl.tarefa_id = t.id AND l.oculta = 0
          )
        """
    ).fetchone()[0]
    concluidas = con.execute(
        "SELECT COUNT(*) FROM tarefas WHERE concluida = 1"
    ).fetchone()[0]
    con.close()
    return {"por_lista": por_lista, "todas": todas, "concluidas": concluidas}


def adicionar_tarefa(titulo, listas, prioridade=1, prazo=None, repetir=None):
    """``listas`` pode ser um nome só ou uma lista de nomes (N:N)."""
    if isinstance(listas, str):
        listas = [listas]
    listas = listas or ["Padrão"]
    con = sqlite3.connect(DB)
    cur = con.execute(
        "INSERT INTO tarefas (titulo, categoria, prioridade, prazo, repetir)"
        " VALUES (?, ?, ?, ?, ?)",
        (titulo, listas[0], prioridade, prazo, repetir),
    )
    _definir_listas(con, cur.lastrowid, listas)
    con.commit()
    con.close()


def atualizar_tarefa(tid, titulo, listas, prioridade, prazo, repetir=None):
    if isinstance(listas, str):
        listas = [listas]
    listas = listas or ["Padrão"]
    con = sqlite3.connect(DB)
    con.execute(
        "UPDATE tarefas SET titulo = ?, prioridade = ?, prazo = ?, repetir = ?"
        " WHERE id = ?",
        (titulo, prioridade, prazo, repetir, tid),
    )
    _definir_listas(con, tid, listas)
    con.commit()
    con.close()


def excluir_tarefa(tid):
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM subtarefas WHERE tarefa_id = ?", (tid,))
    con.execute("DELETE FROM tarefa_listas WHERE tarefa_id = ?", (tid,))
    con.execute("DELETE FROM tarefas WHERE id = ?", (tid,))
    con.commit()
    con.close()


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
            "UPDATE subtarefas SET concluida = 1,"
            " concluida_em = datetime('now','localtime') WHERE id = ?",
            (sid,),
        )
    else:
        con.execute(
            "UPDATE subtarefas SET concluida = 0, concluida_em = NULL WHERE id = ?",
            (sid,),
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
        "SELECT COUNT(*), COALESCE(SUM(concluida), 0) FROM subtarefas"
        " WHERE tarefa_id = ?",
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


def proxima_ocorrencia(prazo_iso, repetir):
    """Próximo prazo de uma tarefa recorrente (diaria/semanal/mensal)."""
    prazo = datetime.fromisoformat(prazo_iso)
    if repetir == "diaria":
        prox = prazo + timedelta(days=1)
    elif repetir == "semanal":
        prox = prazo + timedelta(days=7)
    elif repetir == "mensal":
        if prazo.month < 12:
            ano, mes = prazo.year, prazo.month + 1
        else:
            ano, mes = prazo.year + 1, 1
        dia = min(prazo.day, calendar.monthrange(ano, mes)[1])
        prox = prazo.replace(year=ano, month=mes, day=dia)
    else:
        return None
    return prox.isoformat(sep=" ", timespec="minutes")


def marcar_concluida(tid, valor):
    """Conclui/reabre. Se a tarefa repete e tem prazo, agenda a próxima
    ocorrência (que só aparece perto da data). Retorna o id da ocorrência
    criada, ou None."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    novo_id = None
    if valor:
        con.execute(
            "UPDATE tarefas SET concluida = 1,"
            " concluida_em = datetime('now','localtime') WHERE id = ?",
            (tid,),
        )
        t = con.execute("SELECT * FROM tarefas WHERE id = ?", (tid,)).fetchone()
        if t and t["repetir"] and t["prazo"]:
            prox = proxima_ocorrencia(t["prazo"], t["repetir"])
            if prox:
                aparece = (
                    datetime.fromisoformat(prox) - ANTECEDENCIA_REPETICAO
                ).isoformat(sep=" ", timespec="minutes")
                cur = con.execute(
                    """
                    INSERT INTO tarefas
                        (titulo, categoria, prioridade, prazo, repetir, aparece_em)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        t["titulo"],
                        t["categoria"],
                        t["prioridade"],
                        prox,
                        t["repetir"],
                        aparece,
                    ),
                )
                novo_id = cur.lastrowid
                # A ocorrência nova herda as mesmas listas (N:N)
                con.execute(
                    """
                    INSERT INTO tarefa_listas (tarefa_id, lista)
                    SELECT ?, lista FROM tarefa_listas WHERE tarefa_id = ?
                    """,
                    (novo_id, tid),
                )
                # Renova o checklist: subtarefas iguais, todas desmarcadas
                con.execute(
                    """
                    INSERT INTO subtarefas (tarefa_id, titulo)
                    SELECT ?, titulo FROM subtarefas WHERE tarefa_id = ? ORDER BY id
                    """,
                    (novo_id, tid),
                )
    else:
        con.execute(
            "UPDATE tarefas SET concluida = 0, concluida_em = NULL WHERE id = ?",
            (tid,),
        )
    con.commit()
    con.close()
    return novo_id


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
        return (
            datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M").replace(" 00:00", "")
        )
    except (ValueError, TypeError):
        return iso or ""


# ---------------------------------------------------------------------------
# Backup e restauração
# ---------------------------------------------------------------------------
SCHEMA_BACKUP = 1


def exportar_json():
    """Backup completo num JSON legível, com versão do schema."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    listas = [
        {"nome": lst["nome"], "oculta": bool(lst["oculta"])}
        for lst in con.execute("SELECT * FROM listas ORDER BY nome")
    ]
    tarefas = []
    for t in con.execute("SELECT * FROM tarefas ORDER BY id"):
        nomes = [
            r[0]
            for r in con.execute(
                "SELECT lista FROM tarefa_listas WHERE tarefa_id = ? ORDER BY lista",
                (t["id"],),
            )
        ]
        subtarefas = [
            {
                "titulo": s["titulo"],
                "concluida": bool(s["concluida"]),
                "criada_em": s["criada_em"],
                "concluida_em": s["concluida_em"],
            }
            for s in con.execute(
                "SELECT * FROM subtarefas WHERE tarefa_id = ? ORDER BY id",
                (t["id"],),
            )
        ]
        tarefas.append(
            {
                "titulo": t["titulo"],
                "listas": nomes or [t["categoria"]],
                "concluida": bool(t["concluida"]),
                "criada_em": t["criada_em"],
                "concluida_em": t["concluida_em"],
                "descricao_conclusao": t["descricao_conclusao"],
                "prioridade": t["prioridade"],
                "prazo": t["prazo"],
                "repetir": t["repetir"],
                "aparece_em": t["aparece_em"],
                "subtarefas": subtarefas,
            }
        )
    con.close()
    return json.dumps(
        {
            "app": "tarefas",
            "schema": SCHEMA_BACKUP,
            "exportado_em": datetime.now().isoformat(sep=" ", timespec="minutes"),
            "listas": listas,
            "tarefas": tarefas,
        },
        ensure_ascii=False,
        indent=2,
    )


def importar_json(texto):
    """Restaura um backup JSON, SUBSTITUINDO todos os dados atuais.

    Retorna a quantidade de tarefas restauradas. Levanta ValueError se o
    arquivo não for um backup válido deste app.
    """
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("O arquivo não é um JSON válido.") from exc
    if not isinstance(dados, dict) or dados.get("app") != "tarefas":
        raise ValueError("O arquivo não é um backup deste app.")
    if dados.get("schema", 0) > SCHEMA_BACKUP:
        raise ValueError("Backup de uma versão mais nova do app. Atualize antes.")

    con = sqlite3.connect(DB)
    try:
        con.execute("DELETE FROM subtarefas")
        con.execute("DELETE FROM tarefa_listas")
        con.execute("DELETE FROM tarefas")
        con.execute("DELETE FROM listas")
        for lst in dados.get("listas", []):
            con.execute(
                "INSERT OR IGNORE INTO listas (nome, oculta) VALUES (?, ?)",
                (lst["nome"], 1 if lst.get("oculta") else 0),
            )
        agora = datetime.now().isoformat(sep=" ", timespec="seconds")
        for t in dados.get("tarefas", []):
            listas = t.get("listas") or ["Padrão"]
            cur = con.execute(
                "INSERT INTO tarefas (titulo, categoria, concluida, criada_em,"
                " concluida_em, descricao_conclusao, prioridade, prazo, repetir,"
                " aparece_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    t["titulo"],
                    listas[0],
                    1 if t.get("concluida") else 0,
                    t.get("criada_em") or agora,
                    t.get("concluida_em"),
                    t.get("descricao_conclusao"),
                    t.get("prioridade", 1),
                    t.get("prazo"),
                    t.get("repetir"),
                    t.get("aparece_em"),
                ),
            )
            tid = cur.lastrowid
            for nome in listas:
                con.execute("INSERT OR IGNORE INTO listas (nome) VALUES (?)", (nome,))
                con.execute(
                    "INSERT OR IGNORE INTO tarefa_listas (tarefa_id, lista)"
                    " VALUES (?, ?)",
                    (tid, nome),
                )
            for s in t.get("subtarefas", []):
                con.execute(
                    "INSERT INTO subtarefas (tarefa_id, titulo, concluida,"
                    " criada_em, concluida_em) VALUES (?, ?, ?, ?, ?)",
                    (
                        tid,
                        s["titulo"],
                        1 if s.get("concluida") else 0,
                        s.get("criada_em") or agora,
                        s.get("concluida_em"),
                    ),
                )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    init_db()  # garante as listas padrão e qualquer migração pendente
    return len(dados.get("tarefas", []))


def exportar_db_bytes():
    """Cópia fiel do arquivo do banco, pra backup binário."""
    with open(DB, "rb") as arquivo:
        return arquivo.read()


def importar_db_bytes(dados):
    """Restaura um backup .db, SUBSTITUINDO o banco atual.

    Retorna a quantidade de tarefas restauradas. Levanta ValueError se o
    conteúdo não for um banco SQLite deste app.
    """
    if not dados.startswith(b"SQLite format 3\x00"):
        raise ValueError("O arquivo não é um banco de dados deste app.")
    temporario = DB + ".restauracao"
    with open(temporario, "wb") as arquivo:
        arquivo.write(dados)
    try:
        con = sqlite3.connect(temporario)
        tabelas = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        con.close()
        if "tarefas" not in tabelas:
            raise ValueError("O banco não tem as tabelas deste app.")
        os.replace(temporario, DB)
    finally:
        if os.path.exists(temporario):
            os.remove(temporario)
    init_db()  # migra o backup se ele veio de uma versão antiga do app
    con = sqlite3.connect(DB)
    total = con.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0]
    con.close()
    return total
