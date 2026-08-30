
import logging
import sys
from colorama import init, Fore, Style

# Inicializa colorama para funcionar no Windows
# Inicializa colorama para funcionar no Windows e forçar cores
init(autoreset=True, strip=False)

class SecurityFilter(logging.Filter):
    """
    PROPÓSITO DE NEGÓCIO: garantir que o token do Discord, o token do dashboard web ou uma
    URL de webhook nunca cheguem a `logs/bot.log` nem ao console, independentemente de
    quem chamou o logger e de como escreveu a chamada.

    INVARIANTES DO DOMÍNIO: sanitiza a mensagem RENDERIZADA, com os argumentos já
    interpolados. A versão anterior sanitizava só `record.msg` quando ele era `str` — o
    que, numa chamada de formatação preguiçosa (`log.error("feed %s falhou", url)`),
    limpava apenas o molde `"feed %s falhou"` e deixava o argumento intacto. Como o
    projeto usa esse estilo em vários pontos do scanner, a garantia anunciada no README
    ("tokens e dados sensíveis mascarados") era mais larga do que a realidade. Depois de
    renderizar, `record.args` é zerado — senão o handler tentaria interpolar de novo uma
    mensagem que já não tem marcadores e levantaria erro de formatação.

    COMPORTAMENTO EM CASO DE FALHA: o filtro NUNCA descarta um registo. Falha ao importar
    o sanitizador, ou erro ao renderizar a mensagem (argumentos incompatíveis com o
    molde), devolve `True` deixando o registo seguir como estava — perder o log de um erro
    seria pior do que arriscar não o ter mascarado.
    """
    def filter(self, record):
        try:
            from utils.security import sanitize_log_message
        except ImportError:
            return True

        try:
            renderizada = record.getMessage()
        except Exception:
            # Molde e argumentos incompatíveis: deixa o logging lidar com isso.
            return True

        record.msg = sanitize_log_message(renderizada)
        record.args = ()
        return True


class ColorfulFormatter(logging.Formatter):
    """
    Formatador de logs customizado com cores, ícones e traceback colorido.
    """

    # Ícones e cores para cada nível
    FORMATS = {
        logging.DEBUG:    (Fore.CYAN, "🐛"),
        logging.INFO:     (Fore.GREEN, "ℹ️"),
        logging.WARNING:  (Fore.YELLOW, "⚠️"),
        logging.ERROR:    (Fore.RED, "❌"),
        logging.CRITICAL: (Fore.RED + Style.BRIGHT, "🔥")
    }

    def format(self, record):
        color, icon = self.FORMATS.get(record.levelno, (Fore.WHITE, ""))
        
        # Formato: DATA - [NIVEL] ICON MENSAGEM
        # Agora a mensagem inteira segue a cor do nível
        log_fmt = f"{Fore.LIGHTBLACK_EX}%(asctime)s{Style.RESET_ALL} - [{color}%(levelname)s{Style.RESET_ALL}] {icon} {color}%(message)s{Style.RESET_ALL}"
        
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        message = formatter.format(record)
        
        # Adiciona traceback colorido se existir
        if record.exc_info:
            # Formata o traceback com cores
            exc_text = self.formatException(record.exc_info)
            # Colore o traceback em vermelho claro para erros
            if record.levelno >= logging.ERROR:
                exc_text = f"{Fore.RED}{exc_text}{Style.RESET_ALL}"
            else:
                exc_text = f"{Fore.YELLOW}{exc_text}{Style.RESET_ALL}"
            message += "\n" + exc_text
        
        return message
    
    def formatException(self, exc_info):
        """Formata exception com cores melhoradas."""
        import traceback
        lines = traceback.format_exception(*exc_info)
        
        # Colore diferentes partes do traceback
        colored_lines = []
        for line in lines:
            if "File" in line and "line" in line:
                # Linhas de arquivo em ciano
                colored_lines.append(f"{Fore.CYAN}{line.rstrip()}{Style.RESET_ALL}")
            elif "Error" in line or "Exception" in line:
                # Mensagens de erro em vermelho brilhante
                colored_lines.append(f"{Fore.RED + Style.BRIGHT}{line.rstrip()}{Style.RESET_ALL}")
            else:
                # Código em amarelo claro
                colored_lines.append(f"{Fore.LIGHTYELLOW_EX}{line.rstrip()}{Style.RESET_ALL}")
        
        return "\n".join(colored_lines)

def setup_logger(name="GameBot", log_file="logs/bot.log", level=logging.INFO):
    """
    Configura e retorna um logger com handlers de arquivo (rotativo) e console (colorido).
    """
    
    # Cria o logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Evita duplicação de handlers se chamar setup mais de uma vez
    if logger.hasHandlers():
        logger.handlers.clear()

    # --- File Handler (Sem cores ANSI, formato padrão) ---
    from logging.handlers import RotatingFileHandler
    import os

    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding="utf-8",
        )
        file_fmt = logging.Formatter(
            "%(asctime)s - [%(levelname)s] - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_fmt)
        file_handler.addFilter(SecurityFilter())
        logger.addHandler(file_handler)
    except OSError as e:
        # Docker: volume ./logs montado como root sem chown no entrypoint, etc.
        print(
            f"[GameBot] Aviso: não foi possível abrir log em arquivo ({log_file}): {e}. "
            "Usando apenas console.",
            file=sys.stderr,
        )

    # --- Console Handler (Com cores) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorfulFormatter())
    # Adiciona filtro de segurança também no console
    console_handler.addFilter(SecurityFilter())
    logger.addHandler(console_handler)

    return logger
