"""
Portas: o contrato de tudo o que SAI deste bot.

PROPÓSITO DE NEGÓCIO: dar nome e regra ao que o bot espera de cada serviço externo, para
que a semântica de falha do adaptador pare de vazar para dentro do caso de uso. É a única
peça de desacoplamento que a regra de arquitetura do vault manda ter aqui (§5.5, "toda
saída da fatia passa por porta declarada") — e é a que tinha dano medido atrás dela.

O incidente que a justifica, 2026-08-30: o `deep_translator` devolveu a página de erro do
Google COMO SE FOSSE a tradução. Não levantou exceção, não devolveu `None` — devolveu uma
string plausível. O caso de uso publicou-a como título e resumo, guardou-a em cache e
marcou a notícia como entregue, de modo que a verdadeira nunca mais sairia.

Nenhuma quantidade de `try/except` no chamador teria apanhado isso: o adaptador estava a
mentir dentro do contrato, não a falhar fora dele. O que apanha é **validar a saída do
adaptador contra o contrato declarado** — o mesmo princípio de "o instrumento também
precisa de prova", aplicado à fronteira.

INVARIANTES DO DOMÍNIO:
  1. Adaptador que viola o contrato levanta `ContratoDaPortaViolado`. Ele NÃO é devolvido
     ao chamador nem memorizado. Silenciar aqui foi o defeito original.
  2. Violação de contrato NÃO derruba a varredura: o invólucro converte em degradação
     declarada e CONTA. Notícia em inglês continua a ser notícia; página de erro não é.
  3. Toda degradação é contável. Sem contador, a telemetria de ausência não teria como
     dizer "publicado sem tradução" e o operador voltaria a descobrir pelo canal.

COMPORTAMENTO EM CASO DE FALHA: ver cada função. Nenhuma propaga exceção para o caso de
uso — a fronteira absorve e reporta.

POR QUE VIVE EM `utils/` E NÃO EM `core/`: neste projeto `utils/` é o kernel técnico e
`core/` é a fatia funcional. A regra de arquitetura do vault tem como invariante 1 que o
kernel não conhece fatia funcional — e `utils/translator.py` precisa deste contrato. Pôr
as portas em `core/` obrigaria o kernel a importar da fatia e inverteria a seta, que é a
única coisa que sustenta o desenho inteiro. Tipo de erro-raiz é kernel por definição na
tabela da regra.
"""
from __future__ import annotations

from typing import Protocol


class ContratoDaPortaViolado(Exception):
    """
    O adaptador respondeu com sucesso, mas devolveu algo que o contrato proíbe.

    Distinta de propósito de uma falha de rede: aquela é o mundo a não colaborar, esta é o
    nosso lado a receber lixo achando que é dado. Confundir as duas foi como a página de
    erro do Google chegou ao canal do Discord.
    """

    def __init__(self, porta: str, motivo: str, amostra: str = ""):
        self.porta = porta
        self.motivo = motivo
        self.amostra = amostra[:120]
        super().__init__(f"[{porta}] {motivo}" + (f" | recebido: {self.amostra!r}" if amostra else ""))


class DegradacaoAceitavel(Exception):
    """
    O serviço externo não está disponível, e existe um caminho degradado que preserva o
    valor de negócio (publicar sem traduzir, publicar sem imagem).

    Existe para separar-se de `ContratoDaPortaViolado`: aqui não há dado errado, há dado
    ausente. Perder a distinção é o que faz "não consegui" e "consegui lixo" acabarem no
    mesmo `except Exception: pass`.
    """


class TradutorPort(Protocol):
    """
    Contrato do serviço de tradução.

    O que o bot exige de qualquer adaptador:
      - devolve `str` NÃO vazia;
      - o que devolve é uma tradução, não uma página de erro, um HTML ou uma mensagem de
        diagnóstico do fornecedor;
      - não levanta para o caso de uso.

    Quem não cumpre viola o contrato, e a fronteira trata disso — o caso de uso nunca vê
    conteúdo inválido.
    """

    async def traduzir(self, texto: str, idioma_alvo: str) -> str:
        ...
