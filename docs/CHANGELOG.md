# 📝 Changelog - GameBot

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

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
