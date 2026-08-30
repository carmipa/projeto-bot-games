"""
Telemetria de AUSÊNCIA — o que o painel de sucessos não conseguia dizer.

PROPÓSITO DE NEGÓCIO: responder, depois de cada varredura, a pergunta que os contadores
antigos não respondiam — *não saiu notícia nenhuma porque não havia notícia, ou porque
alguma coisa quebrou?* O painel media só sucesso (`scans_completed`, `news_posted`,
`cache_hits`) e tinha um `feeds_failed` que nunca era incrementado: um campo que sempre
dizia `0`, indistinguível de "nada falhou".

É a regra do job silencioso aplicada a este bot: `0` processado sem motivo conhecido é
ALERTA, não sucesso. Sete dos doze defeitos encontrados na auditoria de 2026-08-29/30
teriam aparecido aqui — o `on_ready` abortado (varredura parada com uptime a crescer), o
`sources.json` congelado no Docker (contagem de fontes menor que o catálogo), o ETag
gravado antes da entrega, e o tradutor a devolver página de erro.

INVARIANTES DO DOMÍNIO:
  1. Todo veredito vem acompanhado de MOTIVO em português. Veredito sem motivo é o mesmo
     número mudo que este módulo existe para eliminar.
  2. `OK` com zero publicações é um resultado legítimo e tem de ser dito como tal — senão
     o alerta vira ruído diário e deixa de ser lido.
  3. CONSERVAÇÃO DE ITENS: todo item que passou o dedup termina publicado ou filtrado. A
     diferença é `itens_sumidos`, e qualquer valor > 0 é ANOMALIA. É a telemetria a
     auditar-se a si própria: sem isto, um `continue` novo no laço engoliria itens em
     silêncio, que é exatamente a classe de defeito desta auditoria.
  4. O histórico é limitado a `_MAX_HISTORICO` execuções. Diagnóstico não pode virar o
     maior consumidor do `state.json`.

COMPORTAMENTO EM CASO DE FALHA: `resumir()` nunca levanta — recebe contadores já apurados
e devolve sempre um registo com veredito. Falha ao gravar o registo é problema do
`save_json_safe`, que já regista e segue: perder telemetria não pode derrubar a varredura.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List

# Chave em state.json. Classificada em utils/storage.py como metadado preservado: o rasto
# de diagnóstico tem de sobreviver a uma limpeza, senão desaparece justamente quando se
# está a investigar o incidente que motivou a limpeza.
CHAVE_ESTADO = "saude_varredura"

_MAX_HISTORICO = 30

# Acima desta fração de fontes com erro, o problema é do bot ou da rede — não das fontes.
_FRACAO_ERRO_CRITICA = 0.5

VEREDITO_OK = "OK"
VEREDITO_ATENCAO = "ATENCAO"
VEREDITO_ANOMALIA = "ANOMALIA"


@dataclass
class Contadores:
    """O que a varredura observou. Preenchido por run_scan_once."""
    trigger: str = "desconhecido"
    fontes_total: int = 0
    fontes_com_erro: int = 0
    fontes_vazias: int = 0
    fontes_bloqueadas: int = 0
    cache_304: int = 0
    itens_novos: int = 0          # passaram o dedup — candidatos reais
    itens_filtrados: int = 0      # descartados por idade, falta de data ou ruído
    itens_publicados: int = 0
    alertas_html: int = 0
    entregas_falhadas: int = 0
    traducoes_degradadas: int = 0
    duracao_s: float = 0.0

    @property
    def fontes_ok(self) -> int:
        indisponiveis = self.fontes_com_erro + self.fontes_bloqueadas
        return max(0, self.fontes_total - indisponiveis)

    @property
    def itens_sumidos(self) -> int:
        """
        Invariante 3: todo item que passou o dedup sai por UMA de três portas —
        publicado, filtrado ou com entrega falhada.

        A terceira porta faltava na primeira versão, e o teste de integração apanhou:
        numa falha de entrega o item não era publicado nem filtrado, a conservação
        disparava primeiro e o motivo dizia "algum caminho está a engoli-los" quando a
        causa era conhecida e específica. Veredito certo, diagnóstico errado — que é o
        defeito que este módulo existe para não cometer.
        """
        contabilizados = self.itens_filtrados + self.itens_publicados + self.entregas_falhadas
        return max(0, self.itens_novos - contabilizados)


@dataclass
class RegistoDeSaude:
    quando: str
    trigger: str
    duracao_s: float
    fontes_total: int
    fontes_ok: int
    fontes_com_erro: int
    fontes_vazias: int
    fontes_bloqueadas: int
    cache_304: int
    itens_novos: int
    itens_filtrados: int
    itens_publicados: int
    alertas_html: int
    entregas_falhadas: int
    traducoes_degradadas: int
    itens_sumidos: int
    veredito: str
    motivo: str

    def dict(self) -> Dict[str, Any]:
        return asdict(self)


def _motivo_do_zero(c: Contadores) -> str:
    """Explica, em português, por que nada foi publicado. É o coração deste módulo."""
    if c.fontes_total == 0:
        return "nenhuma fonte carregada — sources.json vazio ou ilegível"
    if c.fontes_ok == 0:
        return f"nenhuma das {c.fontes_total} fontes respondeu"
    if c.itens_novos == 0:
        if c.cache_304 >= c.fontes_ok:
            return (
                f"não havia novidade: as {c.cache_304} fontes saudáveis responderam 304 "
                f"(sem alteração desde a última varredura)"
            )
        return (
            f"não havia item novo: tudo o que as {c.fontes_ok} fontes devolveram já "
            f"estava no dedup"
        )
    if c.itens_filtrados >= c.itens_novos:
        return (
            f"os {c.itens_novos} itens novos foram todos descartados pelo filtro "
            f"(ruído, idade acima do limite ou falta de data)"
        )
    return "nada publicado apesar de haver item novo aprovado"


def avaliar(c: Contadores) -> tuple[str, str]:
    """
    PROPÓSITO DE NEGÓCIO: transformar contadores em veredito acionável.

    INVARIANTES DO DOMÍNIO: zero publicações só é ANOMALIA quando havia motivo para haver
    publicação. Alarmar em todo dia calmo treinaria o operador a ignorar o alarme, que é a
    forma mais eficaz de desligar um alerta sem o desligar.

    COMPORTAMENTO EM CASO DE FALHA: nunca levanta; na dúvida devolve ATENCAO com o motivo,
    nunca OK silencioso.
    """
    # --- ANOMALIA: alguma coisa está partida ---
    if c.itens_sumidos > 0:
        return VEREDITO_ANOMALIA, (
            f"{c.itens_sumidos} itens passaram o dedup e não foram publicados nem "
            f"filtrados — algum caminho do laço está a engoli-los em silêncio"
        )
    if c.entregas_falhadas > 0:
        return VEREDITO_ANOMALIA, (
            f"{c.entregas_falhadas} entregas falharam (canal sem permissão, canal "
            f"inexistente ou erro do Discord); o cache HTTP dessas fontes não avançou"
        )
    if c.fontes_total == 0:
        # O catalogo vazio caia no ramo final e saia como OK — o detector tinha o buraco
        # exatamente na falha que ele existe para apanhar (sources.json congelado,
        # ilegivel ou vazio no Docker). Apanhado pelo proprio teste, em 2026-08-30.
        return VEREDITO_ANOMALIA, _motivo_do_zero(c)
    if c.fontes_ok == 0:
        return VEREDITO_ANOMALIA, f"nenhuma das {c.fontes_total} fontes respondeu"
    if c.fontes_total > 0:
        fracao = (c.fontes_com_erro + c.fontes_bloqueadas) / c.fontes_total
        if fracao > _FRACAO_ERRO_CRITICA:
            return VEREDITO_ANOMALIA, (
                f"{c.fontes_com_erro + c.fontes_bloqueadas} de {c.fontes_total} fontes "
                f"indisponíveis ({fracao:.0%}) — suspeitar de rede, DNS ou bloqueio de IP, "
                f"não das fontes"
            )
    # NAO existe aqui um ramo "havia item novo e nada saiu": ele seria inalcancavel, porque
    # `novos > 0 e publicados == 0 e filtrados < novos` implica `itens_sumidos > 0` e a
    # conservacao ja o apanhou acima. Escrevi-o na primeira versao e o teste mostrou que era
    # codigo morto — ramo morto numa funcao de decisao e pior que ausente: sugere cobertura
    # que nao existe.

    # --- ATENCAO: funciona, mas degradado ---
    if c.traducoes_degradadas > 0:
        return VEREDITO_ATENCAO, (
            f"{c.traducoes_degradadas} traduções degradadas — notícias publicadas no "
            f"idioma original. Serviço de tradução indisponível ou a bloquear por excesso "
            f"de pedidos"
        )
    if c.fontes_com_erro > 0 or c.fontes_bloqueadas > 0:
        return VEREDITO_ATENCAO, (
            f"{c.fontes_com_erro} fontes com erro e {c.fontes_bloqueadas} bloqueadas por "
            f"segurança, de {c.fontes_total}. Rode "
            f"`python scripts/probe_sources.py --catalogo` para saber quais"
        )
    if c.fontes_vazias > 0:
        return VEREDITO_ATENCAO, (
            f"{c.fontes_vazias} fontes responderam 200 sem entrada nenhuma — sintoma de "
            f"feed descontinuado ou bloqueio parcial"
        )

    # --- OK: incluindo o zero legítimo, dito com todas as letras ---
    if c.itens_publicados == 0 and c.alertas_html == 0:
        return VEREDITO_OK, _motivo_do_zero(c)
    return VEREDITO_OK, (
        f"{c.itens_publicados} notícias e {c.alertas_html} alertas publicados a partir de "
        f"{c.fontes_ok} fontes saudáveis"
    )


def resumir(c: Contadores) -> RegistoDeSaude:
    """Converte contadores em registo persistível, já com veredito e motivo."""
    veredito, motivo = avaliar(c)
    return RegistoDeSaude(
        quando=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        trigger=c.trigger,
        duracao_s=round(c.duracao_s, 1),
        fontes_total=c.fontes_total,
        fontes_ok=c.fontes_ok,
        fontes_com_erro=c.fontes_com_erro,
        fontes_vazias=c.fontes_vazias,
        fontes_bloqueadas=c.fontes_bloqueadas,
        cache_304=c.cache_304,
        itens_novos=c.itens_novos,
        itens_filtrados=c.itens_filtrados,
        itens_publicados=c.itens_publicados,
        alertas_html=c.alertas_html,
        entregas_falhadas=c.entregas_falhadas,
        traducoes_degradadas=c.traducoes_degradadas,
        itens_sumidos=c.itens_sumidos,
        veredito=veredito,
        motivo=motivo,
    )


def registar(state: Dict[str, Any], registo: RegistoDeSaude) -> None:
    """Guarda o registo em state[CHAVE_ESTADO], limitando o histórico."""
    bloco = state.get(CHAVE_ESTADO)
    if not isinstance(bloco, dict):
        bloco = {}
    historico = bloco.get("historico")
    if not isinstance(historico, list):
        historico = []
    historico.append(registo.dict())
    bloco["ultima"] = registo.dict()
    bloco["historico"] = historico[-_MAX_HISTORICO:]
    state[CHAVE_ESTADO] = bloco


def ultima(state: Dict[str, Any]) -> Dict[str, Any] | None:
    bloco = state.get(CHAVE_ESTADO)
    if isinstance(bloco, dict) and isinstance(bloco.get("ultima"), dict):
        return bloco["ultima"]
    return None


def vereditos_recentes(state: Dict[str, Any], quantos: int = 5) -> List[str]:
    bloco = state.get(CHAVE_ESTADO)
    if not isinstance(bloco, dict):
        return []
    hist = bloco.get("historico")
    if not isinstance(hist, list):
        return []
    return [str(r.get("veredito", "?")) for r in hist[-quantos:] if isinstance(r, dict)]


def varredura_atrasada(state: Dict[str, Any], intervalo_min: int, tolerancia: float = 2.0):
    """
    PROPÓSITO DE NEGÓCIO: detectar o agendador morto — o defeito em que o bot fica online,
    responde a comandos e simplesmente nunca varre. Foi assim que a falha do dashboard web
    a abortar o `on_ready` passou despercebida.

    INVARIANTES DO DOMÍNIO: compara o relógio com o registo, nunca com um estado anotado.
    Sem varredura registada, devolve `(False, motivo)` — bot recém-arrancado não é anomalia.

    COMPORTAMENTO EM CASO DE FALHA: data ilegível no registo devolve `(False, motivo)` em
    vez de levantar. Não saber é diferente de estar atrasado, e afirmar atraso sem base
    seria o falso alarme que treina o operador a ignorar.
    """
    reg = ultima(state)
    if not reg:
        return False, "nenhuma varredura registada ainda"
    try:
        quando = datetime.fromisoformat(str(reg.get("quando")))
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False, "data da última varredura ilegível no registo"

    minutos = (datetime.now(timezone.utc) - quando).total_seconds() / 60
    limite = intervalo_min * tolerancia
    if minutos > limite:
        return True, (
            f"última varredura há {minutos:.0f} min, com intervalo configurado de "
            f"{intervalo_min} min — o agendador pode estar parado"
        )
    return False, f"última varredura há {minutos:.0f} min"
