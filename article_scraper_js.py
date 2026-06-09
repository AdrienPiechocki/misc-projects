#!/usr/bin/env python3
"""
article_scraper_js.py — Extrait le contenu d'un article de presse
depuis des pages rendues côté client (React, Vue, Angular…).

Stratégie en cascade :
  1. newspaper3k  (rapide, pas de JS)
  2. Playwright + Chromium  (JS complet, attend le rendu)
  3. BeautifulSoup sur le HTML récupéré par Playwright (fallback texte)

Dépendances :
    pip install playwright newspaper3k beautifulsoup4 lxml
    playwright install chromium

Usage :
    python article_scraper_js.py <URL> [options]

Options :
    --json          Sortie JSON
    --timeout N     Délai d'attente réseau en secondes (défaut : 15)
    --wait-for SEL  Sélecteur CSS à attendre avant extraction
                    ex: --wait-for "article.post-content"
    --no-fast       Désactive newspaper3k (force Playwright)
    --screenshot    Sauvegarde une capture d'écran (page.png)
    --debug         Affiche le HTML brut récupéré par Playwright
"""

import sys
import json
import textwrap
import argparse
from dataclasses import dataclass, field
from typing import Optional

# ── Dépendances optionnelles ───────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    print("[WARN] playwright non installé. Lancez : pip install playwright && playwright install chromium",
          file=sys.stderr)

try:
    from newspaper import Article as NewspaperArticle
    HAS_NEWSPAPER = True
except ImportError:
    HAS_NEWSPAPER = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ── Structure de résultat ──────────────────────────────────────────────────────
@dataclass
class ArticleResult:
    url: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    publish_date: Optional[str] = None
    text: str = ""
    summary: str = ""
    top_image: str = ""
    source: str = ""

    def display(self) -> None:
        sep = "─" * 72
        print(sep)
        print(f"  TITRE   : {self.title or '(non détecté)'}")
        print(f"  AUTEURS : {', '.join(self.authors) or '(non détectés)'}")
        print(f"  DATE    : {self.publish_date or '(non détectée)'}")
        print(f"  SOURCE  : {self.source}")
        if self.top_image:
            print(f"  IMAGE   : {self.top_image}")
        print(sep)
        if self.summary:
            print("\n── Résumé automatique ──")
            print(textwrap.fill(self.summary, width=72))
        print("\n── Contenu complet ──")
        print(self.text or "(contenu vide)")
        print(sep)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "authors": self.authors,
            "publish_date": self.publish_date,
            "text": self.text,
            "summary": self.summary,
            "top_image": self.top_image,
        }


# ── Extracteur 1 : newspaper3k (rapide, sans JS) ──────────────────────────────
def extract_with_newspaper(url: str) -> Optional[ArticleResult]:
    if not HAS_NEWSPAPER:
        return None
    try:
        art = NewspaperArticle(url, language="fr")
        art.download()
        art.parse()
        try:
            art.nlp()
        except Exception:
            pass

        if not art.text.strip():
            return None

        return ArticleResult(
            url=url,
            title=art.title or "",
            authors=art.authors or [],
            publish_date=str(art.publish_date) if art.publish_date else None,
            text=art.text.strip(),
            summary=getattr(art, "summary", "") or "",
            top_image=art.top_image or "",
            source="newspaper3k",
        )
    except Exception as e:
        print(f"[newspaper3k] échec : {e}", file=sys.stderr)
        return None


# ── Extracteur 2 : Playwright ─────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

_ARTICLE_SELECTORS = [
    # Sémantique HTML5
    "article",
    "main",
    # Microdata / schema.org
    "[itemprop='articleBody']",
    "[itemprop='description']",
    # Classes génériques anglophones
    ".article-body", ".article__body", ".article-content", ".article__content",
    ".story-body", ".story-content",
    ".post-content", ".post__content", ".post-body",
    ".entry-content", ".entry-body",
    "#article-body", "#article-content",
    "#main-content", "#content",
    # Classes francophones / CMS divers
    ".news-content", ".news-body", ".news__content",
    ".contenu", ".texte-article", ".corps-article",
    ".actualite-content", ".actu-content",
    # Patterns div génériques avec beaucoup de texte
    "div.content", "div.body", "div.text",
    ".page-content", ".single-content",
    ".td-post-content",   # TagDiv (WordPress)
    ".jeg_post_content",  # JNews
    ".mvp-content-main",  # MVP theme
]

_NOISE_TAGS = {
    "script", "style", "nav", "header", "footer", "aside",
    "figure", "figcaption", "form", "button", "iframe", "noscript",
    "menu", "dialog", "template",
}

# Classes/ids de bruit courants (commentaires, sidebar, pub…)
_NOISE_SELECTORS = [
    ".comments", "#comments", ".comment-section",
    ".sidebar", "#sidebar", ".widget",
    ".advertisement", ".pub", ".banner",
    ".social-share", ".share-buttons",
    ".related-articles", ".related-posts",
    ".newsletter", ".subscription",
    ".breadcrumb", ".pagination",
    "[aria-label='publicité']",
]


def _node_text(node) -> str:
    """Extrait le texte d'un nœud : d'abord via <p>, sinon texte brut du nœud."""
    paragraphs = node.find_all("p")
    if paragraphs:
        return "\n\n".join(
            p.get_text(separator=" ", strip=True)
            for p in paragraphs
            if p.get_text(strip=True)
        )
    # Pas de <p> → texte brut direct (sites maison, CMS exotiques)
    return node.get_text(separator="\n", strip=True)


def _score_density(text: str) -> float:
    """Score heuristique : longueur × ratio mots longs (filtre le bruit nav)."""
    if not text:
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    long_words = sum(1 for w in words if len(w) > 4)
    return len(text) * (long_words / len(words))


def _extract_from_html(html: str, url: str) -> Optional[ArticleResult]:
    """Parse le HTML déjà rendu avec BeautifulSoup."""
    if not HAS_BS4:
        return None

    soup = BeautifulSoup(html, "lxml")

    # Supprime les balises bruyantes
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()
    for sel in _NOISE_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()

    # Titre
    title = ""
    for sel in ["h1", "meta[property='og:title']", "title"]:
        node = soup.select_one(sel)
        if node:
            title = node.get("content", "") or node.get_text(strip=True)
            if title:
                break

    # --- Corps : essaie les sélecteurs dans l'ordre, garde le meilleur score ---
    best_text = ""
    best_score = 0.0

    for sel in _ARTICLE_SELECTORS:
        node = soup.select_one(sel)
        if not node:
            continue
        candidate = _node_text(node)
        score = _score_density(candidate)
        if score > best_score:
            best_score = score
            best_text = candidate

    # Fallback densité : si aucun sélecteur n'a rien donné (> seuil minimal),
    # on parcourt tous les <div> et on garde celui au score le plus élevé.
    if best_score < 500:
        for div in soup.find_all("div"):
            candidate = _node_text(div)
            score = _score_density(candidate)
            if score > best_score:
                best_score = score
                best_text = candidate

    # Dernier recours : tous les <p> de la page sans filtre de longueur
    if not best_text.strip():
        best_text = "\n\n".join(
            p.get_text(separator=" ", strip=True)
            for p in soup.find_all("p")
            if p.get_text(strip=True)
        )

    if not best_text.strip():
        return None

    og_image = soup.select_one("meta[property='og:image']")
    top_image = og_image.get("content", "") if og_image else ""

    return ArticleResult(
        url=url,
        title=title,
        text=best_text.strip(),
        top_image=top_image,
        source="playwright+beautifulsoup4",
    )


def extract_with_playwright(
    url: str,
    timeout_s: int = 15,
    wait_for_selector: Optional[str] = None,
    screenshot_path: Optional[str] = None,
    debug: bool = False,
) -> Optional[ArticleResult]:
    if not HAS_PLAYWRIGHT:
        return None

    timeout_ms = timeout_s * 1000

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",  # évite les crash en mémoire partagée limitée
                    "--disable-blink-features=AutomationControlled",  # réduit la détection bot
                ],
            )

            context = browser.new_context(
                extra_http_headers=_HEADERS,
                java_script_enabled=True,
                accept_downloads=False,
                viewport={"width": 1280, "height": 900},
            )

            # Bloque les ressources inutiles pour aller plus vite
            def _block_heavy(route):
                if route.request.resource_type in {"image", "media", "font"}:
                    route.abort()
                else:
                    route.continue_()

            page = context.new_page()
            page.route("**/*", _block_heavy)

            # Navigation principale
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            # Attente du rendu JS
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
                except PWTimeout:
                    print(f"[playwright] sélecteur '{wait_for_selector}' non trouvé dans le délai imparti.",
                          file=sys.stderr)
            else:
                # Attend que le réseau soit idle (pour les SPAs)
                try:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                except PWTimeout:
                    pass  # on continue avec ce qu'on a

            # Capture d'écran optionnelle
            if screenshot_path:
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"[playwright] capture sauvegardée → {screenshot_path}", file=sys.stderr)

            html = page.content()

            if debug:
                print("── HTML brut (premiers 3000 caractères) ──")
                print(html[:3000])

            # newspaper3k peut re-parser le HTML déjà rendu
            result = None
            if HAS_NEWSPAPER:
                try:
                    art = NewspaperArticle(url, language="fr")
                    art.set_html(html)
                    art.parse()
                    try:
                        art.nlp()
                    except Exception:
                        pass
                    if art.text.strip():
                        result = ArticleResult(
                            url=url,
                            title=art.title or "",
                            authors=art.authors or [],
                            publish_date=str(art.publish_date) if art.publish_date else None,
                            text=art.text.strip(),
                            summary=getattr(art, "summary", "") or "",
                            top_image=art.top_image or "",
                            source="playwright+newspaper3k",
                        )
                except Exception as e:
                    print(f"[playwright+newspaper3k] échec : {e}", file=sys.stderr)

            # Fallback BeautifulSoup sur le HTML rendu
            if result is None:
                result = _extract_from_html(html, url)

            browser.close()
            return result

    except Exception as e:
        print(f"[playwright] erreur fatale : {e}", file=sys.stderr)
        return None


# ── Orchestrateur ──────────────────────────────────────────────────────────────
def scrape(
    url: str,
    output_json: bool = False,
    timeout_s: int = 15,
    wait_for_selector: Optional[str] = None,
    skip_fast: bool = False,
    screenshot_path: Optional[str] = None,
    debug: bool = False,
) -> Optional[ArticleResult]:
    """
    Tente d'extraire l'article dans l'ordre :
      1. newspaper3k (sauf si skip_fast=True)
      2. Playwright + Chromium
    Retourne un ArticleResult ou None.
    """
    result = None

    if not skip_fast:
        result = extract_with_newspaper(url)

    if result is None:
        # print("[info] Lancement de Playwright pour le rendu JS…", file=sys.stderr)
        result = extract_with_playwright(
            url,
            timeout_s=timeout_s,
            wait_for_selector=wait_for_selector,
            screenshot_path=screenshot_path,
            debug=debug,
        )

    if result is None:
        print("Impossible d'extraire le contenu de l'article.", file=sys.stderr)
        return None

    if output_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        result.display()

    return result


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrait le contenu d'un article de presse (avec support JS côté client)."
    )
    parser.add_argument("url", help="URL de l'article")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Sortie JSON")
    parser.add_argument("--timeout", type=int, default=15, metavar="N",
                        help="Délai réseau en secondes (défaut : 15)")
    parser.add_argument("--wait-for", dest="wait_for", metavar="SELECTOR",
                        help="Sélecteur CSS à attendre avant extraction")
    parser.add_argument("--no-fast", action="store_true",
                        help="Désactive newspaper3k, force Playwright d'emblée")
    parser.add_argument("--screenshot", metavar="FICHIER",
                        help="Chemin de la capture d'écran (ex: page.png)")
    parser.add_argument("--debug", action="store_true",
                        help="Affiche le HTML brut récupéré par Playwright")
    args = parser.parse_args()

    scrape(
        url=args.url,
        output_json=args.json_output,
        timeout_s=args.timeout,
        wait_for_selector=args.wait_for,
        skip_fast=args.no_fast,
        screenshot_path=args.screenshot,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()