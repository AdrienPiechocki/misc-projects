import requests
import re
import math
import time
from datetime import datetime, timedelta
import pandas as pd
import random
import sqlite3
import html

STEAM_SEARCH = "https://store.steampowered.com/search/results/"
STEAM_APP_DETAILS = "https://store.steampowered.com/api/appdetails"

# ----------------------------
# CONFIG (production tuning)
# ----------------------------

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

RATE_MIN = 0.6
RATE_MAX = 1.8

DB = "steam_cache.db"


LOOKBACK_DAYS = 7
MIN_REVIEWS = 1
TOP_K = 100


# ----------------------------
# CACHE (SQLite = production safe)
# ----------------------------

conn = sqlite3.connect(DB)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS app_cache (
    appid TEXT PRIMARY KEY,
    data TEXT,
    timestamp INTEGER
)
""")
conn.commit()


def cache_get(appid):
    cursor.execute("SELECT data FROM app_cache WHERE appid=?", (appid,))
    row = cursor.fetchone()
    return eval(row[0]) if row else None


def cache_set(appid, data):
    cursor.execute(
        "REPLACE INTO app_cache VALUES (?, ?, ?)",
        (appid, str(data), int(time.time()))
    )
    conn.commit()


# ----------------------------
# SAFE REQUEST WRAPPER
# ----------------------------

def safe_get(url, params=None, retries=1):
    for i in range(retries):
        try:
            r = requests.get(url, headers=BASE_HEADERS, params=params, timeout=20)

            if r.status_code in [429, 403]:
                sleep = (2 ** i) + random.uniform(1, 3)
                time.sleep(sleep)
                continue

            if r.status_code != 200:
                return None

            return r

        except:
            print("retrying")
            time.sleep(2)

    return None


def throttle():
    time.sleep(random.uniform(RATE_MIN, RATE_MAX))


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
        except:
            pass

    return None


# ----------------------------
# SCRAPER (Steam search expansion)
# ----------------------------

def get_appids():
    ids = set()

    filters = ["popularnew", "topsellers", "comingsoon"]

    for f in filters:
        for page in range(0, 6):

            r = safe_get(
                STEAM_SEARCH,
                params={
                    "query": "",
                    "start": page * 50,
                    "count": 50,
                    "filter": f,
                    "infinite": 1
                }
            )

            if not r:
                continue

            html = r.json().get("results_html", "")

            import re
            found = re.findall(r'data-ds-appid="(\d+)"', html)

            ids.update(found)

            throttle()

    return list(ids)


# ----------------------------
# APP DETAILS
# ----------------------------

def get_details(appid):
    
    cached = cache_get(appid)
    if cached:
        return cached

    r = safe_get(
        "https://store.steampowered.com/api/appdetails",
        params={"appids": appid, "cc": "fr", "l": "en"}
    )

    if not r:
        return None

    try:
        data = r.json().get(str(appid), {})
        if not data.get("success"):
            return None

        result = data.get("data")
        cache_set(appid, result)

        throttle()
        return result

    except:
        return None


# ----------------------------
# TREND ENGINE (PRODUCTION CORE)
# ----------------------------

def trend_score(pos, neg, release_date):

    total = pos + neg
    days = max((datetime.now() - release_date).days, 1)

    # POST-LAUNCH SIGNAL
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
    score = log(post * decay + 1) * 12

    return score


def hype_score(coming_soon):

    score = 0

    if coming_soon:
        score += 40

    return score

def confidence(pos, neg, days_since_release):

    total = pos + neg

    if total > 500:
        return 1.0
    if total > 100:
        return 0.8
    if total > 20:
        return 0.6
    if total > 5:
        return 0.4

    return 0.2

def final_score(post_score, hype_score, confidence):

    # post-launch dominant
    if post_score > 0:
        base = post_score * 1.0 + hype_score * 0.3
    else:
        base = hype_score

    # confidence penalty
    return base * confidence

# ----------------------------
# PIPELINE
# ----------------------------

def main():

    print("🎮 SteamDB Production Engine V6\n")

    appids = get_appids()
    
    print(f"Collected: {len(appids)} apps\n")

    results = []

    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)

    for i, appid in enumerate(appids):

        details = get_details(appid)
        if not details:
            continue

        # only real games
        if details.get("type") != "game":
            continue

        name = details.get("name")
        if not name:
            continue

        release = parse_date(details.get("release_date", {}).get("date", ""))
        is_coming_soon = details.get("release_date", {}).get("coming_soon", False)
        
        if not is_coming_soon:
            if not release or release < cutoff:
                continue

        if release < cutoff:
            continue

        # fake protection
        is_free = details.get("is_free")
        has_price = details.get("price_overview")
        if not is_coming_soon and not is_free and not has_price:
            continue

        # SteamSpy-like approximation removed → avoid failure mode
        pos = details.get("recommendations", {}).get("total", 0)
        neg = 0  # Steam doesn't always provide negatives here

        post_score = trend_score(
            pos, 
            neg, 
            release if release else datetime.now()
        )
        hype = hype_score(is_coming_soon)
        conf = confidence(
            pos, 
            neg, 
            max((datetime.now() - release if release else datetime.now()).days, 1)
        )
        score = final_score(post_score, hype, conf)

        short_desc = details.get("short_description", "Aucune description disponible.")

        results.append({
            "name": name,
            "appid": appid,
            "release": release.strftime("%Y-%m-%d"),
            "score": round(score, 2),
            "recommendations": pos,
            "description": short_desc
        })

        print(f"OK {name}")


    # ----------------------------
    # RANKING
    # ----------------------------

    results.sort(key=lambda x: x["score"], reverse=True)

    print("\n🔥 STEAMDB PRODUCTION TRENDING\n")

    for i, g in enumerate(results[:TOP_K], 1):

        clean_desc = html.unescape(g["description"])

        print(
            f"{i:2d}. {g['name']}\n"
            f"    Score: {g['score']}\n"
            f"    Reviews: {g['recommendations']}\n"
            f"    Release: {g['release']}\n"
            f"    Description: {clean_desc}\n"
        )

if __name__ == "__main__":
    main()