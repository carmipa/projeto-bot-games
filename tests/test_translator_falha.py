"""
Guarda do incidente de 2026-08-30, visto EM PRODUÇÃO no canal do Discord.

O bot publicou notícias cujo título e resumo eram, os dois:

    Error 500 (Server Error)!!1500.That's an error.There was an error.
    Please try again later.That's all we know.

O `deep_translator` não levanta exceção quando o Google responde com página de erro:
devolve o TEXTO da página como se fosse a tradução. O único guarda era `if trad is None`,
que uma string nunca aciona.

O elo mais caro da cadeia é o terceiro: o envio "teve sucesso", o link entrou no dedup, e
a notícia verdadeira nunca mais seria publicada — nem depois de o tradutor voltar. Por
isso o teste central não é "a página de erro é detectada", é **o que o bot publica no
lugar dela**.
"""
import asyncio

import pytest

import utils.translator as tr

# O texto EXATO que chegou ao canal. Não é um vetor inventado: é a evidência.
PAGINA_DE_ERRO = (
    "Error 500 (Server Error)!!1500.That's an error.There was an error. "
    "Please try again later.That's all we know."
)
ORIGINAL = "Next Week on Xbox: New Games for August 31"


@pytest.fixture(autouse=True)
def _estado_limpo():
    tr._reset_estado_do_tradutor()
    yield
    tr._reset_estado_do_tradutor()


def _com_tradutor_que_responde(monkeypatch, resposta):
    """Substitui o tradutor por um duplo que devolve `resposta` e conta as chamadas."""
    chamadas = []

    class _Duplo:
        def translate(self, texto):
            chamadas.append(texto)
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

    monkeypatch.setattr(tr, "_get_translator", lambda alvo: _Duplo())
    return chamadas


# --------------------------------------------------------------------------
# O comportamento que importa: o que o bot PUBLICA
# --------------------------------------------------------------------------

def test_pagina_de_erro_nao_e_publicada(monkeypatch):
    """O caso real: o serviço responde com sucesso, mas o conteúdo é lixo."""
    _com_tradutor_que_responde(monkeypatch, PAGINA_DE_ERRO)
    saida = asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR"))
    assert saida == ORIGINAL, (
        "a página de erro do Google foi publicada como se fosse a notícia"
    )


def test_controle_positivo_traducao_boa_passa(monkeypatch):
    """
    Sem este par, "devolveu o original" seria indistinguível de uma função que NUNCA
    traduz. Prova que o caminho bom continua a funcionar.
    """
    _com_tradutor_que_responde(monkeypatch, "Próxima semana no Xbox")
    saida = asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR"))
    assert saida == "Próxima semana no Xbox"


def test_pagina_de_erro_nao_entra_no_cache(monkeypatch):
    """
    Segundo elo da cadeia. Se o lixo fosse memorizado, o mesmo texto continuaria a sair
    errado mesmo depois de o tradutor voltar ao normal.
    """
    _com_tradutor_que_responde(monkeypatch, PAGINA_DE_ERRO)
    asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR"))
    assert ("pt", ORIGINAL) not in tr._translation_cache

    # E agora que o serviço voltou, a tradução correta tem de sair.
    _com_tradutor_que_responde(monkeypatch, "Próxima semana no Xbox")
    assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == "Próxima semana no Xbox"


def test_excecao_do_tradutor_devolve_o_original(monkeypatch):
    _com_tradutor_que_responde(monkeypatch, RuntimeError("connection reset"))
    assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == ORIGINAL


def test_resposta_vazia_ou_nao_string_devolve_o_original(monkeypatch):
    for resposta in (None, "", "   ", b"bytes"):
        tr._reset_estado_do_tradutor()
        _com_tradutor_que_responde(monkeypatch, resposta)
        assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == ORIGINAL


# --------------------------------------------------------------------------
# Disjuntor: insistir durante bloqueio só prolonga o bloqueio
# --------------------------------------------------------------------------

def test_disjuntor_para_de_chamar_o_servico_apos_falhas_seguidas(monkeypatch):
    chamadas = _com_tradutor_que_responde(monkeypatch, PAGINA_DE_ERRO)

    for i in range(tr._FALHAS_ATE_DEGRADAR + 10):
        saida = asyncio.run(tr.translate_to_target(f"{ORIGINAL} {i}", "pt_BR"))
        assert saida == f"{ORIGINAL} {i}"

    assert len(chamadas) == tr._FALHAS_ATE_DEGRADAR, (
        f"o disjuntor devia ter parado em {tr._FALHAS_ATE_DEGRADAR} chamadas, "
        f"mas o serviço foi chamado {len(chamadas)} vezes"
    )


def test_uma_traducao_boa_zera_o_contador(monkeypatch):
    """Falha isolada não pode aproximar o disjuntor de abrir para sempre."""
    _com_tradutor_que_responde(monkeypatch, PAGINA_DE_ERRO)
    asyncio.run(tr.translate_to_target("a", "pt_BR"))
    assert tr._falhas_consecutivas == 1

    _com_tradutor_que_responde(monkeypatch, "traducao boa")
    asyncio.run(tr.translate_to_target("b", "pt_BR"))
    assert tr._falhas_consecutivas == 0


# --------------------------------------------------------------------------
# Calibração do detector: tem de dizer SIM e tem de dizer NÃO
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lixo", [
    PAGINA_DE_ERRO,
    "That's an error. That's all we know.",
    "Error 502 (Server Error)!!1",
    "",
    "   ",
    None,
    123,
])
def test_detector_recusa_o_que_tem_de_recusar(lixo):
    assert tr._traducao_utilizavel(lixo) is False


@pytest.mark.parametrize("bom", [
    "Próxima semana no Xbox: novos jogos de 31 de agosto",
    "Next Week on Xbox: New Games for August 31",
    "Servidores do jogo caíram após a atualização",   # fala de erro, e é notícia legítima
    "Patch corrige erro 500 no matchmaking",          # idem, com o número no meio
    "!",
])
def test_detector_aceita_o_que_tem_de_aceitar(bom):
    """
    CONTROLE NEGATIVO. Um detector que recusa tudo passaria em todos os testes acima e
    faria o bot nunca traduzir nada. Notícia que FALA de erro de servidor tem de passar —
    a assinatura procurada é o texto da página do Google, não a palavra "erro".
    """
    assert tr._traducao_utilizavel(bom) is True


# --------------------------------------------------------------------------
# Serviço que não responde: requests.get do deep_translator não tem timeout
# --------------------------------------------------------------------------

class _TradutorMudo:
    def translate(self, texto):
        import time as _t
        _t.sleep(0.6)
        return "tarde demais"


def test_servico_mudo_publica_o_original_no_prazo(monkeypatch):
    """Sem prazo, uma conexão parada prendia a varredura inteira."""
    import time as _t
    monkeypatch.setattr(tr, "_get_translator", lambda alvo: _TradutorMudo())
    monkeypatch.setattr(tr, "_TRADUCAO_TIMEOUT_S", 0.05)

    async def medir():
        # Medido DENTRO do loop: o asyncio.run espera a thread presa ao encerrar, coisa que o
        # loop do bot, que nunca encerra, não faz.
        inicio = _t.perf_counter()
        saida = await tr.translate_to_target(ORIGINAL, "pt_BR")
        return saida, _t.perf_counter() - inicio

    saida, decorrido = asyncio.run(medir())
    assert saida == ORIGINAL
    assert decorrido < 0.5
    assert tr.degradacoes_totais() == 1
    assert ("pt", ORIGINAL) not in tr._translation_cache


def test_gemeo_servico_rapido_nao_e_cortado(monkeypatch):
    _com_tradutor_que_responde(monkeypatch, "Na próxima semana no Xbox")
    monkeypatch.setattr(tr, "_TRADUCAO_TIMEOUT_S", 5.0)
    assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == "Na próxima semana no Xbox"
    assert tr.degradacoes_totais() == 0


def test_traducao_roda_no_executor_do_tradutor(monkeypatch):
    """Thread presa no tradutor não pode tomar vaga do executor padrão (feeds, DNS, Discord)."""
    import threading
    nomes = []

    class _Registra:
        def translate(self, texto):
            nomes.append(threading.current_thread().name)
            return "Na próxima semana no Xbox"

    monkeypatch.setattr(tr, "_get_translator", lambda alvo: _Registra())
    assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == "Na próxima semana no Xbox"
    assert nomes and nomes[0].startswith("tradutor"), nomes
