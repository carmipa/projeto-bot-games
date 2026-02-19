#!/bin/sh
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
exec python -u main.py
