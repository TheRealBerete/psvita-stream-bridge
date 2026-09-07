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
  - SetPath() (navigation dossier) fait une simple concatenation de chaines,
    pas une vraie resolution d'URL relative -> chaque href de DOSSIER doit
    etre un segment UNIQUE, sans aucun "/" dedans.
  - Le parseur ne regarde QUE l'attribut href="..." -> le texte entre <a> et
    </a> n'est jamais affiche sur la console (confirme par captures d'ecran
    reelles : on y voit le href brut, jamais un libelle "joli"). Pour qu'un
    nom lisible (nom de pays/langue) soit visible, il doit etre le href
    lui-meme (url-quote), pas juste le texte du lien.

Arborescence de navigation (pas de recherche texte possible cote NetStream,
donc categories + index alphabetique en guise de raccourcis). Deux facons
d'arriver a une chaine -> "pays" et "langue" sont deux vues (partitions)
differentes sur le MEME jeu de chaines, avec exactement la meme mecanique
categorie/A-Z en dessous :

  GET /                                   -> choix "par pays" / "par langue"
  GET /country/                           -> liste des pays (dossiers)
  GET /country/{cc}/                      -> categories du pays + dossier "az"
  GET /country/{cc}/{categorie}/          -> chaines de cette categorie
  GET /country/{cc}/az/                   -> lettres disponibles
  GET /country/{cc}/az/{lettre}/          -> chaines commencant par cette lettre
  GET /language/                          -> liste des langues (dossiers)
  GET /language/{lang}/                   -> categories de la langue + dossier "az"
  GET /language/{lang}/{categorie}/       -> chaines de cette categorie
  GET /language/{lang}/az/                -> lettres disponibles
  GET /language/{lang}/az/{lettre}/       -> chaines commencant par cette lettre
  GET /resolve/{cc}/{chan_id}.m3u8        -> manifest HLS reecrit (URLs absolues),
                                              toujours adresse par le VRAI pays de
                                              la chaine, quelle que soit la partition
                                              utilisee pour y arriver
  GET /_status                            -> diagnostic JSON (pas lie depuis la navigation)
  POST /_admin/recheck                    -> declenche une verification manuelle

Seules les chaines marquees "ok" par le detecteur de sante (health.py) sont
listees dans la navigation -> une chaine morte/geo-bloquee/HS n'apparait
jamais devant l'utilisateur (voir "Detection de sante" ci-dessous).

Donnees generees par build_channels.py (iptv-org/api : channels/categories/
streams/countries/feeds/languages.json), pas de contenu sous licence.

Lancer :
    uvicorn app:app --host 0.0.0.0 --port 8000
"""
import asyncio
import json
import os
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

import health

DATA_DIR = Path(__file__).parent / "data"
M3U8_CONTENT_TYPE = "application/vnd.apple.mpegurl"

# Intervalle entre deux verifications automatiques (secondes). ~9800 chaines
# a 60 requetes en parallele prend de l'ordre de 30-45 min -> pas la peine de
# revener trop souvent. Configurable via variable d'environnement.
RECHECK_INTERVAL_S = int(os.environ.get("HEALTHCHECK_INTERVAL_HOURS", "6")) * 3600


# --- Etat en memoire, recharge par _reload_status() -------------------------

with (DATA_DIR / "channels.json").open(encoding="utf-8") as f:
    _channels = json.load(f)
with (DATA_DIR / "categories.json").open(encoding="utf-8") as f:
    _category_names = json.load(f)
with (DATA_DIR / "countries.json").open(encoding="utf-8") as f:
    _country_names = json.load(f)
with (DATA_DIR / "languages.json").open(encoding="utf-8") as f:
    _language_names = json.load(f)

# NetStream n'affiche JAMAIS le texte entre <a> et </a> : son parseur HTML
# (source/browsers/http_server_browser.cpp) extrait uniquement la valeur de
# l'attribut href et l'affiche telle quelle comme nom de dossier/fichier
# (confirme par les captures d'ecran reelles : on y voit "us", "az", jamais
# les libelles "France (175)" qu'on ecrivait pourtant en texte). Donc pour
# qu'un nom complet ("France", "English") soit VISIBLE sur la console, le
# href lui-meme doit etre ce nom complet -> on a besoin d'un dictionnaire
# inverse nom -> code pour retrouver la partition interne quand la Vita
# revient avec ce nom dans l'URL suivante.
_country_code_by_name = {name: code for code, name in _country_names.items()}
_language_code_by_name = {name: code for code, name in _language_names.items()}

# Deux partitions independantes sur le MEME jeu de chaines (une chaine peut
# apparaitre sous plusieurs langues si elle est multilingue, comme elle peut
# deja apparaitre sous plusieurs categories). Chaque partition a sa propre
# racine, ses (cle, categorie) et (cle, lettre) -> [chaine, ...].
_by_country = defaultdict(list)
_by_country_category = defaultdict(list)
_by_country_letter = defaultdict(list)

_by_language = defaultdict(list)
_by_language_category = defaultdict(list)
_by_language_letter = defaultdict(list)

_channel_by_country_id = {}  # (pays, id) -> chaine, pour /resolve (independant de la partition de navigation)

_status: dict = {}          # cle "PAYS:id" -> {"ok": bool, "error": str|None, "checked_at": float}
_recheck_running = False    # empeche deux verifications de tourner en meme temps


def _letter_bucket(name: str) -> str:
    first = name.strip()[:1].upper()
    return first if first.isalpha() else "0-9"


for chan in _channels:
    cc = chan["country"]
    letter = _letter_bucket(chan["name"])
    _by_country[cc].append(chan)
    _by_country_letter[(cc, letter)].append(chan)
    _channel_by_country_id[(cc, chan["id"])] = chan
    for cat in chan["categories"]:
        _by_country_category[(cc, cat)].append(chan)

    for lang in chan["languages"]:
        _by_language[lang].append(chan)
        _by_language_letter[(lang, letter)].append(chan)
        for cat in chan["categories"]:
            _by_language_category[(lang, cat)].append(chan)

_ALL_PARTITION_LISTS = (
    *_by_country.values(), *_by_country_category.values(), *_by_country_letter.values(),
    *_by_language.values(), *_by_language_category.values(), *_by_language_letter.values(),
)
for lst in _ALL_PARTITION_LISTS:
    lst.sort(key=lambda c: c["name"].lower())


def _reload_status() -> None:
    global _status
    _status = health.load_status()


_reload_status()


def is_ok(chan: dict) -> bool:
    """Une chaine jamais verifiee est consideree disponible par defaut (on ne
    veut pas vider toute la navigation avant la toute premiere verification).
    La sante d'une chaine est toujours liee a son VRAI pays d'origine (c'est
    la cle utilisee par health.py), peu importe la partition (pays ou langue)
    depuis laquelle on la consulte."""
    entry = _status.get(f"{chan['country']}:{chan['id']}")
    return True if entry is None else entry["ok"]


def only_ok(chans: list[dict]) -> list[dict]:
    return [c for c in chans if is_ok(c)]


# --- Rendu HTML minimal (celui que le parseur <a href> de NetStream attend) --

def page(items: list[tuple[str, str]]) -> str:
    lis = "\n".join(f'<li><a href="{escape(href)}">{escape(label)}</a></li>' for label, href in items)
    return f"<html><body><ul>\n{lis}\n</ul></body></html>"


def channel_links(chans: list[dict]) -> list[tuple[str, str]]:
    return [(c["name"], f"/resolve/{c['country']}/{c['id']}.m3u8") for c in only_ok(chans)]


# --- Verification de sante, en tache de fond --------------------------------

async def _run_check_and_reload() -> None:
    global _recheck_running
    if _recheck_running:
        return
    _recheck_running = True
    try:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, health.run_check, _channels)
        health.save_status(results)
        _reload_status()
    finally:
        _recheck_running = False


async def _periodic_recheck_loop() -> None:
    while True:
        await _run_check_and_reload()
        await asyncio.sleep(RECHECK_INTERVAL_S)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_periodic_recheck_loop())
    yield
    task.cancel()


app = FastAPI(title="psvita-stream-bridge", lifespan=lifespan)


# --- Navigation ---------------------------------------------------------
#
# "pays" et "langue" sont deux partitions differentes du meme jeu de chaines,
# avec exactement la meme mecanique de navigation en dessous (racine ->
# categorie ou A-Z -> chaine) -> factorisee une seule fois ici, chaque route
# ne fait que choisir les bons dictionnaires et convertir nom <-> code.
#
# Le href d'une entree "racine" (pays/langue) est le NOM COMPLET, url-quote
# (voir le commentaire sur _country_code_by_name plus haut : c'est le seul
# moyen de le rendre visible sur la console). Les niveaux plus profonds
# (categorie, "az", lettre) restent des identifiants courts deja lisibles
# (ids de categorie iptv-org, lettres) -> pas besoin du meme traitement.

def render_root_listing(by_key: dict[str, list[dict]], names: dict[str, str]) -> str:
    items = [
        (names.get(k, k), quote(names.get(k, k), safe=""))
        for k, chans in by_key.items()
        if only_ok(chans)
    ]
    items.sort(key=lambda t: t[0].lower())
    return page(items)


def render_key_categories(
    key: str, by_key: dict, by_key_category: dict, not_found_msg: str
) -> str:
    if key not in by_key:
        raise HTTPException(status_code=404, detail=not_found_msg)
    cats_here = {cat for c in by_key[key] for cat in c["categories"]}
    items = [
        (_category_names.get(cat, cat), cat)
        for cat in cats_here
        if only_ok(by_key_category[(key, cat)])
    ]
    items.sort(key=lambda t: t[0].lower())
    if only_ok(by_key[key]):
        items.insert(0, ("Toutes les chaines A-Z", "az"))
    return page(items)


def render_key_token(
    key: str, token: str, by_key: dict, by_key_category: dict, by_key_letter: dict, not_found_msg: str
) -> str:
    """Un seul niveau de route pour categorie OU 'az' (meme profondeur, segment unique)."""
    if token == "az":
        if key not in by_key:
            raise HTTPException(status_code=404, detail=not_found_msg)
        letters = sorted({_letter_bucket(c["name"]) for c in by_key[key] if is_ok(c)})
        return page([(l, l) for l in letters])

    chans = by_key_category.get((key, token))
    if chans is None:
        raise HTTPException(status_code=404, detail="categorie inconnue")
    return page(channel_links(chans))


def render_key_letter(key: str, letter: str, by_key_letter: dict, not_found_msg: str) -> str:
    chans = by_key_letter.get((key, letter.upper()))
    if chans is None:
        raise HTTPException(status_code=404, detail=not_found_msg)
    return page(channel_links(chans))


@app.get("/", response_class=HTMLResponse)
def root_menu():
    return page([("Par pays", "country"), ("Par langue", "language")])


@app.get("/country/", response_class=HTMLResponse)
def list_country_root():
    return render_root_listing(_by_country, _country_names)


@app.get("/country/{cc}/", response_class=HTMLResponse)
def list_country_categories(cc: str):
    code = _country_code_by_name.get(cc, cc.upper())
    return render_key_categories(code, _by_country, _by_country_category, "pays inconnu")


@app.get("/country/{cc}/{token}/", response_class=HTMLResponse)
def list_country_token(cc: str, token: str):
    code = _country_code_by_name.get(cc, cc.upper())
    return render_key_token(code, token, _by_country, _by_country_category, _by_country_letter, "pays inconnu")


@app.get("/country/{cc}/az/{letter}/", response_class=HTMLResponse)
def list_country_letter(cc: str, letter: str):
    code = _country_code_by_name.get(cc, cc.upper())
    return render_key_letter(code, letter, _by_country_letter, "lettre inconnue pour ce pays")


@app.get("/language/", response_class=HTMLResponse)
def list_language_root():
    return render_root_listing(_by_language, _language_names)


@app.get("/language/{lang}/", response_class=HTMLResponse)
def list_language_categories(lang: str):
    code = _language_code_by_name.get(lang, lang.lower())
    return render_key_categories(code, _by_language, _by_language_category, "langue inconnue")


@app.get("/language/{lang}/{token}/", response_class=HTMLResponse)
def list_language_token(lang: str, token: str):
    code = _language_code_by_name.get(lang, lang.lower())
    return render_key_token(code, token, _by_language, _by_language_category, _by_language_letter, "langue inconnue")


@app.get("/language/{lang}/az/{letter}/", response_class=HTMLResponse)
def list_language_letter(lang: str, letter: str):
    code = _language_code_by_name.get(lang, lang.lower())
    return render_key_letter(code, letter, _by_language_letter, "lettre inconnue pour cette langue")


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


# Manifest HLS minimal, syntaxiquement valide, sans aucun segment (RFC 8216 :
# une playlist VOD vide se termine directement par EXT-X-ENDLIST). Renvoye a
# la place de TOUTE erreur (chaine inconnue, source injoignable, timeout,
# corps recu qui n'est pas un manifest...).
#
# Pourquoi : confirme sur hardware reel qu'un code d'erreur HTTP (404/502) en
# reponse a une requete .m3u8 fait planter NetStream ENTIEREMENT (dump
# psp2core, pas une simple erreur de lecture) au lieu d'un message d'echec
# propre. Un manifest vide en 200 se comporte comme une chaine qui n'a rien
# a diffuser -> NetStream le gere sans crasher.
DEAD_CHANNEL_MANIFEST = (
    "#EXTM3U\n"
    "#EXT-X-VERSION:3\n"
    "#EXT-X-TARGETDURATION:1\n"
    "#EXT-X-MEDIA-SEQUENCE:0\n"
    "#EXT-X-PLAYLIST-TYPE:VOD\n"
    "#EXT-X-ENDLIST\n"
)


@app.get("/resolve/{cc}/{chan_id}.m3u8")
def resolve(cc: str, chan_id: str):
    chan = _channel_by_country_id.get((cc.upper(), chan_id))
    if chan:
        try:
            r = requests.get(chan["url"], timeout=10, headers={"User-Agent": "VLC/3.0.20"})
            if r.status_code == 200 and r.text.lstrip().startswith("#EXTM3U"):
                rewritten = rewrite_manifest(r.text, r.url)  # r.url = URL APRES redirection
                return Response(content=rewritten, media_type=M3U8_CONTENT_TYPE)
        except requests.RequestException:
            pass
    # Chaine inconnue, source injoignable, timeout, ou reponse invalide :
    # jamais de code d'erreur HTTP ici, voir le commentaire sur DEAD_CHANNEL_MANIFEST.
    return Response(content=DEAD_CHANNEL_MANIFEST, media_type=M3U8_CONTENT_TYPE)


# --- Diagnostic (detection de sante) ---------------------------------------
#
# Pas lie depuis la navigation NetStream (pas de "." donc NetStream le
# traiterait comme un dossier s'il y accedait, mais rien n'y pointe jamais).
# Sert a repondre a la question "c'est la chaine ou mon firmware ?" : si une
# chaine est marquee ok=true ici mais plante quand meme sur la Vita, le
# probleme est cote client (lecteur/firmware), pas cote flux.

@app.get("/_status")
def status_summary():
    if not _status:
        return JSONResponse({"checked": False, "message": "aucune verification effectuee pour le moment"})

    total = len(_status)
    ok = sum(1 for v in _status.values() if v["ok"])
    broken = [
        {"key": k, "error": v["error"]}
        for k, v in _status.items() if not v["ok"]
    ]
    last_checked = max((v["checked_at"] for v in _status.values()), default=None)

    return JSONResponse({
        "checked": True,
        "last_checked_at": last_checked,
        "recheck_running": _recheck_running,
        "total": total,
        "ok": ok,
        "broken": len(broken),
        "broken_sample": broken[:50],
    })


@app.post("/_admin/recheck")
async def trigger_recheck():
    if _recheck_running:
        return JSONResponse({"started": False, "message": "une verification est deja en cours"})
    asyncio.create_task(_run_check_and_reload())
    return JSONResponse({"started": True})
