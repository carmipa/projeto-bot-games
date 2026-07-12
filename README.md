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
| Validação de URLs | Bloqueia IPs privados e domínios locais (anti-SSRF) |
| Rate limiting | Limite de requisições por IP no dashboard web |
| Autenticação web | Token opcional para o dashboard |
| Sanitização de logs | Tokens e dados sensíveis mascarados |
| SSL | Conexões verificadas com certifi |

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
├── scripts/             # Utilitários opcionais (fontes / checagens)
└── tests/               # Testes pytest
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
