"""
Cache utilities - HTTP caching with ETag and Last-Modified support.

O cache HTTP vive dentro de `state["http_cache"]`, NÃO na raiz do `state.json`. As funções
`load_http_state()`/`save_http_state()` que existiam aqui tratavam o `state.json` inteiro
como se fosse o mapa de ETags: `save_http_state()` gravava o dicionário de cache por cima
do ficheiro todo e apagaria `dedup`, `html_hashes` e `last_announced_hash` — repostagem em
massa de tudo o que o bot já publicou. Não eram chamadas em lado nenhum (a varredura usa
`state["http_cache"]` diretamente), e foram removidas em vez de documentadas: caminho
errado que continua disponível e parece certo acaba por ser usado.
"""
from typing import Dict, Any


def get_cache_headers(url: str, state: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """
    Retorna headers de cache para uma URL se disponíveis.
    
    Args:
        url: URL do feed
        state: Estado HTTP carregado
    
    Returns:
        Headers If-None-Match e/ou If-Modified-Since se disponíveis
    """
    headers = {}
    url_state = state.get(url, {})
    
    if "etag" in url_state and url_state["etag"]:
        headers["If-None-Match"] = url_state["etag"]
    
    if "last_modified" in url_state and url_state["last_modified"]:
        headers["If-Modified-Since"] = url_state["last_modified"]
    
    return headers


def update_cache_state(url: str, response_headers: Any, state: Dict[str, Dict[str, str]]) -> None:
    """
    Atualiza state com ETags e Last-Modified da resposta HTTP.
    
    Args:
        url: URL do feed
        response_headers: Headers da resposta HTTP
        state: Estado HTTP a atualizar (modificado in-place)
    """
    if url not in state:
        state[url] = {}
    
    # Salva ETag se presente (case-insensitive)
    if "ETag" in response_headers:
        state[url]["etag"] = response_headers["ETag"]
    elif "etag" in response_headers:
        state[url]["etag"] = response_headers["etag"]
    
    # Salva Last-Modified se presente (case-insensitive)
    if "Last-Modified" in response_headers:
        state[url]["last_modified"] = response_headers["Last-Modified"]
    elif "last-modified" in response_headers:
        state[url]["last_modified"] = response_headers["last-modified"]
