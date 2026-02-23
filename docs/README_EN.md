# 🎮 GameBot — Documentation (EN)

Discord bot for **game news and trailers**. Monitors releases, DLCs, YouTube trailers, and game updates, with category filters and multi-server support.

---

## 📋 Table of Contents

- [Features](#-features)
- [Security](#-security)
- [Installation](#-installation)
- [Configuration](#️-configuration)
- [Commands](#-commands)
- [Dashboard](#-dashboard)
- [Sources (sources.json)](#-sources-sourcesjson)
- [Deploy](#️-deploy)
- [Project Structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## ✨ Features

| Feature | Description |
|--------|-------------|
| 📡 **Periodic scanner** | Scans RSS/Atom/YouTube feeds at configurable intervals |
| 🎬 **Trailers** | YouTube videos with native Discord player |
| 🎛️ **Persistent dashboard** | Button panel that works after bot restart |
| 🎯 **Content filters** | LIXO_FILTER: blocks eSports, reviews, guides; max 7 days |
| 🔄 **Deduplication** | Never repeats news (history in `history.json`) |
| 🌐 **Multi-guild** | Independent configuration per Discord server |
| 🖥️ **Web dashboard** | Real-time panel (optional, port 8080) |
| 🌍 **Multi-language** | Portuguese and English (`/setlang`) |
| 🔒 **URL validation** | Anti-SSRF protection |
| 🛡️ **Rate limiting** | Protection on web server and commands |
| 🧹 **Auto-cleanup** | Periodic cache cleanup (configurable) |

---

## 🔒 Security

| Resource | Description |
|----------|-------------|
| URL validation | Blocks private IPs and local domains (anti-SSRF) |
| Rate limiting | Request limit per IP on web dashboard |
| Web auth | Optional token for dashboard access |
| Log sanitization | Tokens and sensitive data masked in logs |
| SSL | Verified connections with certifi |

Full details: [SECURITY_GRC_ANALYSIS.md](SECURITY_GRC_ANALYSIS.md)

---

## 🚀 Installation

### Prerequisites

- Python 3.10 or higher
- Bot token from [Discord Developer Portal](https://discord.com/developers/applications)

### Steps

```bash
# 1. Enter project folder
cd projeto-bot-games

# 2. Virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS

# 3. Dependencies
pip install -r requirements.txt

# 4. Configuration
cp .env.example .env
# Edit .env and add DISCORD_TOKEN
```

### Docker

```bash
cp .env.example .env
# Edit .env with your DISCORD_TOKEN
docker-compose up -d
docker-compose logs -f
```

Full guide: [DEPLOY.md](DEPLOY.md)

---

## ⚙️ Configuration

### Environment variables (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | ✅ | Discord bot token |
| `COMMAND_PREFIX` | ❌ | Command prefix (default: `!`) |
| `LOOP_MINUTES` | ❌ | Scanner interval in minutes (default: 720 = 12h) |
| `LOG_LEVEL` | ❌ | DEBUG, INFO, WARNING, ERROR |
| `WEB_AUTH_TOKEN` | ❌ | Web dashboard token (recommended in production) |
| `WEB_HOST` | ❌ | e.g. 127.0.0.1 or 0.0.0.0 |
| `WEB_PORT` | ❌ | Dashboard port (default: 8080) |

### First use on Discord

1. Invite the bot with **Send Messages** and **Embed Links** permissions.
2. Use **`/set_canal`** in the desired channel or **`/dashboard`** to open the panel.
3. Configure filters in the dashboard.
4. The bot will post according to the interval set in `LOOP_MINUTES`.

---

## 🧰 Commands

### Administration (Administrator required)

| Command | Description |
|---------|-------------|
| `/set_canal` | Sets the channel where the bot sends news and trailers |
| `/dashboard` | Opens the filter panel and sets the current channel |
| `/forcecheck` | Forces an immediate scan of sources |
| `/clean_state` | Cleans cache/history (with backup and confirmation) |

### Information

| Command | Description |
|---------|-------------|
| `/status` | Uptime, scans, news posted, next scan time |
| `/now` | Forces immediate verification |
| `/feeds` | Lists monitored sources |
| `/about` | About the bot and version |
| `/ping` | Bot latency |
| `/help` | Command list |
| `/setlang` | Sets language (PT-BR or EN) |

### Examples

```bash
/set_canal                    # Uses current channel
/set_canal channel:#news       # Specific channel
/dashboard                    # Filter panel
/setlang language:pt_BR       # Portuguese
/setlang language:en_US       # English
/clean_state type:dedup confirm:no    # View statistics
/clean_state type:dedup confirm:yes   # Run cleanup
```

**`/clean_state` types:** `dedup` (history), `http_cache`, `html_hashes`, `tudo`. A backup is always created before cleaning.

Full reference: [COMMANDS_REFERENCE.md](../COMMANDS_REFERENCE.md) | Quick list: [COMANDOS.md](../COMANDOS.md)

---

## 🎛️ Dashboard

The panel (command `/dashboard`) allows:

| Button | Function |
|--------|----------|
| 🇺🇸 **English** | English language |
| 🇧🇷 **Português** | Portuguese (Brazil) language |

The panel also sets the current channel automatically. All news approved by the filter are sent to the configured channel.

---

## 📁 Sources (sources.json)

The bot accepts RSS/Atom and YouTube feeds. Example with categories:

```json
{
  "rss_feeds": [
    "https://example.com/games-feed.xml"
  ],
  "youtube_feeds": [
    "https://www.youtube.com/feeds/videos.xml?channel_id=YOUR_CHANNEL_ID"
  ],
  "official_sites_reference_(not_rss)": []
}
```

Simple format (list of URLs):

```json
[
  "https://example.com/feed.xml",
  "https://www.youtube.com/feeds/videos.xml?channel_id=ID"
]
```

Replace with the news feeds and game channels you want to monitor.

---

## 🖥️ Deploy

- **Local:** `python main.py`
- **Docker:** `docker-compose up -d`
- **systemd:** See [DEPLOY.md](DEPLOY.md) for Linux service setup.

Recommended volumes for persistence: `config.json`, `state.json`, `history.json`, `sources.json`, `logs/`.

---

## 📁 Project structure

```
projeto-bot-games/
├── main.py              # Bot entry point
├── settings.py          # Config (.env)
├── requirements.txt
├── .env.example
├── sources.json         # RSS/YouTube sources
├── config.json         # Generated: channel and filters per server
├── state.json          # Generated: cache and state
├── history.json        # Generated: sent links
├── bot/cogs/           # Commands (admin, dashboard, status, info)
├── bot/views/          # Filter panel
├── core/               # Scanner, filters, html_monitor
├── utils/              # Logger, storage, security, translator
├── web/                # Dashboard server
├── translations/       # PT-BR and EN
├── docs/               # Documentation
└── logs/               # Bot logs
```

---

## 🧩 Troubleshooting

**Command not found:** Wait a few seconds after the bot connects; slash commands are synced on `on_ready`.

**Bot doesn't send messages:** Check channel permissions (Send Messages, Embed Links). Run `/set_canal` again.

**URL blocked:** The bot blocks private IPs and local domains (anti-SSRF). Use only public URLs in `sources.json`.

**PyNaCl / voice:** You may see a PyNaCl warning; the bot does not use voice, you can ignore it.

---

## 📜 License

MIT. Free for personal and commercial use.

---

**GameBot** — Game news and trailers in your Discord.
