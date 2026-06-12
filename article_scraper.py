#!/usr/bin/env python3
"""
Affiche le contenu textuel d'un article web avec Playwright et Trafilatura.
Usage : python article_scraper.py <url>
"""

import sys
from playwright.sync_api import sync_playwright
import trafilatura

def clean_text(raw_text: str) -> str:
    """Nettoie les doublons et les lignes vides."""
    paragraphs = raw_text.split('\n')
    unique_paragraphs = []
    seen = set()
    for p in paragraphs:
        p_clean = p.strip()
        if p_clean and p_clean not in seen:
            unique_paragraphs.append(p_clean)
            seen.add(p_clean)
    return "\n".join(unique_paragraphs)

def fetch_article(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page()

        page.goto(url, wait_until="domcontentloaded")
        html = page.content()

        browser.close()

    text = trafilatura.extract(
        html,
        favor_precision=True
    )
    return clean_text(text)

def main():
    if len(sys.argv) < 2:
        print("Usage : python article_scraper.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    
    print(fetch_article(url))


if __name__ == "__main__":
    main()