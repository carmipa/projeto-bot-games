"""
Scanner module - Feed fetching and processing logic.
"""
import hashlib
import ssl
import asyncio
import logging
import re
import feedparser
import aiohttp
import certifi
from datetime import datetime, timedelta, timezone
from dateutil import parser as dtparser
from typing import List, Set, Tuple, Dict, Any
from urllib.parse import urlparse, urlunparse
from urllib.parse import urljoin
import time
import os
import random

# User-Agent de navegador real é obtido via utils.http.get_robust_headers()

import discord
from discord.ext import tasks

from settings import (
    BROWSER_USER_AGENTS,
    FEED_FETCH_JITTER_MAX,
    FEED_FETCH_JITTER_MIN,
    FEED_TIMEOUT_SECONDS,
    ENABLE_OG_IMAGE_FALLBACK,
    LOOP_MINUTES,
    MAX_CONCURRENT_FEEDS,
    MAX_ENTRIES_PER_FEED,
    MAX_NEWS_AGE_DAYS,
    OG_IMAGE_ALLOWED_DOMAINS,
    OG_IMAGE_MAX_BYTES,
    OG_IMAGE_TIMEOUT_SECONDS,
    REQUIRE_ENTRY_DATE,
    RSS_MAX_RETRIES,
    RSS_RETRY_BACKOFF_BASE,
    STRICT_GENERIC_YOUTUBE,
)
from utils.storage import p, load_json_safe, save_json_safe
from utils.html import clean_html
from utils.cache import get_cache_headers, update_cache_state
from utils.translator import translate_to_target, t
from utils.security import validate_url_async, sanitize_log_message, imagem_publicavel
from utils.http import get_robust_headers
from core.stats import stats
from core import telemetria
from utils.translator import degradacoes_totais
from core.filters import should_post_to_guild, should_skip_by_content
from core.html_monitor import check_official_sites
from utils.discord_link_buttons import (
    LINK_BUTTON_URL_MAX,
    gmail_compose_button_url,
    safe_https_button_url,
    whatsapp_share_button_url,
)

log = logging.getLogger("GameBot")

# Lock global para impedir varreduras simultâneas
scan_lock = asyncio.Lock()
_runtime_profile_logged = False

# Máximo de links mantidos no dedup por feed (limita o crescimento de state.json sem
# zerar tudo — o wipe total antigo causava repost em massa a cada 7 dias)
MAX_DEDUP_PER_FEED = 500

GENERIC_YOUTUBE_HINTS = (
    "youtube.com/feeds/videos.xml?channel_id=",
    "youtube.com/@",
    "youtube.com/channel/",
)
GAME_CORE_TITLE_TERMS = (
    "game",
    "games",
    "trailer",
    "announcement",
    "revealed",
    "reveal",
    "launch",
    "dlc",
    "expansion",
    "patch",
    "update",
    "steam",
    "xbox",
    "playstation",
    "nintendo",
    "switch",
    "ps5",
    "pc",
)


# =========================================================
# HISTORY MANAGEMENT
# =========================================================

def load_history() -> Tuple[List[str], Set[str]]:
    """Carrega history.json e devolve (lista, set) para dedupe rápido."""
    h = load_json_safe(p("history.json"), [])
    if not isinstance(h, list):
        log.warning("history.json inválido. Reiniciando histórico.")
        h = []
    
    # Filtra apenas strings para evitar erros
    h = [x for x in h if isinstance(x, str)]
    return h, set(h)


def save_history(history_list: List[str], limit: int = 2000) -> None:
    """Mantém histórico limitado para não crescer infinito."""
    save_json_safe(p("history.json"), history_list[-limit:])


# =========================================================
# SOURCE MANAGEMENT
# =========================================================

def load_sources() -> List[str]:
    """
    Carrega feeds de sources.json.
    Retorna lista única de URLs http(s).
    """
    sources_raw = load_json_safe(p("sources.json"), [])
    urls: List[str] = []

    def _add(u: Any):
        if isinstance(u, str):
            u = u.strip()
            if u.startswith(("http://", "https://")):
                urls.append(u)

    if isinstance(sources_raw, dict):
        for key in ("rss_feeds", "youtube_feeds", "official_sites", "feeds", "sources", "urls"):
            val = sources_raw.get(key, [])
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        _add(item)
                    elif isinstance(item, dict):
                        _add(item.get("url") or item.get("link"))

    elif isinstance(sources_raw, list):
        for item in sources_raw:
            if isinstance(item, str):
                _add(item)
            elif isinstance(item, dict):
                _add(item.get("url") or item.get("link"))

    # remove duplicados mantendo ordem
    seen = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# -----------------------------------------
# YouTube @ / channel → feed RSS (channel_id)
# -----------------------------------------

def _is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _is_youtube_feed_url(url: str) -> bool:
    return "youtube.com/feeds/videos.xml" in url and "channel_id=" in url


def _youtube_channel_id_from_url(url: str) -> str | None:
    """Extrai channel_id (UC...) de URL do tipo /channel/UC..."""
    m = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_-]{22})", url)
    return m.group(1) if m else None


def _load_youtube_feed_map() -> Dict[str, str]:
    """Carrega o mapeamento @username -> feed RSS do sources.json (poupa requisições)."""
    sources = load_json_safe(p("sources.json"), {})
    return sources.get("youtube_feed_map") or {}


async def get_yt_rss(
    session: aiohttp.ClientSession,
    url: str,
    cache: Dict[str, str],
    timeout: aiohttp.ClientTimeout,
    feed_map: Dict[str, str] | None = None,
) -> str:
    """
    Converte URL de canal YouTube (@username ou /channel/UC...) para o feed RSS oficial.
    Se o ID estiver mapeado em sources.json (youtube_feed_map), usa o link XML direto para poupar recursos.
    Caso contrário, faz request à página e extrai o channelId do código fonte.
    """
    if not _is_youtube_url(url):
        return url
    if _is_youtube_feed_url(url):
        return url

    # 1. Mapa no JSON: usa feed direto sem fazer request
    if feed_map is None:
        feed_map = _load_youtube_feed_map()
    if url in feed_map:
        log.debug(f"YouTube: usando feed do mapa para {url}")
        return feed_map[url]

    # 2. URL já é /channel/UC...: monta feed
    channel_id = _youtube_channel_id_from_url(url)
    if channel_id:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    # 3. Cache em memória (state)
    if url in cache:
        return cache[url]

    # 4. Fallback: request à página e extração do channelId do HTML
    return await _fetch_youtube_channel_id_from_page(session, url, cache, timeout)


# Âncoras para extrair o channel_id DA PRÓPRIA página do canal, em ordem de confiança.
# A busca ingênua por "channelId" pega a PRIMEIRA ocorrência do HTML, que costuma ser um
# canal recomendado/vinculado da barra lateral — o bot acabava assinando o canal errado
# (medido: @PlayStation -> "Marathon", @Xbox -> "Forza", @SEGA -> "atlustube").
# Estas três âncoras identificam a página, não os vizinhos dela.
_YT_ID_PATTERNS = (
    # 1. <link rel="alternate" type="application/rss+xml" href="...channel_id=UC...">
    #    O próprio YouTube declara aqui o feed canônico da página. Fonte mais confiável.
    re.compile(
        r'<link[^>]+rel=["\']alternate["\'][^>]+href=["\'][^"\']*channel_id=(UC[A-Za-z0-9_-]{22})',
        re.IGNORECASE,
    ),
    # 2. "externalId" no ytInitialData é o ID do canal exibido, não dos recomendados.
    re.compile(r'"externalId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"'),
    # 3. <link rel="canonical" href=".../channel/UC...">
    re.compile(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'][^"\']*/channel/(UC[A-Za-z0-9_-]{22})',
        re.IGNORECASE,
    ),
)


async def _fetch_youtube_channel_id_from_page(
    session: aiohttp.ClientSession,
    url: str,
    cache: Dict[str, str],
    timeout: aiohttp.ClientTimeout,
) -> str:
    """
    PROPÓSITO DE NEGÓCIO: converter a URL amigável de um canal do YouTube (@handle) no
    endereço do feed Atom correspondente, para que o bot consiga acompanhar os trailers e
    anúncios daquele estúdio. É o caminho de recurso — o normal é o `youtube_feed_map` do
    sources.json já trazer o par pronto, sem gastar requisição.

    INVARIANTES DO DOMÍNIO: o channel_id devolvido tem de ser o do canal DA PÁGINA pedida.
    Só valem âncoras que identificam a própria página (link alternate do feed, externalId,
    link canonical); qualquer ocorrência solta de "channelId" no HTML pode ser um canal
    recomendado e é proibida como fonte. O resultado só vai para o cache quando extraído.

    COMPORTAMENTO EM CASO DE FALHA: devolve a URL original inalterada (nunca levanta) em
    qualquer um destes casos — página com status != 200, erro de rede/timeout, ou nenhuma
    âncora encontrada. A URL original vira um feed sem entradas mais à frente, que a
    varredura contabiliza e reporta como fonte problemática.
    """
    try:
        headers = get_robust_headers() # Simula navegador real
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                log.warning(
                    f"YouTube resolve: página do canal {url} retornou {resp.status} "
                    f"(handle provavelmente já não existe). Mantendo URL original."
                )
                return url
            html = await resp.text(errors="ignore")
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning(f"YouTube resolve: falha ao acessar {url}: {e}. Mantendo URL original.")
        return url

    channel_id = None
    for pattern in _YT_ID_PATTERNS:
        m = pattern.search(html)
        if m:
            channel_id = m.group(1)
            break

    if channel_id:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        cache[url] = feed_url
        log.info(f"YouTube: @ resolvido para feed RSS: {url} -> {feed_url}")
        return feed_url

    log.warning(
        f"YouTube: nenhuma âncora de channel_id encontrada em {url}. Mantendo URL original "
        f"(o feed virá vazio). Considere fixar o par no youtube_feed_map do sources.json."
    )
    return url


async def resolve_youtube_urls(
    session: aiohttp.ClientSession,
    urls: List[str],
    state: Dict[str, Any],
    timeout: aiohttp.ClientTimeout,
) -> List[str]:
    """Resolve todas as URLs de canal YouTube (@ ou /channel/) para URLs de feed RSS (concorrente)."""
    cache = state.setdefault("youtube_feed_cache", {})
    feed_map = _load_youtube_feed_map()
    sem = asyncio.Semaphore(5)

    async def _resolve(u: str) -> str:
        if _is_youtube_url(u) and not _is_youtube_feed_url(u):
            async with sem:
                return await get_yt_rss(session, u, cache, timeout, feed_map)
        return u

    return list(await asyncio.gather(*[_resolve(u) for u in urls]))


def sanitize_link(link: str) -> str:
    """
    Remove parâmetros de rastreamento (utm_, etc) para evitar duplicação no histórico.
    Mantém parâmetros úteis (id, v, article).
    """
    try:
        parsed = urlparse(link)
        # Se for YouTube, não mexe na query string (pode quebrar v=...)
        if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
            return link
            
        # Filtra query params
        q_pairs = parsed.query.split('&')
        cleaned_pairs = [
            pair for pair in q_pairs 
            if not pair.startswith(('utm_', 'ref', 'source', 'fbclid', 'timestamp'))
            and pair # remove vazios
        ]
        new_query = '&'.join(cleaned_pairs)
        
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
    except Exception as e:
        log.debug(f"Erro ao sanitizar link '{link[:50]}...': {e}. Retornando link original.")
        return link


def should_skip_generic_youtube_false_positive(source_url: str, title: str, link: str) -> bool:
    """
    Para fontes YouTube genéricas, exige sinal semântico no título para reduzir falso-positivo.
    """
    if not STRICT_GENERIC_YOUTUBE:
        return False
    if "youtube.com" not in source_url:
        return False
    title_lower = (title or "").lower()
    if any(term in title_lower for term in GAME_CORE_TITLE_TERMS):
        return False
    # Mantém permissivo para vídeos com URL já claramente de jogos em domínios fora YouTube
    if "youtube.com" not in (link or "").lower() and "youtu.be" not in (link or "").lower():
        return False
    return True


def parse_entry_dt(entry: Any) -> datetime:
    """
    Tenta extrair a data de publicação de forma robusta.
    Retorna datetime (com tzinfo se possível) ou None.
    """
    try:
        # Tenta dateutil primeiro (ISO 8601 do YouTube)
        s = getattr(entry, "published", None) or getattr(entry, "updated", None)
        if s:
            return dtparser.isoparse(s)
    except (ValueError, TypeError, AttributeError) as e:
        log.debug(f"Falha ao parsear data ISO8601: {e}. Tentando fallback...")
    
    # Fallback para struct_time do feedparser
    try:
        st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc)
    except (ValueError, TypeError, AttributeError) as e:
        log.debug(f"Falha ao parsear data struct_time: {e}")
        
    return None


def get_youtube_duration_seconds(entry: Any) -> int | None:
    """
    Extrai duração do vídeo em segundos a partir da entrada do feed (YouTube Atom/RSS).
    Retorna None se não houver informação de duração.
    """
    try:
        media = getattr(entry, "media_content", None)
        if media and isinstance(media, list) and len(media) > 0:
            first = media[0]
            if isinstance(first, dict):
                dur = first.get("duration")
            else:
                dur = getattr(first, "duration", None)
            if dur is not None:
                return int(dur)
        # Alguns feeds usam media_group ou atributo direto
        if hasattr(entry, "media_group") and entry.media_group:
            for g in entry.media_group if isinstance(entry.media_group, list) else [entry.media_group]:
                dur = g.get("duration") if isinstance(g, dict) else getattr(g, "duration", None)
                if dur is not None:
                    return int(dur)
    except (TypeError, ValueError, AttributeError):
        pass
    return None


def _is_probable_image_url(url: str) -> bool:
    u = (url or "").lower()
    return any(ext in u for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"))


def _is_probable_video_url(url: str) -> bool:
    u = (url or "").lower()
    return any(ext in u for ext in (".mp4", ".webm", ".mov", ".m3u8"))


def extract_entry_media_urls(entry: Any) -> tuple[str | None, str | None]:
    """
    Tenta extrair URLs de imagem e vídeo de entradas RSS/Atom genéricas.
    Prioriza campos padrão de feedparser (media_content, media_thumbnail, links/enclosure).
    """
    image_url: str | None = None
    video_url: str | None = None

    try:
        media_content = getattr(entry, "media_content", None) or []
        if isinstance(media_content, list):
            for item in media_content:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                mtype = str(item.get("type") or "").lower()
                if not url:
                    continue
                if ("image" in mtype or _is_probable_image_url(url)) and not image_url:
                    image_url = url
                if ("video" in mtype or _is_probable_video_url(url)) and not video_url:
                    video_url = url
    except Exception as e:
        log.debug("media_content ilegivel na entrada (%s: %s)", type(e).__name__, e)

    try:
        media_thumb = getattr(entry, "media_thumbnail", None) or []
        if isinstance(media_thumb, list):
            for item in media_thumb:
                if isinstance(item, dict):
                    url = str(item.get("url") or "").strip()
                    if url:
                        image_url = image_url or url
                        break
    except Exception as e:
        log.debug("media_thumbnail ilegivel na entrada (%s: %s)", type(e).__name__, e)

    try:
        links = getattr(entry, "links", None) or []
        if isinstance(links, list):
            for l in links:
                if not isinstance(l, dict):
                    continue
                rel = str(l.get("rel") or "").lower()
                ltype = str(l.get("type") or "").lower()
                href = str(l.get("href") or "").strip()
                if rel != "enclosure" or not href:
                    continue
                if ("image" in ltype or _is_probable_image_url(href)) and not image_url:
                    image_url = href
                if ("video" in ltype or _is_probable_video_url(href)) and not video_url:
                    video_url = href
    except Exception as e:
        log.debug("links/enclosure ilegiveis na entrada (%s: %s)", type(e).__name__, e)

    if image_url and not image_url.startswith(("http://", "https://")):
        image_url = None
    if video_url and not video_url.startswith(("http://", "https://")):
        video_url = None
    return image_url, video_url


async def extract_og_image_safe(session: aiohttp.ClientSession, article_url: str) -> str | None:
    """
    Fallback seguro para og:image:
    - Opt-in por env
    - Whitelist de domínios (se configurada)
    - Validação anti-SSRF
    - Timeout curto
    - Limite de bytes para HTML
    """
    if not ENABLE_OG_IMAGE_FALLBACK:
        return None
    if not article_url or not article_url.startswith(("http://", "https://")):
        return None

    ok, err = await validate_url_async(article_url, allowed_domains=OG_IMAGE_ALLOWED_DOMAINS or None)
    if not ok:
        log.debug("og:image fallback bloqueado para %s (%s)", article_url, err)
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=OG_IMAGE_TIMEOUT_SECONDS)
        async with session.get(article_url, headers=get_robust_headers(), timeout=timeout) as resp:
            if resp.status != 200:
                return None
            ctype = str(resp.headers.get("Content-Type", "")).lower()
            if "text/html" not in ctype and "application/xhtml" not in ctype:
                return None
            raw = await resp.content.read(OG_IMAGE_MAX_BYTES)
            html = raw.decode("utf-8", errors="ignore")
    except Exception as e:
        log.debug("og:image fallback falhou para %s: %s", article_url, e)
        return None

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]
    image_url = None
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            image_url = m.group(1).strip()
            break
    if not image_url:
        return None

    image_url = urljoin(article_url, image_url)
    ok_img, err_img = await validate_url_async(image_url)
    if not ok_img:
        log.debug("og:image inválido/unsafe (%s): %s", image_url, err_img)
        return None
    return image_url


def get_news_metadata(title: str, url: str) -> tuple[str, discord.Color]:
    """
    Retorna (prefixo, cor) baseado em keywords e source url.
    Implementa a lógica de Leaks (🚨) e Rumores (🕵️).
    """
    leak_keywords = ["leak", "riiku", "vazamento", "rumor", "uwasa", "sokuhou", "速報", "リーク", "新型"]
    leak_sources = ["hobbynotoriko", "reddit.com/r/Gunpla", "dengeki", "weibo", "5ch"]

    title_lower = title.lower()
    
    # 1. Palavras-Chave (Prioridade: Alerta Vermelho/Laranja)
    if any(k in title_lower for k in leak_keywords):
        return ("🚨 **[LEAK]**", discord.Color.from_rgb(255, 69, 0)) # Red-Orange
    
    # 2. Fonte de Rumores (Prioridade: Espião/Detective)
    elif any(src in url for src in leak_sources):
         return ("🕵️ **[RUMOR]**", discord.Color.from_rgb(255, 140, 0)) # Dark Orange
    
    # 3. Padrão
    else:
        return ("", discord.Color.from_rgb(255, 0, 32)) # Standard Red

def build_news_message(
    bot: discord.Client,
    entry: Any,
    *,
    t_translated: str,
    s_translated: str,
    link: str,
    embed_color: "discord.Color",
    pub_dt: datetime | None,
    entry_image_url: str | None,
    entry_video_url: str | None,
    is_media: bool,
    target_lang: str,
) -> Tuple[str | None, "discord.Embed | None", "discord.ui.View"]:
    """
    Monta os artefatos de uma notícia (content, embed, view) SEM enviar — função pura,
    testável isoladamente. Extraída de run_scan_once para reduzir o god-function e cobrir
    a construção do embed com testes.
    """
    # Sem data no feed: usa agora em UTC (antes usava datetime.now() naive e rotulava como UTC)
    embed_ts = pub_dt if pub_dt else datetime.now(timezone.utc)
    if embed_ts.tzinfo is None:
        embed_ts = embed_ts.replace(tzinfo=timezone.utc)

    str_date = pub_dt.strftime("%d/%m/%Y %H:%M") if pub_dt else datetime.now().strftime("%d/%m/%Y %H:%M")
    postado_str = f"🕒 **Postado em:** {str_date}"

    # description tem limite de 4096 no Discord; a tradução pode expandir, então cortamos depois
    embed = discord.Embed(
        title=t_translated[:256],
        description=f"{s_translated}\n\n{postado_str}"[:4096],
        url=link,
        color=embed_color,
        timestamp=embed_ts,
    )
    author_name = t.get('embed.author', lang=target_lang)
    icon_url = bot.user.avatar.url if bot.user and bot.user.avatar else None
    embed.set_author(name=author_name, icon_url=icon_url)

    source_domain = urlparse(link).netloc
    footer_text = t.get('embed.source', lang=target_lang, source=source_domain)
    if pub_dt:
        date_str = pub_dt.strftime("%d/%m/%Y %H:%M")
        footer_text = f"{footer_text} • {t.get('embed.published_at', lang=target_lang, date=date_str)}"
    embed.set_footer(text=footer_text)

    # Guarda: URL de imagem malformada faz o Discord recusar o EMBED INTEIRO
    # (50035) -- noticia falha em todas as guilds, nao entra no dedup e o ciclo
    # repete para sempre. O og:image ja passa por validate_url_async; esta guarda
    # fecha o caminho do FEED (entry_image_url do feed e media_thumbnail direto),
    # que ia ao embed sem validacao. Noticia sem imagem e lida; recusada nao existe.
    img_ok = imagem_publicavel(entry_image_url)
    if entry_image_url and not img_ok:
        log.warning(
            "[EMBED] Imagem descartada por URL invalida, noticia segue sem ela: %s",
            str(entry_image_url)[:120],
        )
    if img_ok:
        embed.set_image(url=img_ok)
    elif hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        try:
            thumb_url = entry.media_thumbnail[0].get("url")
            thumb_ok = imagem_publicavel(thumb_url)
            if thumb_url and not thumb_ok:
                log.warning(
                    "[EMBED] Thumbnail descartada por URL invalida, noticia segue sem ela: %s",
                    str(thumb_url)[:120],
                )
            if thumb_ok:
                embed.set_thumbnail(url=thumb_ok)
        except (IndexError, AttributeError, KeyError) as e:
            log.debug(f"Erro ao obter thumbnail da entrada: {e}")
        except Exception as e:
            log.warning(f"Erro inesperado ao processar thumbnail: {e}")

    # Se for mídia, mandamos o LINK no content (Discord gera player nativo) e não o embed
    if is_media:
        msg_content = f"📺 **{t_translated}**\n{link}\n\n{postado_str}"[:2000]
        embed_to_send = None
    else:
        msg_content = None
        embed_to_send = embed

    # Botões de link: só http(s) — Discord rejeita mailto: e URLs > 512 chars
    view = discord.ui.View(timeout=None)
    read_url = safe_https_button_url(link)
    if read_url:
        view.add_item(discord.ui.Button(label="Leia Mais", url=read_url, emoji="📖", style=discord.ButtonStyle.link))
    view.add_item(discord.ui.Button(label="WhatsApp", url=whatsapp_share_button_url(t_translated, link), emoji="🟢", style=discord.ButtonStyle.link))
    view.add_item(discord.ui.Button(label="E-mail", url=gmail_compose_button_url(t_translated, link), emoji="✉️", style=discord.ButtonStyle.link))
    if entry_video_url:
        safe_video = safe_https_button_url(entry_video_url)
        if safe_video:
            view.add_item(discord.ui.Button(label="Assistir vídeo", url=safe_video, emoji="🎬", style=discord.ButtonStyle.link))

    return msg_content, embed_to_send, view


async def _run_html_monitor(
    bot: discord.Client,
    config: Dict[str, Any],
    state: Dict[str, Any],
    html_hashes: Dict[str, str],
) -> int:
    """
    Verifica sites oficiais (HTML Watcher) e despacha alertas de mudança para cada guild.
    Atualiza state['html_hashes']. Retorna o número de mensagens enviadas.
    Extraído de run_scan_once para reduzir o god-function.
    """
    sent = 0
    try:
        log.info("🔎 Verificando sites oficiais (HTML Watcher)...")
        html_updates, new_hashes = await check_official_sites(html_hashes, full_state=state)

        if html_updates:
            log.info(f"✨ {len(html_updates)} atualizações em sites oficiais detectadas!")
            state["html_hashes"] = new_hashes
            for update in html_updates:
                u_title = update["title"]
                u_link = update["link"]
                u_summary = update.get("summary", "")

                for gid, gdata in config.items():
                    if not isinstance(gdata, dict):
                        continue

                    channel_id = gdata.get("channel_id")
                    if not channel_id:
                        continue

                    try:
                        channel = bot.get_channel(int(channel_id))
                    except (ValueError, TypeError) as e:
                        log.warning(
                            f"[HTML Monitor] Canal inválido para guild {gid} (channel_id={channel_id}): {e}"
                        )
                        channel = None

                    if not should_post_to_guild(str(gid), u_title, u_summary, config):
                        log.debug(f"🛡️ [Filtro HTML] Guild {gid} bloqueou site: {u_title}")
                        continue

                    if channel:
                        try:
                            view = discord.ui.View(timeout=None)
                            html_read = safe_https_button_url(u_link)
                            if html_read:
                                view.add_item(
                                    discord.ui.Button(
                                        label="Leia Mais",
                                        url=html_read,
                                        emoji="📖",
                                        style=discord.ButtonStyle.link,
                                    )
                                )
                            ul = str(u_link or "").strip()
                            share_link = html_read or (
                                ul[:LINK_BUTTON_URL_MAX]
                                if ul.startswith(("http://", "https://"))
                                else ""
                            )
                            if not share_link:
                                share_link = "https://mail.google.com/mail/"
                            view.add_item(
                                discord.ui.Button(
                                    label="WhatsApp",
                                    url=whatsapp_share_button_url(u_title, share_link),
                                    emoji="🟢",
                                    style=discord.ButtonStyle.link,
                                )
                            )
                            view.add_item(
                                discord.ui.Button(
                                    label="E-mail",
                                    url=gmail_compose_button_url(u_title, share_link),
                                    emoji="✉️",
                                    style=discord.ButtonStyle.link,
                                )
                            )

                            str_date = datetime.now().strftime("%d/%m/%Y %H:%M")
                            post_text = f"🕒 **Postado em:** {str_date}"
                            alert_msg = f"⚠️ **GameBot — Alerta**\n{u_title}\n{u_link}\n\n{post_text}"
                            await channel.send(alert_msg[:2000], view=view)
                            sent += 1
                        except discord.Forbidden:
                            log.error(
                                f"[HTML Monitor] Sem permissão para enviar no canal {channel_id} (guild {gid})"
                            )
                        except discord.HTTPException as e:
                            log.error(
                                f"[HTML Monitor] Erro HTTP ao enviar alerta no canal {channel_id}: {e.status} - {e.text}"
                            )
        else:
            if new_hashes != html_hashes:
                state["html_hashes"] = new_hashes

    except Exception as e:
        log.exception(
            f"❌ [HTML Monitor] Exceção ao verificar sites oficiais: {type(e).__name__}: {e}"
        )
    return sent


# =========================================================
# SCANNER LOGIC
# =========================================================

def _log_next_run() -> None:
    """Log explícito do próximo horário de varredura."""
    nxt = datetime.now() + timedelta(minutes=LOOP_MINUTES)
    interval_h = LOOP_MINUTES // 60
    log.info(
        f"⏳ Aguardando próxima varredura às {nxt:%Y-%m-%d %H:%M:%S} "
        f"(intervalo: {interval_h}h / {LOOP_MINUTES} min)..."
    )


def _registar_saida_precoce(trigger: str, **contagens) -> None:
    """
    PROPÓSITO DE NEGÓCIO: fazer com que a varredura que desiste no portão de entrada
    deixe rasto, em vez de terminar em silêncio.

    INVARIANTES DO DOMÍNIO: as saídas antecipadas (nenhuma guild configurada, catálogo
    vazio) são a AUSÊNCIA MAIS GRAVE que existe — o bot não tentou sequer. Sem registo, o
    `/status` mostraria o veredito da varredura anterior, que pode ser um `OK` de dias
    atrás, e o painel diria que está tudo bem enquanto nada acontece.

    COMPORTAMENTO EM CASO DE FALHA: qualquer erro ao ler ou gravar o estado é apanhado e
    registado; não impede a saída antecipada nem levanta. Perder telemetria é mau; impedir
    o bot de sair de um portão de entrada seria pior.
    """
    try:
        caminho = p("state.json")
        estado = load_json_safe(caminho, {})
        if not isinstance(estado, dict):
            estado = {}
        registo = telemetria.resumir(telemetria.Contadores(trigger=trigger, **contagens))
        telemetria.registar(estado, registo)
        save_json_safe(caminho, estado)
        log.error("🔴 [Saúde] %s — %s", registo.veredito, registo.motivo)
    except Exception as e:
        log.warning("não foi possível registar a saúde da saída antecipada: %s", e)


async def run_scan_once(bot: discord.Client, trigger: str = "manual") -> None:
    """
    Executa UMA varredura completa.
    
    Args:
        bot: Instância do bot Discord
        trigger: Quem disparou ("loop", "dashboard", "manual")
    """

    if scan_lock.locked():
        log.info(f"⏭️ Varredura ignorada (já existe uma em execução). Trigger: {trigger}")
        return

    async with scan_lock:
        global _runtime_profile_logged
        scan_start_time = time.time()
        # Limite de 125 minutos para que uma varredura não atropele a próxima e evite bloqueios do Discord
        MAX_SCAN_DURATION = 125 * 60 

        log.info(f"🔎 Iniciando varredura de notícias (GameBot)... (trigger={trigger})")
        if not _runtime_profile_logged:
            limit_label = (
                f"{MAX_ENTRIES_PER_FEED}/feed" if MAX_ENTRIES_PER_FEED > 0 else "sem limite por feed"
            )
            log.info(
                "🛡️ [Ingestion Profile] feeds=%s | timeout=%ss | retries=%s | backoff_base=%.2f | "
                "jitter=%.2f-%.2fs | max_age=%sd | entries=%s | strict_youtube=%s",
                MAX_CONCURRENT_FEEDS,
                FEED_TIMEOUT_SECONDS,
                RSS_MAX_RETRIES,
                RSS_RETRY_BACKOFF_BASE,
                min(FEED_FETCH_JITTER_MIN, FEED_FETCH_JITTER_MAX),
                max(FEED_FETCH_JITTER_MIN, FEED_FETCH_JITTER_MAX),
                MAX_NEWS_AGE_DAYS,
                limit_label,
                "on" if STRICT_GENERIC_YOUTUBE else "off",
            )
            _runtime_profile_logged = True

        config = load_json_safe(p("config.json"), {})
        # Mapa em memória de idioma por guild para evitar leitura repetida de config no hot path
        guild_lang_map: Dict[str, str] = {
            str(gid): str(gdata.get("language"))
            for gid, gdata in config.items()
            if isinstance(gdata, dict) and gdata.get("language")
        }
        
        # Verifica se há guilds configuradas
        if not config or not any(isinstance(v, dict) and v.get("channel_id") for v in config.values()):
            log.warning("⚠️ Nenhuma guild configurada com 'channel_id'. Use /set_canal ou /dashboard para configurar.")
            _registar_saida_precoce(trigger)
            _log_next_run()
            return
            
        urls = load_sources()
        if not urls:
            log.warning("Nenhuma URL válida em sources.json.")
            _registar_saida_precoce(trigger)
            _log_next_run()
            return

        # Impressão digital do catálogo em uso. Existe por causa de um defeito real: no
        # Docker o `sources.json` ficava congelado no volume, e o contêiner lia um catálogo
        # antigo depois de cada rebuild — em silêncio. O caminho e a contagem no log fazem
        # "adicionei fontes e não mudou nada" virar uma linha comparável, em vez de uma
        # suspeita. O hash distingue duas versões com o mesmo número de fontes.
        _caminho_catalogo = p("sources.json")
        _digest = hashlib.sha256(
            "\n".join(urls).encode("utf-8", errors="ignore")
        ).hexdigest()[:12]
        log.info(
            "📚 [Catálogo] %s fontes | sha=%s | arquivo=%s",
            len(urls), _digest, _caminho_catalogo,
        )

        # =========================================================
        # UNIFIED STATE MANAGEMENT & AUTO-CLEANUP
        # =========================================================
        # Carrega o estado unificado (HTTP Cache + HTML Monitor + Deduplication + Cleanup)
        state_file = p("state.json")
        state = load_json_safe(state_file, {})
        
        # Garante estruturas básicas
        state.setdefault("dedup", {})
        state.setdefault("http_cache", {})
        state.setdefault("html_hashes", {})
        state.setdefault("last_cleanup", 0)
        state.setdefault("source_failures", {})  # Source Health Monitor: url -> {count, last_error, last_ts}

        # Regra de Auto-Limpeza (Cleanup) a cada 7 dias
        now_ts = time.time()
        last_clean = state.get("last_cleanup", 0)
        CLEANUP_INTERVAL = 604800  # 7 dias em segundos

        if now_ts - last_clean > CLEANUP_INTERVAL:
            log.info("🧹 [Auto-Cleanup] Limitando dedup e podando caches órfãos (Ciclo de 7 dias)")
            # NÃO zera mais o dedup inteiro (o wipe causava repost em massa). Apenas limita
            # o tamanho de cada balde aos últimos MAX_DEDUP_PER_FEED links.
            dedup_map = state.get("dedup", {})
            if isinstance(dedup_map, dict):
                for _links in dedup_map.values():
                    if isinstance(_links, list) and len(_links) > MAX_DEDUP_PER_FEED:
                        del _links[:-MAX_DEDUP_PER_FEED]
            # Poda entradas órfãs (fontes que não existem mais). No pior caso força um refetch,
            # nunca um repost — por isso é seguro remover.
            active_urls = set(load_sources()) | set(state.get("youtube_feed_cache", {}).values())
            for bucket_name in ("http_cache", "source_failures"):
                bucket = state.get(bucket_name, {})
                if isinstance(bucket, dict):
                    for dead in [k for k in list(bucket.keys()) if k not in active_urls]:
                        del bucket[dead]
            state["last_cleanup"] = now_ts
        
        # Referências locais para facilitar acesso
        http_cache = state["http_cache"]
        html_hashes = state["html_hashes"]
        # history_set ainda usado como fallback global, mas dedup por site é prioritário
        history_list, history_set = load_history()

        # SSL Configuration
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        base_headers = get_robust_headers()
        timeout = aiohttp.ClientTimeout(total=FEED_TIMEOUT_SECONDS)
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        sent_count = 0
        cache_hits = 0
        feeds_empty = 0
        feeds_errors = 0
        feeds_blocked_security = 0
        entries_undated_skipped = 0
        # Telemetria de ausencia: sem estes tres nao ha como distinguir "0 publicados
        # porque nao havia" de "0 publicados porque quebrou". itens_novos conta o que
        # passou o dedup; itens_filtrados o que foi descartado de proposito; a diferenca
        # entre eles e os publicados e a invariante de conservacao (telemetria.py).
        itens_novos = 0
        itens_filtrados = 0
        entregas_falhadas = 0
        degradacoes_no_inicio = degradacoes_totais()
        
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FEEDS)
        RSS_BACKOFF = [RSS_RETRY_BACKOFF_BASE * (2 ** i) for i in range(max(1, RSS_MAX_RETRIES))]
        source_failures = state["source_failures"]

        async def fetch_and_process_feed(session, url):
            # `state` e `entries_undated_skipped` NAO entram aqui: não são atribuídos neste
            # escopo, e `nonlocal` de nome nunca reatribuído é F824 — que o `--select=F82`
            # do CI captura por prefixo. O passo de lint reprovava e, sendo anterior ao
            # `pytest` no workflow, deixava a suíte sem rodar no CI.
            nonlocal cache_hits, feeds_empty, feeds_errors, feeds_blocked_security

            async with semaphore:
                # Validação de segurança: anti-SSRF
                is_valid, error_msg = await validate_url_async(url)
                if not is_valid:
                    log.warning(sanitize_log_message(f"🔒 URL bloqueada por segurança: {url} - {error_msg}"))
                    feeds_blocked_security += 1
                    return None

                # B311: `random` nao-criptografico basta — este numero so espaca as
                # requisicoes para nao parecerem uma rajada. Nao e segredo.
                jitter = random.uniform(  # nosec B311
                    min(FEED_FETCH_JITTER_MIN, FEED_FETCH_JITTER_MAX),
                    max(FEED_FETCH_JITTER_MIN, FEED_FETCH_JITTER_MAX),
                )
                await asyncio.sleep(jitter)

                request_headers = {**get_cache_headers(url, http_cache), **get_robust_headers()}
                last_error: Exception | None = None

                for attempt in range(RSS_MAX_RETRIES):
                    if (time.time() - scan_start_time) > MAX_SCAN_DURATION:
                        log.warning(f"🛑 [Timeout Scan-Feed] Cancelando fetch de {url} para não travar o bot.")
                        return None

                    try:
                        async with session.get(url, headers=request_headers) as resp:
                            if resp.status == 304:
                                cache_hits += 1
                                log.debug(f"📦 Cache hit: {url} (304)")
                                if url in source_failures:
                                    source_failures[url]["count"] = 0
                                return None

                            if resp.status == 431:
                                log.warning(f"⚠️ Twitter/X Error: Header value too long (431) - {url}")
                                return None

                            # Qualquer outro não-200 é FALHA DE FONTE, não "feed vazio".
                            # Antes o corpo do 403/404 era entregue ao feedparser, que devolvia
                            # zero entradas — e o aviso abaixo só dispara em status 200. Resultado:
                            # fontes mortas não contavam erro, não entravam em source_failures e
                            # não apareciam em log nenhum (medido: 20 fontes mortas com
                            # feeds_com_erro=0 no resumo da varredura).
                            if resp.status != 200:
                                rec = source_failures.setdefault(
                                    url, {"count": 0, "last_error": "", "last_ts": 0}
                                )
                                rec["count"] = rec.get("count", 0) + 1
                                rec["last_error"] = f"HTTP {resp.status}"
                                rec["last_ts"] = time.time()
                                feeds_errors += 1
                                log.error(
                                    f"❌ Feed respondeu HTTP {resp.status} (falha {rec['count']}x): {url}"
                                )
                                if rec["count"] >= 3:
                                    log.error(
                                        f"🔴 [Source Health] Fonte falhou {rec['count']} vezes com "
                                        f"HTTP {resp.status}: {url} | Verifique se a fonte ainda existe "
                                        f"ou remova-a do sources.json."
                                    )
                                return None

                            # NAO grava o ETag aqui. Gravar antes de postar transforma
                            # qualquer falha de entrega (canal sem permissao, canal
                            # apagado, 5xx do Discord) em perda PERMANENTE: a varredura
                            # seguinte recebe 304 e as entradas nunca mais aparecem.
                            # Os cabecalhos viajam com o resultado e so viram cache
                            # depois que o processamento do feed terminou inteiro.
                            # Nomes canônicos: `resp.headers` é CIMultiDict (busca sem
                            # distinguir maiúsculas); um dict comum não é, e um servidor
                            # que respondesse `Etag:` perderia o cache em silêncio.
                            cabecalhos_cache = {}
                            for _nome in ("ETag", "Last-Modified"):
                                _valor = resp.headers.get(_nome)
                                if _valor:
                                    cabecalhos_cache[_nome] = _valor
                            text = await resp.text(errors="ignore")

                        loop = asyncio.get_running_loop()
                        feed = await loop.run_in_executor(None, lambda: feedparser.parse(text))

                        entries = getattr(feed, "entries", []) or []
                        # MAX_ENTRIES_PER_FEED <= 0 => sem limitação (processa tudo)
                        if MAX_ENTRIES_PER_FEED > 0 and len(entries) > MAX_ENTRIES_PER_FEED:
                            # Truncagem SILENCIOSA era perda invisivel: com varredura de
                            # 24h e teto de 10, um feed que publica 14 itens/dia perdia 4
                            # todo dia sem uma linha de log. O feed nao tem paginacao, entao
                            # o que se pode fazer e tornar a perda VISIVEL — e o operador
                            # decide entre subir MAX_ENTRIES_PER_FEED ou baixar LOOP_MINUTES.
                            log.warning(
                                "✂️ Feed truncado: %s trouxe %s entradas, MAX_ENTRIES_PER_FEED=%s "
                                "— %s descartadas SEM analise. Se repetir, aumente "
                                "MAX_ENTRIES_PER_FEED ou reduza LOOP_MINUTES (hoje %s min).",
                                url, len(entries), MAX_ENTRIES_PER_FEED,
                                len(entries) - MAX_ENTRIES_PER_FEED, LOOP_MINUTES,
                            )
                            entries = entries[:MAX_ENTRIES_PER_FEED]

                        if not entries:
                            # 200 sem entrada nenhuma também é sintoma de fonte doente
                            # (handle de YouTube ocupado por terceiro, feed descontinuado,
                            # bloqueio que devolve HTML em vez de XML). Passa a contar.
                            rec = source_failures.setdefault(
                                url, {"count": 0, "last_error": "", "last_ts": 0}
                            )
                            rec["count"] = rec.get("count", 0) + 1
                            rec["last_error"] = "HTTP 200 sem entradas"
                            rec["last_ts"] = time.time()
                            log.warning(
                                "⚠️ Feed 200 sem entradas (falha %sx — bloqueio parcial, parser "
                                "mismatch ou feed descontinuado): %s",
                                rec["count"],
                                url,
                            )
                            feeds_empty += 1
                            if rec["count"] >= 3:
                                log.error(
                                    f"🔴 [Source Health] Fonte devolve 200 sem entradas há "
                                    f"{rec['count']} varreduras: {url} | Provavelmente morta."
                                )
                            return (url, entries, cabecalhos_cache)

                        if url in source_failures:
                            source_failures[url]["count"] = 0
                        return (url, entries, cabecalhos_cache)

                    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                        last_error = e
                        if attempt < RSS_MAX_RETRIES - 1:
                            delay = RSS_BACKOFF[attempt]
                            log.debug(
                                "🔁 Retry feed em %.2fs | tentativa=%s/%s | url=%s | erro=%s",
                                delay,
                                attempt + 1,
                                RSS_MAX_RETRIES,
                                url,
                                e,
                            )
                            await asyncio.sleep(delay)
                        else:
                            rec = source_failures.setdefault(url, {"count": 0, "last_error": "", "last_ts": 0})
                            rec["count"] = rec.get("count", 0) + 1
                            rec["last_error"] = str(e)
                            rec["last_ts"] = time.time()
                            feeds_errors += 1
                            log.error(sanitize_log_message(f"❌ Erro de conexão ao baixar feed '{url}' após {RSS_MAX_RETRIES} tentativas: {e}"))
                            if rec["count"] >= 3:
                                log.error(
                                    f"🔴 [Source Health] Fonte RSS falhou {rec['count']} vezes: {url} | "
                                    f"last_error={rec.get('last_error')} | Verifique conectividade ou remova a fonte."
                                )
                            return None
                    except Exception as e:
                        last_error = e
                        if attempt < RSS_MAX_RETRIES - 1:
                            delay = RSS_BACKOFF[attempt]
                            log.debug(
                                "🔁 Retry feed em %.2fs | tentativa=%s/%s | url=%s | erro=%s",
                                delay,
                                attempt + 1,
                                RSS_MAX_RETRIES,
                                url,
                                e,
                            )
                            await asyncio.sleep(delay)
                        else:
                            rec = source_failures.setdefault(url, {"count": 0, "last_error": "", "last_ts": 0})
                            rec["count"] = rec.get("count", 0) + 1
                            rec["last_error"] = f"{type(e).__name__}: {e}"
                            rec["last_ts"] = time.time()
                            feeds_errors += 1
                            log.error(sanitize_log_message(f"❌ Falha inesperada ao processar feed '{url}': {type(e).__name__}: {e}"), exc_info=True)
                            if rec["count"] >= 3:
                                log.error(
                                    f"🔴 [Source Health] Fonte RSS falhou {rec['count']} vezes: {url} | "
                                    f"last_error={rec.get('last_error')}"
                                )
                            return None

                return None

        async with aiohttp.ClientSession(connector=connector, headers=base_headers, timeout=timeout) as session:
            # Converte URLs de canais YouTube (@usuario ou /channel/) para feed RSS (channel_id)
            resolved_urls = await resolve_youtube_urls(session, urls, state, timeout)
            total_feeds = len(resolved_urls)
            tasks = [fetch_and_process_feed(session, url) for url in resolved_urls]
            results = await asyncio.gather(*tasks)
            
            for result in results:
                if result is None:
                    continue

                url, entries, cabecalhos_cache = result

                # Vira True assim que uma entrega FALHA (canal ausente, sem permissão, erro
                # do Discord) ou o processamento do feed é cortado pelo teto de tempo.
                # Enquanto for True, o ETag deste feed NÃO avança: na próxima varredura o
                # feed é rebaixado inteiro e as entradas voltam a ser vistas. Item
                # descartado por filtro não conta como falha — foi decisão, não perda.
                falha_de_entrega = False

                # Cold Start Check para este feed específico
                # Se a URL não estiver no dedup, é um cold start ou reset deste feed
                is_cold_start = url not in state["dedup"]
                if is_cold_start:
                    log.info(f"❄️ [Cold Start] Detectado para {url}. Ignorando travas de tempo para os 3 primeiros posts.")
                    state["dedup"][url] = []

                feed_posted_count = 0

                for entry in entries:
                    if (time.time() - scan_start_time) > MAX_SCAN_DURATION:
                         log.warning(f"🛑 [Timeout Scan-Post] Interrompendo processamento de {url} (scan > 125m).")
                         falha_de_entrega = True
                         break

                    link = entry.get("link") or "" 
                    if not link: continue
                    
                    link = sanitize_link(link)
                    
                    # 1. Verifica no dedup específico do site (Prioridade)
                    if link in state["dedup"][url]:
                        continue
                        
                    # 2. Verifica histórico global (Legado/Fallback)
                    if link in history_set:
                        # Adiciona ao novo dedup para consistência
                        state["dedup"][url].append(link)
                        continue

                    itens_novos += 1

                    # Cold Start: Respeitando pedido de "sem limitação", removemos a trava rígida de 3 posts.
                    # O dedup cuidará das duplicatas nas próximas rodadas.
                    # if is_cold_start and feed_posted_count >= 3: continue # Removido

                    # Filtragem por data: nunca publicar notícias com mais de 7 dias (inclui Cold Start)
                    entry_dt = parse_entry_dt(entry)
                    if entry_dt:
                        now = datetime.now(entry_dt.tzinfo) if entry_dt.tzinfo else datetime.now()
                        age = now - entry_dt
                        if age.days > MAX_NEWS_AGE_DAYS:
                            log.debug(f"👴 [Old] Ignorado (idade {age.days}d, máx. {MAX_NEWS_AGE_DAYS} dias): {link}")
                            itens_filtrados += 1
                            continue
                    elif REQUIRE_ENTRY_DATE:
                        entries_undated_skipped += 1
                        log.debug(f"🕒 [Undated] Ignorado por falta de data no feed: {link}")
                        itens_filtrados += 1
                        continue

                    title = entry.get("title") or ""
                    summary = entry.get("summary") or entry.get("description") or ""
                    entry_image_url, entry_video_url = extract_entry_media_urls(entry)
                    if not entry_image_url:
                        entry_image_url = await extract_og_image_safe(session, link)

                    # Filtro de conteúdo (LIXO_FILTER): descarta ruído e loga
                    if should_skip_by_content(title, summary):
                        log.debug(f"🛡️ [Filtro] Ruído filtrado: {title[:50]}...")
                        itens_filtrados += 1
                        continue
                    if should_skip_generic_youtube_false_positive(url, title, link):
                        log.debug(f"🛡️ [Filtro] YouTube genérico sem sinal de jogo no título: {title[:60]}...")
                        itens_filtrados += 1
                        continue

                    # Regra extra: filtrar YouTube Shorts que não sejam claramente trailers/anúncios de jogos
                    if "youtube.com/shorts/" in link:
                        title_lower = (title or "").lower()
                        allowed_short_kw = (
                            "trailer",
                            "announcement",
                            "reveal",
                            "launch",
                            "gameplay trailer",
                            "official trailer",
                        )
                        if not any(kw in title_lower for kw in allowed_short_kw):
                            log.debug(f"🛡️ [Filtro] YouTube Shorts descartado: {title[:50]}...")
                            itens_filtrados += 1
                            continue

                    # GRC: vídeos YouTube com mais de 12 min são descartados (podcasts/entrevistas), exceto Official Gameplay / Reveal
                    if "youtube.com" in link or "youtu.be" in link:
                        duration_sec = get_youtube_duration_seconds(entry)
                        if duration_sec is not None and duration_sec > 12 * 60:
                            title_lower = (title or "").lower()
                            if "official gameplay" not in title_lower and "reveal" not in title_lower:
                                log.debug(f"🛡️ [Filtro] Vídeo longo descartado ({duration_sec // 60} min): {title[:50]}...")
                                itens_filtrados += 1
                                continue

                    posted_anywhere = False
                    # Por ITEM, não por feed: `falha_de_entrega` diz que algo correu mal
                    # neste feed, mas a conservação precisa de saber qual ITEM não saiu.
                    entrega_falhou_neste_item = False
                    t_clean = clean_html(title).strip()
                    s_clean = clean_html(summary).strip()[:2000]
                    # Cache de tradução por idioma para esta notícia (título + resumo)
                    translations_by_lang: Dict[str, Tuple[str, str]] = {}

                    # Verifica cada guild
                    for gid, gdata in config.items():
                        if not isinstance(gdata, dict): continue
                        
                        channel_id = gdata.get("channel_id")
                        if not isinstance(channel_id, int): continue

                        if not should_post_to_guild(str(gid), title, summary, config):
                            log.debug(f"🛡️ [Filtro] Guild {gid} bloqueou: {title[:50]}...")
                            continue
                        
                        # Envio (código de envio inalterado abaixo)
                        log.info(f"✨ [Match] Guild {gid} aprovou: {title[:50]}...")

                        channel = bot.get_channel(channel_id)
                        if channel is None:
                            log.warning(f"Canal {channel_id} não encontrado.")
                            falha_de_entrega = True
                            entrega_falhou_neste_item = True
                            continue

                        # Tradução
                        target_lang = t.detect_lang(str(gid), guild_lang_map=guild_lang_map)
                        if target_lang not in translations_by_lang:
                            t_translated = await translate_to_target(t_clean, target_lang)
                            s_translated = await translate_to_target(s_clean, target_lang)
                            translations_by_lang[target_lang] = (t_translated, s_translated)
                        else:
                            t_translated, s_translated = translations_by_lang[target_lang]

                        # Detecção de Leaks/Rumores (Refined Logic via Helper)
                        prefix, embed_color = get_news_metadata(t_clean, link)
                        
                        if prefix:
                            t_translated = f"{prefix} {t_translated}"


                        # Verifica se é mídia para expor o link e gerar player
                        media_domains = ("youtube.com", "youtu.be", "twitch.tv", "soundcloud.com", "spotify.com")
                        is_media = False
                        try:
                            if any(d in link for d in media_domains):
                                is_media = True
                        except Exception as e:
                            log.debug(f"Erro ao verificar domínio de mídia para '{link[:50]}...': {e}")

                        try:
                            pub_dt = entry_dt if entry_dt else None
                            msg_content, embed_to_send, view = build_news_message(
                                bot,
                                entry,
                                t_translated=t_translated,
                                s_translated=s_translated,
                                link=link,
                                embed_color=embed_color,
                                pub_dt=pub_dt,
                                entry_image_url=entry_image_url,
                                entry_video_url=entry_video_url,
                                is_media=is_media,
                                target_lang=target_lang,
                            )

                            await channel.send(content=msg_content, embed=embed_to_send, view=view)

                            posted_anywhere = True
                            sent_count += 1
                            if is_cold_start:
                                feed_posted_count += 1
                            # Delay anti-spam (GRC-Refined): evita rate limit e detecção de spam pelo Discord
                            # Aumentado para 2.5s para maior segurança em varreduras longas
                            await asyncio.sleep(2.5)

                        except discord.Forbidden as e:
                            log.error(f"🚫 Sem permissão para enviar mensagem no canal {channel_id} (guild {gid}): {e}")
                            falha_de_entrega = True
                            entrega_falhou_neste_item = True
                        except discord.HTTPException as e:
                            log.error(f"🌐 Erro HTTP ao enviar mensagem no canal {channel_id}: {e.status} - {e.text}")
                            falha_de_entrega = True
                            entrega_falhou_neste_item = True
                        except (ValueError, TypeError) as e:
                            # discord.py 2.x removeu discord.InvalidArgument; embed/botão inválido
                            # lança ValueError/TypeError. Sem este catch, o erro abortava a varredura.
                            log.error(f"⚠️ Argumento inválido ao criar embed/mensagem: {type(e).__name__}: {e}")
                            falha_de_entrega = True
                            entrega_falhou_neste_item = True
                        except Exception as e:
                            log.exception(f"❌ Falha inesperada ao enviar no canal {channel_id} (guild {gid}): {type(e).__name__}: {e}")
                            falha_de_entrega = True
                            entrega_falhou_neste_item = True

                    if posted_anywhere:
                        # Adiciona ao dedup específico e global
                        state["dedup"][url].append(link)
                        history_set.add(link)
                        history_list.append(link)
                    elif entrega_falhou_neste_item:
                        # Terceira porta da conservacao: o item existia, foi aprovado e
                        # NAO saiu por falha de entrega. Sem esta contagem, a conservacao
                        # acusaria "item sumido" e esconderia a causa verdadeira.
                        entregas_falhadas += 1
                    else:
                        # Nenhuma guild aprovou e nada falhou: foi decisao de filtro, nao
                        # perda.
                        itens_filtrados += 1

                # O ETag/Last-Modified só entra no cache depois que o feed inteiro foi
                # processado SEM falha de entrega. É o que garante que "não consegui postar"
                # vire "tento de novo na próxima", e não "perdi para sempre".
                if falha_de_entrega:
                    log.warning(
                        "🔁 Cache HTTP de %s NÃO avançado: houve falha de entrega nesta varredura. "
                        "O feed será rebaixado inteiro na próxima para não perder as entradas.",
                        url,
                    )
                elif cabecalhos_cache:
                    update_cache_state(url, cabecalhos_cache, http_cache)

        # =========================================================
        # HTML MONITOR RUN (SITE WATCHER)
        # =========================================================
        # Separados de proposito: alerta de site mudado nao e noticia, e misturar os dois
        # num contador so impediria a telemetria de dizer "0 noticias, mas 2 alertas".
        noticias_publicadas = sent_count
        alertas_html = await _run_html_monitor(bot, config, state, html_hashes)
        sent_count += alertas_html

        # Salva TUDO em um único arquivo de forma atômica/safe
        save_history(history_list)
        # Telemetria calculada ANTES do merge+save: assim o registo de saude entra na
        # mesma (unica) escrita de state.json e passa pela reconciliacao com o disco.
        # Uma segunda escrita depois do save abriria de novo a janela de lost-update
        # que o merge existe para fechar.
        contadores = telemetria.Contadores(
            trigger=trigger,
            fontes_total=total_feeds if 'total_feeds' in locals() else len(urls),
            fontes_com_erro=feeds_errors,
            fontes_vazias=feeds_empty,
            fontes_bloqueadas=feeds_blocked_security,
            cache_304=cache_hits,
            itens_novos=itens_novos,
            itens_filtrados=itens_filtrados,
            itens_publicados=noticias_publicadas,
            alertas_html=alertas_html,
            entregas_falhadas=entregas_falhadas,
            traducoes_degradadas=degradacoes_totais() - degradacoes_no_inicio,
            duracao_s=time.time() - scan_start_time,
        )
        registo = telemetria.resumir(contadores)
        telemetria.registar(state, registo)

        # Recarrega o state do disco e preserva chaves escritas por comandos DURANTE o scan
        # (ex.: last_announced_hash gravado pelo main.py). A varredura só é dona destas chaves;
        # o resto é mesclado do disco para não sofrer lost-update numa janela de até 125 min.
        _scan_owned = (
            "dedup", "http_cache", "html_hashes", "youtube_feed_cache",
            "source_failures", "last_cleanup", telemetria.CHAVE_ESTADO,
        )
        disk_state = load_json_safe(state_file, {})
        if isinstance(disk_state, dict):
            for _k, _v in disk_state.items():
                if _k not in _scan_owned:
                    state[_k] = _v
        save_json_safe(state_file, state)
        
        stats.scans_completed += 1
        stats.news_posted += sent_count
        stats.cache_hits_total += cache_hits
        stats.feeds_failed += feeds_errors + feeds_blocked_security
        stats.last_scan_time = datetime.now()

        # =========================================================
        # TELEMETRIA DE AUSENCIA
        # =========================================================
        # O resumo antigo despejava numeros e deixava a interpretacao para quem lesse o
        # log. Numero mudo nao diz se `posts_enviados=0` e um dia calmo ou o bot partido —
        # e foi assim que o `on_ready` abortado e o sources.json congelado passaram
        # despercebidos. Agora a varredura emite VEREDITO com MOTIVO, e persiste-o.

        nivel = {
            telemetria.VEREDITO_ANOMALIA: log.error,
            telemetria.VEREDITO_ATENCAO: log.warning,
        }.get(registo.veredito, log.info)
        emoji = {
            telemetria.VEREDITO_ANOMALIA: "🔴",
            telemetria.VEREDITO_ATENCAO: "🟡",
        }.get(registo.veredito, "🟢")
        nivel(
            "%s [Saúde] %s — %s | fontes %s/%s ok, %s erro, %s vazias, %s bloqueadas | "
            "304=%s | itens: %s novos, %s filtrados, %s publicados, %s alertas | "
            "entregas falhadas=%s | traduções degradadas=%s | %.1fs | trigger=%s",
            emoji, registo.veredito, registo.motivo,
            registo.fontes_ok, registo.fontes_total, registo.fontes_com_erro,
            registo.fontes_vazias, registo.fontes_bloqueadas, registo.cache_304,
            registo.itens_novos, registo.itens_filtrados, registo.itens_publicados,
            registo.alertas_html, registo.entregas_falhadas,
            registo.traducoes_degradadas, registo.duracao_s, registo.trigger,
        )
        _log_next_run()


# =========================================================
# LOOP MANAGEMENT
# =========================================================

# Loop global que será iniciado pelo bot
loop_task = None

def start_scheduler(bot: discord.Client):
    """
    PROPÓSITO DE NEGÓCIO: pôr de pé o agendador que dispara a varredura de notícias de
    tempos em tempos. É chamado do `on_ready`, que o discord.py reexecuta a cada
    reconexão do gateway — não apenas no arranque.

    INVARIANTES DO DOMÍNIO: existe no máximo UM loop de varredura vivo por processo.
    Como o `@tasks.loop` é declarado dentro desta função, cada chamada criava um objeto
    `Loop` novo — não havia o `RuntimeError` de "already launched" que protegeria um loop
    de módulo, o loop anterior não era cancelado e o global só perdia a referência.
    Medido: duas chamadas => 2 tasks `news_scan_loop` ativas, uma por reconexão.

    COMPORTAMENTO EM CASO DE FALHA: se já houver loop em execução, não cria outro nem
    levanta exceção — regista em log e devolve o controlo, deixando o agendador existente
    intacto. Nunca interrompe o `on_ready` (o anúncio de versão vem logo a seguir).
    """
    global loop_task

    if loop_task is not None and loop_task.is_running():
        log.info(
            "🔄 [Scheduler] Agendador já em execução (on_ready repetido por reconexão). "
            "Mantendo o loop atual."
        )
        return

    @tasks.loop(minutes=LOOP_MINUTES)
    async def news_scan_loop():
        try:
            await run_scan_once(bot, trigger="loop")
        except Exception as e:
            log.exception(
                f"🔥 [Scanner] Exceção não tratada no loop de notícias: {type(e).__name__}: {e}"
            )

    @news_scan_loop.error
    async def news_scan_loop_error(error):
        log.exception(f"💀 [Scheduler] Erro no loop de varredura (tasks.loop): {error}")

    @news_scan_loop.before_loop
    async def _before_loop():
        await bot.wait_until_ready()

    loop_task = news_scan_loop
    loop_task.start()
    interval_h = LOOP_MINUTES // 60
    log.info(
        f"🔄 [Scheduler] Agendador iniciado — intervalo de varredura: {interval_h}h ({LOOP_MINUTES} min)"
    )
