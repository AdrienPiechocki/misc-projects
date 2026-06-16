"""
steam_adgen.py — Générateur de texte publicitaire pour les jeux Steam
Compagnon de steam_trending.py

Usage :
    # À partir d'un CSV exporté par steam_trending.py
    python steam_adgen.py --input results.csv

    # Pipe direct depuis steam_trending.py
    python steam_trending.py --output /tmp/t.csv && python steam_adgen.py --input /tmp/t.csv

    # Nombre de jeux à traiter
    python steam_adgen.py --input results.csv --top 5
"""

import csv
import argparse
import random
import html
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# DICTIONNAIRES DE PHRASES
# Chaque phrase peut contenir des placeholders :
#   {name}        — titre du jeu
#   {release}     — date de sortie (ou "Upcoming")
#   {score}       — score de tendance
#   {reviews}     — nombre de recommendations
# ---------------------------------------------------------------------------

# -- Accroches d'ouverture génériques
HOOKS_GENERIC = [
    "Vous cherchez votre prochain jeu préféré ?",
    "Le jeu dont tout le monde parle en ce moment :",
    "Ne passez pas à côté de ça.",
    "Attention, pépite repérée.",
    "Steam a parlé. Voici ce que les joueurs plébiscitent.",
    "Le classement ne ment pas.",
    "Un jeu qui mérite toute votre attention.",
    "Les joueurs ont tranché.",
]

# -- Accroches pour les jeux très bien notés (reviews élevées)
HOOKS_POPULAR = [
    "Avec {reviews} recommandations, le verdict est sans appel :",
    "La communauté Steam est formelle — {reviews} avis positifs pour {name}.",
    "{reviews} joueurs ont adoré. Pourquoi pas vous ?",
    "Ce n'est pas un hasard si {reviews} joueurs recommandent {name}.",
]

# -- Accroches pour les coming soon
HOOKS_UPCOMING = [
    "Marquez la date : {name} arrive bientôt.",
    "Déjà en tête des wishlist Steam — {name} est à surveiller.",
    "La hype est réelle. {name} fait déjà parler avant même sa sortie.",
    "Wishlistez maintenant avant que tout le monde ne le fasse.",
    "Le compte à rebours est lancé pour {name}.",
]

# -- Phrases de corps par genre/tag détecté
# Clé : fragment de tag Steam (insensible à la casse, correspondance partielle)
TAG_PHRASES = {
    "action": [
        "Du rythme, de l'adrénaline, et une action sans temps mort.",
        "Pour ceux qui ne veulent pas s'endormir devant un écran.",
        "Chaque session est un défi. Êtes-vous prêt ?",
        "L'action ne s'arrête jamais dans {name}.",
    ],
    "rpg": [
        "Des heures de jeu garanties dans un univers qui vous absorbe.",
        "Construisez votre légende, forgez votre destin.",
        "Un RPG qui récompense l'exploration et la curiosité.",
        "Perdez-vous dans un monde riche en quêtes et en secrets.",
    ],
    "strategy": [
        "Chaque décision compte. Chaque erreur aussi.",
        "Pour les fans de jeux de stratégie.",
        "La stratégie, c'est un art. {name} en est la preuve.",
        "Réfléchissez avant d'agir — ou subissez les conséquences.",
    ],
    "puzzle": [
        "Des énigmes qui vous feront douter de vous-même — dans le bon sens.",
        "Pour les cerveaux qui cherchent un vrai défi.",
        "Chaque niveau est une petite victoire. Osez les relever.",
        "Posez le téléphone. Branchez votre cerveau.",
    ],
    "horror": [
        "Jouez… si vous l'osez.",
        "La peur n'a jamais été aussi addictive.",
        "Éteignez les lumières. Mettez le casque. Bonne chance.",
        "L'horreur de {name} restera gravée dans votre mémoire.",
    ],
    "indie": [
        "Créé avec passion par une équipe indépendante. Ça se ressent.",
        "Pas de gros studio, juste un jeu sincère et original.",
        "L'indie gaming à son meilleur.",
        "Une vision unique, loin des formules éculées des AAA.",
    ],
    "multiplayer": [
        "Meilleur entre amis. Encore meilleur contre des inconnus.",
        "Le fun est décuplé à plusieurs — invitez vos amis.",
        "Compétitif, coopératif, ou les deux à la fois.",
        "Une communauté active vous attend dans {name}.",
    ],
    "co-op": [
        "À jouer en duo ou en équipe — la coopération avant tout.",
        "Parfait pour une soirée entre amis ou en couple.",
        "Ensemble, vous irez beaucoup plus loin.",
    ],
    "simulation": [
        "Aussi détaillé que fascinant — la simulation prise au sérieux.",
        "Pour ceux qui veulent vivre une autre vie… virtuellement.",
        "Chaque détail a son importance dans {name}.",
    ],
    "platformer": [
        "Précision, timing, persévérance — les ingrédients d'un bon platformer.",
        "Facile à prendre en main, difficile à maîtriser.",
        "Sautez, courez, recommencez. Vous allez adorer.",
    ],
    "open world": [
        "Un monde entier vous attend. Il suffit de l'explorer.",
        "Liberté totale dans un univers sans limites.",
        "L'open world comme vous ne l'avez jamais vécu.",
    ],
    "roguelike": [
        "Mourir n'est pas une fin — c'est le début.",
        "Chaque run est différent. La rejouabilité est infinie.",
        "Le genre roguelike sublimé dans {name}.",
    ],
    "adventure": [
        "Une aventure qui vous transporte ailleurs.",
        "L'exploration au cœur du gameplay.",
        "Partez à la découverte d'un univers qui ne ressemble à rien d'autre.",
    ],
    "sports": [
        "La compétition dans toute sa splendeur.",
        "Pour les fans de sport qui veulent aller plus loin.",
        "Montrez ce que vous avez dans le ventre.",
    ],
    "racing": [
        "Pied au plancher, cerveau en mode off.",
        "La vitesse comme seul objectif.",
        "Pour les amateurs de sensations fortes sur circuit.",
    ],
    "casual": [
        "Accessible à tous, agréable pour tous.",
        "Pas besoin d'être un joueur aguerri pour apprécier {name}.",
        "Détendez-vous avec quelque chose de léger et plaisant.",
    ],
    "free to play": [
        "Gratuit. Oui, vous avez bien lu.",
        "Commencez sans rien dépenser — et voyez si vous résistez.",
        "Zéro risque financier. Aucune excuse pour ne pas essayer.",
    ],
    "early access": [
        "Déjà jouable, déjà prometteur — et ça ne fait que commencer.",
        "Rejoignez les pionniers et façonnez le jeu avec vos retours.",
        "En accès anticipé, mais déjà incontournable.",
    ],
}

# -- Phrases de score/tendance
SCORE_PHRASES = {
    "viral":    [  # score > 80
        "Le score de tendance explose. {name} est en train de devenir viral.",
        "Difficile d'ignorer {name} quand les chiffres s'emballent comme ça.",
        "Tendance maximale. Tout Steam en parle.",
    ],
    "hot":      [  # score 40-80
        "Un score de tendance solide — {name} monte en puissance.",
        "En pleine ascension sur Steam.",
        "Les joueurs se l'arrachent en ce moment.",
    ],
    "rising":   [  # score 10-40
        "Un jeu qui commence à faire parler de lui.",
        "La communauté commence à s'y intéresser sérieusement.",
        "À surveiller de près — la tendance est à la hausse.",
    ],
    "fresh":    [  # score < 10
        "Tout juste sorti, déjà dans les radars.",
        "Un jeu récent qui mérite le coup d'œil.",
        "Encore peu connu, mais ça ne devrait pas durer.",
    ],
}

# -- Appels à l'action de clôture
CTAS = [
    "Disponible maintenant sur Steam.",
    "Lancez Steam et foncez.",
    "Votre prochain jeu vous attend sur Steam.",
    "Ajoutez-le à votre bibliothèque dès aujourd'hui.",
    "Ne le laissez pas passer.",
    "Retrouvez {name} sur Steam.",
    "Foncez sur la page Steam de {name} — vous ne le regretterez pas.",
    "La page Steam n'attend que vous.",
]

# -- CTA pour les coming soon
CTAS_UPCOMING = [
    "Ajoutez-le à votre wishlist dès maintenant sur Steam.",
    "Ne manquez pas la sortie — wishlistez {name} sur Steam.",
    "Suivez {name} sur Steam pour être notifié à sa sortie.",
    "Soyez parmi les premiers informés : wishlistez {name}.",
]


# ---------------------------------------------------------------------------
# LOGIQUE DE GÉNÉRATION
# ---------------------------------------------------------------------------

def classify_score(score: float) -> str:
    if score > 80:
        return "viral"
    elif score > 40:
        return "hot"
    elif score > 10:
        return "rising"
    return "fresh"


def pick(lst: list, **kwargs) -> str:
    """Choisit une phrase au hasard et remplace les placeholders."""
    template = random.choice(lst)
    return template.format(**{k: v for k, v in kwargs.items() if v is not None})


def find_tag_phrases(tags_str: str, name: str) -> list[str]:
    """Retourne 1 à 2 phrases pertinentes selon les tags détectés."""
    tags_lower = tags_str.lower() if tags_str else ""
    matches = []
    for keyword, phrases in TAG_PHRASES.items():
        if keyword in tags_lower:
            matches.append(pick(phrases, name=name))
    # On garde 2 phrases au maximum pour ne pas surcharger
    random.shuffle(matches)
    return matches[:2]


def generate_ad(game: dict) -> str:
    """
    Génère un texte publicitaire pour un jeu à partir de son entrée dict.

    Attendu :
        name, appid, release, score (float), recommendations (int),
        coming_soon (bool/str), tags (str), description (str)
    """
    name        = game.get("name", "Ce jeu")
    appid       = game.get("appid", "")
    release     = game.get("release", "")
    tags        = game.get("tags", "")
    description = html.unescape(game.get("description", "") or "")
    coming_soon = str(game.get("coming_soon", "")).lower() in ("true", "1", "yes")

    try:
        score = float(game.get("score", 0))
    except (ValueError, TypeError):
        score = 0.0

    try:
        reviews = int(game.get("recommendations", 0))
    except (ValueError, TypeError):
        reviews = 0

    parts = []

    # 1. Accroche d'ouverture
    if coming_soon:
        parts.append(pick(HOOKS_UPCOMING, name=name, release=release))
    elif reviews >= 500:
        parts.append(pick(HOOKS_POPULAR, name=name, reviews=reviews))
    else:
        parts.append(pick(HOOKS_GENERIC))

    # 2. Phrase de tendance
    tier = classify_score(score)
    parts.append(pick(SCORE_PHRASES[tier], name=name, score=score))

    # 3. Phrases liées aux tags (0, 1 ou 2 phrases)
    tag_lines = find_tag_phrases(tags, name)
    parts.extend(tag_lines)

    # 4. Description courte du jeu (tronquée proprement)
    if description:
        parts.append(f"« {description} »")

    # 5. Appel à l'action
    if coming_soon:
        parts.append(pick(CTAS_UPCOMING, name=name))
    else:
        parts.append(pick(CTAS, name=name))

    return "  ".join(parts)


# ---------------------------------------------------------------------------
# RENDU
# ---------------------------------------------------------------------------

def render_text(games: list[dict]) -> str:
    lines = []
    for i, game in enumerate(games, 1):
        name  = game.get("name", "?")
        appid = game.get("appid", "")
        url   = f"https://store.steampowered.com/app/{appid}" if appid else ""
        ad    = generate_ad(game)

        # lines.append(f"{'─'*70}")
        # lines.append(f"  #{i}  {name}")
        # if url:
        #     lines.append(f"  {url}")
        # lines.append("")
        # Wrap à 68 caractères
        for para in ad.split("  "):
            wrapped = textwrap.fill(para.strip(), width=68, initial_indent="  ", subsequent_indent="  ")
            lines.append(wrapped)
        lines.append("")
    # lines.append(f"{'─'*70}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Génère des textes publicitaires pour les jeux issus de steam_trending.py",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", "-i", required=True, metavar="FILE.csv",
        help="Fichier CSV exporté par steam_trending.py (--output)")
    parser.add_argument("--top", "-t", type=int, default=0, metavar="N",
        help="Nombre de jeux à traiter (0 = tous)")
    parser.add_argument("--output", "-o", metavar="FILE",
        help="Fichier de sortie (si absent : affichage console)")
    parser.add_argument("--section", "-s", choices=["released", "upcoming", "all"],
        default="all", help="Section à traiter")
    parser.add_argument("--seed", type=int, default=None,
        help="Graine aléatoire pour des résultats reproductibles")
    parser.add_argument("--pick", "-p", type=int, default=None, metavar="N",
        help="N'affiche que le jeu en position N (1-indexé, après filtrage --section et --top)")
    return parser.parse_args()


def load_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    games = load_csv(args.input)

    if args.section != "all":
        games = [g for g in games if g.get("section", "") == args.section]

    if args.top > 0:
        games = games[:args.top]

    if not games:
        print("Aucun jeu à traiter.")
        return

    if args.pick is not None:
        if args.pick < 1 or args.pick > len(games):
            print(f"❌ --pick {args.pick} hors limites (liste de {len(games)} jeux).")
            return
        games = [games[args.pick - 1]]

    output = render_text(games)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"✅ Exporté dans {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()