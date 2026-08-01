"""
Storage utilities - JSON load/save functions.
"""
import os
import json
import logging
import shutil
from datetime import datetime
from typing import Any, Dict, Tuple, Optional

log = logging.getLogger("GameBot")


# Só estes arquivos vão para DATA_DIR no Docker; o resto (translations/, web/, etc.) fica no app.
_DATA_FILES = ("config.json", "state.json", "history.json", "sources.json")


def _base_dir() -> str:
    """Diretório base para dados: DATA_DIR no Docker, senão CWD."""
    base = os.environ.get("DATA_DIR", "").strip()
    return base if base else os.path.abspath(".")


def p(filename: str) -> str:
    """
    Retorna o caminho absoluto para um arquivo.
    Só config, state, history e sources usam DATA_DIR; traduções e outros ficam no diretório do app.
    """
    name = os.path.basename(filename)
    if name in _DATA_FILES:
        return os.path.join(_base_dir(), filename)
    return os.path.abspath(filename)


def load_json_safe(filepath: str, default: Any) -> Any:
    """
    Carrega JSON sem derrubar o bot se faltar / vazio / corrompido.
    
    Args:
        filepath: Caminho do arquivo JSON
        default: Valor padrão se falhar
    
    Returns:
        Dados do JSON ou valor padrão
    """
    try:
        if not os.path.exists(filepath):
            log.warning(f"Arquivo '{filepath}' não existe. Usando padrão.")
            return default
        if os.path.isdir(filepath):
            log.error(f"'{filepath}' é um diretório, não um arquivo. Use DATA_DIR e monte um diretório no Docker. Usando padrão.")
            return default
        if os.path.getsize(filepath) == 0:
            log.warning(f"Arquivo '{filepath}' está vazio. Usando padrão.")
            return default
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log.error(f"Erro de sintaxe JSON ao carregar '{filepath}': linha {e.lineno}, coluna {e.colno}. Usando padrão.")
        return default
    except PermissionError as e:
        log.error(f"Sem permissão para ler '{filepath}': {e}. Usando padrão.")
        return default
    except Exception as e:
        log.error(f"Falha ao carregar '{filepath}': {type(e).__name__}: {e}. Usando padrão.", exc_info=True)
        return default


def save_json_safe(filepath: str, data: Any) -> None:
    """
    Salva JSON com indentação de forma atômica (write temp + rename) para evitar corrupção.
    Em erro, loga e segue.
    
    Args:
        filepath: Caminho do arquivo JSON
        data: Dados a salvar
    """
    tmp = filepath + ".tmp"
    try:
        if os.path.isdir(filepath):
            log.error(f"Não é possível salvar: '{filepath}' é um diretório.")
            return
        parent = os.path.dirname(filepath)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            # Garante que os dados foram para o disco antes do rename (evita arquivo
            # truncado/vazio em queda de energia ou crash do kernel num container 24/7)
            f.flush()
            os.fsync(f.fileno())
        # Atômico: replace sobrescreve o destino; em crash o .tmp fica, o original intacto
        os.replace(tmp, filepath)
    except PermissionError as e:
        log.error(f"Sem permissão para escrever '{filepath}': {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    except OSError as e:
        log.error(f"Erro de sistema ao salvar '{filepath}': {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    except TypeError as e:
        log.error(f"Dados não serializáveis em JSON ao salvar '{filepath}': {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    except Exception as e:
        log.error(f"Falha inesperada ao salvar '{filepath}': {type(e).__name__}: {e}", exc_info=True)
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def create_backup(filepath: str, backup_dir: str = "backups") -> Optional[str]:
    """
    Cria um backup do arquivo antes de modificações críticas.
    
    Args:
        filepath: Caminho do arquivo a fazer backup
        backup_dir: Diretório onde salvar backups
    
    Returns:
        Caminho do arquivo de backup criado ou None se falhar
    """
    try:
        if not os.path.exists(filepath):
            log.warning(f"Arquivo '{filepath}' não existe para backup.")
            return None
        
        # Cria diretório de backups se não existir
        os.makedirs(backup_dir, exist_ok=True)
        
        # Nome do backup com timestamp
        filename = os.path.basename(filepath)
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{name}_backup_{timestamp}{ext}"
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # Copia arquivo
        shutil.copy2(filepath, backup_path)
        
        log.info(f"✅ Backup criado: {backup_path}")
        return backup_path
        
    except Exception as e:
        log.error(f"Falha ao criar backup de '{filepath}': {type(e).__name__}: {e}", exc_info=True)
        return None


def get_state_stats(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtém estatísticas do state.json.
    
    Args:
        state: Dicionário do state.json
    
    Returns:
        Dicionário com estatísticas
    """
    stats = {
        "dedup_feeds": 0,
        "dedup_total_links": 0,
        "http_cache_urls": 0,
        "html_hashes_sites": 0,
        "youtube_feed_cache": 0,
        "source_failures": 0,
        "last_cleanup": None,
        "last_announced_hash": state.get("last_announced_hash"),
        "file_size_kb": 0
    }

    for chave in ("youtube_feed_cache", "source_failures"):
        valor = state.get(chave, {})
        if isinstance(valor, dict):
            stats[chave] = len(valor)
    
    # Estatísticas de dedup
    dedup = state.get("dedup", {})
    if isinstance(dedup, dict):
        stats["dedup_feeds"] = len(dedup)
        stats["dedup_total_links"] = sum(
            len(links) if isinstance(links, list) else 0
            for links in dedup.values()
        )
    
    # Estatísticas de http_cache
    http_cache = state.get("http_cache", {})
    if isinstance(http_cache, dict):
        stats["http_cache_urls"] = len(http_cache)
    
    # Estatísticas de html_hashes
    html_hashes = state.get("html_hashes", {})
    if isinstance(html_hashes, dict):
        stats["html_hashes_sites"] = len(html_hashes)
    
    # Última limpeza
    last_cleanup = state.get("last_cleanup", 0)
    if last_cleanup:
        try:
            cleanup_dt = datetime.fromtimestamp(last_cleanup)
            stats["last_cleanup"] = cleanup_dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            pass
    
    return stats


# Chaves de dados que o scanner escreve em state.json e que uma limpeza precisa conhecer.
# `_METADADOS_PRESERVADOS` é o oposto: sobrevive até a um "tudo", de propósito.
# Toda chave nova em state.json TEM de entrar numa destas duas listas — a guarda em
# tests/test_clean_state_chaves.py falha se alguém acrescentar estado sem classificar.
CHAVES_LIMPAVEIS = ("dedup", "http_cache", "html_hashes", "youtube_feed_cache", "source_failures")
METADADOS_PRESERVADOS = ("last_cleanup", "last_announced_hash")


def clean_state(state: Dict[str, Any], clean_type: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    PROPÓSITO DE NEGÓCIO: dar ao administrador uma forma cirúrgica de zerar partes do
    estado do bot — repostar de propósito, forçar refetch quando um feed muda de formato,
    ou reinicializar o monitor de sites — sem apagar o ficheiro inteiro à mão.

    INVARIANTES DO DOMÍNIO: `tudo` significa tudo. `youtube_feed_cache` e
    `source_failures` eram ignorados por esta função: o "tudo" deixava para trás
    resoluções de canal em cache (que podiam apontar para o canal errado) e contadores de
    falha antigos, e o relatório dizia que estava limpo. `html_hashes` e
    `youtube_feed_cache` andam juntos com o refetch; `last_cleanup` e
    `last_announced_hash` são metadados e sobrevivem a qualquer limpeza, para não
    disparar auto-limpeza nem reanunciar a versão.

    COMPORTAMENTO EM CASO DE FALHA: `clean_type` desconhecido levanta `ValueError` e não
    devolve estado nenhum — o comando aborta antes de gravar. O dicionário original nunca
    é mutado: trabalha-se sobre uma cópia rasa e as chaves limpas são substituídas.

    Args:
        state: Estado atual do state.json
        clean_type: 'dedup', 'http_cache', 'html_hashes', 'youtube_feed_cache' ou 'tudo'

    Returns:
        Tupla (novo_state, stats_antes)
    """
    stats_before = get_state_stats(state)
    new_state = state.copy()

    if clean_type == "dedup":
        new_state["dedup"] = {}
        log.info("🧹 Limpeza: dedup removido")

    elif clean_type == "http_cache":
        new_state["http_cache"] = {}
        log.info("🧹 Limpeza: http_cache removido")

    elif clean_type == "html_hashes":
        new_state["html_hashes"] = {}
        log.info("🧹 Limpeza: html_hashes removido")

    elif clean_type == "youtube_feed_cache":
        # Também zera source_failures: uma resolução errada em cache costuma vir
        # acompanhada de contadores de falha da URL antiga, que deixam de fazer sentido.
        new_state["youtube_feed_cache"] = {}
        new_state["source_failures"] = {}
        log.info("🧹 Limpeza: youtube_feed_cache e source_failures removidos")

    elif clean_type == "tudo":
        for chave in CHAVES_LIMPAVEIS:
            new_state[chave] = {}
        log.info(
            "🧹 Limpeza: tudo removido (%s) — preservados: %s",
            ", ".join(CHAVES_LIMPAVEIS),
            ", ".join(METADADOS_PRESERVADOS),
        )

    else:
        raise ValueError(f"Tipo de limpeza inválido: {clean_type}")

    return new_state, stats_before
