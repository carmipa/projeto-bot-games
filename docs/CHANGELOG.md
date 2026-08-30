# 📝 Changelog - GameBot

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

---

## [2.4.0] - 2026-08-30 — Telemetria de ausência, e uma porta para o tradutor

Resposta à pergunta "vale a pena incluir desacoplamento e telemetria?": telemetria sim,
uma porta sim, fatias verticais não — a regra de arquitetura do vault (§2 *duplicação
consciente > acoplamento*, §6 *não elevar fatia isolada*) desaconselha reescrever um bot de
uma fatia só.

### Telemetria de ausência
- **O painel media só sucesso.** `scans_completed`, `news_posted`, `cache_hits` — e um
  `feeds_failed` **definido e nunca incrementado**, um campo que sempre dizia `0`,
  indistinguível de "nada falhou". Sete dos doze defeitos desta semana teriam aparecido num
  painel que medisse ausência.
- Cada varredura passa a emitir **VEREDITO com MOTIVO** (`OK` / `ATENCAO` / `ANOMALIA`),
  persistido em `state.json` e exposto no `/status` e no `/api/stats`. O zero legítimo é
  dito com todas as letras — *"não havia novidade: as 92 fontes saudáveis responderam 304"* —
  porque alarmar em dia calmo treina o operador a ignorar o alarme.
- **Invariante de conservação:** todo item que passa o dedup sai por uma de três portas —
  publicado, filtrado ou com entrega falhada. Qualquer diferença é ANOMALIA. É a telemetria
  a auditar-se a si própria: um `continue` novo que esqueça de contar passa a reprovar.
- **Agendador morto é detectado** comparando o relógio com o último registo — o defeito do
  `on_ready` abortado, que deixava o bot online sem nunca varrer.
- **Saídas antecipadas também registam.** Sem guild configurada ou catálogo vazio é a
  ausência mais grave (o bot nem tentou) e antes terminava em silêncio, deixando o `/status`
  a mostrar um `OK` de dias atrás.
- **Impressão digital do catálogo no arranque** (contagem + sha + caminho): faz "adicionei
  fontes e não mudou nada" virar uma linha comparável no log.

### Porta do tradutor
- `utils/portas.py`: `TradutorPort`, `ContratoDaPortaViolado` e `DegradacaoAceitavel`. É o
  único desacoplamento que a regra manda ter aqui (§5.5, *toda saída passa por porta
  declarada*) e o único com dano medido atrás dele — nenhum `try/except` teria apanhado o
  incidente de ontem, porque o adaptador estava a **mentir dentro do contrato**, não a
  falhar fora dele. Vive em `utils/` e não em `core/` porque o kernel não pode importar da
  fatia (invariante 1 da regra).

### Achados durante a implementação, todos apanhados pelos próprios testes
- O detector reportava **catálogo vazio como `OK`** — tinha o buraco exatamente na falha que
  existe para apanhar.
- Um ramo de decisão era **inalcançável** (a conservação já o cobria). Removido: ramo morto
  numa função de decisão sugere cobertura que não existe.
- A conservação tinha **duas portas em vez de três**, e mascarava "entrega falhou" com "item
  sumido" — veredito certo, diagnóstico errado.
- O portão de lint apanhou um `global` para nome só lido (F824), a mesma classe de ontem.

### Testes
- **135 → 167.** Cada regra de veredito tem par: o cenário que TEM de alarmar e o gêmeo
  saudável que TEM de ficar calado. Calibração principal: remover a contagem de **um**
  `continue` faz a invariante de conservação reprovar.

---

## [2.3.1] - 2026-08-30 — Tradutor devolvia página de erro e ela ia para o canal

Achado **em produção**, na primeira execução real desde 2026-03-27. O canal recebeu
notícias cujo título e resumo eram, os dois:
`Error 500 (Server Error)!!1500.That's an error.There was an error. Please try again
later.That's all we know.`

### Crítico
- **`deep_translator` não levanta exceção quando o Google responde com página de erro** —
  devolve o *texto* da página como se fosse a tradução. O único guarda era
  `if trad is None`, que uma string nunca aciona. A cadeia de dano tinha três elos:
  a página era publicada como título e resumo; era **gravada no cache LRU**, repetindo-se
  para todo texto igual; e o envio "teve sucesso", então o link entrava no dedup — a
  notícia verdadeira **nunca mais** sairia, nem depois de o tradutor voltar ao normal.
  O terceiro elo é o caro, e é a mesma classe do ETag gravado antes da entrega:
  *"entreguei lixo" contava como "entreguei"*.
- A resposta do tradutor passa a ser validada. Inválida ⇒ publica o **texto original**
  (notícia em inglês continua a ser notícia; página de erro não é), **não** entra no cache,
  e sai em WARNING — degradação visível tem de aparecer no log.
- **Disjuntor:** após 5 falhas seguidas, 10 minutos publicando sem traduzir, sem sequer
  chamar o serviço. Insistir durante um bloqueio por excesso de pedidos só o prolonga — e
  a rajada de cold start das 25 fontes novas é o gatilho provável do incidente.

### Recuperação
- `scripts/repor_noticias_perdidas.py`: esquece o dedup e o histórico de uma fonte para que
  as notícias publicadas como lixo voltem ao canal. Faz backup antes e aborta se ele
  falhar; `--simular` é o padrão. Não toca no `http_cache`, de propósito.

### Testes
- **116 → 135**. A guarda usa o texto **exato** que chegou ao canal — é evidência, não
  vetor inventado — e foi calibrada reintroduzindo o defeito de produção: 5 guardas
  acusam, incluindo a central. Controle negativo incluído: notícia que *fala* de erro de
  servidor ("Patch corrige erro 500 no matchmaking") tem de passar, senão o detector
  recusaria tudo e o bot nunca traduziria nada.

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
- **CI ganhou análise estática dedicada** (`bandit`) e **varredura de dependências
  vulneráveis** (`pip-audit`) — os dois eram GAP declarado. Ambos **reprovam** a build.
  O `bandit` achou 11 na primeira execução; os 3 reais (`except Exception: pass` mudo em
  `extract_entry_media_urls`, que fazia a entrada perder a imagem sem deixar rasto) foram
  **corrigidos**, não suprimidos. Os 2 de severidade média eram falso positivo: ele marca a
  *string* `"0.0.0.0"`, e os dois usos são o oposto de abrir o bind — um está na lista de
  domínios **bloqueados** e o outro numa comparação que **avisa**. As 6 exceções são
  `# nosec BXXX` no ponto exato, com o motivo escrito na linha acima.
- Sobre o `pip-audit`:
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
