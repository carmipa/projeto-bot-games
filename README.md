# 🎮 Game News & Trailers Bot — Documentação (PT-BR)

Bot de Discord para **notícias e trailers de jogos**. Monitora lançamentos, DLCs, trailers no YouTube e novidades de jogos, com filtros por categoria e suporte a múltiplos servidores.

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
| 🎯 **Filtros por categoria** | Games, Trailers, etc. + opção "TUDO" |
| 🔄 **Deduplicação** | Não repete notícias (histórico em `history.json`) |
| 🌐 **Multi-Guild** | Configuração independente por servidor Discord |
| 🖥️ **Web Dashboard** | Painel em tempo real (opcional, porta 8080) |
| 🌍 **Multi-idioma** | Português e Inglês (`/setlang`) |
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

Documentação detalhada: [docs/SECURITY_GRC_ANALYSIS.md](docs/SECURITY_GRC_ANALYSIS.md)

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
| `LOOP_MINUTES` | ❌ | Intervalo do scanner em minutos (padrão: 45) |
| `LOG_LEVEL` | ❌ | DEBUG, INFO, WARNING, ERROR |
| `WEB_AUTH_TOKEN` | ❌ | Token do dashboard web (recomendado em produção) |
| `WEB_HOST` | ❌ | Ex.: 127.0.0.1 ou 0.0.0.0 |
| `WEB_PORT` | ❌ | Porta do dashboard (padrão: 8080) |

### Primeiro uso no Discord

1. Convide o bot com permissões **Enviar Mensagens** e **Incorporar Links**.
2. Use **`/set_canal`** no canal desejado ou **`/dashboard`** para abrir o painel.
3. Configure os filtros no dashboard.
4. O bot passa a publicar conforme o intervalo definido em `LOOP_MINUTES`.

---

## 🧰 Comandos

### Administração (requer Administrador)

| Comando | Descrição |
|---------|-----------|
| `/set_canal` | Define o canal onde o bot envia notícias e trailers |
| `/dashboard` | Abre o painel de filtros e define o canal atual |
| `/forcecheck` | Força uma varredura imediata das fontes |
| `/clean_state` | Limpa cache/histórico (com backup e confirmação) |

### Informação

| Comando | Descrição |
|---------|-----------|
| `/status` | Uptime, varreduras e notícias enviadas |
| `/feeds` | Lista as fontes monitoradas |
| `/about` | Sobre o bot e versão |
| `/ping` | Latência do bot |
| `/help` | Lista de comandos |
| `/setlang` | Define o idioma (PT-BR ou EN) |

### Exemplos

```bash
/set_canal                    # Usa o canal atual
/set_canal canal:#noticias    # Canal específico
/dashboard                    # Painel de filtros
/setlang idioma:pt_BR         # Português
/setlang idioma:en_US         # Inglês
/clean_state tipo:dedup confirmar:não   # Ver estatísticas
/clean_state tipo:dedup confirmar:sim   # Executar limpeza
```

**Tipos do `/clean_state`:** `dedup` (histórico), `http_cache`, `html_hashes`, `tudo`. Sempre é feito backup antes da limpeza.

Referência completa: [docs/COMMANDS_REFERENCE.md](docs/COMMANDS_REFERENCE.md)

---

## 🎛️ Dashboard

O painel (comando `/dashboard`) permite:

| Botão | Função |
|-------|--------|
| 🌟 **TUDO** | Ativa/desativa todas as categorias |
| 🤖 **Games** | Notícias de jogos |
| 🎬 **Trailers / Filmes** | Trailers, teasers, vídeos |
| 🎵 **Música** | OST, trilhas |
| 👕 **Fashion/Merch** | Merchandise |
| 📌 **Ver filtros** | Mostra filtros ativos |
| 🔄 **Reset** | Limpa todos os filtros |

Indicadores: 🟢 Verde = ativo, ⚪ Cinza = inativo. Idiomas (PT/EN) também podem ser escolhidos no painel.

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
├── config.json          # Gerado: canal e filtros por servidor
├── state.json           # Gerado: cache e histórico
├── history.json         # Gerado: links já enviados
├── bot/cogs/            # Comandos (admin, dashboard, status, info)
├── bot/views/           # Painel de filtros
├── core/                # Scanner, filtros, html_monitor
├── utils/               # Logger, storage, security, translator
├── web/                 # Servidor do dashboard
├── translations/        # PT-BR e EN
├── docs/                # Documentação
└── logs/                # Logs do bot
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

**Game News & Trailers Bot** — Notícias e trailers de jogos no seu Discord.
