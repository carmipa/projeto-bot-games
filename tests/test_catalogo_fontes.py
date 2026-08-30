"""
Guardas estruturais do `sources.json`. Nenhuma toca na rede — a saude das fontes mede-se
com `scripts/probe_sources.py`; aqui garante-se a coerencia do catalogo, que apodrece em
silencio e so aparece como "o bot esta lento" ou "o bot assinou o canal errado".

As tres invariantes que estas guardas protegem:

  CAT-1  Todo handle `@` em `youtube_feeds` tem entrada em `youtube_feed_map`.
         Sem ela, a varredura faz uma requisicao HTTP por handle so para descobrir o
         channel_id. Foi o que o mapa de 41 pares eliminou em 2026-08-01 (de 1 para 41).
         A falha e INVISIVEL: o bot funciona, so gasta ~50 requisicoes a mais por ciclo.

  CAT-2  Nenhum channel_id repete no mapa. Dois handles apontando para o mesmo canal
         publicam a mesma noticia duas vezes. Nao e hipotetico: `@PlayStationEurope`
         resolve para o channel_id de `@PlayStation` (medido em 2026-08-29).

  CAT-3  O mapa nao tem entradas orfas. Par que sobreviveu a remocao da fonte engana a
         proxima auditoria, que o le como fonte ativa.
"""
import json
import os
import re
from collections import Counter

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAMINHO = os.path.join(ROOT, "sources.json")


@pytest.fixture(scope="module")
def catalogo():
    with open(CAMINHO, "r", encoding="utf-8") as f:
        return json.load(f)


def test_catalogo_e_json_valido_e_nao_esta_vazio(catalogo):
    """
    Controle positivo de toda a suite deste ficheiro: se o catalogo estivesse vazio, as
    guardas abaixo passariam por nao terem o que verificar — verdes e cegas.
    """
    assert catalogo.get("rss_feeds"), "rss_feeds vazio: as guardas abaixo nao provariam nada"
    assert catalogo.get("youtube_feeds"), "youtube_feeds vazio"
    assert catalogo.get("youtube_feed_map"), "youtube_feed_map vazio"


def test_cat1_todo_handle_tem_par_no_mapa(catalogo):
    handles = [u for u in catalogo["youtube_feeds"] if "/@" in u]
    assert handles, "nenhum handle no catalogo: guarda cega"

    sem_par = [u for u in handles if u not in catalogo["youtube_feed_map"]]
    assert not sem_par, (
        "handle sem entrada em youtube_feed_map — cada um custa uma requisicao HTTP extra "
        "por varredura, e a resolucao pode devolver o canal errado:\n  "
        + "\n  ".join(sem_par)
    )


def test_cat2_nenhum_channel_id_repetido(catalogo):
    contagem = Counter(catalogo["youtube_feed_map"].values())
    repetidos = {feed: n for feed, n in contagem.items() if n > 1}
    assert not repetidos, (
        f"channel_id repetido no mapa — a mesma noticia seria publicada em duplicado: {repetidos}"
    )


def test_cat3_mapa_sem_entradas_orfas(catalogo):
    fontes = set(catalogo["youtube_feeds"])
    orfas = [k for k in catalogo["youtube_feed_map"] if k not in fontes]
    assert not orfas, (
        "youtube_feed_map tem par sem fonte correspondente em youtube_feeds; uma auditoria "
        f"futura leria isto como fonte ativa: {orfas}"
    )


def test_todo_feed_do_mapa_tem_forma_de_feed_atom(catalogo):
    """channel_id no formato UC + 22 caracteres. ID torto foi a causa de 14 fontes mortas."""
    padrao = re.compile(
        r"^https://www\.youtube\.com/feeds/videos\.xml\?channel_id=UC[A-Za-z0-9_-]{22}$"
    )
    tortos = [
        f"{handle} -> {feed}"
        for handle, feed in catalogo["youtube_feed_map"].items()
        if not padrao.match(feed)
    ]
    assert not tortos, "feed com forma invalida no mapa:\n  " + "\n  ".join(tortos)


def test_nenhuma_url_repetida_entre_as_secoes(catalogo):
    """URL repetida = feed baixado duas vezes por varredura e noticia publicada em duplicado."""
    todas = (
        catalogo["rss_feeds"]
        + catalogo["youtube_feeds"]
        + catalogo["official_sites_reference_(not_rss)"]
    )
    repetidas = {u: n for u, n in Counter(todas).items() if n > 1}
    assert not repetidas, f"URL repetida no catalogo: {repetidas}"


def test_toda_url_e_http_ou_https(catalogo):
    """load_sources() descarta silenciosamente o que nao comeca com http(s): fonte some sem aviso."""
    todas = (
        catalogo["rss_feeds"]
        + catalogo["youtube_feeds"]
        + catalogo["official_sites_reference_(not_rss)"]
    )
    invalidas = [u for u in todas if not u.startswith(("http://", "https://"))]
    assert not invalidas, (
        f"URL que load_sources() descartaria em silencio: {invalidas}"
    )


def test_calibracao_das_guardas_do_catalogo():
    """
    As guardas acima so valem se souberem reprovar. Aqui correm contra um catalogo-controle
    DOENTE, montado de proposito com um defeito de cada tipo. Se qualquer um passar, as
    guardas estao cegas e o veredito sobre o catalogo real nao vale.
    """
    doente = {
        "rss_feeds": ["https://a.com/feed", "https://a.com/feed"],          # repetida
        "youtube_feeds": [
            "https://www.youtube.com/@SemPar",                              # sem par no mapa
            "https://www.youtube.com/@Um",
            "https://www.youtube.com/@Dois",
            "ftp://invalida/feed",                                          # esquema invalido
        ],
        "youtube_feed_map": {
            "https://www.youtube.com/@Um": "https://www.youtube.com/feeds/videos.xml?channel_id=UCaaaaaaaaaaaaaaaaaaaaaa",
            "https://www.youtube.com/@Dois": "https://www.youtube.com/feeds/videos.xml?channel_id=UCaaaaaaaaaaaaaaaaaaaaaa",  # duplicado
            "https://www.youtube.com/@Orfao": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbbbbbbbbbbbbbbbbbbbbbb",  # orfa
            "https://www.youtube.com/@Torto": "https://www.youtube.com/feeds/videos.xml?channel_id=NAO_E_UC",                  # forma invalida
        },
        "official_sites_reference_(not_rss)": [],
    }

    reprovou = []
    for nome, funcao in (
        ("CAT-1 handle sem par", test_cat1_todo_handle_tem_par_no_mapa),
        ("CAT-2 id duplicado", test_cat2_nenhum_channel_id_repetido),
        ("CAT-3 entrada orfa", test_cat3_mapa_sem_entradas_orfas),
        ("forma do feed", test_todo_feed_do_mapa_tem_forma_de_feed_atom),
        ("url repetida", test_nenhuma_url_repetida_entre_as_secoes),
        ("esquema invalido", test_toda_url_e_http_ou_https),
    ):
        try:
            funcao(doente)
        except AssertionError:
            reprovou.append(nome)

    esperadas = 6
    assert len(reprovou) == esperadas, (
        f"apenas {len(reprovou)}/{esperadas} guardas acusaram o catalogo doente "
        f"({reprovou}) — as que ficaram caladas estao cegas"
    )
