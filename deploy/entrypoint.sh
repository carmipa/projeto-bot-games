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
  # sources.json NAO e mais copiado para o volume. Ele e catalogo versionado e passou a
  # ser lido de /app/sources.json (ver _DATA_FILES em utils/storage.py). A copia antiga
  # congelava o catalogo na primeira subida: fonte nova no repositorio nunca chegava ao
  # container. Um arquivo remanescente de deploys anteriores fica no volume sem uso —
  # avisar e melhor que apagar dado de quem talvez o tenha editado a mao.
  if [ -e "$DATA_DIR/sources.json" ]; then
    echo "entrypoint: aviso — $DATA_DIR/sources.json existe mas NAO e mais lido."
    echo "entrypoint:   o catalogo em uso e /app/sources.json (vem da imagem)."
    echo "entrypoint:   se voce editou esse arquivo a mao, monte-o por cima:"
    echo "entrypoint:     volumes: [ './data/sources.json:/app/sources.json:ro' ]"
  fi
fi

mkdir -p /app/data /app/logs

if ! chown -R gamebot:gamebot /app/data /app/logs 2>/dev/null; then
  echo "entrypoint: aviso — chown em /app/data ou /app/logs falhou (volume read-only ou não-root?). O bot pode usar só console para logs."
fi

exec gosu gamebot python -u main.py
