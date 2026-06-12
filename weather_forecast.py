import requests
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
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

    # -------------------------
    # GEO
    # -------------------------
    def get_coordinates(self, city: str, country: Optional[str] = None):
        params = {
            "name": city,
            "count": 5,
            "language": "en",
            "format": "json"
        }

        r = requests.get(self.GEO_URL, params=params)
        r.raise_for_status()
        data = r.json()

        if "results" not in data:
            raise ValueError(f"City not found: {city}")

        results = data["results"]

        if country:
            results = [x for x in results if x["country"].lower() == country.lower()]
            if not results:
                raise ValueError(f"No match found for {city} in {country}")

        best = results[0]

        return {
            "name": best["name"],
            "country": best["country"],
            "latitude": best["latitude"],
            "longitude": best["longitude"]
        }

    # -------------------------
    # BASIC WEATHER
    # -------------------------
    def get_weather(self, lat: float, lon: float):
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "wind_speed_10m_max",
                "wind_direction_10m_dominant",
                "weathercode",
                "sunrise",
                "sunset"
            ],
            "timezone": "auto"
        }

        r = requests.get(self.WEATHER_URL, params=params)
        r.raise_for_status()
        return r.json()

    def get_weather_by_city(self, city: str, country: Optional[str] = None) -> WeatherResult:
        loc = self.get_coordinates(city, country)
        data = self.get_weather(loc["latitude"], loc["longitude"])

        current = data["current_weather"]
        daily = data["daily"]

        forecast = [
            DailyForecast(
                date=datetime.strptime(daily["time"][i], "%Y-%m-%d"),
                temp_max=daily["temperature_2m_max"][i],
                temp_min=daily["temperature_2m_min"][i],
                precipitation_sum=daily["precipitation_sum"][i],
                wind_speed_max=daily["wind_speed_10m_max"][i],
                wind_direction=daily["wind_direction_10m_dominant"][i],
                weathercode=daily["weathercode"][i],
                sunrise=daily["sunrise"][i],
                sunset=daily["sunset"][i],
            )
            for i in range(len(daily["time"]))
        ]

        return WeatherResult(
            city=loc["name"],
            country=loc["country"],
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            current=CurrentWeather(**current),
            forecast=forecast
        )

    # -------------------------
    # NATIONAL WEEKLY FORECAST
    # -------------------------
    def get_national_weekly_forecast(self) -> List[Dict]:
        url = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/regions.geojson"
        regions = gpd.read_file(url).to_crs("EPSG:4326")

        def sample_points(polygon, n=3):
            minx, miny, maxx, maxy = polygon.bounds
            points = []

            while len(points) < n:
                p = Point(
                    np.random.uniform(minx, maxx),
                    np.random.uniform(miny, maxy)
                )
                if polygon.contains(p):
                    points.append(p)

            return points

        # 1. Generate 3 points per region
        region_points = []

        for _, row in regions.iterrows():
            pts = sample_points(row.geometry, 3)
            for p in pts:
                region_points.append({
                    "region": row["nom"],
                    "lat": p.y,
                    "lon": p.x
                })

        # 2. API request (single batch)
        coords = [(p["lat"], p["lon"]) for p in region_points]

        params = {
            "latitude": ",".join(str(p[0]) for p in coords),
            "longitude": ",".join(str(p[1]) for p in coords),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,wind_speed_10m_max",
            "timezone": "auto"
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

            for region in regions["nom"].unique():

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

                reg_summary[region] = {
                    "t_max": round(np.mean([v["tmax"] for v in vals])),
                    "t_min": round(np.mean([v["tmin"] for v in vals])),
                    "rain": round(np.mean([v["rain"] for v in vals])),
                    "wind": round(np.max([v["wind"] for v in vals])),
                    "weathercode": round(np.mean([v["code"] for v in vals]))
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

            results.append({
                "date": date,
                "regions": reg_summary,
                "avg_max": round(np.mean(all_tmax)) if all_tmax else None,
                "avg_min": round(np.mean(all_tmin)) if all_tmin else None,
                "max_abs": max(all_tmax) if all_tmax else None,
                "min_abs": min(all_tmin) if all_tmin else None
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
    3:  "nuageux à couvert", 16: "brume légère",            17: "orages isolés",
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


def wmo_label(code: int) -> str:
    return WMO_DESCRIPTIONS.get(code, "conditions variables")

def _pick(options: list) -> str:
    return random.choice(options)

def _prep(region: str) -> str:
    p, name, _ = REGION_META.get(region, ("en", region, False))
    return f"{p} {name}"

def _is_plural(region: str) -> bool:
    return REGION_META.get(region, ("", "", False))[2]

def _elide(mot: str, suite: str) -> str:
    voyelles = "aàâeéèêëiîïoôuùûœæhAÀÂEÉÈÊËIÎÏOÔUÙÛŒÆH"
    if suite and suite[0] in voyelles:
        return mot.rstrip("e") + "'" + suite
    return mot + " " + suite

def _format_prep_list(regions: list[str]) -> str | None:
    if not regions:
        return None
    if len(regions) == 1:
        return _prep(regions[0])
    return ", ".join(_prep(r) for r in regions[:-1]) + " et " + _prep(regions[-1])

def _verb_agree(regions: list[str], sing: str, plur: str) -> str:
    if len(regions) > 1:
        return plur
    return plur if _is_plural(regions[0]) else sing

def _classify_regions(regions: dict) -> dict:
    rainy, stormy, sunny, windy = [], [], [], []
    for name, d in regions.items():
        code = d["weathercode"]
        if 59 <= code <= 65:
            rainy.append(name)
        elif code in (17, 18, 19, 29, 42, 95, 96, 99):
            stormy.append(name)
        elif code <= 2:
            sunny.append(name)
        if d["wind"] >= 40:
            windy.append(name)
    return {"rainy": rainy, "stormy": stormy, "sunny": sunny, "windy": windy}

def _day_str(date: datetime) -> str:
    return f"{DAY_NAMES[date.weekday()]} {date.day} {MONTH_NAMES[date.month - 1]}"

def _verb_agree(regions: list[str], sing: str, plur: str) -> str:
    # Si une seule région, on accorde au singulier. Si plusieurs, au pluriel.
    return sing if len(regions) == 1 else plur

def generate_bulletin(day: dict, day_label: str = "aujourd'hui"):

    regions = day["regions"]

    avg_max = day["avg_max"]
    min_abs = round(day["min_abs"])
    max_abs = round(day["max_abs"])

    groups = _classify_regions(regions)

    all_codes = [r["weathercode"] for r in regions.values()]
    dominant = wmo_label(statistics.mode(all_codes))

    max_region = max(regions.items(), key=lambda x: x[1]["t_max"])

    candidates = {k: v for k, v in regions.items() if k != max_region[0]}
    min_region = min(candidates.items(), key=lambda x: x[1]["t_min"])

    max_t = max_region[1]["t_max"]
    min_t = min_region[1]["t_min"]

    max_loc = _prep(max_region[0])
    min_loc = _prep(min_region[0])

    lines = []

    # INTRO

    lines.append(_pick([
        f"{day_label.capitalize()}, le temps restera majoritairement {dominant} sur une grande partie du pays.",
        f"Pour {day_label}, l'ambiance sera globalement {dominant}, avec des températures comprises entre {min_abs} et {max_abs}°C.",
        f"Au programme {day_label} : un ciel souvent {dominant}.",
    ]))

    lines.append(
        f"La température moyenne sera de {avg_max}°C."
    )

    lines.append("")

    # PLUIE

    if groups["rainy"]:

        loc = _format_prep_list(groups["rainy"])

        lines.append(_pick([
            f"Côté précipitations, la pluie sera présente {loc}, parfois de façon soutenue.",
            f"Quelques passages pluvieux concerneront {loc}.",
            f"Un temps plus humide est attendu {loc}.",
        ]))

    # ORAGES

    if groups["stormy"]:

        loc = _format_prep_list(groups["stormy"])

        lines.append(_pick([
            f"Le risque orageux restera présent {loc}.",
            f"Des orages pourront éclater {loc} au fil de la journée.",
            f"La prudence sera de mise {loc} en raison d'un risque d'orages.",
        ]))

    # SOLEIL

    if groups["sunny"]:

        loc = _format_prep_list(groups["sunny"])

        lines.append(_pick([
            f"Le soleil s'imposera largement {loc}.",
            f"De belles éclaircies sont attendues {loc}.",
            f"Les habitants {loc} profiteront d'un temps largement ensoleillé.",
        ]))

    lines.append("")

    # TEMPÉRATURES

    lines.append(_pick([
        f"Les températures les plus élevées seront observées {max_loc} avec jusqu'à {max_t}°C.",
        f"La chaleur se concentrera {max_loc} avec {max_t}°C attendus.",
        f"{max_loc} enregistrera les valeurs les plus élevées avec {max_t}°C.",
    ]))

    lines.append(_pick([
        f"Au réveil, il fera seulement {min_t}°C {min_loc}.",
        f"La fraîcheur matinale sera surtout marquée {min_loc} avec {min_t}°C.",
        f"Les températures les plus basses au petit matin seront relevées {min_loc} avec {min_t}°C.",
    ]))

    # VENT

    if groups["windy"]:

        loc = _format_prep_list(groups["windy"])

        max_wind = max(r["wind"] for r in regions.values())

        lines.append("")

        lines.append(_pick([
            f"Le vent sera également à surveiller {loc}, avec des rafales pouvant atteindre {max_wind} km/h.",
            f"Des rafales jusqu'à {max_wind} km/h sont attendues {loc}.",
            f"Le vent soufflera assez fort {loc}, avec des pointes à {max_wind} km/h.",
        ]))

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