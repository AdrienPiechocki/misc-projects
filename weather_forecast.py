import requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime
import json, os, random, statistics

# =========================
# MODELS
# =========================

@dataclass
class CurrentWeather:
    temperature: float
    windspeed: float
    winddirection: int
    weathercode: int
    time: str
    interval: int
    is_day: int


@dataclass
class DailyForecast:
    date: datetime
    temp_max: float
    temp_min: float
    precipitation_sum: float
    wind_speed_max: float
    wind_direction: int
    weathercode: int
    sunrise: str
    sunset: str


@dataclass
class WeatherResult:
    city: str
    country: str
    latitude: float
    longitude: float
    current: CurrentWeather
    forecast: List[DailyForecast]


# =========================
# CLIENT
# =========================

class OpenMeteoClient:
    GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

    # Villes représentatives par région (nom, lat, lon)
    # 3-4 villes par région pour couvrir la diversité géographique et climatique
    REGION_CITIES: Dict[str, List[tuple]] = {
        "Île-de-France": [
            ("Paris",        48.8566,  2.3522),
            ("Versailles",   48.8014,  2.1301),
            ("Meaux",        48.9600,  2.8878),
        ],
        "Centre-Val de Loire": [
            ("Orléans",      47.9029,  1.9093),
            ("Tours",        47.3941,  0.6848),
            ("Bourges",      47.0810,  2.3988),
            ("Chartres",     48.4469,  1.4899),
        ],
        "Bourgogne-Franche-Comté": [
            ("Dijon",        47.3220,  5.0415),
            ("Besançon",     47.2378,  6.0241),
            ("Mâcon",        46.3066,  4.8322),
            ("Belfort",      47.6376,  6.8640),
        ],
        "Normandie": [
            ("Rouen",        49.4431,  1.0993),
            ("Caen",         49.1829, -0.3707),
            ("Le Havre",     49.4944,  0.1079),
            ("Cherbourg",    49.6333, -1.6167),
        ],
        "Hauts-de-France": [
            ("Lille",        50.6292,  3.0573),
            ("Amiens",       49.8942,  2.2958),
            ("Reims",        49.2583,  4.0317),
            ("Calais",       50.9513,  1.8587),
        ],
        "Grand Est": [
            ("Strasbourg",   48.5734,  7.7521),
            ("Metz",         49.1193,  6.1757),
            ("Nancy",        48.6921,  6.1844),
            ("Mulhouse",     47.7508,  7.3359),
        ],
        "Pays de la Loire": [
            ("Nantes",       47.2184, -1.5536),
            ("Le Mans",      48.0061,  0.1996),
            ("Angers",       47.4784, -0.5632),
            ("Saint-Nazaire",47.2736, -2.2137),
        ],
        "Bretagne": [
            ("Rennes",       48.1173, -1.6778),
            ("Brest",        48.3905, -4.4860),
            ("Quimper",      47.9960, -4.0953),
            ("Saint-Malo",   48.6493, -2.0255),
        ],
        "Nouvelle-Aquitaine": [
            ("Bordeaux",     44.8378, -0.5792),
            ("Limoges",      45.8354,  1.2644),
            ("Poitiers",     46.5802,  0.3404),
            ("Biarritz",     43.4832, -1.5586),
            ("Périgueux",    45.1839,  0.7205),
        ],
        "Occitanie": [
            ("Toulouse",     43.6047,  1.4442),
            ("Montpellier",  43.6108,  3.8767),
            ("Nîmes",        43.8367,  4.3601),
            ("Perpignan",    42.6887,  2.8948),
            ("Carcassonne",  43.2130,  2.3491),
        ],
        "Auvergne-Rhône-Alpes": [
            ("Lyon",         45.7640,  4.8357),
            ("Grenoble",     45.1885,  5.7245),
            ("Clermont-Ferrand", 45.7797, 3.0863),
            ("Annecy",       45.8992,  6.1294),
            ("Saint-Étienne",45.4347,  4.3900),
        ],
        "Provence-Alpes-Côte d'Azur": [
            ("Marseille",    43.2965,  5.3698),
            ("Nice",         43.7102,  7.2620),
            ("Toulon",       43.1242,  5.9280),
            ("Avignon",      43.9493,  4.8059),
            ("Gap",          44.5594,  6.0784),
        ],
        "Corse": [
            ("Ajaccio",      41.9267,  8.7369),
            ("Bastia",       42.6976,  9.4507),
            ("Corte",        42.3062,  9.1503),
        ],
    }

    # -------------------------
    # NATIONAL WEEKLY FORECAST
    # -------------------------
    def get_national_weekly_forecast(self) -> List[Dict]:

        # 1. Aplatir les villes en liste ordonnée de points
        region_points = [
            {"region": region, "city": city, "lat": lat, "lon": lon}
            for region, cities in self.REGION_CITIES.items()
            for city, lat, lon in cities
        ]

        # 2. API request (single batch)
        coords = [(p["lat"], p["lon"]) for p in region_points]

        params = {
            "latitude": ",".join(str(p[0]) for p in coords),
            "longitude": ",".join(str(p[1]) for p in coords),
            "hourly": "temperature_2m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,wind_speed_10m_max",
            "timezone": "UTC"
        }

        r = requests.get(self.WEATHER_URL, params=params)
        data = r.json()

        if "error" in data:
            raise ValueError(f"API error: {data}")

        responses = data if isinstance(data, list) else [data]

        results = []

        for day_idx in range(5):

            try:
                date = responses[0]["daily"]["time"][day_idx]
            except:
                break

            reg_summary = {}

            for region in self.REGION_CITIES.keys():

                vals = []

                for i, pt in enumerate(region_points):
                    if pt["region"] != region:
                        continue

                    try:
                        d = responses[i]["daily"]

                        vals.append({
                            "tmax": d["temperature_2m_max"][day_idx],
                            "tmin": d["temperature_2m_min"][day_idx],
                            "rain": d["precipitation_sum"][day_idx],
                            "wind": d["wind_speed_10m_max"][day_idx],
                            "code": d["weathercode"][day_idx]
                        })
                    except:
                        continue

                if not vals:
                    continue
                
                corrected_codes = [
                    _effective_sky(
                        v["code"],
                        v["rain"],
                        v["tmax"]
                    )
                    for v in vals
                ]

                reg_summary[region] = {
                    "t_max": round(statistics.mean([v["tmax"] for v in vals])),
                    "t_min": round(statistics.mean([v["tmin"] for v in vals])),
                    "rain":  round(statistics.mean([v["rain"] for v in vals]), 1),
                    "wind":  round(max(v["wind"] for v in vals)),
                    "weathercode": statistics.mode(corrected_codes)
                }

            # National stats
            all_tmax = [
                responses[i]["daily"]["temperature_2m_max"][day_idx]
                for i in range(len(responses))
                if len(responses[i]["daily"]["temperature_2m_max"]) > day_idx
            ]

            all_tmin = [
                responses[i]["daily"]["temperature_2m_min"][day_idx]
                for i in range(len(responses))
                if len(responses[i]["daily"]["temperature_2m_min"]) > day_idx
            ]

            day_temps = []

            for i in range(len(responses)):
                try:
                    hourly = responses[i]["hourly"]
                    times = hourly["time"]
                    temps = hourly["temperature_2m"]

                    for t, temp in zip(times, temps):

                        # filtre jour exact (UTC)
                        if not t.startswith(date):
                            continue

                        # extraire heure UTC
                        hour = int(t[11:13])

                        # fenêtre "journée UTC"
                        if hour == 12:
                            day_temps.append(temp)

                except:
                    continue

            results.append({
                "date": date,
                "regions": reg_summary,
                "avg_max": round(statistics.mean(all_tmax)) if all_tmax else None,
                "avg_min": round(statistics.mean(all_tmin)) if all_tmin else None,
                "max_abs": max(day_temps) if day_temps else None,
                "min_abs": min(day_temps) if day_temps else None
            })

        return results

# =========================
# BULLETIN
# =========================

# (préposition, nom affiché, grammaticalement pluriel)
REGION_META = {
    "Île-de-France":               ("en",       "Île-de-France",               False),
    "Centre-Val de Loire":         ("en",       "Centre-Val de Loire",          False),
    "Bourgogne-Franche-Comté":     ("en",       "Bourgogne-Franche-Comté",      False),
    "Normandie":                   ("en",       "Normandie",                    False),
    "Hauts-de-France":             ("dans les", "Hauts-de-France",              True),
    "Grand Est":                   ("dans le",  "Grand Est",                    False),
    "Pays de la Loire":            ("dans les", "Pays de la Loire",             True),
    "Bretagne":                    ("en",       "Bretagne",                     False),
    "Nouvelle-Aquitaine":          ("en",       "Nouvelle-Aquitaine",           False),
    "Occitanie":                   ("en",       "Occitanie",                    False),
    "Auvergne-Rhône-Alpes":        ("en",       "Auvergne-Rhône-Alpes",         False),
    "Provence-Alpes-Côte d'Azur":  ("en",       "Provence-Alpes-Côte d'Azur",   False),
    "Corse":                       ("en",       "Corse",                        False),
}

WMO_DESCRIPTIONS = {
    0:  "ciel dégagé",       1:  "principalement dégagé",  2:  "partiellement nuageux",
    3:  "couvert",           16: "brume légère",            17: "orages isolés",
    18: "orages locaux",     19: "orages épars",            29: "averses orageuses",
    31: "légèrement nuageux",38: "nébulosité variable",     42: "averses possibles",
    45: "brouillard",        51: "bruine légère",           53: "bruine modérée",
    55: "bruine dense",      59: "averses et brouillard",
    61: "pluie faible",      63: "pluie modérée",           65: "pluie forte",
    71: "neige légère",      73: "neige modérée",           75: "neige forte",
    80: "averses légères",   81: "averses modérées",        82: "averses violentes",
    95: "orage",             96: "orage avec grêle",        99: "orage violent avec grêle",
}

DAY_NAMES   = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTH_NAMES = ["janvier","février","mars","avril","mai","juin",
               "juillet","août","septembre","octobre","novembre","décembre"]


# =========================
# ZONES MÉTÉO
# =========================

ZONE_LABELS = {
    "nord": "dans le nord du pays",
    "sud": "dans le sud du pays",
    "est": "dans l'est du pays",
    "ouest": "sur la façade ouest",
    "nord-ouest": "dans le nord-ouest",
    "nord-est": "dans le nord-est",
    "sud-ouest": "dans le sud-ouest",
    "sud-est": "dans le sud-est",
    "centre": "sur les régions centrales",
}

ZONE_REGIONS = {
    "nord": {
        "Hauts-de-France",
        "Normandie",
        "Île-de-France",
        "Grand Est",
    },

    "ouest": {
        "Bretagne",
        "Pays de la Loire",
        "Normandie",
        "Nouvelle-Aquitaine",
    },

    "est": {
        "Grand Est",
        "Bourgogne-Franche-Comté",
        "Auvergne-Rhône-Alpes",
    },

    "sud": {
        "Occitanie",
        "Provence-Alpes-Côte d'Azur",
        "Corse",
        "Nouvelle-Aquitaine",
        "Auvergne-Rhône-Alpes",
    },

    "nord-ouest": {
        "Normandie",
        "Bretagne",
        "Pays de la Loire",
        "Hauts-de-France",
    },

    "nord-est": {
        "Hauts-de-France",
        "Grand Est",
        "Bourgogne-Franche-Comté",
    },

    "sud-ouest": {
        "Nouvelle-Aquitaine",
        "Occitanie",
    },

    "sud-est": {
        "Provence-Alpes-Côte d'Azur",
        "Corse",
        "Auvergne-Rhône-Alpes",
    },

    "centre": {
        "Centre-Val de Loire",
        "Île-de-France",
        "Bourgogne-Franche-Comté",
    },
}

def wmo_label(code: int) -> str:
    return WMO_DESCRIPTIONS.get(code, "conditions variables")

def _pick(options: list) -> str:
    return random.choice(options)

def _cap(s: str) -> str:
    """Capitalise le premier caractère d'une chaîne."""
    return s[:1].upper() + s[1:] if s else s

def _prep(region: str) -> str:
    p, name, _ = REGION_META.get(region, ("en", region, False))
    return f"{p} {name}"

def _prep_cap(region: str) -> str:
    """Préposition + nom avec majuscule en début de phrase."""
    return _cap(_prep(region))

def _is_plural(region: str) -> bool:
    return REGION_META.get(region, ("", "", False))[2]

def _format_prep_list(regions: list[str]) -> str | None:
    if not regions:
        return None
    if len(regions) == 1:
        return _prep(regions[0])
    return ", ".join(_prep(r) for r in regions[:-1]) + " et " + _prep(regions[-1])

def _verb_agree(regions: list[str], sing: str, plur: str) -> str:
    return sing if len(regions) == 1 else plur

def _day_str(date: datetime) -> str:
    return f"{DAY_NAMES[date.weekday()]} {date.day} {MONTH_NAMES[date.month - 1]}"

def _temp_qualifier(t: float) -> str:
    """Qualificatif narratif pour une température maximale."""
    if t >= 35:   return "caniculaire"
    if t >= 30:   return "très chaude"
    if t >= 25:   return "estivale"
    if t >= 20:   return "agréable"
    if t >= 15:   return "douce"
    if t >= 10:   return "fraîche"
    return "froide"

def _amplitude_comment(min_abs: float, max_abs: float) -> str | None:
    """Commentaire sur l'amplitude thermique si elle est notable."""
    amp = max_abs - min_abs
    if amp >= 18:
        return _pick([
            f"L'amplitude thermique sera importante, entre {round(min_abs)} et {round(max_abs)}° à midi, à l'échelle du pays.",
            f"Attention aux écarts : de {round(min_abs)}° à {round(max_abs)}° en journée, en fonction des régions.",
        ])
    if amp >= 12:
        return _pick([
            f"Les températures varieront entre {round(min_abs)} et {round(max_abs)}° à midi, selon les régions.",
            f"En journée, on notera des contrastes sensibles, de {round(min_abs)} à {round(max_abs)}°.",
        ])
    return None

def _effective_sky(code: int, rain: float, t_max: float) -> int:
    """
    Corrige le code WMO d'une région en croisant pluie et température.

    Open-Meteo renvoie fréquemment code=3 (couvert) pour des journées chaudes
    et sèches — biais connu du modèle. On déduit le ciel réel :
      - Pluie significative (≥ 1 mm) → on garde le code tel quel ou on force 61
      - Code nuageux/couvert + pas de pluie + journée chaude → on reclasse en
        partiellement nuageux (2) ou dégagé (1) selon la chaleur
      - Orages/neige → jamais modifiés
    """
    STORMY = {17, 18, 19, 29, 42, 95, 96, 99}
    SNOWY  = {71, 73, 75}

    # Phénomènes intenses : on ne touche pas
    if code in STORMY or code in SNOWY:
        return code

    # Pluie réelle confirmée par les mm → le code pluvieux est fiable
    if rain >= 1.0 and 51 <= code <= 82:
        return code

    # Code nuageux/couvert (3, 45 brouillard, 31, 38, 2…) + journée sèche
    if code in (2, 3, 31, 38, 45) and rain < 1.0:
        if rain < 0.5:
            if t_max >= 30:
                return 0      # ciel dégagé
            elif t_max >= 24:
                return 1      # principalement dégagé
            else:
                return 2      # partiellement nuageux
        if t_max >= 22:
            # Journée douce sans pluie → partiellement nuageux
            return 2
        # Journée fraîche et sèche → on garde le nuageux (peut être réel)
        return code

    return code

def _smart_region_list(regions: list[str]) -> str | None:
    """
    Remplace les longues listes de régions par une formulation géographique.
    """

    if not regions:
        return None

    regions = sorted(set(regions))
    n = len(regions)

    # Peu de régions -> liste détaillée
    if n <= 2:
        return _format_prep_list(regions)

    # Très grande couverture
    if n >= 10:
        return "sur une grande partie du pays"

    if n >= 7:
        return "sur une large moitié du pays"

    region_set = set(regions)

    best_zone = None
    best_score = 0

    for zone_name, zone_regions in ZONE_REGIONS.items():

        overlap = len(region_set & zone_regions)

        coverage = overlap / len(region_set)

        if overlap >= 3 and coverage > best_score:
            best_score = coverage
            best_zone = zone_name

    if best_zone and best_score >= 0.70:
        return ZONE_LABELS[best_zone]

    # Cas intermédiaire : on garde les régions
    return _format_prep_list(regions)

def _dominant_sky(regions: dict) -> tuple[str, str]:

    total = len(regions)

    sunny = 0
    partly = 0
    rainy = 0
    stormy = 0
    cloudy = 0

    for d in regions.values():

        code = _effective_sky(
            d["weathercode"],
            d["rain"],
            d["t_max"]
        )

        rain = d["rain"]

        if code in (17, 18, 19, 29, 42, 95, 96, 99):
            stormy += 1

        elif rain >= 1.0:
            rainy += 1

        elif code <= 1:
            sunny += 1

        elif code == 2:
            partly += 1

        else:
            cloudy += 1

    sunny_pct = sunny / total
    partly_pct = partly / total
    rainy_pct = rainy / total
    stormy_pct = stormy / total
    cloudy_pct = cloudy / total

    if stormy_pct >= 0.25:
        return "orageux par endroits", "stormy"

    if rainy_pct >= 0.50:
        return "pluvieux sur une large partie du pays", "rainy"

    if rainy_pct >= 0.25:
        return "perturbé avec quelques passages pluvieux", "rainy"

    if sunny_pct >= 0.60:
        return "largement ensoleillé", "sunny"

    if sunny_pct + partly_pct >= 0.60:
        return "partiellement ensoleillé", "partly"

    if cloudy_pct >= 0.60:
        return "nuageux sur la majeure partie du pays", "cloudy"

    return "variable selon les régions", "partly"


def _classify_regions(regions: dict) -> dict:
    """
    Classe les régions selon le temps réellement attendu.

    Une région n'est considérée pluvieuse que si les précipitations
    prévues atteignent un seuil significatif.
    """

    rainy = []
    stormy = []
    sunny = []
    partly = []
    cloudy_dry = []
    windy = []

    STORM_CODES = {17, 18, 19, 29, 42, 95, 96, 99}

    for name, d in regions.items():

        code = _effective_sky(
            d["weathercode"],
            d["rain"],
            d["t_max"]
        )

        rain = d["rain"]

        # Orages
        if code in STORM_CODES:
            stormy.append(name)

        # Pluie réellement significative
        elif rain >= 1.0:
            rainy.append(name)

        # Soleil
        elif code <= 1:
            sunny.append(name)

        # Éclaircies
        elif code == 2:
            partly.append(name)

        # Nuageux mais sec
        else:
            cloudy_dry.append(name)

        # Vent fort
        if d["wind"] >= 50:
            windy.append(name)

    return {
        "rainy": rainy,
        "stormy": stormy,
        "sunny": sunny,
        "partly": partly,
        "cloudy_dry": cloudy_dry,
        "windy": windy,
    }


def _wind_comment(regions: dict) -> str | None:
    """Phrase sur le vent : fort si rafales > 50 km/h, calme si tout < 25."""
    max_wind  = max(r["wind"] for r in regions.values())
    mean_wind = round(sum(r["wind"] for r in regions.values()) / len(regions))
    windy_regs = [n for n, d in regions.items() if d["wind"] >= 50]

    if windy_regs:
        loc = _smart_region_list(windy_regs)
        return _pick([
            f"Le vent sera à surveiller {loc}, avec des rafales pouvant dépasser {max_wind} km/h.",
            f"Des rafales soutenues jusqu'à {max_wind} km/h sont attendues {loc}.",
            f"Le vent soufflera en bourrasques {loc}, avec des pointes à {max_wind} km/h.",
        ])
    if mean_wind <= 15:
        return _pick([
            "Le vent sera globalement calme et discret sur l'ensemble du territoire.",
            "Aucun épisode venteux significatif n'est à signaler ce jour.",
        ])
    if mean_wind <= 30:
        return _pick([
            f"Le vent sera modéré, soufflant en moyenne autour de {mean_wind} km/h.",
            f"Une petite brise de {mean_wind} km/h en moyenne animera la journée sans excès.",
        ])
    return None  # vent moyen, rien à signaler de particulier

def generate_bulletin(day: dict, day_label: str = "aujourd'hui") -> str:

    regions  = day["regions"]
    avg_max  = day["avg_max"]
    min_abs  = day["min_abs"]
    max_abs  = day["max_abs"]

    groups   = _classify_regions(regions)
    sky_label, sky_cat = _dominant_sky(regions)

    # Région la + chaude (t_max) et la + froide (t_min), non confondues
    max_region = max(regions.items(), key=lambda x: x[1]["t_max"])
    min_region = min(
        ((k, v) for k, v in regions.items() if k != max_region[0]),
        key=lambda x: x[1]["t_min"]
    )
    max_t   = max_region[1]["t_max"]
    min_t   = min_region[1]["t_min"]
    max_loc = _prep(max_region[0])
    min_loc = _prep(min_region[0])

    temp_qual   = _temp_qualifier(avg_max)
    amplitude   = _amplitude_comment(min_abs, max_abs)

    lines = []

    # ── INTRO ────────────────────────────────────────────────────────────────

    lines.append(_pick([
        f"{_cap(day_label)}, le temps sera {sky_label} sur une grande partie du pays.",
        f"Pour {day_label}, on attend un ciel {sky_label}, avec une journée {temp_qual}s.",
        f"Au programme {day_label} : un temps {sky_label} et des températures {temp_qual}s.",
    ]))

    lines.append(_pick([
        f"Les maximales nationales tourneront autour de {avg_max}°.",
        f"La température moyenne en journée atteindra {avg_max}°.",
        f"On retiendra une moyenne nationale de {avg_max}° en journée.",
    ]))

    if amplitude:
        lines.append(amplitude)

    lines.append("")

    # ── PRÉCIPITATIONS / ORAGES ───────────────────────────────────────────────

    if groups["stormy"]:
        loc = _smart_region_list(groups["stormy"])
        lines.append(_pick([
            f"La prudence sera de mise {loc} : des orages sont attendus, localement forts.",
            f"Des orages pourront éclater {loc} au fil de la journée, avec un risque de grêle.",
            f"Le risque orageux sera bien présent {loc}, à surveiller de près.",
        ]))

    if groups["rainy"]:
        loc = _smart_region_list(groups["rainy"])
        # quantifier la pluie si disponible
        max_rain = max(regions[r]["rain"] for r in groups["rainy"])
        rain_intensity = "de façon soutenue" if max_rain >= 10 else "par intermittence"
        lines.append(_pick([
            f"Des précipitations sont attendues {loc}, {rain_intensity}.",
            f"La pluie s'imposera {loc}, avec jusqu'à {max_rain} mm localement.",
            f"Un temps humide sera prévu {loc}, parfois {rain_intensity}.",
        ]))

    if groups["cloudy_dry"] and sky_cat == "cloudy" and not groups["rainy"] and not groups["stormy"]:
        # ciel couvert mais sec : le préciser pour éviter l'amalgame "couvert = pluie"
        loc = _smart_region_list(groups["cloudy_dry"])
        lines.append(_pick([
            f"Le ciel restera couvert {loc} mais sans précipitation notable.",
            f"Malgré des nuages persistants {loc}, la journée devrait rester sèche.",
            f"Les nuages domineront {loc} sans apporter de pluie significative.",
        ]))

    # ── SOLEIL / ÉCLAIRCIES ───────────────────────────────────────────────────

    all_sunny = groups["sunny"] + groups["partly"]

    if groups["sunny"] and groups["partly"]:
        loc_sun   = _smart_region_list(groups["sunny"])
        loc_part  = _smart_region_list(groups["partly"])
        lines.append(_pick([
            f"Le soleil brillera généreusement {loc_sun}, tandis que des éclaircies alterneront avec les nuages {loc_part}.",
            f"Beau temps {loc_sun} ; {loc_part}, le ciel sera plus nuancé mais les éclaircies seront présentes.",
        ]))
    elif groups["sunny"]:
        loc = _smart_region_list(groups["sunny"])
        lines.append(_pick([
            f"Le soleil s'imposera {loc}, offrant de belles journées ensoleillées.",
            f"Beau fixe {loc} avec un ciel largement dégagé tout au long de la journée.",
            f"Les habitants {loc} profiteront d'un ensoleillement généreux.",
        ]))
    elif groups["partly"]:
        loc = _smart_region_list(groups["partly"])
        lines.append(_pick([
            f"Des éclaircies alterneront avec les nuages {loc}.",
            f"Le ciel sera partiellement dégagé {loc}, avec de belles fenêtres ensoleillées.",
            f"Un temps mitigé {loc} : des nuages, mais aussi de belles éclaircies.",
        ]))

    lines.append("")

    # ── TEMPÉRATURES ─────────────────────────────────────────────────────────

    # Chaleur
    if max_t >= 30:
        lines.append(_pick([
            f"La chaleur sera particulièrement marquée {max_loc}, où le thermomètre atteindra {max_t}°.",
            f"C'est {max_loc} que l'on enregistrera les pics les plus élevés avec {max_t}°.",
            f"Jusqu'à {max_t}° {max_loc} : la journée s'annonce chaude.",
        ]))
    else:
        lines.append(_pick([
            f"Les maximales les plus douces seront atteintes {max_loc} avec {max_t}°.",
            f"Les températures les plus élevées, {max_t}°, seront relevées {max_loc}.",
            f"{_prep_cap(max_region[0])}, on attend jusqu'à {max_t}° en après-midi.",
        ]))

    # Fraîcheur matinale
    if min_t <= 8:
        lines.append(_pick([
            f"Les matins seront froids {min_loc}, avec seulement {min_t}° au lever du jour.",
            f"Attention à la fraîcheur matinale {min_loc} : le thermomètre descendra jusqu'à {min_t}°.",
            f"Le petit matin sera glacial {min_loc} avec {min_t}°.",
        ]))
    elif min_t <= 14:
        lines.append(_pick([
            f"La fraîcheur sera surtout sensible {min_loc} au réveil, avec {min_t}°.",
            f"On notera des matins frais {min_loc} avec {min_t}° avant le lever du soleil.",
            f"Au petit matin, {min_t}° {min_loc} : une petite laine ne sera pas de trop.",
        ]))
    else:
        lines.append(_pick([
            f"Les nuits resteront douces : {min_t}° {min_loc} au plus bas.",
            f"Même au réveil, les températures seront clémentes : {min_t}° {min_loc}.",
        ]))

    # ── VENT ──────────────────────────────────────────────────────────────────

    wind_line = _wind_comment(regions)
    if wind_line:
        lines.append("")
        lines.append(wind_line)

    return "\n".join(lines)


# ── Script hebdomadaire ───────────────────────────────────────────────────────

WEEK_INTROS = [
    "Bonjour à toutes et à tous. Voici votre point météo pour les cinq prochains jours.",
    "Bienvenue dans votre bulletin météo national. Regardons ensemble les tendances des prochains jours.",
    "Bonjour et merci de nous rejoindre pour votre rendez-vous météo de la semaine.",
]

TRANSITIONS = [
    "Passons maintenant à {dstr}.",
    "Direction {dstr}.",
    "Voyons ce qui nous attend pour {dstr}.",
    "Intéressons-nous à {dstr}.",
    "Poursuivons avec {dstr}.",
]

WEEK_OUTROS = [
    "C'est la fin de ce bulletin météo. Excellente semaine à toutes et à tous.",
    "Merci de votre attention et à très bientôt pour un nouveau point météo.",
    "Très bonne semaine à toutes et à tous et à bientôt.",
]


def generate_weekly_script(forecast: list[dict]) -> str:
    if not forecast:
        return ""

    parts = [_pick(WEEK_INTROS), ""]

    for i, day in enumerate(forecast):
        date  = datetime.strptime(day["date"], "%Y-%m-%d")
        dstr  = _day_str(date)
        label = f"ce {DAY_NAMES[date.weekday()]}"  # "ce vendredi", "ce samedi"…

        if i == 0:
            # Premier jour : intro directe
            parts.append(f"On commence avec {dstr}.")
            parts.append("")
        else:
            # Transition vers le jour suivant
            parts.append(_pick(TRANSITIONS).format(dstr=dstr))
            parts.append("")

        parts.append(generate_bulletin(day, day_label=label))
        parts.append("")

    parts.append(_pick(WEEK_OUTROS))
    return "\n".join(parts)

def generate_daily_script(forecast: list[dict]) -> str:
    if not forecast:
        return ""

    day = forecast[0]

    date = datetime.strptime(day["date"], "%Y-%m-%d")
    dstr = _day_str(date)

    label = f"ce {DAY_NAMES[date.weekday()]}"

    parts = [
        f"Bonjour à toutes et à tous. Voici votre bulletin météo pour {dstr}.",
        "",
        generate_bulletin(day, day_label=label),
        "",
        f"C'était votre météo pour {dstr}. Excellente journée à toutes et à tous."
    ]

    return "\n".join(parts)



if __name__ == "__main__":
    client = OpenMeteoClient()
    data = generate_weekly_script(client.get_national_weekly_forecast())
    print(data)