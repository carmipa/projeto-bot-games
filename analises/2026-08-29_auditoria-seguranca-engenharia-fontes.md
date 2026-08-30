# Auditoria de segurança, engenharia e testes + ampliação de fontes — 2026-08-29

**Máquina:** `DESKTOP-QDNQHL1` (desktop AMD, IP residencial). Medida na sessão, não suposta.
**Base:** `main` @ `8b87ae2`, working tree limpa no início.
**Venv:** Python 3.12.0. **Suíte no início:** 80 passed, exit 0.

Método: protocolo de engenharia de alta garantia — três lentes sobre cada conclusão
(correção · impacto real · já resolvido) e três sobre cada alteração (adversarial · erro de
boa-fé · falha operacional). Todo achado abaixo sobreviveu às três primeiras; os refutados
estão registrados com o motivo, para a próxima auditoria não os reencontrar do zero.

---

## Entendimento da missão

Verificação geral de segurança, engenharia e testes do GameBot; propor e aplicar melhorias;
acrescentar fontes de dados. Escopo fechado antes de começar. Duas auditorias anteriores
(2026-07-12 e 2026-08-01) já haviam passado pelo código — o valor desta estava em achar o
que sobreviveu às duas, não em repetir o que elas fizeram.

## Fluxo atual confirmado

`main.py` (`on_ready`: web → views → sync → agendador → anúncio de versão) → `core/scanner.py`
`run_scan_once` (carrega config/sources/state → resolve handles do YouTube → fetch concorrente
com semáforo → `feedparser` em executor → dedup por feed → filtros → tradução → publica no
Discord → HTML Monitor → salva estado) → `utils/{storage,cache,security,logger,translator}` +
`web/server.py`.

---

## Invariantes declarados

| ID | Invariante | Dano se quebrado | Camadas | Testes | Estado |
|---|---|---|---|---|---|
| INV-ENTREGA-001 | O cache HTTP de um feed só avança quando aquele feed foi processado **sem falha de entrega** | Notícia perdida para sempre: sem o link no dedup e com 304 na varredura seguinte, ela nunca mais é vista | `falha_de_entrega` no laço de resultados; cabeçalhos viajam com o resultado em vez de irem direto ao cache | `test_scanner_cache_entrega.py` (3, com controle positivo) | ✅ fechado, guarda calibrada |
| INV-ARRANQUE-001 | Nenhum componente acessório pode impedir o agendador de subir | Bot online, aparentemente saudável, que nunca varre — falha invisível | `start_web_server_tolerante()` não propaga exceção | `test_web_server_tolerante.py` (4, com calibração) | ✅ fechado, guarda calibrada |
| INV-LOOP-001 | Nenhuma chamada bloqueante corre na thread do event loop no caminho de varredura | Heartbeat do gateway atrasa e o Discord derruba a conexão | `validate_url_async` com `loop.getaddrinfo`; política única em `_validar_estrutura`/`_veredito_dns` | `test_security_dns_async.py` (13, mede a thread + guarda de uso no código de produção) | ✅ fechado, guarda calibrada |
| INV-SEGREDO-001 | Token do Discord, token do dashboard e URL de webhook nunca chegam a log | Segredo em `logs/bot.log`, que viaja em relatório e captura de tela | `sanitize_log_message` (padrões ancorados) + `SecurityFilter` sobre a mensagem **renderizada** | `test_log_filter_args.py` (7, com controle negativo) | ✅ fechado |
| INV-CATALOGO-001 | Todo handle do YouTube tem par no mapa, nenhum `channel_id` repete, nenhum par é órfão | Requisição extra por handle; notícia publicada em duplicado; auditoria futura lê fonte morta como ativa | `sources.json` v3.1 | `test_catalogo_fontes.py` (8, com catálogo-controle doente) | ✅ fechado |
| INV-SSRF-001 | Nenhuma URL do catálogo alcança IP privado | Bot vira proxy para a rede interna de quem o hospeda | `validate_url`/`validate_url_async`, falha fechada em erro de resolução | `test_security_dns_async.py` | 🟡 ver risco residual (TOCTOU) |

---

## Achados confirmados e corrigidos

### 🔴 1. Falha do dashboard web abortava o `on_ready` inteiro

`on_ready` é handler de evento: uma exceção ali é apenas registrada pelo discord.py e **tudo
o que vem depois deixa de executar**. `await start_web_server()` era a primeira instrução,
sem proteção. Bastava a porta 8080 ocupada — outra instância, qualquer serviço — para o bot
ficar online, responder aos comandos já sincronizados, e **nunca** sincronizar comandos novos,
**nunca** iniciar o agendador e **nunca** varrer. Sem nenhum log que ligasse causa e efeito.

*Lente 3 (já resolvido?):* não. A auditoria de 2026-08-01 tornou `start_scheduler`
idempotente — o que garante um único loop, não que o loop chegue a nascer.

**Evidência da correção (calibração — proteção removida do código):**
```
=== teste com a protecao removida ===
FAILED tests/test_web_server_tolerante.py::test_porta_ocupada_nao_propaga_excecao
FAILED tests/test_web_server_tolerante.py::test_excecao_generica_tambem_e_contida
2 failed, 2 passed
=== restaurado ===
4 passed in 0.30s
```

### 🔴 2. Perda permanente de notícia por ETag gravado antes da publicação

`update_cache_state()` corria logo após o HTTP 200, antes do parse e antes de publicar. Se a
publicação falhasse (sem permissão no canal, canal apagado, 5xx do Discord), o link **não**
entrava no dedup mas o ETag ficava gravado ⇒ a varredura seguinte recebia 304, o feed não
devolvia entrada nenhuma, e aquelas notícias desapareciam para sempre.

É a mesma classe que o `conftest.py` já descrevia para os testes; ninguém tinha notado que
ela existe **em produção**, no caminho normal.

**Evidência da correção (calibração — defeito reintroduzido):**
```
=== CALIBRACAO 1: reintroduz o bug do ETag (cache avanca sempre) ===
FAILED tests/test_scanner_cache_entrega.py::test_falha_de_entrega_nao_grava_o_etag
FAILED tests/test_scanner_cache_entrega.py::test_canal_inexistente_tambem_segura_o_cache
2 failed, 1 passed
=== restaurado; reconferindo ===
3 passed in 1.13s
```
O `1 passed` no meio é o controle positivo: com o bug, o cache continua avançando no caminho
de sucesso. Sem ele, "cache vazio" seria indistinguível de "este código nunca grava cache".

### 🔴 3. O passo de lint do CI estava vermelho — e a suíte não rodava no CI

`flake8 --select=E9,F63,F7,F82` casa por **prefixo**: `F82` captura `F824`, regra introduzida
no pyflakes 3.x. `core/scanner.py:893` declarava `nonlocal state, entries_undated_skipped`,
nomes nunca reatribuídos naquele escopo.

**Evidência (comando exato do CI, contra o arquivo do HEAD, antes de qualquer alteração minha):**
```
$ git show HEAD:core/scanner.py > /tmp/scanner.py
$ flake8 /tmp/scanner.py --count --select=E9,F63,F7,F82 --show-source
scanner.py:893:13: F824 `nonlocal state` is unused: name is never assigned in scope
scanner.py:893:13: F824 `nonlocal entries_undated_skipped` is unused: name is never assigned in scope
2
EXIT_HEAD=1
flake8 7.3.0 (mccabe: 0.7.0, pycodestyle: 2.14.0, pyflakes: 3.4.0)
```
Como o passo de lint vem **antes** do `pytest` e os passos são sequenciais, o `pytest` nunca
chegava a rodar. O CI estava decorativo. Corrigido no código, não afrouxando o filtro.

**Depois:** `flake8 . --count --select=E9,F63,F7,F82` → `0`, exit `0`.

### 🟠 4. DNS bloqueante dentro do event loop

`validate_url()` faz `socket.getaddrinfo`, que bloqueia, e era chamada de dentro de
corrotinas: uma vez por feed (~92 no catálogo novo) e uma por site do HTML Monitor (~29).
Mesma classe do defeito de julho, quando o BeautifulSoup bloqueava o loop e foi movido para
executor — o DNS ficou para trás.

A primeira versão do teste afirmava "o caminho async não chama `socket.getaddrinfo`" e
**reprovou na calibração**: `loop.getaddrinfo` acaba a chamá-lo também, numa thread do
executor. O instrumento estava errado, não o código. A propriedade correta — e a que o teste
final mede — é **em que thread** a chamada corre.

**Evidência (calibração — os dois defeitos reintroduzidos: `socket` no async e `validate_url`
no scanner):**
```
=== com os defeitos de volta ===
E   scanner.py:901: is_valid, error_msg = validate_url(url)
FAILED tests/test_security_dns_async.py::test_async_resolve_fora_da_thread_do_event_loop
FAILED tests/test_security_dns_async.py::test_nenhum_modulo_async_chama_a_versao_sincrona
2 failed, 11 passed
=== restaurado ===
13 passed
```

### 🟠 5. Docker congelava o `sources.json` — fonte nova nunca chegava ao contêiner

`utils/storage.py` resolvia `sources.json` por `DATA_DIR`, e o `entrypoint.sh` o copiava para
o volume **só se não existisse**. Depois da primeira subida, toda fonte acrescentada ao
repositório era ignorada pelo contêiner, em silêncio: rebuild, redeploy, catálogo antigo.

Diretamente no caminho do que foi pedido nesta sessão — sem isto, "adicionei fontes" seria
mentira em qualquer deploy Docker. `sources.json` deixou de ser dado de execução (é escrito
por quem edita o repositório, não pelo bot) e passou a ser catálogo versionado lido de
`/app/sources.json`. O entrypoint avisa se sobrou uma cópia no volume.

### 🟠 6. Truncagem silenciosa por `MAX_ENTRIES_PER_FEED`

Teto de 10 entradas por feed com varredura de 24 h. Medido hoje no catálogo: `@IGN` trouxe 11
itens em 24 h e `polygon.com` exatamente 10 — ou seja, já há feeds no limite ou acima, e o
excesso era descartado **sem uma linha de log**. Feeds não paginam, então o que se pode fazer
é tornar a perda visível: agora loga quantas entradas foram descartadas sem análise e o que
ajustar (`MAX_ENTRIES_PER_FEED` ou `LOOP_MINUTES`).

### 🟠 7. Sanitização de log não cobria formatação preguiçosa

`SecurityFilter` limpava apenas `record.msg`. Em `log.error("feed %s falhou", url)` — estilo
usado em vários pontos do scanner — o **argumento** passava intacto. A garantia anunciada no
README era mais larga do que a realidade. Passa a sanitizar a mensagem renderizada, com
`record.args` zerado para não haver dupla formatação. Controle negativo no teste: um
`channel_id` do YouTube tem de **sobreviver** — mascarar tudo o que é longo foi exatamente a
regressão corrigida em 2026-08-01.

### 🟠 8. Logger do dashboard fora do arquivo de log

`web/server.py` usava `getLogger("GameNewsWeb")` — irmão, não filho, de `GameBot`. Sem
handlers e sem `SecurityFilter`: os `INFO` sumiam e "tentativa de acesso com token inválido de
IP X", um evento de segurança, só saía no stderr de último recurso, **nunca** em
`logs/bot.log`. Agora é `GameBot.web`.

### 🟡 9. Mina dormente em `utils/cache.py`

`save_http_state()` gravaria o dicionário de cache HTTP **por cima do `state.json` inteiro**,
apagando `dedup`, `html_hashes` e `last_announced_hash` — repostagem em massa de tudo o que o
bot já publicou. Estava morta (a varredura usa `state["http_cache"]` diretamente), portanto o
dano hoje é zero. Removida em vez de documentada: caminho errado que continua disponível e
parece certo acaba por ser usado.

### 🟡 10. Lacuna de varredura de dependências no CI (era GAP declarado)

Acrescentado `pip-audit`, que **reprova** em qualquer CVE nova. Achado real na primeira
execução:

```
Name            Version ID             Fix Versions
deep-translator 1.11.4  PYSEC-2022-252
Found 1 known vulnerability in 1 package
```

O aviso registra o sequestro da conta do mantenedor no PyPI em 2022, com release maliciosa
que roubava variáveis de ambiente e baixava malware **em tempo de instalação**. Não declara
versão corrigida, então casa com qualquer versão — inclusive a 1.11.4, que é a mais recente
publicada e já é o piso do `requirements.txt`.

**Verificação do artefato instalado (não da afirmação):**
```
--- WHEEL --- Generator: poetry-core 1.6.1 ; Root-Is-Purelib: true
--- hooks de instalacao (setup.py / *.pth) --- (vazio)
--- imports de rede/exec suspeitos --- (vazio: sem subprocess|os.system|eval(|exec(|environ)
```
O vetor descrito no aviso não existe neste artefato. Exceção nominal, datada e justificada no
workflow; qualquer CVE **nova** reprova. Calibrado nos dois sentidos: sem o `--ignore-vuln`,
1 achado e exit 1; com ele, `No known vulnerabilities found, 1 ignored`, exit 0.

### 🟡 11. Arranque sem `DISCORD_TOKEN`

`bot.start(None)` levantava erro cru da biblioteca depois de já ter carregado cogs e aberto o
servidor web. Agora falha no início com a instrução exata.

---

## Achados REFUTADOS — registrados com o motivo

A regra exige registrar o refutado: senão a próxima auditoria o reencontra, ninguém lembra
que já foi julgado, e o ciclo se repete.

| Suspeita | Por que foi refutada |
|---|---|
| `/health` sem autenticação e sem rate limit | Vinculado a `127.0.0.1` por padrão e publicado no Docker só em `127.0.0.1:8080`. Devolve `{"status":"ok"}`, sem dado sensível. É o que o `HEALTHCHECK` consome. Dano visível: nenhum. |
| Ordem dos decoradores põe os headers de segurança dentro do `auth_required` | Verificado: os headers aplicam-se às respostas de sucesso; só faltam nos corpos JSON de 401/403, em servidor local. Consequência real nula. |
| `sanitize_link` remove parâmetros com prefixo `ref`/`source`/`timestamp` | Poderia cortar `refresh=`/`source_id=`. Nenhuma fonte do catálogo usa esses parâmetros como identificador; o link continua único para dedup. Defeito teórico sem consequência. |
| Injeção de markdown pelo `<title>` de site no alerta do HTML Monitor | O bot é construído com `allowed_mentions=discord.AllowedMentions.none()`, então `@everyone`/`@here`/cargo não disparam. Sobra formatação torta, não dano. |
| `main.py` sobrescreve `state.json` no anúncio de versão, concorrendo com a varredura | A varredura mescla do disco as chaves que não lhe pertencem no save final, e a janela do anúncio é de segundos contra uma varredura de minutos. Não observado; permanece como risco residual, não achado. |
| `.dockerignore` exclui `.git`, então o anúncio de versão não funciona no contêiner | Confirmado que `get_current_hash()` devolve `None`, mas o código trata: cai no ramo `else` e apenas loga. Recurso inativo em Docker, não defeito. |

---

## Fontes de dados — catálogo v3.0 → v3.1

### O instrumento veio antes das fontes

`scripts/probe_sources.py` sonda pelo **caminho real do bot** (mesmo `get_robust_headers`,
mesmo `certifi`, mesmo `feedparser`, mesmo resolvedor de handle com as três âncoras) e
**calibra-se antes de emitir veredito**: um controle positivo que tem de passar e um negativo
que tem de reprovar. Três estados de saída — `0` passou, `1` reprovou, `2` **NÃO VERIFICOU**,
que não é aprovação.

```
[calibracao] controle positivo OK (10 entradas, mais recente 1d) | controle negativo reprovou como esperado (HTTP 404)
```

Um ajuste no meio do caminho, digno de nota: a primeira versão sondava os 29 sites
institucionais com critério de feed e produziria **29 falhas falsas**. A chave do filtro tem
de ser a chave da coisa — site do HTML Monitor mede-se por `200` + corpo não vazio.

### Reauditoria do catálogo existente

```
resumo: 96/96 saudaveis          (67 feeds + 29 sites; nenhuma morreu desde 2026-08-01)
pares conferidos=41 divergencias=0
handles no mapa nao sondados: []
```
Os 41 pares do `youtube_feed_map` conferem com a resolução **ao vivo**, e todos os títulos
batem com o handle: a correção das três âncoras de agosto continua de pé.

### O que a sonda pegou e um "está no ar?" não pegaria

| Candidata | O que parecia | O que era |
|---|---|---|
| `@nintendo` | handle oficial | canal **'koi'** (terceiro), 0 vídeos |
| `@PlayStationLatam` | conta regional da Sony | **'Conejo en Luna'**, parado há 1507 dias |
| `@SNKGLOBAL` | SNK | canal em sânscrito, 15 vídeos recentes — **passa** no critério de saúde; só o título denuncia |
| `@ObsidianEntertainment` | Obsidian | **'Isaac Watts'** (terceiro), 0 vídeos |
| `@PlayStationEurope` | canal europeu | **mesmo `channel_id`** de `@PlayStation` — publicaria em duplicado |
| `playstationblast.com.br` | 200, 25 entradas | item mais recente há **2696 dias** |
| `toucharcade.com` | 200, 100 entradas | há **497 dias** |
| `pcinvasion.com` | 200, 6 entradas | há **478 dias** |
| `rss.uol.com.br/feed/jogos.xml` | 200, 15 entradas | **nenhuma entrada tem data** — com `REQUIRE_ENTRY_DATE=1` o bot descartaria todas: fonte que parece viva e nunca posta |
| `theenemy.com.br` | site conhecido | certificado TLS inválido (hostname mismatch). Não se desliga a verificação para acomodar uma fonte |

### Volume: medido, não estimado

A sonda passou a aplicar o `should_skip_by_content` de produção e contar o que **chegaria ao
canal**:

```
CATALOGO v3.0: 67 feeds | 24h=88 | 7d=649 | media/dia=92.7
CATALOGO v3.1: 92 feeds | 24h=103 | 7d=823 | media/dia=117.6   (+24,9/dia, +27%)
```

O número mudou a decisão. As 7 fontes documentadas em agosto como "~45 posts/dia extra"
medem hoje **~70/dia** — a estimativa antiga estava conservadora, e a decisão de mantê-las
fora ficou mais justificada, agora com número. A admissão passou a ter orçamento explícito:
até ~6 itens/24 h pós-filtro entram; acima disso a fonte fica registrada **com o número**, e
promovê-la é mover uma linha.

### Resultado

**+25 fontes** (13 RSS, 12 YouTube), com ênfase em primeira parte e pt-BR — Xbox Wire em
Português, `@XboxBR`, MeuPlayStation, Nintendo Blast — e em publishers que faltavam
(Epic Games, Remedy, 11 bit, Kojima Productions, Arc System Works, Marvelous, XSEED,
tinyBuild, 505 Games).

```
resumo: 121/121 saudaveis
1. pares mapa x resolucao ao vivo: 53 conferidos, 0 divergencias
2. handles em youtube_feeds: 53 | sem entrada no mapa: 0 []
3. channel_id duplicado no mapa: 0 {}
4. entradas no mapa sem fonte correspondente: 0 []
6. @GameSpot -> 'GameSpot' | @XboxBR -> 'XBOXBR' | @EpicGamesStore -> 'Epic Games'
   @PlayStationAccess -> 'PlayStation Access' | @RemedyGames -> 'Remedy Entertainment'
   @KojimaProductions -> 'KOJIMA PRODUCTIONS' | @ArcSystemWorksU -> 'Arc System Works America'
   @marveloususa -> 'Marvelous USA' | @XSEEDGames -> 'XSEEDgames' | @505Games -> '505 Games'
   @11bitstudios -> '11 bit studios' | @tinyBuildGAMES -> 'tinyBuildGAMES'
```
Os itens 1–4 viraram guarda executável (`tests/test_catalogo_fontes.py`), calibrada contra um
catálogo-controle doente com um defeito de cada tipo.

Nota preservada: `siliconera` e `primagames` respondem **200 com conteúdo de hoje** a partir
deste desktop (IP residencial), confirmando o registro de agosto de que a remoção foi por
**bloqueio do IP do servidor**, não por fonte morta. Continuam fora — o veredito que importa é
o do IP onde o bot roda.

### 🟡 12. Lacuna de análise estática no CI (era GAP declarado — fechado)

O `flake8` do CI só reprova em erro de sintaxe e nome indefinido; nada procurava **padrão de
risco**. Acrescentado `bandit`, que **reprova a build**. Achados na primeira execução: 11
(9 baixos, 2 médios, 0 altos).

**Os 3 achados REAIS foram corrigidos, não suprimidos:** três `except Exception: pass` mudos em
`extract_entry_media_urls` (B110). Uma entrada de feed com media malformada perdia a imagem
**sem deixar rasto**. Passam a registar a causa em `log.debug` — o feed continua a ser
processado, porque falta de imagem não pode derrubar a notícia.

**Os 2 de severidade média eram falsos positivos**, e a leitura importa: o `bandit` marca a
*string* `"0.0.0.0"`, e os dois usos são o **oposto** de vincular a todas as interfaces — um
está na lista de domínios **bloqueados** e o outro numa comparação que **avisa** que o bind
ficou aberto. Marcar sem ler teria "corrigido" código que já era a proteção.

As 6 exceções são `# nosec BXXX` no ponto exato, com o motivo na linha acima — nominal e
auditável, em vez de desligar o teste inteiro no config, que é o afrouxamento criticado no
achado 3.

**Calibração (o instrumento sabe reprovar?):** arquivo-controle com
`subprocess.check_output(cmd, shell=True)` → `B602 subprocess_popen_with_shell_equals_true`,
**Severity: High**, exit 1. E o projeto, depois do trabalho: exit 0.

---

## Testes executados

```
$ .venv/Scripts/python.exe -m pytest -q
116 passed in 1.90s                      (eram 80 no início da sessão)
SUITE_EXIT=0

$ .venv/Scripts/python.exe -m flake8 . --count --select=E9,F63,F7,F82 --statistics
0
LINT_EXIT=0                              (era exit 1 no HEAD)

$ .venv/Scripts/python.exe -m pip_audit --requirement requirements.txt --strict --ignore-vuln PYSEC-2022-252
No known vulnerabilities found, 1 ignored
AUDIT_EXIT=0

$ .venv/Scripts/python.exe scripts/probe_sources.py --catalogo
resumo: 121/121 saudaveis
EXIT=0
```

**Toda guarda nova foi calibrada reintroduzindo o defeito**, e as saídas de cada calibração
estão coladas junto ao achado correspondente. Nenhuma foi aceita por sair verde na primeira
execução.

---

## Riscos residuais declarados

1. **Nada foi validado com o bot conectado ao Discord.** O bot não roda desde 2026-03-27, e
   esta sessão não o ligou. Tudo o que depende de gateway real — `on_ready` completo, o
   agendador numa reconexão de verdade, publicação real no canal — está **provado por teste
   automatizado, não por execução em produção**. Fechar isto exige subir com `.\run.ps1` e
   observar uma varredura.
2. **A primeira varredura depois desta mudança vai ser uma rajada.** 25 fontes novas em cold
   start, sem dedup, com até 10 entradas cada e janela de 7 dias. Com 2,5 s entre publicações,
   a estimativa é de dezenas de minutos dentro do teto de 125 min — mas é estimativa, não
   medição.
3. **TOCTOU de SSRF.** Entre o `getaddrinfo` da validação e a resolução do `aiohttp` há uma
   janela para DNS rebinding. Mitigado na prática porque o catálogo é controlado pelo
   operador, não pelo atacante. Fechar exigiria resolver uma vez e conectar pelo IP com
   `Host` explícito.
4. **A validação de alcance das fontes vale para o IP desta máquina.** Fonte que responde 200
   daqui pode responder 403 do IP do servidor — é exatamente o caso registrado do
   `siliconera`/`primagames`. Rodar `probe_sources.py --catalogo` de onde o bot roda antes de
   confiar no veredito lá.
5. **`MAX_ENTRIES_PER_FEED=10` com `LOOP_MINUTES=1440` continua a descartar entradas** nos
   feeds mais movimentados. A perda deixou de ser silenciosa (agora avisa), mas continua a
   existir. O valor do teto e do intervalo é decisão de produto — muda o volume que chega ao
   canal do Paulo — e por isso não foi alterado por conta própria.
6. ~~Análise estática dedicada ausente no pipeline.~~ **FECHADO ainda nesta sessão** — ver
   achado 12 abaixo. Estava escrito aqui como GAP e não passava no teste das três perguntas
   (é reversível, está no escopo do pedido, e eu sabia como fazer), então virou trabalho.

## Veredito

**VALIDADO NO ESCOPO TESTADO** — 11 achados corrigidos com guarda executável e calibrada;
catálogo em 121/121 saudáveis com +25 fontes e coerência estrutural protegida por teste;
três portões (suíte, lint, auditoria de dependências) verdes e reproduzíveis nesta máquina.

**Não validado:** comportamento com o bot conectado ao Discord (risco residual 1) e alcance
das fontes a partir do IP de produção (risco residual 4). Os dois exigem, respectivamente,
ligar o bot e rodar a sonda no servidor — nenhum é contornável a partir daqui.
