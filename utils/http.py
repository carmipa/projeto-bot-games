import random
from typing import Dict
from settings import BROWSER_USER_AGENTS

def get_robust_headers() -> Dict[str, str]:
    """Gera um conjunto de headers robustos para simular um navegador real."""
    ua = random.choice(BROWSER_USER_AGENTS)
    referers = [
        "https://www.google.com/",
        "https://www.bing.com/",
        "https://duckduckgo.com/",
        "https://t.co/",
        "https://www.facebook.com/",
        "https://news.google.com/",
        "https://www.reddit.com/",
        "https://www.youtube.com/"
    ]
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": random.choice(referers),
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }
