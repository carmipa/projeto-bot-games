"""
Configuração do pytest: execução na raiz do projeto e ISOLAMENTO dos dados de produção.

Motivo do isolamento (auditoria 2026-08-01): `test_integration_run_scan_once_with_empty_config`
rodava com o `config.json` real — que tem `channel_id` configurado — e portanto executava uma
varredura de verdade: baixava as 69 fontes, casava dezenas de notícias reais e gravava
`state.json`/`history.json` do bot. O estrago não era só sujeira: `update_cache_state()` grava
ETag/Last-Modified de todo feed baixado, mesmo sem postar nada. Como o bot mockado não tem canal,
nada era postado, mas a varredura real seguinte recebia 304 e perdia essas notícias para sempre.
"""
import json
import os
import shutil
import sys
import tempfile

import pytest

# Raiz do projeto = diretório que contém main.py (um nível acima de tests/)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if os.path.basename(ROOT) == "tests":
    ROOT = os.path.dirname(ROOT)

# Arquivos que utils.storage.p() redireciona para DATA_DIR
_DATA_FILES = ("config.json", "state.json", "history.json", "sources.json")


def pytest_configure(config):
    """Garante que o pytest rode com CWD na raiz do projeto."""
    if os.getcwd() != ROOT:
        os.chdir(ROOT)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)


@pytest.fixture(scope="session", autouse=True)
def _isola_dados_de_producao():
    """
    PROPÓSITO DE NEGÓCIO: garantir que rodar a suíte nunca altere o estado operacional do
    bot. `state.json` guarda o dedup e o cache HTTP que decidem quais notícias já saíram;
    corrompê-los provoca repostagem em massa ou perda silenciosa de notícias.

    INVARIANTES DO DOMÍNIO: durante toda a sessão de testes, `DATA_DIR` aponta para um
    diretório temporário. Como `utils.storage.p()` resolve config/state/history/sources por
    `DATA_DIR`, nenhuma escrita alcança a raiz do projeto. O `sources.json` real é copiado
    para lá (os testes precisam do catálogo verdadeiro), mas `config.json` nasce VAZIO — sem
    guild configurada, `run_scan_once` sai no primeiro portão e não faz requisição alguma.

    COMPORTAMENTO EM CASO DE FALHA: se o diretório temporário não puder ser criado, a
    exceção do `tempfile` sobe e a sessão de testes aborta — de propósito. Rodar sem
    isolamento é pior do que não rodar. No fim da sessão o diretório é removido e o valor
    anterior de `DATA_DIR` é restaurado (ou removido, se não existia).
    """
    anterior = os.environ.get("DATA_DIR")
    tmp = tempfile.mkdtemp(prefix="gamebot-testes-")

    origem_sources = os.path.join(ROOT, "sources.json")
    if os.path.isfile(origem_sources):
        shutil.copy2(origem_sources, os.path.join(tmp, "sources.json"))
    else:
        with open(os.path.join(tmp, "sources.json"), "w", encoding="utf-8") as f:
            json.dump({"rss_feeds": [], "youtube_feeds": []}, f)

    with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as f:
        json.dump({}, f)
    with open(os.path.join(tmp, "state.json"), "w", encoding="utf-8") as f:
        json.dump({}, f)
    with open(os.path.join(tmp, "history.json"), "w", encoding="utf-8") as f:
        json.dump([], f)

    os.environ["DATA_DIR"] = tmp
    try:
        yield tmp
    finally:
        if anterior is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = anterior
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def sem_rede(monkeypatch):
    """
    Falha o teste se alguém abrir uma sessão HTTP. Usado nos testes que afirmam
    'não faz rede' — a afirmação passa a ser verificada, não confiada.
    """
    import aiohttp

    def _proibido(*args, **kwargs):
        raise AssertionError(
            "Este teste abriu uma aiohttp.ClientSession. Testes da suíte não podem "
            "fazer requisições de rede."
        )

    monkeypatch.setattr(aiohttp, "ClientSession", _proibido)
    return True
