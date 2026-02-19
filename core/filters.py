"""
Filters module - News filtering and categorization logic.
"""
from typing import Dict, List, Any
from utils.html import clean_html


# =========================================================
# FILTROS / CATEGORIAS (bot de notícias de jogos)
# =========================================================

CAT_MAP = {
    "gunpla":  ["gunpla", "model kit", "kit", "ver.ka", "p-bandai", "premium bandai", "hg ", "mg ", "rg ", "pg ", "sd ", "fm ", "re/100"],
    "filmes":  ["anime", "episode", "movie", "film", "pv", "trailer", "teaser", "series", "season", "seed freedom", "witch from mercury", "hathaway"],
    "games":   ["game", "steam", "ps5", "xbox", "gbo2", "battle operation", "breaker", "gundam breaker"],
    "musica":  ["music", "ost", "soundtrack", "album", "opening", "ending"],
    "fashion": ["fashion", "clothing", "apparel", "t-shirt", "hoodie", "jacket", "merch"],
}

FILTER_OPTIONS = {
    "todos": ("TUDO", "🌟"),
    "gunpla": ("Gunpla", "🤖"),
    "filmes": ("Filmes", "🎬"),
    "games": ("Games", "🎮"),
    "musica": ("Música", "🎵"),
    "fashion": ("Fashion", "👕"),
}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

import re

def _contains_any(text: str, keywords: List[str]) -> bool:
    """
    Verifica se alguma keyword está presente no texto usando Regex.
    
    Usa word boundaries (\b) para evitar matches parciais (ex: 'wing' em 'drawing').
    Suporta plural opcional ('s?').
    Protege '00' de match em horários (12:00) usando negative lookbehind (?<!:).
    
    Args:
        text: Texto a verificar (já em lowercase)
        keywords: Lista de palavras-chave (em lowercase)
    
    Returns:
        True se pelo menos uma keyword foi encontrada
    """
    if not keywords:
        return False

    # Escapa keywords para segurança no regex
    # Monta padrão: (?<!:)\b(?:kw1|kw2|...|kwn)s?\b
    escaped_kws = [re.escape(k) for k in keywords]
    pattern_str = r'(?<!:)\b(?:' + '|'.join(escaped_kws) + r')s?\b'
    
    return bool(re.search(pattern_str, text))


def match_intel(guild_id: str, title: str, summary: str, config: Dict[str, Any]) -> bool:
    """
    Decide se notícia deve ir para a guild.

    Lógica:
      1. Exige filtros configurados
      2. "todos" libera tudo
      3. Senão, precisa bater em pelo menos uma categoria selecionada

    Args:
        guild_id: ID da guild
        title: Título da notícia
        summary: Resumo da notícia
        config: Configuração carregada

    Returns:
        True se notícia deve ser postada
    """
    g = config.get(str(guild_id), {})
    filters = g.get("filters", [])

    if not isinstance(filters, list) or not filters:
        return False

    content = f"{clean_html(title)} {clean_html(summary)}".lower()

    # "todos" libera tudo
    if "todos" in filters:
        return True

    # Verifica categorias específicas
    for f in filters:
        kws = CAT_MAP.get(f, [])
        if kws and _contains_any(content, kws):
            return True

    return False
