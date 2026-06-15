from playwright.sync_api import sync_playwright
import re
import json

# --- text cleaning ---
def clean_name(text: str) -> str:
    # remove emojis / pictographs
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    # remove weird leftover symbols
    text = re.sub(r"[^\w\s&'-]", "", text)
    # normalize spaces
    return " ".join(text.split()).strip()

# --- main scrape ---
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://steamdb.info/tags/")

    page.wait_for_timeout(3000)

    elements = page.query_selector_all("a[href*='/tag/']")

    tags = {}

    for el in elements:
        href = el.get_attribute("href")
        if not href:
            continue

        match = re.search(r"/tag/(\d+)/", href)
        if not match:
            continue

        tag_id = match.group(1)

        name = clean_name(el.inner_text())

        # skip empty results
        if not name:
            continue

        # keep only first occurrence (dedupe)
        if tag_id not in tags:
            tags[tag_id] = {
                "id": int(tag_id),
                "name": name.lower().replace(" ", "-")
            }

    browser.close()

# --- convert to API-friendly list ---
output = list(tags.values())

# --- save JSON ---
with open("steam_tags.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Exported {len(output)} tags")