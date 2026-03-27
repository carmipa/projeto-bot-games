"""
URLs para discord.ui.Button(style=link).

A API do Discord só aceita esquemas http, https e discord — mailto:, javascript:, etc. falham com 400.
O comprimento máximo da URL do botão é 512 caracteres.
"""
from __future__ import annotations

from urllib.parse import quote

# Limite da API Discord para url em botões de link
LINK_BUTTON_URL_MAX = 512


def safe_https_button_url(url: str | None) -> str | None:
    """Retorna url se for http(s) utilizável em botão; caso contrário None."""
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        return None
    if len(u) > LINK_BUTTON_URL_MAX:
        return u[:LINK_BUTTON_URL_MAX]
    return u


def whatsapp_share_button_url(title: str, article_url: str) -> str:
    """https://api.whatsapp.com/... respeitando o teto de 512 caracteres."""
    base = "https://api.whatsapp.com/send?text="
    text = f"{title}\n\n{article_url}".strip()
    room = LINK_BUTTON_URL_MAX - len(base)
    if room < 8:
        return base + quote("News")
    while len(text) > 0:
        q = quote(text)
        if len(q) <= room:
            return base + q
        text = text[:-25] if len(text) > 25 else text[:-1]
    return base + quote("News")


def gmail_compose_button_url(title: str, article_url: str) -> str:
    """
    Abre composição no Gmail via HTTPS (nunca mailto:).
    Encurta título/corpo até a URL total <= 512.
    """
    prefix = "https://mail.google.com/mail/?view=cm&fs=1&su="
    sep = "&body="

    def build(su: str, body: str) -> str:
        return prefix + quote(su) + sep + quote(body)

    su_raw = (title or "Notícia")[:400]
    body_raw = f"Confira esta notícia:\n\n{article_url}"

    su, body = su_raw, body_raw
    url = build(su, body)
    while len(url) > LINK_BUTTON_URL_MAX and (len(su) > 5 or len(body) > len(article_url) + 15):
        if len(su) > 5:
            su = su[:-10] if len(su) > 15 else su[: max(1, len(su) - 1)]
        else:
            body = body[:-20]
        url = build(su, body)

    if len(url) > LINK_BUTTON_URL_MAX:
        return "https://mail.google.com/mail/"
    return url
