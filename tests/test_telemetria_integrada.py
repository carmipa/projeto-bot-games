"""
Telemetria ligada ao fio: uma varredura de verdade tem de deixar registo em `state.json`.

Os testes de `test_telemetria.py` provam a LÓGICA do veredito. Estes provam que ela está
LIGADA — que os contadores do scanner chegam lá, que o registo é persistido e que sobrevive
ao merge com o disco. Lógica correta e desligada é o mesmo que ausente, e foi assim que o
`feeds_failed` viveu meses definido e nunca incrementado.
"""
import asyncio

import pytest

discord = pytest.importorskip("discord")

import core.scanner as scanner  # noqa: E402
from core import telemetria as tel  # noqa: E402
from core.stats import stats  # noqa: E402
from utils.storage import p, save_json_safe, load_json_safe  # noqa: E402

URL = "https://exemplo-telemetria.invalid/feed"

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Novo trailer do jogo</title>
<link>https://exemplo-telemetria.invalid/n1</link>
<description>trailer</description><pubDate>{data}</pubDate></item>
<item><title>Review completa do jogo</title>
<link>https://exemplo-telemetria.invalid/n2</link>
<description>review</description><pubDate>{data}</pubDate></item>
</channel></rss>
"""


class _Resp:
    def __init__(self, status, headers, texto):
        self.status, self.headers, self._t = status, headers, texto

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def text(self, errors=None):
        return self._t


class _Sessao:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, headers=None, timeout=None):
        from datetime import datetime, timezone
        from multidict import CIMultiDict
        agora = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        return _Resp(200, CIMultiDict({"ETag": '"x"'}), _FEED.format(data=agora))


def _preparar(monkeypatch, canal, com_guild=True, com_fontes=True):
    save_json_safe(p("config.json"),
                   {"111": {"channel_id": 999, "language": "pt_BR"}} if com_guild else {})
    save_json_safe(p("state.json"), {})
    save_json_safe(p("history.json"), [])

    monkeypatch.setattr(scanner, "load_sources", lambda: [URL] if com_fontes else [])
    monkeypatch.setattr(scanner.aiohttp, "ClientSession", _Sessao)

    async def _sem_traducao(t, alvo):
        return t
    monkeypatch.setattr(scanner, "translate_to_target", _sem_traducao)

    async def _sem_html(bot, config, state, hashes):
        return 0
    monkeypatch.setattr(scanner, "_run_html_monitor", _sem_html)

    async def _valida(url, allowed_domains=None):
        return True, None
    monkeypatch.setattr(scanner, "validate_url_async", _valida)

    async def _sem_sleep(_s):
        return None
    monkeypatch.setattr(scanner.asyncio, "sleep", _sem_sleep)

    from unittest.mock import MagicMock
    bot = MagicMock()
    bot.get_channel.return_value = canal
    bot.user = None
    return bot


def _saude():
    return tel.ultima(load_json_safe(p("state.json"), {}))


def test_varredura_saudavel_deixa_registo_OK(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    canal = MagicMock()
    canal.send = AsyncMock()

    bot = _preparar(monkeypatch, canal)
    asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    reg = _saude()
    assert reg is not None, "a varredura não deixou registo de saúde nenhum"
    assert reg["veredito"] == tel.VEREDITO_OK, reg["motivo"]
    assert reg["trigger"] == "teste"
    assert reg["fontes_total"] == 1
    # Um item é trailer (publica) e o outro é review (o LIXO_FILTER descarta).
    assert reg["itens_novos"] == 2
    assert reg["itens_publicados"] == 1
    assert reg["itens_filtrados"] == 1
    assert reg["itens_sumidos"] == 0, "invariante de conservação quebrou no fluxo real"


def test_falha_de_entrega_vira_ANOMALIA_no_registo(monkeypatch):
    """O caminho completo: o Discord recusa, e isso chega ao painel como ANOMALIA."""
    from unittest.mock import AsyncMock, MagicMock
    canal = MagicMock()
    canal.send = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(status=403), "sem permissão")
    )

    bot = _preparar(monkeypatch, canal)
    asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    reg = _saude()
    assert reg["veredito"] == tel.VEREDITO_ANOMALIA
    assert reg["entregas_falhadas"] == 1
    assert "entregas falharam" in reg["motivo"]


def test_sem_guild_configurada_tambem_deixa_registo(monkeypatch):
    """
    Saída antecipada é a ausência mais grave: o bot nem tentou. Sem registo, o `/status`
    mostraria o veredito da varredura anterior — possivelmente um OK de dias atrás.
    """
    bot = _preparar(monkeypatch, None, com_guild=False)
    asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    reg = _saude()
    assert reg is not None, "saída antecipada não registou nada"
    assert reg["veredito"] == tel.VEREDITO_ANOMALIA


def test_catalogo_vazio_deixa_registo_de_anomalia(monkeypatch):
    """O sources.json congelado ou ilegível no Docker chega aqui."""
    from unittest.mock import AsyncMock, MagicMock
    canal = MagicMock()
    canal.send = AsyncMock()

    bot = _preparar(monkeypatch, canal, com_fontes=False)
    asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    reg = _saude()
    assert reg is not None
    assert reg["veredito"] == tel.VEREDITO_ANOMALIA
    assert "sources.json" in reg["motivo"]


def test_feeds_failed_deixou_de_ser_contador_morto(monkeypatch):
    """
    `stats.feeds_failed` esteve definido e nunca incrementado — um campo que sempre dizia
    `0`, indistinguível de "nada falhou". Aqui prova-se que ele se mexe.
    """
    from unittest.mock import AsyncMock, MagicMock

    class _SessaoQueFalha(_Sessao):
        def get(self, url, headers=None, timeout=None):
            from multidict import CIMultiDict
            return _Resp(403, CIMultiDict({}), "")

    canal = MagicMock()
    canal.send = AsyncMock()
    bot = _preparar(monkeypatch, canal)
    monkeypatch.setattr(scanner.aiohttp, "ClientSession", _SessaoQueFalha)

    antes = stats.feeds_failed
    asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    assert stats.feeds_failed > antes, "feeds_failed continua a não ser alimentado"
    assert _saude()["fontes_com_erro"] == 1


def test_historico_acumula_entre_varreduras(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    canal = MagicMock()
    canal.send = AsyncMock()

    bot = _preparar(monkeypatch, canal)
    for _ in range(3):
        asyncio.run(scanner.run_scan_once(bot, trigger="teste"))

    estado = load_json_safe(p("state.json"), {})
    assert len(estado[tel.CHAVE_ESTADO]["historico"]) == 3
    assert len(tel.vereditos_recentes(estado)) == 3
