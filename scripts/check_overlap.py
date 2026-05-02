import json
import os

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SOURCES = os.path.join(_ROOT, "sources.json")

with open(_SOURCES, "r", encoding="utf-8") as f:
    data = json.load(f)

rss_domains = set()
for url in data['rss_feeds']:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace('www.', '')
    rss_domains.add(domain)

html_urls = data['official_sites_reference_(not_rss)']
overlapping = []

for url in html_urls:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace('www.', '')
    if domain in rss_domains:
        overlapping.append(url)

if overlapping:
    print("Overlapping sources (both RSS and HTML):")
    for u in overlapping:
        print(f"  - {u}")
else:
    print("No overlapping sources found.")
