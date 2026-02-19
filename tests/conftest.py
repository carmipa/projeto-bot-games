"""
Configuração do pytest: garante execução na raiz do projeto.
"""
import os
import sys

# Raiz do projeto = diretório que contém main.py (um nível acima de tests/)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if os.path.basename(ROOT) == "tests":
    ROOT = os.path.dirname(ROOT)


def pytest_configure(config):
    """Garante que o pytest rode com CWD na raiz do projeto."""
    if os.getcwd() != ROOT:
        os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
