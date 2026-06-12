import asyncio
import edge_tts
import re
import argparse
from pathlib import Path

async def generate_audio_and_subs(text, path, name, voice: str = "fr-FR-HenriNeural"):
    communicate = edge_tts.Communicate(text, voice)
    submaker = edge_tts.SubMaker()

    with open(f"{path}{name}.wav", "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            # On accepte les phrases si les mots sont absents
            elif chunk["type"] in ["WordBoundary", "SentenceBoundary"]:
                submaker.feed(chunk)

    # On vérifie si on a récupéré quelque chose
    subtitles = submaker.get_srt()

    with open(f"{path}{name}.vtt", "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        vtt_content = re.sub(r'(\d),(\d)', r'\1.\2', subtitles)
        f.write(vtt_content)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Générateur d'audio et de sous-titres à partir d'un texte.")
    parser.add_argument("text", help="texte à utiliser")
    parser.add_argument("-f", "--folder", type=str, default="./TTS/", help="Chemin de sortie des fichers.")
    parser.add_argument("-n", "--name", type=str, default="audio", help="Nom des fichers.")

    args = parser.parse_args()
    
    output = Path(args.folder).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    asyncio.run(generate_audio_and_subs(args.text, args.folder, args.name))