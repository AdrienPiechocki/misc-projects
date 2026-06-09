"""
summarizer.py — Résumé automatique de texte via TextRank
Dépendances : nltk, scikit-learn, numpy, networkx
    pip install nltk scikit-learn numpy networkx
"""

import re
import numpy as np
import networkx as nx
import nltk
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Téléchargement des ressources NLTK nécessaires (une seule fois)
for resource in ("punkt", "punkt_tab", "stopwords"):
    try:
        nltk.data.find(f"tokenizers/{resource}" if resource.startswith("punkt") else f"corpora/{resource}")
    except LookupError:
        nltk.download(resource, quiet=True)

from nltk.tokenize import sent_tokenize
from nltk.corpus import stopwords


# ---------------------------------------------------------------------------
# Étape 1 — Segmentation
# ---------------------------------------------------------------------------

def split_sentences(text: str, lang: str = "french") -> list[str]:
    """Découpe le texte en phrases propres."""
    sentences = sent_tokenize(text, language=lang)
    # Supprime les phrases trop courtes (bruit)
    return [s.strip() for s in sentences if len(s.split()) > 3]


# ---------------------------------------------------------------------------
# Étape 2 — Pré-traitement léger
# ---------------------------------------------------------------------------

def clean_sentence(sentence: str, lang: str = "french") -> str:
    """Retire la ponctuation et les stopwords pour la vectorisation."""
    stops = set(stopwords.words(lang))
    tokens = re.sub(r"[^a-zA-ZÀ-ÿ\s]", " ", sentence.lower()).split()
    return " ".join(t for t in tokens if t not in stops)


# ---------------------------------------------------------------------------
# Étape 3 — Graphe de similarité (TF-IDF + cosinus)
# ---------------------------------------------------------------------------

def build_similarity_graph(sentences: list[str], lang: str = "french") -> np.ndarray:
    """
    Construit une matrice de similarité cosinus entre toutes les paires
    de phrases vectorisées par TF-IDF.
    """
    cleaned = [clean_sentence(s, lang) for s in sentences]

    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform(cleaned)
    except ValueError:
        # Texte trop court ou vide après nettoyage
        return np.eye(len(sentences))

    sim_matrix = cosine_similarity(tfidf_matrix)

    # Neutralise la diagonale (auto-similarité) pour ne pas biaiser PageRank
    np.fill_diagonal(sim_matrix, 0.0)

    # Filtre les arêtes très faibles pour un graphe plus net
    threshold = sim_matrix.mean() * 0.5
    sim_matrix[sim_matrix < threshold] = 0.0

    return sim_matrix


# ---------------------------------------------------------------------------
# Étape 4 — TextRank
# ---------------------------------------------------------------------------

def rank_sentences(sim_matrix: np.ndarray) -> list[float]:
    """
    Applique PageRank sur le graphe de similarité.
    Retourne un score par phrase.
    """
    graph = nx.from_numpy_array(sim_matrix)

    # Gère le cas dégénéré (graphe sans arêtes)
    if graph.number_of_edges() == 0:
        return [1.0 / len(sim_matrix)] * len(sim_matrix)

    scores = nx.pagerank(graph, alpha=0.85, max_iter=200, tol=1e-6)
    return [scores[i] for i in range(len(sim_matrix))]


# ---------------------------------------------------------------------------
# Étape 5 — Sélection & reconstruction du résumé
# ---------------------------------------------------------------------------

def build_summary(
    original_sentences: list[str],
    scores: list[float],
    ratio: float = 0.3,
    min_sentences: int = 1,
    max_sentences: int | None = None,
) -> str:
    """
    Sélectionne les phrases avec les meilleurs scores et les restitue
    dans leur ordre d'apparition dans le texte original.

    ratio        — fraction du texte à conserver (0.3 = 30 %)
    min_sentences — nombre minimum de phrases dans le résumé
    max_sentences — nombre maximum (None = pas de limite)
    """
    n = len(original_sentences)
    k = max(min_sentences, round(n * ratio))
    if max_sentences is not None:
        k = min(k, max_sentences)
    k = min(k, n)  # sécurité

    # Top-k par score, puis retour à l'ordre original
    top_indices = sorted(
        sorted(range(n), key=lambda i: scores[i], reverse=True)[:k]
    )

    return " ".join(original_sentences[i] for i in top_indices)


# ---------------------------------------------------------------------------
# Interface publique
# ---------------------------------------------------------------------------

def summarize(
    text: str,
    ratio: float = 0.3,
    lang: str = "french",
    min_sentences: int = 1,
    max_sentences: int | None = None,
) -> str:
    """
    Résume `text` en extrayant les phrases les plus représentatives.

    Paramètres
    ----------
    text          : texte brut à résumer
    ratio         : part du texte à conserver (entre 0 et 1)
    lang          : langue pour la tokenisation et les stopwords
                    ("french", "english", "spanish", …)
    min_sentences : nombre minimum de phrases dans le résumé
    max_sentences : nombre maximum de phrases (None = sans limite)

    Retour
    ------
    Chaîne de caractères contenant le résumé.
    """
    if not text or not text.strip():
        return ""

    sentences = split_sentences(text, lang)

    if len(sentences) <= 2:
        return text.strip()

    sim_matrix = build_similarity_graph(sentences, lang)
    scores = rank_sentences(sim_matrix)
    return build_summary(sentences, scores, ratio, min_sentences, max_sentences)


# ---------------------------------------------------------------------------
# Démonstration
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SAMPLE_FR = """
Le changement climatique est l'un des défis les plus pressants de notre époque.
Les scientifiques s'accordent à dire que les émissions de gaz à effet de serre
d'origine humaine sont la principale cause du réchauffement observé depuis le milieu
du XXe siècle. La fonte des glaces polaires et la montée du niveau des mers menacent
des millions de personnes vivant en zones côtières. Les événements climatiques
extrêmes, tels que les vagues de chaleur, les sécheresses et les inondations,
augmentent en fréquence et en intensité. Les gouvernements du monde entier ont
signé l'Accord de Paris en 2015, s'engageant à limiter le réchauffement global
à 1,5 °C par rapport aux niveaux préindustriels. Cependant, les engagements actuels
restent insuffisants pour atteindre cet objectif. La transition vers les énergies
renouvelables, l'efficacité énergétique et les changements dans nos modes de
consommation sont indispensables. Les entreprises et les citoyens ont également
un rôle crucial à jouer pour réduire leur empreinte carbone. Sans action rapide
et concertée, les conséquences pour les générations futures pourraient être
irréversibles.
    """

    print("=== Texte original ===")
    print(SAMPLE_FR.strip())
    print()

    summary = summarize(SAMPLE_FR, ratio=0.35, lang="french")
    print("=== Résumé (35 %) ===")
    print(summary)
