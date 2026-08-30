"""
Recuperacao do incidente de 2026-08-30 (traducao devolvia pagina de erro do Google).

PROPOSITO DE NEGOCIO: devolver ao canal as noticias que foram publicadas como lixo. Elas
"tiveram sucesso" no envio, entao o link entrou no dedup e no historico — e a noticia
verdadeira NUNCA mais sairia, nem depois de o tradutor voltar ao normal. Corrigir o codigo
impede a repeticao; so isto desfaz o estrago.

INVARIANTES DO DOMINIO:
  1. Faz BACKUP de state.json e history.json antes de tocar em qualquer coisa, e aborta se
     o backup falhar. Sem backup nao se mexe em estado de producao.
  2. Age por FONTE, nao por item: remove o balde de dedup da(s) fonte(s) indicada(s) e os
     links daquele dominio no historico. Nao ha como identificar item a item quais sairam
     com lixo — o estado nao guarda o que foi publicado, so que foi.
  3. NAO toca em `http_cache`. Se tocasse, a fonte seria rebaixada inteira; deixando como
     esta, o ETag ja avancou e o feed sera relido normalmente na proxima varredura.
  4. So repoe o que ainda esta na janela de MAX_NEWS_AGE_DAYS (7 dias). Item mais velho
     que isso o proprio scanner descarta — nao ha como o trazer de volta.

COMPORTAMENTO EM CASO DE FALHA: qualquer erro de leitura, backup ou escrita aborta ANTES
de gravar, com mensagem e saida != 0. `--simular` (padrao) nao escreve nada: mostra o que
seria feito. So `--aplicar` grava.

Uso, na maquina onde o bot roda (na VPS, dentro do container ou com DATA_DIR apontado):
    python scripts/repor_noticias_perdidas.py --fonte https://news.xbox.com/en-us/feed/
    python scripts/repor_noticias_perdidas.py --fonte https://news.xbox.com/en-us/feed/ --aplicar
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.storage import p, load_json_safe, save_json_safe, create_backup  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Repoe noticias publicadas como pagina de erro")
    ap.add_argument("--fonte", action="append", required=True,
                    help="URL da fonte cujo dedup sera limpo (pode repetir)")
    ap.add_argument("--aplicar", action="store_true",
                    help="grava as alteracoes; sem isto so simula")
    args = ap.parse_args()

    caminho_state = p("state.json")
    caminho_hist = p("history.json")

    state = load_json_safe(caminho_state, None)
    if not isinstance(state, dict):
        print(f"ERRO: {caminho_state} ausente ou ilegivel. Nada foi alterado.", file=sys.stderr)
        return 2
    historico = load_json_safe(caminho_hist, None)
    if not isinstance(historico, list):
        print(f"ERRO: {caminho_hist} ausente ou ilegivel. Nada foi alterado.", file=sys.stderr)
        return 2

    dedup = state.get("dedup", {})
    if not isinstance(dedup, dict):
        print("ERRO: state['dedup'] nao e um dicionario. Nada foi alterado.", file=sys.stderr)
        return 2

    dominios = set()
    total_links = 0
    ausentes = []
    for fonte in args.fonte:
        links = dedup.get(fonte)
        if links is None:
            ausentes.append(fonte)
            continue
        total_links += len(links) if isinstance(links, list) else 0
        dominios.add(urlparse(fonte).netloc.lower())

    for f in ausentes:
        print(f"aviso: fonte sem balde de dedup (nada a repor): {f}")

    if not dominios:
        print("NAO VERIFICOU: nenhuma das fontes indicadas tem dedup. Confira a URL exata "
              "como aparece em sources.json.", file=sys.stderr)
        return 2

    do_historico = [l for l in historico
                    if isinstance(l, str) and urlparse(l).netloc.lower() in dominios]

    print(f"fontes atingidas : {len(dominios)}")
    print(f"links no dedup   : {total_links}  (serao esquecidos e republicados)")
    print(f"links no historico: {len(do_historico)}  (serao removidos)")
    print("nota: so volta ao canal o que ainda tiver menos de 7 dias; o resto o proprio "
          "scanner descarta por idade.")

    if not args.aplicar:
        print("\nSIMULACAO — nada foi gravado. Repita com --aplicar para executar.")
        return 0

    # Invariante 1: sem backup nao se mexe.
    for caminho in (caminho_state, caminho_hist):
        if create_backup(caminho) is None:
            print(f"ERRO: backup de {caminho} falhou. Abortado sem gravar.", file=sys.stderr)
            return 2

    for fonte in args.fonte:
        dedup.pop(fonte, None)
    state["dedup"] = dedup
    save_json_safe(caminho_state, state)

    restante = [l for l in historico
                if not (isinstance(l, str) and urlparse(l).netloc.lower() in dominios)]
    save_json_safe(caminho_hist, restante)

    print(f"\nfeito. historico: {len(historico)} -> {len(restante)} links.")
    print("A proxima varredura republica as noticias dentro da janela de 7 dias.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
