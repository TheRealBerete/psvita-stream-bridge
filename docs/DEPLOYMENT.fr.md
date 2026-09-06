# Déploiement

## Local (dev)

```bash
pip install -r requirements.txt
python build_channels.py   # génère data/*.json depuis l'API iptv-org
python health.py           # (optionnel) premier passage de vérification des chaînes
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker compose up --build -d
```

Le build exécute `build_channels.py`, donc l'image contient une liste de
chaînes figée au moment du build. Pour la rafraîchir : `docker compose build --no-cache`.
La vérification de santé, elle, tourne en tâche de fond dans le conteneur
(pas besoin de rebuild pour ça, voir `.env.example`).

## Reverse proxy générique (Nginx, Caddy, Traefik autonome…)

Le conteneur écoute en clair sur le port `8000`. N'importe quel reverse proxy
peut le mettre derrière un domaine en HTTPS — pointer simplement vers
`http://<conteneur_ou_IP>:8000`.

## Dokploy (le cas testé en production sur ce projet)

[Dokploy](https://dokploy.com/) propose deux façons de déployer un projet :
un mode **"Application"** (buildpack/Dockerfile natif, où Dokploy gère
automatiquement le routage Traefik) et un mode **"Docker Compose"** (on
fournit son propre `docker-compose.yml`, exécuté quasi tel quel).

⚠️ **Piège rencontré** : en mode Docker Compose, Dokploy **n'injecte pas**
automatiquement les labels Traefik ni le rattachement au réseau partagé —
contrairement au mode "Application". Un service démarré avec un
`docker-compose.yml` "nu" (juste `build` + `ports`) tourne très bien, mais
reste invisible pour Traefik : le domaine renvoie un `404 page not found`
**qui vient de Traefik, pas de l'appli** (à ne pas confondre avec un 404
applicatif — vérifier le header `Server: cloudflare`/`traefik` et l'absence
de `content-type: application/json`).

**La solution**, déjà en place dans `docker-compose.yml` de ce repo :

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
      - traefik.http.routers.<nom>-web.rule=Host(`ton-domaine.tld`)
      - traefik.http.routers.<nom>-web.entrypoints=web
      - traefik.http.routers.<nom>-web.middlewares=redirect-to-https@file
      - traefik.http.routers.<nom>-websecure.rule=Host(`ton-domaine.tld`)
      - traefik.http.routers.<nom>-websecure.entrypoints=websecure
      - traefik.http.routers.<nom>-websecure.tls.certresolver=letsencrypt
      - traefik.http.routers.<nom>-websecure.service=<nom>
      - traefik.http.services.<nom>.loadbalancer.server.port=8000
```

Remplace `<nom>` et `ton-domaine.tld`, puis configure le domaine dans
l'onglet **Domains** de l'app Dokploy (port conteneur `8000`) — Dokploy
gère alors le certificat Let's Encrypt automatiquement. Plus besoin de
publier le port 8000 directement (`ports:` peut être omis).

### Si tu dois relancer `docker compose` à la main en SSH sur un serveur géré par Dokploy

Toujours préciser le **nom de projet** que Dokploy utilise (visible dans
`/etc/dokploy/compose/<nom-genere>/`), sinon Docker Compose en crée un
nouveau basé sur le nom du dossier courant, et tu te retrouves avec un
conteneur en doublon :

```bash
cd /etc/dokploy/compose/<nom-genere-par-dokploy>/code
docker compose -p <nom-genere-par-dokploy> up -d --build
```

## Variables d'environnement

Voir `.env.example`. La seule pour l'instant :

| Variable | Défaut | Rôle |
|---|---|---|
| `HEALTHCHECK_INTERVAL_HOURS` | `6` | Intervalle entre deux vérifications automatiques de toutes les chaînes |

## NetStream (côté PS Vita)

Réglages → HTTP server :

- **Adresse de l'hôte** : `http://<ip-ou-domaine>` — **le schéma est
  obligatoire**, une IP/domaine nu fait échouer la connexion silencieusement
  côté NetStream (voir `docs/ARCHITECTURE.md`).
- **Port** : `8000` en local, `443` derrière un reverse proxy HTTPS (le champ
  port de NetStream accepte `443` avec un hôte en `https://` sans problème
  particulier — confirmé fonctionnel sur hardware réel).
