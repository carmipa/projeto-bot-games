#!/bin/sh

# Este script deve rodar como root no container para poder fazer chown em volumes montados
# (ex.: ./logs e ./data no host costumam ser root:root).

# Cria arquivos JSON em DATA_DIR se não existirem (evita IsADirectoryError quando o host monta dir vazio).
if [ -n "$DATA_DIR" ]; then
  mkdir -p "$DATA_DIR"
  for f in config.json state.json history.json; do
    path="$DATA_DIR/$f"
    if [ ! -e "$path" ]; then
      case "$f" in
        history.json) echo "[]" > "$path" ;;
        *)            echo "{}" > "$path" ;;
      esac
      echo "Created $path"
    fi
  done
  # Copia sources.json do projeto para data se não existir
  if [ ! -e "$DATA_DIR/sources.json" ] && [ -f /app/sources.json ]; then
    cp /app/sources.json "$DATA_DIR/sources.json"
    echo "Created $DATA_DIR/sources.json from image"
  fi
fi

mkdir -p /app/data /app/logs

# Volumes montados do host: garantir dono gamebot (sem isso, PermissionError em logs/bot.log)
if ! chown -R gamebot:gamebot /app/data /app/logs 2>/dev/null; then
  echo "entrypoint: aviso — chown em /app/data ou /app/logs falhou (volume read-only ou não-root?). O bot pode usar só console para logs."
fi

# Executa o bot como usuário não privilegiado
exec gosu gamebot python -u main.py
