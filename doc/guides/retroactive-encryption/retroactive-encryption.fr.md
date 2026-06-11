# Chiffrement rétroactif : supprimer le texte clair de l'historique git

## Problème

`veil_setup.py` a détecté que des fichiers correspondant à vos motifs existent déjà dans
l'historique git en texte clair. Cela signifie que toute personne ayant accès au dépôt peut
les lire, même après avoir configuré le chiffrement pour la suite.

Le chiffrement à partir de maintenant ne protège que les **futurs** commits. Pour supprimer
le texte clair de l'historique passé, vous devez réécrire l'historique git avec
`git filter-repo`.

> **⚠ Avertissement :** La réécriture de l'historique est irréversible et affecte tous les
> collaborateurs. Tous les clones existants devront être re-clonés après le force-push.

---

## Prérequis

Installez `git filter-repo` :

```bash
pip install git-filter-repo
# Alternative macOS :
brew install git-filter-repo
```

Vérification : `git filter-repo --version`

---

## Instructions étape par étape

### Étape 1 — Sauvegarder les fichiers

Copiez les fichiers sensibles **en dehors** du dépôt avant que `filter-repo` ne les supprime :

```bash
cp -r chemin/vers/sensibles/ /tmp/veilgit_backup/
```

### Étape 2 — Supprimer les fichiers de tout l'historique git

```bash
git filter-repo --path chemin/vers/sensibles/ --invert-paths
```

Pour plusieurs chemins, répétez `--path` :

```bash
git filter-repo \
  --path docs/private/ \
  --path secrets/ \
  --invert-paths
```

Après cette commande, les fichiers sont supprimés du répertoire de travail **et** de chaque
commit de l'historique.

### Étape 3 — Vérifier la suppression

```bash
git log --all --oneline -- chemin/vers/sensibles/
# ne doit produire aucune sortie
```

### Étape 4 — Restaurer les fichiers dans le répertoire de travail

```bash
cp -r /tmp/veilgit_backup/ chemin/vers/sensibles/
```

### Étape 5 — Réinitialiser les filtres veilgit

`git filter-repo` réinitialise `.git/config`. Réenregistrez les filtres veilgit :

```bash
python veil_setup.py . --reinit
```

### Étape 6 — Indexer la configuration et les fichiers chiffrés

```bash
# D'abord, indexer la configuration veilgit
git add .gitattributes .veil/

# Indexer les fichiers restaurés — le filtre clean les chiffre lors du git add
git add chemin/vers/sensibles/

git commit -m "chore: chiffrer rétroactivement les fichiers sensibles"
```

### Étape 7 — Force-pousser l'historique réécrit

```bash
git push --force-with-lease origin main
```

`--force-with-lease` est plus sûr que `--force` : il échoue si le dépôt distant contient
des commits que vous n'avez pas localement, évitant ainsi les écrasements accidentels.

### Étape 8 — Informer les collaborateurs

Tous les clones existants divergent après le force-push. Chaque collaborateur doit
re-cloner le dépôt :

```bash
git clone <url_du_depot>
cd <repo>
bash .veil/setup_veil.sh /chemin/vers/leur_cle_privee.txt
```

---

## Vérifier le chiffrement

Après le commit, confirmez que git ne stocke que du contenu chiffré :

```bash
git show HEAD:chemin/vers/sensibles/fichier.md | xxd | head -3
# les premiers octets doivent afficher l'en-tête de chiffrement age, pas du texte clair
```

---

## Remarques sur les caches GitHub

GitHub peut conserver des objets mis en cache référençant l'ancienne histoire pendant un
certain temps. Pour une sécurité maximale (par exemple avant de rendre le dépôt public),
contactez le [support GitHub](https://support.github.com) pour demander une purge du cache
après le force-push.

---

*Généré par veilgit. Pour plus d'informations, consultez le README du projet.*
