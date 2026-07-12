# Gerenciador de Tarefas

App Android de gerenciamento de tarefas escrito em **Python + Flet** (o Flet
renderiza com Flutter por baixo, então o visual é Material Design nativo).
A especificação vem do documento "Ideia de App Tarefa" do usuário, inspirado
no app de referência (Mi Notes/Tarefas, tema azul-marinho escuro).

## Decisões do projeto

- **100% offline nesta versão.** Persistência só em SQLite local (`tarefas.db`).
  Não implementar banco online nem sync.
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
flet run main.py                # janela nativa (funciona no Hyprland via XWayland)
flet run --web main.py          # navegador
flet build apk --split-per-abi  # APKs Android (o flet baixa o próprio Flutter;
                                #  precisa de ANDROID_HOME=/opt/android-sdk e JDK 17)
./release.sh "o que mudou"      # build + release no GitHub num comando
```

Usar sempre o Python do projeto: `.venv/bin/python` (Python 3.14, Flet 0.85.3).

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

**Estilo: PEP 8, verificado com ruff** (config no pyproject: linha até 99,
regras E/W/F/I/N). Rodar antes de commitar:

```bash
.venv/bin/ruff check .
```

## Como testar

Sem framework de teste por enquanto. O padrão usado: script Python no
scratchpad que importa as funções de dados do `main.py` (removendo o
`ft.run(main)`), cria um banco temporário, simula o schema antigo pra validar
a migração e asserta a lógica. Nunca testar contra o `tarefas.db` do projeto.

## Ferramentas instaladas pro build do APK (jul/2026)

Instaladas só pra gerar o APK — anotado pra desinstalar no futuro se quiser:

```bash
# Pacotes (AUR, via yay):
yay -Rns jdk17-openjdk android-sdk-cmdline-tools-latest android-sdk-platform-tools
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
- [ ] Notificações Android (plugin nativo + rebuild) — ADIADO a pedido do
      usuário; é o único item restante do documento original
- [ ] (Opcional, junto com notificações) atualização estilo Snaptube:
      download e instalação dentro do app, sem navegador — exige extensão
      nativa Flet (REQUEST_INSTALL_PACKAGES + FileProvider/intent)
