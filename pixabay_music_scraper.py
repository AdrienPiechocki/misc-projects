import os
import re
import argparse
import requests

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from mutagen.id3 import ID3, TIT2, TPE1, TCON, APIC, ID3NoHeaderError

# ================== CLI ==================
def parse_args():
    parser = argparse.ArgumentParser(
        description="Download music from Pixabay with metadata.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "query",
        help="Search query (e.g. 'ambient', 'lo-fi hip hop', 'cinematic')"
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

# ================== HELPERS ==================
def query_to_url(query: str) -> str:
    """Convert a search query to a Pixabay music search base URL."""
    slug = re.sub(r'\s+', '-', query.strip().lower())
    slug = re.sub(r'[^\w-]', '', slug)
    return f"https://pixabay.com/music/search/{slug}"

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

# ================== BROWSER FACTORY ==================
def make_browser(playwright):
    """Launch a Chromium browser. Returns a (browser, context, page) tuple."""
    b = playwright.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = b.new_context(
        viewport={"width": 1280, "height": 900},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    page = context.new_page()
    return b, context, page

# ================== SCRAPING FUNCTION ==================
def scrape_songs(song_urls, process_id, download_dir, sleep_time):
    with sync_playwright() as pw:
        b, context, page = make_browser(pw)

        for i, url in enumerate(song_urls, start=1):
            print(f"🧵 Worker {process_id} | Song {i}/{len(song_urls)}")
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            try:
                # -------- GENRE --------
                try:
                    genre_el = page.locator("a[class*='theme--']").first
                    genre_el.wait_for(timeout=10_000)
                    genre = genre_el.inner_text()
                except PlaywrightTimeoutError:
                    genre = None

                # -------- TITLE --------
                title_el = page.locator("[class*='title--']").first
                title_el.wait_for(timeout=15_000)
                title = title_el.inner_text()

                # -------- AUTHOR --------
                author_el = page.locator("[class*='userName--']").first
                author_el.wait_for(timeout=15_000)
                author = author_el.inner_text()

                # -------- PLAY --------
                play_button = page.locator("button[class*='playIcon']").first
                play_button.wait_for(state="visible", timeout=15_000)
                play_button.click()

                # -------- AUDIO --------
                # The <audio> element is hidden in the DOM — wait for it to be
                # attached (src present) rather than visible.
                audio_el = page.locator("audio").first
                audio_el.wait_for(state="attached", timeout=15_000)
                mp3_url = audio_el.get_attribute("src")

                if not mp3_url:
                    print("   ⚠️  MP3 URL not found, skipping.")
                    continue

                # -------- IMAGE --------
                try:
                    image_url = page.locator(
                        "img[src*='cdn.pixabay.com']"
                    ).first.get_attribute("src")
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

            page.wait_for_timeout(int(sleep_time * 1000))

        b.close()

# ================== MAIN ==================
if __name__ == "__main__":
    from multiprocessing import Process

    args = parse_args()

    base_url = query_to_url(args.query)
    os.makedirs(args.output, exist_ok=True)

    print(f"\n🔍 Query    : {args.query}")
    print(f"🔗 URL      : {base_url}")
    print(f"🎯 Max songs: {args.max_songs}")
    print(f"📂 Output   : {args.output}")
    print(f"👷 Workers  : {args.workers}\n")

    # -------- COLLECT LINKS --------
    song_urls = []

    with sync_playwright() as pw:
        b, context, page = make_browser(pw)

        page_num = 1
        empty_pages = 0
        MAX_EMPTY_PAGES = 5

        while len(song_urls) < args.max_songs and page_num <= args.max_pages:
            url = f"{base_url}/?pagi={page_num}"
            print(f"📄 Page {page_num} | Links collected: {len(song_urls)}")
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            new_links = page.evaluate("""
                () => [...new Set(
                    Array.from(document.querySelectorAll("a[class*='title--']"))
                        .map(a => a.href)
                        .filter(h => h.includes('/music/'))
                )]
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

            page_num += 1
            page.wait_for_timeout(int(args.sleep * 1000))

        b.close()

    print(f"\n🎧 Links collected: {len(song_urls)}")

    if not song_urls:
        print("❌ No links found. Check your query or connection.")
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
                args=(chunk, worker_id, args.output, args.sleep)
            )
            processes.append(p)
            p.start()

    for p in processes:
        p.join()

    print(f"\n🎵 Done! MP3s saved in: ./{args.output}/")