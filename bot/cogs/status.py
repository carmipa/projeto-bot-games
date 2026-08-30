"""
Status cog - /status command to show bot statistics.
"""
import discord
import logging
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta

from core import telemetria
from core.stats import stats
from settings import LOOP_MINUTES
from utils.storage import p, load_json_safe

log = logging.getLogger("GameBot")


def _is_admin(interaction: discord.Interaction) -> bool:
    """True se o autor da interação tem permissão de Administrador na guild."""
    member = interaction.user
    perms = getattr(member, "guild_permissions", None)
    return bool(perms and perms.administrator)


class ScanButton(discord.ui.View):
    def __init__(self, run_scan_func):
        super().__init__(timeout=None)
        self.run_scan = run_scan_func

    @discord.ui.button(label="Verificar Agora", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="status_scan_now")
    async def scan_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        # Só administradores podem disparar varredura manual (evita abuso/DoS)
        if not _is_admin(interaction):
            await interaction.followup.send("❌ Apenas administradores podem forçar uma varredura.", ephemeral=True)
            return
        try:
            # Feedback imediato
            await interaction.followup.send("🔎 Iniciando verificação manual...", ephemeral=True)
            
            # Executa o scan
            await self.run_scan(trigger="manual_button")
            
            # Confirmação
            await interaction.followup.send("✅ Verificação concluída! Se houver notícias novas, elas foram enviadas para o canal.", ephemeral=True)
        except Exception as e:
            log.exception(f"Erro ao executar verificação manual: {type(e).__name__}: {e}")
            try:
                await interaction.followup.send(f"❌ Erro ao verificar: {type(e).__name__}", ephemeral=True)
            except Exception as send_err:
                log.warning(f"Falha ao enviar mensagem de erro ao usuário: {send_err}")


class StatusCog(commands.Cog):
    """Cog com comando de status do bot."""
    
    def __init__(self, bot, run_scan_once_func):
        self.bot = bot
        self.run_scan_once = run_scan_once_func
    
    @app_commands.command(name="status", description="Mostra estatísticas do bot.")
    async def status(self, interaction: discord.Interaction):
        """Exibe estatísticas e status atual do bot."""
        await interaction.response.defer(ephemeral=True) # Fix timeout
        
        # Calcula próxima varredura
        next_scan = datetime.now() + timedelta(minutes=LOOP_MINUTES)
        next_scan_ts = int(next_scan.timestamp())
        
        embed = discord.Embed(
            title="🎮 Status do GameBot",
            color=discord.Color.from_rgb(255, 0, 32),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="⏰ Uptime",
            value=stats.format_uptime(),
            inline=True
        )
        
        # Saúde ANTES dos números, ocupando a linha inteira. Um contador de varreduras não
        # diz se elas estão a funcionar: foi um painel só de sucessos que deixou o bot ficar
        # online sem varrer e o catálogo congelar no Docker sem ninguém notar.
        # Lido do state.json e não da memória — sobrevive a reinício do contêiner, que é
        # justamente quando se quer saber o que aconteceu antes.
        estado_disco = load_json_safe(p("state.json"), {})
        registo = telemetria.ultima(estado_disco) or {}
        veredito = registo.get("veredito")
        emoji_saude = {
            telemetria.VEREDITO_ANOMALIA: "🔴",
            telemetria.VEREDITO_ATENCAO: "🟡",
            telemetria.VEREDITO_OK: "🟢",
        }.get(veredito, "⚪")

        if veredito:
            linhas_saude = [f"{emoji_saude} **{veredito}** — {registo.get('motivo', '')}"]
        else:
            linhas_saude = ["⚪ Nenhuma varredura registada ainda."]

        atrasada, motivo_atraso = telemetria.varredura_atrasada(estado_disco, LOOP_MINUTES)
        if atrasada:
            linhas_saude.append(f"🔴 **Agendador suspeito:** {motivo_atraso}")

        embed.add_field(
            name="🩺 Saúde da última varredura",
            value="\n".join(linhas_saude)[:1024],
            inline=False,
        )

        if veredito:
            embed.add_field(
                name="🔎 Fontes",
                value="\n".join([
                    f"{registo.get('fontes_ok', 0)}/{registo.get('fontes_total', 0)} ok",
                    f"{registo.get('fontes_com_erro', 0)} com erro",
                    f"{registo.get('fontes_vazias', 0)} vazias",
                ]),
                inline=True,
            )
            embed.add_field(
                name="📥 Itens",
                value="\n".join([
                    f"{registo.get('itens_novos', 0)} novos",
                    f"{registo.get('itens_filtrados', 0)} filtrados",
                    f"{registo.get('itens_publicados', 0)} publicados",
                ]),
                inline=True,
            )
            degradadas = registo.get("traducoes_degradadas", 0)
            falhadas = registo.get("entregas_falhadas", 0)
            if degradadas or falhadas:
                embed.add_field(
                    name="⚠️ Degradações",
                    value="\n".join([
                        f"{degradadas} traduções degradadas",
                        f"{falhadas} entregas falhadas",
                    ]),
                    inline=True,
                )

        embed.add_field(
            name="📡 Varreduras",
            value=f"{stats.scans_completed}",
            inline=True
        )
        
        embed.add_field(
            name="📰 Notícias Enviadas",
            value=f"{stats.news_posted}",
            inline=True
        )
        
        embed.add_field(
            name="📦 Cache Hits Total",
            value=f"{stats.cache_hits_total}",
            inline=True
        )
        
        if stats.last_scan_time:
            last_scan_str = f"<t:{int(stats.last_scan_time.timestamp())}:R>"
        else:
            last_scan_str = "Nenhuma ainda"
        
        embed.add_field(
            name="🕐 Última Varredura",
            value=last_scan_str,
            inline=True
        )
        
        embed.add_field(
            name="⏳ Próxima Varredura",
            value=f"<t:{next_scan_ts}:R>",
            inline=True
        )
        
        interval_str = f"{LOOP_MINUTES // 60}h" if LOOP_MINUTES >= 60 else f"{LOOP_MINUTES} min"
        embed.set_footer(text=f"Bot v2.1 | Intervalo: {interval_str}")
        
        # Adiciona o botão de scan
        view = ScanButton(self.run_scan_once)
        
        # EPHEMERAL: Apenas o usuário que digitou vê a mensagem.
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="now", description="Força uma verificação imediata de notícias.")
    async def now(self, interaction: discord.Interaction):
        """Verifica notícias imediatamente."""
        await interaction.response.defer(ephemeral=True)
        # Só administradores podem forçar varredura (evita abuso/DoS por membros comuns)
        if not _is_admin(interaction):
            await interaction.followup.send("❌ Apenas administradores podem forçar uma varredura.", ephemeral=True)
            return
        try:
            await interaction.followup.send("🚀 Iniciando varredura manual (comando /now)...", ephemeral=True)
            await self.run_scan_once(trigger="command_now")
            await interaction.followup.send("✅ Scan finalizado.", ephemeral=True)
        except Exception as e:
            log.exception(f"Erro ao executar comando /now: {type(e).__name__}: {e}")
            try:
                await interaction.followup.send(f"❌ Erro: {type(e).__name__}", ephemeral=True)
            except Exception as send_err:
                log.warning(f"Falha ao enviar mensagem de erro ao usuário: {send_err}")


async def setup(bot, run_scan_once_func):
    """Setup function para carregar o cog."""
    await bot.add_cog(StatusCog(bot, run_scan_once_func))
