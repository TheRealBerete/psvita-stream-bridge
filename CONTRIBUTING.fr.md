# Contribuer

*[English version](CONTRIBUTING.md)*

Merci de considérer une contribution ! C'est un petit projet personnel, la
barre est basse mais quelques points aident à garder le tout maintenable.

## Périmètre du projet

Ce bridge existe pour traduire une source de chaînes TV dans le format HTTP
exact que [NetStream](https://github.com/GrapheneCt/NetStream) sur PS Vita
sait parcourir et lire. Ce n'est **pas** un serveur multimédia généraliste,
et ce n'est **pas** destiné à redistribuer du contenu sous licence — voir
l'avertissement dans `README.fr.md`.

## Mise en place

```bash
git clone https://github.com/TheRealBerete/psvita-stream-bridge.git
cd psvita-stream-bridge
pip install -r requirements.txt
python build_channels.py
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Lis `docs/ARCHITECTURE.fr.md` avant de toucher à `app.py` — la majorité de
son code existe pour contourner une contrainte precise et verifiee du
client NetStream. Si un changement te semble inutilement complique, verifie
d'abord ce fichier ; il y a probablement une raison documentee juste
au-dessus du code concerne.

## Faire des changements

- Garde stable la forme de `data/channels.json` (`id`, `name`, `country`,
  `categories`, `url`) — tout ce qui utilise ce bridge comme modele pour une
  autre source de donnees compte sur sa simplicite.
- Si tu touches a quoi que ce soit lie au modele de navigation de NetStream
  (hrefs de dossier, extensions de fichier, sortie HTML), reverifie contre
  le tableau de contraintes de `docs/ARCHITECTURE.fr.md`, et teste sur un
  vrai appareil si possible — ce projet a deja livre des bugs subtils qui
  ne se voyaient que sur le hardware reel (voir `CHANGELOG.md`).
- Il n'y a pas encore de suite de tests. Pour l'instant, teste manuellement
  les routes que tu as modifiees avec `curl` (voir les exemples dans les
  README) avant d'ouvrir une pull request, et mentionne ce que tu as teste
  dans la description de la PR.

## Signaler une chaine cassee ou un comportement etrange de NetStream

Ouvre une issue avec :
- l'URL exacte que tu as appelee (`/resolve/...`, `/_status`, etc.),
- ce que NetStream (ou `curl`) affiche,
- ce que `/_status` rapporte pour cette chaine, si pertinent.

## Pull requests

Des PR petites et ciblees sont plus faciles a relire que des grosses. Si tu
prevois un changement important (un nouveau backend de source de donnees,
un autre schema de navigation), ouvre d'abord une issue pour en discuter.
