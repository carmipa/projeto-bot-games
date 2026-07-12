"""
Testes da construção de mensagem de notícia (build_news_message), extraída de run_scan_once.
Cobre a montagem de embed/content/view — antes sem nenhum teste. Requer discord.py.
"""
from types import SimpleNamespace

import pytest

discord = pytest.importorskip("discord")
from core.scanner import build_news_message  # noqa: E402

_BOT = SimpleNamespace(user=None)  # bot.user None -> icon_url None (caminho simples)
_ENTRY = SimpleNamespace()          # sem media_thumbnail


def test_article_builds_embed_no_content():
    content, embed, view = build_news_message(
        _BOT, _ENTRY,
        t_translated="Novo jogo anunciado",
        s_translated="Resumo da noticia",
        link="https://ign.com/artigo",
        embed_color=discord.Color.red(),
        pub_dt=None,
        entry_image_url=None,
        entry_video_url=None,
        is_media=False,
        target_lang="pt_BR",
    )
    assert content is None
    assert isinstance(embed, discord.Embed)
    assert embed.title == "Novo jogo anunciado"
    assert "Resumo da noticia" in embed.description
    assert "Postado em" in embed.description
    assert embed.url == "https://ign.com/artigo"
    # botões: Leia Mais + WhatsApp + E-mail
    labels = [i.label for i in view.children]
    assert "Leia Mais" in labels and "WhatsApp" in labels and "E-mail" in labels


def test_media_builds_content_no_embed():
    content, embed, view = build_news_message(
        _BOT, _ENTRY,
        t_translated="Trailer oficial",
        s_translated="assista",
        link="https://youtube.com/watch?v=abc",
        embed_color=discord.Color.red(),
        pub_dt=None,
        entry_image_url=None,
        entry_video_url=None,
        is_media=True,
        target_lang="pt_BR",
    )
    assert embed is None
    assert content is not None
    assert content.startswith("📺")
    assert "https://youtube.com/watch?v=abc" in content


def test_title_truncated_to_256():
    long_title = "x" * 400
    _, embed, _ = build_news_message(
        _BOT, _ENTRY,
        t_translated=long_title,
        s_translated="s",
        link="https://ex.com/a",
        embed_color=discord.Color.red(),
        pub_dt=None,
        entry_image_url=None,
        entry_video_url=None,
        is_media=False,
        target_lang="pt_BR",
    )
    assert len(embed.title) == 256


def test_video_button_added_when_direct_video():
    _, _, view = build_news_message(
        _BOT, _ENTRY,
        t_translated="Materia com video",
        s_translated="s",
        link="https://ex.com/a",
        embed_color=discord.Color.red(),
        pub_dt=None,
        entry_image_url=None,
        entry_video_url="https://ex.com/video.mp4",
        is_media=False,
        target_lang="pt_BR",
    )
    labels = [i.label for i in view.children]
    assert "Assistir vídeo" in labels
