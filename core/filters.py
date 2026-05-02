"""
Filters module - Verifica se a guild recebe notícias e filtra ruído (eSports, reviews, etc.).
Foco: trailers, anúncios AAA e lançamentos oficiais. Camada de descarte agressiva (LIXO_FILTER).
"""
import re
from typing import Dict, Any, List

# Lista de exclusão agressiva: se o título (ou resumo) contiver qualquer termo, descarta e loga "Ruído filtrado"
LIXO_FILTER = [
    # Franquia excluída do escopo do bot (jogos / mídia)
    "gundam",

    # eSports / competitivo
    "esports", "e-sports", "tournament", "tournaments", "highlights",
    "championship", "championships", "campeonato", "international championships",
    "vct", "valorant", "champions tour", "euic", "vgc",

    # Conteúdo de filmes / featurettes / trailers não-jogos
    "featurette", "anniversary trailer", "25th anniversary",

    # Conteúdo editorial/opinião/patrocinado
    "review", "reviews", "analise", "análise", "opiniao", "opinião", "opinion",
    "entrevista", "interview", "q&a", "qa", "q and a",
    "podcast", "unboxing",
    "presented by", "sponsored by", "you decide",
    "best mobile game of all time", "best game of all time",

    # Guias e walkthroughs
    "guide", "guia", "tips", "how to", "walkthrough", "gameplay walkthrough",

    # Lives e bastidores
    "live stream", "livestream", "streaming",
    "bastidores", "behind the scenes",

    # Outras séries recorrentes de noticiário geral
    "daily fix", "networking and security",
]

# Compatibilidade: NOISE_KEYWORDS = LIXO_FILTER + extras que não estão em LIXO_FILTER
NOISE_KEYWORDS = LIXO_FILTER + [
    "competitive", "competition", "championship", "finals", "grand finals", "playoffs",
    "tier list", "ranking", "editorial", "streamer",
]

# Normalização: busca case-insensitive e em título + resumo concatenados
def _normalize_for_filter(text: str) -> str:
    return (text or "").lower().strip()


def should_skip_by_content(title: str, summary: str) -> bool:
    """
    Retorna True se a notícia for considerada "ruído" (LIXO_FILTER).
    Descarta e deve ser logado como "Ruído filtrado".
    Foco do bot: trailers, announcements e official reveals apenas.
    """
    raw = f"{_normalize_for_filter(title)} {_normalize_for_filter(summary)}"
    if not raw:
        return False
    for kw in LIXO_FILTER:
        if kw in raw:
            return True
    return False


def _contains_any(text: str, keywords: List[str]) -> bool:
    """Verifica se alguma keyword está no texto (word boundaries). Usado em testes."""
    if not keywords:
        return False
    escaped = [re.escape(k) for k in keywords]
    pattern = r'(?<!:)\b(?:' + '|'.join(escaped) + r')s?\b'
    return bool(re.search(pattern, text))


def should_post_to_guild(guild_id: str, title: str, summary: str, config: Dict[str, Any]) -> bool:
    """
    Decide se notícia deve ir para a guild.
    Se o servidor tem canal configurado, recebe todas as notícias que passaram no filtro de conteúdo.
    """
    g = config.get(str(guild_id), {})
    if not g.get("channel_id"):
        return False
    # Canal configurado = recebe tudo (filtro de ruído já foi aplicado antes no scanner)
    return True
