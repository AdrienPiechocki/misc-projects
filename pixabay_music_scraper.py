import os
import re
import time
import argparse
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from mutagen.id3 import ID3, TIT2, TPE1, TCON, APIC, ID3NoHeaderError

# ================== CLI ==================
def parse_args():
    parser = argparse.ArgumentParser(
        description="Download music from Pixabay with metadata.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://pixabay.com/music/search/ambient/",
        help="Pixabay search URL (e.g. 'https://pixabay.com/music/search/ambient/')"
    )
    parser.add_argument(
        "--browser", "-b",
        choices=["firefox", "chrome"],
        default="firefox",
        help="Browser to use for scraping"
    )
    parser.add_argument(
        "--max-songs", "-n",
        type=int,
        default=10,
        help="Maximum number of songs to download"
    )
    parser.add_argument(
        "--max-pages", "-p",
        type=int,
        default=10,
        help="Maximum number of search pages to browse"
    )
    parser.add_argument(
        "--sleep", "-s",
        type=float,
        default=2.0,
        help="Sleep time (seconds) between requests"
    )
    parser.add_argument(
        "--output", "-o",
        default="music_downloads",
        help="Output directory for downloaded MP3s"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=2,
        help="Number of parallel download workers"
    )
    return parser.parse_args()

# ================== DRIVER FACTORY ==================
def make_driver(browser: str) -> webdriver.Remote:
    if browser == "firefox":
        from selenium.webdriver.firefox.service import Service
        from selenium.webdriver.firefox.options import Options
        from webdriver_manager.firefox import GeckoDriverManager

        options = Options()
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        return webdriver.Firefox(
            service=Service(GeckoDriverManager().install()),
            options=options
        )

    elif browser == "chrome":
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager

        options = Options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

    else:
        raise ValueError(f"Unsupported browser: {browser}")

# ================== HELPERS ==================
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def download_mp3(mp3_url, filepath):
    response = requests.get(mp3_url, timeout=30, stream=True)
    response.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

def apply_metadata(filepath, title, author, genre, image_url):
    try:
        audio = ID3(filepath)
    except ID3NoHeaderError:
        audio = ID3()

    audio[TIT2] = TIT2(encoding=3, text=title or "Unknown Title")
    audio[TPE1] = TPE1(encoding=3, text=author or "Unknown Artist")

    if genre:
        audio[TCON] = TCON(encoding=3, text=genre)

    if image_url:
        try:
            img_response = requests.get(image_url, timeout=15)
            img_response.raise_for_status()
            content_type = img_response.headers.get("Content-Type", "image/jpeg")
            audio[APIC] = APIC(
                encoding=3,
                mime=content_type,
                type=3,
                desc="Cover",
                data=img_response.content
            )
        except Exception as e:
            print(f"   ⚠️  Could not embed cover art: {e}")

    audio.save(filepath, v2_version=3)

# ================== SCRAPING FUNCTION ==================
def scrape_songs(song_urls, process_id, browser, download_dir, sleep_time):
    driver = make_driver(browser)
    driver.maximize_window()
    wait = WebDriverWait(driver, 25)

    for i, url in enumerate(song_urls, start=1):
        print(f"🧵 Worker {process_id} | Song {i}/{len(song_urls)}")
        driver.get(url)
        time.sleep(3)

        try:
            # -------- GENRE --------
            try:
                genre = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "a[class*='theme--']")
                    )
                ).text
            except Exception:
                genre = None

            # -------- TITLE --------
            title = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[class*='title--']")
                )
            ).text

            # -------- AUTHOR --------
            author = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[class*='userName--']")
                )
            ).text

            # -------- PLAY --------
            play_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@class,'playIcon')]")
                )
            )
            driver.execute_script("arguments[0].click();", play_button)

            # -------- AUDIO --------
            audio_el = wait.until(
                EC.presence_of_element_located((By.TAG_NAME, "audio"))
            )
            mp3_url = audio_el.get_attribute("src")

            if not mp3_url:
                print("   ⚠️  MP3 URL not found, skipping.")
                continue

            # -------- IMAGE --------
            try:
                image_url = driver.find_element(
                    By.XPATH,
                    "//img[contains(@src,'cdn.pixabay.com')]"
                ).get_attribute("src")
            except Exception:
                image_url = None

            # -------- DOWNLOAD & TAG --------
            safe_title = sanitize_filename(title or f"track_{i}")
            safe_author = sanitize_filename(author or "unknown")
            filename = f"{safe_title} - {safe_author}.mp3"
            filepath = os.path.join(download_dir, filename)

            print(f"   ⬇️  Downloading: {filename}")
            download_mp3(mp3_url, filepath)
            print(f"   🏷️  Applying metadata...")
            apply_metadata(filepath, title, author, genre, image_url)
            print(f"   ✅ {title} | Genre: {genre}")

        except Exception as e:
            print(f"   ❌ Worker {process_id} error on {url}: {e}")

        time.sleep(sleep_time)

    driver.quit()

# ================== MAIN ==================
if __name__ == "__main__":
    from multiprocessing import Process

    args = parse_args()

    # Strip trailing slash for consistent pagination
    base_url = args.url.rstrip("/")
    os.makedirs(args.output, exist_ok=True)

    print(f"\n🔧 Browser  : {args.browser}")
    print(f"🔗 URL      : {base_url}")
    print(f"🎯 Max songs: {args.max_songs}")
    print(f"📂 Output   : {args.output}")
    print(f"👷 Workers  : {args.workers}\n")

    # -------- COLLECT LINKS --------
    driver = make_driver(args.browser)
    driver.maximize_window()

    song_urls = []
    page = 1
    empty_pages = 0
    MAX_EMPTY_PAGES = 5

    while len(song_urls) < args.max_songs and page <= args.max_pages:
        url = f"{base_url}/?pagi={page}"
        print(f"📄 Page {page} | Links collected: {len(song_urls)}")
        driver.get(url)
        time.sleep(3)

        new_links = driver.execute_script("""
            return [...new Set(
                Array.from(document.querySelectorAll("a[class*='title--']"))
                    .map(a => a.href)
                    .filter(h => h.includes('/music/'))
            )];
        """)

        print(f"   → {len(new_links)} link(s) found on this page")

        if not new_links:
            empty_pages += 1
            print(f"   ⚠️  Empty page ({empty_pages}/{MAX_EMPTY_PAGES})")
            if empty_pages >= MAX_EMPTY_PAGES:
                print("🛑 Too many empty pages. Stopping link collection.")
                break
        else:
            empty_pages = 0

        for link in new_links:
            if link not in song_urls:
                song_urls.append(link)
            if len(song_urls) >= args.max_songs:
                break

        page += 1
        time.sleep(args.sleep)

    driver.quit()

    print(f"\n🎧 Links collected: {len(song_urls)}")

    if not song_urls:
        print("❌ No links found. Check the URL or your connection.")
        exit(1)

    # -------- DISTRIBUTE ACROSS WORKERS --------
    chunks = [[] for _ in range(args.workers)]
    for idx, url in enumerate(song_urls):
        chunks[idx % args.workers].append(url)

    processes = []
    for worker_id, chunk in enumerate(chunks, start=1):
        if chunk:
            p = Process(
                target=scrape_songs,
                args=(chunk, worker_id, args.browser, args.output, args.sleep)
            )
            processes.append(p)
            p.start()

    for p in processes:
        p.join()

    print(f"\n🎵 Done! MP3s saved in: ./{args.output}/")