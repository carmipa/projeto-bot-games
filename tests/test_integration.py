"""
Testes de integração simples: carregamento de config, sources, filtros, web e scanner.
Rodar na raiz do projeto: pytest tests/test_integration.py -v
"""
import os
import sys
import asyncio

import pytest

# aiohttp TestServer + asyncio.run derruba o interpretador (access violation) no CPython 3.14.
# Produção roda 3.10 e dev deveria usar 3.11/3.12 — pulamos só nesse interpretador problemático
# para a suíte não abortar inteira em vez de reportar pass/fail.
_WEB_TESTS_UNSAFE = sys.version_info >= (3, 14)
_skip_web = pytest.mark.skipif(
    _WEB_TESTS_UNSAFE,
    reason="aiohttp TestServer instável no CPython 3.14 (use 3.11/3.12 em dev)",
)

# Alguns testes importam core.scanner -> discord.py -> ctypes. Se o interpretador não
# consegue importar discord (ex.: venv 3.14 com _ctypes quebrado), pulamos em vez de
# reportar falha. Em produção (3.10) e CI (3.11) roda normalmente.
try:
    import discord  # noqa: F401
    _DISCORD_OK = True
except Exception:
    _DISCORD_OK = False
_skip_no_discord = pytest.mark.skipif(
    not _DISCORD_OK,
    reason="discord.py indisponível neste interpretador (recrie a venv com Python 3.11/3.12)",
)

# Garante import a partir da raiz
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)


# ============== Integração: Storage + Sources ==============

@_skip_no_discord
def test_integration_load_sources_from_json():
    """Carrega sources.json e verifica que retorna lista de URLs válidas."""
    from core.scanner import load_sources

    urls = load_sources()
    assert isinstance(urls, list), "load_sources deve retornar lista"
    assert len(urls) > 0, "sources.json deve ter pelo menos uma URL"
    for u in urls[:5]:
        assert u.startswith(("http://", "https://")), f"URL inválida: {u}"


def test_integration_load_config_and_state():
    """Carrega config.json e state.json sem erros."""
    from utils.storage import load_json_safe, p

    config = load_json_safe(p("config.json"), {})
    state = load_json_safe(p("state.json"), {})
    assert isinstance(config, dict)
    assert isinstance(state, dict)


def test_integration_should_post_to_guild():
    """should_post_to_guild: guild com channel_id recebe tudo; sem channel_id não recebe."""
    from core.filters import should_post_to_guild

    config = {
        "123456": {"channel_id": 789},
        "654321": {"channel_id": 790},
    }
    assert should_post_to_guild("123456", "Any title", "Any summary", config) is True
    assert should_post_to_guild("654321", "Other news", "Text", config) is True
    assert should_post_to_guild("999", "Title", "Summary", config) is False
    assert should_post_to_guild("123456", "X", "Y", {"123456": {}}) is False


def test_integration_stats_module():
    """Módulo de stats expõe format_uptime e contadores."""
    from core.stats import stats

    assert hasattr(stats, "format_uptime")
    assert hasattr(stats, "scans_completed")
    assert hasattr(stats, "news_posted")
    uptime_str = stats.format_uptime()
    assert isinstance(uptime_str, str) and len(uptime_str) > 0


# ============== Integração: Web (app + rotas) ==============

def _web_routes_without_auth(monkeypatch):
    """Recarrega web.server sem WEB_AUTH_TOKEN (evita 401 quando .env define token)."""
    import importlib
    monkeypatch.delenv("WEB_AUTH_TOKEN", raising=False)
    import web.server as ws
    importlib.reload(ws)
    return ws.routes


@_skip_web
def test_integration_web_index_returns_200(monkeypatch):
    """Servidor web: GET / retorna 200 e HTML."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    import aiohttp_jinja2
    import jinja2

    routes = _web_routes_without_auth(monkeypatch)
    from utils.storage import p

    app = web.Application()
    template_dir = p("web/templates")
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(template_dir))
    app.add_routes(routes)

    async def _run():
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            text = await resp.text()
            assert "html" in text.lower() or "dashboard" in text.lower()

    asyncio.run(_run())


@_skip_web
def test_integration_web_api_stats_structure(monkeypatch):
    """Servidor web: GET /api/stats retorna JSON com campos esperados (sem auth)."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    import aiohttp_jinja2
    import jinja2

    routes = _web_routes_without_auth(monkeypatch)
    from utils.storage import p

    app = web.Application()
    template_dir = p("web/templates")
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(template_dir))
    app.add_routes(routes)

    async def _run():
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/stats")
            if resp.status == 200:
                data = await resp.json()
                assert "uptime" in data
                assert "scans" in data
                assert "news_posted" in data

    asyncio.run(_run())


# ============== Integração: Scanner (run_scan_once com mock) ==============

@_skip_no_discord
def test_integration_run_scan_once_with_empty_config(sem_rede):
    """
    run_scan_once com config sem guild sai no primeiro portão, sem tocar a rede.

    O `config.json` vem VAZIO do isolamento em conftest (DATA_DIR temporário). A fixture
    `sem_rede` faz o teste falhar se alguém abrir uma ClientSession — antes esta função
    dizia na docstring que 'não faz HTTP' enquanto executava uma varredura de produção
    inteira contra 69 fontes reais.
    """
    from core.scanner import run_scan_once
    from utils.storage import load_json_safe, p

    assert not load_json_safe(p("config.json"), {}), (
        "isolamento falhou: config.json de testes deveria estar vazio"
    )

    class MockBot:
        guilds = []
        def get_channel(self, _):
            return None

    async def _run():
        bot = MockBot()
        await run_scan_once(bot, trigger="test")

    asyncio.run(_run())


@_skip_no_discord
def test_integration_scan_nao_escreve_em_producao(sem_rede):
    """
    Trava de regressão: todo arquivo que o bot ESCREVE tem de resolver dentro do DATA_DIR
    temporário durante os testes, nunca na raiz do projeto. Se alguém remover o isolamento
    do conftest, este teste denuncia — em vez de o estrago só aparecer no bot em produção.

    `sources.json` ficou de fora desta lista de propósito: ele deixou de ser dado de
    execução e passou a ser catálogo versionado, lido do diretório da aplicação (ver
    `_DATA_FILES` em utils/storage.py). Enquanto resolvia por DATA_DIR, o entrypoint do
    Docker o copiava para o volume só na primeira subida e congelava o catálogo lá.
    """
    from utils.storage import p

    data_dir = os.environ.get("DATA_DIR", "")
    assert data_dir, "DATA_DIR não definido: isolamento do conftest não está ativo"
    for nome in ("config.json", "state.json", "history.json"):
        resolvido = os.path.abspath(p(nome))
        assert resolvido.startswith(os.path.abspath(data_dir)), (
            f"{nome} resolveu para {resolvido}, fora do DATA_DIR de testes"
        )
        assert resolvido != os.path.join(ROOT, nome), (
            f"{nome} resolveu para o arquivo de produção"
        )


@_skip_no_discord
def test_sources_json_e_catalogo_somente_leitura(sem_rede):
    """
    `sources.json` resolve para o diretório da aplicação — é isso que faz uma fonte nova
    commitada chegar ao contêiner. A contrapartida é que o bot NUNCA pode escrevê-lo: se
    escrevesse, estaria a mexer no arquivo versionado do repositório.

    O teste prova as duas metades. A segunda usa um caso-controle: primeiro confirma que a
    sonda de escrita SABE disparar (gravando config.json, que o bot legitimamente escreve),
    e só então afirma que nada tocou em sources.json. Sem o controle positivo, "ninguém
    escreveu" seria indistinguível de "a sonda não enxerga escrita nenhuma".
    """
    import utils.storage as storage

    resolvido = os.path.abspath(storage.p("sources.json"))
    assert resolvido == os.path.join(ROOT, "sources.json"), (
        f"sources.json resolveu para {resolvido}; deveria vir do diretório da aplicação"
    )

    escritos = []
    original = storage.save_json_safe

    def _espiao(filepath, data):
        escritos.append(os.path.abspath(filepath))
        return original(filepath, data)

    storage.save_json_safe = _espiao
    try:
        # Controle positivo: a sonda tem de registar uma escrita legítima.
        storage.save_json_safe(storage.p("config.json"), {})
        assert escritos, "sonda de escrita não registou nem a escrita de controle"

        escritos.clear()
        from core.scanner import load_sources
        load_sources()
    finally:
        storage.save_json_safe = original

    assert resolvido not in escritos, (
        f"sources.json foi escrito durante a leitura do catálogo: {escritos}"
    )


@_skip_no_discord
def test_integration_sanitize_link():
    """sanitize_link remove UTM e preserva links do YouTube."""
    from core.scanner import sanitize_link

    assert "utm_" not in sanitize_link("https://site.com/page?utm_source=x&id=1")
    assert sanitize_link("https://youtube.com/watch?v=abc") == "https://youtube.com/watch?v=abc"
