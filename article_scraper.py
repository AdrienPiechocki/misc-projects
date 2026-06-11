#!/usr/bin/env python3
"""
Affiche le contenu textuel d'un article web avec Playwright.
Usage : python fetch_body.py <url> [html|text]
"""

import sys
from playwright.sync_api import sync_playwright

CONTENT_SELECTORS = [
    "article",
    '[role="main"] .content',
    "main .content",
    ".article-news .content",
    ".article-content",
    ".article__content",
    ".article-body",
    "#article-body",
    ".post-content",
    ".entry-content",
    ".content-article",
    "#main-content .content",
    '[role="main"]',
    "main",
    "#main-content",
]

NOISE_SELECTORS = [
    "nav", "header", "footer",
    '[class*="author"]',
    '[class*="meta"]',
    '[class*="breadcrumb"]',
    '[class*="reading-time"]', '[class*="read-time"]',
    "figure", "figcaption", "picture",
    '[class*="figure"]', '[class*="caption"]',
    '[class*="image"]', '[class*="photo"]',
    ".tags", ".related", ".share", ".social", ".comments",
    ".newsletter", ".ad", ".ads", ".pub",
    ".actions", ".more",
    "aside",
    '[class*="related"]', '[class*="share"]',
    '[class*="social"]', '[class*="newsletter"]',
    '[class*="sponsor"]', '[class*="pub"]',
    '[class*="tag"]',
    '[class*="suggestion"]', '[class*="recommend"]',
]

# Patterns à supprimer — uniquement sur des éléments inline courts (pas les <p>, <div>, <span> génériques)
NOISE_TEXT_PATTERNS = [
    r"comprendre cette valeur",
    r"lire aussi",
    r"voir aussi",
    r"en savoir plus",
    r"à lire aussi",
]

# Balises candidates pour la suppression par texte
# On exclut volontairement <span> et <p> pour ne pas avaler du contenu légitime
NOISE_TEXT_TAGS = "a, button, small, sup, aside"


def fetch_article(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"[*] Chargement de : {url}", file=sys.stderr)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # 1. Supprimer les blocs parasites structurels
        for sel in NOISE_SELECTORS:
            safe_sel = sel.replace("'", "\\'")
            page.evaluate(f"document.querySelectorAll('{safe_sel}').forEach(el => el.remove())")

        # Supprimer les spans de texte masqué visuellement (screen-reader only)
        # Ex: .ico2-hidden (franceinfo), .sr-only, .visually-hidden, .hidden-text...
        page.evaluate("""
            document.querySelectorAll('span').forEach(el => {
                const cls = el.className || '';
                if (/hidden|sr-only|visually.?hidden|screen.?reader/i.test(cls)) {
                    el.remove();
                }
            });
        """)

        # 2. Supprimer les éléments inline dont le texte normalisé correspond à un pattern parasite
        noise_patterns_js = str(NOISE_TEXT_PATTERNS)
        page.evaluate(f"""
            const patterns = {noise_patterns_js}.map(p => new RegExp('^' + p + '$', 'i'));
            document.querySelectorAll('{NOISE_TEXT_TAGS}').forEach(el => {{
                const text = el.textContent
                    .replace(/[\\u00A0\\u200B\\u200C\\u200D\\uFEFF]/g, ' ')
                    .replace(/\\s+/g, ' ')
                    .trim();
                if (patterns.some(re => re.test(text))) {{
                    el.remove();
                }}
            }});
        """)

        # 3. Chercher le sélecteur de contenu le plus précis
        selected = None
        for sel in CONTENT_SELECTORS:
            if page.locator(sel).count() > 0:
                selected = sel
                print(f"[*] Sélecteur utilisé : {sel}", file=sys.stderr)
                break

        if selected:
            el = page.locator(selected).first
            content = el.inner_text()
        else:
            print("[!] Fallback sur <body>", file=sys.stderr)
            content = page.inner_text("body")

        browser.close()

        # 4. Nettoyer les lignes vides multiples
        lines = content.splitlines()
        cleaned = []
        prev_blank = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not prev_blank:
                    cleaned.append("")
                prev_blank = True
            else:
                cleaned.append(stripped)
                prev_blank = False

        return "\n".join(cleaned).strip()


def main():
    if len(sys.argv) < 2:
        print("Usage : python fetch_body.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    
    print(fetch_article(url))


if __name__ == "__main__":
    main()