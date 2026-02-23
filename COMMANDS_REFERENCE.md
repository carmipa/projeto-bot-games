# 📚 Referência Completa de Comandos - GameBot

**Versão:** 2.1 "v2.1"  
**Última Atualização:** 13 de Fevereiro de 2026

---

## 📋 Índice

- [🔧 Comandos Administrativos](#-comandos-administrativos)
- [📊 Comandos Informativos](#-comandos-informativos)
- [📖 Guia de Uso Detalhado](#-guia-de-uso-detalhado)

**Lista rápida:** Ver [COMANDOS.md](COMANDOS.md)

---

## 🔧 Comandos Administrativos

> **⚠️ Requerem permissão de Administrador no servidor Discord**

### `/set_canal`

**Descrição:** Define o canal onde o bot enviará notícias de jogos.

**Sintaxe:**
```
/set_canal [canal:#noticias]
```

**Parâmetros:**
- `canal` (opcional): Canal de texto onde as notícias serão enviadas
  - Se não especificado, usa o canal atual

**Exemplos:**
```
/set_canal                    # Usa o canal atual
/set_canal canal:#noticias    # Define canal específico
```

**Validações:**
- ✅ Verifica se o canal é de texto
- ✅ Verifica permissões do bot (Enviar Mensagens, Incorporar Links)
- ✅ Mostra avisos se faltar permissão

**Resposta:**
- ✅ Confirmação com canal configurado
- ⚠️ Aviso se faltar permissão
- ❌ Erro se canal inválido

---

### `/dashboard`

**Descrição:** Abre painel visual interativo para configurar filtros e idioma.

**Sintaxe:**
```
/dashboard
```

**Funcionalidades:**
- 🌐 Seleciona idioma (🇺🇸 English / 🇧🇷 Português)
- ⚙️ Configura o canal automaticamente

**Botões Disponíveis:**
- 🇺🇸 **English** - Idioma inglês
- 🇧🇷 **Português** - Idioma português (Brasil)

**Nota:** O painel é **persistente** — funciona mesmo após restart do bot. Todas as notícias aprovadas pelo filtro são enviadas ao canal configurado.

---

### `/setlang`

**Descrição:** Define o idioma do bot para o servidor.

**Sintaxe:**
```
/setlang idioma:[código]
```

**Parâmetros:**
- `idioma` (obrigatório): Código do idioma
  - `en_US` - 🇺🇸 English
  - `pt_BR` - 🇧🇷 Português (Brasil)

**Exemplos:**
```
/setlang idioma:pt_BR    # Português
/setlang idioma:en_US    # Inglês
```

**Resposta:**
- ✅ Confirmação com idioma configurado

---

### `/forcecheck`

**Descrição:** Força uma varredura imediata de todos os feeds.

**Sintaxe:**
```
/forcecheck
```

**Uso:**
- Útil para testar se o bot está funcionando
- Quando você sabe que saiu uma notícia urgente
- Não quer esperar o ciclo automático (padrão: 12h)

**Resposta:**
- ✅ Confirmação quando varredura concluída
- ❌ Erro se falhar

**Nota:** Respeita o lock de varredura - se já houver uma em execução, ignora.

---

### `/clean_state`

**Descrição:** Limpa partes específicas do `state.json` com backup automático.

**Sintaxe:**
```
/clean_state tipo:[tipo] confirmar:[sim/não]
```

**Parâmetros:**
- `tipo` (obrigatório): Tipo de limpeza
  - `dedup` - 🧹 Histórico de links enviados
  - `http_cache` - 🌐 Cache HTTP (ETags)
  - `html_hashes` - 🔍 Hashes de monitoramento HTML
  - `tudo` - ⚠️ Limpa tudo (use com cuidado!)
- `confirmar` (opcional): Confirmação explícita
  - `sim`, `yes`, `s`, `y`, `confirmar`, `confirm` - Confirma
  - Qualquer outro valor - Mostra estatísticas e pede confirmação

**Fluxo de Uso:**

**Passo 1 - Ver Estatísticas:**
```
/clean_state tipo:dedup confirmar:não
```
Mostra estatísticas atuais e pede confirmação.

**Passo 2 - Confirmar Limpeza:**
```
/clean_state tipo:dedup confirmar:sim
```
Executa limpeza após criar backup.

**Opções de Limpeza:**

| Tipo | O que Limpa | Impacto | Quando Usar |
|------|-------------|---------|-------------|
| 🧹 **dedup** | Histórico de links enviados | ⚠️ Bot repostará notícias recentes | Histórico corrompido |
| 🌐 **http_cache** | Cache HTTP (ETags, Last-Modified) | ℹ️ Mais requisições HTTP | Feeds não atualizam |
| 🔍 **html_hashes** | Hashes de monitoramento HTML | ⚠️ Sites detectados como "mudados" | Monitor HTML não funciona |
| ⚠️ **tudo** | Limpa tudo (exceto metadados) | 🚨 Todos os efeitos acima | Apenas em emergências |

**Proteções:**
- ✅ Backup automático antes de limpar
- ✅ Se backup falhar, limpeza é cancelada
- ✅ Confirmação dupla obrigatória
- ✅ Estatísticas antes/depois
- ✅ Logging de auditoria completo

**Exemplo Completo:**
```
# 1. Ver estatísticas
/clean_state tipo:dedup confirmar:não

Resposta:
🧹 Limpeza do state.json
Tipo selecionado: 🧹 Dedup (Histórico de links enviados)
⚠️ ATENÇÃO: Isso fará o bot repostar notícias já enviadas!

📊 Estatísticas Atuais:
Dedup: 15 feeds, 1.234 links
HTTP Cache: 33 URLs
HTML Hashes: 8 sites
Tamanho: 245.3 KB

✅ Para Confirmar
Use /clean_state tipo:dedup confirmar:sim

# 2. Confirmar
/clean_state tipo:dedup confirmar:sim

Resposta:
✅ Limpeza Concluída
Tipo: 🧹 Dedup (Histórico de links)
Backup criado: state_backup_20260213_152630.json

📊 Antes          📊 Depois
Dedup: 1234      Dedup: 0
HTTP: 33         HTTP: 33
HTML: 8          HTML: 8
```

---

## 📊 Comandos Informativos

> **✅ Disponíveis para todos os usuários**

### `/status`

**Descrição:** Mostra estatísticas completas do bot.

**Sintaxe:**
```
/status
```

**Informações Exibidas:**
- ⏰ **Uptime** - Tempo online desde o último restart
- 📡 **Varreduras** - Total de scans completados
- 📰 **Notícias Enviadas** - Total de notícias postadas
- 📦 **Cache Hits** - Total de hits de cache HTTP
- 🕐 **Última Varredura** - Timestamp da última varredura
- ⏳ **Próxima Varredura** - Quando será a próxima (intervalo: 12h)
- 📋 **Intervalo** - Exibido no rodapé (ex.: 12h)

**Botão Adicional:**
- 🔄 **Verificar Agora** - Executa varredura manual (comando `/now`)

**Resposta:** Embed com todas as estatísticas

---

### `/now`

**Descrição:** Força uma verificação imediata de notícias (atalho para varredura manual).

**Sintaxe:** `/now`

**Resposta:** Confirmação quando a varredura for concluída.

---

### `/feeds`

**Descrição:** Lista todas as fontes de feeds monitoradas.

**Sintaxe:**
```
/feeds
```

**Informações Exibidas:**
- Lista de até 15 feeds (com link clicável)
- Total de feeds monitorados
- Contador de feeds adicionais (se houver mais de 15)

**Resposta:** Embed com lista de feeds

---

### `/help`

**Descrição:** Mostra manual de ajuda com todos os comandos.

**Sintaxe:**
```
/help
```

**Informações Exibidas:**
- 📖 Lista de comandos administrativos
- 📊 Lista de comandos informativos
- Organizado por categoria

**Resposta:** Embed com manual completo

---

### `/about`

**Descrição:** Informações sobre o bot, desenvolvedor e tecnologias.

**Sintaxe:**
```
/about
```

**Informações Exibidas:**
- Nome e descrição do bot
- 👨‍💻 Desenvolvedor
- 📦 Versão
- 🛠️ Stack tecnológico
- Mensagem de rodapé

**Resposta:** Embed com informações do bot

---

### `/ping`

**Descrição:** Verifica latência do bot com a API do Discord.

**Sintaxe:**
```
/ping
```

**Resposta:**
```
🏓 Pong! Latência: 45ms
```

---

## 📖 Guia de Uso Detalhado

### 🚀 Primeira Configuração

1. **Configure o Canal:**
   ```
   /set_canal
   ```
   Ou use o dashboard:
   ```
   /dashboard
   ```

2. **Configure o Idioma:**
   - Use `/setlang idioma:pt_BR` ou `/dashboard` e clique nas bandeiras (🇺🇸 🇧🇷)

3. **Verifique se Está Funcionando:**
   ```
   /forcecheck
   /status
   ```

---

### 🔧 Manutenção Regular

**Limpar Cache (quando necessário):**
```
# Ver estatísticas primeiro
/clean_state tipo:http_cache confirmar:não

# Se necessário, confirmar
/clean_state tipo:http_cache confirmar:sim
```

**Forçar Varredura:**
```
/forcecheck
```

**Verificar Status:**
```
/status
```

---

### ⚠️ Troubleshooting

**Bot não está enviando notícias:**
1. Verifique se canal está configurado: `/status`
2. Verifique se há filtros ativos: `/dashboard` → "Ver filtros"
3. Force uma varredura: `/forcecheck`

**Notícias duplicadas:**
- Limpe o dedup: `/clean_state tipo:dedup confirmar:sim`
- ⚠️ Isso fará o bot repostar notícias recentes!

**Feeds não atualizam:**
- Limpe o cache HTTP: `/clean_state tipo:http_cache confirmar:sim`
- Isso forçará novas requisições HTTP

**Monitor HTML não funciona:**
- Limpe os hashes: `/clean_state tipo:html_hashes confirmar:sim`
- Sites serão detectados como "mudados" novamente

---

## 🔒 Permissões Necessárias

### Para o Bot:
- ✅ **Enviar Mensagens** - Obrigatório
- ✅ **Incorporar Links** - Recomendado (para embeds)
- ✅ **Ler Histórico de Mensagens** - Opcional

### Para Usuários:
- ✅ **Administrador** - Para comandos administrativos
- ✅ **Nenhuma** - Para comandos informativos

---

## 📝 Notas Importantes

1. **Comandos são case-insensitive** - `/HELP` funciona igual a `/help`
2. **Comandos podem levar alguns segundos** - Especialmente `/forcecheck` e `/clean_state`
3. **Backups são criados automaticamente** - Em `backups/` antes de limpezas
4. **Logs de auditoria** - Todas as ações administrativas são logadas
5. **Painel é persistente** - Funciona mesmo após restart do bot

---

**Última Atualização:** 19 de Fevereiro de 2026  
**Versão do Bot:** 2.1 "v2.1"
