"""
Verification de sante des chaines : pour chaque chaine, on refait exactement
ce que /resolve fait (GET l'URL source, suivre les redirections, verifier
qu'on recoit bien un manifest HLS valide) et on enregistre le resultat.

But : distinguer un bug cote source (chaine morte/geo-bloquee -> a masquer de
la navigation NetStream) d'un bug cote client (firmware/lecteur PS Vita ->
la chaine est marquee "ok" ici mais plante quand meme sur la console).

Usage :
    python health.py                 # verifie tout data/channels.json, ecrit data/channel_status.json
    python health.py --limit 200     # verifie un echantillon (tests rapides)
"""
import argparse
import concurrent.futures
import json
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent / "data"
STATUS_FILE = DATA_DIR / "channel_status.json"
TIMEOUT_S = 8
DEFAULT_WORKERS = 60


def check_one(chan: dict) -> tuple[bool, str | None]:
    """Reproduit la logique de /resolve (app.py) : GET + suivi de redirection
    + verification que le corps recu est bien un manifest HLS (#EXTM3U)."""
    try:
        r = requests.get(chan["url"], timeout=TIMEOUT_S, headers={"User-Agent": "VLC/3.0.20"})
    except requests.RequestException as e:
        return False, type(e).__name__
    if r.status_code != 200:
        return False, f"http_{r.status_code}"
    if not r.text.lstrip().startswith("#EXTM3U"):
        return False, "not_a_manifest"
    return True, None


def run_check(channels: list[dict], max_workers: int = DEFAULT_WORKERS) -> dict:
    results = {}
    total = len(channels)
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(check_one, c): c for c in channels}
        for fut in concurrent.futures.as_completed(futures):
            c = futures[fut]
            ok, error = fut.result()
            key = f"{c['country']}:{c['id']}"
            results[key] = {"ok": ok, "error": error, "checked_at": time.time()}
            done += 1
            if done % 500 == 0 or done == total:
                print(f"  {done}/{total} verifiees...")
    return results


def save_status(results: dict) -> None:
    STATUS_FILE.write_text(json.dumps(results), encoding="utf-8")


def load_status() -> dict:
    if not STATUS_FILE.exists():
        return {}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="ne verifier qu'un echantillon (debug)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    args = parser.parse_args()

    with (DATA_DIR / "channels.json").open(encoding="utf-8") as f:
        channels = json.load(f)
    if args.limit:
        channels = channels[: args.limit]

    print(f"Verification de {len(channels)} chaines ({args.workers} en parallele)...")
    t0 = time.time()
    results = run_check(channels, max_workers=args.workers)
    save_status(results)

    ok = sum(1 for r in results.values() if r["ok"])
    print(f"Termine en {time.time() - t0:.0f}s : {ok}/{len(results)} chaines OK.")


if __name__ == "__main__":
    main()
