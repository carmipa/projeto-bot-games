"""
Guarda da perda silenciosa de notícia.

O `update_cache_state` corria logo a seguir ao HTTP 200, ANTES de a notícia ser publicada.
Se a publicação falhasse — canal sem permissão, canal apagado, 5xx do Discord — o link não
entrava no dedup, mas o ETag ficava gravado: a varredura seguinte recebia 304, o feed não
devolvia entrada nenhuma e aquelas notícias desapareciam para sempre.

Os dois testes formam um par calibrado: o de sucesso prova que o cache SABE avançar; sem
ele, "o cache está vazio" no teste de falha seria indistinguível de "este código nunca
grava cache nenhum".
"""
import asyncio
import os

import pytest

discord = pytest.importorskip("discord")

import core.scanner as scanner  # noqa: E402
from utils.storage import p, save_json_safe, load_json_safe  # noqa: E402

URL = "https://exemplo-teste.invalid/feed"
ETAG = 'W/"etag-de-teste-123"'

_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Feed de Teste</title>
<item>
  <title>Novo trailer do jogo anunciado</title>
  <link>https://exemplo-teste.invalid/noticia-1</link>
  <description>Um trailer novo.</description>
  <pubDate>{data}</pubDate>
</item>
</channel></rss>
"""


class _RespostaFalsa:
    def __init__(self, status, headers, texto):
        self.status = status
        self.headers = headers
        self._texto = texto

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def text(self, errors=None):
        return self._texto


class _SessaoFalsa:
    """Substitui aiohttp.ClientSession: responde 200 com ETag, sem tocar na rede."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, headers=None, timeout=None):
        from multidict import CIMultiDict
        from datetime import datetime, timezone
        agora = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        return _RespostaFalsa(200, CIMultiDict({"ETag": ETAG}), _FEED_XML.format(data=agora))


def _preparar(monkeypatch, canal):
    """Isola a varredura: uma fonte, um canal, sem rede, sem tradução, sem HTML Monitor."""
    save_json_safe(p("config.json"), {"111": {"channel_id": 999, "language": "pt_BR"}})
    save_json_safe(p("state.json"), {})
    save_json_safe(p("history.json"), [])

    monkeypatch.setattr(scanner, "load_sources", lambda: [URL])
    monkeypatch.setattr(scanner.aiohttp, "ClientSession", _SessaoFalsa)

    async def _sem_traducao(texto, alvo):
        return texto
    monkeypatch.setattr(scanner, "translate_to_target", _sem_traducao)

    async def _sem_html_monitor(bot, config, state, html_hashes):
        return 0
    monkeypatch.setattr(scanner, "_run_html_monitor", _sem_html_monitor)

    async def _validacao_ok(url, allowed_domains=None):
        return True, None
    monkeypatch.setattr(scanner, "validate_url_async", _validacao_ok)

    async def _sem_sleep(_s):
        return None
    monkeypatch.setattr(scanner.asyncio, "sleep", _sem_sleep)

    from unittest.mock import MagicMock
    bot = MagicMock()
    bot.get_channel.return_value = canal
    bot.user = None
    return bot


def _cache_gravado():
    estado = load_json_safe(p("state.json"), {})
    return estado.get("http_cache", {}).get(URL, {})


def test_entrega_ok_grava_o_etag(monkeypatch):
    """CONTROLE POSITIVO: com a publicação a correr bem, o ETag entra no cache."""
    from unittest.mock import AsyncMock, MagicMock
    canal = MagicMock()
    canal.send = AsyncMock()

    bot = _preparar(monkeypatch, canal)
    asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    canal.send.assert_awaited()
    assert _cache_gravado().get("etag") == ETAG, (
        "o cache HTTP deveria ter avançado depois de uma entrega bem-sucedida"
    )


def test_falha_de_entrega_nao_grava_o_etag(monkeypatch):
    """
    CASO REAL: o Discord recusa a publicação (403 Forbidden — bot sem permissão no canal).
    O ETag NÃO pode avançar, senão a próxima varredura leva 304 e a notícia é perdida.
    """
    from unittest.mock import AsyncMock, MagicMock
    canal = MagicMock()
    canal.send = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(status=403), "sem permissão no canal")
    )

    bot = _preparar(monkeypatch, canal)
    asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    canal.send.assert_awaited()
    assert _cache_gravado() == {}, (
        "cache HTTP avançou apesar da falha de entrega: a próxima varredura receberia 304 "
        "e a notícia estaria perdida para sempre"
    )


def test_canal_inexistente_tambem_segura_o_cache(monkeypatch):
    """
    Erro de boa-fé: o canal foi apagado ou o bot foi removido do servidor. `get_channel`
    devolve None, nada é publicado — e isso também é perda, não decisão.
    """
    bot = _preparar(monkeypatch, None)
    asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    assert _cache_gravado() == {}, (
        "cache HTTP avançou mesmo sem canal para publicar"
    )
