import requests
import re
import math
import time
from datetime import datetime, timedelta
import random
import sqlite3
import html
import argparse
import csv
import json
import translator
from pathlib import Path
import scrape_steam_tags

STEAM_SEARCH = "https://store.steampowered.com/search/results/"
STEAM_APP_DETAILS = "https://store.steampowered.com/api/appdetails"

# ----------------------------
# ARGS
# ----------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="SteamDB Trending Engine — detects recent trending games on Steam.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--days", "-d", type=int, default=7, metavar="N",
        help="Number of days back for the search window")

    parser.add_argument("--top", "-t", type=int, default=100, metavar="N",
        help="Number of released games to display")

    parser.add_argument("--top-upcoming", type=int, default=100, metavar="N",
        help="Number of upcoming games to display in their dedicated section")

    parser.add_argument("--min-reviews", type=int, default=1, metavar="N",
        help="Minimum number of reviews required to include a released game")

    parser.add_argument("--filters", nargs="+",
        default=["popularnew", "topsellers", "comingsoon", "upcoming"],
        choices=["popularnew", "topsellers", "comingsoon", "upcoming", "mostplayed"],
        metavar="FILTER",
        help="Steam filters to use")

    parser.add_argument("--pages", type=int, default=6, metavar="N",
        help="Number of pages to scrape per filter (50 apps/page)")

    parser.add_argument("--rate-min", type=float, default=0.6, metavar="SEC",
        help="Minimum delay between requests (seconds)")

    parser.add_argument("--rate-max", type=float, default=1.8, metavar="SEC",
        help="Maximum delay between requests (seconds)")

    parser.add_argument("--db", default="steam_cache.db", metavar="FILE",
        help="Path to the SQLite cache database")

    parser.add_argument("--no-cache", action="store_true",
        help="Ignore cache and force reloading from the API")

    parser.add_argument("--clear-cache", action="store_true",
        help="Clear cache before running scraping")

    parser.add_argument("--output", "-o", metavar="FILE.csv",
        help="Export results to a CSV file (both sections)")

    parser.add_argument("--lang", "-l", default="en", metavar="CC",
        help="Language code for Steam descriptions (e.g., fr, en, de)")

    parser.add_argument("--quiet", "-q", action="store_true",
        help="Show only the final ranking")

    parser.add_argument("--verbose", "-v", action="store_true",
        help="Show details for each processed app")

    parser.add_argument("--tags-include", nargs="+", metavar="TAG", default=[],
        help="Include only games that have ALL of these tags")

    parser.add_argument("--tags-exclude", nargs="+", metavar="TAG", default=[],
        help="Exclude games that have AT LEAST ONE of these tags")

    parser.add_argument("--list-tags", action="store_true",
        help="Display all tags found in the results")

    return parser.parse_args()


# ----------------------------
# CACHE (SQLite)
# ----------------------------

def init_db(db_path, clear=False):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if clear:
        cursor.execute("DROP TABLE IF EXISTS app_cache")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_cache (
            appid TEXT PRIMARY KEY,
            data TEXT,
            timestamp INTEGER
        )
    """)
    conn.commit()
    return conn, cursor


def cache_get(cursor, appid, no_cache=False):
    if no_cache:
        return None
    cursor.execute("SELECT data FROM app_cache WHERE appid=?", (appid,))
    row = cursor.fetchone()
    return eval(row[0]) if row else None


def cache_set(conn, cursor, appid, data):
    cursor.execute(
        "REPLACE INTO app_cache VALUES (?, ?, ?)",
        (appid, str(data), int(time.time()))
    )
    conn.commit()


# ----------------------------
# REQUÊTES
# ----------------------------

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def safe_get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=BASE_HEADERS, params=params, timeout=20)
            if r.status_code in [429, 403]:
                time.sleep((2 ** i) + random.uniform(1, 3))
                continue
            if r.status_code != 200:
                return None
            return r
        except Exception:
            time.sleep(2)
    return None


def throttle(rate_min, rate_max):
    time.sleep(random.uniform(rate_min, rate_max))


# ----------------------------
# UTIL
# ----------------------------

def log(x):
    return math.log(max(x, 1))


def parse_date(s):
    if not s:
        return None
    for fmt in ["%d %b, %Y", "%b %d, %Y"]:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


# ----------------------------
# TAGS
# ----------------------------

def extract_tags(details):
    tags = set()
    for g in details.get("genres", []):
        desc = g.get("description", "").strip()
        if desc:
            tags.add(desc.lower())
    for c in details.get("categories", []):
        desc = c.get("description", "").strip()
        if desc:
            tags.add(desc.lower())
    return tags


def tags_match(tags, exclude):
    for t in exclude:
        if t.lower() in tags:
            return False
    return True


def tags_display(details):
    names = sorted({
        g.get("description", "") for g in details.get("genres", [])
    } | {
        c.get("description", "") for c in details.get("categories", [])
    })
    return ", ".join(n for n in names if n)


# ----------------------------
# SCRAPER
# ----------------------------

def load_tags(path):
    if not path.exists():
        scrape_steam_tags.main()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_tag_map(tag_list):
    return {t["name"].lower(): t["id"] for t in tag_list}

def build_tag_query(tag_map, names):
    return ",".join(
        str(tag_map[n.lower().replace(" ", "-")])
        for n in names
        if n.lower().replace(" ", "-") in tag_map
    )

def get_appids(filters, pages, rate_min, rate_max, quiet, tag_map, tag_names):

    appids = set()

    rankings = {
        "upcoming": {},
        "comingsoon": {},
        "topsellers": {},
        "popularnew": {},
    }

    tag_query = build_tag_query(tag_map, tag_names)
    base_category = "998" # Game

    for f in filters:
        global_rank = 1

        for page in range(pages):

            params = {
                "query": "",
                "start": page * 50,
                "count": 50,
                "filter": f,
                "infinite": 1,
                "category1": base_category,
            }

            if tag_query:
                params["tags"] = tag_query

            r = safe_get(STEAM_SEARCH, params=params)

            if not r:
                continue

            html_block = r.json().get("results_html", "")

            found = re.findall(r'data-ds-appid="(\d+)"', html_block)

            for appid in found:
                appids.add(appid)

                if f in rankings and appid not in rankings[f]:
                    rankings[f][appid] = global_rank

                global_rank += 1

            if not quiet:
                print(f"  [{f}] page {page+1}/{pages} — {len(found)} apps")

            throttle(rate_min, rate_max)

    return list(appids), rankings


def get_details(appid, conn, cursor, lang, rate_min, rate_max, no_cache):
    cached = cache_get(cursor, appid, no_cache)
    if cached:
        return cached
    r = safe_get(STEAM_APP_DETAILS, params={"appids": appid, "cc": lang, "l": "en"})
    if not r:
        return None
    try:
        data = r.json().get(str(appid), {})
        if not data.get("success"):
            return None
        result = data.get("data")
        cache_set(conn, cursor, appid, result)
        throttle(rate_min, rate_max)
        return result
    except Exception:
        return None


# ----------------------------
# SCORING — jeux sortis
# ----------------------------

def trend_score(pos, neg, release_date):
    total = pos + neg
    days = max((datetime.now() - release_date).days, 1)
    if total < 1:
        post = 0
    else:
        ratio = pos / (total + 1)
        velocity = total / days
        post = (
            0.5 * velocity * 10 +
            0.3 * ratio * 100 +
            0.2 * log(total)
        )
    decay = 1 / math.sqrt(days)
    return log(post * decay + 1) * 12


def confidence(pos, neg):
    total = pos + neg
    if total > 500: return 1.0
    if total > 100: return 0.8
    if total > 20:  return 0.6
    if total > 5:   return 0.4
    return 0.2


def released_score(pos, neg, release_date):
    return trend_score(pos, neg, release_date) * confidence(pos, neg)


# ----------------------------
# SCORING — coming soon
# ----------------------------

def rank_points(rank):
    """
    Rang Steam -> points.
    Le top 10 reste très dominant.
    """

    if not rank:
        return 0.0

    return 100 / math.sqrt(rank)

def upcoming_presale_score(appid, rankings, details):

    upcoming_rank = rankings["upcoming"].get(appid)

    if not upcoming_rank:
        return 0

    score = rank_points(upcoming_rank)

    comingsoon_rank = rankings["comingsoon"].get(appid)
    topseller_rank = rankings["topsellers"].get(appid)
    popularnew_rank = rankings["popularnew"].get(appid)

    if comingsoon_rank:
        score += rank_points(comingsoon_rank) * 0.25

    if topseller_rank:
        score += rank_points(topseller_rank) * 0.15

    if popularnew_rank:
        score += rank_points(popularnew_rank) * 0.05

    return round(score, 2)

# ----------------------------
# AFFICHAGE
# ----------------------------

def print_section(title, items, quiet):
    if not quiet:
        print(f"\n{'='*60}")
        print(f"  {title}  ({len(items)} games)")
        print(f"{'='*60}\n")
    for i, g in enumerate(items, 1):
        desc = g.get("description")
        if not isinstance(desc, str):
            desc = ""
        clean_desc = html.unescape(desc)
        tags_line = f"      🏷️  {g['tags']}\n" if g.get("tags") else ""
        score_label = "Presale" if g["coming_soon"] else "Score"
        extra = ""
        if g["coming_soon"] and g.get("presale_breakdown"):
            extra = f"      📊 {g['presale_breakdown']}\n"
        print(
            f"{i:3d}. {g['name']}\n"
            f"      {score_label} : {g['score']}  |  Release : {g['release']}\n"
            f"{tags_line}"
            f"{extra}"
            f"      📝 {clean_desc}\n"
        )


def presale_breakdown(appid, rankings):
    parts = []

    r = rankings["upcoming"].get(appid)
    if r:
        parts.append(f"Upcoming #{r}")

    r = rankings["comingsoon"].get(appid)
    if r:
        parts.append(f"ComingSoon #{r}")

    r = rankings["topsellers"].get(appid)
    if r:
        parts.append(f"TopSeller #{r}")

    return " | ".join(parts)


# ----------------------------
# PIPELINE
# ----------------------------

def main():
    args = parse_args()

    if not args.quiet:
        print("🎮 SteamDB Trending Engine\n")
        print(f"  Window   : {args.days} jours | Top releases : {args.top} | Top upcoming : {args.top_upcoming}")
        print(f"  Filters   : {', '.join(args.filters)} | Pages/filter : {args.pages} | Language : {args.lang}")
        if args.tags_include:
            print(f"  🏷️  Required tags : {', '.join(args.tags_include)}")
        if args.tags_exclude:
            print(f"  🚫 Excluded tags : {', '.join(args.tags_exclude)}")
        if args.no_cache:
            print("  ⚠️  Cache desactivated")
        print()

    all_tags_seen = set()

    conn, cursor = init_db(args.db, clear=args.clear_cache)
    if args.clear_cache and not args.quiet:
        print("🗑️  Cache cleaned\n")

    if not args.quiet:
        print("🔍 Collecting AppIDs...")

    tag_list = load_tags(Path("steam_tags.json").expanduser().resolve())
    tag_map = build_tag_map(tag_list)
    
    appids, rankings = get_appids(
        args.filters,
        args.pages,
        args.rate_min,
        args.rate_max,
        args.quiet,
        tag_map,
        args.tags_include
    )
    if not args.quiet:
        print(f"\n✅ {len(appids)} games collected\n")
        print("\nWriting to database and generating lists (this can take a few moments)...\n")

    released = []
    upcoming = []
    cutoff = datetime.now() - timedelta(days=args.days)

    for appid in appids:
        details = get_details(appid, conn, cursor, args.lang, args.rate_min, args.rate_max, args.no_cache)
        if not details:
            continue
        if details.get("type") != "game":
            continue

        name = details.get("name")
        if not name:
            continue

        release = parse_date(details.get("release_date", {}).get("date", ""))
        is_coming_soon = details.get("release_date", {}).get("coming_soon", False)

        # Fenêtre temporelle : coming soon sans date → toujours inclus
        if not is_coming_soon:
            if not release or release < cutoff:
                continue
        elif release and release < cutoff:
            # coming soon dont la date annoncée est déjà passée → ignorer
            continue

        is_free = details.get("is_free")
        has_price = details.get("price_overview")
        if not is_coming_soon and not is_free and not has_price:
            continue

        pos = details.get("recommendations", {}).get("total", 0)
        neg = 0

        if not is_coming_soon and pos < args.min_reviews:
            continue

        tags = extract_tags(details)
        all_tags_seen.update(tags)

        if args.tags_exclude:
            if not tags_match(tags, args.tags_exclude):
                if args.verbose:
                    print(f"  ✗ {name} — excluded tags")
                continue
        
        entry = {
            "name": name,
            "appid": appid,
            "release": release.strftime("%Y-%m-%d") if release else "Upcoming",
            "recommendations": pos,
            "coming_soon": is_coming_soon,
            "tags": tags_display(details),
            "description": translator.translate_stream([details.get("short_description", "")], args.lang),
        }

        if is_coming_soon:
            entry["score"] = upcoming_presale_score(
                appid,
                rankings,
                details
            )

            entry["presale_breakdown"] = presale_breakdown(
                appid,
                rankings
            )

            entry["upcoming_rank"] = rankings["upcoming"].get(appid, 999999)
            entry["comingsoon_rank"] = rankings["comingsoon"].get(appid, 999999)
            entry["topseller_rank"] = rankings["topsellers"].get(appid, 999999)

            upcoming.append(entry)
            if args.verbose:
                print(f"  🔜 {name} (presale={entry['score']} — {entry['presale_breakdown']})")
        else:
            ref_date = release if release else datetime.now()
            entry["score"] = round(released_score(pos, neg, ref_date), 2)
            released.append(entry)
            if args.verbose:
                print(f"  ✓ {name} (score={entry['score']}, reviews={pos})")

    # ----------------------------
    # CLASSEMENT
    # ----------------------------

    released.sort(key=lambda x: x["score"], reverse=True)
    upcoming.sort(
        key=lambda x: (
            -x["score"],
            x["upcoming_rank"],
            x["comingsoon_rank"],
            x["topseller_rank"]
        )
    )

    top_released = released[:args.top]
    top_upcoming = upcoming[:args.top_upcoming]

    if not args.quiet:
        print(f"  {len(released)} released games found | {len(upcoming)} games coming soon found\n")

    if top_released:
        print_section("🔥 TRENDING — Released games", top_released, args.quiet)
    else:
        print("\n  (No released game found)\n")

    if top_upcoming:
        print_section("🔜 PRESALE — Coming soon", top_upcoming, args.quiet)
    else:
        print("\n  (No coming soon game found)\n")

    if args.list_tags and all_tags_seen:
        print("\n📋 Availiable tags in this section :\n")
        for t in sorted(all_tags_seen):
            print(f"  • {t}")

    # ----------------------------
    # EXPORT CSV
    # ----------------------------

    if args.output:
        all_results = (
            [{**g, "section": "released"} for g in top_released] +
            [{**g, "section": "upcoming"} for g in top_upcoming]
        )
        fieldnames = ["section", "name", "appid", "release", "score",
                      "recommendations", "coming_soon", "tags", "description"]
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_results)
        print(f"\n💾 Exported results in {args.output}")

    conn.close()


if __name__ == "__main__":
    main()