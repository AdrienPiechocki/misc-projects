#!/usr/bin/env python3
"""
summarize_article.py — Récupère un article depuis une URL et résume chaque paragraphe.

Usage :
    python summarize_article.py <URL> [--ratio 0.3] [--no-fast] [--min-len N]
"""

import sys
import re
import argparse

from summarizer import summarize
from article_scraper import fetch_article


def split_paragraphs(text: str, min_len: int = 150) -> list[str]:
    """
    Découpe le texte en paragraphes en combinant plusieurs stratégies :
      1. Sauts doubles \n\n (séparateurs explicites)
      2. Sauts simples \n  (chaque ligne devient un candidat)
    Les blocs résultants sont fusionnés avec le suivant tant que leur
    longueur cumulée est inférieure à min_len, afin d'éviter de passer
    des micro-paragraphes à summarize().
    """
    # Normalise les sauts : \r\n → \n, 3+ sauts → 2
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Sépare d'abord sur les doubles sauts, puis sur les simples
    raw_blocks: list[str] = []
    for chunk in text.split("\n\n"):
        lines = [l.strip() for l in chunk.split("\n") if l.strip()]
        raw_blocks.extend(lines)

    # Fusionne les blocs trop courts avec le suivant
    merged: list[str] = []
    buf = ""
    for block in raw_blocks:
        if buf:
            buf += " " + block
        else:
            buf = block
        if len(buf) >= min_len:
            merged.append(buf)
            buf = ""
    if buf:  # dernier bloc non vidé
        if merged:
            merged[-1] += " " + buf  # colle au précédent s'il existe
        else:
            merged.append(buf)

    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape un article de presse et résume chaque paragraphe."
    )
    parser.add_argument("url", help="URL de l'article")
    parser.add_argument(
        "--ratio", type=float, default=0.3,
        help="Proportion du texte à conserver par paragraphe (défaut : 0.3)"
    )
    parser.add_argument(
        "--min-len", type=int, default=150, metavar="N",
        help="Longueur minimale d'un paragraphe (défaut : 150 caractères)"
    )
    args = parser.parse_args()

    # ── 1. Scraping ────────────────────────────────────────────────────────────
    result = fetch_article(args.url)

    if result is None:
        print("Impossible de récupérer le contenu de l'article.", file=sys.stderr)
        sys.exit(1)

    # ── 2. Découpe en paragraphes ──────────────────────────────────────────────
    paragraphs = split_paragraphs(result, min_len=args.min_len)

    if not paragraphs:
        print("Aucun paragraphe suffisamment long trouvé.", file=sys.stderr)
        sys.exit(1)

    print(f"── {len(paragraphs)} paragraphe(s) détecté(s)\n")
    sep = "─" * 68

    # ── 3. Résumé par paragraphe ───────────────────────────────────────────────
    for i, para in enumerate(paragraphs, 1):
        resume = summarize(para, ratio=args.ratio, lang="french")
        print(resume if resume.strip() else para)
        print()


if __name__ == "__main__":
    main()