"""
Guarda do `SecurityFilter`: a sanitização tem de valer para a mensagem RENDERIZADA.

A versão anterior só limpava `record.msg`. Numa chamada de formatação preguiçosa —
`log.error("feed %s falhou", url)` — isso limpava apenas o molde `"feed %s falhou"` e
deixava o argumento intacto. O scanner usa esse estilo em vários pontos, portanto a
garantia anunciada no README ("tokens e dados sensíveis mascarados") era mais larga do que
a realidade.

Cada teste positivo tem par negativo: mascarar tudo o que é longo já foi o defeito
anterior (um `channel_id` do YouTube virava `UCKy1dAq...` e o diagnóstico de fonte morta
ficava ilegível). Provar que redige o segredo sem provar que preserva o resto é meia prova.
"""
import logging

from utils.logger import SecurityFilter


def _passar_pelo_filtro(msg, *args):
    """Monta um LogRecord real, passa pelo filtro e devolve a mensagem final formatada."""
    record = logging.LogRecord(
        name="GameBot", level=logging.ERROR, pathname=__file__, lineno=1,
        msg=msg, args=args or None, exc_info=None,
    )
    assert SecurityFilter().filter(record) is True, "o filtro nunca pode descartar um registo"
    return record.getMessage()


def test_segredo_no_argumento_e_redigido():
    """O caso que passava batido: o segredo está no ARGUMENTO, não no molde."""
    saida = _passar_pelo_filtro("chamando endpoint %s", "https://api.x/feed?token=abc123secreto")
    assert "abc123secreto" not in saida
    assert "[REDACTED]" in saida


def test_token_do_discord_no_argumento():
    # O token e montado em partes DE PROPOSITO. Um literal com a forma exata de um bot
    # token do Discord faz o secret scanning do GitHub RECUSAR o push -- e ele esta certo:
    # nao tem como saber que este e sintetico. A forma continua a ser a mesma que o padrao
    # estrutural procura (23-28 caracteres . 6 . 27 ou mais); o que deixa de existir e uma
    # string unica no ficheiro que pareca um segredo de verdade.
    corpo = "MTIzNDU2Nzg5MDEyMzQ1Njc4"
    meio = "GaBcDe"
    assinatura = "ZzYyXxWwVvUuTtSsRrQqPpOoNnMmLlKkJj"
    token = f"{corpo}.{meio}.{assinatura}"
    saida = _passar_pelo_filtro("conectando com %s", token)
    assert token not in saida
    assert "[REDACTED]" in saida


def test_rotulo_com_valor_no_argumento():
    saida = _passar_pelo_filtro("config %s", "DISCORD_TOKEN=valorsupersecreto123")
    assert "valorsupersecreto123" not in saida


def test_channel_id_do_youtube_sobrevive_intacto():
    """
    CONTROLE NEGATIVO. Um channel_id não é segredo. Se ele for mascarado, o diagnóstico de
    fonte morta fica ilegível — foi exatamente a regressão corrigida em 2026-08-01.
    """
    url = "https://www.youtube.com/feeds/videos.xml?channel_id=UCKy1dAqELo0zrOtPkf0eTMw"
    saida = _passar_pelo_filtro("Feed respondeu HTTP %s: %s", 404, url)
    assert "UCKy1dAqELo0zrOtPkf0eTMw" in saida, "channel_id foi mascarado sem ser segredo"
    assert "404" in saida


def test_mensagem_sem_argumentos_continua_a_funcionar():
    saida = _passar_pelo_filtro("varredura concluída sem novidades")
    assert saida == "varredura concluída sem novidades"


def test_args_zerados_evitam_dupla_formatacao():
    """
    Depois de renderizar, `record.args` tem de ficar vazio. Se ficassem, o handler tentaria
    interpolar de novo uma mensagem que já não tem marcadores — e levantaria erro de
    formatação na hora de escrever o log.
    """
    record = logging.LogRecord(
        name="GameBot", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="feed %s devolveu %s", args=("https://x/feed", 500), exc_info=None,
    )
    SecurityFilter().filter(record)
    assert record.args == ()
    # Segunda renderização (o que o handler faz) não pode explodir nem mudar o texto.
    assert record.getMessage() == "feed https://x/feed devolveu 500"


def test_molde_incompativel_com_argumentos_nao_derruba_o_log():
    """
    Falha aberta de propósito: se o programador errou o número de marcadores, perder o
    registo do erro seria pior do que não o ter mascarado. O filtro devolve True e deixa o
    logging tratar do assunto.
    """
    record = logging.LogRecord(
        name="GameBot", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="faltam marcadores", args=("sobrando",), exc_info=None,
    )
    assert SecurityFilter().filter(record) is True
