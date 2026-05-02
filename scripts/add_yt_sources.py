"""
Script de exemplo: resolver @handles do YouTube para URLs de feed Atom (channel_id).
Edite KNOWN_IDS com os canais desejados; as fontes oficiais ficam na raiz do projeto (sources.json).
Executar a partir da raiz: python scripts/add_yt_sources.py
"""
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SOURCES = os.path.join(_ROOT, "sources.json")

# Exemplo genérico — substitua pelos IDs reais (formato UC...) antes de usar
KNOWN_IDS = {
    "@ExampleStudio": "UCxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
}


def update_sources():
    try:
        with open(_SOURCES, "r", encoding="utf-8") as f:
            data = json.load(f)

        current_yt = set(data.get("youtube_feeds", []))

        new_feeds = [
            f"https://www.youtube.com/feeds/videos.xml?channel_id={KNOWN_IDS[k]}"
            for k in KNOWN_IDS
            if not KNOWN_IDS[k].startswith("UCxxxx")
        ]
        if not new_feeds:
            print("⚠️ Defina KNOWN_IDS com channel_id reais (UC...) antes de executar.")
            sys.exit(1)

        added = 0
        for feed in new_feeds:
            if feed not in current_yt:
                data["youtube_feeds"].append(feed)
                print(f"➕ Added YouTube Feed: {feed}")
                added += 1
            else:
                print(f"⚠️ Feed already exists: {feed}")

        if added > 0:
            with open(_SOURCES, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("💾 sources.json updated.")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    update_sources()
