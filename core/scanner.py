"""
Scanner module - Feed fetching and processing logic.
"""
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
import time
import os
import random

# User-Agent de navegador real é obtido via utils.http.get_robust_headers()

import discord
from discord.ext import tasks

from settings import LOOP_MINUTES, BROWSER_USER_AGENTS
from utils.storage import p, load_json_safe, save_json_safe
from utils.html import clean_html
from utils.cache import load_http_state, save_http_state, get_cache_headers, update_cache_state
from utils.translator import translate_to_target, t
from utils.security import validate_url, sanitize_log_message
from utils.http import get_robust_headers
from core.stats import stats
from core.filters import should_post_to_guild, should_skip_by_content
from core.html_monitor import check_official_sites

log = logging.getLogger("GameBot")

# Lock global para impedir varreduras simultâneas
scan_lock = asyncio.Lock()


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


async def _fetch_youtube_channel_id_from_page(
    session: aiohttp.ClientSession,
    url: str,
    cache: Dict[str, str],
    timeout: aiohttp.ClientTimeout,
) -> str:
    """Faz GET na página do canal e extrai channelId do código fonte (fallback quando não está no mapa)."""
    try:
        headers = get_robust_headers() # Simula navegador real
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                log.debug(f"YouTube resolve: {url} retornou {resp.status}. Mantendo URL original.")
                return url
            html = await resp.text(errors="ignore")
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning(f"YouTube resolve: falha ao acessar {url}: {e}. Mantendo URL original.")
        return url

    # YouTube embute channelId no HTML (ytInitialData ou meta)
    m = re.search(r'"channelId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"', html)
    if not m:
        m = re.search(r'channel_id=([A-Za-z0-9_-]{24})', html)
    if not m:
        m = re.search(r'/channel/(UC[A-Za-z0-9_-]{22})', html)
    channel_id = m.group(1) if m else None

    if channel_id:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        cache[url] = feed_url
        log.info(f"YouTube: @ resolvido para feed RSS: {url} -> {feed_url}")
        return feed_url

    log.debug(f"YouTube: não foi possível extrair channel_id de {url}. Mantendo URL original.")
    return url


async def resolve_youtube_urls(
    session: aiohttp.ClientSession,
    urls: List[str],
    state: Dict[str, Any],
    timeout: aiohttp.ClientTimeout,
) -> List[str]:
    """Resolve todas as URLs de canal YouTube (@ ou /channel/) para URLs de feed RSS."""
    cache = state.setdefault("youtube_feed_cache", {})
    feed_map = _load_youtube_feed_map()
    resolved: List[str] = []
    for u in urls:
        if _is_youtube_url(u) and not _is_youtube_feed_url(u):
            r = await get_yt_rss(session, u, cache, timeout, feed_map)
            resolved.append(r)
        else:
            resolved.append(u)
    return resolved


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
        scan_start_time = time.time()
        # Limite de 125 minutos para que uma varredura não atropele a próxima e evite bloqueios do Discord
        MAX_SCAN_DURATION = 125 * 60 

        log.info(f"🔎 Iniciando varredura de notícias (GameBot)... (trigger={trigger})")

        config = load_json_safe(p("config.json"), {})
        
        # Verifica se há guilds configuradas
        if not config or not any(isinstance(v, dict) and v.get("channel_id") for v in config.values()):
            log.warning("⚠️ Nenhuma guild configurada com 'channel_id'. Use /set_canal ou /dashboard para configurar.")
            _log_next_run()
            return
            
        urls = load_sources()
        if not urls:
            log.warning("Nenhuma URL válida em sources.json.")
            _log_next_run()
            return

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
            log.info("🧹 [Auto-Cleanup] Executando limpeza de cache (Ciclo de 7 dias)")
            state["dedup"] = {}  # Limpa histórico de mensagens enviadas para forçar refresh se necessário
            state["last_cleanup"] = now_ts
            # Nota: Não limpamos http_cache para manter eficiência, apenas o dedup de posts
        
        # Referências locais para facilitar acesso
        http_cache = state["http_cache"]
        html_hashes = state["html_hashes"]
        # history_set ainda usado como fallback global, mas dedup por site é prioritário
        history_list, history_set = load_history()

        # SSL Configuration
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        base_headers = {
            "User-Agent": BROWSER_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        timeout = aiohttp.ClientTimeout(total=40) # Aumentado timeout para feeds lentos
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)

        sent_count = 0
        cache_hits = 0
        
        MAX_CONCURRENT_FEEDS = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FEEDS)
        RSS_BACKOFF = [1, 2, 4]  # Exponential backoff (segundos)
        RSS_MAX_RETRIES = 3
        source_failures = state["source_failures"]

        async def fetch_and_process_feed(session, url):
            nonlocal cache_hits, state

            async with semaphore:
                # Validação de segurança: anti-SSRF
                is_valid, error_msg = validate_url(url)
                if not is_valid:
                    log.warning(sanitize_log_message(f"🔒 URL bloqueada por segurança: {url} - {error_msg}"))
                    return None

                if "youtube.com" in url or "youtu.be" in url:
                    await asyncio.sleep(2)

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

                            update_cache_state(url, resp.headers, http_cache)
                            text = await resp.text(errors="ignore")

                        loop = asyncio.get_running_loop()
                        feed = await loop.run_in_executor(None, lambda: feedparser.parse(text))

                        entries = getattr(feed, "entries", []) or []

                        if not entries and resp.status == 200:
                            log.warning(f"⚠️ Feed retornou 200 OK mas 0 entradas: {url}")

                        if url in source_failures:
                            source_failures[url]["count"] = 0
                        return (url, entries)

                    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                        last_error = e
                        if attempt < RSS_MAX_RETRIES - 1:
                            delay = RSS_BACKOFF[attempt]
                            log.debug(f"Retry em {delay}s para feed '{url}' (tentativa {attempt + 1}): {e}")
                            await asyncio.sleep(delay)
                        else:
                            rec = source_failures.setdefault(url, {"count": 0, "last_error": "", "last_ts": 0})
                            rec["count"] = rec.get("count", 0) + 1
                            rec["last_error"] = str(e)
                            rec["last_ts"] = time.time()
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
                            log.debug(f"Retry em {delay}s para feed '{url}' (tentativa {attempt + 1}): {e}")
                            await asyncio.sleep(delay)
                        else:
                            rec = source_failures.setdefault(url, {"count": 0, "last_error": "", "last_ts": 0})
                            rec["count"] = rec.get("count", 0) + 1
                            rec["last_error"] = f"{type(e).__name__}: {e}"
                            rec["last_ts"] = time.time()
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
            tasks = [fetch_and_process_feed(session, url) for url in resolved_urls]
            results = await asyncio.gather(*tasks)
            
            for result in results:
                if result is None:
                    continue
                    
                url, entries = result
                
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

                    # Cold Start: Respeitando pedido de "sem limitação", removemos a trava rígida de 3 posts.
                    # O dedup cuidará das duplicatas nas próximas rodadas.
                    # if is_cold_start and feed_posted_count >= 3: continue # Removido

                    # Filtragem por data: nunca publicar notícias com mais de 7 dias (inclui Cold Start)
                    entry_dt = parse_entry_dt(entry)
                    if entry_dt:
                        now = datetime.now(entry_dt.tzinfo) if entry_dt.tzinfo else datetime.now()
                        age = now - entry_dt
                        if age.days > 7:
                            log.debug(f"👴 [Old] Ignorado (idade {age.days}d, máx. 7 dias): {link}")
                            continue

                    title = entry.get("title") or ""
                    summary = entry.get("summary") or entry.get("description") or ""

                    # Filtro de conteúdo (LIXO_FILTER): descarta ruído e loga
                    if should_skip_by_content(title, summary):
                        log.debug(f"🛡️ [Filtro] Ruído filtrado: {title[:50]}...")
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
                            continue

                    # GRC: vídeos YouTube com mais de 12 min são descartados (podcasts/entrevistas), exceto Official Gameplay / Reveal
                    if "youtube.com" in link or "youtu.be" in link:
                        duration_sec = get_youtube_duration_seconds(entry)
                        if duration_sec is not None and duration_sec > 12 * 60:
                            title_lower = (title or "").lower()
                            if "official gameplay" not in title_lower and "reveal" not in title_lower:
                                log.debug(f"🛡️ [Filtro] Vídeo longo descartado ({duration_sec // 60} min): {title[:50]}...")
                                continue

                    posted_anywhere = False

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
                            continue

                        t_clean = clean_html(title).strip()
                        s_clean = clean_html(summary).strip()[:2000]

                        # Tradução
                        target_lang = "en_US"
                        if str(gid) in config and "language" in config[str(gid)]:
                            target_lang = config[str(gid)]["language"]
                        
                        t_translated = await translate_to_target(t_clean, target_lang)
                        s_translated = await translate_to_target(s_clean, target_lang)

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
                            from utils.translator import t
                            # Data/hora oficial da matéria ou vídeo (quando o feed fornece)
                            pub_dt = entry_dt if entry_dt else None
                            embed_ts = pub_dt if pub_dt else datetime.now()
                            # Discord exige datetime timezone-aware para timestamp do embed
                            if embed_ts.tzinfo is None:
                                embed_ts = embed_ts.replace(tzinfo=timezone.utc)

                            # Embed para notícias
                            embed = discord.Embed(
                                title=t_translated[:256],
                                description=s_translated,
                                url=link,
                                color=embed_color,
                                timestamp=embed_ts
                            )
                            author_name = t.get('embed.author', lang=target_lang)
                            # Usa avatar do bot se disponível
                            icon_url = bot.user.avatar.url if bot.user and bot.user.avatar else None
                            embed.set_author(name=author_name, icon_url=icon_url)

                            source_domain = urlparse(link).netloc
                            footer_text = t.get('embed.source', lang=target_lang, source=source_domain)
                            if pub_dt:
                                date_str = pub_dt.strftime("%d/%m/%Y %H:%M")
                                footer_text = f"{footer_text} • {t.get('embed.published_at', lang=target_lang, date=date_str)}"
                            embed.set_footer(text=footer_text)
                            
                            if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                                try:
                                    thumb_url = entry.media_thumbnail[0].get("url")
                                    # Se for mídia (video), as vezes a thumb do RSS é ruim ou duplica o player.
                                    # Mas vamos manter por enquanto.
                                    if thumb_url:
                                        embed.set_thumbnail(url=thumb_url)
                                except (IndexError, AttributeError, KeyError) as e:
                                    log.debug(f"Erro ao obter thumbnail da entrada: {e}")
                                except Exception as e:
                                    log.warning(f"Erro inesperado ao processar thumbnail: {e}")
                            
                            # Se for mídia, mandamos o LINK no content para o Discord gerar o player nativo
                            # E NÃO mandamos o embed, pois o Discord prioriza o embed sobre o player
                            if is_media:
                                msg_content = f"📺 **{t_translated}**\n{link}"
                                embed_to_send = None
                            else:
                                msg_content = None
                                embed_to_send = embed
                            
                            await channel.send(content=msg_content, embed=embed_to_send)

                            posted_anywhere = True
                            sent_count += 1
                            if is_cold_start:
                                feed_posted_count += 1
                            # Delay anti-spam (GRC-Refined): evita rate limit e detecção de spam pelo Discord
                            # Aumentado para 2.5s para maior segurança em varreduras longas
                            await asyncio.sleep(2.5)

                        except discord.Forbidden as e:
                            log.error(f"🚫 Sem permissão para enviar mensagem no canal {channel_id} (guild {gid}): {e}")
                        except discord.HTTPException as e:
                            log.error(f"🌐 Erro HTTP ao enviar mensagem no canal {channel_id}: {e.status} - {e.text}")
                        except discord.InvalidArgument as e:
                            log.error(f"⚠️ Argumento inválido ao criar embed/mensagem: {e}")
                        except Exception as e:
                            log.exception(f"❌ Falha inesperada ao enviar no canal {channel_id} (guild {gid}): {type(e).__name__}: {e}")

                    if posted_anywhere:
                        # Adiciona ao dedup específico e global
                        state["dedup"][url].append(link)
                        history_set.add(link)
                        history_list.append(link)

        # =========================================================
        # HTML MONITOR RUN (SITE WATCHER)
        # =========================================================
        try:
            log.info("🔎 Verificando sites oficiais (HTML Watcher)...")
            # Passa apenas o dicionário de hashes para o monitor
            # Se check_official_sites retornar updates, atualizamos o state principal
            html_updates, new_hashes = await check_official_sites(html_hashes, full_state=state)
            
            if html_updates:
                log.info(f"✨ {len(html_updates)} atualizações em sites oficiais detectadas!")
                state["html_hashes"] = new_hashes
                # Dispatch updates
                for update in html_updates:
                    u_title = update["title"]
                    u_link = update["link"]
                    u_summary = update.get("summary", "")
                    
                    for gid, gdata in config.items():
                        if not isinstance(gdata, dict): continue
                        
                        channel_id = gdata.get("channel_id")
                        if not channel_id: continue

                        try:
                            channel = bot.get_channel(int(channel_id))
                        except (ValueError, TypeError) as e:
                            log.warning(
                                f"[HTML Monitor] Canal inválido para guild {gid} (channel_id={channel_id}): {e}"
                            )
                            channel = None
                        
                        # Aplica filtro por guild (canal configurado) também no monitor HTML
                        if not should_post_to_guild(str(gid), u_title, u_summary, config):
                            log.debug(f"🛡️ [Filtro HTML] Guild {gid} bloqueou site: {u_title}")
                            continue

                        if channel:
                            try:
                                await channel.send(f"⚠️ **GameBot — Alerta**\n{u_title}\n{u_link}")
                                sent_count += 1
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

        # Salva TUDO em um único arquivo de forma atômica/safe
        save_history(history_list)
        save_json_safe(state_file, state)
        # Removido save_http_state duplicado que causava race condition
        
        stats.scans_completed += 1
        stats.news_posted += sent_count
        stats.cache_hits_total += cache_hits
        stats.last_scan_time = datetime.now()
        
        log.info(f"✅ Varredura concluída. (enviadas={sent_count}, cache_hits={cache_hits}/{len(urls)}, trigger={trigger})")
        _log_next_run()


# =========================================================
# LOOP MANAGEMENT
# =========================================================

# Loop global que será iniciado pelo bot
loop_task = None

def start_scheduler(bot: discord.Client):
    """Inicia o loop agendado."""
    global loop_task
    
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
