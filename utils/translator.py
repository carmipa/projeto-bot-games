"""
Translator utilities - Localization and Google Translate wrapper.
"""
import time
import logging
import asyncio
from collections import OrderedDict
from typing import Dict, Any, Optional
from deep_translator import GoogleTranslator

from utils.portas import ContratoDaPortaViolado
from utils.storage import p, load_json_safe

log = logging.getLogger("GameBot")

# Reuso de instâncias do GoogleTranslator por idioma (antes: nova instância a cada chamada)
_translator_instances: Dict[str, GoogleTranslator] = {}
# Cache LRU de traduções para evitar round-trips repetidos ao Google (mesmo texto/idioma)
_translation_cache: "OrderedDict[tuple, str]" = OrderedDict()
_TRANSLATION_CACHE_MAX = 512


def _get_translator(target: str) -> GoogleTranslator:
    inst = _translator_instances.get(target)
    if inst is None:
        inst = GoogleTranslator(source="auto", target=target)
        _translator_instances[target] = inst
    return inst


class Translator:
    """Gerencia traduções e localizações."""
    
    def __init__(self):
        self.translations: Dict[str, dict] = {}
        self.default_lang = 'en_US'
        self.supported_langs = ['en_US', 'pt_BR']
        self._load_all()
    
    def _load_all(self):
        """Carrega todos arquivos de tradução."""
        for lang in self.supported_langs:
            try:
                # Caminho: translations/en_US.json
                path = p(f"translations/{lang}.json")
                data = load_json_safe(path, {})
                if data:
                    self.translations[lang] = data
                    log.info(f"🌍 Tradução carregada: {lang}")
                else:
                    log.warning(f"⚠️ Tradução vazia ou não encontrada: {lang}")
            except Exception as e:
                log.error(f"Erro ao carregar tradução {lang}: {e}")

    def detect_lang(
        self,
        guild_id: str,
        guild_locale: str = None,
        guild_lang_map: Dict[str, str] | None = None
    ) -> str:
        """
        Detecta idioma do servidor.
        Prioridade: 
        1. Config manual (config.json)
        2. Locale do servidor Discord
        3. Padrão (en_US)
        """
        # 1. Mapa em memória (hot path otimizado)
        if guild_lang_map and guild_id in guild_lang_map:
            return guild_lang_map[guild_id]

        # 2. Config manual (fallback)
        config = load_json_safe(p("config.json"), {})
        if guild_id in config and "language" in config[guild_id]:
            return config[guild_id]["language"]
        
        # 3. Locale do Discord (ex: 'pt-BR' -> 'pt_BR')
        if guild_locale:
            # Converte enum para string e normaliza
            locale_str = str(guild_locale)
            normalized = locale_str.replace('-', '_')
            
            if normalized in self.supported_langs:
                return normalized
            
            # Apenas inglês e português Brasil
            maps = {
                'en-GB': 'en_US',
                'pt-BR': 'pt_BR'
            }
            return maps.get(locale_str, self.default_lang)
            
        return self.default_lang

    def get(self, key: str, lang: str = 'en_US', **kwargs) -> str:
        """
        Obtém texto traduzido por chave (ex: 'commands.help.title').
        Suporta formatação com **kwargs.
        """
        if lang not in self.translations:
            lang = self.default_lang

        keys = key.split('.')
        value = self.translations.get(lang, {})
        
        try:
            for k in keys:
                value = value[k]
            
            if isinstance(value, str):
                return value.format(**kwargs)
            return str(value)
            
        except (KeyError, TypeError):
            # Tenta fallback para inglês
            if lang != self.default_lang:
                return self.get(key, lang=self.default_lang, **kwargs)
            return key

# Instância global
t = Translator()


# =========================================================
# VALIDAÇÃO DA RESPOSTA DO TRADUTOR
# =========================================================
#
# Incidente de 2026-08-30, visto em produção: o canal recebeu notícias cujo TÍTULO e
# RESUMO eram, os dois, `Error 500 (Server Error)!!1500.That's an error.There was an
# error. Please try again later.That's all we know.`
#
# O `deep_translator` NÃO levanta exceção quando o Google responde com página de erro —
# devolve o TEXTO da página como se fosse a tradução. O único guarda existente era
# `if trad is None`, que uma string nunca aciona. A cadeia de dano tinha três elos:
#   1. a página de erro era publicada como título e resumo;
#   2. era GRAVADA no cache LRU, repetindo-se para todo texto igual;
#   3. o envio "teve sucesso", então o link entrava no dedup — e a notícia verdadeira
#      nunca mais seria publicada, nem depois de o tradutor voltar ao normal.
#
# O elo 3 é o caro, e é a mesma classe do ETag gravado antes da entrega: "entreguei lixo"
# contava como "entreguei".
#
# Estas assinaturas são o texto padrão das páginas de erro do Google. `!!1` é o marcador
# que elas todas carregam. Falso positivo aqui é barato — publica-se o texto original,
# que é sempre aceitável; falso negativo é que custa caro.
_ASSINATURAS_DE_PAGINA_DE_ERRO = (
    "!!1",
    "that's an error",
    "that’s an error",
    "that's all we know",
    "that’s all we know",
)

# Disjuntor: bloqueio por excesso de pedidos afeta a varredura inteira, não um item.
# Insistir só prolonga o bloqueio e enche o canal de originais quando poderia parar de
# tentar por uns minutos.
_FALHAS_ATE_DEGRADAR = 5
_DEGRADACAO_SEGUNDOS = 600
_falhas_consecutivas = 0
_degradado_ate = 0.0
# Cumulativo desde o arranque. A telemetria de ausencia le a diferenca entre varreduras
# para poder dizer "publicado sem traducao" — sem contador, essa degradacao so apareceria
# no canal, que foi exatamente como o incidente de 2026-08-30 foi descoberto.
_degradacoes_totais = 0


def _traducao_utilizavel(trad) -> bool:
    """
    PROPÓSITO DE NEGÓCIO: decidir se o que voltou do tradutor é mesmo uma tradução, e não
    uma página de erro travestida de sucesso.

    INVARIANTES DO DOMÍNIO: só devolve True para string não vazia que não carregue
    assinatura de página de erro do Google. A comparação é feita em minúsculas sobre o
    texto inteiro, porque a assinatura aparece no meio da página, não no começo.

    COMPORTAMENTO EM CASO DE FALHA: qualquer coisa que não seja `str` (None, bytes, um
    objeto do tradutor) devolve False — sem levantar. Recusar de mais é seguro: quem
    chama publica o texto original.
    """
    if not isinstance(trad, str):
        return False
    if not trad.strip():
        return False
    baixo = trad.lower()
    return not any(a in baixo for a in _ASSINATURAS_DE_PAGINA_DE_ERRO)


def _registrar_falha() -> None:
    """Conta a falha e abre o disjuntor quando elas se acumulam."""
    global _falhas_consecutivas, _degradado_ate, _degradacoes_totais
    _falhas_consecutivas += 1
    _degradacoes_totais += 1
    if _falhas_consecutivas >= _FALHAS_ATE_DEGRADAR and time.monotonic() >= _degradado_ate:
        _degradado_ate = time.monotonic() + _DEGRADACAO_SEGUNDOS
        log.error(
            "🌐 [Tradutor] %s falhas seguidas — provavelmente bloqueio por excesso de "
            "pedidos. Publicando SEM tradução pelos próximos %s minutos, em vez de "
            "insistir e prolongar o bloqueio.",
            _falhas_consecutivas, _DEGRADACAO_SEGUNDOS // 60,
        )


def _reset_estado_do_tradutor() -> None:
    """Zera contadores, disjuntor e cache. Existe para os testes não herdarem estado."""
    global _falhas_consecutivas, _degradado_ate, _degradacoes_totais
    _falhas_consecutivas = 0
    _degradado_ate = 0.0
    _degradacoes_totais = 0
    _translation_cache.clear()


def degradacoes_totais() -> int:
    """Quantas vezes se publicou sem traduzir desde o arranque. Lido pela telemetria."""
    return _degradacoes_totais


async def translate_to_target(text: str, target_lang: str) -> str:
    """
    PROPÓSITO DE NEGÓCIO: entregar o título e o resumo da notícia no idioma do servidor.
    Tradução é melhoria de leitura, nunca requisito: notícia em inglês continua a ser
    notícia, página de erro do Google não é.

    INVARIANTES DO DOMÍNIO: o que sai daqui é a tradução OU o texto original — nunca uma
    terceira coisa. Resultado que não passa em `_traducao_utilizavel` não é publicado nem
    entra no cache. Só resultado validado é memorizado.

    COMPORTAMENTO EM CASO DE FALHA: devolve o `text` recebido, e regista em WARNING (não
    em debug: publicar sem tradução é degradação visível e tem de aparecer no log). Nunca
    levanta. Depois de `_FALHAS_ATE_DEGRADAR` falhas seguidas abre um disjuntor de
    `_DEGRADACAO_SEGUNDOS`, durante o qual devolve o original sem sequer chamar o serviço.
    """
    if not text:
        return ""

    # `_degradado_ate` NAO entra aqui: e so lido nesta funcao (quem o atribui e
    # `_registrar_falha`). `global` de nome nunca reatribuido e F824, que o
    # `--select=F82` do CI captura por prefixo — o mesmo defeito corrigido em 2026-08-29.
    global _falhas_consecutivas

    # Mapeia códigos internos (pt_BR) para códigos Google (pt)
    google_map = {
        'pt_BR': 'pt',
        'en_US': 'en',
    }
    target = google_map.get(target_lang) or 'en'

    # Cache LRU: mesmo texto+idioma não refaz round-trip ao Google
    cache_key = (target, text)
    cached = _translation_cache.get(cache_key)
    if cached is not None:
        _translation_cache.move_to_end(cache_key)
        return cached

    # Disjuntor: enquanto degradado, devolve o original SEM chamar o Google. Insistir
    # durante um bloqueio por excesso de pedidos só prolonga o bloqueio, e cada tentativa
    # devolveria outra página de erro.
    agora = time.monotonic()
    if agora < _degradado_ate:
        return text

    try:
        loop = asyncio.get_running_loop()
        translator = _get_translator(target)
        trad = await loop.run_in_executor(None, translator.translate, text)
    except Exception as e:
        log.warning(
            "🌐 Tradução falhou (%s: %s). Publicando o texto original.",
            type(e).__name__, e,
        )
        _registrar_falha()
        return text

    try:
        if not _traducao_utilizavel(trad):
            # Violação de CONTRATO, não falha de rede: o adaptador respondeu com sucesso e
            # devolveu lixo. A distinção importa — foi por confundir as duas que a página
            # de erro do Google acabou publicada como notícia.
            raise ContratoDaPortaViolado(
                "tradutor",
                "resposta bem-sucedida com conteúdo de página de erro",
                str(trad or ""),
            )
    except ContratoDaPortaViolado as violacao:
        log.warning("🌐 %s. Publicando o texto original.", violacao)
        _registrar_falha()
        return text

    # Só chega aqui o que passou na validação — resultado inválido NUNCA entra no cache.
    _falhas_consecutivas = 0
    _translation_cache[cache_key] = trad
    _translation_cache.move_to_end(cache_key)
    if len(_translation_cache) > _TRANSLATION_CACHE_MAX:
        _translation_cache.popitem(last=False)
    return trad
