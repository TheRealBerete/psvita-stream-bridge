# Changelog

Format loosely based on [Keep a Changelog](https://keepachangelog.com/).
This project doesn't cut versioned releases yet — entries are grouped by
milestone instead of a version number.

## Unreleased

### Added
- Channel health detection (`health.py`): every channel is checked in
  parallel against the same logic `/resolve` uses, results stored in
  `data/channel_status.json`. Broken channels are automatically filtered
  out of navigation. Runs on startup and every `HEALTHCHECK_INTERVAL_HOURS`
  (default 6h), plus a manual `POST /_admin/recheck` trigger and a
  `GET /_status` diagnostics endpoint.
- Project scope confirmed as TV channel streaming (iptv-org data) — no
  plans to add licensed anime/manga sources.
- Open-source housekeeping: MIT license, `CONTRIBUTING.md`,
  `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, English + French docs.
- **Browse by country or by language**: the landing page now asks which
  partition to browse first (`/country/` or `/language/`), each sharing the
  identical category/A-Z navigation logic underneath. Language data comes
  from a previously-unused iptv-org endpoint (`feeds.json`), with 100%
  channel coverage. A channel can appear under multiple languages, the same
  way it already could under multiple categories.
- Root and country/language listings now show the actual **full name**
  (e.g. "France", "English") instead of a 2-3 letter code — discovered that
  NetStream's HTML parser only ever reads the `href="..."` attribute and
  never displays the link's inner text, so the full name has to be the href
  itself (URL-quoted), not just a label.

## MVP (initial working version)

### Added
- FastAPI bridge exposing an HTTP-server-mode-compatible navigation tree
  for [NetStream](https://github.com/GrapheneCt/NetStream) on PS Vita:
  countries → categories / A-Z index → channels → HLS manifest.
- HLS manifest rewriting (`rewrite_manifest`) to fix relative paths that
  NetStream's player resolves against the wrong base URL.
- `build_channels.py`: pulls channel/category/country/stream data from the
  public [iptv-org/api](https://github.com/iptv-org/api).
- Docker image + `docker-compose.yml`.
- Deployed to production behind a domain via Dokploy + Traefik.

### Fixed (all confirmed on real PS Vita hardware)
- NetStream's "Host address" field requires an explicit `http://`/`https://`
  scheme — a bare IP fails silently (`E-00000003`).
- NetStream's folder navigation (`SetPath()`) does plain string
  concatenation, not real relative-URL resolution — folder `href`s must be
  a single path segment with no `/` in them, or double slashes 404.
- Manifests with relative sub-playlist paths broke playback because
  NetStream's HLS player resolved them against the bridge's URL instead of
  the real CDN's — fixed by rewriting every manifest to absolute URLs
  before returning it.
- `requests` was missing from `requirements.txt` (worked by accident in a
  local dev environment that already had it installed globally) — the
  Docker container crashed on startup with `ModuleNotFoundError`.
- Dokploy's "Docker Compose" deployment mode doesn't auto-attach Traefik
  labels/network the way its "Application" mode does — the domain returned
  a Traefik-level 404 until labels and the shared network were added by
  hand (see `docs/DEPLOYMENT.md`).
