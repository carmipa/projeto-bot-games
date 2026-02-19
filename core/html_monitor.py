"""
HTML Monitor - Detects changes in static websites (e.g. game news sites).
"""
import ssl
import logging
import hashlib
import asyncio
import httpx

import certifi
from typing import List, Dict, Tuple
from bs4 import BeautifulSoup

from utils.storage import p, load_json_safe, save_json_safe
from utils.security import validate_url

log = logging.getLogger("GameBot")

# Lista rotativa de User-Agents para evitar bloqueios (Rockstar, Activision, etc.)
ROTATING_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
_ua_index = 0

def _next_user_agent() -> str:
    global _ua_index
    ua = ROTATING_USER_AGENTS[_ua_index % len(ROTATING_USER_AGENTS)]
    _ua_index += 1
    return ua

# Tags to ignore during hash calculation (noise reduction)
IGNORE_TAGS = ['script', 'style', 'meta', 'noscript', 'iframe', 'svg']
# Classes/IDs often used for ads or dynamic widgets
IGNORE_SELECTORS = ['.ad', '.advertisement', '.widget', '#clock', '.timestamp', '.cookie-consent']

# Exponential backoff: delays em segundos (tentativa 1, 2, 3)
HTML_FETCH_BACKOFF = [1, 2, 4]
HTML_FETCH_MAX_RETRIES = 3

async def fetch_page_hash(
    client: httpx.AsyncClient, url: str, use_ua: str | None = None
) -> tuple[str, str, str]:
    """
    Fetches a page, cleans it, and returns (url, title, hash).
    Usa User-Agent rotativo e exponential backoff em falhas de conexão.
    Returns (url, "", "") on failure.
    """
    ua = use_ua or _next_user_agent()
    last_error: Exception | None = None
    for attempt in range(HTML_FETCH_MAX_RETRIES):
        try:
            # Validação de segurança: anti-SSRF
            is_valid, error_msg = validate_url(url)
            if not is_valid:
                log.warning(f"🔒 URL bloqueada por segurança no HTML Monitor: {url} - {error_msg}")
                return url, "", ""

            resp = await client.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"},
            )
            if resp.status_code != 200:
                log.debug(f"HTML Monitor: {url} returned {resp.status_code}")
                return url, "", ""

            content = resp.text

            # Parse and Clean
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

            # Hash calculation
            page_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
            title = soup.title.string.strip() if soup.title else "No Title"

            return url, title, page_hash

        except httpx.RequestError as e:
            last_error = e
            if attempt < HTML_FETCH_MAX_RETRIES - 1:
                delay = HTML_FETCH_BACKOFF[attempt]
                log.debug(f"HTML Monitor: retry em {delay}s para '{url}' (tentativa {attempt + 1}): {e}")
                await asyncio.sleep(delay)
            else:
                log.warning(f"🌐 Erro de conexão no HTML Monitor para '{url}' após {HTML_FETCH_MAX_RETRIES} tentativas: {e}")
                return url, "", ""
        except Exception as e:
            last_error = e
            if attempt < HTML_FETCH_MAX_RETRIES - 1:
                delay = HTML_FETCH_BACKOFF[attempt]
                log.debug(f"HTML Monitor: retry em {delay}s para '{url}' (tentativa {attempt + 1}): {e}")
                await asyncio.sleep(delay)
            else:
                log.warning(f"⚠️ Erro inesperado no HTML Monitor para '{url}': {type(e).__name__}: {e}", exc_info=True)
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

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    updates = []
    new_state = current_state.copy()
    failures = full_state.setdefault("source_failures", {}) if full_state else {}

    async with httpx.AsyncClient(headers=headers, timeout=30.0, verify=certifi.where()) as client:
        tasks = [fetch_page_hash(client, url) for url in urls]
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
                        f"🔴 [Source Health] Fonte HTML falhou {rec['count']} vezes: {url} | last_error={rec.get('last_error')}"
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
