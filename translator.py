#!/usr/bin/env python3

import sys
import warnings
import logging
import os

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import argparse
import argostranslate.package
import argostranslate.translate
from langdetect import detect

def normalize_lang(code: str) -> str:
    code = code.lower()

    mapping = {
        "zh-cn": "zh",
        "zh-tw": "zh",
    }

    return mapping.get(code, code)

def ensure_language_pair(from_code: str, to_code: str):
    installed_languages = argostranslate.translate.get_installed_languages()

    for lang in installed_languages:
        if lang.code == from_code:
            for translation in lang.translations_from:
                if translation.to_lang.code == to_code:
                    return

    argostranslate.package.update_package_index()

    available_packages = argostranslate.package.get_available_packages()

    package = next(
        (
            pkg
            for pkg in available_packages
            if pkg.from_code == from_code
            and pkg.to_code == to_code
        ),
        None,
    )

    if package is None:
        raise RuntimeError(
            f"Aucun modèle disponible pour {from_code} -> {to_code}"
        )

    download_path = package.download()
    argostranslate.package.install_from_path(download_path)

def translate_via_english(text, from_lang, to_lang):
    if from_lang == to_lang:
        return text

    # étape 1 : source → anglais
    if from_lang != "en":
        ensure_language_pair(from_lang, "en")
        text = argostranslate.translate.translate(text, from_lang, "en")
        from_lang = "en"

    # étape 2 : anglais → cible
    if to_lang != "en":
        ensure_language_pair(from_lang, to_lang)
        text = argostranslate.translate.translate(text, from_lang, to_lang)

    return text

def translate_stream(text, to_lang):
    result = []
    for line in text:
        line = line.rstrip("\n")

        if not line.strip():
            print()
            continue

        lang = detect(line) if len(line.strip()) > 3 else "en"
        lang = normalize_lang(lang)
        translated = translate_via_english(line, lang, to_lang)

        result.append(translated)
    return "\n".join(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?")
    parser.add_argument("-l", "--lang", default="en")

    args = parser.parse_args()
    if args.text:
        text = [args.text]
    else:
        text = sys.stdin
    
    print(translate_stream(text, args.lang))


if __name__ == "__main__":
    main()