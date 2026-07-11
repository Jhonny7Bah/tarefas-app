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
- Um commit por feature.

## Como rodar

```bash
flet run main.py          # janela nativa (funciona no Hyprland via XWayland)
flet run --web main.py    # navegador
flet build apk            # APK Android (exige Flutter SDK + JDK 17)
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
- `page.show_drawer()`/`page.close_drawer()` são **async** → handlers `async def`
  com `await`.
- Antes de usar componente novo, validar construção com `.venv/bin/python`.

## Arquitetura

Tudo em `main.py`, em duas camadas separadas de propósito:

1. **Camada de dados** (topo do arquivo): funções puras de SQLite
   (`init_db`, `listar_pendentes`, `adicionar_tarefa`, ...). `init_db()` faz
   migração incremental via `PRAGMA table_info` + `ALTER TABLE` — bancos de
   versões antigas ganham as colunas novas sem perder dados.
2. **Interface** (`main(page)`): estado em dicts (`filtro`, `ultima_concluida`),
   funções `render_*` reconstroem a tela a partir do banco.

## Como testar

Sem framework de teste por enquanto. O padrão usado: script Python no
scratchpad que importa as funções de dados do `main.py` (removendo o
`ft.run(main)`), cria um banco temporário, simula o schema antigo pra validar
a migração e asserta a lógica. Nunca testar contra o `tarefas.db` do projeto.

## Roadmap (do documento do usuário)

- [x] Grupos por data, prioridade, prazo, timestamps, lote, desfazer
- [x] Gaveta lateral com listas, contadores e filtro
- [x] Listas dinâmicas com flag de oculta
- [x] Tela de Concluídas com descrição de conclusão
- [ ] Editar/apagar tarefa (e apagar concluídas)
- [ ] Editar/apagar lista
- [ ] Busca (pendentes + concluídas)
- [ ] Subtarefas (máx. 10 por tarefa)
- [ ] Tarefa em mais de uma lista (N:N)
- [ ] "Repetir" inteligente (reaparece só perto da data)
- [ ] Notificações Android + build do APK (fazer juntos)
