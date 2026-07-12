"""
Testes do dispatch de alertas do HTML Monitor (_run_html_monitor), extraído de run_scan_once.
Usa um bot/canal mockados e monkeypatch de check_official_sites (nenhuma rede). Requer discord.py.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

discord = pytest.importorskip("discord")
import core.scanner as scanner  # noqa: E402


def _make_bot_with_channel():
    channel = MagicMock()
    channel.send = AsyncMock()
    bot = MagicMock()
    bot.get_channel.return_value = channel
    return bot, channel


def test_dispatch_sends_alert_on_update(monkeypatch):
    bot, channel = _make_bot_with_channel()
    config = {"111": {"channel_id": 999}}
    state = {"html_hashes": {}}

    async def fake_check(current_state, full_state=None):
        return (
            [{"title": "🔄 Update: Nintendo", "link": "https://nintendo.com/", "summary": ""}],
            {"https://nintendo.com/": "hashnovo"},
        )

    monkeypatch.setattr(scanner, "check_official_sites", fake_check)

    sent = asyncio.run(scanner._run_html_monitor(bot, config, state, {}))

    assert sent == 1
    channel.send.assert_awaited_once()
    # a mensagem enviada carrega o título do update
    args, kwargs = channel.send.call_args
    assert "Nintendo" in args[0]
    assert state["html_hashes"] == {"https://nintendo.com/": "hashnovo"}


def test_dispatch_no_update_sends_nothing(monkeypatch):
    bot, channel = _make_bot_with_channel()
    config = {"111": {"channel_id": 999}}

    async def fake_check(current_state, full_state=None):
        return ([], {"https://nintendo.com/": "igual"})

    monkeypatch.setattr(scanner, "check_official_sites", fake_check)

    sent = asyncio.run(scanner._run_html_monitor(bot, config, {"html_hashes": {}}, {}))
    assert sent == 0
    channel.send.assert_not_awaited()


def test_dispatch_skips_guild_without_channel(monkeypatch):
    bot, channel = _make_bot_with_channel()
    config = {"111": {}}  # sem channel_id

    async def fake_check(current_state, full_state=None):
        return ([{"title": "x", "link": "https://a.com/", "summary": ""}], {})

    monkeypatch.setattr(scanner, "check_official_sites", fake_check)

    sent = asyncio.run(scanner._run_html_monitor(bot, config, {"html_hashes": {}}, {}))
    assert sent == 0
    channel.send.assert_not_awaited()
