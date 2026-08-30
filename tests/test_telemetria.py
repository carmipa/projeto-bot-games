"""
Guardas da telemetria de ausência.

O valor deste módulo está inteiro numa distinção: **zero porque não havia** contra **zero
porque quebrou**. Um detector que gritasse sempre passaria em todos os testes de "detecta
defeito" e seria inútil — o operador aprenderia a ignorar o alarme numa semana, que é a
forma mais eficaz de desligar um alerta sem o desligar.

Por isso cada teste de ANOMALIA tem par: um cenário gêmeo, saudável, que TEM de dar OK.
"""
import pytest

from core import telemetria as tel
from core.telemetria import Contadores


def _dia_calmo(**ajustes) -> Contadores:
    """Varredura saudável e sem novidade: 92 fontes ok, tudo respondeu 304."""
    base = dict(
        trigger="loop", fontes_total=92, fontes_com_erro=0, fontes_vazias=0,
        fontes_bloqueadas=0, cache_304=92, itens_novos=0, itens_filtrados=0,
        itens_publicados=0, alertas_html=0, entregas_falhadas=0,
        traducoes_degradadas=0, duracao_s=12.0,
    )
    base.update(ajustes)
    return Contadores(**base)


# ==========================================================================
# O par que define o módulo
# ==========================================================================

def test_zero_legitimo_e_OK_e_explica_o_motivo():
    """
    CONTROLE NEGATIVO, e o mais importante do ficheiro. Dia sem notícia nova é o caso
    COMUM. Se ele alarmasse, o alerta viraria ruído diário e ninguém leria o dia em que
    fosse a sério.
    """
    veredito, motivo = tel.avaliar(_dia_calmo())
    assert veredito == tel.VEREDITO_OK
    assert "304" in motivo and "não havia novidade" in motivo


def test_zero_por_defeito_e_ANOMALIA():
    """
    Mesma saída visível (0 publicados), causa oposta: havia 14 itens novos aprovados e
    nenhum saiu nem foi filtrado. Quem apanha é a invariante de conservação — e foi este
    teste que mostrou que o ramo dedicado que eu tinha escrito para o caso era inalcançável.
    """
    veredito, motivo = tel.avaliar(_dia_calmo(
        cache_304=0, itens_novos=14, itens_filtrados=0, itens_publicados=0,
    ))
    assert veredito == tel.VEREDITO_ANOMALIA
    assert "engoli" in motivo


# ==========================================================================
# Invariante de conservação: a telemetria a auditar-se a si própria
# ==========================================================================

def test_item_que_some_sem_ser_publicado_nem_filtrado_e_ANOMALIA():
    """
    Se alguém acrescentar um `continue` no laço de entradas e esquecer de contar, os itens
    desaparecem em silêncio — exatamente a classe de defeito desta auditoria. A conta
    `novos == filtrados + publicados` denuncia sozinha.
    """
    c = _dia_calmo(cache_304=0, itens_novos=10, itens_filtrados=3, itens_publicados=2)
    assert c.itens_sumidos == 5
    veredito, motivo = tel.avaliar(c)
    assert veredito == tel.VEREDITO_ANOMALIA
    assert "engoli" in motivo


def test_conservacao_fechada_nao_alarma():
    """CONTROLE: com a conta fechando, o mesmo cenário é saudável."""
    c = _dia_calmo(cache_304=0, itens_novos=10, itens_filtrados=3, itens_publicados=7)
    assert c.itens_sumidos == 0
    assert tel.avaliar(c)[0] == tel.VEREDITO_OK


def test_tudo_filtrado_e_OK_nao_anomalia():
    """10 itens novos e todos eram ruído é trabalho do filtro, não defeito."""
    c = _dia_calmo(cache_304=0, itens_novos=10, itens_filtrados=10, itens_publicados=0)
    veredito, motivo = tel.avaliar(c)
    assert veredito == tel.VEREDITO_OK
    assert "descartados pelo filtro" in motivo


# ==========================================================================
# Os defeitos reais desta semana, cada um como cenário
# ==========================================================================

def test_entrega_falhada_e_ANOMALIA():
    """Canal sem permissão: o bot vê notícia e não consegue publicar."""
    veredito, motivo = tel.avaliar(_dia_calmo(
        cache_304=0, itens_novos=5, itens_filtrados=0, itens_publicados=5,
        entregas_falhadas=2,
    ))
    assert veredito == tel.VEREDITO_ANOMALIA
    assert "entregas falharam" in motivo


def test_nenhuma_fonte_responde_e_ANOMALIA():
    veredito, motivo = tel.avaliar(_dia_calmo(
        fontes_com_erro=92, cache_304=0,
    ))
    assert veredito == tel.VEREDITO_ANOMALIA


def test_maioria_das_fontes_fora_aponta_para_a_rede_nao_para_as_fontes():
    """60 de 92 falhando não são 60 sites com problema no mesmo dia."""
    veredito, motivo = tel.avaliar(_dia_calmo(fontes_com_erro=60, cache_304=32))
    assert veredito == tel.VEREDITO_ANOMALIA
    assert "bloqueio de IP" in motivo or "rede" in motivo


def test_traducao_degradada_e_ATENCAO_nao_anomalia():
    """
    O incidente de 2026-08-30. Publicar em inglês é degradação, não perda: o bot continua
    a entregar valor. ANOMALIA aqui seria exagero e gastaria a atenção do operador.
    """
    veredito, motivo = tel.avaliar(_dia_calmo(
        cache_304=0, itens_novos=8, itens_filtrados=1, itens_publicados=7,
        traducoes_degradadas=14,
    ))
    assert veredito == tel.VEREDITO_ATENCAO
    assert "idioma original" in motivo


def test_poucas_fontes_com_erro_e_ATENCAO_com_a_receita():
    veredito, motivo = tel.avaliar(_dia_calmo(fontes_com_erro=3, cache_304=89))
    assert veredito == tel.VEREDITO_ATENCAO
    assert "probe_sources.py" in motivo, "o aviso tem de dizer o que fazer a seguir"


def test_catalogo_vazio_e_ANOMALIA():
    """O sources.json congelado ou ilegível no Docker cai aqui."""
    veredito, motivo = tel.avaliar(_dia_calmo(fontes_total=0, cache_304=0))
    assert veredito == tel.VEREDITO_ANOMALIA
    assert "sources.json" in motivo


# ==========================================================================
# Todo veredito carrega motivo — a regra que impede o número mudo de voltar
# ==========================================================================

@pytest.mark.parametrize("c", [
    _dia_calmo(),
    _dia_calmo(fontes_com_erro=92, cache_304=0),
    _dia_calmo(cache_304=0, itens_novos=10, itens_filtrados=3, itens_publicados=2),
    _dia_calmo(entregas_falhadas=1),
    _dia_calmo(traducoes_degradadas=5),
    _dia_calmo(fontes_vazias=2, cache_304=90),
    _dia_calmo(fontes_total=0, cache_304=0),
    _dia_calmo(cache_304=0, itens_novos=4, itens_filtrados=1, itens_publicados=3),
])
def test_nenhum_veredito_sai_sem_motivo(c):
    veredito, motivo = tel.avaliar(c)
    assert veredito in (tel.VEREDITO_OK, tel.VEREDITO_ATENCAO, tel.VEREDITO_ANOMALIA)
    assert motivo and len(motivo) > 15, f"veredito {veredito} saiu com motivo vazio ou raso"


# ==========================================================================
# Persistência e histórico
# ==========================================================================

def test_registo_persiste_e_historico_e_limitado():
    estado = {}
    for i in range(tel._MAX_HISTORICO + 12):
        tel.registar(estado, tel.resumir(_dia_calmo(itens_publicados=i)))

    bloco = estado[tel.CHAVE_ESTADO]
    assert len(bloco["historico"]) == tel._MAX_HISTORICO, "histórico sem teto cresce sem fim"
    assert bloco["ultima"]["itens_publicados"] == tel._MAX_HISTORICO + 11
    assert tel.ultima(estado)["veredito"] in (tel.VEREDITO_OK, tel.VEREDITO_ATENCAO)


def test_registar_sobre_estado_corrompido_nao_levanta():
    """Chave com tipo errado (edição à mão, versão antiga) não pode derrubar a varredura."""
    estado = {tel.CHAVE_ESTADO: "isto devia ser um dict"}
    tel.registar(estado, tel.resumir(_dia_calmo()))
    assert isinstance(estado[tel.CHAVE_ESTADO], dict)
    assert tel.ultima(estado) is not None


def test_ultima_em_estado_vazio_devolve_None():
    assert tel.ultima({}) is None
    assert tel.vereditos_recentes({}) == []


# ==========================================================================
# Agendador morto — o defeito do on_ready abortado
# ==========================================================================

def test_agendador_parado_e_detectado():
    from datetime import datetime, timedelta, timezone
    antigo = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec="seconds")
    estado = {tel.CHAVE_ESTADO: {"ultima": {"quando": antigo, "veredito": "OK"}}}

    atrasada, motivo = tel.varredura_atrasada(estado, intervalo_min=360)
    assert atrasada is True
    assert "agendador pode estar parado" in motivo


def test_varredura_recente_nao_e_atraso():
    """CONTROLE: sem isto, um detector que diz sempre 'atrasado' passaria no teste acima."""
    from datetime import datetime, timezone
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    estado = {tel.CHAVE_ESTADO: {"ultima": {"quando": agora, "veredito": "OK"}}}
    atrasada, _ = tel.varredura_atrasada(estado, intervalo_min=360)
    assert atrasada is False


def test_sem_registo_nenhum_nao_acusa_atraso():
    """Bot recém-arrancado não é anomalia — afirmar atraso sem base é o falso alarme."""
    atrasada, motivo = tel.varredura_atrasada({}, intervalo_min=360)
    assert atrasada is False
    assert "nenhuma varredura registada" in motivo


def test_data_ilegivel_nao_acusa_atraso_nem_levanta():
    estado = {tel.CHAVE_ESTADO: {"ultima": {"quando": "ontem à tarde"}}}
    atrasada, motivo = tel.varredura_atrasada(estado, intervalo_min=360)
    assert atrasada is False
    assert "ilegível" in motivo
