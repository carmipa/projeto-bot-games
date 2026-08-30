import random
from typing import Dict
from settings import BROWSER_USER_AGENTS

def get_robust_headers() -> Dict[str, str]:
    """Gera um conjunto de headers robustos para simular um navegador real."""
    # B311: `random` nao-criptografico e adequado aqui — o User-Agent e camuflagem contra
    # bloqueio de scraping, nao segredo nem decisao de seguranca.
    ua = random.choice(BROWSER_USER_AGENTS)  # nosec B311
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
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": random.choice(referers),  # nosec B311
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "max-age=0"
    }
