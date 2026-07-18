"""Sincronização com o Supabase via REST (PostgREST), com urllib puro.

O SQLite local continua sendo a verdade: o servidor é o ponto de
encontro entre os dispositivos. O merge é "último carimbo leva", por
documento (a tarefa viaja inteira, com subtarefas e listas dentro).

A credencial NUNCA é embutida no app: fica num sync.json no diretório
de dados do dispositivo, preenchido pela tela de configuração.
"""

import json
import os
import urllib.request

import db

ARQ_CONFIG = os.path.join(os.path.dirname(db.DB), "sync.json")


def carregar_config():
    """Config salva no dispositivo, ou None se o sync não foi configurado."""
    try:
        with open(ARQ_CONFIG, encoding="utf-8") as arq:
            cfg = json.load(arq)
        if cfg.get("url") and cfg.get("chave"):
            return cfg
    except (OSError, ValueError):
        pass
    return None


def salvar_config(url, chave):
    cfg = {"url": url.strip().rstrip("/"), "chave": chave.strip()}
    with open(ARQ_CONFIG, "w", encoding="utf-8") as arq:
        json.dump(cfg, arq)
    return cfg


def _req(cfg, metodo, caminho, corpo=None, prefer=None):
    cabecalhos = {
        "apikey": cfg["chave"],
        "Authorization": "Bearer " + cfg["chave"],
        "Content-Type": "application/json",
    }
    if prefer:
        cabecalhos["Prefer"] = prefer
    req = urllib.request.Request(
        cfg["url"] + "/rest/v1/" + caminho,
        method=metodo,
        data=json.dumps(corpo).encode("utf-8") if corpo is not None else None,
        headers=cabecalhos,
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        texto = resp.read().decode("utf-8")
    return json.loads(texto) if texto else None


def testar_conexao(cfg):
    """Confere URL/chave e se as tabelas existem. Levanta exceção se não."""
    _req(cfg, "GET", "listas?select=uuid&limit=1")
    _req(cfg, "GET", "tarefas?select=uuid&limit=1")
    return True


def _upsert(cfg, caminho, linhas):
    if linhas:
        _req(
            cfg,
            "POST",
            caminho,
            corpo=linhas,
            prefer="resolution=merge-duplicates",
        )


def sincronizar(cfg):
    """Puxa, faz o merge (último carimbo leva) e empurra os pendentes.

    Retorna {"recebidas": n, "enviadas": n} pro aviso da interface.
    """
    lapides = db.lapides()
    local = db.indice_sync()
    recebidas = 0

    # ---- puxar: listas primeiro (tarefas referenciam listas pelo nome)
    for caminho, tipo in (("listas", "lista"), ("tarefas", "tarefa")):
        indice = local[caminho]
        for r in _req(cfg, "GET", f"{caminho}?select=*") or []:
            uid, carimbo = r["uuid"], r["modificado_em"]
            if r["excluida"]:
                # o servidor diz que morreu; some daqui se não mexemos depois
                meu = indice.get(uid)
                if meu is not None and meu <= carimbo:
                    db.excluir_remoto(tipo, uid)
                    recebidas += 1
                continue
            lap = lapides.get(uid)
            if lap:
                if lap["excluido_em"] >= carimbo:
                    continue  # nossa exclusão é mais nova: vence no envio
                db.remover_lapide(uid)  # reviveu no servidor depois de morrer
                del lapides[uid]
            meu = indice.get(uid)
            if meu is None or meu < carimbo:
                if tipo == "lista":
                    db.aplicar_lista_remota(uid, r["dados"], carimbo)
                else:
                    db.aplicar_tarefa_remota(uid, r["dados"], carimbo)
                recebidas += 1

    # ---- empurrar: pendentes + lápides que sobreviveram ao merge
    pendentes = db.pendentes_de_envio()
    for caminho in ("listas", "tarefas"):
        _upsert(
            cfg,
            caminho,
            [{**doc, "excluida": False} for doc in pendentes[caminho]],
        )
    lapides = db.lapides()
    for caminho, tipo in (("listas", "lista"), ("tarefas", "tarefa")):
        _upsert(
            cfg,
            caminho,
            [
                {
                    "uuid": uid,
                    "dados": {},
                    "modificado_em": lap["excluido_em"],
                    "excluida": True,
                }
                for uid, lap in lapides.items()
                if lap["tipo"] == tipo
            ],
        )
    db.marcar_enviadas(
        [doc["uuid"] for doc in pendentes["tarefas"]],
        [doc["uuid"] for doc in pendentes["listas"]],
    )
    db.limpar_lapides(list(lapides))
    enviadas = len(pendentes["tarefas"]) + len(pendentes["listas"]) + len(lapides)
    return {"recebidas": recebidas, "enviadas": enviadas}
