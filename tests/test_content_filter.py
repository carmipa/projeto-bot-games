"""
Testes do filtro de conteúdo REAL usado pelo scanner (should_skip_by_content).
Antes, só existia teste para _contains_any, que NÃO é o filtro de produção.
Não depende do Discord (importa apenas core.filters).
"""
from core.filters import should_skip_by_content


def test_noise_terms_are_skipped():
    """Termos do LIXO_FILTER descartam a notícia."""
    assert should_skip_by_content("Game Review: Zelda", "") is True
    assert should_skip_by_content("Weekly Podcast #12", "") is True
    assert should_skip_by_content("Valorant Champions Tour Finals", "") is True
    assert should_skip_by_content("How to beat the boss (guide)", "") is True


def test_gundam_is_excluded_from_scope():
    """'gundam' está fora do escopo deste bot de jogos e deve ser filtrado."""
    assert should_skip_by_content("New Gundam model announced", "") is True


def test_word_boundary_avoids_false_positive():
    """'review' filtra, mas 'preview' NÃO (word boundary)."""
    assert should_skip_by_content("Game review", "") is True
    assert should_skip_by_content("Exclusive preview of the new game", "") is False


def test_clean_news_passes():
    """Trailers/anúncios legítimos passam (retornam False = não filtrado)."""
    assert should_skip_by_content("Official Trailer revealed", "") is False
    assert should_skip_by_content("Elden Ring DLC launch date", "") is False


def test_matches_in_summary_too():
    """O filtro concatena título + resumo: termo só no resumo também descarta."""
    assert should_skip_by_content("Cool game", "This is a sponsored review") is True


def test_empty_input_is_not_skipped():
    assert should_skip_by_content("", "") is False
    assert should_skip_by_content(None, None) is False
