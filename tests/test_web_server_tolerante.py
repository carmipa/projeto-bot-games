"""
Guarda do achado mais caro desta auditoria: uma falha ao subir o dashboard web abortava o
`on_ready` INTEIRO — sem sincronizar comandos, sem iniciar o agendador, sem varrer — e o
bot continuava online e aparentemente saudável. Bastava a porta estar ocupada.

O teste é de dois lados de propósito: sem o controle positivo, um wrapper que devolvesse
`False` sempre passaria no caso negativo e ninguém notaria.
"""
import asyncio
import socket

import pytest

import web.server as srv


def _porta_ocupada():
    """Abre um socket real e devolve (host, porta, socket) — a porta fica indisponível."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return "127.0.0.1", s.getsockname()[1], s


def test_porta_ocupada_nao_propaga_excecao():
    """
    Caso negativo REAL (não simulado): a porta está mesmo tomada, o aiohttp levanta OSError,
    e a função tem de engolir e devolver False.
    """
    host, porta, sock = _porta_ocupada()
    try:
        subiu = asyncio.run(srv.start_web_server_tolerante(host=host, port=porta))
    finally:
        sock.close()

    assert subiu is False, "porta ocupada deveria devolver False, não subir"


def test_porta_ocupada_levantaria_sem_a_protecao():
    """
    Calibração: prova que o cenário do teste acima REALMENTE produz uma exceção. Se um dia o
    aiohttp deixar de levantar em porta ocupada, o teste anterior passaria por não haver o
    que engolir — verde e cego.
    """
    host, porta, sock = _porta_ocupada()
    try:
        with pytest.raises(OSError):
            asyncio.run(srv.start_web_server(host=host, port=porta))
    finally:
        sock.close()


def test_sucesso_devolve_true(monkeypatch):
    """Controle positivo: a função sabe dizer True. Sem isto, False não significaria nada."""
    async def _sobe_ok(host=None, port=None):
        return None

    monkeypatch.setattr(srv, "start_web_server", _sobe_ok)
    assert asyncio.run(srv.start_web_server_tolerante()) is True


def test_excecao_generica_tambem_e_contida(monkeypatch):
    """Erro que não é OSError (ex.: template dir ausente) também não pode derrubar o on_ready."""
    async def _explode(host=None, port=None):
        raise RuntimeError("falha inesperada no setup do jinja2")

    monkeypatch.setattr(srv, "start_web_server", _explode)
    assert asyncio.run(srv.start_web_server_tolerante()) is False
