"""
HTML Monitor - Detects changes in static websites (e.g. game news sites).
"""
import ssl
import logging
import hashlib
import certifi
import aiohttp
import asyncio
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup
from settings import MAX_CONCURRENT_FEEDS

from utils.storage import p, load_json_safe, save_json_safe
from utils.security import validate_url, sanitize_log_message
from utils.http import get_robust_headers

log = logging.getLogger("GameBot")

# Tags to ignore during hash calculation (noise reduction)
IGNORE_TAGS = ['script', 'style', 'meta', 'noscript', 'iframe', 'svg']
# Classes/IDs often used for ads or dynamic widgets
IGNORE_SELECTORS = ['.ad', '.advertisement', '.widget', '.cookie-consent']

# Exponential backoff: delays em segundos (tentativa 1, 2, 3)
HTML_FETCH_BACKOFF = [1, 2, 4]
HTML_FETCH_MAX_RETRIES = 3

def _extract_title_and_hash(content: str) -> tuple[str, str]:
    """Parse/limpa HTML e devolve (title, sha256 do texto). Função síncrona pesada
    (BeautifulSoup) — deve rodar em executor para não bloquear o event loop."""
    soup = BeautifulSoup(content, "html.parser")

    # Remove noise tags
    for tag in soup(IGNORE_TAGS):
        tag.decompose()

    # Remove noise classes (Safe attempt)
    for selector in IGNORE_SELECTORS:
        for match in soup.select(selector):
            match.decompose()

    # Get text content only (ignoring HTML structure changes)
    text_content = soup.get_text(separator=" ", strip=True)
    page_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()

    # soup.title.string pode ser None mesmo com <title> presente
    title = "No Title"
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    return title, page_hash


async def _get_page_content(
    session: aiohttp.ClientSession, url: str, headers: Dict[str, str]
) -> tuple[int, str | None]:
    """GET com aiohttp; devolve (status, corpo ou None se != 200). Segue redirects."""
    async with session.get(url, headers=headers, allow_redirects=True) as resp:
        if resp.status != 200:
            return resp.status, None
        return resp.status, await resp.text()


async def fetch_page_hash(
    session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore | None = None
) -> tuple[str, str, str]:
    """
    Fetches a page, cleans it, and returns (url, title, hash).
    O parse/hash (BeautifulSoup) roda em executor; downloads concorrentes são limitados
    pelo semáforo (evita baixar dezenas de páginas HTML inteiras ao mesmo tempo).
    """
    # Validação de segurança (anti-SSRF) uma única vez, antes das tentativas
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        log.warning(sanitize_log_message(f"🔒 URL bloqueada por segurança no HTML Monitor: {url} - {error_msg}"))
        return url, "", ""

    for attempt in range(HTML_FETCH_MAX_RETRIES):
        try:
            headers = get_robust_headers()
            if sem is not None:
                async with sem:
                    status, content = await _get_page_content(session, url, headers)
            else:
                status, content = await _get_page_content(session, url, headers)

            if content is None:
                log.debug(f"HTML Monitor: {url} returned {status}")
                return url, "", ""

            loop = asyncio.get_running_loop()
            title, page_hash = await loop.run_in_executor(None, _extract_title_and_hash, content)
            return url, title, page_hash

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < HTML_FETCH_MAX_RETRIES - 1:
                delay = HTML_FETCH_BACKOFF[attempt]
                log.debug(f"HTML Monitor: retry em {delay}s para '{url}' (tentativa {attempt + 1}): {e}")
                await asyncio.sleep(delay)
            else:
                log.warning(sanitize_log_message(f"🌐 Erro de conexão no HTML Monitor para '{url}' após {HTML_FETCH_MAX_RETRIES} tentativas: {e}"))
                return url, "", ""
        except Exception as e:
            if attempt < HTML_FETCH_MAX_RETRIES - 1:
                delay = HTML_FETCH_BACKOFF[attempt]
                log.debug(f"HTML Monitor: retry em {delay}s para '{url}' (tentativa {attempt + 1}): {e}")
                await asyncio.sleep(delay)
            else:
                log.warning(sanitize_log_message(f"⚠️ Erro inesperado no HTML Monitor para '{url}': {type(e).__name__}: {e}"), exc_info=True)
                return url, "", ""

    return url, "", ""

async def check_official_sites(
    current_state: Dict[str, str],
    full_state: Dict | None = None,
) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """
    Checks official sites for changes.
    Args:
        current_state: Dict {url: last_hash}
        full_state: Estado completo (opcional); se fornecido, atualiza source_failures e loga saúde.
    Returns:
        (updates_list, new_state)
    """
    import time
    sources = load_json_safe(p("sources.json"), {})
    urls = sources.get("official_sites_reference_(not_rss)", [])

    if not urls:
        return [], current_state

    headers = get_robust_headers()

    updates = []
    new_state = current_state.copy()
    failures = full_state.setdefault("source_failures", {}) if full_state else {}

    # Limita downloads concorrentes (antes: N sites baixados ao mesmo tempo, sem limite)
    sem = asyncio.Semaphore(MAX_CONCURRENT_FEEDS)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout, connector=connector) as session:
        tasks = [fetch_page_hash(session, url, sem) for url in urls]
        results = await asyncio.gather(*tasks)

        for url, title, page_hash in results:
            if not page_hash:
                # Falha: incrementar contador e logar se >= 3
                rec = failures.setdefault(url, {"count": 0, "last_error": "connection/parse failure", "last_ts": 0})
                rec["count"] = rec.get("count", 0) + 1
                rec["last_error"] = "connection or non-200"
                rec["last_ts"] = time.time()
                if rec["count"] >= 3:
                    log.error(
                        sanitize_log_message(f"🔴 [Source Health] Fonte HTML falhou {rec['count']} vezes: {url} | last_error={rec.get('last_error')}")
                    )
                continue

            # Sucesso: resetar contador
            if url in failures:
                failures[url]["count"] = 0

            last_hash = current_state.get(url)

            if not last_hash:
                new_state[url] = page_hash
                log.info(f"HTML Monitor: Initialized hash for {url}")
                continue

            if page_hash != last_hash:
                log.info(f"HTML Monitor: CHANGE DETECTED in {url}")
                updates.append({
                    "title": f"🔄 Update: {title}",
                    "link": url,
                    "summary": "Official site content has changed. Please check for new announcements.",
                })
                new_state[url] = page_hash

    return updates, new_state
