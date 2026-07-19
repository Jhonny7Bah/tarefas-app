# Gerenciador de Tarefas

App Android de gerenciamento de tarefas escrito em **Python + Flet** (o Flet
renderiza com Flutter por baixo, então o visual é Material Design nativo).
A especificação vem do documento "Ideia de App Tarefa" do usuário.
Identidade visual própria desde a v1.2.0: grafite + verde-esmeralda, cards
de cantos arredondados com chips de lista e borda de prioridade.

## Decisões do projeto

- **Offline-first.** O SQLite local (`tarefas.db`) é sempre a verdade; o app
  funciona 100% sem internet. Desde a v1.8.0 existe sync OPCIONAL via
  Supabase (REST/PostgREST, urllib puro, motor em `sync.py`): merge por
  documento com "último carimbo leva", lápides pra exclusão, uuids como
  identidade. A credencial (service_role) NUNCA vai no código nem no
  pacote: o usuário cola URL + chave na tela "Configurar sincronização"
  de cada dispositivo (fica em `sync.json` no diretório de dados). As
  tabelas remotas têm RLS ligado sem policy: chave anon não acessa nada.
- Prioridade manda na ordenação (alta > média > baixa); prazo mais próximo
  desempata; sem prazo vai pro fim do empate.
- Tarefas agrupadas por situação do prazo: Atrasada / Hoje / Próximas / Sem data.
- Listas marcadas como ocultas somem do filtro "Todas", mas aparecem normalmente
  quando filtradas diretamente.
- Toda tarefa registra criação (`criada_em`) e conclusão (`concluida_em`).
- A descrição de "como foi concluída" só aparece na aba de Concluídas.
- **Nunca usar travessão (—) em textos visíveis do app** — preferência
  explícita do usuário (o `·` separador de listas pode).
- Um commit por feature.

## Como rodar

```bash
flet run --ignore-dirs storage main.py   # janela nativa (SEMPRE com a flag!)
flet run --web main.py                   # navegador
flet build apk --split-per-abi  # APKs Android (o flet baixa o próprio Flutter;
                                #  precisa de ANDROID_HOME=/opt/android-sdk e JDK 17)
CFLAGS="-Wno-macro-redefined" CXXFLAGS="-Wno-macro-redefined" flet build linux
    # Executável desktop (build/linux/tarefas; dados em
    # ~/.local/share/dev.jhon7bah.tarefas). As flags são OBRIGATÓRIAS: o
    # runner do Flutter compila com -Werror e os headers do Python do
    # serious_python redefinem _POSIX_C_SOURCE/_XOPEN_SOURCE (clang novo
    # promove a erro). Precisa de clang, cmake e ninja. Pra forçar rebuild
    # do zero, apagar build/flutter E build/.hash juntos (o .hash é o cache
    # de etapas; sem apagar os dois o flet se perde)
./release.sh "o que mudou"      # build + release no GitHub num comando
```

Usar sempre o Python do projeto: `.venv/bin/python` (Python 3.14, Flet 0.85.3).

**Por que o `--ignore-dirs storage` é obrigatório no desktop:** o `flet run`
vigia a pasta do projeto pra hot-reload e reinicia o app em QUALQUER mudança
de arquivo — e o banco fica em `storage/data/` (é o FLET_APP_STORAGE_DATA que
o próprio flet run define). Sem a flag, cada gravação no banco reinicia o app
no meio do render: banner vermelho de reconexão, tela congelada e cards
"duplicados" (só visual; o banco fica correto). No Android não existe watcher,
então nada disso acontece no celular.

## ⚠️ Flet 0.85 — APIs que mudaram

A doc/exemplos online usam a API antiga, que **quebra** nessa versão:

| Antigo (quebra)                | Correto na 0.85                                  |
|--------------------------------|--------------------------------------------------|
| `ft.alignment.center`          | `ft.Alignment(0, 0)`                             |
| `ft.padding.symmetric/only`    | `ft.Padding(left=, top=, right=, bottom=)`       |
| `ft.border.only(...)`          | `ft.Border(left=ft.BorderSide(width=, color=))`  |
| `page.open(x)` / `page.close(x)` | `page.show_dialog(x)` / `page.pop_dialog()`    |
| `ft.app(main)`                 | `ft.run(main)`                                   |

- `BottomSheet`, `SnackBar` e `AlertDialog` são `DialogControl` → usar
  `show_dialog`/`pop_dialog`.
- `page.show_drawer()`/`page.close_drawer()` e `page.launch_url()` são
  **async** → handlers `async def` com `await`. CUIDADO: `inspect.
  iscoroutinefunction` mente pro `launch_url` (decorator de deprecação
  mascara) — sem await ele silenciosamente não faz nada.
- `can_pop`/`on_confirm_pop` (botão voltar) moram na **View**, e o `Page`
  NÃO faz proxy deles (só de appbar/drawer, que têm property explícita) —
  usar `page.views[0]`.
- Cor hexadecimal de 8 dígitos é **#AARRGGBB** (alpha PRIMEIRO, padrão
  Flutter), não #RRGGBBAA como no CSS — "#ffffff12" vira AMARELO opaco.
- NUNCA trocar o `content` do AnimatedSwitcher e reconstruir os filhos do
  novo conteúdo no MESMO lote de update: duplica visualmente os controles.
  Padrão: trocar o content + page.update(), `await asyncio.sleep(0.35)`
  (o fade), e só então reconstruir (ver `voltar_para_lista`). O mesmo vale
  pra fechar diálogo e trocar tela juntos: congela o front (ver
  `excluir_confirmado`).
- Antes de usar componente novo, validar construção com `.venv/bin/python`.

## Arquitetura

Módulos separados por responsabilidade (refatorado em 12/07/2026):

- `constantes.py` — cores do tema, prioridades, repetições, limites.
- `db.py` — camada de dados: SQLite + regras de domínio, sem nada de Flet
  (testável sem GUI). `init_db()` faz migração incremental via
  `PRAGMA table_info` + `ALTER TABLE`; bancos antigos ganham colunas novas
  sem perder dados.
- `atualizacao.py` — consulta de releases do GitHub e comparação de versão.
- `main.py` — só interface (`main(page)`): estado em dicts (`filtro`,
  `ultima_concluida`), funções `render_*` reconstroem a tela a partir do
  banco. A `VERSAO` mora aqui (o release.sh depende disso).

A interface é intencionalmente um módulo só: as telas são closures
interligadas; quebrar em `ui/` só quando houver como testar GUI (fazer
junto com as notificações, se valer a pena).

**Estilo: PEP 8 com 88 colunas** (mesmo limite do Flake8 do editor do
usuário; config do ruff no pyproject, regras E/W/F/I/N). O código é
formatado com `ruff format`. Rodar antes de commitar:

```bash
.venv/bin/ruff format . && .venv/bin/ruff check .
```

Evitar padrões que o Pylance (modo basic) marca: não indexar dicionário
com `dropdown.value` direto (é `str | None`) — usar `valor or "padrão"`.

## Como testar

**Regra de ouro (combinada com o usuário): validar TUDO no desktop antes de
soltar release** — `flet run --ignore-dirs storage main.py`, UMA janela por
vez (várias instâncias no mesmo banco geram comportamento fantasma). O ciclo
local é instantâneo; o de release custa ~5 min de build por tentativa.

Pra lógica: script Python no scratchpad que importa o módulo `db`, cria um
banco temporário, simula o schema antigo pra validar a migração e asserta as
regras. Nunca testar contra o banco do projeto.

## Ferramentas instaladas pro build do APK (jul/2026)

Instaladas só pra gerar o APK — anotado pra desinstalar no futuro se quiser:

```bash
# Pacotes (AUR, via yay):
yay -Rns jdk17-openjdk android-sdk-cmdline-tools-latest android-sdk-platform-tools
# Toolchain do flet build linux (repo oficial, instalada em 18/07/2026):
sudo pacman -Rns clang cmake ninja
```

O `flutter-bin` do AUR foi instalado e **removido logo em seguida** (jul/2026):
o link `/usr/bin/flutter` dele fazia o `flet build` apagar o `/usr/bin` do
PATH (bug do `cleanup_path` do Flet) e quebrava com `env: "bash": Arquivo ou
diretório inexistente`. O flet baixa e usa o Flutter próprio em `~/flutter/`.
(Os restos dele — montagem unionfs e `~/.cache/flutter_{sdk,local}` — já
foram limpos em 12/07/2026.)

Caches e diretórios que essas ferramentas criam por fora (apagar manualmente):

- `/opt/android-sdk/` — SDK do Android (pode passar de 1 GB; o chown pro
  usuário foi proposital, pro Gradle conseguir baixar componentes)
- `~/flutter/` — Flutter 3.41.7 que o **flet build** baixa por conta própria
  (ele exige essa versão exata; a do flutter-bin 3.44.6 é só ignorada)
- `~/.flet/` — caches do Flet
- `~/.config/flutter/` — settings do Flutter (inclui o jdk-dir apontando
  pro Java 17)
- `~/.gradle/` — cache do Gradle (cresce bastante com builds)
- `~/.pub-cache/` — pacotes do Dart/Flutter
- `~/.android/` — configs e chaves de debug do Android
- `~/.dart/` e `~/.flutter` — configs do Flutter
- `build/` dentro deste projeto — saída do flet build (já está no .gitignore)

## Como lançar uma versão nova

O app tem o botão "Verificar atualização" (gaveta), que consulta a última
release de https://github.com/Jhonny7Bah/tarefas-app e compara com a
constante `VERSAO` do main.py.

Checklist de release (a ordem importa):

1. Bumpar a versão nos **dois** lugares: `VERSAO` no `main.py` e
   `[project] version` no `pyproject.toml` (o `release.sh` valida isso).
2. Commit + push.
3. `./release.sh "o que mudou"` — builda e publica a release com o APK.
   (Manual, se precisar: `flet build apk --split-per-abi` +
   `gh release create v<versão> build/apk/tarefas-arm64-v8a.apk ...`;
   o asset PRECISA ter "arm64" no nome, o botão procura por isso.)
4. No celular: gaveta → Verificar atualização → Baixar → instalar por cima.

O banco fica em `FLET_APP_STORAGE_DATA` (persistente), então atualizar não
apaga as tarefas. NUNCA trocar o pacote (`dev.jhon7bah.tarefas`) nem buildar
em outra máquina sem migrar a chave de assinatura — senão o Android recusa
a atualização por cima.

## Roadmap (do documento do usuário)

- [x] Grupos por data, prioridade, prazo, timestamps, lote, desfazer
- [x] Gaveta lateral com listas, contadores e filtro
- [x] Listas dinâmicas com flag de oculta
- [x] Tela de Concluídas com descrição de conclusão
- [x] Editar/apagar tarefa (e apagar concluídas)
- [x] Editar/apagar lista (tela "Gerenciar listas"; Padrão protegida)
- [x] Busca (pendentes + concluídas, inclui descrição de conclusão)
- [x] Subtarefas (máx. 10 por tarefa, com timestamps)
- [x] Tarefa em mais de uma lista (N:N, tabela tarefa_listas)
- [x] "Repetir" inteligente (próxima ocorrência aparece 1 dia antes do prazo)
- [x] Timestamps de criação/conclusão visíveis na folha de edição
- [x] Build do APK (v1.0.0 instalada no celular do usuário em 11/07/2026;
      `flet build apk --split-per-abi`, instalar o tarefas-arm64-v8a.apk)
- [x] Botão "verificar atualização" — ciclo completo validado em 12/07/2026
      (v1.1.2→v1.1.3 instalada pelo próprio app, dados preservados)
- [x] Identidade visual própria (v1.2.0, instalada e aprovada pelo usuário
      em 12/07/2026): paleta grafite + verde-esmeralda, textos com voz
      própria, cards com chips de lista, AppBar à esquerda, ícone novo.
      Usabilidade intacta. Cores centralizadas em constantes.py
- [x] Nova tarefa em página inteira (v1.3.0): o "+" abre a tela toda com
      seta de voltar na barra, em vez do BottomSheet de meia tela.
      PREFERÊNCIA DO USUÁRIO: formulários em tela cheia, não meia tela
- [x] Edição de tarefa em página inteira (v1.5.0), mesmo padrão do "+";
      guarda de onde veio (lista ou busca) e devolve pro lugar certo ao
      salvar/voltar/excluir
- [x] Botão voltar do Android (v1.6.0): interceptado via View raiz
      (page.views[0].can_pop = False + on_confirm_pop, sempre chamando
      await confirm_pop(False)). Cascata: nova/edição volta pra origem,
      outras telas voltam pras pendentes, lista filtrada volta pro Todas,
      e na raiz pergunta "Sair do app?" (a saída usa os._exit(0), o jeito
      de encerrar um app Flet no Android)
- [ ] Notificações Android (plugin nativo + rebuild) — ADIADO a pedido do
      usuário; é o único item restante do documento original
- [x] MIGRAÇÃO CONCLUÍDA (13/07/2026): as 64 tarefas reais do app antigo
      (backup .tasksbak, SQLite com tabelas Task/TaskList) foram
      convertidas pro JSON do nosso backup e restauradas no celular do
      usuário via "Restaurar backup". O app antigo está aposentado;
      este app é agora o gerenciador de tarefas titular do usuário
- [x] Rodada de polimento v1.6.2–v1.6.6 (validada tela a tela pelo
      usuário no desktop): fluxo de exclusão com Desfazer completo,
      aviso próprio animado acima do FAB, pílulas de prioridade, tema
      unificado (labels/botões brancos), faixa na barra de status do
      Android, campos e dropdowns de largura cheia, e barra de rolagem
      com trilho próprio (sem cobrir cards/campos)
- [x] Backup e restauração (v1.4.0): exportar pela gaveta com escolha de
      formato — JSON (recomendado; schema versionado, subtarefas/listas
      aninhadas) ou cópia fiel do .db. Restaurar aceita os dois (detecta
      pelo conteúdo), avisa que substitui tudo, valida o arquivo e o
      banco fica intacto se a importação falhar. FilePicker via
      page.services; funções em db.py (exportar_json/importar_json/
      exportar_db_bytes/importar_db_bytes) com testes de ida e volta
- [x] App desktop Linux (v1.7.0, 18/07/2026): fase 1 da UI (janela 480x850,
      coluna central de até 520px, aviso acompanhando) com Android intacto;
      `flet build linux` funcionando (flags no "Como rodar"); release.sh
      publica o tarefas-linux-x64.tar.gz junto do APK e o botão de
      atualização baixa o asset da plataforma. Instalado na gaveta de apps
      do usuário via ~/.local/opt/tarefas + tarefas.desktop; dados em
      ~/.local/share/dev.jhon7bah.tarefas. PRÓXIMOS CAPÍTULOS COMBINADOS:
      fase 2 responsiva só depois de uso real no PC, e sync online
      (debater Supabase/Postgres; Sheets descartado)
- [x] Autoatualização desktop (v1.7.1, validada de ponta a ponta em
      18/07/2026): botão Atualizar baixa o tar.gz com barra de progresso,
      troca a instalação com swap atômico (falha no meio deixa a versão
      atual intacta; funções puras em atualizacao.py, testadas) e reabre
      sozinho. IMPORTANTE: o app empacotado extrai o app.zip pra
      ~/.local/share/dev.jhon7bah.tarefas/flet/app no BOOT (com .hash);
      sessão aberta não enxerga instalação nova, tem que fechar e abrir.
      Crash conhecido: o reinício automático da v1.7.1 pode crashar uma
      vez (corrida boot novo x teardown velho); corrigido com sleep no
      reiniciar() a partir da versão seguinte, a v1.7.1→seguinte ainda
      usa o código velho e pode soluçar
- [x] Sincronização online (v1.8.0, 18/07/2026): fundação (uuids +
      carimbos + lápides + backup schema 2) e motor completo, validado de
      ponta a ponta contra o Supabase real com dois dispositivos
      simulados (conflito resolvido pelo carimbo maior, exclusão sem
      ressurreição, rename de lista propagando). Sync silencioso ao
      abrir, após cada mudança (mutadores do db embrulhados no main com
      debounce de 2s; v1.8.1, depois do bug real: concluir num aparelho
      não chegava no outro porque só sincronizava na abertura) e a cada
      60s com o app aberto, além do botão "Sincronizar agora". Sem
      segundo plano: app fechado não sincroniza (sinergia futura com as
      notificações nativas). Arquitetura na seção "Decisões do projeto".
      VALIDADO PELO USUÁRIO NOS APARELHOS REAIS em 18/07/2026 (celular +
      PC na v1.8.1): "funcionou de boas"
- [ ] (Opcional, junto com notificações) atualização estilo Snaptube:
      download e instalação dentro do app, sem navegador — exige extensão
      nativa Flet (REQUEST_INSTALL_PACKAGES + FileProvider/intent)
