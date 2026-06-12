#!/usr/bin/env python3
"""
Affiche le contenu textuel d'un article web avec Playwright et Trafilatura.
Usage : python article_scraper.py <url>
"""

import sys
from playwright.sync_api import sync_playwright
import trafilatura

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
    return text

def main():
    if len(sys.argv) < 2:
        print("Usage : python article_scraper.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    
    print(fetch_article(url))


if __name__ == "__main__":
    main()