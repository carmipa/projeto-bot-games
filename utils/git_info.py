import subprocess
import logging

log = logging.getLogger("GameBot")

def get_git_changes():
    """
    Retrieves the last commit hash (short) and message.
    Returns a string formatted as 'hash - message', or a fallback message on failure.
    """
    try:
        # Último commit (hash curto + mensagem). shell=False + lista de args evita injeção de shell.
        cmd = ["git", "log", "-1", "--pretty=format:%h - %s"]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8').strip()
        return output
    except Exception as e:
        log.debug(f"Git info fetch failed: {e}")
        return "Maintenance Update (No Git Info)"

def get_current_hash():
    """
    Returns just the short hash for comparison state.
    """
    try:
        cmd = ["git", "log", "-1", "--pretty=format:%h"]
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8').strip()
    except Exception as e:
        log.debug(f"Falha ao obter hash do Git: {e}")
        return None
