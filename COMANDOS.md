# 📋 Lista de Comandos — GameBot

**Versão:** 2.1 | **Intervalo padrão:** 12h

---

## 🔧 Administração (requer Administrador)

| Comando | Descrição |
|---------|-----------|
| `/set_canal` | Define o canal onde o bot envia notícias |
| `/dashboard` | Abre o painel (idioma PT/EN e configura canal) |
| `/forcecheck` | Força varredura imediata de todas as fontes |
| `/clean_state` | Limpa cache/histórico (dedup, http_cache, html_hashes, tudo) |

---

## 📊 Informação (todos os usuários)

| Comando | Descrição |
|---------|-----------|
| `/status` | Uptime, varreduras, notícias enviadas, próxima varredura |
| `/now` | Força verificação imediata (atalho) |
| `/feeds` | Lista fontes monitoradas (RSS, YouTube) |
| `/about` | Sobre o bot, desenvolvedor, versão |
| `/ping` | Latência do bot |
| `/help` | Manual de ajuda |
| `/setlang` | Define idioma (en_US ou pt_BR) |

---

## 🔧 Parâmetros do `/clean_state`

| Tipo | O que limpa |
|------|-------------|
| `dedup` | Histórico de links enviados |
| `http_cache` | Cache HTTP (ETags) |
| `html_hashes` | Hashes do monitor de sites |
| `tudo` | Tudo (use com cuidado) |

**Uso:** `/clean_state tipo:dedup confirmar:sim` (sempre cria backup antes)

---

## ⚙️ Variáveis de ambiente (.env)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DISCORD_TOKEN` | — | Token do bot (obrigatório) |
| `LOOP_MINUTES` | 720 | Intervalo de varredura (min) — 720 = 12h |
| `LOG_LEVEL` | INFO | DEBUG, INFO, WARNING, ERROR |

---

📖 **Referência completa:** [COMMANDS_REFERENCE.md](COMMANDS_REFERENCE.md)
