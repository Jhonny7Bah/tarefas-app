"""Constantes compartilhadas: tema de cores, prioridades e repetições.

Identidade visual própria desde a v1.2.0: grafite + verde-esmeralda.
"""

LISTAS_INICIAIS = ["Padrão", "Financeiro", "Pessoal", "Compras", "Trabalho", "Tech"]

# prioridade: 2 = alta, 1 = média, 0 = baixa
PRIORIDADES = {"Alta": 2, "Média": 1, "Baixa": 0}
NOMES_PRIORIDADE = {v: k for k, v in PRIORIDADES.items()}

REPETICOES = {
    "Não repete": None,
    "Diária": "diaria",
    "Semanal": "semanal",
    "Mensal": "mensal",
}
NOMES_REPETICAO = {v: k for k, v in REPETICOES.items()}

MAX_SUBTAREFAS = 10

COR_FUNDO = "#121417"
COR_CARD = "#1e2227"
COR_ACENTO = "#10b981"
COR_TEXTO_SUAVE = "#9ca3af"
COR_ATRASADA = "#f87171"

# Cor da pílula do chip de prioridade (a fonte do chip é sempre branca);
# tons -600 pra ter contraste com o texto branco
COR_BOLINHA_PRIORIDADE = {2: "#dc2626", 1: "#d97706", 0: "#059669"}
