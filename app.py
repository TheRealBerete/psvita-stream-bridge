"""
Bridge — expose une petite API HTTP que NetStream (PS Vita) peut consommer
directement en mode "HTTP server".

Contraintes verifiees dans le code source de NetStream (source/browsers/http_server_browser.cpp
et source/players/player_beav.cpp) :
  - Le navigateur HTTP de NetStream parse la reponse comme du HTML et cherche
    des balises <a href="...">, PAS du JSON.
  - Un href SANS point (n'importe ou dans le chemin) est traite comme un
    DOSSIER navigable (AVPlayer/BEAVPlayer/FMODPlayer::IsSupported renvoient
    tous "MaybeSupported" si sce_paf_strrchr ne trouve pas de '.').
  - Un href reconnu comme flux HLS doit se terminer litteralement par ".m3u8".
  - Le client curl de NetStream suit les redirections HTTP (FOLLOWLOCATION=1),
    mais le lecteur HLS interne resout les chemins RELATIFS du manifest par
    rapport a l'URL demandee (nous), pas par rapport a l'URL reelle apres
    redirection -> on reecrit nous-memes le manifest en URLs absolues.

Arborescence de navigation (pas de recherche texte possible cote NetStream,
donc categories + index alphabetique en guise de raccourcis) :

  GET /                                   -> liste des pays (dossiers)
  GET /country/{cc}/                      -> categories du pays + dossier A-Z
  GET /country/{cc}/category/{cat}/       -> chaines de cette categorie
  GET /country/{cc}/az/                   -> lettres disponibles
  GET /country/{cc}/az/{letter}/          -> chaines commencant par cette lettre
  GET /resolve/{cc}/{chan_id}.m3u8        -> manifest HLS reecrit (URLs absolues)

Donnees generees par build_channels.py (iptv-org/api : channels/categories/
streams/countries.json), pas de contenu sous licence.

Lancer :
    uvicorn app:app --host 0.0.0.0 --port 8000
"""
import json
import re
from collections import defaultdict
from html import escape
from pathlib import Path
from urllib.parse import urljoin

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

DATA_DIR = Path(__file__).parent / "data"
M3U8_CONTENT_TYPE = "application/vnd.apple.mpegurl"

app = FastAPI(title="anime-vita-bridge")

with (DATA_DIR / "channels.json").open(encoding="utf-8") as f:
    _channels = json.load(f)
with (DATA_DIR / "categories.json").open(encoding="utf-8") as f:
    _category_names = json.load(f)
with (DATA_DIR / "countries.json").open(encoding="utf-8") as f:
    _country_names = json.load(f)

# --- Index en memoire, construits une fois au demarrage ---------------------

# pays (code, ex "FR") -> liste de chaines
_by_country = defaultdict(list)
# (pays, categorie) -> liste de chaines
_by_country_category = defaultdict(list)
# (pays, lettre) -> liste de chaines
_by_country_letter = defaultdict(list)
# (pays, id) -> chaine, pour /resolve
_by_country_id = {}


def _letter_bucket(name: str) -> str:
    first = name.strip()[:1].upper()
    return first if first.isalpha() else "0-9"


for chan in _channels:
    cc = chan["country"]
    _by_country[cc].append(chan)
    for cat in chan["categories"]:
        _by_country_category[(cc, cat)].append(chan)
    _by_country_letter[(cc, _letter_bucket(chan["name"]))].append(chan)
    _by_country_id[(cc, chan["id"])] = chan

for lst in _by_country.values():
    lst.sort(key=lambda c: c["name"].lower())
for lst in _by_country_category.values():
    lst.sort(key=lambda c: c["name"].lower())
for lst in _by_country_letter.values():
    lst.sort(key=lambda c: c["name"].lower())


def page(items: list[tuple[str, str]]) -> str:
    """items = [(label, href), ...] -> page HTML minimaliste avec <a href>."""
    lis = "\n".join(f'<li><a href="{escape(href)}">{escape(label)}</a></li>' for label, href in items)
    return f"<html><body><ul>\n{lis}\n</ul></body></html>"


def channel_links(cc: str, chans: list[dict]) -> list[tuple[str, str]]:
    return [(c["name"], f"/resolve/{cc}/{c['id']}.m3u8") for c in chans]


# --- Navigation ---------------------------------------------------------
#
# IMPORTANT (verifie dans source/browsers/http_server_browser.cpp) : quand on
# entre dans un DOSSIER, NetStream ne fait PAS de vraie resolution d'URL
# relative. Sa fonction SetPath() fait juste :
#     nouvelle_url = url_courante + curl_easy_escape(ref) + "/"
# Donc si `ref` contient lui-meme un "/" (au debut, au milieu ou a la fin),
# on obtient des doubles slashs qui cassent tout (404 cote serveur, dossier
# vide cote Vita). Chaque href de DOSSIER doit donc etre un segment UNIQUE,
# sans aucun "/" dedans -> l'arborescence est encodee par des routes
# imbriquees cote serveur, jamais par des chemins multi-segments dans un href.
#
# Seuls les FICHIERS (.m3u8) passent par GetInfoForPlayer(), qui lui fait une
# vraie fusion d'URL (RFC 3986) -> un href absolu ("/resolve/...") y fonctionne
# correctement, d'ou son succes des le premier test.

@app.get("/", response_class=HTMLResponse)
def list_countries():
    items = [
        (f"{_country_names.get(cc, cc)} ({len(chans)})", cc.lower())
        for cc, chans in _by_country.items()
    ]
    items.sort(key=lambda t: t[0].lower())
    return page(items)


@app.get("/{cc}/", response_class=HTMLResponse)
def list_country_categories(cc: str):
    cc = cc.upper()
    if cc not in _by_country:
        raise HTTPException(status_code=404, detail="pays inconnu")

    cats_here = {cat for c in _by_country[cc] for cat in c["categories"]}
    items = [
        (f"{_category_names.get(cat, cat)} ({len(_by_country_category[(cc, cat)])})", cat)
        for cat in cats_here
    ]
    items.sort(key=lambda t: t[0].lower())
    items.insert(0, (f"Toutes les chaines A-Z ({len(_by_country[cc])})", "az"))
    return page(items)


@app.get("/{cc}/{token}/", response_class=HTMLResponse)
def list_country_token(cc: str, token: str):
    """Un seul niveau de route pour categorie OU 'az' (meme profondeur, segment unique)."""
    cc = cc.upper()
    if token == "az":
        if cc not in _by_country:
            raise HTTPException(status_code=404, detail="pays inconnu")
        letters = sorted({_letter_bucket(c["name"]) for c in _by_country[cc]})
        items = [(f"{l} ({len(_by_country_letter[(cc, l)])})", l) for l in letters]
        return page(items)

    chans = _by_country_category.get((cc, token))
    if chans is None:
        raise HTTPException(status_code=404, detail="categorie inconnue pour ce pays")
    return page(channel_links(cc, chans))


@app.get("/{cc}/az/{letter}/", response_class=HTMLResponse)
def list_letter_channels(cc: str, letter: str):
    cc = cc.upper()
    chans = _by_country_letter.get((cc, letter.upper()))
    if chans is None:
        raise HTTPException(status_code=404, detail="lettre inconnue pour ce pays")
    return page(channel_links(cc, chans))


# --- Resolution HLS -------------------------------------------------------

def rewrite_manifest(text: str, base_url: str) -> str:
    """
    Reecrit un manifest HLS pour que toutes les URI (lignes de playlist/segment
    ET attributs URI="..." des tags EXT-X-MEDIA/EXT-X-KEY/etc.) soient absolues,
    resolues contre `base_url` (l'URL REELLE apres redirection, pas l'URL de
    depart). Necessaire car le lecteur HLS de NetStream resout les chemins
    relatifs par rapport a l'URL qu'on lui donne (notre bridge), pas par
    rapport a l'hote reel du flux.
    """
    def resolve(url: str) -> str:
        return url if url.startswith(("http://", "https://")) else urljoin(base_url, url)

    out_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
        elif stripped.startswith("#"):
            out_lines.append(re.sub(r'URI="([^"]+)"', lambda m: f'URI="{resolve(m.group(1))}"', line))
        else:
            out_lines.append(resolve(stripped))
    return "\n".join(out_lines) + "\n"


@app.get("/resolve/{cc}/{chan_id}.m3u8")
def resolve(cc: str, chan_id: str):
    chan = _by_country_id.get((cc.upper(), chan_id))
    if not chan:
        raise HTTPException(status_code=404, detail="chaine inconnue")
    try:
        r = requests.get(chan["url"], timeout=10, headers={"User-Agent": "VLC/3.0.20"})
        r.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"source injoignable: {e}")
    rewritten = rewrite_manifest(r.text, r.url)  # r.url = URL APRES redirection
    return Response(content=rewritten, media_type=M3U8_CONTENT_TYPE)
