#!/usr/bin/env python3
"""
Lit un flux RSS et extrait le contenu textuel de chaque article via article_scraper.
Usage : python rss_reader.py <rss_url> [--limit N]
"""

import sys
import argparse
import xml.etree.ElementTree as ET
import urllib.request
from article_scraper import fetch_article


def fetch_rss(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_feed(xml_text: str) -> list[dict]:
    """Parse RSS 2.0 ou Atom, retourne une liste de {title, url}."""
    root = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el  = item.find("link")
        if link_el is not None and link_el.text:
            items.append({
                "title": title_el.text.strip() if title_el is not None else "(sans titre)",
                "url":   link_el.text.strip(),
            })

    # Atom
    if not items:
        for entry in root.findall(".//atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            link_el  = entry.find("atom:link", ns)
            url = link_el.get("href") if link_el is not None else None
            if url:
                items.append({
                    "title": title_el.text.strip() if title_el is not None else "(sans titre)",
                    "url":   url.strip(),
                })

    return items


def main():
    parser = argparse.ArgumentParser(description="Lit un flux RSS et affiche le contenu des articles.")
    parser.add_argument("rss_url", help="URL du flux RSS")
    parser.add_argument("--limit", type=int, default=10, help="Nombre max d'articles à traiter")
    parser.add_argument("--scrape", action="store_true", help="Affiche uniquement les URLs sans scraper")
    args = parser.parse_args()

    print(f"Récupération du flux : {args.rss_url}", file=sys.stderr)
    xml_text = fetch_rss(args.rss_url)
    items = parse_feed(xml_text)

    if not items:
        print("Aucun article trouvé dans le flux.", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        items = items[: args.limit]

    print(f"{len(items)} article(s) trouvé(s).\n", file=sys.stderr)

    for i, item in enumerate(items, 1):
        print(f"{'='*60}")
        print(f"[{i}/{len(items)}] {item['title']}")
        print(f"URL : {item['url']}")
        print(f"{'='*60}")

        if args.scrape:

            try:
                content = fetch_article(item["url"])
                if content:
                    print(content)
                else:
                    print("(contenu non extrait)")
            except Exception as e:
                print(f"Erreur lors du scraping : {e}", file=sys.stderr)

            print()


if __name__ == "__main__":
    main()