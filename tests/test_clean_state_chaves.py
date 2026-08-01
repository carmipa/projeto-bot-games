"""
Guarda genérica do clean_state.

Lição da auditoria: acrescentar estado é meia funcionalidade. A outra metade é ensinar
quem limpa esse estado a conhecê-lo. `youtube_feed_cache` e `source_failures` existiam
há meses e o `tipo:tudo` os ignorava — o relatório dizia "tudo removido" e não era.

Este teste lê o código do scanner, extrai as chaves que ele escreve em `state` e falha
se alguma não estiver classificada como limpável ou como metadado preservado de
propósito. A próxima chave nova não passa despercebida.
"""
import os
import re

import pytest

from utils.storage import (
    CHAVES_LIMPAVEIS,
    METADADOS_PRESERVADOS,
    clean_state,
    get_state_stats,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCANNER = os.path.join(ROOT, "core", "scanner.py")

# state["chave"] = ...  |  state.setdefault("chave", ...)  |  state.get("chave"...)
_PADRAO_CHAVE = re.compile(
    r'state(?:\[|\.setdefault\(|\.get\()\s*["\']([a-z_]+)["\']'
)


def _chaves_escritas_pelo_scanner():
    with open(SCANNER, "r", encoding="utf-8") as f:
        codigo = f.read()
    return set(_PADRAO_CHAVE.findall(codigo))


def test_toda_chave_do_scanner_esta_classificada():
    conhecidas = set(CHAVES_LIMPAVEIS) | set(METADADOS_PRESERVADOS)
    encontradas = _chaves_escritas_pelo_scanner()
    assert encontradas, "regex não encontrou chave nenhuma — o padrão ficou obsoleto"
    nao_classificadas = encontradas - conhecidas
    assert not nao_classificadas, (
        f"chaves de state.json sem classificação: {sorted(nao_classificadas)}. "
        f"Acrescente em CHAVES_LIMPAVEIS (some no clean_state) ou em "
        f"METADADOS_PRESERVADOS (sobrevive de propósito), em utils/storage.py."
    )


def test_tudo_limpa_todas_as_chaves_limpaveis():
    estado = {c: {"x": 1} for c in CHAVES_LIMPAVEIS}
    estado["last_cleanup"] = 12345
    estado["last_announced_hash"] = "abc1234"

    novo, _ = clean_state(estado, "tudo")

    for chave in CHAVES_LIMPAVEIS:
        assert novo[chave] == {}, f"'tudo' não limpou {chave}"
    assert novo["last_cleanup"] == 12345
    assert novo["last_announced_hash"] == "abc1234"


def test_youtube_feed_cache_limpa_tambem_as_falhas():
    """Resolução errada em cache costuma vir com contadores de falha da URL antiga."""
    estado = {
        "youtube_feed_cache": {"https://youtube.com/@x": "feed"},
        "source_failures": {"https://feed": {"count": 3}},
        "dedup": {"https://feed": ["link"]},
    }
    novo, _ = clean_state(estado, "youtube_feed_cache")
    assert novo["youtube_feed_cache"] == {}
    assert novo["source_failures"] == {}
    assert novo["dedup"] == {"https://feed": ["link"]}, "não devia tocar no dedup"


def test_clean_state_nao_muta_o_original():
    estado = {"dedup": {"a": ["1"]}, "http_cache": {"a": {}}}
    novo, _ = clean_state(estado, "dedup")
    assert estado["dedup"] == {"a": ["1"]}, "clean_state mutou o dicionário recebido"
    assert novo["dedup"] == {}


def test_tipo_invalido_levanta_value_error():
    with pytest.raises(ValueError):
        clean_state({"dedup": {}}, "inexistente")


def test_stats_reportam_as_chaves_novas():
    estado = {
        "youtube_feed_cache": {"a": "1", "b": "2"},
        "source_failures": {"a": {"count": 1}},
    }
    stats = get_state_stats(estado)
    assert stats["youtube_feed_cache"] == 2
    assert stats["source_failures"] == 1
