# Auditoria Profunda — GameBot v2.1 → v2.2.0

**Data:** 2026-07-12 · **Branch:** `fix/auditoria-2026-07-12` · **Autor:** Paulo (carmipa) + Claude Code

Análise cruzada por 4 frentes (segurança, desempenho/memória, bugs/testes, arquitetura/deploy) + leitura direta dos arquivos-núcleo. Todos os achados foram validados contra o código instalado.

---

## Veredito geral

Bot funcional e consciente de segurança (anti-SSRF com resolução DNS, autorização na maioria dos comandos, sanitização de logs, escrita JSON atômica, container não-root via `gosu`, logs com rotação). **Não vaza memória** de forma relevante. Tinha 1 exposição HIGH de segredo, 2 bugs HIGH latentes e dívidas de arquitetura/deploy — todos endereçados nesta auditoria.

---

## Achados e correções aplicadas

### Segurança
| Sev | Achado | Correção |
|-----|--------|----------|
| HIGH | `.dockerignore` não excluía `.env` → `COPY . .` assava `DISCORD_TOKEN`/`WEB_AUTH_TOKEN` na imagem. (Token **não** vazou pelo git — `.gitignore` protege; git history confirma) | `.dockerignore` += `.env`/`.env.*`. **Rotação NÃO necessária** desde que nenhuma imagem já construída tenha sido enviada a um registry compartilhado/público (o `docker-compose build` só monta local, sem push). Tokens estão protegidos. |
| MED | `/now` e botão "Verificar Agora" sem checagem de permissão (DoS) | Gate de Administrador em ambos |
| MED | Redirects seguidos sem revalidar anti-SSRF | *Mantido* (quebrar redirect prejudica sites que redirecionam www/https); risco baixo (fontes só via operador) |
| MED | Sem `allowed_mentions` → `@everyone` via título de feed | `allowed_mentions.none()` no Bot |
| MED | Web sem auth quando `WEB_AUTH_TOKEN` vazio | *Documentado*; `.env.example` mantém token vazio, mas deploy publica só em `127.0.0.1` |
| LOW | Limites Compose ignorados fora do Swarm; sem hardening | `mem_limit`/`cpus` a nível de serviço + `no-new-privileges` + `cap_drop: ALL` (+caps mínimas) |
| LOW | Token web comparado com `!=` (timing) | `hmac.compare_digest` |
| LOW | IP interno (`192.168.0.50/Guarulhos`) em embed público | Removido |
| LOW | `subprocess(shell=True)` em git_info | Lista de args, `shell=False` |

### Bugs / Correção
| Sev | Achado | Correção |
|-----|--------|----------|
| HIGH | `except discord.InvalidArgument` (classe removida na discord.py 2.x) → `AttributeError` não capturado abortava a varredura e causava repost | `except (ValueError, TypeError)` |
| HIGH | Lost-update de `state.json` entre scan longo (até 125 min) e comandos | Reload+merge do state antes do save final (preserva `last_announced_hash` etc.) |
| MED | Auto-limpeza de 7 dias zerava `dedup` inteiro → repost em massa | Limita a 500 links/feed + poda caches órfãos; sem wipe |
| MED | `save_json_safe` sem `fsync` antes do `os.replace` | `f.flush(); os.fsync()` |
| LOW | Timestamp de embed sem data: `datetime.now()` naive rotulado como UTC (offset errado) | `datetime.now(timezone.utc)` |
| LOW | Sem cap de tamanho pós-tradução (post descartado) | `description[:4096]`, `content[:2000]` |
| LOW | Shadowing do helper `p` (path) no loop de og:image | `for pat in patterns` |

### Desempenho / Memória
**Sem vazamento** (history cap 2000, ClientSession fechada por scan, logs rotacionados). Problemas de CPU/latência em rajada corrigidos:
- HTML Monitor: BeautifulSoup movido para `run_in_executor` (não bloqueia mais o event loop/heartbeat) + downloads limitados por `Semaphore(MAX_CONCURRENT_FEEDS)` (antes: 31 páginas baixadas juntas).
- Tradução: reuso de instância `GoogleTranslator` por idioma + cache LRU (512) — corta round-trips repetidos ao Google.
- Filtro de ruído: uma alternância regex pré-compilada (era ~50 `re.search`/entrada).
- Poda de `http_cache`/`source_failures` órfãos no cleanup (evita inchar `state.json` ao longo de meses).

### Testes / Deps / Deploy
- **Estado anterior:** `pytest` completo **derrubava o interpretador** (aiohttp TestServer sob Python 3.14); venv 3.14 com `_ctypes` quebrado impedia `import discord`.
- `test_utils` passou a testar o `clean_html` **real** (era cópia local); novos `test_content_filter` (filtro de produção) e `test_storage_atomic` (atomicidade/recuperação).
- Testes web e os que importam `discord` são **skipped** no interpretador problemático → suíte reporta **47 passed / 5 skipped / 0 failed** em vez de crashar.
- Dependências com piso acima de CVEs (aiohttp ≥3.10.11, jinja2 ≥3.1.6) + teto de major.
- `HEALTHCHECK` real via `/health` (antes só checava existência de `config.json`).
- Removido `icon.png` duplicado (2 MB, não referenciado).

---

## Fase 2 (2026-07-12) — pendências resolvidas

1. **Rotação de tokens:** dispensável. `.env` nunca foi commitado (protegido) e o build Docker é local; a rotação só seria necessária se uma imagem já construída tivesse sido pushed a um registry compartilhado.
2. **Venv recriada com Python 3.12** (o 3.14 local tinha `_ctypes` quebrado; achado em `%LOCALAPPDATA%\Programs\Python\Python312`). Deps instaladas; suíte agora **59 passed, 0 skipped, exit 0** — inclusive os testes web e de scanner antes pulados.
3. **`run_scan_once()` decomposto** (~590 → ~464 linhas): extraídos `build_news_message()` (puro, testável) e `_run_html_monitor()`; +7 testes novos cobrindo construção de embed e dispatch de alerta (áreas antes sem cobertura).
4. **httpx → aiohttp consolidado**: `html_monitor` e `add_sources_script` migrados; `httpx` removido do requirements (verificado: bot roda sem httpx instalado; `check_official_sites` buscou os 29 sites reais via aiohttp).
5. **i18n:** decisão do Paulo — manter respostas de comando em pt-BR (bot é pt-BR single-user); notícias seguem traduzidas p/ o idioma do servidor. README ajustado para refletir isso.
6. **Legado Gundam/Gunpla:** decisão do Paulo — **manter** a exclusão (ele tem um bot de Gundam separado; exclusão é intencional). Sem mudança de código.

Verificação da Fase 2: 4 commits adicionais na `main` (venv não versionada); `import main` + suíte 59 passed na venv 3.12.

---

## Commits desta auditoria (branch `fix/auditoria-2026-07-12`)

```
seguranca: fecha vazamentos e endurece autorizacao
bugfix: corrige repost, lost-update de state e robustez de escrita
desempenho: tira bloqueio do event loop e corta round-trips de traducao
deps/deploy: pin de versoes, hardening do container e healthcheck real
testes: cobre filtro real e atomicidade do storage; suite deixa de crashar
docs: reconcilia com a realidade + changelog da auditoria
```
