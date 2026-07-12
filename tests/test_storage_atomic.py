"""
Testes de atomicidade/robustez do storage (save_json_safe / load_json_safe).
Área crítica antes sem cobertura: escrita atômica, limpeza do .tmp e recuperação de JSON corrompido.
Não depende do Discord (importa apenas utils.storage).
"""
import json
import os

from utils.storage import save_json_safe, load_json_safe


def test_save_then_load_roundtrip(tmp_path):
    fp = str(tmp_path / "data.json")
    data = {"a": 1, "b": [1, 2, 3], "acentuação": "ção"}
    save_json_safe(fp, data)
    assert load_json_safe(fp, {}) == data


def test_save_is_atomic_no_tmp_left(tmp_path):
    """Após salvar com sucesso, o arquivo .tmp não deve permanecer."""
    fp = str(tmp_path / "state.json")
    save_json_safe(fp, {"x": 1})
    assert os.path.exists(fp)
    assert not os.path.exists(fp + ".tmp")


def test_save_overwrites_existing(tmp_path):
    fp = str(tmp_path / "state.json")
    save_json_safe(fp, {"v": 1})
    save_json_safe(fp, {"v": 2})
    assert load_json_safe(fp, {}) == {"v": 2}


def test_load_missing_returns_default(tmp_path):
    fp = str(tmp_path / "inexistente.json")
    sentinel = {"default": True}
    assert load_json_safe(fp, sentinel) is sentinel


def test_load_empty_returns_default(tmp_path):
    fp = tmp_path / "vazio.json"
    fp.write_text("", encoding="utf-8")
    assert load_json_safe(str(fp), []) == []


def test_load_corrupted_returns_default(tmp_path):
    """JSON inválido não deve derrubar o bot; retorna o default."""
    fp = tmp_path / "corrompido.json"
    fp.write_text("{ isto não é json válido ", encoding="utf-8")
    assert load_json_safe(str(fp), {"ok": False}) == {"ok": False}


def test_load_directory_returns_default(tmp_path):
    """Se o caminho é um diretório (erro de montagem no Docker), retorna default."""
    d = tmp_path / "umdir.json"
    d.mkdir()
    assert load_json_safe(str(d), {"fallback": 1}) == {"fallback": 1}


def test_original_intact_when_data_unserializable(tmp_path):
    """Dados não serializáveis não devem corromper um arquivo já existente."""
    fp = str(tmp_path / "state.json")
    save_json_safe(fp, {"keep": "me"})
    save_json_safe(fp, {"bad": {1, 2, 3}})  # set não é serializável em JSON
    # O arquivo anterior permanece válido e legível
    assert load_json_safe(fp, {}) == {"keep": "me"}
    assert not os.path.exists(fp + ".tmp")
