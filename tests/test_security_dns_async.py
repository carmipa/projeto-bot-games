"""
Guarda do DNS bloqueante dentro do event loop.

`validate_url` chama `socket.getaddrinfo`, que BLOQUEIA. Ela era chamada de dentro de
corrotinas — uma vez por feed na varredura (~70) e uma vez por site no HTML Monitor (~29).
Cada resolução lenta segurava a thread do asyncio inteira, incluindo o heartbeat do
gateway do Discord. É a mesma classe do defeito de julho, quando o BeautifulSoup bloqueava
o loop e foi movido para executor.

O teste central não mede tempo (seria instável) nem afirma que `socket.getaddrinfo` deixou
de ser chamado — isso seria falso: `loop.getaddrinfo` acaba a chamá-lo também, só que numa
thread do executor. A propriedade correta, e a que este teste mede, é EM QUE THREAD a
chamada bloqueante corre: fora da thread do event loop, o loop continua livre.

A primeira versão deste ficheiro afirmava "não chama getaddrinfo" e reprovou na calibração
— o instrumento estava errado, não o código. Fica registado porque a distinção é fácil de
perder na próxima leitura.
"""
import asyncio
import threading

import pytest

import utils.security as security
from utils.security import validate_url, validate_url_async

_IP_PUBLICO_FALSO = [(2, 1, 6, "", ("93.184.216.34", 0))]


def _instrumentar(monkeypatch):
    """Substitui getaddrinfo por um espião que regista a thread de cada chamada."""
    threads_das_chamadas = []

    def _espiao(*a, **k):
        threads_das_chamadas.append(threading.get_ident())
        return _IP_PUBLICO_FALSO

    monkeypatch.setattr(security.socket, "getaddrinfo", _espiao)
    return threads_das_chamadas


def test_async_resolve_fora_da_thread_do_event_loop(monkeypatch):
    """
    A propriedade que interessa: a resolução bloqueante não pode correr na thread do loop.
    Se alguém voltar a chamar `validate_url` (síncrona) de dentro de uma corrotina, isto
    acusa.
    """
    chamadas = _instrumentar(monkeypatch)
    thread_do_loop = {}

    async def _corre():
        thread_do_loop["id"] = threading.get_ident()
        return await validate_url_async("https://exemplo.example/feed")

    ok, _ = asyncio.run(_corre())

    assert ok is True
    assert chamadas, "nenhuma resolução aconteceu — sonda cega, o veredito não vale"
    assert all(t != thread_do_loop["id"] for t in chamadas), (
        "getaddrinfo correu na thread do event loop: o loop fica bloqueado durante a "
        "resolução, e com ~100 fontes por varredura isso derruba o heartbeat do Discord"
    )


def test_calibracao_a_sonda_distingue_a_thread(monkeypatch):
    """
    CALIBRAÇÃO. Prova que a sonda SABE apontar o dedo: a versão síncrona, chamada de dentro
    de uma corrotina, resolve na própria thread do loop — e o espião tem de registar
    exatamente isso. Sem este par, "correu noutra thread" seria indistinguível de uma sonda
    que nunca consegue ver a thread do loop.
    """
    chamadas = _instrumentar(monkeypatch)
    thread_do_loop = {}

    async def _corre():
        thread_do_loop["id"] = threading.get_ident()
        return validate_url("https://exemplo.example/feed")  # síncrona de propósito

    ok, _ = asyncio.run(_corre())

    assert ok is True
    assert chamadas, "sonda cega: nem a chamada síncrona foi registada"
    assert any(t == thread_do_loop["id"] for t in chamadas), (
        "a sonda não conseguiu detetar resolução na thread do loop — instrumento inútil"
    )


@pytest.mark.parametrize("url", [
    "http://localhost/feed",
    "http://127.0.0.1/feed",
    "ftp://exemplo.com/feed",
    "javascript:alert(1)",
    "",
    "https://exemplo.com/feed\nHost: outro",
])
def test_as_duas_versoes_recusam_o_mesmo(url):
    """
    As duas partilham `_validar_estrutura`; divergirem seria ter duas políticas de segurança
    com o mesmo nome. Nenhum destes casos chega a resolver DNS.
    """
    sinc_ok, _ = validate_url(url)
    asinc_ok, _ = asyncio.run(validate_url_async(url))
    assert sinc_ok is False
    assert asinc_ok is False
    assert sinc_ok == asinc_ok


def test_ip_privado_e_recusado_nas_duas(monkeypatch):
    """Um nome público que resolve para a rede interna é o SSRF clássico. Falha fechada."""
    monkeypatch.setattr(
        security.socket, "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("192.168.0.10", 0))],
    )

    async def _fake_getaddrinfo(*a, **k):
        return [(2, 1, 6, "", ("192.168.0.10", 0))]

    class _LoopFalso:
        getaddrinfo = staticmethod(_fake_getaddrinfo)

    monkeypatch.setattr(security.asyncio, "get_running_loop", lambda: _LoopFalso())

    sinc_ok, sinc_erro = validate_url("https://parece-publico.example/feed")
    asinc_ok, asinc_erro = asyncio.run(validate_url_async("https://parece-publico.example/feed"))

    assert sinc_ok is False and "192.168.0.10" in sinc_erro
    assert asinc_ok is False and "192.168.0.10" in asinc_erro


def test_erro_inesperado_na_resolucao_falha_fechado(monkeypatch):
    """Erro que não é `gaierror` significa que não se sabe para onde o nome aponta: recusa."""
    def _explode(*a, **k):
        raise RuntimeError("resolvedor em estado estranho")

    monkeypatch.setattr(security.socket, "getaddrinfo", _explode)
    ok, erro = validate_url("https://exemplo.example/feed")
    assert ok is False
    assert "DNS" in erro


def test_nenhum_modulo_async_chama_a_versao_sincrona():
    """
    Documento e hash provam a ENTRADA; só guarda executável prova a SAÍDA. Os testes acima
    provam que `validate_url_async` está correta — não provam que alguém a usa. Esta guarda
    lê o código de produção e reprova se um módulo assíncrono voltar a chamar a versão
    bloqueante, que é como o defeito existia.
    """
    import os
    import re

    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    modulos = [
        os.path.join(raiz, "core", "scanner.py"),
        os.path.join(raiz, "core", "html_monitor.py"),
    ]

    # `validate_url(` que NÃO seja `validate_url_async(`
    padrao = re.compile(r"\bvalidate_url\s*\(")

    lidos = 0
    infratores = []
    for caminho in modulos:
        if not os.path.isfile(caminho):
            continue
        lidos += 1
        with open(caminho, "r", encoding="utf-8") as f:
            for n, linha in enumerate(f, 1):
                if padrao.search(linha):
                    infratores.append(f"{os.path.basename(caminho)}:{n}: {linha.strip()}")

    assert lidos == len(modulos), (
        f"guarda cega: esperava ler {len(modulos)} módulos, leu {lidos}. "
        "Ficheiro renomeado ou movido — isto NÃO é aprovação."
    )
    assert not infratores, (
        "módulo assíncrono a chamar validate_url (bloqueante); use validate_url_async:\n"
        + "\n".join(infratores)
    )


def test_calibracao_da_guarda_de_saida():
    """
    A guarda acima só vale se souber acusar. Aqui ela corre contra um texto-controle que
    TEM de reprovar, e outro que TEM de passar.
    """
    import re
    padrao = re.compile(r"\bvalidate_url\s*\(")

    assert padrao.search("    ok, err = validate_url(article_url)"), "não acusou o caso doente"
    assert not padrao.search("    ok, err = await validate_url_async(article_url)"), (
        "acusou o caso são — a guarda daria falso positivo"
    )


def test_whitelist_de_dominio_continua_a_valer():
    ok, _ = asyncio.run(validate_url_async(
        "https://cdn.exemplo.com/img.png", allowed_domains=["exemplo.com"]
    ))
    assert ok is True

    ok2, erro2 = asyncio.run(validate_url_async(
        "https://outro.com/img.png", allowed_domains=["exemplo.com"]
    ))
    assert ok2 is False and "whitelist" in erro2
