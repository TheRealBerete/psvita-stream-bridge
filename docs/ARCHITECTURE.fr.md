# Architecture

## Le problème

[NetStream](https://github.com/GrapheneCt/NetStream) est un client de streaming
pour PS Vita. Son mode "serveur HTTP" est volontairement minimal :

- il parse la réponse comme du **HTML** et cherche des balises `<a href="...">`
  (pas de JSON, pas de protocole media-server type Jellyfin/Plex/DLNA) ;
- il n'a **aucune recherche texte** ;
- son lecteur HLS interne ne reconnaît un fichier que si l'URL se termine
  littéralement par `.m3u8`.

Ce dépôt ne réécrit pas NetStream : il expose une petite API HTTP qui **parle
exactement le langage que NetStream sait lire**, pour n'importe quelle source
de chaînes derrière (aujourd'hui [iptv-org](https://github.com/iptv-org/iptv),
potentiellement autre chose demain).

## Vue d'ensemble

```
PS Vita (NetStream) ──HTTP simple──▶ bridge (ce repo) ──HTTP──▶ CDN des chaînes
                                          │
                                          ├─ data/channels.json (pays, catégories, url)
                                          └─ data/channel_status.json (sain/mort, health.py)
```

Le bridge ne relaie **jamais** le flux vidéo lui-même (aucun proxy vidéo) :
il ne fait qu'un aller-retour sur le petit manifest texte (`.m3u8`), que la
Vita télécharge ensuite directement depuis le vrai CDN. La bande passante
vidéo ne transite jamais par le bridge.

## Contraintes NetStream, trouvées en lisant son code source

Toutes vérifiées dans [GrapheneCt/NetStream](https://github.com/GrapheneCt/NetStream)
(licence propre à ce projet, code non modifié ici — seulement étudié pour
comprendre son comportement client) :

| Contrainte | Fichier source | Conséquence sur ce bridge |
|---|---|---|
| Le champ "Adresse de l'hôte" doit contenir un schéma explicite (`http://` ou `https://`) | `include/menus/menu_http.h` (champ `keyboard_type="url"`), `curl_url_set(CURLUPART_URL, ...)` | Documenté dans le README — une IP nue fait échouer `curl_url_set` silencieusement |
| Navigation = parsing HTML `<a href="...">`, pas JSON | `source/browsers/http_server_browser.cpp` | Toutes les routes de navigation renvoient du HTML minimal (`app.py:page()`) |
| Un fichier lisible doit avoir une extension reconnue, `.m3u8` pour le flux HLS | `source/players/player_beav.cpp` (`k_supportedExtensions`) | Toute route de résolution se termine par `.m3u8` |
| **`SetPath()` (navigation dossier) fait une simple concaténation de chaînes** : `url_actuelle + escape(href) + "/"`, **pas** une vraie résolution d'URL relative (RFC 3986) | `source/browsers/http_server_browser.cpp::SetPath` | Chaque `href` de **dossier** doit être un segment unique, sans aucun `/` dedans, sinon on obtient un double-slash → 404 → dossier vide côté Vita |
| Le lecteur HLS interne (`GetInfoForPlayer`) fait, lui, une vraie fusion d'URL | `source/browsers/http_server_browser.cpp::GetInfoForPlayer` | Les `href` de **fichiers** (`/resolve/...`) peuvent être des chemins absolus sans problème |
| Le lecteur HLS résout les chemins **relatifs à l'intérieur d'un manifest** par rapport à l'URL demandée (le bridge), pas par rapport à l'hôte réel du flux après redirection | comportement observé (pas de code source disponible pour cette partie fermée) | `/resolve/...` télécharge le manifest lui-même et réécrit chaque URI (lignes + attributs `URI="..."`) en absolu via `urljoin` avant de le renvoyer |

## Arborescence de navigation exposée

```
/                          liste des pays
/{cc}/                     catégories du pays + raccourci "az"
/{cc}/{categorie}/         chaînes de cette catégorie
/{cc}/az/                  lettres disponibles
/{cc}/az/{lettre}/         chaînes commençant par cette lettre
/resolve/{cc}/{id}.m3u8    manifest HLS réécrit, prêt à être lu
/_status                   diagnostic JSON (santé des chaînes)
/_admin/recheck            déclenche une vérification manuelle (POST)
```

Il n'y a pas de recherche texte (NetStream n'en offre pas) : la navigation
par catégorie et l'index alphabétique en tiennent lieu.

## Détection de santé des chaînes

`health.py` reproduit exactement la logique de `/resolve` (requête HTTP,
suivi des redirections, vérification que le corps commence par `#EXTM3U`)
sur l'ensemble des chaînes, en parallèle (`ThreadPoolExecutor`). Le résultat
est écrit dans `data/channel_status.json` et rechargé en mémoire par `app.py`.

Une chaîne jamais vérifiée est considérée disponible par défaut (pour ne pas
vider toute la navigation avant la toute première vérification). Une chaîne
marquée `ok: false` disparaît de la navigation — catégories, index A-Z et
liste des pays recalculent leurs compteurs en conséquence.

Le bridge relance cette vérification automatiquement en tâche de fond au
démarrage puis toutes les `HEALTHCHECK_INTERVAL_HOURS` heures (6 par défaut,
voir `.env.example`). Elle peut aussi être déclenchée manuellement :

```bash
curl -X POST https://ton-domaine/_admin/recheck
```

**Utilité pratique** : si une chaîne est marquée `ok: true` dans `/_status`
mais plante quand même sur la Vita, le problème est côté client (lecteur
HLS/firmware de la console), pas côté flux — ça isole vite la source d'un bug.

## Pourquoi pas de vraie base de données ?

Le volume (~10 000 chaînes, quelques Mo de JSON) et le usage pattern (lecture
seule côté navigation, une réécriture complète périodique côté santé) ne
justifient pas une base de données : des fichiers JSON chargés en mémoire au
démarrage suffisent et gardent le déploiement trivial (une seule image Docker,
aucune dépendance externe).
