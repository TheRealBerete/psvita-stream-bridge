"""
Construit data/channels.json, data/categories.json et data/countries.json a
partir de l'API publique iptv-org (channels.json, categories.json,
streams.json, countries.json) :
  - garde TOUS les pays (pas seulement la France)
  - filtre les chaines fermees ("closed" non null)
  - ne garde que celles qui ont au moins un flux dans streams.json
  - associe chaque chaine a ses categories (ids -> noms lisibles)
  - ne garde que les pays qui ont au moins 1 chaine valide

A relancer de temps en temps pour rafraichir la liste (les flux changent).

Usage :
    python build_channels.py
"""
import json
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
API = "https://iptv-org.github.io/api"


def fetch(name: str):
    with urllib.request.urlopen(f"{API}/{name}") as r:
        return json.load(r)


def main():
    print("Telechargement des donnees iptv-org...")
    channels = fetch("channels.json")
    categories = fetch("categories.json")
    streams = fetch("streams.json")
    countries = fetch("countries.json")

    cat_names = {c["id"]: c["name"] for c in categories}
    country_names = {c["code"]: c["name"] for c in countries}

    # une chaine peut avoir plusieurs entrees de flux -> on garde la 1ere valide
    stream_by_channel = {}
    for s in streams:
        chan_id = s.get("channel")
        if chan_id and s.get("url") and chan_id not in stream_by_channel:
            stream_by_channel[chan_id] = s["url"]

    all_channels = []
    used_cat_ids = set()
    used_country_codes = set()
    for c in channels:
        if c.get("closed") or not c.get("country"):
            continue
        url = stream_by_channel.get(c["id"])
        if not url:
            continue
        cats = c.get("categories") or ["other"]
        all_channels.append({
            "id": c["id"],
            "name": c["name"],
            "country": c["country"],
            "categories": cats,
            "url": url,
        })
        used_cat_ids.update(cats)
        used_country_codes.add(c["country"])

    DATA_DIR.mkdir(exist_ok=True)
    with (DATA_DIR / "channels.json").open("w", encoding="utf-8") as f:
        json.dump(all_channels, f, ensure_ascii=False, indent=2)

    cat_names["other"] = "Autres"
    out_categories = {cid: cat_names.get(cid, cid) for cid in used_cat_ids}
    with (DATA_DIR / "categories.json").open("w", encoding="utf-8") as f:
        json.dump(out_categories, f, ensure_ascii=False, indent=2)

    out_countries = {cc: country_names.get(cc, cc) for cc in used_country_codes}
    with (DATA_DIR / "countries.json").open("w", encoding="utf-8") as f:
        json.dump(out_countries, f, ensure_ascii=False, indent=2)

    print(f"{len(all_channels)} chaines valides, {len(out_countries)} pays, "
          f"{len(out_categories)} categories.")


if __name__ == "__main__":
    main()
