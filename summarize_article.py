#!/usr/bin/env python3
import sys
import argparse
from article_scraper import fetch_article
from summarizer import summarize

def process_grouped_sections(url: str, ratio: float, group_size: int = 3):
    print(f"--- Récupération : {url} ---")
    raw_text = fetch_article(url)
    
    if not raw_text:
        return

    # Découpage simple par paragraphe
    paragraphs = [p.strip() for p in raw_text.split('\n')]
    
    # Fusion des paragraphes par groupes
    grouped_sections = []
    for i in range(0, len(paragraphs), group_size):
        group = " ".join(paragraphs[i:i + group_size])
        grouped_sections.append(group)

    print(f"--- Résumé par groupes de {group_size} paragraphes (Ratio : {ratio}) ---\n")
    for i, section in enumerate(grouped_sections):
        # On résume le groupe
        summary = summarize(section, ratio=ratio, lang="french")
        print(summary.strip())
        print("\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Résume par groupes de paragraphes.")
    parser.add_argument("url", help="URL de l'article")
    parser.add_argument("-r", "--ratio", type=float, default=0.3, help="Ratio")
    parser.add_argument("-g", "--group", type=int, default=1, help="Nb de paragraphes par groupe")
    
    args = parser.parse_args()
    process_grouped_sections(args.url, args.ratio, args.group)