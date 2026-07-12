FROM python:3.10-slim

# Metadata
LABEL maintainer="Paulo André Carminati"
LABEL description="GameBot Discord Bot"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/deploy/entrypoint.sh

RUN groupadd -r gamebot && useradd -r -g gamebot gamebot \
    && mkdir -p /app/data /app/logs \
    && chown -R gamebot:gamebot /app

# Liveness real: o event loop/web server responde em /health (rota sem auth).
# Prova que o processo está vivo e o loop asyncio não travou, ao contrário do antigo
# check que só verificava a existência de config.json (passava até com o bot morto).
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).status==200 else 1)"

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
