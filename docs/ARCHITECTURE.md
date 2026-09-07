# Architecture

*[Version française](ARCHITECTURE.fr.md)*

## The problem

[NetStream](https://github.com/GrapheneCt/NetStream) is a streaming client
for the PS Vita. Its "HTTP server" mode is deliberately minimal:

- it parses the response as **HTML** and looks for `<a href="...">` tags
  (no JSON, no media-server protocol like Jellyfin/Plex/DLNA);
- it has **no text search** at all;
- its internal HLS player only recognizes a file if the URL literally ends
  in `.m3u8`.

This repo doesn't rewrite NetStream: it exposes a small HTTP API that
**speaks exactly the language NetStream already understands**, in front of
whatever channel source sits behind it (today [iptv-org](https://github.com/iptv-org/iptv),
potentially something else tomorrow).

## Overview

```
PS Vita (NetStream) ──plain HTTP──▶ bridge (this repo) ──HTTP──▶ channel CDN
                                          │
                                          ├─ data/channels.json (country, categories, url)
                                          └─ data/channel_status.json (up/down, health.py)
```

The bridge **never** proxies the actual video stream: it only does a single
round-trip on the small text manifest (`.m3u8`), which the Vita then
downloads directly from the real CDN. Video bandwidth never flows through
the bridge.

## NetStream constraints, found by reading its source code

All verified in [GrapheneCt/NetStream](https://github.com/GrapheneCt/NetStream)
(that project's own license applies to its code — only studied here to
understand client behavior, never modified):

| Constraint | Source file | Consequence for this bridge |
|---|---|---|
| The "Host address" field must contain an explicit scheme (`http://` or `https://`) | `include/menus/menu_http.h` (`keyboard_type="url"` field), `curl_url_set(CURLUPART_URL, ...)` | Documented in the README — a bare IP/domain makes `curl_url_set` fail silently |
| Navigation = HTML `<a href="...">` parsing, not JSON | `source/browsers/http_server_browser.cpp` | Every navigation route returns minimal HTML (`app.py:page()`) |
| A readable file needs a recognized extension, `.m3u8` for HLS | `source/players/player_beav.cpp` (`k_supportedExtensions`) | Every resolution route ends in `.m3u8` |
| **`SetPath()` (folder navigation) does plain string concatenation**: `current_url + escape(href) + "/"`, **not** real RFC 3986 relative URL resolution | `source/browsers/http_server_browser.cpp::SetPath` | Every **folder** `href` must be a single segment with no `/` inside it, otherwise a double slash appears → 404 → empty folder on the Vita |
| The internal HLS player (`GetInfoForPlayer`), on the other hand, does proper URL merging | `source/browsers/http_server_browser.cpp::GetInfoForPlayer` | **File** hrefs (`/resolve/...`) can safely be absolute paths |
| The HLS player resolves relative paths **inside a manifest** against the URL it was given (the bridge), not against the real stream host after redirection | observed behavior (this part is closed-source, no code available) | `/resolve/...` fetches the manifest itself and rewrites every URI (playlist lines and `URI="..."` attributes) to an absolute one via `urljoin` before returning it |
| **The HTML parser only ever looks at the `href="..."` attribute** — the text between `<a>` and `</a>` is parsed but never displayed on the console | `source/browsers/http_server_browser.cpp` (the loop only extracts the `href` substring; confirmed against real screenshots, which always show the raw href, never a "pretty" label) | Any human-readable name (a country, a language) has to **be** the href itself (URL-quoted), not just the link's text |

## Exposed navigation tree

```
/                              choice: browse by country or by language
/country/                      list of countries
/country/{cc}/                 the country's categories + an "az" shortcut
/country/{cc}/{category}/      channels in that category
/country/{cc}/az/              available letters
/country/{cc}/az/{letter}/     channels starting with that letter
/language/                     list of languages
/language/{lang}/              the language's categories + an "az" shortcut
/language/{lang}/{category}/   channels in that category
/language/{lang}/az/           available letters
/language/{lang}/az/{letter}/  channels starting with that letter
/resolve/{cc}/{id}.m3u8         rewritten HLS manifest, ready to play — always
                                addressed by the channel's real country, no
                                matter which partition (country or language)
                                was used to reach it
/_status                       JSON health diagnostics
/_admin/recheck                 manually trigger a health check (POST)
```

**Country and language are two independent partitions over the exact same
channel set**, not two separate datasets: a channel can appear under several
languages (if it broadcasts bilingually) the same way it can already appear
under several categories. Both partitions share the identical
category/A-Z browsing logic underneath (`render_key_categories`,
`render_key_token`, `render_key_letter` in `app.py`) — only the partitioning
key changes. Language data comes from a separate `feeds.json` endpoint
(`channels.json` itself carries no language field) and covers 100% of the
channels used here.

There's no text search (NetStream doesn't offer one): category browsing and
the alphabetical index stand in for it.

## Channel health detection

`health.py` reproduces the exact logic of `/resolve` (HTTP request, follow
redirects, check that the body starts with `#EXTM3U`) across every channel,
in parallel (`ThreadPoolExecutor`). Results are written to
`data/channel_status.json` and reloaded into memory by `app.py`.

A channel that has never been checked is considered available by default
(so navigation isn't empty before the very first check completes). A
channel marked `ok: false` disappears from navigation — country lists,
categories, and the A-Z index all recompute their counts accordingly.

The bridge re-runs this check automatically in the background on startup,
then every `HEALTHCHECK_INTERVAL_HOURS` hours (6 by default, see
`.env.example`). It can also be triggered manually:

```bash
curl -X POST https://your-domain/_admin/recheck
```

**Practical use**: if a channel is marked `ok: true` in `/_status` but still
fails to play on the Vita, the problem is on the client side (the console's
HLS player/firmware), not the stream — this narrows down the source of a
bug quickly.

## Why no real database?

The scale (~10,000 channels, a few MB of JSON) and the usage pattern
(read-only navigation, one periodic full rewrite for health data) don't
justify a database: JSON files loaded into memory at startup are enough,
and they keep the deployment trivial — a single Docker image, no external
dependency.
