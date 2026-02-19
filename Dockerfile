FROM python:3.10-slim

# Metadata
LABEL maintainer="Paulo André Carminati"
LABEL description="GameBot Discord Bot"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Diretório de trabalho
WORKDIR /app

# Instala dependências do sistema (necessárias para certifi e SSL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements primeiro (melhor cache de layers)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia código do bot
COPY . .

# Entrypoint que cria arquivos em DATA_DIR se necessário
RUN chmod +x /app/entrypoint.sh

# Cria diretório para volume de dados
RUN mkdir -p /app/data /app/logs

# Healthcheck: config existe em DATA_DIR ou em /app
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; d=os.environ.get('DATA_DIR','/app'); exit(0 if os.path.isfile(os.path.join(d,'config.json')) or os.path.isfile('/app/config.json') else 1)"

ENTRYPOINT ["./entrypoint.sh"]
