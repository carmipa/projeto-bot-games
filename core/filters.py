"""
Filters module - Verifica se a guild recebe notícias (canal configurado = recebe tudo).
Filtros por categoria foram removidos.
"""
import re
from typing import Dict, Any, List


def _contains_any(text: str, keywords: List[str]) -> bool:
    """Verifica se alguma keyword está no texto (word boundaries). Usado em testes."""
    if not keywords:
        return False
    escaped = [re.escape(k) for k in keywords]
    pattern = r'(?<!:)\b(?:' + '|'.join(escaped) + r')s?\b'
    return bool(re.search(pattern, text))


def match_intel(guild_id: str, title: str, summary: str, config: Dict[str, Any]) -> bool:
    """
    Decide se notícia deve ir para a guild.
    Se o servidor tem canal configurado, recebe todas as notícias (sem filtros).
    """
    g = config.get(str(guild_id), {})
    if not g.get("channel_id"):
        return False
    # Canal configurado = recebe tudo (filtros removidos do projeto)
    return True
