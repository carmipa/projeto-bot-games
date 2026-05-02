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

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; d=os.environ.get('DATA_DIR','/app'); exit(0 if os.path.isfile(os.path.join(d,'config.json')) or os.path.isfile('/app/config.json') else 1)"

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
