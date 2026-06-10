#!/usr/bin/env python3
"""
🎵 Playlist Generator (sans clé API)
Analyse tes MP3 via métadonnées ID3 + analyse audio et génère des playlists .m3u.

Dépendances :
    pip install mutagen librosa numpy

Usage :
    python playlist_generator.py --folder /chemin/vers/musiques
    python playlist_generator.py --folder ./music --output ./playlists
"""

import re
import json
import argparse
import hashlib
from pathlib import Path

try:
    from mutagen import File as MutagenFile
    MUTAGEN_OK = True
except ImportError:
    MUTAGEN_OK = False
    print("⚠️  mutagen manquant → pip install mutagen")

try:
    import librosa
    import numpy as np
    LIBROSA_OK = True
except ImportError:
    LIBROSA_OK = False
    print("⚠️  librosa/numpy manquants → pip install librosa numpy")


# ══════════════════════════════════════════════════════════════════════════════
# 1. MÉTADONNÉES ID3
# ══════════════════════════════════════════════════════════════════════════════

def extract_metadata(mp3_path: Path) -> dict:
    meta = {
        "path": str(mp3_path),
        "filename": mp3_path.name,
        "title": mp3_path.stem,
        "artist": "",
        "album": "",
        "genre": "",
        "year": "",
        "duration_sec": 0,
    }
    if not MUTAGEN_OK:
        return meta
    try:
        audio = MutagenFile(mp3_path, easy=True)
        if audio is None:
            return meta
        def tag(k):
            v = audio.get(k)
            return v[0] if v else ""
        meta["title"]        = tag("title") or mp3_path.stem
        meta["artist"]       = tag("artist")
        meta["album"]        = tag("album")
        meta["genre"]        = tag("genre")
        meta["year"]         = tag("date")
        meta["duration_sec"] = int(audio.info.length) if audio.info else 0
    except Exception as e:
        print(f"  ⚠️  Métadonnées [{mp3_path.name}] : {e}")
    return meta


# ══════════════════════════════════════════════════════════════════════════════
# 2. ANALYSE AUDIO (librosa) — compatible ≥ 0.10
# ══════════════════════════════════════════════════════════════════════════════

def analyze_audio(mp3_path: Path) -> dict:
    features = {
        "bpm": 0.0,
        "energy": 0.0,
        "spectral_centroid": 0.0,
        "spectral_rolloff": 0.0,
        "zero_crossing_rate": 0.0,
        "mode": "unknown",
        "key": "unknown",
    }
    if not LIBROSA_OK:
        return features
    try:
        y, sr = librosa.load(str(mp3_path), sr=22050, duration=30, mono=True)

        # ── BPM : np.squeeze() gère les scalaires 0-D (librosa ≥ 0.10) ──
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        features["bpm"] = round(float(np.squeeze(tempo)), 1)

        rms = librosa.feature.rms(y=y)
        features["energy"] = round(float(np.mean(rms)), 5)

        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        features["spectral_centroid"] = round(float(np.mean(centroid)), 1)

        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
        features["spectral_rolloff"] = round(float(np.mean(rolloff)), 1)

        zcr = librosa.feature.zero_crossing_rate(y)
        features["zero_crossing_rate"] = round(float(np.mean(zcr)), 5)

        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)
        notes = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
        features["key"] = notes[int(np.argmax(chroma_mean))]

        major_p = np.array([1,0,1,0,1,1,0,1,0,1,0,1], dtype=float)
        minor_p = np.array([1,0,1,1,0,1,0,1,1,0,1,0], dtype=float)
        features["mode"] = "major" if np.dot(chroma_mean, major_p) >= np.dot(chroma_mean, minor_p) else "minor"

    except Exception as e:
        print(f"  ⚠️  Analyse audio [{mp3_path.name}] : {e}")
    return features


# ══════════════════════════════════════════════════════════════════════════════
# 3. CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

# ── Mood depuis les features audio ────────────────────────────────────────────

def classify_mood(f: dict) -> str:
    bpm    = f.get("bpm", 0)
    energy = f.get("energy", 0)
    mode   = f.get("mode", "unknown")

    HIGH_E = 0.055
    MED_E  = 0.030
    LOW_E  = 0.018

    if bpm > 130 and energy > HIGH_E:
        return "energetic"
    if bpm > 120 and mode == "minor" and energy > HIGH_E:
        return "intense"
    if bpm > 105 and mode == "major" and energy > MED_E:
        return "upbeat"
    if 90 <= bpm <= 130 and mode == "major":
        return "adventurous"
    if mode == "minor" and energy > MED_E:
        return "dark"
    if bpm < 80 and mode == "minor" and energy < MED_E:
        return "melancholic"
    if bpm < 90 and energy < LOW_E:
        return "calm"
    return "neutral"


# ══════════════════════════════════════════════════════════════════════════════
# 4. GÉNÉRATION DES PLAYLISTS .m3u
# ══════════════════════════════════════════════════════════════════════════════

def generate_playlists(tracks: list, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    by_mood:      dict = {}

    for t in tracks:
        mood      = t.get("mood", "unknown")
        by_mood.setdefault(mood, []).append(t)

    mood_dir = output_dir / "by_mood"
    mood_dir.mkdir(exist_ok=True)
    for mood, group in sorted(by_mood.items()):
        _write_m3u(mood_dir / f"{_safe(mood)}.m3u", group, f"Mood: {mood}")

    _write_m3u(output_dir / "all_tracks.m3u", tracks, "All tracks")

    print(f"\n📁 Playlists générées dans : {output_dir}")
    print(f"   🎭 {len(by_mood)} mood(s)  : {', '.join(sorted(by_mood))}")


def _write_m3u(path: Path, tracks: list, title: str):
    lines = ["#EXTM3U", f"#PLAYLIST:{title}", ""]
    for t in tracks:
        dur     = t.get("duration_sec", -1)
        display = f"{t['artist']} — {t['title']}" if t["artist"] else t["title"]
        lines.append(f"#EXTINF:{dur},{display}")
        lines.append(t["path"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✔ {path.name}  ({len(tracks)} piste{'s' if len(tracks)>1 else ''})")


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()


# ══════════════════════════════════════════════════════════════════════════════
# 5. CACHE
# ══════════════════════════════════════════════════════════════════════════════

def _file_hash(path: Path) -> str:
    h = hashlib.md5()
    h.update(str(path.stat().st_mtime).encode())
    h.update(str(path.stat().st_size).encode())
    return h.hexdigest()

def load_cache(cache_file: Path) -> dict:
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except Exception:
            pass
    return {}

def save_cache(cache_file: Path, cache: dict):
    cache_file.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


# ══════════════════════════════════════════════════════════════════════════════
# 6. MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="🎵 Game Music Playlist Generator")
    parser.add_argument("--folder",      required=True, help="Dossier contenant les .mp3")
    parser.add_argument("--output",      default="playlists", help="Dossier de sortie")
    parser.add_argument("--no-audio",    action="store_true", help="Désactiver l'analyse librosa")
    parser.add_argument("--clear-cache", action="store_true", help="Vider le cache")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    if not folder.exists():
        print(f"❌ Dossier introuvable : {folder}")
        return

    mp3_files = sorted(folder.rglob("*.mp3"))
    if not mp3_files:
        print(f"❌ Aucun .mp3 trouvé dans {folder}")
        return

    print(f"🔍 {len(mp3_files)} fichier(s) MP3 trouvé(s)\n")

    output.mkdir(parents=True, exist_ok=True)
    cache_file = output / ".analysis_cache.json"
    cache = {} if args.clear_cache else load_cache(cache_file)

    tracks = []
    for i, mp3 in enumerate(mp3_files, 1):
        fhash = _file_hash(mp3)
        print(f"[{i}/{len(mp3_files)}] {mp3.name}")

        if fhash in cache:
            print("  ↩️  Cache")
            tracks.append(cache[fhash])
            continue

        track    = extract_metadata(mp3)
        features = {} if args.no_audio else analyze_audio(mp3)

        if not features:
            features = {"bpm":0,"energy":0,"spectral_centroid":0,
                        "spectral_rolloff":0,"zero_crossing_rate":0,
                        "mode":"unknown","key":"unknown"}

        track["features"]  = features
        track["mood"]      = classify_mood(features) if not args.no_audio else "unknown"

        label = f"{track['artist']} — {track['title']}" if track["artist"] else track["title"]
        print(f"  mood={track['mood']} bpm={features.get('bpm',0):.0f}  mode={features.get('mode','?')}")

        cache[fhash] = track
        tracks.append(track)

    save_cache(cache_file, cache)
    print()
    generate_playlists(tracks, output)

    json_out = output / "tracks_analysis.json"
    json_out.write_text(json.dumps(tracks, indent=2, ensure_ascii=False))
    print(f"\n📊 Analyse complète : {json_out}")


if __name__ == "__main__":
    main()