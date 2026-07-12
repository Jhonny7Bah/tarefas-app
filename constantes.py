"""Constantes compartilhadas: tema de cores, prioridades e repetições."""

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

COR_PRIORIDADE = {2: "#ef4444", 1: "#f59e0b", 0: "#475569"}
COR_FUNDO = "#0f2540"
COR_CARD = "#16335c"
COR_AZUL = "#1e6fd0"
COR_TEXTO_SUAVE = "#94a3b8"
COR_ATRASADA = "#f87171"
