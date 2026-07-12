<p align="center">
  <img src="../assets/icon.png" alt="GameBot" width="200"/>
</p>

<h1 align="center">🐳 Guia de Deploy — GameBot</h1>

<p align="center">
  <b>Deploy do bot GameBot em VPS Linux com Docker</b><br>
  <i>Rápido, seguro e automatizado</i>
</p>

---

## 📋 Pré-requisitos

Antes de começar, você precisa ter:

| Item | Descrição | Verificar |
|------|-----------|-----------|
| 🖥️ **VPS/Servidor** | Ubuntu 20.04+, Debian 11+ ou similar | `lsb_release -a` |
| 🐳 **Docker** | Versão 20.10+ | `docker --version` |
| 🔧 **Docker Compose** | Versão 1.29+ | `docker-compose --version` |
| 🔑 **Token Discord** | Bot token do Discord Developer Portal | [Criar bot](https://discord.com/developers/applications) |
| 📡 **Acesso SSH** | Conexão ao servidor | `ssh user@seu-servidor` |

---

## 🚀 Instalação Rápida (5 minutos)

### Passo 1: Instalar Docker

```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Docker (script oficial)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Adicionar usuário ao grupo docker (evita sudo)
sudo usermod -aG docker $USER

# Instalar Docker Compose
sudo apt install docker-compose-plugin -y   # v2: use 'docker compose' (com espaco), nao 'docker-compose' (v1)

# Logout e login novamente para aplicar permissões
exit
```

**⚠️ Importante:** Faça logout (`exit`) e login novamente no SSH para as permissões funcionarem!

**Verificar instalação:**

```bash
docker --version          # Docker version 24.x.x
docker-compose --version  # docker-compose version 1.29.x
```

---

### Passo 2: Clonar Projeto

```bash
# Criar diretório
sudo mkdir -p /opt/projeto-bot-games
sudo chown $USER:$USER /opt/projeto-bot-games
cd /opt/projeto-bot-games

# Copiar arquivos do projeto para o servidor
```

**Ou upload manual via SCP:**

```bash
# Do seu PC Windows:
scp -r ./* user@seu-servidor:/opt/projeto-bot-games/
```

---

### Passo 3: Configurar Variáveis

**Criar arquivo .env:**

```bash
nano .env
```

**Conteúdo do .env:**

```env
# ⚠️ OBRIGATÓRIO
DISCORD_TOKEN=seu_token_discord_aqui

# ⚙️ OPCIONAL (valores padrão)
COMMAND_PREFIX=!
LOOP_MINUTES=1440
```

**Dica:** Obtenha seu token em <https://discord.com/developers/applications>

**Salvar:** `Ctrl+O` → Enter → `Ctrl+X`

**Proteger o arquivo:**

```bash
chmod 600 .env
```

---

### Passo 4: Iniciar Bot

```bash
# Build da imagem Docker
docker-compose build

# Iniciar em background
docker-compose up -d

# Verificar se está rodando
docker-compose ps
```

**✅ Saída esperada:**

```
    Name              Command        State
-----------------------------------------------
projeto-bot-games   python -u main.py  Up
```

**Ver logs em tempo real:**

```bash
docker-compose logs -f
```

**Mensagem de sucesso nos logs:**

```
✅ Bot conectado como GameBot#1234
📡 Iniciando loop de varredura (intervalo: 24h / 1440 min)
```

---

## 🎮 Comandos Úteis

### Gerenciamento Básico

| Comando | Descrição |
|---------|-----------|
| `docker-compose up -d` | Inicia bot em background |
| `docker-compose down` | Para o bot |
| `docker-compose restart` | Reinicia bot |
| `docker-compose ps` | Verifica status |
| `docker-compose logs -f` | Logs em tempo real |
| `docker-compose logs --tail=100` | Últimas 100 linhas |

### Atualizações

```bash
# Atualizar código
cd /opt/projeto-bot-games
# Faça backup e atualize os arquivos manualmente

# Reiniciar bot com novo código
docker-compose restart

# OU rebuild completo (se mudou requirements.txt)
docker-compose down
docker-compose up -d --build
```

### Debug e Manutenção

```bash
# Entrar no container (modo interativo)
docker-compose exec bot bash

# Executar Python no container
docker-compose exec bot python -c "print('Hello from container')"

# Ver uso de recursos
docker stats projeto-bot-games

# Limpar containers antigos e cache
docker system prune -a
```

---

## 🔧 Troubleshooting

### ❌ Bot não inicia

**Verificar logs:**

```bash
docker-compose logs --tail=50
```

**Problemas comuns:**

| Erro | Solução |
|------|---------|
| `Invalid token` | Verificar DISCORD_TOKEN no .env |
| `Permission denied` | `sudo chown $USER:$USER /opt/projeto-bot-games` |
| `Port already in use` | Verificar se outro container está rodando |
| `No module named 'discord'` | Rebuild: `docker-compose up -d --build` |

---

### 🔄 Restart automático não funciona

**Verificar política:**

```bash
docker inspect projeto-bot-games | grep -A 5 RestartPolicy
```

Deve mostrar: `"Name": "unless-stopped"`

**Corrigir:**

```bash
docker-compose down
docker-compose up -d
```

---

### 💾 Logs crescendo muito

**Configuração atual:** log da aplicação em `logs/bot.log` = 3 arquivos de 5MB (RotatingFileHandler); log do Docker (stdout) = 3 arquivos de 10MB (json-file). Ambos com rotação automática.

**Limpar logs antigos manualmente:**

```bash
docker-compose down
docker system prune -a --volumes
docker-compose up -d
```

---

## 📊 Monitoramento

### Verificar Saúde do Bot

```bash
# Status do container
docker-compose ps

# Healthcheck
docker inspect projeto-bot-games | grep -A 10 Health

# Uso de recursos (CPU, RAM, Rede)
docker stats projeto-bot-games
```

**Saída esperada do stats:**

```
NAME              CPU %   MEM USAGE / LIMIT    MEM %
projeto-bot-games   0.5%    120MiB / 2GiB       6%
```

### Logs Estruturados

```bash
# Filtrar por nível
docker-compose logs | grep ERROR
docker-compose logs | grep WARNING

# Filtrar por timestamp
docker-compose logs --since 1h

# Seguir logs com timestamp
docker-compose logs -f --timestamps
```

---

## 🔐 Segurança

### Proteger Arquivos Sensíveis

```bash
# .env com permissões restritas
chmod 600 .env

# Configurações do bot
chmod 644 config.json history.json state.json
```

### Firewall (UFW)

```bash
# Permitir apenas SSH
sudo ufw allow 22/tcp

# Ativar firewall
sudo ufw enable

# Verificar status
sudo ufw status
```

**Nota:** Bot Discord não precisa abrir portas (só conexões de saída).

---

## 💾 Backup e Restore

### Backup Manual

```bash
# Criar backup com timestamp
cd /opt/projeto-bot-games
tar -czf ~/bot-games-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  config.json \
  history.json \
  state.json \
  .env

# Download para PC local
scp user@servidor:~/bot-games-backup-*.tar.gz ./Desktop/
```

### Backup Automático (Cron)

```bash
# Editar crontab
crontab -e

# Adicionar backup diário às 3h da manhã
0 3 * * * cd /opt/projeto-bot-games && tar -czf ~/backups/bot-games-$(date +\%Y\%m\%d).tar.gz data/ .env
```

### Restore

```bash
# Upload do backup
scp ./bot-games-backup-20260104.tar.gz user@servidor:~/

# Restaurar
cd /opt/projeto-bot-games
docker-compose down
tar -xzf ~/bot-games-backup-20260104.tar.gz
docker-compose up -d
```

---

## 🔄 Migração Entre Servidores

### Servidor Antigo

```bash
# Fazer backup completo
cd /opt/projeto-bot-games
tar -czf bot-games-full-backup.tar.gz *

# Download
scp user@servidor-antigo:/opt/projeto-bot-games/bot-games-full-backup.tar.gz ./
```

### Servidor Novo

```bash
# Preparar diretório
sudo mkdir -p /opt/projeto-bot-games
sudo chown $USER:$USER /opt/projeto-bot-games
cd /opt/projeto-bot-games

# Upload e extrair
scp bot-games-full-backup.tar.gz user@servidor-novo:/opt/projeto-bot-games/
tar -xzf bot-games-full-backup.tar.gz

# Instalar Docker (se necessário)
curl -fsSL https://get.docker.com | sh
sudo apt install docker-compose-plugin -y   # v2: use 'docker compose' (com espaco), nao 'docker-compose' (v1)

# Iniciar bot
docker-compose up -d

# Verificar
docker-compose logs -f
```

**Tempo total de migração:** ~10 minutos ⚡

---

## 🆙 Atualizações de Versão

### Minor Updates (ex: v2.1.0 → v2.1.1)

```bash
cd /opt/projeto-bot-games
git pull
docker-compose restart
```

### Major Updates (ex: v2.0 → v2.1)

```bash
# Backup antes de atualizar
tar -czf backup-pre-update.tar.gz config.json history.json state.json

# Atualizar código
git pull

# Rebuild completo
docker-compose down
docker-compose up -d --build

# Verificar logs
docker-compose logs -f
```

---

## 📂 Estrutura de Arquivos no Servidor

O bot usa o diretório **`./data`** para persistir configuração e estado (evita erro "Is a directory" no Docker). Na primeira execução, o entrypoint cria `data/config.json`, `data/state.json`, `data/history.json` e copia `sources.json` se não existirem.

```
/opt/projeto-bot-games/
├── data/                       # Volume montado no container (DATA_DIR)
│   ├── config.json             # Canal e idioma por servidor
│   ├── state.json              # Cache e dedup
│   ├── history.json            # Links já enviados
│   └── sources.json            # Feeds RSS (cópia na 1ª execução)
├── logs/                       # Logs do bot
├── docker-compose.yml          # Na raiz: aponta build para deploy/Dockerfile
├── deploy/
│   ├── Dockerfile
│   └── entrypoint.sh           # Cria arquivos em data/ se necessário
│
├── 🤖 Bot
│   ├── main.py
│   ├── settings.py
│   ├── sources.json            # Feeds padrão (dentro da imagem)
│   ├── requirements.txt        # Dependências
│   │
│   ├── 📁 bot/                 # Cogs e Views
│   │   ├── cogs/
│   │   └── views/
│   ├── 📁 core/                # Lógica (Scanner, Stats, Filters)
│   ├── 📁 utils/               # Utilitários (Cache, HTML, Tradutor)
│   ├── 📁 web/                 # Web Dashboard (aiohttp)
│   │   ├── server.py
│   │   └── templates/
│   └── 📁 translations/        # Arquivos JSON (en_US, pt_BR, etc)
```

---

## 💡 Dicas e Boas Práticas

### ✅ Do's

- ✅ Use `.env` para secrets
- ✅ Faça backups regulares (cron)
- ✅ Monitore logs com `docker-compose logs -f`
- ✅ Mantenha Docker atualizado
- ✅ Use `docker-compose restart` para updates rápidos
- ✅ Configure firewall (UFW)

### ❌ Don'ts

- ❌ Não commite .env no Git
- ❌ Não rode container como root
- ❌ Não ignore logs de erro
- ❌ Não use `docker-compose up` sem `-d` (trava terminal)
- ❌ Não delete config.json sem backup

---

## 🆘 Suporte

### Recursos

| Recurso | Link |
|---------|------|
| 📖 **README Principal** | [README.md](../README.md) |
| 📚 **Docker Docs** | [docs.docker.com](https://docs.docker.com) |
| 💬 **Discord.py Docs** | [discordpy.readthedocs.io](https://discordpy.readthedocs.io) |

### Comandos de Debug Comuns

```bash
# Ver todas as variáveis de ambiente
docker-compose exec bot env

# Verificar Python e módulos instalados
docker-compose exec bot python --version
docker-compose exec bot pip list

# Testar conexão Discord
docker-compose exec bot python -c "import discord; print(discord.__version__)"

# Ver configuração JSON
docker-compose exec bot cat /app/data/config.json | python -m json.tool
```

---

## ⏱️ Status do Deploy

**Após seguir este guia, seu bot estará:**

- ✅ Rodando 24/7 em Docker
- ✅ Reinício automático se crashar
- ✅ Logs com rotação automática
- ✅ Dados persistentes em volumes
- ✅ Fácil de atualizar (`git pull && docker-compose restart`)
- ✅ Isolado do sistema (seguro)
- ✅ Monitorável com `docker stats`

---

<p align="center">
  <b>🎉 Bot está ONLINE e rodando!</b><br>
  <i>Desenvolvido com ❤️ para a comunidade de jogos</i>
</p>
