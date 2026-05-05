# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# Obrigatório
TOKEN = os.getenv("DISCORD_TOKEN")

# Operação (opcional via env)
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
# Intervalo do scanner: 24 em 24 horas (1440 minutos)
try:
    LOOP_MINUTES = int(os.getenv("LOOP_MINUTES", "1440"))
except ValueError:
    LOOP_MINUTES = 1440

# Logging Level (INFO, DEBUG, WARNING, ERROR)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# -------------------------------
# Feed ingestion hardening (anti-bloqueio / anti-scraping agressivo)
# -------------------------------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


MAX_CONCURRENT_FEEDS = _env_int("MAX_CONCURRENT_FEEDS", 5)
FEED_TIMEOUT_SECONDS = _env_int("FEED_TIMEOUT_SECONDS", 40)
RSS_MAX_RETRIES = _env_int("RSS_MAX_RETRIES", 3)
RSS_RETRY_BACKOFF_BASE = _env_float("RSS_RETRY_BACKOFF_BASE", 1.0)
MAX_ENTRIES_PER_FEED = _env_int("MAX_ENTRIES_PER_FEED", 10)
MAX_NEWS_AGE_DAYS = _env_int("MAX_NEWS_AGE_DAYS", 7)
FEED_FETCH_JITTER_MIN = _env_float("FEED_FETCH_JITTER_MIN", 0.3)
FEED_FETCH_JITTER_MAX = _env_float("FEED_FETCH_JITTER_MAX", 1.2)

# Fontes genéricas (YouTube agregadores) exigem sinal semântico no título
STRICT_GENERIC_YOUTUBE = os.getenv("STRICT_GENERIC_YOUTUBE", "1") == "1"

# HTTP / Feeds – User-Agent rotativo para se parecer com usuário navegando real (Evita bloqueios)
BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0"
]
