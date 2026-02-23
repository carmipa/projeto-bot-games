# 📝 Changelog - GameBot

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

---

## [2.1.1] - 2026-02-19

### ✨ Adicionado

- **Intervalo de varredura: 12h** — Padrão alterado de 6h (360 min) para 12h (720 min)
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
