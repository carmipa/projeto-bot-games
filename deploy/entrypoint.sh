#!/bin/sh

# Este script deve rodar como root no container para poder fazer chown em volumes montados
# (ex.: ./logs e ./data no host costumam ser root:root).

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
  if [ ! -e "$DATA_DIR/sources.json" ] && [ -f /app/sources.json ]; then
    cp /app/sources.json "$DATA_DIR/sources.json"
    echo "Created $DATA_DIR/sources.json from image"
  fi
fi

mkdir -p /app/data /app/logs

if ! chown -R gamebot:gamebot /app/data /app/logs 2>/dev/null; then
  echo "entrypoint: aviso — chown em /app/data ou /app/logs falhou (volume read-only ou não-root?). O bot pode usar só console para logs."
fi

exec gosu gamebot python -u main.py
