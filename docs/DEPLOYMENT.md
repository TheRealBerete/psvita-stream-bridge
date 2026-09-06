# Deployment

*[Version française](DEPLOYMENT.fr.md)*

## Local (dev)

```bash
pip install -r requirements.txt
python build_channels.py   # generates data/*.json from the iptv-org API
python health.py           # (optional) run a first channel health check
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker compose up --build -d
```

The build runs `build_channels.py`, so the image ships with a channel list
frozen at build time. To refresh it: `docker compose build --no-cache`. The
health check itself runs in the background inside the container (no rebuild
needed for that — see `.env.example`).

## Generic reverse proxy (Nginx, Caddy, standalone Traefik…)

The container listens in plain HTTP on port `8000`. Any reverse proxy can
put it behind an HTTPS domain — just point it at `http://<container_or_ip>:8000`.

## Dokploy (the setup actually running this project in production)

[Dokploy](https://dokploy.com/) offers two ways to deploy a project: an
**"Application"** mode (native buildpack/Dockerfile, where Dokploy wires up
Traefik routing automatically) and a **"Docker Compose"** mode (you supply
your own `docker-compose.yml`, run close to as-is).

⚠️ **Gotcha hit in production**: in Docker Compose mode, Dokploy does **not**
automatically inject Traefik labels or attach the service to its shared
network — unlike Application mode. A service started with a bare
`docker-compose.yml` (just `build` + `ports`) runs perfectly fine, but stays
invisible to Traefik: the domain returns a `404 page not found` **from
Traefik, not from the app** (don't confuse it with an application 404 —
check the `Server: cloudflare`/`traefik` header and the absence of
`content-type: application/json`).

**The fix**, already in place in this repo's `docker-compose.yml`:

```yaml
networks:
  dokploy-network:
    external: true

services:
  bridge:
    build: .
    restart: unless-stopped
    networks:
      - dokploy-network
    labels:
      - traefik.enable=true
      - traefik.docker.network=dokploy-network
      - traefik.http.routers.<name>-web.rule=Host(`your-domain.tld`)
      - traefik.http.routers.<name>-web.entrypoints=web
      - traefik.http.routers.<name>-web.middlewares=redirect-to-https@file
      - traefik.http.routers.<name>-websecure.rule=Host(`your-domain.tld`)
      - traefik.http.routers.<name>-websecure.entrypoints=websecure
      - traefik.http.routers.<name>-websecure.tls.certresolver=letsencrypt
      - traefik.http.routers.<name>-websecure.service=<name>
      - traefik.http.services.<name>.loadbalancer.server.port=8000
```

Replace `<name>` and `your-domain.tld`, then set up the domain in the app's
**Domains** tab on Dokploy (container port `8000`) — Dokploy then handles
the Let's Encrypt certificate automatically. No need to publish port 8000
directly anymore (the `ports:` key can be omitted).

### If you need to run `docker compose` by hand over SSH on a Dokploy-managed server

Always pass the **project name** Dokploy uses (visible under
`/etc/dokploy/compose/<generated-name>/`), otherwise Docker Compose creates
a brand new project based on the current directory name, leaving you with a
duplicate container:

```bash
cd /etc/dokploy/compose/<dokploy-generated-name>/code
docker compose -p <dokploy-generated-name> up -d --build
```

## Environment variables

See `.env.example`. Only one for now:

| Variable | Default | Role |
|---|---|---|
| `HEALTHCHECK_INTERVAL_HOURS` | `6` | Interval between two automatic full channel health checks |

## NetStream (on the PS Vita side)

Settings → HTTP server:

- **Host address**: `http://<ip-or-domain>` — **the scheme is mandatory**,
  a bare IP/domain makes the connection fail silently on NetStream's side
  (see `docs/ARCHITECTURE.md`).
- **Port**: `8000` locally, `443` behind an HTTPS reverse proxy (NetStream's
  port field accepts `443` with an `https://` host without any special
  handling — confirmed working on real hardware).
