# anime-vita-bridge (MVP)

Petit bridge HTTP qui expose des chaines IPTV publiques ([iptv-org/api](https://github.com/iptv-org/api),
donnees libres, pas de contenu sous licence) sous une forme que le client
PS Vita [NetStream](https://github.com/GrapheneCt/NetStream) sait consommer
en mode "HTTP server" : navigation par pays -> categorie / A-Z -> chaine, et
resolution HLS avec reecriture de manifest.

## Pourquoi ce bridge existe

NetStream ne parle que HTTP simple + fichiers reconnus par extension — pas de
JSON, pas de protocole media-server (Jellyfin/Plex/DLNA), pas de recherche
texte. Ce service traduit une source de donnees (ici iptv-org) dans le format
exact qu'il attend. Voir les commentaires dans `app.py` pour le detail des
contraintes reverse-engineerees depuis le code source de NetStream.

## Lancer en local

```bash
pip install -r requirements.txt
python build_channels.py   # genere data/*.json depuis l'API iptv-org
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Lancer avec Docker

```bash
docker compose up --build -d
```

Le build execute `build_channels.py`, donc l'image contient une liste de
chaines figee au moment du build. Pour la rafraichir : `docker compose build --no-cache`.

## Brancher NetStream dessus

Dans NetStream (PS Vita), reglages -> HTTP server :

- **Adresse de l'hote** : `http://<IP_OU_DOMAINE_DU_SERVEUR>` (le `http://`
  est obligatoire, une IP nue fait echouer la connexion — voir pourquoi dans
  `app.py`)
- **Port** : `8000` (ou celui choisi en prod, ex. 80/443 derriere un reverse proxy)

## Arborescence exposee

```
/                          -> liste des pays
/{cc}/                     -> categories du pays + "az"
/{cc}/{categorie}/         -> chaines de la categorie
/{cc}/az/{lettre}/         -> chaines commencant par cette lettre
/resolve/{cc}/{id}.m3u8    -> manifest HLS reecrit (URLs absolues)
```

## Etat du projet

MVP valide sur hardware reel (Vita + NetStream) avec les chaines iptv-org.
Prochaine etape : remplacer `build_channels.py` (source iptv-org) par une
vraie source de contenu legitime (Jellyfin auto-heberge ou API officielle)
sans toucher au reste du bridge — `app.py` ne depend que de la forme du
fichier `data/channels.json` (`id`, `name`, `country`, `categories`, `url`).
