<p align="center">
  <img src="assets/icon.png" alt="GameBot" width="200"/>
</p>

# 🎮 GameBot — Documentação (PT-BR)

Bot de Discord para **notícias e trailers de jogos**. Monitora lançamentos, DLCs, trailers no YouTube e novidades de jogos, com filtro de ruído global e suporte a múltiplos servidores.

---

## 📋 Índice

- [Funcionalidades](#-funcionalidades)
- [Segurança](#-segurança)
- [Instalação](#-instalação)
- [Configuração](#️-configuração)
- [Comandos](#-comandos)
- [Dashboard](#-dashboard)
- [Fontes (sources.json)](#-fontes-sourcesjson)
- [Deploy](#-deploy)
- [Estrutura do projeto](#-estrutura-do-projeto)
- [Troubleshooting](#-troubleshooting)
- [Licença](#-licença)

---

## ✨ Funcionalidades

| Recurso | Descrição |
|--------|-----------|
| 📡 **Scanner periódico** | Varredura de feeds RSS/Atom/YouTube em intervalos configuráveis |
| 🎬 **Trailers** | Vídeos do YouTube com player nativo no Discord |
| 🎛️ **Dashboard persistente** | Painel com botões que funciona após restart do bot |
| 🎯 **Filtros de conteúdo** | LIXO_FILTER: bloqueia eSports, reviews, guias; máximo 7 dias |
| 🔄 **Deduplicação** | Não repete notícias (histórico em `history.json`) |
| 🌐 **Multi-Guild** | Configuração independente por servidor Discord |
| 🖥️ **Web Dashboard** | Painel em tempo real (opcional, porta 8080) |
| 🌍 **Notícias multi-idioma** | Notícias traduzidas para o idioma do servidor — PT/EN via `/setlang`. As respostas dos comandos são em pt-BR. |
| 🔒 **Validação de URLs** | Proteção anti-SSRF |
| 🛡️ **Rate limiting** | Proteção no servidor web e comandos |
| 🧹 **Auto-cleanup** | Limpeza de cache periódica (configurável) |

---

## 🔒 Segurança

| Recurso | Descrição |
|---------|-----------|
| Validação de URLs | Bloqueia IPs privados e domínios locais (anti-SSRF), resolvendo o DNS fora da thread do event loop |
| Rate limiting | Limite de requisições por IP no dashboard web |
| Autenticação web | Token opcional para o dashboard, comparado em tempo constante |
| Sanitização de logs | Tokens, `Authorization:` e URLs de webhook mascarados na mensagem **já formatada** (cobre `log.error("... %s", segredo)`) |
| SSL | Conexões verificadas com certifi |
| Auditoria de dependências | `pip-audit` no CI, que reprova em CVE nova (exceções são nominais e justificadas no workflow) |

> Limite conhecido: a validação anti-SSRF resolve o nome e depois deixa o `aiohttp` resolver
> de novo — há uma janela de DNS rebinding. Aceitável porque `sources.json` é controlado por
> quem opera o bot, não por terceiros. Está declarado em
> `analises/2026-08-29_auditoria-seguranca-engenharia-fontes.md`.

---

## 🚀 Instalação

### Pré-requisitos

- Python 3.10 ou superior
- Token do bot no [Discord Developer Portal](https://discord.com/developers/applications)

### Passo a passo

```bash
# 1. Entre na pasta do projeto
cd projeto-bot-games

# 2. Ambiente virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS

# 3. Dependências
pip install -r requirements.txt

# 4. Configuração
cp .env.example .env
# Edite o .env e adicione DISCORD_TOKEN
```

### Docker

```bash
cp .env.example .env
# Edite o .env com seu DISCORD_TOKEN
docker-compose up -d
docker-compose logs -f
```

Guia completo: [docs/DEPLOY.md](docs/DEPLOY.md)

---

## ⚙️ Configuração

### Variáveis de ambiente (`.env`)

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `DISCORD_TOKEN` | ✅ | Token do bot do Discord |
| `COMMAND_PREFIX` | ❌ | Prefixo de comandos (padrão: `!`) |
| `LOOP_MINUTES` | ❌ | Intervalo do scanner em minutos (padrão: 1440 = 24h) |
| `LOG_LEVEL` | ❌ | DEBUG, INFO, WARNING, ERROR |
| `WEB_AUTH_TOKEN` | ❌ | Token do dashboard web (recomendado em produção) |
| `WEB_HOST` | ❌ | Ex.: 127.0.0.1 ou 0.0.0.0 |
| `WEB_PORT` | ❌ | Porta do dashboard (padrão: 8080) |

### Primeiro uso no Discord

1. Convide o bot com permissões **Enviar Mensagens** e **Incorporar Links**.
2. Use **`/set_canal`** no canal desejado ou **`/dashboard`** para abrir o painel.
3. (Opcional) Escolha o idioma das notícias no dashboard.
4. O bot passa a publicar conforme o intervalo definido em `LOOP_MINUTES`.

---

## 🧰 Comandos

### Administração (requer Administrador)

| Comando | Descrição |
|---------|-----------|
| `/set_canal` | Define o canal onde o bot envia notícias e trailers |
| `/dashboard` | Define o canal atual e abre o painel de idioma |
| `/forcecheck` | Força uma varredura imediata das fontes |
| `/clean_state` | Limpa cache/histórico (com backup e confirmação) |

### Informação

| Comando | Descrição |
|---------|-----------|
| `/status` | Uptime, varreduras, notícias enviadas, próxima varredura |
| `/now` | Força verificação imediata |
| `/feeds` | Lista as fontes monitoradas |
| `/about` | Sobre o bot e versão |
| `/ping` | Latência do bot |
| `/help` | Lista de comandos |
| `/setlang` | Define o idioma (PT-BR ou EN) |

### Exemplos

```bash
/set_canal                    # Usa o canal atual
/set_canal canal:#noticias    # Canal específico
/dashboard                    # Define canal + painel de idioma
/setlang idioma:pt_BR         # Português
/setlang idioma:en_US         # Inglês
/clean_state tipo:dedup confirmar:não   # Ver estatísticas
/clean_state tipo:dedup confirmar:sim   # Executar limpeza
```

**Tipos do `/clean_state`:** `dedup` (histórico), `http_cache`, `html_hashes`, `tudo`. Sempre é feito backup antes da limpeza.

Referência completa: [docs/COMMANDS_REFERENCE.md](docs/COMMANDS_REFERENCE.md) | Lista rápida: [docs/COMANDOS.md](docs/COMANDOS.md) | [Changelog](docs/CHANGELOG.md)

---

## 🎛️ Dashboard

O painel (comando `/dashboard`) permite:

| Botão | Função |
|-------|--------|
| 🇺🇸 **English** | Idioma inglês |
| 🇧🇷 **Português** | Idioma português (Brasil) |

O painel também configura o canal atual automaticamente. Todas as notícias aprovadas pelo filtro são enviadas ao canal configurado.

---

## 📁 Fontes (sources.json)

O bot aceita feeds RSS/Atom e YouTube. Exemplo com categorias:

```json
{
  "rss_feeds": [
    "https://exemplo.com/feed-jogos.xml"
  ],
  "youtube_feeds": [
    "https://www.youtube.com/feeds/videos.xml?channel_id=SEU_CHANNEL_ID"
  ],
  "official_sites_reference_(not_rss)": []
}
```

Formato simples (lista de URLs):

```json
[
  "https://exemplo.com/feed.xml",
  "https://www.youtube.com/feeds/videos.xml?channel_id=ID"
]
```

Substitua pelos feeds de notícias e canais de jogos que desejar monitorar.

### Antes de adicionar uma fonte: sonde

```bash
.venv\Scripts\python.exe scripts\probe_sources.py https://site.com/feed https://www.youtube.com/@Canal
.venv\Scripts\python.exe scripts\probe_sources.py --catalogo    # reaudita tudo
```

A sonda usa o **caminho real do bot** (mesmo fetch, mesmo `feedparser`, mesmo resolvedor de
handle) e calibra-se com um caso-controle positivo e um negativo antes de dar veredito.
Saída em três estados: `0` passou · `1` reprovou · `2` **NÃO VERIFICOU** — que não é aprovação.

Ela reporta `status`, número de entradas, idade do item mais recente, **título do feed** e o
volume pós-filtro (`pos_filtro_24h` / `7d`). Ler o título não é detalhe: um handle do YouTube
ocupado por terceiro responde 200 e devolve vídeos — só o título denuncia que o canal é outro.
Casos reais medidos estão registrados em `sources.json` → `_schema.handles_de_youtube_PERIGOSOS_nao_usar`.

Critério de admissão do catálogo: HTTP 200, ≥ 1 entrada, item mais recente com menos de 180
dias, título coerente com a fonte, e até ~6 itens/24 h sobreviventes ao filtro de ruído.
Fontes acima desse volume ficam documentadas no `_schema` **com o número medido** — promover
uma delas é mover uma linha.

> **Docker:** `sources.json` é catálogo versionado e vem da imagem (`/app/sources.json`), não
> do volume de dados. Para usar um catálogo próprio, monte-o por cima:
> `- ./meu-sources.json:/app/sources.json:ro`.

---

## 🖥️ Deploy

- **Local:** `python main.py`
- **Docker:** `docker-compose up -d`
- **systemd:** Ver [docs/DEPLOY.md](docs/DEPLOY.md) para serviço em Linux.

Volumes recomendados para persistência: `config.json`, `state.json`, `history.json`, `sources.json`, `logs/`.

---

## 📁 Estrutura do projeto

```
projeto-bot-games/
├── main.py              # Entrada do bot
├── settings.py          # Configuração (.env)
├── requirements.txt
├── .env.example
├── sources.json         # Fontes RSS/YouTube
├── config.json          # Gerado: canal e idioma por servidor
├── state.json           # Gerado: cache e histórico
├── history.json         # Gerado: links já enviados
├── bot/cogs/            # Comandos (admin, dashboard, status, info)
├── bot/views/           # Painel de idioma
├── core/                # Scanner, filtros, html_monitor
├── utils/               # Logger, storage, security, translator
├── web/                 # Servidor do dashboard
├── translations/        # PT-BR e EN
├── deploy/              # Dockerfile e entrypoint do container
├── assets/              # Ícone / marca (ex.: icon.png para o README)
├── docs/                # Documentação (deploy, comandos, changelog, EN)
├── analises/            # Relatórios de auditoria com evidência colada
├── scripts/             # probe_sources.py (sonda de fontes) e utilitários
└── tests/               # Testes pytest
```

### Portões locais (os mesmos que o CI roda)

```bash
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m flake8 . --count --select=E9,F63,F7,F82 --statistics
.venv\Scripts\python.exe -m pip_audit --requirement requirements.txt --strict --ignore-vuln PYSEC-2022-252
.venv\Scripts\python.exe scripts\probe_sources.py --catalogo
```

---

## 🧩 Troubleshooting

**Comando não encontrado:** Aguarde alguns segundos após o bot conectar; os comandos slash são sincronizados no `on_ready`.

**Bot não envia mensagens:** Verifique permissões no canal (Enviar Mensagens, Incorporar Links). Use `/set_canal` novamente.

**URL bloqueada:** O bot bloqueia IPs privados e domínios locais (anti-SSRF). Use apenas URLs públicas em `sources.json`.

**PyNaCl / voice:** Aviso sobre PyNaCl pode aparecer; o bot não usa voz, pode ignorar.

---

## 📜 Licença

MIT. Uso livre para projetos pessoais e comerciais.

---

**GameBot** — Notícias e trailers de jogos no seu Discord.
