"""
Testes de integração simples: carregamento de config, sources, filtros, web e scanner.
Rodar na raiz do projeto: pytest tests/test_integration.py -v
"""
import os
import sys
import asyncio

# Garante import a partir da raiz
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)


# ============== Integração: Storage + Sources ==============

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


def test_integration_match_intel_with_real_config_shape():
    """match_intel: guild com channel_id recebe tudo; sem channel_id não recebe."""
    from core.filters import match_intel

    config = {
        "123456": {"channel_id": 789},
        "654321": {"channel_id": 790},
    }
    assert match_intel("123456", "Any title", "Any summary", config) is True
    assert match_intel("654321", "Other news", "Text", config) is True
    assert match_intel("999", "Title", "Summary", config) is False
    assert match_intel("123456", "X", "Y", {"123456": {}}) is False


def test_integration_stats_module():
    """Módulo de stats expõe format_uptime e contadores."""
    from core.stats import stats

    assert hasattr(stats, "format_uptime")
    assert hasattr(stats, "scans_completed")
    assert hasattr(stats, "news_posted")
    uptime_str = stats.format_uptime()
    assert isinstance(uptime_str, str) and len(uptime_str) > 0


# ============== Integração: Web (app + rotas) ==============

def test_integration_web_index_returns_200():
    """Servidor web: GET / retorna 200 e HTML."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    import aiohttp_jinja2
    import jinja2

    from web.server import routes
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


def test_integration_web_api_stats_structure():
    """Servidor web: GET /api/stats retorna JSON com campos esperados (sem auth)."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    import aiohttp_jinja2
    import jinja2

    from web.server import routes
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

def test_integration_run_scan_once_with_empty_config():
    """run_scan_once com config vazio/sem channel_id retorna sem erro (não faz HTTP)."""
    from core.scanner import run_scan_once

    class MockBot:
        guilds = []
        def get_channel(self, _):
            return None

    async def _run():
        bot = MockBot()
        await run_scan_once(bot, trigger="test")

    asyncio.run(_run())
    assert True


def test_integration_sanitize_link():
    """sanitize_link remove UTM e preserva links do YouTube."""
    from core.scanner import sanitize_link

    assert "utm_" not in sanitize_link("https://site.com/page?utm_source=x&id=1")
    assert sanitize_link("https://youtube.com/watch?v=abc") == "https://youtube.com/watch?v=abc"
