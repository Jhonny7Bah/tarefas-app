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
from datetime import datetime, timedelta

import db

ARQ_CONFIG = os.path.join(os.path.dirname(db.DB), "sync.json")


def _carimbo_vencedor(carimbo_remoto, carimbo_local):
    """Carimbo que garante vitória sobre o remoto: 1s à frente dele.

    Relógios de aparelhos diferentes desviam; quando o remoto está "no
    futuro", a mudança local pendente (o evento real mais recente) precisa
    de um carimbo maior pra não ser atropelada nem aqui nem nos outros.
    """
    try:
        vencedor = datetime.fromisoformat(carimbo_remoto) + timedelta(seconds=1)
        vencedor = vencedor.isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return carimbo_local
    return max(vencedor, carimbo_local)


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


MAX_BACKUPS_NUVEM = 20


def salvar_backup_nuvem(cfg, conteudo_json, dispositivo):
    """Sobe uma foto completa dos dados pra tabela backups e poda antigas."""
    agora = datetime.now().isoformat(sep=" ", timespec="seconds")
    _req(
        cfg,
        "POST",
        "backups",
        corpo=[
            {
                "criado_em": agora,
                "dispositivo": dispositivo,
                "conteudo": json.loads(conteudo_json),
            }
        ],
    )
    # retenção: além das MAX_BACKUPS_NUVEM mais novas, o resto morre
    linhas = _req(cfg, "GET", "backups?select=id&order=criado_em.desc") or []
    excedentes = [str(r["id"]) for r in linhas[MAX_BACKUPS_NUVEM:]]
    if excedentes:
        _req(cfg, "DELETE", f"backups?id=in.({','.join(excedentes)})")


def listar_backups_nuvem(cfg):
    """Fotos disponíveis, mais novas primeiro (sem o conteúdo, que pesa)."""
    return (
        _req(
            cfg,
            "GET",
            "backups?select=id,criado_em,dispositivo&order=criado_em.desc",
        )
        or []
    )


def baixar_backup_nuvem(cfg, backup_id):
    """Conteúdo de uma foto, como texto JSON pro importar_json."""
    linhas = _req(cfg, "GET", f"backups?id=eq.{backup_id}&select=conteudo")
    if not linhas:
        raise ValueError("Esse backup não existe mais no servidor.")
    return json.dumps(linhas[0]["conteudo"], ensure_ascii=False)


def sincronizar(cfg):
    """Puxa, faz o merge (último carimbo leva) e empurra os pendentes.

    Retorna {"recebidas": n, "enviadas": n} pro aviso da interface.
    """
    lapides = db.lapides()
    local = db.indice_sync()
    recebidas = 0

    # ---- puxar: listas primeiro (tarefas referenciam listas pelo nome).
    # Regra de ouro do merge: mudança local AINDA NÃO ENVIADA é sagrada.
    # O pull nunca a atropela; no máximo adianta o carimbo dela pra vencer
    # o remoto "do futuro" (relógio de outro aparelho adiantado) no push
    for caminho, tipo in (("listas", "lista"), ("tarefas", "tarefa")):
        indice = local[caminho]
        for r in _req(cfg, "GET", f"{caminho}?select=*") or []:
            uid, carimbo = r["uuid"], r["modificado_em"]
            meu = indice.get(uid)
            if r["excluida"]:
                # o servidor diz que morreu; some daqui se não mexemos depois
                if meu is not None and meu[0] <= carimbo:
                    if meu[1]:  # pendente local: sobrevive e revive no push
                        db.adiantar_carimbo(
                            tipo, uid, _carimbo_vencedor(carimbo, meu[0])
                        )
                        continue
                    db.excluir_remoto(tipo, uid)
                    recebidas += 1
                continue
            lap = lapides.get(uid)
            if lap:
                if lap["excluido_em"] >= carimbo:
                    continue  # nossa exclusão é mais nova: vence no envio
                db.remover_lapide(uid)  # reviveu no servidor depois de morrer
                del lapides[uid]
            if meu is None or meu[0] < carimbo:
                if meu is not None and meu[1]:  # pendente local: sagrada
                    db.adiantar_carimbo(tipo, uid, _carimbo_vencedor(carimbo, meu[0]))
                    continue
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
        [(doc["uuid"], doc["modificado_em"]) for doc in pendentes["tarefas"]],
        [(doc["uuid"], doc["modificado_em"]) for doc in pendentes["listas"]],
    )
    db.limpar_lapides(list(lapides))
    enviadas = len(pendentes["tarefas"]) + len(pendentes["listas"]) + len(lapides)
    return {"recebidas": recebidas, "enviadas": enviadas}
