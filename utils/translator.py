"""
Translator utilities - Localization and Google Translate wrapper.
"""
import json
import logging
import asyncio
from collections import OrderedDict
from typing import Dict, Any, Optional
from deep_translator import GoogleTranslator

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


async def translate_to_target(text: str, target_lang: str) -> str:
    """
    Traduz texto para idioma alvo usando Google Translate.
    target_lang: 'pt', 'en', 'es', 'it'
    """
    if not text:
        return ""
        
    try:
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

        loop = asyncio.get_running_loop()
        translator = _get_translator(target)
        trad = await loop.run_in_executor(None, translator.translate, text)
        if trad is None:
            return text

        _translation_cache[cache_key] = trad
        _translation_cache.move_to_end(cache_key)
        if len(_translation_cache) > _TRANSLATION_CACHE_MAX:
            _translation_cache.popitem(last=False)
        return trad
    except Exception as e:
        log.debug(f"Falha na tradução de texto (retornando original): {type(e).__name__}: {e}")
        return text
