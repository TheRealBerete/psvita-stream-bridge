# psvita-stream-bridge

*[English version](README.md)*

Un petit bridge HTTP qui permet à [NetStream](https://github.com/GrapheneCt/NetStream)
— un client de streaming vidéo pour **PS Vita** — de parcourir et lire des
chaînes TV en direct, organisées par pays, catégorie, et index A-Z.

Le mode "serveur HTTP" de NetStream est volontairement minimal : il parse
des liens HTML `<a href>` bruts, n'a pas de barre de recherche, et aucune
notion de catégorie. Ce projet ne touche pas à NetStream lui-même — il
expose une petite API qui parle exactement le format que NetStream
comprend déjà, alimentée aujourd'hui par la liste de chaînes publique
[iptv-org](https://github.com/iptv-org/iptv) (~10 000 chaînes, ~180 pays,
aucun contenu sous licence).

## Pourquoi ce projet existe

Streamer sur une console portable de 2012 via un client de navigation HTTP
minimal élimine d'office l'approche habituelle (protocole media-server, API
riche, endpoint de recherche). Ce bridge existe pour contourner exactement
ça — voir [`docs/ARCHITECTURE.fr.md`](docs/ARCHITECTURE.fr.md) pour le
détail des contraintes de NetStream (trouvées en lisant son code source)
qui ont dicté chaque choix de conception ici.

## Fonctionnalités

- Une arborescence de navigation que NetStream peut réellement parcourir :
  `pays → catégorie ou A-Z → chaîne → flux`.
- Réécriture du manifest HLS pour que les chemins relatifs des
  sous-playlists se résolvent correctement dans le lecteur de NetStream
  (voir [`docs/ARCHITECTURE.fr.md`](docs/ARCHITECTURE.fr.md) pour le
  pourquoi).
- **Détection de santé des chaînes** : chaque chaîne est vérifiée en tâche
  de fond selon un planning ; les chaînes mortes ou géo-bloquées sont
  automatiquement masquées de la navigation au lieu d'apparaître comme un
  lien cassé sur la console. Un endpoint `/_status` rapporte ce qui
  fonctionne, ce qui ne fonctionne pas, et pourquoi — pratique pour
  distinguer une chaîne défaillante d'un souci de console/firmware.
- Aucun proxy vidéo : le bridge ne touche jamais qu'au petit manifest
  texte ; les segments vidéo réels sont streamés directement depuis le CDN
  source vers la Vita.

## Démarrage rapide

```bash
git clone https://github.com/TheRealBerete/psvita-stream-bridge.git
cd psvita-stream-bridge
pip install -r requirements.txt
python build_channels.py      # recupere les donnees chaine/categorie/pays depuis iptv-org
uvicorn app:app --host 0.0.0.0 --port 8000
```

Ou avec Docker :

```bash
docker compose up --build -d
```

Voir [`docs/DEPLOYMENT.fr.md`](docs/DEPLOYMENT.fr.md) pour les notes de
déploiement en production, y compris un piège documenté pour les
configurations [Dokploy](https://dokploy.com/) + Traefik.

## Brancher NetStream dessus

Sur la PS Vita, dans les réglages de NetStream → HTTP server :

- **Adresse de l'hôte** : `http://<ip-ou-domaine>` — le schéma (`http://` /
  `https://`) est **obligatoire** ; une IP nue fait échouer la connexion
  silencieusement.
- **Port** : `8000` en local, ou `443` derrière un reverse proxy HTTPS.

## Diagnostic de santé

```bash
curl https://ton-domaine/_status                  # resume : total / ok / cassees, avec exemples d'erreurs
curl -X POST https://ton-domaine/_admin/recheck    # declenche une verification manuelle
```

Si une chaîne affiche `ok: true` ici mais plante quand même sur la console,
le problème est très probablement côté client (lecteur HLS/firmware), pas
le flux — voir [`docs/ARCHITECTURE.fr.md`](docs/ARCHITECTURE.fr.md#détection-de-santé-des-chaînes).

## Périmètre du projet

C'est, et ça doit rester, un **bridge de streaming de chaînes TV**. Il ne
sert que des URL de chaînes IPTV publiquement listées (données du domaine
public d'iptv-org) — il ne récupère, ne relaie, ni ne redistribue aucun
contenu vidéo à la demande sous licence, et les contributions allant dans
cette direction ne seront pas fusionnées.

## Documentation

- [`docs/ARCHITECTURE.fr.md`](docs/ARCHITECTURE.fr.md) — comment ça
  fonctionne, et les contraintes du client NetStream qui ont dicté la
  conception.
- [`docs/DEPLOYMENT.fr.md`](docs/DEPLOYMENT.fr.md) — notes de déploiement
  local, Docker, et Dokploy/Traefik.
- [`CHANGELOG.md`](CHANGELOG.md) — changements notables et vrais bugs
  trouvés (et corrigés) sur le hardware réel.
- [`CONTRIBUTING.fr.md`](CONTRIBUTING.fr.md) — comment contribuer.

## Crédits

- [NetStream](https://github.com/GrapheneCt/NetStream) par GrapheneCt — le
  client PS Vita que ce bridge sert.
- [iptv-org](https://github.com/iptv-org) — les données de chaînes
  publiques et libres de droits utilisées par défaut dans ce MVP.

## Licence

[MIT](LICENSE) pour le code de ce dépôt. Les données de chaînes viennent
d'[iptv-org](https://github.com/iptv-org), publiées dans le domaine public
sous [The Unlicense](https://github.com/iptv-org/iptv/blob/master/LICENSE).
