"""
Web Server module using aiohttp.
Integrates directly with the bot loop.
"""
import hmac
import logging
from aiohttp import web
import aiohttp_jinja2
import jinja2
import os
from datetime import datetime
from functools import wraps

from core import telemetria
from core.stats import stats
from utils.storage import p, load_json_safe
from settings import LOG_LEVEL

# Logger FILHO de "GameBot", não um logger irmão. Como "GameNewsWeb", este módulo não
# herdava nem os handlers nem o SecurityFilter configurados em `setup_logger`: os avisos
# de INFO desapareciam, e "tentativa de acesso com token inválido de IP X" — um evento de
# segurança — só saía no stderr do último recurso, nunca em `logs/bot.log`.
log = logging.getLogger("GameBot.web")

# Configuração de segurança
WEB_AUTH_TOKEN = os.getenv("WEB_AUTH_TOKEN", None)
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")  # Por padrão, apenas localhost
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

routes = web.RouteTableDef()

# Rate limiting simples (por IP)
_rate_limit_store = {}
RATE_LIMIT_WINDOW = 60  # segundos
RATE_LIMIT_MAX_REQUESTS = 30  # máximo de requisições por janela


def rate_limit_middleware(handler):
    """Middleware de rate limiting simples."""
    @wraps(handler)
    async def wrapper(request):
        client_ip = request.remote
        current_time = datetime.now().timestamp()

        # Remove IPs inativos para evitar crescimento ilimitado do dict
        stale = [ip for ip, ts_list in _rate_limit_store.items()
                 if not ts_list or current_time - max(ts_list) > RATE_LIMIT_WINDOW]
        for ip in stale:
            del _rate_limit_store[ip]

        # Limpa entradas antigas
        if client_ip in _rate_limit_store:
            _rate_limit_store[client_ip] = [
                ts for ts in _rate_limit_store[client_ip]
                if current_time - ts < RATE_LIMIT_WINDOW
            ]
        else:
            _rate_limit_store[client_ip] = []

        # Verifica limite
        if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
            log.warning(f"⚠️ Rate limit excedido para IP: {client_ip}")
            return web.json_response(
                {"error": "Rate limit exceeded. Please try again later."},
                status=429
            )
        
        # Adiciona timestamp atual
        _rate_limit_store[client_ip].append(current_time)
        
        return await handler(request)
    return wrapper


def auth_required(handler):
    """Decorator para requerer autenticação via token."""
    @wraps(handler)
    async def wrapper(request):
        # Se não há token configurado, permite acesso (modo desenvolvimento)
        if not WEB_AUTH_TOKEN:
            log.warning("⚠️ Servidor web rodando SEM autenticação! Configure WEB_AUTH_TOKEN no .env")
            return await handler(request)
        
        # Verifica token no header Authorization
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response(
                {"error": "Authentication required"},
                status=401,
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        token = auth_header.replace("Bearer ", "").strip()
        # Comparação constant-time evita timing side-channel na validação do token
        if not hmac.compare_digest(token, WEB_AUTH_TOKEN):
            log.warning(f"⚠️ Tentativa de acesso com token inválido de IP: {request.remote}")
            return web.json_response(
                {"error": "Invalid token"},
                status=403
            )
        
        return await handler(request)
    return wrapper


def security_headers_middleware(handler):
    """Adiciona headers de segurança HTTP."""
    @wraps(handler)
    async def wrapper(request):
        response = await handler(request)
        
        # Adiciona headers de segurança
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy básica
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:;"
        )
        
        return response
    return wrapper


@routes.get('/health')
async def health(request):
    """Liveness sem autenticação: prova que o event loop/web server responde.
    Usado pelo HEALTHCHECK do Docker. Não expõe dados sensíveis."""
    return web.json_response({"status": "ok"})


@routes.get('/')
@rate_limit_middleware
@auth_required
@security_headers_middleware
async def index(request):
    """Renderiza a página inicial."""
    return aiohttp_jinja2.render_template('index.html', request, {})

@routes.get('/api/stats')
@rate_limit_middleware
@auth_required
@security_headers_middleware
async def api_stats(request):
    """API JSON para atualizar status via AJAX."""
    # A saude vem do state.json, nao da memoria: sobrevive a reinicio do container, que e
    # justamente quando se quer saber o que aconteceu antes.
    estado = load_json_safe(p("state.json"), {})
    registo = telemetria.ultima(estado)
    return web.json_response({
        "uptime": stats.format_uptime(),
        "scans": stats.scans_completed,
        "news_posted": stats.news_posted,
        "feeds_failed": stats.feeds_failed,
        "cache_hits": stats.cache_hits_total,
        "last_scan": stats.last_scan_time.isoformat() if stats.last_scan_time else "Never",
        "saude": registo,
        "vereditos_recentes": telemetria.vereditos_recentes(estado),
    })

async def start_web_server(host=None, port=None):
    """Inicia o servidor web aiohttp."""
    # Usa configurações do ambiente ou padrões seguros
    server_host = host or WEB_HOST
    server_port = port or WEB_PORT
    
    app = web.Application()
    
    # Configura templates
    template_dir = p("web/templates")
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(template_dir))
    
    app.add_routes(routes)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, server_host, server_port)
    
    # Log de segurança
    if WEB_AUTH_TOKEN:
        log.info(f"🌍 Web Dashboard iniciado em http://{server_host}:{server_port} (com autenticação)")
    else:
        log.warning(f"⚠️ Web Dashboard iniciado em http://{server_host}:{server_port} SEM autenticação!")
        log.warning("⚠️ Configure WEB_AUTH_TOKEN no .env para produção!")
    
    # Falso positivo do bandit (B104): esta comparacao existe para AVISAR que o bind
    # ficou aberto, nao para o abrir.
    if server_host == "0.0.0.0":  # nosec B104
        log.warning("⚠️ Servidor web escutando em 0.0.0.0 (acessível de qualquer IP)!")
        log.warning("⚠️ Considere usar 127.0.0.1 ou configurar firewall adequadamente!")

    await site.start()


async def start_web_server_tolerante(host=None, port=None) -> bool:
    """
    PROPÓSITO DE NEGÓCIO: subir o dashboard web sem que a falha dele possa derrubar a
    função principal do bot, que é varrer fontes e publicar notícias. O dashboard é
    acessório; a varredura não é.

    INVARIANTES DO DOMÍNIO: esta função NUNCA propaga exceção. Ela é chamada de dentro do
    `on_ready`, e `on_ready` é um handler de evento: uma exceção ali é apenas registada
    pelo discord.py e TUDO o que vem depois deixa de correr. Bastava a porta 8080 estar
    ocupada — outra instância do bot, um serviço qualquer — para o bot ficar online,
    responder aos comandos já sincronizados e nunca mais sincronizar comandos, iniciar o
    agendador ou varrer, sem nenhum log que ligasse a causa ao efeito.

    COMPORTAMENTO EM CASO DE FALHA: devolve `False` e regista o motivo. `OSError` (porta
    ocupada, host inválido, permissão) sai como ERROR com a instrução de conferir
    WEB_HOST/WEB_PORT; qualquer outra exceção sai como `log.exception` com traceback.
    Devolve `True` só quando o servidor ficou de facto a escutar.
    """
    try:
        await start_web_server(host=host, port=port)
        return True
    except OSError as e:
        log.error(
            f"🌐 Dashboard web não subiu ({type(e).__name__}: {e}). "
            f"Porta ocupada ou host inválido — confira WEB_HOST/WEB_PORT. "
            f"O bot CONTINUA: varredura, comandos e agendador não dependem dele."
        )
    except Exception as e:
        log.exception(
            f"🌐 Falha inesperada ao iniciar o dashboard web: {type(e).__name__}: {e}. "
            f"O bot continua sem ele."
        )
    return False
