"""
Security utilities - URL validation, SSRF protection, input sanitization.
"""
import asyncio
import re
import ipaddress
import socket
from urllib.parse import urlparse
from typing import Optional, List, Tuple
import logging

log = logging.getLogger("GameBot")

# IPs privados e locais que devem ser bloqueados (anti-SSRF)
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
]

# Domínios locais que devem ser bloqueados
BLOCKED_DOMAINS = [
    "localhost",
    "127.0.0.1",
    # Falso positivo do bandit (B104): esta e a lista de dominios BLOQUEADOS. A string
    # aqui PROIBE o endereco, nao vincula o servidor a ele.
    "0.0.0.0",  # nosec B104
    "::1",
]

# Schemas permitidos
ALLOWED_SCHEMES = ["http", "https"]


def is_private_ip(ip: str) -> bool:
    """
    Verifica se um IP é privado/local.
    
    Args:
        ip: Endereço IP (IPv4 ou IPv6)
    
    Returns:
        True se o IP for privado/local
    """
    try:
        ip_obj = ipaddress.ip_address(ip)
        for network in PRIVATE_IP_RANGES:
            if ip_obj in network:
                return True
        return False
    except ValueError:
        return False


def _validar_estrutura(url: str, allowed_domains: Optional[List[str]]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Parte SÍNCRONA e barata da validação: esquema, netloc, domínio bloqueado, whitelist e
    caracteres de controle. Não toca na rede.

    Returns:
        (ok, erro, host) — `host` só vem preenchido quando ok=True e ainda falta a
        checagem de DNS. Separar as duas metades existe para que o caminho assíncrono
        possa resolver o DNS sem bloquear o event loop.
    """
    if not url or not isinstance(url, str):
        return False, "URL inválida: deve ser uma string não vazia", None

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        return False, "URL deve começar com http:// ou https://", None

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Erro ao fazer parse da URL: {e}", None

    if parsed.scheme not in ALLOWED_SCHEMES:
        return False, f"Esquema '{parsed.scheme}' não permitido. Use http:// ou https://", None

    if not parsed.netloc:
        return False, "URL deve conter um domínio ou IP válido", None

    netloc_without_port = parsed.netloc.split(":")[0]

    if netloc_without_port.lower() in BLOCKED_DOMAINS:
        return False, f"Domínio '{netloc_without_port}' não permitido (domínio local)", None

    if allowed_domains:
        domain_match = False
        for allowed in allowed_domains:
            if netloc_without_port.lower() == allowed.lower() or netloc_without_port.lower().endswith("." + allowed.lower()):
                domain_match = True
                break

        if not domain_match:
            return False, f"Domínio '{netloc_without_port}' não está na whitelist permitida", None

    suspicious_chars = ["\x00", "\r", "\n", "\t"]
    for char in suspicious_chars:
        if char in url:
            return False, "URL contém caracteres suspeitos", None

    return True, None, netloc_without_port


def _veredito_dns(host: str, enderecos: Optional[List[str]], erro_resolucao: Optional[BaseException]) -> Tuple[bool, Optional[str]]:
    """Aplica a política anti-SSRF sobre o resultado da resolução, venha ela de onde vier."""
    if erro_resolucao is not None:
        if isinstance(erro_resolucao, socket.gaierror):
            # Domínio inexistente ou rede fora: a própria conexão vai falhar depois.
            # Não é caso de bloquear como se fosse ataque.
            return True, None
        log.debug(f"Erro na resolução DNS para validação SSRF: {erro_resolucao}")
        # Erro inesperado na resolução: falha FECHADA.
        return False, "Erro ao validar o endereço (resolução DNS falhou)"

    for resolved_ip in enderecos or []:
        if is_private_ip(resolved_ip):
            return False, f"O endereço '{host}' resolve para um IP privado ({resolved_ip}) e não é permitido."
    return True, None


def validate_url(url: str, allowed_domains: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    PROPÓSITO DE NEGÓCIO: impedir que uma URL de `sources.json` (ou o `og:image` de um
    artigo de terceiro) faça o bot buscar um recurso da rede interna de quem o hospeda —
    o clássico SSRF. Toda URL que o bot vai baixar passa por aqui antes.

    INVARIANTES DO DOMÍNIO: esquema restrito a http/https; nome local explícito é
    recusado; o IP por trás do nome é conferido contra as faixas privadas, porque um
    domínio público pode apontar para 127.0.0.1. Erro inesperado na resolução falha
    FECHADO; nome inexistente passa (a conexão falha depois, e tratar NXDOMAIN como
    ataque só produziria ruído).

    COMPORTAMENTO EM CASO DE FALHA: devolve `(False, motivo)` — nunca levanta. Esta versão
    é SÍNCRONA e faz `socket.getaddrinfo`, que bloqueia. Dentro de corrotina, use
    `validate_url_async`: com dezenas de fontes por varredura, a soma dos DNS lentos
    trava o event loop e derruba o heartbeat do gateway do Discord.
    """
    ok, erro, host = _validar_estrutura(url, allowed_domains)
    if not ok or host is None:
        return ok, erro

    enderecos: Optional[List[str]] = None
    falha: Optional[BaseException] = None
    try:
        enderecos = [item[4][0] for item in socket.getaddrinfo(host, None)]
    except Exception as e:
        falha = e

    return _veredito_dns(host, enderecos, falha)


def imagem_publicavel(url: Optional[str]) -> Optional[str]:
    """
    PROPOSITO DE NEGOCIO: impedir que uma imagem ruim APAGUE a noticia. O Discord
    recusa o embed inteiro com 400 (error code 50035) quando a URL de imagem e
    malformada; a noticia falha em todas as guilds, nao entra no dedup e o ciclo
    seguinte tenta de novo -- para sempre. Guarda aplicada a TODA imagem do FEED
    antes do set_image/set_thumbnail (o og:image ja passa por validate_url_async;
    o caminho do feed estava descoberto -- medido 2026-09-18, portado dos irmaos).

    INVARIANTES DO DOMINIO: usa a parte ESTRUTURAL da validacao (_validar_estrutura)
    -- esquema http(s), host presente, dominio local recusado, sem caracteres de
    controle. NAO faz DNS: e chamada dentro do event loop (build_embed e corrotina),
    e getaddrinfo bloquearia o heartbeat do gateway. A imagem e buscada pelo
    Discord, nao pelo bot, entao validar FORMATO basta para o 50035; o SSRF do
    fetch ja e coberto por validate_url_async no caminho do og:image.

    COMPORTAMENTO EM CASO DE FALHA: devolve None (noticia sai sem imagem, desfecho
    seguro); nunca levanta.
    """
    if not url or not isinstance(url, str):
        return None
    limpa = url.strip()
    ok, _erro, _host = _validar_estrutura(limpa, None)
    if not ok:
        return None
    return limpa


async def validate_url_async(url: str, allowed_domains: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    PROPÓSITO DE NEGÓCIO: a mesma validação anti-SSRF de `validate_url`, para uso dentro
    do event loop. A varredura valida ~70 feeds e o HTML Monitor ~29 sites por ciclo.

    INVARIANTES DO DOMÍNIO: mesma política, mesmos vereditos — a única diferença é que a
    resolução usa `loop.getaddrinfo`, que não segura a thread do asyncio. Qualquer regra
    nova tem de entrar em `_validar_estrutura`/`_veredito_dns`, que as duas versões
    partilham; duas cópias da política divergiriam em silêncio.

    COMPORTAMENTO EM CASO DE FALHA: idêntico ao síncrono — devolve `(False, motivo)` e
    nunca levanta. Sem event loop em execução, `asyncio.get_running_loop()` levantaria
    `RuntimeError`, mas a função é uma corrotina: só há como aguardá-la dentro de um loop.
    """
    ok, erro, host = _validar_estrutura(url, allowed_domains)
    if not ok or host is None:
        return ok, erro

    loop = asyncio.get_running_loop()
    enderecos: Optional[List[str]] = None
    falha: Optional[BaseException] = None
    try:
        info = await loop.getaddrinfo(host, None)
        enderecos = [item[4][0] for item in info]
    except Exception as e:
        falha = e

    return _veredito_dns(host, enderecos, falha)


# Padrões ANCORADOS de segredo. Cada um exige um rótulo, um cabeçalho ou uma forma
# estrutural — nunca "sequência longa qualquer".
_PADROES_SENSIVEIS = [
    # token=..., secret: ..., api_key = ..., password=...
    # O valor para em espaço OU em '&': senão, num `?token=x&y=1`, o \S+ engolia o resto
    # da query string e o log perdia parâmetros que não são segredo.
    (re.compile(r'(?i)\b(discord[_-]?token|api[_-]?key|access[_-]?token|token|password|senha|secret|webhook[_-]?url)\b\s*[:=]\s*[^\s&]+'),
     r'\1=[REDACTED]'),
    # Authorization: Bearer xxx  /  Authorization: Bot xxx
    (re.compile(r'(?i)\b(authorization\s*:\s*)(bearer|bot)\s+\S+'), r'\1\2 [REDACTED]'),
    # Forma estrutural de um bot token do Discord: base64.base64.base64
    (re.compile(r'\b[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b'), '[REDACTED]'),
    # Webhook do Discord (o path contém o segredo)
    (re.compile(r'(?i)(https?://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/)\S+'), r'\1[REDACTED]'),
    # Segredo em query string: ?token=... &key=... &secret=...
    (re.compile(r'(?i)([?&](?:token|key|api[_-]?key|secret|password|auth)=)[^&\s]+'), r'\1[REDACTED]'),
]


def sanitize_log_message(message: str, sensitive_patterns: Optional[List[str]] = None) -> str:
    """
    PROPÓSITO DE NEGÓCIO: impedir que o token do Discord, o token do dashboard web ou uma
    URL de webhook acabem gravados em `logs/bot.log`, que não é secreto e viaja em
    relatórios e capturas de ecrã.

    INVARIANTES DO DOMÍNIO: só mascara o que tem forma ou rótulo de segredo. A regra
    anterior (`[a-zA-Z0-9_-]{20,}` truncado para 8 caracteres) mascarava QUALQUER
    sequência longa: um `channel_id` do YouTube virava `UCKy1dAq...` e o diagnóstico de
    fonte morta ficava ilegível — protegendo zero segredos que os padrões rotulados já
    não cubram. Nenhum padrão aqui pode depender apenas de comprimento.

    COMPORTAMENTO EM CASO DE FALHA: mensagem vazia/None devolve string vazia. Um padrão
    customizado inválido levanta `re.error` do próprio `re` — é erro de programação de
    quem chamou, não se mascara. A função nunca descarta a mensagem: no pior caso devolve
    o texto original inalterado.

    Args:
        message: Mensagem de log original
        sensitive_patterns: Lista opcional de padrões regex adicionais para mascarar

    Returns:
        Mensagem sanitizada
    """
    if not message:
        return ""

    sanitized = message
    for pattern, replacement in _PADROES_SENSIVEIS:
        sanitized = pattern.sub(replacement, sanitized)

    # Aplica padrões customizados se fornecidos
    if sensitive_patterns:
        for pattern in sensitive_patterns:
            sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)

    return sanitized


def validate_guild_id(guild_id: str) -> bool:
    """
    Valida se um guild_id é válido (numérico).
    
    Args:
        guild_id: ID da guild a validar
    
    Returns:
        True se válido
    """
    if not guild_id:
        return False
    
    try:
        int(guild_id)
        return True
    except (ValueError, TypeError):
        return False


def validate_channel_id(channel_id) -> bool:
    """
    Valida se um channel_id é válido (numérico).
    
    Args:
        channel_id: ID do canal a validar
    
    Returns:
        True se válido
    """
    if channel_id is None:
        return False
    
    try:
        int(channel_id)
        return True
    except (ValueError, TypeError):
        return False


def sanitize_filter_name(filter_name: str) -> Optional[str]:
    """
    Sanitiza e valida um nome de filtro.
    
    Args:
        filter_name: Nome do filtro a validar
    
    Returns:
        Nome sanitizado ou None se inválido
    """
    if not filter_name or not isinstance(filter_name, str):
        return None
    
    # Remove espaços e converte para lowercase
    sanitized = filter_name.strip().lower()
    
    # Valida contra caracteres não permitidos
    if not re.match(r'^[a-z0-9_-]+$', sanitized):
        return None
    
    return sanitized
