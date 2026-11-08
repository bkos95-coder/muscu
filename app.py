"""
AGEOTERRA Suite — module Météo multi-modèles
Moyenne de 5 modèles numériques (via Open-Meteo) pour le widget KWGT.

  GET /meteo/api?k=TOKEN&lat=43.29&lon=5.62   -> JSON compact pour le widget
  GET /meteo/?k=TOKEN&lat=43.29&lon=5.62      -> page détail (comparatif des modèles)
  GET /meteo/sante                            -> contrôle de santé (sans token)

Sans lat/lon valides -> Gémenos par défaut.
"""
import hmac
import math
import sqlite3
import sys
import json
import os
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, Flask, abort, jsonify, render_template_string, request

VERSION = "1.9 - 08/11/2026"
TOKEN = os.environ.get("METEO_TOKEN", "")
PREFIX = os.environ.get("APP_PREFIX", "/meteo")  # "" si Caddy retire le préfixe (handle_path)
TZ = ZoneInfo("Europe/Paris")
CACHE_TTL = 30 * 60
NB_JOURS = 7
DB = os.environ.get("METEO_DB", "/var/lib/meteo/meteo.db")
# Points de référence pour l'apprentissage (prévisions archivées puis comparées au réel)
REFS = {"gemenos": (43.2950, 5.6283)}
MIN_N = 10        # nb mini de jours évalués avant d'utiliser l'apprentissage
K_LISSAGE = 30    # plus il est grand, plus l'apprentissage remplace lentement les poids initiaux

# Poids initiaux selon l'échéance (0 = aujourd'hui/demain, 1 = J+2/J+3, 2 = J+4 à J+6)
PRIOR = {
    0: {"meteofrance_seamless": 3.0, "ecmwf_ifs025": 2.0, "icon_seamless": 2.0, "ukmo_seamless": 1.5, "gfs_seamless": 1.0},
    1: {"meteofrance_seamless": 1.5, "ecmwf_ifs025": 2.5, "icon_seamless": 1.5, "ukmo_seamless": 1.5, "gfs_seamless": 1.0},
    2: {"meteofrance_seamless": 1.0, "ecmwf_ifs025": 3.0, "icon_seamless": 1.5, "ukmo_seamless": 1.5, "gfs_seamless": 1.0},
}
# Alertes (ntfy)
NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
SEUILS = {"pluie_mm": 0.5, "rafales_kmh": 60, "gel_c": 0.0, "canicule_c": 35.0}
SILENCE = (22, 7)  # pas de notification entre 22h et 7h (sauf orage et rafales)
LIB_ECH = {0: "Aujourd’hui et demain", 1: "J+2 et J+3", 2: "J+4 à J+6"}
DEFAUT = (43.2950, 5.6283, "Gémenos")

MODELES = {
    "meteofrance_seamless": "Météo-France (AROME/ARPEGE)",
    "ecmwf_ifs025": "ECMWF (européen)",
    "icon_seamless": "ICON (allemand)",
    "gfs_seamless": "GFS (américain)",
    "ukmo_seamless": "UKMO (britannique)",
}
HOURLY = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_gusts_10m",
          "precipitation", "weather_code", "soil_temperature_6cm", "is_day", "cloud_cover",
          "apparent_temperature", "wind_direction_10m"]
DAILY = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "wind_speed_10m_max",
         "wind_gusts_10m_max", "et0_fao_evapotranspiration", "weather_code",
         "sunrise", "sunset", "uv_index_max", "cloud_cover_mean"]
COURT = {"meteofrance_seamless": "mf", "ecmwf_ifs025": "ecmwf", "icon_seamless": "icon",
         "gfs_seamless": "gfs", "ukmo_seamless": "ukmo"}
ABREV = {"mf": "MF", "ecmwf": "EC", "icon": "IC", "gfs": "GF", "ukmo": "UK"}
# Habillage du widget : (couleur haut, couleur bas, couleur du texte)
FONDS = {
    "soleil": ("#3E8FD6", "#86C3EE", "#FFFFFF"), "eclaircie": ("#5288BF", "#9DBFE0", "#FFFFFF"),
    "couvert": ("#6E7B87", "#9AA5AF", "#FFFFFF"), "brouillard": ("#9AA3A8", "#C7CCCF", "#1D2420"),
    "pluie": ("#3F5168", "#687D94", "#FFFFFF"), "neige": ("#A9BBCF", "#DDE6EF", "#1D2420"),
    "orage": ("#272C38", "#4A5366", "#FFFFFF"), "nuit": ("#141C36", "#2C3858", "#FFFFFF"),
}
PALETTE_T = [(-5, (91, 141, 239)), (5, (79, 179, 217)), (15, (124, 196, 127)),
             (22, (242, 179, 61)), (30, (232, 96, 60)), (38, (184, 50, 42))]
BLOCS = "▁▂▃▄▅▆▇█"
JOURS_COURTS = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
CIEL = {
    0: ("Ensoleillé", "☀️"), 1: ("Peu nuageux", "🌤️"), 2: ("Partiellement nuageux", "⛅"),
    3: ("Couvert", "☁️"), 4: ("Nuageux", "🌥️"), 45: ("Brouillard", "🌫️"), 48: ("Brouillard givrant", "🌫️"),
    51: ("Quelques gouttes", "🌦️"), 53: ("Bruine", "🌦️"), 55: ("Bruine forte", "🌧️"),
    56: ("Bruine verglaçante", "🌧️"), 57: ("Bruine verglaçante", "🌧️"),
    61: ("Pluie faible", "🌦️"), 63: ("Pluie", "🌧️"), 65: ("Forte pluie", "🌧️"),
    66: ("Pluie verglaçante", "🌧️"), 67: ("Pluie verglaçante", "🌧️"),
    71: ("Neige faible", "🌨️"), 73: ("Neige", "🌨️"), 75: ("Forte neige", "❄️"), 77: ("Grésil", "🌨️"),
    80: ("Averses", "🌦️"), 81: ("Averses", "🌧️"), 82: ("Fortes averses", "⛈️"),
    85: ("Averses de neige", "🌨️"), 86: ("Averses de neige", "❄️"),
    95: ("Orage", "⛈️"), 96: ("Orage avec grêle", "⛈️"), 99: ("Orage avec grêle", "⛈️"),
}


# ---------- Récupération Open-Meteo ----------

def appel_open_meteo(lat, lon):
    params = {
        "latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}",
        "hourly": ",".join(HOURLY), "daily": ",".join(DAILY),
        "models": ",".join(MODELES), "timezone": "Europe/Paris",
        "forecast_days": NB_JOURS, "wind_speed_unit": "kmh",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params, safe=",")
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


POLLENS = {"alder_pollen": "aulne", "birch_pollen": "bouleau", "grass_pollen": "graminées",
           "mugwort_pollen": "armoise", "olive_pollen": "olivier", "ragweed_pollen": "ambroisie"}


def appel_air(lat, lon):
    """Qualité de l'air et pollens (Open-Meteo / Copernicus CAMS). None si indisponible."""
    try:
        params = {"latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}", "timezone": "Europe/Paris",
                  "current": ",".join(["european_aqi", "pm2_5", "pm10", "ozone", *POLLENS])}
        url = "https://air-quality-api.open-meteo.com/v1/air-quality?" + urllib.parse.urlencode(params, safe=",")
        with urllib.request.urlopen(url, timeout=15) as r:
            cur = json.load(r).get("current", {})
    except Exception:
        return None
    aqi = cur.get("european_aqi")
    if aqi is None:
        return None
    niveaux = [(20, "Bon", "ok"), (40, "Correct", "ok"), (60, "Moyen", "moy"),
               (80, "Médiocre", "bad"), (100, "Très mauvais", "bad"), (10**9, "Extrêmement mauvais", "bad")]
    label, classe = next((l, c) for seuil, l, c in niveaux if aqi < seuil)
    pollens = []
    for k, nom in POLLENS.items():
        v = cur.get(k)
        if v is not None and v >= 1:
            niv = "faible" if v < 10 else "modéré" if v < 50 else "élevé"
            pollens.append({"nom": nom, "valeur": round(v), "niveau": niv})
    return {"aqi": round(aqi), "label": label, "classe": classe,
            "pm25": round(cur.get("pm2_5") or 0), "pm10": round(cur.get("pm10") or 0),
            "ozone": round(cur.get("ozone") or 0), "pollens": pollens}


def premier(d):
    return next(iter(d.values()), None) if d else None


def jour_commun(bloc, var, j):
    """Valeur indépendante du modèle (lever/coucher, parfois UV) : clé suffixée ou non."""
    s = bloc.get(var) or []
    v = s[j] if j < len(s) else None
    return v if v is not None else premier(serie(bloc, var, j))


def heure(iso):
    return iso[11:16] if isinstance(iso, str) and len(iso) >= 16 else None


_communes = {}


def nom_commune(lat, lon):
    """Commune la plus proche via le géocodage inverse IGN (Géoplateforme). None hors France."""
    cle = (round(lat, 2), round(lon, 2))
    if cle in _communes:
        return _communes[cle]
    nom = None
    try:
        params = {"lon": f"{lon:.5f}", "lat": f"{lat:.5f}", "index": "address", "limit": 1}
        url = "https://data.geopf.fr/geocodage/reverse?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=8) as r:
            feats = json.load(r).get("features") or []
        if feats:
            nom = feats[0].get("properties", {}).get("city")
    except Exception:
        return None  # pas mis en cache : nouvel essai la prochaine fois
    if len(_communes) > 500:
        _communes.clear()
    _communes[cle] = nom
    return nom


# ---------- Calculs ----------

def serie(bloc, var, i):
    """{modèle: valeur} pour une variable à l'index i (modèles sans donnée ignorés)."""
    out = {}
    for m in MODELES:
        s = bloc.get(f"{var}_{m}") or []
        if i < len(s) and s[i] is not None:
            out[m] = s[i]
    return out


def moy(d, n=1, w=None):
    """Moyenne (pondérée par w = {modèle: poids} si fourni)."""
    if not d:
        return None
    if w:
        tot = sum(w.get(m, 1.0) for m in d)
        v = round(sum(val * w.get(m, 1.0) for m, val in d.items()) / tot, n)
    else:
        v = round(statistics.fmean(d.values()), n)
    return int(v) if n == 0 else v


def arr(v, n=1):
    return None if v is None else round(v, n)


def ecart(d, n=1):
    return round(max(d.values()) - min(d.values()), n) if len(d) > 1 else 0.0


def code_dominant(d):
    """Code temps le plus fréquent entre modèles ; à égalité, le plus sévère."""
    if not d:
        return None
    c = Counter(int(v) for v in d.values())
    top = max(c.values())
    return max(k for k, v in c.items() if v == top)


CARDINAUX = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


def direction_moy(dirs, w=None):
    """Direction moyenne du vent (moyenne vectorielle pondérée), en degrés d'où il vient."""
    if not dirs:
        return None
    sx = sy = 0.0
    for m, dg in dirs.items():
        p = (w or {}).get(m, 1.0)
        sx += p * math.sin(math.radians(dg))
        sy += p * math.cos(math.radians(dg))
    return round(math.degrees(math.atan2(sx, sy))) % 360


def cardinal(dg):
    return None if dg is None else CARDINAUX[int((dg + 22.5) // 45) % 8]


def graphe_journee(hs):
    """Graphique SVG 24 h : courbe de température + barres de pluie."""
    pts = [(k, x["t"]) for k, x in enumerate(hs) if x["t"] is not None]
    if len(pts) < 2:
        return ""
    W, H, ml, mr, top, bas = 600, 180, 22, 22, 26, 150
    dx = (W - ml - mr) / max(len(hs) - 1, 1)
    tmin, tmax = min(t for _, t in pts), max(t for _, t in pts)
    if tmax - tmin < 4:
        m = (4 - (tmax - tmin)) / 2
        tmin, tmax = tmin - m, tmax + m
    def y(t):
        return top + (tmax - t) / (tmax - tmin) * 70
    pmax = max([2.0] + [x["pluie"] or 0 for x in hs])
    el = []
    for k, x in enumerate(hs):
        cx = ml + k * dx
        p = x["pluie"] or 0
        if p >= 0.1:
            hp = max(2, p / pmax * 45)
            el.append(f'<rect x="{cx - dx * 0.35:.1f}" y="{bas - hp:.1f}" width="{dx * 0.7:.1f}" height="{hp:.1f}" rx="2" fill="var(--pluie)" opacity=".75"/>')
            if p >= 0.5:
                el.append(f'<text x="{cx:.1f}" y="{bas - hp - 3:.1f}" text-anchor="middle" class="gp">{p:g}</text>')
        if k % 3 == 0:
            el.append(f'<text x="{cx:.1f}" y="{H - 8}" text-anchor="middle" class="gh">{x["h"]}</text>')
            el.append(f'<line x1="{cx:.1f}" y1="{top - 6}" x2="{cx:.1f}" y2="{bas}" stroke="var(--line)"/>')
    ligne = " ".join(f"{ml + k * dx:.1f},{y(t):.1f}" for k, t in pts)
    el.append(f'<polyline points="{ligne}" fill="none" stroke="var(--temp)" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>')
    for k, t in pts:
        if k % 3 == 0:
            el.append(f'<circle cx="{ml + k * dx:.1f}" cy="{y(t):.1f}" r="3" fill="var(--temp)"/>')
            el.append(f'<text x="{ml + k * dx:.1f}" y="{y(t) - 8:.1f}" text-anchor="middle" class="gt">{round(t)}°</text>')
    el.append(f'<line x1="{ml}" y1="{bas}" x2="{W - mr}" y2="{bas}" stroke="var(--line)"/>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
            f'aria-label="Température et pluie sur 24 heures">{"".join(el)}</svg>')


def code_actuel(codes, nuages):
    """Ciel actuel : pluie/orage/neige/brouillard si la majorité des modèles l'annoncent,
    sinon d'après la couverture nuageuse moyenne (plus fiable que le code « le plus sévère »)."""
    if not codes:
        return None
    marques = {m: c for m, c in codes.items() if c >= 45}
    if len(marques) * 2 > len(codes):
        return code_dominant(marques)
    if nuages:
        cc = statistics.fmean(nuages.values())
        return 0 if cc < 15 else 1 if cc < 35 else 2 if cc < 70 else 3
    return code_dominant(codes)


def code_jour(codes, pluie, nuages):
    """Ciel du jour d'après la pluie moyenne pondérée et la nébulosité moyenne
    (orage / neige seulement si la majorité des modèles les annoncent)."""
    if codes:
        n = len(codes)
        if sum(1 for c in codes.values() if c >= 95) * 2 > n:
            return 95
        neige = sum(1 for c in codes.values() if c in (71, 73, 75, 77, 85, 86))
        if neige * 2 > n and (pluie or 0) >= 0.2:
            return 73 if pluie >= 2 else 71
    if pluie is not None and pluie >= 0.2:
        return 51 if pluie < 1 else 61 if pluie < 5 else 63 if pluie < 15 else 65
    if nuages is not None:
        return 0 if nuages < 20 else 1 if nuages < 40 else 2 if nuages < 65 else 4 if nuages < 85 else 3
    return code_dominant(codes)


def ciel(code):
    return CIEL.get(code, ("—", "❔"))


def categorie(code, jour=True):
    if code is None:
        return "couvert"
    if code in (0, 1):
        cat = "soleil"
    elif code == 2:
        cat = "eclaircie"
    elif code == 4:
        cat = "couvert"
    elif code in (45, 48):
        cat = "brouillard"
    elif code in (71, 73, 75, 77, 85, 86):
        cat = "neige"
    elif code >= 95:
        cat = "orage"
    elif code >= 51:
        cat = "pluie"
    else:
        cat = "couvert"
    return "nuit" if not jour and cat in ("soleil", "eclaircie") else cat


def icone_mdi(code, jour=True):
    """Nom d'icône Material Design Icons (police intégrée à KWGT)."""
    cat = categorie(code, True)
    if not jour and cat == "soleil":
        return "weather-night"
    if not jour and cat == "eclaircie":
        return "weather-night-partly-cloudy"
    if cat == "pluie" and code in (65, 67, 82):
        return "weather-pouring"
    if code == 4:
        return "weather-partly-cloudy"
    return {"soleil": "weather-sunny", "eclaircie": "weather-partly-cloudy", "couvert": "weather-cloudy",
            "brouillard": "weather-fog", "pluie": "weather-rainy", "neige": "weather-snowy",
            "orage": "weather-lightning-rainy"}[cat]


def couleur_t(t):
    """Couleur hexadécimale selon la température (bleu froid -> rouge chaud)."""
    if t is None:
        return "#9AA5AF"
    pts = PALETTE_T
    if t <= pts[0][0]:
        c = pts[0][1]
    elif t >= pts[-1][0]:
        c = pts[-1][1]
    else:
        for (t1, c1), (t2, c2) in zip(pts, pts[1:]):
            if t1 <= t <= t2:
                k = (t - t1) / (t2 - t1)
                c = tuple(round(a + (b - a) * k) for a, b in zip(c1, c2))
                break
    return "#%02X%02X%02X" % c


def barres_pluie(pluie):
    """Barres par modèle : % de la plus forte prévision (échelle mini 5 mm) + version texte."""
    echelle = max([5.0] + list(pluie.values()))
    out, txt = {}, []
    for m, court in COURT.items():
        if m in pluie:
            pct = round(pluie[m] / echelle * 100)
            out[court] = {"mm": arr(pluie[m]), "pct": pct}
            txt.append(f"{ABREV[court]} {BLOCS[min(7, pct * 8 // 101)]}")
    return out, "  ".join(txt)


def confiance(tmax, pluie):
    """Score 0-100 : baisse quand les modèles divergent (Tmax, cumul, pluie oui/non)."""
    nb = len(pluie)
    pluvieux = sum(1 for v in pluie.values() if v >= 1)
    score = 100 - min(ecart(tmax) * 8, 40) - min(ecart(pluie) * 4, 40)
    if 0 < pluvieux < nb:
        score -= 20
    score = max(0, round(score))
    return score, ("Élevée" if score >= 70 else "Moyenne" if score >= 40 else "Faible")


def tranche(j):
    return 0 if j <= 1 else 1 if j <= 3 else 2


_poids = {"t": 0.0, "val": {}}


def poids(b):
    """Poids des modèles pour une tranche d'échéance : initiaux, puis appris (recalcul horaire)."""
    if time.time() - _poids["t"] > 3600:
        try:
            _poids["val"] = calcul_poids()
        except Exception:
            _poids["val"] = {}
        _poids["t"] = time.time()
    return _poids["val"].get(b, {}).get("poids") or PRIOR[b]


def calcul_poids():
    """Erreur moyenne de chaque modèle (90 derniers jours) -> poids, lissés avec les poids initiaux."""
    if not os.path.exists(DB):
        return {}
    with sqlite3.connect(DB) as c:
        rows = c.execute("""
            SELECT p.modele, p.echeance, ABS(p.tmax - o.tmax), ABS(p.tmin - o.tmin),
                   ABS(COALESCE(p.pluie, 0) - COALESCE(o.pluie, 0))
            FROM previsions p JOIN observations o ON o.lieu = p.lieu AND o.date = p.date_cible
            WHERE o.date >= date('now', '-90 day')
              AND p.tmax IS NOT NULL AND p.tmin IS NOT NULL AND o.tmax IS NOT NULL AND o.tmin IS NOT NULL
        """).fetchall()
    stats = {}
    for m, e, dtx, dtn, dp in rows:
        st = stats.setdefault((tranche(e), m), [0, 0.0, 0.0])
        st[0] += 1
        st[1] += (dtx + dtn) / 2
        st[2] += dp
    out = {}
    for b in PRIOR:
        mods = {m: st for (bb, m), st in stats.items() if bb == b and st[0] >= MIN_N}
        if len(mods) < 2:
            continue
        mae_t = {m: st[1] / st[0] for m, st in mods.items()}
        mae_p = {m: st[2] / st[0] for m, st in mods.items()}
        mt = statistics.fmean(mae_t.values()) or 1.0
        mp = statistics.fmean(mae_p.values()) or 1.0
        appris = {m: 1.0 / (mae_t[m] / mt + mae_p[m] / mp + 1e-6) for m in mods}
        tot = sum(appris.values())
        appris = {m: v / tot for m, v in appris.items()}
        ptot = sum(PRIOR[b].values())
        res = {}
        for m in MODELES:
            pr = PRIOR[b].get(m, 1.0) / ptot
            n = mods[m][0] if m in mods else 0
            k = n / (n + K_LISSAGE)
            res[m] = pr * (1 - k) + appris.get(m, pr) * k
        out[b] = {"poids": res, "n": min(st[0] for st in mods.values()),
                  "erreur_t": {m: round(v, 2) for m, v in mae_t.items()},
                  "erreur_p": {m: round(v, 2) for m, v in mae_p.items()}}
    return out


def synthese(b):
    maintenant = datetime.now(TZ)
    h, d = b.get("hourly", {}), b.get("daily", {})
    heures = h.get("time", [])
    cle = maintenant.strftime("%Y-%m-%dT%H:00")
    i = heures.index(cle) if cle in heures else 0

    code_now = code_actuel(serie(h, "weather_code", i), serie(h, "cloud_cover", i))
    W0 = poids(0)
    is_day = serie(h, "is_day", i)
    jour = moy(is_day, 0) >= 1 if is_day else 8 <= maintenant.hour < 19
    label, icone = ciel(code_now)
    t_now = moy(serie(h, "temperature_2m", i), w=W0)
    fond1, fond2, texte = FONDS[categorie(code_now, jour)]
    horaire = []
    for k in range(i, min(i + 24, len(heures))):
        isd = serie(h, "is_day", k)
        jour_k = moy(isd, 0) >= 1 if isd else 7 <= int(heures[k][11:13]) < 19
        code_k = code_actuel(serie(h, "weather_code", k), serie(h, "cloud_cover", k))
        pl_moy = moy(serie(h, "precipitation", k), w=W0)
        if pl_moy is not None and pl_moy >= 0.2 and (code_k or 0) < 45:
            code_k = 51 if pl_moy < 1 else 61 if pl_moy < 4 else 63
        lab, ico = ciel(code_k)
        if not jour_k and code_k in (0, 1):
            ico = "🌙"
        pl = serie(h, "precipitation", k)
        dk = direction_moy(serie(h, "wind_direction_10m", k), W0)
        horaire.append({
            "h": f"{int(heures[k][11:13])}h", "icone": ico, "ciel": lab,
            "t": moy(serie(h, "temperature_2m", k), w=W0),
            "ressenti": moy(serie(h, "apparent_temperature", k), 0, W0),
            "pluie": moy(pl, w=W0),
            "risque": round(100 * sum(1 for v in pl.values() if v >= 0.1) / len(pl)) if pl else None,
            "vent": moy(serie(h, "wind_speed_10m", k), 0, W0),
            "raf": moy(serie(h, "wind_gusts_10m", k), 0, W0),
            "dir": dk, "card": cardinal(dk),
        })
    res = {
        "heures": horaire,
        "maj": maintenant.strftime("%H:%M"),
        "nb_modeles": len(serie(d, "temperature_2m_max", 0)),
        "fond1": fond1, "fond2": fond2, "texte": texte,
        "now": {
            "t": t_now, "couleur_t": couleur_t(t_now), "mdi": icone_mdi(code_now, jour),
            "hr": moy(serie(h, "relative_humidity_2m", i), 0, w=W0),
            "vent": moy(serie(h, "wind_speed_10m", i), 0, w=W0),
            "rafales": moy(serie(h, "wind_gusts_10m", i), 0, w=W0),
            "pluie": moy(serie(h, "precipitation", i), w=W0),
            "sol": moy(serie(h, "soil_temperature_6cm", i), w=W0),
            "nuages": moy(serie(h, "cloud_cover", i), 0, w=W0),
            "ciel": label, "icone": icone,
        },
    }
    for j, date in enumerate(d.get("time", [])[:NB_JOURS]):
        W = poids(tranche(j))
        tmax = serie(d, "temperature_2m_max", j)
        tmin = serie(d, "temperature_2m_min", j)
        pluie = serie(d, "precipitation_sum", j)
        code_j = code_jour(serie(d, "weather_code", j), moy(pluie, w=W),
                           moy(serie(d, "cloud_cover_mean", j), 0, W))
        label, icone = ciel(code_j)
        score, niveau = confiance(tmax, pluie)
        barres, barres_txt = barres_pluie(pluie)
        dt = datetime.fromisoformat(date)
        nom = "Aujourd’hui" if j == 0 else "Demain" if j == 1 else JOURS[dt.weekday()].capitalize()
        res[f"j{j}"] = {
            "nom": nom, "date": dt.strftime("%d/%m"),
            "court": "Auj." if j == 0 else "Dem." if j == 1 else JOURS_COURTS[dt.weekday()],
            "tmin": moy(tmin, w=W), "tmax": moy(tmax, w=W), "pluie": moy(pluie, w=W),
            "vent": moy(serie(d, "wind_speed_10m_max", j), 0, W),
            "rafales": moy(serie(d, "wind_gusts_10m_max", j), 0, W),
            "etp": moy(serie(d, "et0_fao_evapotranspiration", j), 1, W),
            "ciel": label, "icone": icone, "mdi": icone_mdi(code_j),
            "couleur_tmin": couleur_t(moy(tmin, w=W)), "couleur_tmax": couleur_t(moy(tmax, w=W)),
            "couleur_confiance": "#2F7D4F" if score >= 70 else "#B7770C" if score >= 40 else "#B3392F",
            "pluie_mod": barres, "barres_txt": barres_txt,
            "confiance": niveau, "confiance_pct": score,
            "ecart_tmax": ecart(tmax), "ecart_pluie": ecart(pluie),
            "nb": len(tmax),
            "lever": heure(jour_commun(d, "sunrise", j)),
            "coucher": heure(jour_commun(d, "sunset", j)),
            "uv": moy(serie(d, "uv_index_max", j), 0) if serie(d, "uv_index_max", j)
                  else (round(jour_commun(d, "uv_index_max", j)) if jour_commun(d, "uv_index_max", j) is not None else None),
            "accord_pluie": f"{sum(1 for v in pluie.values() if v >= 1)}/{len(pluie)}",
            "modeles": {MODELES[m]: {"tmin": arr(tmin.get(m)), "tmax": arr(tmax.get(m)), "pluie": arr(pluie.get(m))}
                        for m in MODELES if m in tmax or m in pluie},
        }
    res["jours"] = [f"j{j}" for j in range(NB_JOURS) if f"j{j}" in res]
    appris = _poids["val"]
    res["poids"] = [{
        "echeance": LIB_ECH[b],
        "source": f"appris sur {appris[b]['n']} jours" if b in appris else "réglage initial",
        "modeles": {MODELES[m]: round(100 * poids(b).get(m, 0) / sum(poids(b).values())) for m in MODELES},
    } for b in PRIOR]
    return res


# ---------- Apprentissage : tâches lancées par le timer systemd ----------

def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS previsions (
            date_emission TEXT, lieu TEXT, modele TEXT, date_cible TEXT, echeance INTEGER,
            tmin REAL, tmax REAL, pluie REAL,
            PRIMARY KEY (date_emission, lieu, modele, date_cible));
        CREATE TABLE IF NOT EXISTS observations (
            lieu TEXT, date TEXT, tmin REAL, tmax REAL, pluie REAL, PRIMARY KEY (lieu, date));
        CREATE TABLE IF NOT EXISTS position (id INTEGER PRIMARY KEY, lat REAL, lon REAL, horodatage TEXT);
        CREATE TABLE IF NOT EXISTS alertes (lieu TEXT, type TEXT, cle TEXT, envoye TEXT,
            PRIMARY KEY (lieu, type, cle));
        """)


def appel_json(url, params):
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params, safe=","), timeout=60) as r:
        return json.load(r)


def charger_observations(c, lieu, lat, lon, debut, fin):
    """Valeurs « réelles » : réanalyse Open-Meteo (ERA5), disponible avec ~5 jours de retard."""
    if debut > fin:
        return 0
    d = appel_json("https://archive-api.open-meteo.com/v1/archive", {
        "latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}",
        "start_date": debut.isoformat(), "end_date": fin.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "timezone": "Europe/Paris",
    }).get("daily", {})
    n = 0
    for k, date in enumerate(d.get("time", [])):
        tx, tn, p = (d.get(v, [None] * (k + 1))[k] for v in
                     ("temperature_2m_max", "temperature_2m_min", "precipitation_sum"))
        if tx is not None and tn is not None:
            c.execute("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?)", (lieu, date, tn, tx, p))
            n += 1
    return n


def quotidien():
    """Archive les prévisions du jour et récupère le réel des jours passés."""
    init_db()
    auj = datetime.now(TZ).date()
    with sqlite3.connect(DB) as c:
        for lieu, (lat, lon) in REFS.items():
            d = appel_open_meteo(lat, lon).get("daily", {})
            n = 0
            for j, date in enumerate(d.get("time", [])[:NB_JOURS]):
                for m in MODELES:
                    vals = [(d.get(f"{v}_{m}") or [None] * (j + 1))[j] for v in
                            ("temperature_2m_min", "temperature_2m_max", "precipitation_sum")]
                    if any(x is not None for x in vals):
                        c.execute("INSERT OR REPLACE INTO previsions VALUES (?,?,?,?,?,?,?,?)",
                                  (auj.isoformat(), lieu, m, date, j, *vals))
                        n += 1
            obs = charger_observations(c, lieu, lat, lon, auj - timedelta(days=40), auj - timedelta(days=6))
            print(f"{lieu} : {n} prévisions archivées, {obs} jours de réel mis à jour")
        c.execute("DELETE FROM previsions WHERE date_emission < date('now', '-200 day')")


def amorcer(jours=90):
    """Démarrage rapide : prévisions archivées des 90 derniers jours (échéance J+0/J+1)."""
    init_db()
    auj = datetime.now(TZ).date()
    debut, fin = auj - timedelta(days=jours + 6), auj - timedelta(days=6)
    with sqlite3.connect(DB) as c:
        for lieu, (lat, lon) in REFS.items():
            d = appel_json("https://historical-forecast-api.open-meteo.com/v1/forecast", {
                "latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}",
                "start_date": debut.isoformat(), "end_date": fin.isoformat(),
                "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum",
                "models": ",".join(MODELES), "timezone": "Europe/Paris",
            }).get("daily", {})
            n = 0
            for k, date in enumerate(d.get("time", [])):
                for m in MODELES:
                    vals = [(d.get(f"{v}_{m}") or [None] * (k + 1))[k] for v in
                            ("temperature_2m_min", "temperature_2m_max", "precipitation_sum")]
                    if all(x is not None for x in vals[:2]):
                        c.execute("INSERT OR REPLACE INTO previsions VALUES (?,?,?,?,?,?,?,?)",
                                  (date, lieu, m, date, 0, *vals))
                        n += 1
            obs = charger_observations(c, lieu, lat, lon, debut, fin)
            print(f"{lieu} : {n} prévisions historiques, {obs} jours de réel")
    print("Poids obtenus :", json.dumps(calcul_poids(), ensure_ascii=False, indent=1))


# ---------- Dernière position connue (envoyée par le widget) ----------

_derniere_pos = {"lat": None, "lon": None, "t": 0.0}


def enregistrer_position(lat, lon):
    """Mémorise la position du widget (au plus toutes les 10 min ou si déplacement > ~1 km)."""
    d = _derniere_pos
    bouge = d["lat"] is None or abs(lat - d["lat"]) > 0.01 or abs(lon - d["lon"]) > 0.01
    if not bouge and time.time() - d["t"] < 600:
        return
    try:
        init_db()
        with sqlite3.connect(DB) as c:
            c.execute("INSERT OR REPLACE INTO position VALUES (1, ?, ?, ?)",
                      (lat, lon, datetime.now(TZ).isoformat(timespec="seconds")))
        d.update(lat=lat, lon=lon, t=time.time())
    except Exception:
        pass  # base en lecture seule : on se contente de Gémenos


# ---------- Alertes ntfy (timer toutes les 15 min) ----------

def envoyer_ntfy(titre, message, tags, priorite=3):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC non défini : notification non envoyée :", titre)
        return
    corps = json.dumps({"topic": NTFY_TOPIC, "title": titre, "message": message,
                        "tags": tags, "priority": priorite}).encode()
    req = urllib.request.Request(NTFY_URL.rstrip("/") + "/", data=corps,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def prevision_horaire(lat, lon):
    """Prochaines 24 h, heure par heure, en moyenne pondérée (poids d'aujourd'hui)."""
    d = appel_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}", "timezone": "Europe/Paris",
        "hourly": "temperature_2m,precipitation,wind_gusts_10m,weather_code",
        "models": ",".join(MODELES), "forecast_hours": 24, "wind_speed_unit": "kmh",
    }).get("hourly", {})
    W = poids(0)
    heures = []
    for i, t in enumerate(d.get("time", [])):
        pl = serie(d, "precipitation", i)
        codes = serie(d, "weather_code", i)
        heures.append({
            "h": int(t[11:13]), "date": t[:10],
            "t": moy(serie(d, "temperature_2m", i), 1, W),
            "pluie": moy(pl, 1, W), "raf": moy(serie(d, "wind_gusts_10m", i), 0, W),
            "pluie_accord": sum(1 for v in pl.values() if v >= 0.3) * 2 > max(len(pl), 1),
            "orage": sum(1 for c in codes.values() if c >= 95) * 2 > max(len(codes), 1),
        })
    return heures


def detecter(heures):
    """Liste de (type, clé anti-doublon, titre, message, tags, priorité)."""
    if not heures:
        return []
    out, h0 = [], heures[0]
    jour = h0["date"]
    # Pluie dans l'heure : il ne pleut pas maintenant, il pleuvra dans l'heure suivante
    if len(heures) > 1 and (h0["pluie"] or 0) < 0.2:
        h1 = heures[1]
        if (h1["pluie"] or 0) >= SEUILS["pluie_mm"] and h1["pluie_accord"]:
            out.append(("pluie", f"{jour}-{h1['h'] // 3}", "Pluie dans l’heure",
                        f"Pluie attendue vers {h1['h']}h (≈ {h1['pluie']} mm/h)", ["umbrella"], 3))
    # Orage dans les 3 h
    for h in heures[:3]:
        if h["orage"]:
            out.append(("orage", f"{jour}-{h['h'] // 3}", "Orage possible",
                        f"Orage annoncé par la majorité des modèles vers {h['h']}h", ["zap"], 4))
            break
    # Rafales dans les 6 h
    raf = max(heures[:6], key=lambda h: h["raf"] or 0)
    if (raf["raf"] or 0) >= SEUILS["rafales_kmh"]:
        out.append(("rafales", f"{jour}-{raf['h'] // 6}", "Rafales fortes",
                    f"Rafales jusqu’à {raf['raf']} km/h vers {raf['h']}h", ["dash"], 4))
    # Gel dans les 18 h
    froid = min(heures[:18], key=lambda h: h["t"] if h["t"] is not None else 99)
    if froid["t"] is not None and froid["t"] < SEUILS["gel_c"]:
        out.append(("gel", froid["date"], "Gel prévu",
                    f"Jusqu’à {froid['t']} °C vers {froid['h']}h", ["snowflake"], 3))
    # Canicule dans les 24 h
    chaud = max(heures, key=lambda h: h["t"] if h["t"] is not None else -99)
    if chaud["t"] is not None and chaud["t"] >= SEUILS["canicule_c"]:
        out.append(("canicule", chaud["date"], "Forte chaleur",
                    f"{chaud['t']} °C attendus vers {chaud['h']}h", ["hot_face"], 4))
    return out


def alertes():
    init_db()
    maintenant = datetime.now(TZ)
    silence = maintenant.hour >= SILENCE[0] or maintenant.hour < SILENCE[1]
    lieux = {"Gémenos": REFS["gemenos"]}
    with sqlite3.connect(DB) as c:
        pos = c.execute("SELECT lat, lon, horodatage FROM position WHERE id = 1").fetchone()
        if pos:
            age = maintenant - datetime.fromisoformat(pos[2])
            loin = abs(pos[0] - REFS["gemenos"][0]) > 0.05 or abs(pos[1] - REFS["gemenos"][1]) > 0.05
            if age < timedelta(hours=3) and loin:
                lieux[nom_commune(pos[0], pos[1]) or "Position actuelle"] = (pos[0], pos[1])
        for nom, (lat, lon) in lieux.items():
            for typ, cle, titre, msg, tags, prio in detecter(prevision_horaire(lat, lon)):
                if silence and typ not in ("orage", "rafales"):
                    continue
                if c.execute("SELECT 1 FROM alertes WHERE lieu=? AND type=? AND cle=?", (nom, typ, cle)).fetchone():
                    continue
                envoyer_ntfy(f"{titre} — {nom}", msg, tags, prio)
                c.execute("INSERT INTO alertes VALUES (?,?,?,?)", (nom, typ, cle, maintenant.isoformat(timespec="seconds")))
                print("Envoyé :", nom, typ, msg)
        c.execute("DELETE FROM alertes WHERE envoye < date('now', '-7 day')")


# ---------- Cache (clé arrondie ~1 km, 30 min) ----------

_cache = {}


def meteo(lat, lon):
    cle = (round(lat, 2), round(lon, 2))
    t = time.time()
    hit = _cache.get(cle)
    if hit and t - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        res = synthese(appel_open_meteo(lat, lon))
        res["air"] = appel_air(lat, lon)
    except Exception:
        if hit:  # Open-Meteo en panne : ancienne donnée plutôt que rien
            return hit[1]
        raise
    for k in [k for k, v in _cache.items() if t - v[0] > 3 * CACHE_TTL]:
        del _cache[k]
    _cache[cle] = (t, res)
    return res


def position():
    try:
        lat = float(request.args.get("lat", "").replace(",", "."))
        lon = float(request.args.get("lon", "").replace(",", "."))
        if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0.0, 0.0):
            return lat, lon, None
    except ValueError:
        pass
    return DEFAUT


# ---------- Routes ----------

bp = Blueprint("meteo", __name__)


@bp.before_request
def verif_token():
    k = request.args.get("k", "").encode()
    if not TOKEN or not hmac.compare_digest(k, TOKEN.encode()):
        abort(403)


@bp.get("/api")
def api():
    lat, lon, nom = position()
    try:
        data = meteo(lat, lon)
    except Exception as e:
        return jsonify(erreur=f"Open-Meteo indisponible : {e}"), 502
    if nom is None:
        enregistrer_position(lat, lon)
    rep = jsonify({"version": VERSION, "lieu": nom or nom_commune(lat, lon), "lat": round(lat, 3), "lon": round(lon, 3), **data})
    rep.headers["Cache-Control"] = "no-cache"  # KWGT respecte le cache HTTP : on l'empêche de garder une vieille réponse
    return rep


@bp.get("/")
def page():
    lat, lon, nom = position()
    try:
        data = meteo(lat, lon)
    except Exception as e:
        return f"Open-Meteo indisponible : {e}", 502
    lieu = nom or nom_commune(lat, lon) or f"{lat:.3f}, {lon:.3f}"
    return render_template_string(PAGE, version=VERSION, d=data, lieu=lieu,
                                  graphe=graphe_journee(data.get("heures", [])))


PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Météo — {{ lieu }}</title>
<style>
:root{--bg:#f4f6f3;--card:#fff;--txt:#1d2420;--mut:#68716b;--ok:#2f7d4f;--moy:#b7770c;--bad:#b3392f;--line:#e2e6e1;--temp:#e0632f;--pluie:#3f7cc4}
@media (prefers-color-scheme:dark){:root{--bg:#121513;--card:#1c211e;--txt:#e8ece9;--mut:#99a29c;--line:#2c332f}}
body{margin:0 auto;max-width:600px;padding:12px;font:15px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--txt)}
.scroll{overflow-x:auto}
h1{font-size:2rem;margin:.2em 0}h1 small{font-size:1rem;color:var(--mut);font-weight:500}
.mut{color:var(--mut);font-size:.9rem}
.card{background:var(--card);border-radius:14px;padding:12px 14px;margin:12px 0}
.ok{color:var(--ok)}.moy{color:var(--moy)}.bad{color:var(--bad)}b{font-weight:600}
table{width:100%;border-collapse:collapse;font-size:.85rem}
td,th{padding:5px 2px;border-top:1px solid var(--line);text-align:right;white-space:nowrap}
.wrap{white-space:normal}
td:first-child,th:first-child{text-align:left}th{font-weight:600}
details{border-top:1px solid var(--line);padding:8px 0}details:first-of-type{border-top:0}
summary{cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:8px}
summary::-webkit-details-marker{display:none}
summary .g{flex:1}details table{margin-top:6px}
.gh{font-size:13px;fill:var(--mut)}.gt{font-size:13px;font-weight:600;fill:var(--txt)}.gp{font-size:11px;fill:var(--pluie)}
.h24 td,.h24 th{text-align:center;padding:4px 7px}.h24 td:first-child,.h24 th:first-child{position:sticky;left:0;background:var(--card);text-align:left;color:var(--mut);font-weight:400;padding-left:0}
.fl{display:inline-block}
details.sub{border:0;padding:4px 0 0}details.sub summary{color:var(--pluie);font-size:.88rem;display:inline}
</style></head><body>
<h1>{{ d.now.icone }} {{ d.now.t|f }}° <small>{{ lieu }}</small></h1>
<p class="mut">{{ d.now.ciel }} · nuages {{ d.now.nuages|f }} % · HR {{ d.now.hr|f }} % · vent {{ d.now.vent|f }} km/h (raf. {{ d.now.rafales|f }}) · sol {{ d.now.sol|f }}°<br>
{% if d.j0 and d.j0.lever %}🌅 {{ d.j0.lever }} · 🌇 {{ d.j0.coucher }}{% if d.j0.uv is not none %} · UV max {{ d.j0.uv }} ({{ d.j0.uv|uv }}){% endif %}<br>{% endif %}
Moyenne de {{ d.nb_modeles }} modèles · mis à jour à {{ d.maj }}</p>

{% if d.heures %}<section class="card"><b>Heure par heure (24 h)</b>
{{ graphe|safe }}
<div class="scroll"><table class="h24">
<tr><th></th>{% for x in d.heures %}<th>{{ x.h }}</th>{% endfor %}</tr>
<tr><td></td>{% for x in d.heures %}<td title="{{ x.ciel }}">{{ x.icone }}</td>{% endfor %}</tr>
<tr><td>Temp.</td>{% for x in d.heures %}<td><b>{{ x.t|f }}°</b></td>{% endfor %}</tr>
<tr><td>Ressenti</td>{% for x in d.heures %}<td>{{ x.ressenti|f }}°</td>{% endfor %}</tr>
<tr><td>Pluie</td>{% for x in d.heures %}<td>{% if x.pluie and x.pluie >= 0.1 %}{{ x.pluie }}{% else %}·{% endif %}</td>{% endfor %}</tr>
<tr><td>Risque</td>{% for x in d.heures %}<td class="{{ 'bad' if (x.risque or 0) >= 60 else 'moy' if (x.risque or 0) >= 30 else 'mut' }}">{{ x.risque if x.risque is not none else '–' }}%</td>{% endfor %}</tr>
<tr><td>Vent</td>{% for x in d.heures %}<td>{% if x.dir is not none %}<span class="fl" style="transform:rotate({{ (x.dir + 180) % 360 }}deg)">↑</span>{% endif %} {{ x.vent|f }}</td>{% endfor %}</tr>
<tr><td>Rafales</td>{% for x in d.heures %}<td class="{{ 'bad' if (x.raf or 0) >= 60 else 'moy' if (x.raf or 0) >= 40 else '' }}">{{ x.raf|f }}</td>{% endfor %}</tr>
<tr><td>Dir.</td>{% for x in d.heures %}<td class="mut">{{ x.card or '–' }}</td>{% endfor %}</tr>
</table></div>
<p class="mut" style="margin:6px 0 0">Fais défiler le tableau vers la droite · pluie en mm · vent et rafales en km/h · la flèche montre où va le vent · risque = part des modèles qui annoncent de la pluie.</p></section>{% endif %}
{% if d.air %}<section class="card"><b>Qualité de l’air</b> · <span class="{{ d.air.classe }}">{{ d.air.label }}</span> <span class="mut">(indice {{ d.air.aqi }})</span><br>
<span class="mut">PM2.5 {{ d.air.pm25 }} · PM10 {{ d.air.pm10 }} · ozone {{ d.air.ozone }} µg/m³</span><br>
Pollens : {% if d.air.pollens %}{% for p in d.air.pollens %}{{ p.nom }} <span class="{{ 'ok' if p.niveau == 'faible' else 'moy' if p.niveau == 'modéré' else 'bad' }}">{{ p.niveau }}</span>{% if not loop.last %} · {% endif %}{% endfor %}{% else %}<span class="mut">rien de notable</span>{% endif %}
</section>{% endif %}

<section class="card"><div class="scroll"><table>
<tr><th>Jour</th><th></th><th>Min</th><th>Max</th><th>mm</th><th>Raf.</th><th>Conf.</th></tr>
{% for k in d.jours %}{% set j = d[k] %}
<tr><td>{{ j.court }} <span class="mut">{{ j.date[:2] }}</span></td><td>{{ j.icone }}</td>
<td>{{ j.tmin|f }}°</td><td><b>{{ j.tmax|f }}°</b></td><td>{{ j.pluie|f }}</td><td>{{ j.rafales|f }}</td>
<td class="{{ 'ok' if j.confiance_pct >= 70 else 'moy' if j.confiance_pct >= 40 else 'bad' }}">{{ j.confiance_pct }}%</td></tr>
{% endfor %}</table></div>
<p class="mut" style="margin:6px 0 0">mm = pluie · Raf. = rafales max (km/h) · touche un jour ci-dessous pour son détail.</p></section>

<section class="card">
{% for k in d.jours %}{% set j = d[k] %}
<details>
<summary><span class="g wrap"><b>{{ j.icone }} {{ j.nom }}</b> <span class="mut">{{ j.date }} · {{ j.ciel }}</span></span>
<span class="{{ 'ok' if j.confiance_pct >= 70 else 'moy' if j.confiance_pct >= 40 else 'bad' }}">{{ j.confiance }}</span></summary>
<div class="mut">{{ j.tmin|f }}° / {{ j.tmax|f }}° · {{ j.pluie|f }} mm · vent {{ j.vent|f }} km/h (raf. {{ j.rafales|f }}) · ETP {{ j.etp|f }} mm<br>
pluie ≥ 1 mm pour {{ j.accord_pluie }} modèles · {{ j.nb }} modèle(s) disponibles<br>
{% if j.lever %}🌅 {{ j.lever }} · 🌇 {{ j.coucher }}{% endif %}{% if j.uv is not none %} · UV {{ j.uv }} ({{ j.uv|uv }}){% endif %}</div>
<details class="sub"><summary>Voir le détail par modèle ›</summary>
<table><tr><th>Modèle</th><th>Min</th><th>Max</th><th>Pluie</th></tr>
{% for nom, v in j.modeles.items() %}<tr><td>{{ nom.split(' ')[0] }}</td><td>{{ v.tmin|f }}</td><td>{{ v.tmax|f }}</td><td>{{ v.pluie|f }}</td></tr>{% endfor %}
</table></details></details>
{% endfor %}</section>

<section class="card"><details class="sub"><summary>Infos techniques : poids des modèles ›</summary>
<div class="scroll"><table><tr><th>Modèle</th><th>J0-J1</th><th>J2-J3</th><th>J4-J6</th></tr>
{% for nom in d.poids[0].modeles %}<tr><td>{{ nom.split(' ')[0] }}</td>
{% for p in d.poids %}<td>{{ p.modeles[nom] }} %</td>{% endfor %}</tr>{% endfor %}
</table></div>
<p class="mut" style="margin:6px 0 0">{% for p in d.poids %}{{ p.echeance }} : {{ p.source }}{% if not loop.last %} · {% endif %}{% endfor %}.<br>
Les moyennes sont pondérées : un modèle qui s’est moins trompé ici ces 90 derniers jours compte davantage.</p></details></section>

<p class="mut">Au-delà de 2 à 4 jours, certains modèles (dont AROME de Météo-France) n’ont plus de prévision : la moyenne porte alors sur moins de modèles et la confiance baisse naturellement.<br>
Source : Open-Meteo (Météo-France, ECMWF, DWD, NOAA, Met Office ; air et pollens : Copernicus CAMS) · module météo v{{ version }}</p>
</body></html>"""

app = Flask(__name__)
app.json.ensure_ascii = False
app.json.sort_keys = False
app.jinja_env.filters["f"] = lambda v: "–" if v is None else v
app.jinja_env.filters["uv"] = lambda v: ("faible" if v < 3 else "modéré" if v < 6 else "élevé"
                                         if v < 8 else "très élevé" if v < 11 else "extrême")
app.register_blueprint(bp, url_prefix=PREFIX or None)


@app.get(f"{PREFIX}/sante")
def sante():
    return {"ok": True, "version": VERSION}


if __name__ == "__main__":
    # Tâches en ligne de commande :  python app.py quotidien  |  python app.py amorcer
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "quotidien":
        quotidien()
    elif cmd == "amorcer":
        amorcer()
    elif cmd == "alertes":
        alertes()
    elif cmd == "test_alerte":
        envoyer_ntfy("Test — météo AGEOTERRA", "Les alertes fonctionnent ✅", ["white_check_mark"])
        print("Notification de test envoyée.")
    else:
        print("Usage : python app.py quotidien | amorcer | alertes | test_alerte")
