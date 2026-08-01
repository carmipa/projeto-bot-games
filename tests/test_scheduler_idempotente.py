"""
Trava de regressão do agendador: on_ready dispara de novo a cada reconexão do gateway,
e start_scheduler tem de continuar com UM loop só. Nenhuma rede: run_scan_once é
substituído e wait_until_ready nunca resolve, então o corpo do loop não chega a correr.
"""
import asyncio

import pytest

try:
    import discord  # noqa: F401
    _DISCORD_OK = True
except Exception:
    _DISCORD_OK = False

pytestmark = pytest.mark.skipif(
    not _DISCORD_OK, reason="discord.py indisponível neste interpretador"
)


class _BotFalso:
    """wait_until_ready que nunca resolve: o loop arranca mas não executa varredura."""

    def __init__(self):
        self._nunca = asyncio.Event()

    async def wait_until_ready(self):
        await self._nunca.wait()


def _cenario(chamadas: int):
    import core.scanner as scanner

    async def _sem_varredura(bot, trigger="loop"):
        return None

    async def _run():
        original_scan = scanner.run_scan_once
        original_task = scanner.loop_task
        scanner.run_scan_once = _sem_varredura
        scanner.loop_task = None
        try:
            bot = _BotFalso()
            loops = []
            for _ in range(chamadas):
                scanner.start_scheduler(bot)
                loops.append(scanner.loop_task)
            await asyncio.sleep(0.05)
            ativos = [
                t for t in asyncio.all_tasks() if "news_scan_loop" in (t.get_name() or "")
            ]
            # Captura o estado ANTES de cancelar: is_running() lido depois do cancel
            # devolve False e o teste mediria o cleanup, não o comportamento.
            rodando = [bool(lp is not None and lp.is_running()) for lp in loops]
            resultado = (loops, rodando, len(ativos))
            for lp in {id(x): x for x in loops if x is not None}.values():
                lp.cancel()
            await asyncio.sleep(0)
            return resultado
        finally:
            scanner.run_scan_once = original_scan
            scanner.loop_task = original_task

    return asyncio.run(_run())


def test_start_scheduler_cria_um_loop():
    loops, rodando, ativos = _cenario(1)
    assert loops[0] is not None
    assert rodando[0], "o loop não ficou em execução após start_scheduler"
    assert ativos == 1


def test_start_scheduler_repetido_nao_duplica_loop():
    """
    Antes desta correção o resultado era 2 tasks ativas e dois objetos Loop distintos —
    um agendador extra por reconexão, acumulando ao longo dos dias.
    """
    loops, rodando, ativos = _cenario(3)
    assert loops[0] is loops[1] is loops[2], "start_scheduler criou um Loop novo"
    assert all(rodando), "o loop original devia continuar em execução"
    assert ativos == 1, f"esperado 1 loop de varredura ativo, encontrados {ativos}"
