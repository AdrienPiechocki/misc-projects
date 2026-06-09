#!/usr/bin/env python3
"""
linkedin_scraper.py — Recherche d'emploi LinkedIn SANS connexion
Utilise l'API publique guest de LinkedIn + httpx + BeautifulSoup.
Aucune session, aucun navigateur requis.

Usage:
    python linkedin_scraper.py
    python linkedin_scraper.py --config mon_profil.yaml
    python linkedin_scraper.py --debug     # sauvegarde le HTML brut
"""

import argparse
import csv
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx
import yaml
from bs4 import BeautifulSoup

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Constantes ─────────────────────────────────────────────────────────────
BASE_URL = "https://www.linkedin.com"

# Endpoint public — renvoie du HTML de cartes d'offres (pagination par 25)
GUEST_SEARCH_API = f"{BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search"
# Page d'une offre individuelle (publique)
JOB_PAGE_URL = f"{BASE_URL}/jobs/view/{{job_id}}/"

FILTER_MAP = {
    "job_type":         {"full_time": "F", "part_time": "P", "contract": "C", "temporary": "T", "internship": "I"},
    "experience_level": {"internship": "1", "entry_level": "2", "associate": "3", "mid_senior_level": "4", "director": "5"},
    "work_type":        {"on_site": "1", "remote": "2", "hybrid": "3"},
    "date_posted":      {"past_24h": "r86400", "past_week": "r604800", "past_month": "r2592000"},
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.linkedin.com/jobs/search/",
}


# ─── Modèle de données ───────────────────────────────────────────────────────
@dataclass
class Job:
    title: str = ""
    company: str = ""
    location: str = ""
    work_type: str = ""
    date_posted: str = ""
    url: str = ""
    job_id: str = ""
    description: str = ""
    skills_found: list = field(default_factory=list)
    score: int = 0
    search_keyword: str = ""


# ─── Config ──────────────────────────────────────────────────────────────────
def load_config(path: str = "linkedin_config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── Client HTTP réutilisable ─────────────────────────────────────────────────
def make_client() -> httpx.Client:
    return httpx.Client(
        headers=HEADERS,
        follow_redirects=True,
        timeout=20,
        # Pas de vérif SSL agressive
        verify=True,
    )


# ─── Délais anti-détection ───────────────────────────────────────────────────
def sleep_random(range_: list):
    time.sleep(random.uniform(range_[0], range_[1]))


# ─── Construction des paramètres de recherche ────────────────────────────────
def build_params(keyword: str, location: str, filters: dict, start: int = 0) -> dict:
    params: dict = {
        "keywords": keyword,
        "location": location,
        "start": start,
        "pageNum": start // 25,
    }
    if filters.get("job_type"):
        params["f_JT"] = FILTER_MAP["job_type"].get(filters["job_type"], "")
    if filters.get("experience_level"):
        params["f_E"] = FILTER_MAP["experience_level"].get(filters["experience_level"], "")
    if filters.get("work_type"):
        params["f_WT"] = FILTER_MAP["work_type"].get(filters["work_type"], "")
    if filters.get("date_posted"):
        params["f_TPR"] = FILTER_MAP["date_posted"].get(filters["date_posted"], "")
    return {k: v for k, v in params.items() if v != ""}


# ─── Parsing d'une liste de cartes HTML ──────────────────────────────────────
def parse_cards(html: str, debug_path: Optional[Path] = None) -> list[Job]:
    if debug_path:
        debug_path.write_text(html, encoding="utf-8")
        log.info(f"  📄 HTML brut sauvegardé: {debug_path}")

    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []

    # Les cartes sont des <li> contenant un lien vers /jobs/view/
    cards = soup.find_all("li")
    log.debug(f"  {len(cards)} <li> trouvés")

    for card in cards:
        job = parse_one_card(card)
        if job:
            jobs.append(job)

    return jobs


def parse_one_card(card) -> Optional[Job]:
    job = Job()

    # ── ID + URL depuis data-entity-urn ou le lien principal ──
    div = card.find("div", attrs={"data-entity-urn": re.compile(r"jobPosting")})
    if div:
        urn = div.get("data-entity-urn", "")
        m = re.search(r"jobPosting:(\d+)", urn)
        if m:
            job.job_id = m.group(1)

    # Lien principal (base-card__full-link couvre toute la carte)
    link = card.find("a", class_="base-card__full-link")
    if not link:
        # fallback: n'importe quel lien vers /jobs/view/
        link = card.find("a", href=re.compile(r"/jobs/view/"))
    if not link:
        return None

    href = link.get("href", "")
    if not job.job_id:
        m = re.search(r"/jobs/view/[^/]*-(\d+)", href)
        if m:
            job.job_id = m.group(1)
    if job.job_id:
        job.url = f"{BASE_URL}/jobs/view/{job.job_id}/"
    else:
        job.url = href.split("?")[0]

    # ── Titre ──
    title_tag = card.find("h3", class_="base-search-card__title")
    if title_tag:
        job.title = title_tag.get_text(strip=True)
    else:
        # fallback: span sr-only dans le lien principal
        sr = link.find("span", class_="sr-only")
        job.title = sr.get_text(strip=True) if sr else link.get_text(strip=True)

    if not job.title:
        return None

    # ── Entreprise ──
    subtitle = card.find("h4", class_="base-search-card__subtitle")
    if subtitle:
        job.company = subtitle.get_text(strip=True)
    else:
        a_company = card.find("a", href=re.compile(r"/company/"))
        if a_company:
            job.company = a_company.get_text(strip=True)

    # ── Localisation ──
    loc_tag = card.find("span", class_="job-search-card__location")
    if loc_tag:
        job.location = loc_tag.get_text(strip=True)

    # ── Date ──
    time_tag = card.find("time")
    if time_tag:
        job.date_posted = time_tag.get("datetime", "") or time_tag.get_text(strip=True)

    return job


# ─── Récupération de la description d'une offre ──────────────────────────────
def fetch_description(client: httpx.Client, job: Job, delay_range: list) -> Job:
    """Scrape la page publique de l'offre pour récupérer la description."""
    try:
        r = client.get(job.url, timeout=15)
        sleep_random(delay_range)

        if r.status_code != 200:
            log.debug(f"  HTTP {r.status_code} pour {job.url}")
            return job

        soup = BeautifulSoup(r.text, "html.parser")

        # Description
        desc_tag = soup.find("div", class_=re.compile(r"description|job-details|show-more"))
        if not desc_tag:
            desc_tag = soup.find("section", class_=re.compile(r"description"))
        if desc_tag:
            job.description = desc_tag.get_text(separator=" ", strip=True)[:3000]

        # Work type (télétravail / hybrid / on-site) depuis les métadonnées
        criteria = soup.find_all("span", class_=re.compile(r"criteria|workplace"))
        for c in criteria:
            text = c.get_text(strip=True)
            if any(w in text.lower() for w in ["remote", "hybrid", "on-site", "télétravail", "hybride"]):
                job.work_type = text
                break

        # Fallback: chercher dans tout le texte de la page
        if not job.work_type:
            full_text = soup.get_text()
            for term in ["Télétravail", "Hybride", "Sur site", "Remote", "Hybrid", "On-site"]:
                if term.lower() in full_text.lower():
                    job.work_type = term
                    break

    except Exception as e:
        log.debug(f"  Erreur description {job.url}: {e}")

    return job


# ─── Scoring ─────────────────────────────────────────────────────────────────
def skill_matches(skill: str, text: str) -> bool:
    """Vérifie que le skill est un mot entier, pas une sous-chaîne.
    Ex: "Unity" ne matche pas "opportunity", "Git" ne matche pas "digital".
    Utilise des lookaround plutôt que \b pour gérer C#, C++, etc.
    """
    escaped = re.escape(skill.lower())
    pattern = r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])"
    return bool(re.search(pattern, text))


def score_job(job: Job, required_skills: list, bonus_skills: list) -> Job:
    text = (job.title + " " + job.description).lower()
    found, score = [], 0
    for skill in required_skills:
        if skill_matches(skill, text):
            found.append(skill)
            score += 2
    for skill in bonus_skills:
        if skill_matches(skill, text):
            found.append(skill)
            score += 1
    job.skills_found = found
    job.score = score
    return job


def should_exclude(job: Job, exclude_keywords: list) -> bool:
    return any(skill_matches(kw, job.title.lower()) for kw in exclude_keywords)


# ─── Recherche pour un mot-clé ───────────────────────────────────────────────
def search_keyword(
    client: httpx.Client,
    keyword: str,
    config: dict,
    debug: bool = False,
) -> list[Job]:
    search_cfg = config["search"]
    filters = search_cfg.get("filters", {})
    delays = config.get("delays", {"between_jobs": [1, 2.5], "between_pages": [2, 4], "between_searches": [4, 8]})
    max_jobs = search_cfg.get("max_jobs_per_keyword", 25)
    max_per_company = search_cfg.get("max_jobs_per_company", 2)
    exclude = config.get("exclude_keywords", [])
    required_skills = config.get("required_skills", [])
    bonus_skills = config.get("bonus_skills", [])

    log.info(f'🔍 Recherche: "{keyword}" à {search_cfg["location"]}')

    all_jobs: list[Job] = []
    seen_ids: set[str] = set()
    start = 0
    first_page = True

    while len(all_jobs) < max_jobs:
        params = build_params(keyword, search_cfg["location"], filters, start)

        try:
            r = client.get(GUEST_SEARCH_API, params=params)
        except Exception as e:
            log.error(f"  Erreur réseau: {e}")
            break

        if r.status_code == 429:
            log.warning("  ⚠️  Rate limit (429) — pause 30s")
            time.sleep(30)
            continue
        if r.status_code != 200:
            log.warning(f"  HTTP {r.status_code} — arrêt pour ce mot-clé")
            break

        debug_path = Path(f"debug_page_{start}.html") if (debug and first_page) else None
        cards = parse_cards(r.text, debug_path=debug_path)
        first_page = False

        if not cards:
            log.debug("  Plus de résultats")
            break

        for job in cards:
            if job.job_id in seen_ids:
                continue
            seen_ids.add(job.job_id)

            if should_exclude(job, exclude):
                log.debug(f"  ⏭  Exclus: {job.title}")
                continue

            # Limiter le nombre d'offres par entreprise
            company_key = job.company.strip().lower()
            company_count = sum(1 for j in all_jobs if j.company.strip().lower() == company_key)
            if max_per_company and company_count >= max_per_company:
                log.debug(f"  ⏭  Limite entreprise ({max_per_company}): {job.company}")
                continue

            job.search_keyword = keyword

            # Récupérer description pour le scoring
            job = fetch_description(client, job, delays["between_jobs"])
            job = score_job(job, required_skills, bonus_skills)

            all_jobs.append(job)
            log.info(
                f"  ✅ [{len(all_jobs):2d}] {job.title} @ {job.company}"
                f"  (score: {job.score}"
                + (f", skills: {', '.join(job.skills_found)}" if job.skills_found else "")
                + ")"
            )

            if len(all_jobs) >= max_jobs:
                break

        start += 25
        sleep_random(delays["between_pages"])

    log.info(f"  → {len(all_jobs)} offres collectées pour «{keyword}»")
    return all_jobs


# ─── Export ──────────────────────────────────────────────────────────────────
def export_results(jobs: list[Job], config: dict, output_dir: Path) -> list[Job]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_cfg = config.get("output", {})
    min_score = output_cfg.get("min_score", 0)

    filtered = sorted(
        [j for j in jobs if j.score >= min_score],
        key=lambda j: j.score,
        reverse=True,
    )

    csv_path = output_dir / output_cfg.get("csv_file", "jobs_output.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "score", "title", "company", "location", "work_type",
            "date_posted", "search_keyword", "skills_found", "job_id", "url", "description",
        ])
        writer.writeheader()
        for job in filtered:
            row = asdict(job)
            row["skills_found"] = ", ".join(row["skills_found"])
            row["description"] = row["description"][:500].replace("\n", " ")
            writer.writerow(row)
    log.info(f"📄 CSV: {csv_path}  ({len(filtered)} offres)")

    json_path = output_dir / output_cfg.get("json_file", "jobs_output.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([asdict(j) for j in filtered], f, ensure_ascii=False, indent=2)
    log.info(f"📄 JSON: {json_path}")

    return filtered


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="LinkedIn Job Scraper (sans login)")
    parser.add_argument("--config", default="linkedin_config.yaml")
    parser.add_argument("--debug", action="store_true", help="Sauvegarde le HTML brut de la 1ère page")
    parser.add_argument("--output", default="jobs", help="Dossier de sortie")
    args = parser.parse_args()

    config = load_config(args.config)
    delays = config.get("delays", {})
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    all_jobs: list[Job] = []
    keywords = config["search"]["keywords"]

    with make_client() as client:
        for i, keyword in enumerate(keywords):
            jobs = search_keyword(client, keyword, config, debug=args.debug)
            all_jobs.extend(jobs)
            if i < len(keywords) - 1:
                log.info("⏳ Pause entre recherches...")
                sleep_random(delays.get("between_searches", [4, 8]))

    # Dédoublonnage global
    seen: set[str] = set()
    unique: list[Job] = []
    for job in all_jobs:
        key = job.job_id or job.url
        if key not in seen:
            seen.add(key)
            unique.append(job)

    log.info(f"\n📊 Total: {len(unique)} offres uniques")
    filtered = export_results(unique, config, output)

    log.info("\n🏆 Top 5 offres:")
    for job in filtered[:5]:
        log.info(
            f"  [{job.score:2d}] {job.title} @ {job.company} — {job.location}\n"
            f"       {job.url}"
        )


if __name__ == "__main__":
    main()