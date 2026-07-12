"""
Testes para as funções utilitárias do bot.
Estes testes NÃO importam main.py para evitar dependência do Discord token.
"""
# Importa a função REAL de produção (antes: testava uma cópia local que podia divergir
# silenciosamente da implementação em utils/html.py).
from utils.html import clean_html


def test_clean_html_basic():
    """Testa remoção de tags HTML simples."""
    assert clean_html("<p>Test</p>") == "Test"
    assert clean_html("<b>Bold</b> text") == "Bold text"


def test_clean_html_entities():
    """Testa conversão de entidades HTML."""
    result = clean_html("Hello&nbsp;World")
    assert "Hello" in result and "World" in result


def test_clean_html_whitespace():
    """Testa normalização de espaços."""
    assert clean_html("  Multiple   spaces  ") == "Multiple spaces"
    assert clean_html("\n\nNew\nlines\n\n") == "New lines"


def test_clean_html_empty():
    """Testa strings vazias."""
    assert clean_html("") == ""
    assert clean_html(None) == ""


def test_sources_json_exists():
    """Verifica que sources.json existe."""
    import os
    assert os.path.exists("sources.json"), "sources.json deve existir"


def test_sources_json_valid():
    """Verifica que sources.json é JSON válido."""
    import json
    with open("sources.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "sources.json deve ser um dicionário"
    assert "rss_feeds" in data or "youtube_feeds" in data, "Deve ter pelo menos uma categoria de feeds"


def test_sources_urls_are_valid():
    """Verifica que URLs em sources.json começam com http(s)."""
    import json
    with open("sources.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    all_urls = []
    for key in data:
        if isinstance(data[key], list):
            all_urls.extend(data[key])
    
    for url in all_urls:
        assert url.startswith(("http://", "https://")), f"URL inválida: {url}"


def test_readme_exists():
    """Smoke test: verifica que README existe."""
    import os
    assert os.path.exists("README.md") or os.path.exists("readme.md") or os.path.exists("docs/README.md"), (
        "README.md na raiz ou docs/README.md deve existir"
    )

