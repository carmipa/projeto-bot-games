# Correções da auditoria de saúde — GameBot v2.2

**Data:** 2026-08-01 · **Branch:** `main` · **Autor:** Paulo (carmipa) + Claude Code

Continuação de `2026-07-12_auditoria-profunda.md`. Ordem de execução pedida pelo Paulo:
**fontes → críticos → sérios**. Toda fonte e todo comportamento aqui foi medido pelo
caminho real do código antes de entrar; nada foi aceite por inspeção.

Contexto que enquadra tudo: **o bot não roda desde 2026-03-27** (última linha de
`logs/bot.log`). As correções de julho nunca passaram por runtime.

---

## Fase 1 — Fontes

### O achado que mudou o diagnóstico

`_fetch_youtube_channel_id_from_page` procurava a **primeira** ocorrência de
`"channelId"` no HTML da página do canal. Numa página de canal do YouTube essa primeira
ocorrência costuma ser um canal **recomendado ou vinculado** da barra lateral. O bot vinha
assinando o canal errado, em silêncio, e a fonte "funcionava" — devolvia vídeos, só que
dos outros:

| pedido | canal que o bot assinava |
|---|---|
| `@PlayStation` | Marathon |
| `@Xbox` | Forza |
| `@Ubisoft` | Rainbow 6 |
| `@SEGA` | atlustube |
| `@Blizzard` | PlayOverwatch |
| `@CDPROJEKTRED` | Cyberpunk 2077 |
| `@UnrealEngine` | Fab |
| `@2K` | cloner |
| `@Nintendo` | koi |

Substituído por três âncoras que identificam a **própria** página, por ordem de confiança:
`<link rel="alternate" ... channel_id=UC…>` (o feed canónico que o YouTube declara),
`"externalId"` do `ytInitialData`, e `<link rel="canonical" .../channel/UC…>`.

**Medido em 38 handles: acerto do nome 24/38 → 35/38.** Os 3 restantes são handles
realmente ocupados por terceiros (`@2K`, `@Nintendo`, e um caso sem âncora).

### Catálogo

Critério de entrada: status 200, ≥1 entrada, item mais recente com menos de 180 dias,
verificado 3× quando o veredito era negativo.

**Removidas (20 fontes mortas):**
- 14 `channel_id` com 404 determinístico. Não eram inventados — eram **corrompidos**:
  `UCGIY_O-8G0jTH-kd_4_236g` é o Nintendo of America (`UCGIY_O-8vW4rfX98KlMkvRg`) com o
  sufixo trocado.
- 3 `@handle` com página 404: `@TakeTwoGames`, `@KoeiTecmo`, `@Team17`.
- `giantbomb.com/feeds/mashup/` — 403 em 6 User-Agents (navegador, curl, requests,
  aiohttp, leitor de feed, googlebot). `/feeds/news/` também reprova.
- `vg247.com/feed` — congelado há 60 dias (`/feed/news` idem).
- `eurogamer.pt/feed/videos` — congelado há 917 dias.

**Corrigidas:** `gameinformer.com/rss` (200 com 0 entradas) → `/news.xml` (50 entradas);
`videogamer.com/news/feed` (403) → `www.videogamer.com/feed/` (30 entradas). Nos dois
casos o problema era o caminho, não bloqueio: nenhum User-Agent alterava o resultado.

**Handles ocupados por terceiros:** `@EA` → `@ElectronicArts` (o `@EA` resolve para um
canal chamado "Albania" com 0 vídeos — era ele que produzia o "Feed 200 sem entradas" nos
logs); `@2K` → `@2KGames`.

**Adicionadas** (só depois de aprovadas na sondagem): canais oficiais que faltavam
(PlayStation, Xbox, Nintendo of America, Ubisoft, Rockstar, Bethesda, CD PROJEKT RED,
Devolver, Call of Duty, Steam, The Game Awards, ATLUS West), canais **BR** (PlayStation
Brasil, Ubisoft Brasil, IGN Brasil) e 9 RSS (Polygon, Gematsu, Siliconera, Automaton,
Nintendo Life, Push Square, Pure Xbox, Insider Gaming, The Verge Games).

**Reprovadas e por isso fora:** `@Activision` (0 vídeos), `@HoYoverse` (877 dias),
`@larianstudios` (229d), `@FocusEntertainment` (249d — o Focus vivo já estava na lista por
`channel_id`), `@Krafton` (handle ocupado), `@NintendoBrasil` (3061 dias).

**HTML Monitor:** `sega.com` e `devolverdigital.com` removidos — bloqueio de bot
recorrente, falhavam em toda varredura.

### `youtube_feed_map`

Passou de 1 para 41 pares verificados. Efeito medido: a resolução de canais do YouTube faz
agora **0 requisições HTTP** por varredura (eram ~14 raspagens de página HTML).

### Validação

Ponta-a-ponta pelo código real (`load_sources` → `resolve_youtube_urls` → fetch →
feedparser): **69/69 fontes saudáveis, 0 requisições de resolução.**

---

## Fase 2 — Críticos

### 1. Status não-200 engolido em silêncio

`fetch_and_process_feed` só tratava `304` e `431`. Qualquer outro não-200 caía no
`feedparser`, que devolvia zero entradas — e o aviso "Feed 200 sem entradas" estava
guardado por `resp.status == 200`. Consequência: 403/404 **não contavam erro, não entravam
em `source_failures` e não apareciam em log nenhum**. O resumo dizia `feeds_com_erro=0`
com 20 fontes mortas.

Ironia registada: em março essas fontes falhavam **alto** (`ClientError` por falta de
brotli). Instalar o brotli corrigiu o erro e converteu falha ruidosa em falha muda.

Agora não-200 conta erro, grava `source_failures`, loga status + URL, escala para
`[Source Health]` na 3ª falha e **não grava ETag de resposta de erro**. `200` com zero
entradas também passou a contar.

Prova em `DATA_DIR` isolado com 3 fontes (403, 404, viva):
`feeds_com_erro=2` (era 0) e as duas gravadas em `source_failures` com URL completa.

### 2. `pytest` executava uma varredura de produção

`test_integration_run_scan_once_with_empty_config` afirmava na docstring "não faz HTTP",
mas rodava com o `config.json` real — que tem `channel_id`. Executava uma varredura
completa: 69 fontes baixadas, dezenas de notícias reais casadas, `state.json` e
`history.json` do bot reescritos (`history.json` de produção continha `mock.feed/1..4`).

O estrago não era a sujeira. `update_cache_state()` grava ETag/`Last-Modified` de todo feed
baixado, tenha ou não postado. Como o bot mockado não tem canal, nada saía — mas a
varredura real seguinte recebia **304** e perdia essas notícias para sempre.

Correção estrutural em `tests/conftest.py`: fixture autouse aponta `DATA_DIR` para
diretório temporário durante toda a sessão (`sources.json` real copiado, `config.json`
vazio). Nenhum teste alcança a raiz. Fixture `sem_rede` falha o teste que abrir
`ClientSession`, e um teste novo trava a regressão do isolamento.

| | antes | depois |
|---|---|---|
| suíte | 59 passed em **24,49s** | 80 passed em **1,00s** |
| `state.json`/`history.json` | reescritos | hash idêntico antes/depois |

Os 24 segundos eram a rede.

### 3. O bot não subia no interpretador padrão

O `python` do PATH é `C:\Python314\python.exe`, sem nenhuma dependência instalada; só a
`.venv` (3.12) tem o ambiente. `python main.py` morria no `import discord`.

Preflight em `main.py` (só biblioteca padrão, antes dos imports de terceiros): exige 3.10+
e verifica os 12 pacotes — incluindo **brotli**, que o código não importa mas o aiohttp
precisa para decodificar o `Accept-Encoding: br` que o bot pede. Imprime interpretador em
uso, o que falta e o comando exato de correção. `run.ps1` sobe sempre pela venv (e cria a
venv se não existir).

---

## Fase 3 — Sérios

### 4. Agendador duplicado a cada reconexão

`start_scheduler` é chamado do `on_ready`, que o discord.py reexecuta a cada reconexão do
gateway. Como o `@tasks.loop` era declarado **dentro** da função, cada chamada criava um
objeto `Loop` novo: não havia o `RuntimeError` de "already launched" que protegeria um loop
de módulo, o anterior não era cancelado e o global só perdia a referência. Medido: 2
chamadas → 2 tasks `news_scan_loop` ativas. Um agendador extra por reconexão, acumulando.

O próprio `main.py` já tinha a guarda `_commands_synced` 10 linhas acima, pelo mesmo
motivo — o autor sabia que `on_ready` repete.

### 5. CI quebrada em Python 3.9

A matriz rodava `["3.9","3.10","3.11"]`, mas o código usa PEP 604 (`str | None`) avaliado
em tempo de definição, sem `from __future__ import annotations`. Em 3.9 é `TypeError` no
import. Matriz passou a 3.10 (versão do Dockerfile), 3.11 e 3.12 (versão da venv).

### 6. `clean_state` incompleto e sem trava

`youtube_feed_cache` e `source_failures` nunca eram limpos: `tipo:tudo` mentia. Chaves
agora declaradas em `CHAVES_LIMPAVEIS` / `METADADOS_PRESERVADOS`, nova opção
`youtube_feed_cache` no comando e contadores no relatório.

`test_clean_state_chaves.py` é uma **guarda genérica**: lê `core/scanner.py`, extrai as
chaves que o scanner escreve em `state` e falha se alguma não estiver classificada.
Verificado que enxerga as 6 chaves reais.

O comando também passou a pegar o `scan_lock`. Sem ele, uma limpeza durante uma varredura
(até 125 min) era desfeita pelo `save_json_safe` final — e o admin via "limpeza concluída".

### 7. Sanitizador de log destruía o diagnóstico

`([a-zA-Z0-9_-]{20,})` truncava **qualquer** sequência longa para 8 chars + "…", sem
proteger segredo nenhum que as regras rotuladas já não cobrissem:

```
antigo: Feed HTTP 404: .../videos.xml?channel_id=UCKy1dAq...
novo  : Feed HTTP 404: .../videos.xml?channel_id=UCKy1dAqELo0zrOtPkf0eTMw
```

Cegava exatamente as mensagens de fonte morta, que existem para ser lidas. Substituído por
5 padrões ancorados (rótulo `token=`/`secret=`, header `Authorization`, forma estrutural do
bot token do Discord, webhook do Discord, segredo em query string). 12 testes cobrem os
dois lados: esconde segredo **e** preserva URL, status e erro técnico.

Detalhe apanhado por teste: o padrão rotulado com `\S+` engolia o resto da query string
(`?token=x&y=1` perdia o `y=1`). Valor passou a parar em `&`.

---

## Estado do `state.json` de produção

Limpezas feitas via `clean_state` (com backup em `backups/`), porque o estado estava
contaminado pelas execuções antigas do pytest e pela resolução quebrada:

| chave | antes | depois | motivo |
|---|---|---|---|
| `http_cache` | 88 | 0 | ETags de feeds que o teste baixou e nunca postou |
| `youtube_feed_cache` | 23 | 0 | resoluções do regex quebrado (ex.: `@EA` → canal "Albania") |
| `source_failures` | 12 | 0 | falhas de brotli de março, obsoletas |
| `html_hashes` | 39 | 39 | preservado — limpar geraria alerta falso em 39 sites |
| `dedup` | 0 links | 0 links | já estava vazio |

---

## Verificação final

- ✅ Suíte: **80 passed em 1,00s**, sem `--ignore`.
- ✅ `compileall` exit 0.
- ✅ Fontes: **69/69 saudáveis** pelo caminho real do código, 0 requisições de resolução.
- ✅ Produção intocada pela suíte: hash de `state.json`, `history.json` e `config.json`
  idêntico antes e depois.
- ✅ Fonte morta agora acusa: `feeds_com_erro=2` onde antes era 0.
- 🟡 **Nada disto foi validado com o bot ligado ao Discord** — o bot está parado desde
  março e não foi iniciado nesta sessão. Continuam por provar em runtime: o anúncio de
  versão, o `/clean_state` pela interface do Discord e o comportamento do agendador numa
  reconexão real.
- 🟡 **Primeira varredura vai ter rajada.** As fontes novas entram em cold start e o
  `http_cache` foi zerado; espere um volume alto de posts na primeira execução, limitado a
  10 itens por feed e a notícias com menos de 7 dias.

## Ficheiros alterados

```
sources.json                       catálogo v3.0 verificado + youtube_feed_map com 41 pares
core/scanner.py                    âncoras do channel_id, não-200 contabilizado, scheduler idempotente
main.py                            preflight de ambiente
run.ps1                            (novo) sobe sempre pela venv
utils/security.py                  sanitizador ancorado
utils/storage.py                   clean_state completo + chaves declaradas + stats
bot/cogs/admin.py                  scan_lock, nova opção e contadores no /clean_state
tests/conftest.py                  isolamento de DATA_DIR + fixture sem_rede
tests/test_integration.py          teste honesto + trava do isolamento
tests/test_scheduler_idempotente.py  (novo)
tests/test_clean_state_chaves.py     (novo) guarda genérica de chaves
tests/test_log_sanitizer.py          (novo)
.github/workflows/python-package.yml matriz 3.10/3.11/3.12
```

## Commits

```
f9b27fd  fontes: repara catalogo (20 mortas removidas) e corrige resolucao de canal do YouTube
cb7815f  criticos: fonte morta deixa de ser silenciosa, testes param de tocar producao e bot falha com instrucao
bfda6dc  serios: agendador idempotente, CI sem 3.9, clean_state completo e sanitizador ancorado
```

## Lições transversais

1. **Sonda simplificada mente.** Uma primeira sondagem com regex único deu 11 handles como
   mortos; repetida pelo caminho real do código (3 regexes de fallback), 12 dos 15
   resolviam. Verificar sempre pelo código de produção, não por uma reimplementação.
2. **Fonte que "funciona" pode estar errada.** O teste de vivacidade (200 + entradas) não
   detetava nada — os canais recomendados publicam normalmente. Só comparar o **nome** do
   feed com o que se pediu expôs o problema.
3. **Corrigir um erro pode silenciar o diagnóstico.** Instalar o brotli transformou falha
   ruidosa em falha muda durante meses.
4. **Acrescentar estado é meia funcionalidade.** A outra metade é ensinar quem limpa esse
   estado a conhecê-lo — daí a guarda genérica em vez de mais uma chave na lista.
