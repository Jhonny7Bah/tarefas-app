"""Roda a suíte inteira: .venv/bin/python testes/roda_tudo.py

Todos os testes usam bancos temporários e servidor falso em memória;
nenhum toca no banco do projeto, nos dados reais ou no Supabase.
"""

import subprocess
import sys
from pathlib import Path

pasta = Path(__file__).resolve().parent
falhas = 0
for teste in sorted(pasta.glob("testa_*.py")):
    resultado = subprocess.run([sys.executable, str(teste)], capture_output=True)
    ok = resultado.returncode == 0
    print(("PASSOU" if ok else "FALHOU"), "-", teste.name)
    if not ok:
        falhas += 1
        print(resultado.stdout.decode(), resultado.stderr.decode())

sys.exit(1 if falhas else 0)
