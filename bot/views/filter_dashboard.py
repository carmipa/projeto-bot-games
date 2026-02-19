"""
Dashboard view - Painel com apenas seletor de idioma (filtros removidos).
"""
import discord
from typing import Dict, Any
import logging

from utils.storage import p, load_json_safe, save_json_safe

log = logging.getLogger("GameBot")


class FilterDashboard(discord.ui.View):
    """
    Painel do GameBot: apenas seletor de idioma.
    Filtros foram removidos — todas as notícias são enviadas ao canal configurado.
    """

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = str(guild_id)
        self._rebuild()

    def _cfg(self) -> Dict[str, Any]:
        """Carrega config.json e garante estrutura mínima por guild."""
        cfg = load_json_safe(p("config.json"), {})
        if not isinstance(cfg, dict):
            log.error("config.json inválido. Recriando.")
            cfg = {}
        cfg.setdefault(self.guild_id, {"channel_id": None})
        return cfg

    def _save(self, cfg: Dict[str, Any]) -> None:
        save_json_safe(p("config.json"), cfg)

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        try:
            return bool(interaction.user.guild_permissions.administrator)
        except (AttributeError, Exception):
            return False

    def _get_lang(self) -> str:
        cfg = self._cfg()
        return cfg[self.guild_id].get("language", "en_US")

    def _set_lang(self, lang_code: str) -> None:
        cfg = self._cfg()
        cfg[self.guild_id]["language"] = lang_code
        self._save(cfg)

    def _rebuild(self) -> None:
        """Apenas botões de idioma."""
        self.clear_items()
        current_lang = self._get_lang()
        languages = {
            "en_US": "🇺🇸",
            "pt_BR": "🇧🇷",
            "es_ES": "🇪🇸",
            "it_IT": "🇮🇹",
            "ja_JP": "🇯🇵"
        }
        for code, flag in languages.items():
            style = discord.ButtonStyle.primary if code == current_lang else discord.ButtonStyle.secondary
            btn = discord.ui.Button(
                emoji=flag,
                style=style,
                custom_id=f"gamesbot:lang:{self.guild_id}:{code}",
                row=0
            )
            btn.callback = self._lang_callback
            self.add_item(btn)

    async def _lang_callback(self, interaction: discord.Interaction):
        """Troca o idioma."""
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)
            return
        parts = interaction.data.get("custom_id", "").split(":")
        if len(parts) < 4:
            await interaction.response.send_message("❌ Erro ao processar.", ephemeral=True)
            return
        lang_code = parts[3]
        self._set_lang(lang_code)
        self._rebuild()
        flags = {"en_US": "🇺🇸", "pt_BR": "🇧🇷", "es_ES": "🇪🇸", "it_IT": "🇮🇹", "ja_JP": "🇯🇵"}
        flag = flags.get(lang_code, "🏳️")
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🌐 Idioma alterado para {flag} **{lang_code}**", ephemeral=True)
