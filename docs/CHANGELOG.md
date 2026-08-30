# 📝 Changelog - GameBot

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

---

## [2.3.0] - 2026-08-29 — Auditoria de segurança/engenharia + catálogo v3.1

Relatório com evidência colada: `analises/2026-08-29_auditoria-seguranca-engenharia-fontes.md`.

### Crítico
- **Falha do dashboard web abortava o `on_ready` inteiro.** `on_ready` é handler de evento:
  a exceção era engolida pelo discord.py e **tudo o que vinha depois** — sync de comandos,
  agendador, anúncio de versão — deixava de rodar. Bastava a porta 8080 ocupada para o bot
  ficar online, responder `/ping` e **nunca varrer**, sem log que ligasse causa e efeito.
  Agora `start_web_server_tolerante()` contém a falha; guarda em `tests/test_web_server_tolerante.py`.
- **Perda permanente de notícia por ETag prematuro.** `update_cache_state()` gravava o
  ETag logo após o HTTP 200, *antes* de publicar. Falha de entrega (sem permissão no canal,
  canal apagado, 5xx do Discord) não punha o link no dedup mas gravava o ETag ⇒ a varredura
  seguinte recebia 304 e aquelas notícias sumiam para sempre. O cache só avança quando o
  feed inteiro foi processado sem falha de entrega.

### Segurança
- **DNS bloqueante dentro do event loop.** `validate_url()` chama `socket.getaddrinfo` e era
  usada de dentro de corrotinas — ~92 feeds + 29 sites por ciclo. Cada resolução lenta
  segurava o loop inteiro, incluindo o heartbeat do gateway. Criada `validate_url_async()`
  (usa `loop.getaddrinfo`); as duas partilham a mesma política, sem cópia.
- **Sanitização de log não cobria formatação preguiçosa.** `SecurityFilter` limpava só o
  molde: em `log.error("feed %s falhou", url)`, o argumento passava intacto. Passa a
  sanitizar a mensagem renderizada.
- **Logger do dashboard não chegava ao arquivo.** Era `getLogger("GameNewsWeb")`, irmão e não
  filho de `GameBot`: sem handlers e sem `SecurityFilter`. "Token inválido do IP X" — evento
  de segurança — nunca entrava em `logs/bot.log`. Agora é `GameBot.web`.
- **CI ganhou varredura de dependências vulneráveis** (`pip-audit`), que era GAP declarado.
  Reprova em qualquer CVE nova; a única exceção é nominal, datada e justificada
  (PYSEC-2022-252 do `deep-translator`, sem versão de correção — artefato instalado
  verificado: wheel pura, sem `setup.py`/`.pth`/`subprocess`/`eval`/`environ`).

### Correção
- **O passo de lint do CI estava vermelho** e, sendo anterior ao `pytest`, deixava a suíte
  sem rodar no CI. Causa: `--select=F82` casa por prefixo e captura `F824` (`nonlocal` de
  nome nunca reatribuído em `core/scanner.py`). Corrigido no código, não afrouxando o filtro.
- **Docker congelava o `sources.json`.** O entrypoint copiava o catálogo para o volume só na
  primeira subida; a partir daí toda fonte nova commitada era ignorada pelo contêiner, em
  silêncio. `sources.json` deixou de ser arquivo de `DATA_DIR` e passou a ser catálogo
  versionado lido de `/app/sources.json`.
- **Truncagem silenciosa por `MAX_ENTRIES_PER_FEED`.** Com varredura de 24 h e teto de 10, um
  feed que publica 14 itens/dia perdia 4 por dia sem uma linha de log. Agora avisa quantas
  entradas foram descartadas sem análise, com a instrução do que ajustar.
- `DISCORD_TOKEN` ausente falha no arranque com instrução, em vez de erro cru da biblioteca.
- Removidas `load_http_state()`/`save_http_state()` de `utils/cache.py`: mortas, e
  `save_http_state()` gravaria o cache HTTP por cima do `state.json` inteiro, apagando
  `dedup` e `html_hashes` — repostagem em massa. Removidas em vez de documentadas.
- Removido `tests/manual_http_probe.py`, que ainda importava `httpx` (dependência retirada
  em `f977e94`).

### Fontes — catálogo v3.1
- Nova ferramenta: **`scripts/probe_sources.py`**, que sonda pelo caminho real do bot
  (mesmo fetch, mesmo `feedparser`, mesmo resolvedor de handle) e **se calibra** com controle
  positivo e negativo antes de emitir veredito. Três estados de saída: `0` passou, `1`
  reprovou, `2` **NÃO VERIFICOU** — que não é aprovação.
- Reauditoria do v3.0: **96/96 saudáveis**; `youtube_feed_map` conferido contra a resolução
  ao vivo, 41/41 pares corretos.
- **+25 fontes** (13 RSS, 12 YouTube), todas sondadas e com volume medido. Catálogo agora
  em **121/121 saudáveis**. Volume pós-filtro: 92,7 → **117,6 itens/dia** (+27%), medido e
  não estimado.
- Admissão passou a ter **orçamento medido**: entra fonte com até ~6 itens/24 h sobreviventes
  ao `LIXO_FILTER`. As de maior volume ficam documentadas **com o número**, e promovê-las é
  mover uma linha.
- Registradas no `_schema` as armadilhas medidas: `@nintendo` → canal 'koi' (terceiro),
  `@PlayStationLatam` → 'Conejo en Luna', `@SNKGLOBAL` → canal em sânscrito que **passa** no
  critério de saúde, `@PlayStationEurope` → duplicata do `@PlayStation`. Mais 3 feeds com
  HTTP 200 e conteúdo congelado há 1–7 anos, e o UOL Jogos com 15 entradas e **nenhuma data**
  (o `REQUIRE_ENTRY_DATE=1` descartaria todas — fonte que parece viva e nunca posta).

### Testes
- **80 → 116 testes**, todos verdes. Cada correção nasceu com guarda, e **cada guarda foi
  calibrada reintroduzindo o defeito** — sem exceção.
- Guardas novas: contenção da falha do dashboard, ETag x falha de entrega (com controle
  positivo), sanitização de log com argumentos (com controle negativo para não voltar a
  mascarar `channel_id`), DNS fora da thread do loop, uso da variante assíncrona no código de
  produção, e coerência estrutural do catálogo (handle sem par, `channel_id` duplicado,
  entrada órfã, URL repetida).

---

## [2.2.0] - 2026-07-12 — Auditoria profunda (segurança, bugs, desempenho, testes)

### Segurança
- `.dockerignore` passa a excluir `.env`/`.env.*` (o token do Discord era assado na imagem via `COPY . .`)
- `allowed_mentions.none()`: conteúdo de feed externo não dispara mais `@everyone`/`@here`
- `/now` e o botão "Verificar Agora" agora exigem Administrador (antes qualquer membro forçava varredura)
- Web: comparação de token constant-time (`hmac.compare_digest`); rota `/health` sem auth
- `git_info` sem `shell=True`; remove IP interno vazado no embed de versão
- Container: `no-new-privileges`, `cap_drop: ALL` (+ caps mínimas), dashboard publicado só em `127.0.0.1`

### Correção
- `except discord.InvalidArgument` (classe removida na discord.py 2.x) → `(ValueError, TypeError)`; antes abortava a varredura e causava repost
- Auto-limpeza de 7 dias não zera mais o dedup inteiro (causava repost em massa); limita a 500/feed e poda caches órfãos
- `state.json`: reload+merge antes do save final evita lost-update de chaves escritas por comandos durante o scan
- Timestamp de embed sem data usa UTC (antes hora local rotulada como UTC); caps de tamanho pós-tradução
- `storage`: `fsync` antes do `os.replace` (evita `state.json` truncado em queda de energia)

### Desempenho
- HTML Monitor: BeautifulSoup em executor (não bloqueia o event loop) + downloads limitados por semáforo
- Tradução: reuso de instância `GoogleTranslator` + cache LRU (evita round-trips repetidos ao Google)
- Filtro de ruído: uma alternância regex pré-compilada (era ~50 `re.search` por entrada)

### Testes / Deps
- Testa o filtro real (`should_skip_by_content`) e a atomicidade do `storage`; `clean_html` passa a testar a função real
- Suíte deixa de derrubar o interpretador (skip dos testes web no CPython 3.14)
- Dependências com piso acima de CVEs (aiohttp ≥3.10.11, jinja2 ≥3.1.6) e teto de major
- `HEALTHCHECK` real via `/health` (antes só checava existência de `config.json`)

### Arquitetura / Manutenção
- **Stack HTTP consolidado**: `html_monitor` e o script de fontes migrados de `httpx` para `aiohttp` (dependência `httpx` removida)
- **`run_scan_once` decomposto**: extraídos `build_news_message()` (monta content/embed/view, testável) e `_run_html_monitor()` (dispatch de alertas); ~590 → ~464 linhas, com testes novos para ambos
- **Ambiente de dev**: alvo Python 3.12 (o 3.14 local tinha `_ctypes` quebrado); suíte roda limpa (**59 passed**)
- Notícias são traduzidas para o idioma do servidor (PT/EN via `/setlang`); respostas de comando permanecem em pt-BR (README ajustado). Filtros por servidor foram removidos (só filtro de ruído global)

---

## [2.1.4] - 2026-05-02

### Alterado

- **`deploy/`** — `Dockerfile` e `entrypoint.sh` concentrados aqui; `docker-compose.yml` na raiz usa `dockerfile: deploy/Dockerfile`
- **`assets/`** — Ícone e marca (`assets/icon.png` referenciado no README; ver `assets/README.md`)
- **`docs/README.md`** — Índice da documentação; removido `docs/readme.md` duplicado do guia PT (conteúdo principal permanece no README da raiz)

---

## [2.1.3] - 2026-05-02

### Alterado

- **Layout do repositório** — `.md` de suporte movidos para `docs/` (mantém-se apenas `README.md` na raiz). Guias: `docs/DEPLOY.md`, `docs/COMMANDS_REFERENCE.md`, `docs/COMANDOS.md`, `docs/CHANGELOG.md`
- **`scripts/`** — Utilitários `add_sources_script.py`, `add_yt_sources.py`, `check_overlap.py` (caminhos relativos à raiz do projeto)

---

## [2.1.2] - 2026-05-02

### Alterado

- **Intervalo de varredura: 24h** — Padrão `LOOP_MINUTES` = 1440 (antes 720 / 12h)
- **Filtro de conteúdo** — Termo `gundam` em `LIXO_FILTER` para descartar títulos/resumos relacionados
- **`scripts/add_yt_sources.py`** — Exemplo genérico sem referências a canais legados

---

## [2.1.1] - 2026-02-19

### ✨ Adicionado

- **Intervalo de varredura: 12h** — Padrão alterado de 6h (360 min) para 12h (720 min) *(supersedido em 2.1.2 por 24h)*
- **COMANDOS.md** — Lista rápida de comandos para referência
- **Exponential backoff** — Retry com backoff (1s, 2s, 4s) em falhas de RSS e HTML Monitor
- **Source Health Monitor** — Log detalhado quando fonte falha 3+ vezes
- **User-Agents rotativos** — Lista rotativa no HTML Monitor para evitar bloqueios (Rockstar, Activision)
- **Escrita atômica** — `history.json` e `state.json` gravados via temp + rename para evitar corrupção
- **LIXO_FILTER ampliado** — Bloqueio de campeonatos (championship, campeonato, vct, valorant, euic, vgc)

### 📝 Melhorado

- **Logs específicos** — Prefixos [Scheduler], [Scanner], [HTML Monitor] para facilitar busca
- **Exceções** — Tratamento específico (Forbidden, HTTPException) no envio de alertas HTML
- **Documentação** — README, docs/, COMMANDS_REFERENCE e nova COMANDOS.md atualizados

---

## [2.1.0] - 2026-02-13

### ✨ Adicionado

- **Novo comando `/set_canal`** - Comando dedicado para configurar o canal onde o bot enviará notícias
- **Sistema de segurança aprimorado** (`utils/security.py`)
  - Validação de URLs (anti-SSRF)
  - Bloqueio de IPs privados e domínios locais
  - Sanitização de logs automática
- **Rate limiting** no servidor web
- **Autenticação opcional** no servidor web via token
- **Headers de segurança HTTP** (CSP, X-Frame-Options, etc.)
- **Sistema de logging melhorado**
  - Logs coloridos no console
  - Traceback colorido para exceções
  - Sanitização automática de informações sensíveis
  - Tratamento específico de exceções com contexto

### 🔒 Segurança

- ✅ Validação de URLs antes de fazer requisições HTTP
- ✅ Proteção anti-SSRF (Server-Side Request Forgery)
- ✅ Rate limiting em comandos críticos
- ✅ Sanitização de logs (tokens, senhas mascarados)
- ✅ Headers de segurança HTTP configurados
- ✅ Validação de certificados SSL

### 🐛 Corrigido

- **Erros silenciosos corrigidos** - Todos os `except: pass` agora logam adequadamente
- **Tratamento de exceções melhorado** - Exceções específicas com contexto detalhado
- **Teste de SSL corrigido** - Agora verifica `core/scanner.py` ao invés de `main.py`

### 📝 Melhorado

- **Documentação completa** - READMEs atualizados em 4 idiomas (PT, EN, ES, IT, JP)
- **Logs mais informativos** - Tipo de exceção, contexto e traceback completo
- **Mensagens de erro melhoradas** - Mais claras e específicas
- **Validação de permissões** - Verificação automática ao configurar canal

### 📚 Documentação

- Adicionado `SECURITY_GRC_ANALYSIS.md` - Análise completa de segurança e GRC
- Adicionado `LOGGING_IMPROVEMENTS.md` - Documentação das melhorias de logging
- READMEs atualizados com:
  - Diagramas de arquitetura melhorados
  - Shields/badges atualizados
  - Instruções detalhadas de segurança
  - Exemplos de uso do novo comando `/set_canal`

---

## [2.0.0] - Versão Anterior

### Funcionalidades Principais

- Scanner periódico de feeds RSS/Atom/YouTube
- Dashboard interativo persistente
- Sistema de filtros por categoria
- Multi-guild e multi-idioma
- Web dashboard
- Auto-cleanup de cache
- Cold start para novas fontes

---

**Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/)**
