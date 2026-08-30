"""
Sonda de saude de fontes — usa o CAMINHO REAL do bot, nao um cliente HTTP paralelo.

PROPOSITO DE NEGOCIO: responder, com evidencia colavel, se uma URL candidata (ou o
catalogo inteiro) rende noticia de verdade para o GameBot. O criterio e o mesmo que o
`_schema` do sources.json declara desde a v3.0: HTTP 200, pelo menos uma entrada, e item
mais recente com menos de 180 dias. Serve para admitir fonte nova e para reauditar o
catalogo depois de meses parado.

INVARIANTES DO DOMINIO:
  1. A sonda usa `utils.http.get_robust_headers`, `certifi` e `feedparser` — os mesmos que
     `core.scanner.fetch_and_process_feed`. Sonda com cliente diferente mede outra coisa.
  2. Handle do YouTube e resolvido por `core.scanner._fetch_youtube_channel_id_from_page`,
     que usa as tres ancoras da propria pagina. Resolver por conta propria reintroduziria o
     bug de 2026-08-01 (assinar o canal recomendado da barra lateral).
  3. O titulo do feed resolvido e SEMPRE impresso. Handle ocupado por terceiro devolve 200
     com entradas — so o titulo denuncia (`@EA` -> "Albania", `@2K` -> "cloner").
  4. A sonda so vale depois de passar na CALIBRACAO: um controle positivo (fonte que TEM de
     passar) e um controle negativo (URL que TEM de reprovar). Instrumento que nunca foi
     visto dizendo NAO nao prova nada quando diz SIM.

COMPORTAMENTO EM CASO DE FALHA: tres estados de saida, nunca dois.
  0 = PASSOU        todas as URLs sondadas estao saudaveis
  1 = REPROVOU      pelo menos uma URL sondada esta doente
  2 = NAO VERIFICOU a calibracao falhou ou nao havia alvo — nao e aprovacao nem reprovacao

Uso:
    python scripts/probe_sources.py --catalogo
    python scripts/probe_sources.py https://exemplo.com/feed https://www.youtube.com/@Canal
    python scripts/probe_sources.py --arquivo candidatos.txt --json saida.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import aiohttp  # noqa: E402
import certifi  # noqa: E402
import feedparser  # noqa: E402

from core.filters import should_skip_by_content  # noqa: E402
from core.scanner import (  # noqa: E402
    _fetch_youtube_channel_id_from_page,
    _is_youtube_feed_url,
    _is_youtube_url,
    parse_entry_dt,
    should_skip_generic_youtube_false_positive,
)
from utils.http import get_robust_headers  # noqa: E402

IDADE_MAXIMA_DIAS = 180
TIMEOUT_SEGUNDOS = 40
CONCORRENCIA = 5

# --- Casos-controle da calibracao -------------------------------------------------
# Positivo: feed oficial estavel, no catalogo desde a v3.0. TEM de passar.
CONTROLE_POSITIVO = "https://blog.playstation.com/feed/"
# Negativo: channel_id sintaticamente valido e inexistente. TEM de reprovar com 404.
# (Mesma forma dos 14 IDs corrompidos removidos em 2026-08-01.)
CONTROLE_NEGATIVO = "https://www.youtube.com/feeds/videos.xml?channel_id=UCzzzzzzzzzzzzzzzzzzzzzz"


@dataclass
class Resultado:
    url: str
    url_resolvida: str
    tipo: str
    status: int | None
    entradas: int
    titulo_feed: str
    idade_dias: int | None
    saudavel: bool
    motivo: str
    # Volume medido: itens das ultimas 24h que SOBREVIVEM ao LIXO_FILTER de producao.
    # Estimar volume "no olho" foi o que deixou 7 fontes fora do catalogo sem numero;
    # aqui o numero sai do mesmo `should_skip_by_content` que roda na varredura.
    posts_24h: int = 0
    posts_7d: int = 0

    def linha(self) -> str:
        marca = "OK  " if self.saudavel else "FALHA"
        idade = f"{self.idade_dias}d" if self.idade_dias is not None else "-"
        resolvida = "" if self.url_resolvida == self.url else f"\n        -> {self.url_resolvida}"
        vol = f" pos_filtro_24h={self.posts_24h} 7d={self.posts_7d}" if self.tipo == "feed" else ""
        return (
            f"[{marca}] ({self.tipo}) {self.url}{resolvida}\n"
            f"        status={self.status} entradas={self.entradas} recente={idade}{vol} "
            f"titulo={self.titulo_feed!r}"
            + (f"\n        motivo: {self.motivo}" if not self.saudavel else "")
        )


async def _resolver(session: aiohttp.ClientSession, url: str, timeout: aiohttp.ClientTimeout) -> str:
    """Handle/canal do YouTube -> feed Atom, pelo resolvedor de producao."""
    if not _is_youtube_url(url) or _is_youtube_feed_url(url):
        return url
    return await _fetch_youtube_channel_id_from_page(session, url, {}, timeout)


async def sondar(
    session: aiohttp.ClientSession,
    url: str,
    timeout: aiohttp.ClientTimeout,
    tipo: str = "feed",
) -> Resultado:
    """
    tipo='feed' : criterio de RSS/Atom — 200 + >=1 entrada + item mais recente < 180d.
    tipo='html' : criterio do HTML Monitor — 200 e corpo nao vazio. Sondar um site
                  institucional com criterio de feed produz FALHA falsa: ele nunca teve
                  entradas, e nem por isso esta doente. A chave do filtro tem de ser a
                  chave da coisa.
    """
    resolvida = await _resolver(session, url, timeout)

    if _is_youtube_url(url) and not _is_youtube_feed_url(url) and resolvida == url:
        return Resultado(url, resolvida, tipo, None, 0, "", None, False,
                         "handle do YouTube nao resolveu para channel_id (pagina 404 ou sem ancora)")

    try:
        async with session.get(resolvida, headers=get_robust_headers(), timeout=timeout) as resp:
            status = resp.status
            if status != 200:
                return Resultado(url, resolvida, tipo, status, 0, "", None, False, f"HTTP {status}")
            texto = await resp.text(errors="ignore")
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        return Resultado(url, resolvida, tipo, None, 0, "", None, False, f"{type(e).__name__}: {e}")

    if tipo == "html":
        if not texto.strip():
            return Resultado(url, resolvida, tipo, status, 0, "", None, False,
                             "HTTP 200 com corpo vazio — o HTML Monitor nao consegue tirar hash")
        return Resultado(url, resolvida, tipo, status, 0, "", None, True, "")

    feed = feedparser.parse(texto)
    entradas = getattr(feed, "entries", []) or []
    titulo = str(getattr(getattr(feed, "feed", None), "title", "") or "")

    if not entradas:
        return Resultado(url, resolvida, tipo, status, 0, titulo, None, False,
                         "HTTP 200 sem entradas (bloqueio parcial, HTML no lugar de XML ou feed morto)")

    agora = datetime.now(timezone.utc)
    idades = []
    posts_24h = 0
    posts_7d = 0
    for e in entradas:
        dt = parse_entry_dt(e)
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dias = (agora - dt).days
        idades.append(dias)

        # Volume que CHEGARIA ao canal: aplica os mesmos descartes da varredura.
        titulo_e = e.get("title") or ""
        resumo_e = e.get("summary") or e.get("description") or ""
        link_e = e.get("link") or ""
        if should_skip_by_content(titulo_e, resumo_e):
            continue
        if should_skip_generic_youtube_false_positive(resolvida, titulo_e, link_e):
            continue
        if dias < 1:
            posts_24h += 1
        if dias <= 7:
            posts_7d += 1

    if not idades:
        return Resultado(url, resolvida, tipo, status, len(entradas), titulo, None, False,
                         "nenhuma entrada tem data (REQUIRE_ENTRY_DATE=1 descartaria todas)")

    recente = min(idades)
    if recente > IDADE_MAXIMA_DIAS:
        return Resultado(url, resolvida, tipo, status, len(entradas), titulo, recente, False,
                         f"congelado: item mais recente com {recente} dias (max {IDADE_MAXIMA_DIAS})",
                         posts_24h, posts_7d)

    return Resultado(url, resolvida, tipo, status, len(entradas), titulo, recente, True, "",
                     posts_24h, posts_7d)


async def _sondar_todas(alvos: list[tuple[str, str]]) -> list[Resultado]:
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEGUNDOS)
    sem = asyncio.Semaphore(CONCORRENCIA)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async def _uma(alvo: tuple[str, str]) -> Resultado:
            url, tipo = alvo
            async with sem:
                return await sondar(session, url, timeout, tipo)

        return list(await asyncio.gather(*[_uma(a) for a in alvos]))


async def calibrar() -> tuple[bool, str]:
    """
    Roda os dois casos-controle. So depois disto a saida sobre as demais URLs vale.
    Devolve (calibrada, explicacao).
    """
    positivo, negativo = await _sondar_todas(
        [(CONTROLE_POSITIVO, "feed"), (CONTROLE_NEGATIVO, "feed")]
    )
    if not positivo.saudavel:
        return False, (
            f"controle POSITIVO reprovou ({CONTROLE_POSITIVO}: {positivo.motivo}). "
            "A sonda, a rede ou o proprio caminho do bot esta quebrado — o veredito sobre "
            "as outras URLs nao vale."
        )
    if negativo.saudavel:
        return False, (
            f"controle NEGATIVO passou ({CONTROLE_NEGATIVO}). A sonda nao sabe dizer NAO; "
            "qualquer 'OK' abaixo seria indistinguivel de cegueira."
        )
    return True, (
        f"controle positivo OK ({positivo.entradas} entradas, mais recente {positivo.idade_dias}d) | "
        f"controle negativo reprovou como esperado ({negativo.motivo})"
    )


def urls_do_catalogo() -> list[tuple[str, str]]:
    """Devolve (url, tipo) — o tipo vem da secao do sources.json em que a URL vive."""
    caminho = os.path.join(_ROOT, "sources.json")
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    alvos: list[tuple[str, str]] = []
    for chave, tipo in (
        ("rss_feeds", "feed"),
        ("youtube_feeds", "feed"),
        ("official_sites_reference_(not_rss)", "html"),
    ):
        alvos.extend((u, tipo) for u in dados.get(chave, []) if isinstance(u, str))
    return alvos


def main() -> int:
    ap = argparse.ArgumentParser(description="Sonda de saude de fontes do GameBot")
    ap.add_argument("urls", nargs="*", help="URLs candidatas a sondar")
    ap.add_argument("--catalogo", action="store_true", help="sonda tudo que ja esta em sources.json")
    ap.add_argument("--arquivo", help="arquivo texto com uma URL por linha (# = comentario)")
    ap.add_argument("--html", action="store_true",
                    help="trata as URLs da linha de comando/arquivo como sites do HTML Monitor")
    ap.add_argument("--json", help="grava o resultado bruto em JSON neste caminho")
    ap.add_argument("--sem-calibracao", action="store_true",
                    help="PERIGO: pula os casos-controle. Use so para depurar a propria sonda.")
    args = ap.parse_args()

    tipo_manual = "html" if args.html else "feed"
    alvos: list[tuple[str, str]] = [(u, tipo_manual) for u in args.urls]
    if args.arquivo:
        with open(args.arquivo, "r", encoding="utf-8") as f:
            alvos.extend(
                (linha.strip(), tipo_manual) for linha in f
                if linha.strip() and not linha.strip().startswith("#")
            )
    if args.catalogo:
        alvos.extend(urls_do_catalogo())

    # dedup mantendo ordem
    vistos: set[str] = set()
    alvos = [a for a in alvos if not (a[0] in vistos or vistos.add(a[0]))]

    if not alvos:
        print("NAO VERIFICOU: nenhuma URL alvo. Use --catalogo, --arquivo ou passe URLs.",
              file=sys.stderr)
        return 2

    if not args.sem_calibracao:
        calibrada, explicacao = asyncio.run(calibrar())
        print(f"[calibracao] {explicacao}\n")
        if not calibrada:
            print("NAO VERIFICOU: instrumento nao calibrado.", file=sys.stderr)
            return 2
    else:
        print("[calibracao] PULADA por --sem-calibracao — este resultado nao e evidencia.\n")

    resultados = asyncio.run(_sondar_todas(alvos))
    for r in resultados:
        print(r.linha())

    doentes = [r for r in resultados if not r.saudavel]
    print(f"\nresumo: {len(resultados) - len(doentes)}/{len(resultados)} saudaveis")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in resultados], f, indent=2, ensure_ascii=False)
        print(f"json: {args.json}")

    return 1 if doentes else 0


if __name__ == "__main__":
    sys.exit(main())
