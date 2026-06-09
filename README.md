# Python Automation Suite

A collection of lightweight, efficient, and specialized Python tools for web scraping, music management, and natural language processing.

## Projects Overview

### 1. Web Scrapers

* **Article Scraper ([`article_scraper_js.py`](https://www.google.com/search?q=article_scraper_js.py))**: A robust tool to extract article content from web pages, including JavaScript-rendered sites (React, Vue, etc.). It uses a cascade strategy: `newspaper3k` for speed, falling back to `Playwright` + `BeautifulSoup` for complex rendering.
* **LinkedIn Job Scraper ([`linkedin_scraper.py`](https://www.google.com/search?q=linkedin_scraper.py))**: A "guest-mode" scraper that fetches job listings from LinkedIn without requiring a session or browser login. It utilizes LinkedIn’s public guest API, `httpx`, and `BeautifulSoup`.
* **Pixabay Music Scraper ([`pixabay_music_scraper.py`](https://www.google.com/search?q=pixabay_music_scraper.py))**: Automates the search and download of music from Pixabay. Includes metadata management (ID3 tags) and parallel download capabilities using `Selenium` and `mutagen`.

### 2. Music Tools

* **Playlist Generator ([`playlis_generator.py`](https://www.google.com/search?q=playlis_generator.py))**: Scans directories for MP3 files, analyzes their audio characteristics (BPM, energy, mood, key) using `librosa` and `numpy`, and generates `.m3u` playlists based on the audio analysis.

### 3. Text Summarization

* **Summarizer Engine ([`summarizer.py`](https://www.google.com/search?q=summarizer.py))**: A core module implementing the TextRank algorithm. It segments text, computes similarity matrices using TF-IDF and cosine similarity, and ranks sentences to produce concise summaries.
* **Article Summarizer ([`summarize_article.py`](https://www.google.com/search?q=summarize_article.py))**: A CLI tool that combines the Article Scraper and the Summarizer Engine to fetch an online article and generate a paragraph-by-paragraph summary.

---

## Getting Started

### Prerequisites

Most scripts require Python 3 and several dependencies. To install the core libraries:

```bash
pip install -r requirements.txt
# Additional setup for Playwright
playwright install chromium

```

Voici des exemples d'utilisation détaillés et concrets, un pour chaque script, à ajouter dans la section "Usage" de votre fichier `README.md`.

---

### Usage Examples

* **`article_scraper_js.py`**
* *Scraping dynamique :* Pour extraire le contenu d'un article :
```bash
python article_scraper_js.py "https://tech-blog.com/post-123"
```

* **`pixabay_music_scraper.py`**
* *Téléchargement par lots :* Pour télécharger automatiquement les 20 premiers titres de musique "Lo-fi" trouvés sur 5 pages de résultats :
```bash
python pixabay_music_scraper.py "https://pixabay.com/music/search/lofi/" --max-songs 20 --max-pages 5 --browser chrome
```

* **`linkedin_scraper.py`**
* *Recherche ciblée :* Pour lancer une recherche d'emplois basée sur un fichier de configuration personnalisé (`my_jobs.yaml`) :
```bash
python linkedin_scraper.py --config my_jobs.yaml --output "./linkedin_jobs"
```

* **`playlis_generator.py`**
* *Génération intelligente :* Pour analyser une bibliothèque musicale locale et créer des playlists `.m3u` en se basant sur les caractéristiques audio (BPM, humeur) :
```bash
python playlis_generator.py --folder "/home/user/Music/Jazz" --output "./playlists"
```

* **`summarize_article.py`**
* *Résumé complet :* Pour récupérer directement une page web et générer un résumé synthétique de l'article :
```bash
python summarize_article.py "https://news.com/long-article" --ratio 0.3
```

---

## License

Feel free to use and modify these scripts for your personal projects.