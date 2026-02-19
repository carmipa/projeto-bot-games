# 🎮 Game News & Trailers Bot

Bot de Discord para **notícias e trailers de jogos**. Monitora lançamentos, DLCs, trailers no YouTube e novidades de jogos AAA, com filtros por plataforma e qualidade.

---

## ✨ O que o bot faz

| Recurso | Descrição |
|--------|-----------|
| 📰 **Notícias de jogos** | Lançamentos, DLCs, atualizações e anúncios |
| 🎬 **Trailers** | Novos trailers (YouTube) com player nativo no Discord |
| 🎯 **Filtros** | Por categoria (Games, Trailers, etc.) e por servidor |
| 📡 **Scanner periódico** | Verificação automática em intervalos configuráveis |
| 🖥️ **Dashboard web** | Painel de status em tempo real (opcional) |
| 🌐 **Multi-idioma** | Português e Inglês |
| 🔒 **Segurança** | Validação de URLs, rate limiting, logs sanitizados |

---

## 🚀 Início rápido

### Pré-requisitos

- **Python 3.10+**
- **Token do bot** no [Discord Developer Portal](https://discord.com/developers/applications)

### Instalação

```bash
# Clone ou baixe o projeto
cd projeto-bot-games

# Ambiente virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS

# Dependências
pip install -r requirements.txt

# Configuração
cp .env.example .env
# Edite o .env e adicione seu DISCORD_TOKEN
```

### Executar

```bash
python main.py
```

---

## ⚙️ Configuração

### Variáveis de ambiente (`.env`)

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `DISCORD_TOKEN` | ✅ | Token do bot do Discord |
| `COMMAND_PREFIX` | ❌ | Prefixo de comandos (padrão: `!`) |
| `LOOP_MINUTES` | ❌ | Intervalo do scanner em minutos (padrão: 45) |
| `LOG_LEVEL` | ❌ | Nível de log: DEBUG, INFO, WARNING, ERROR |
| `WEB_HOST` / `WEB_PORT` | ❌ | Host e porta do dashboard web |
| `WEB_AUTH_TOKEN` | ❌ | Token de autenticação do dashboard (recomendado em produção) |

### Primeiro uso no Discord

1. Convide o bot para o seu servidor (com permissão de **Enviar Mensagens** e **Incorporar Links**).
2. Use **`/set_canal`** no canal onde quer receber as notícias (ou **`/dashboard`** para abrir o painel).
3. Configure os filtros no dashboard (categorias que deseja receber).
4. O bot começa a publicar automaticamente conforme o intervalo configurado.

---

## 🧰 Comandos

### Administração (requer Administrador)

| Comando | Descrição |
|---------|-----------|
| `/set_canal` | Define o canal onde o bot envia notícias e trailers |
| `/dashboard` | Abre o painel de filtros e configura o canal atual |
| `/forcecheck` | Força uma verificação imediata de fontes |
| `/clean_state` | Limpa cache/histórico (com backup e confirmação) |

### Informação

| Comando | Descrição |
|---------|-----------|
| `/status` | Uptime, número de varreduras e notícias enviadas |
| `/feeds` | Lista as fontes monitoradas |
| `/about` | Sobre o bot e versão |
| `/ping` | Latência do bot |
| `/help` | Lista de comandos |
| `/setlang` | Define o idioma do bot (PT-BR / EN) |

---

## 📁 Estrutura do projeto

```
projeto-bot-games/
├── main.py              # Entrada do bot
├── settings.py          # Configuração (.env)
├── requirements.txt
├── .env.example
├── sources.json         # Fontes RSS/feeds (ou config de API)
├── config.json          # Gerado: canal e filtros por servidor
├── state.json           # Gerado: cache e histórico
├── history.json         # Gerado: links já enviados
├── bot/
│   ├── cogs/            # Comandos (admin, dashboard, status, info)
│   └── views/           # Painel de filtros (botões)
├── core/
│   ├── scanner.py       # Scanner de feeds/API
│   ├── filters.py       # Filtros por categoria
│   └── html_monitor.py  # Monitor de sites (opcional)
├── utils/               # Logger, storage, security, translator
├── web/                 # Servidor do dashboard
├── translations/        # PT-BR e EN
├── docs/                # Documentação adicional
└── logs/                # Logs do bot
```

---

## 🐳 Docker

```bash
# Build e execução
docker-compose up -d

# Logs
docker-compose logs -f
```

Configure o `.env` antes. Os arquivos `config.json`, `state.json` e `history.json` podem ser persistidos com volumes (ver `docker-compose.yml`).

---

## 📚 Documentação completa

Documentação detalhada em **português** e **inglês** na pasta **`docs/`**:

| Documento | Descrição |
|-----------|-----------|
| [docs/readme.md](docs/readme.md) | Documentação completa em **PT-BR** |
| [docs/README_EN.md](docs/README_EN.md) | Full documentation in **English** |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Guia de deploy / Deploy guide |
| [docs/COMMANDS_REFERENCE.md](docs/COMMANDS_REFERENCE.md) | Referência de comandos / Commands reference |
| [docs/SECURITY_GRC_ANALYSIS.md](docs/SECURITY_GRC_ANALYSIS.md) | Análise de segurança / Security analysis |

---

## 🔧 Tecnologias

- **Python 3.10+**
- **discord.py** (comandos slash e embeds)
- **aiohttp** / **httpx** (requisições assíncronas)
- **feedparser** (RSS/Atom)
- **Docker** (opcional)

---

## 📜 Licença

MIT. Uso livre para projetos pessoais e comerciais.

---

**Game News & Trailers Bot** — Notícias e trailers de jogos direto no seu Discord.
