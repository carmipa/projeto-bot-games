"""
Sanitizador de log: tem de esconder segredo E preservar diagnóstico.

O regex antigo (`[a-zA-Z0-9_-]{20,}` -> 8 chars + "...") mascarava qualquer sequência
longa. Não protegia segredo nenhum que os padrões rotulados já não cobrissem e cegava a
operação: um channel_id do YouTube virava `UCKy1dAq...` justamente nas mensagens de
"fonte morta", que existem para ser lidas.

Nenhum literal com forma de token real neste ficheiro: valores fictícios são montados em
tempo de execução, senão o secret scanning do GitHub recusa o push (lição do bot Gundam).
"""
from utils.security import sanitize_log_message


def _token_falso():
    """Monta em runtime algo com a FORMA de bot token do Discord, sem literal no ficheiro."""
    return ".".join(["M" + "T" * 22, "G" + "h" * 5, "k" + "9" * 30])


# ---------- esconde o que é segredo ----------

def test_esconde_token_rotulado():
    saida = sanitize_log_message("Falha ao logar com DISCORD_TOKEN=abcdefgh12345678")
    assert "abcdefgh12345678" not in saida
    assert "[REDACTED]" in saida


def test_esconde_password_e_secret():
    for rotulo in ("password", "senha", "secret", "api_key", "access_token"):
        saida = sanitize_log_message(f"cfg {rotulo}=valorsupersecreto123")
        assert "valorsupersecreto123" not in saida, f"não mascarou {rotulo}"


def test_esconde_authorization_header():
    saida = sanitize_log_message("Authorization: Bot ABCdefGHIjklMNOpqrs.tuv")
    assert "ABCdefGHIjklMNOpqrs" not in saida
    assert "[REDACTED]" in saida


def test_esconde_token_pela_forma_estrutural():
    tok = _token_falso()
    saida = sanitize_log_message(f"conectando com {tok} ...")
    assert tok not in saida
    assert "[REDACTED]" in saida


def test_esconde_webhook_do_discord():
    saida = sanitize_log_message(
        "post para https://discord.com/api/webhooks/123456789/segredoDoWebhookAqui"
    )
    assert "segredoDoWebhookAqui" not in saida


def test_esconde_segredo_em_query_string():
    saida = sanitize_log_message("GET https://api.exemplo.com/feed?token=abc123secreto&x=1")
    assert "abc123secreto" not in saida
    assert "x=1" in saida, "não devia comer o resto da query string"


# ---------- preserva o que é diagnóstico ----------

def test_preserva_channel_id_do_youtube():
    """Regressão direta do bug: era exatamente esta string que ficava ilegível."""
    cid = "UCKy1dAqELo0zrOtPkf0eTMw"
    msg = f"❌ Feed respondeu HTTP 404: https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    saida = sanitize_log_message(msg)
    assert cid in saida, f"channel_id foi destruído: {saida}"


def test_preserva_url_completa_e_status():
    msg = "❌ Feed respondeu HTTP 403 (falha 3x): https://www.giantbomb.com/feeds/mashup/"
    assert sanitize_log_message(msg) == msg


def test_preserva_erro_tecnico_longo():
    msg = "erro TLSV1_ALERT_INTERNAL_ERROR ao conectar em gamesindustry.biz"
    saida = sanitize_log_message(msg)
    assert "TLSV1_ALERT_INTERNAL_ERROR" in saida


def test_preserva_mensagem_de_content_encoding():
    msg = "Can not decode content-encoding: brotli (br). Please install Brotli"
    assert sanitize_log_message(msg) == msg


def test_idempotente():
    """O filtro roda uma vez por handler (arquivo e console) sobre o mesmo record."""
    msg = f"token={_token_falso()} feed=https://x.com/rss?channel_id=UCKy1dAqELo0zrOtPkf0eTMw"
    uma = sanitize_log_message(msg)
    assert sanitize_log_message(uma) == uma


def test_mensagem_vazia():
    assert sanitize_log_message("") == ""
    assert sanitize_log_message(None) == ""
