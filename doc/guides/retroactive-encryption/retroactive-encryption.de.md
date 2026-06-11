# Retroaktive Verschlüsselung: Klartext aus der Git-Historie entfernen

## Problem

`veil_setup.py` hat festgestellt, dass Dateien, die Ihren Mustern entsprechen, bereits als
Klartext in der Git-Historie vorhanden sind. Das bedeutet, dass jeder mit Zugang zum
Repository diese Dateien lesen kann, auch nachdem Sie die Verschlüsselung einrichten.

Die Verschlüsselung ab diesem Zeitpunkt schützt nur **zukünftige** Commits. Um Klartext
aus der vergangenen Historie zu entfernen, müssen Sie die Git-Historie mit `git filter-repo`
neu schreiben.

> **⚠ Warnung:** Das Neuschreiben der Historie ist unwiderruflich und betrifft alle
> Mitarbeiter. Alle bestehenden Klone müssen nach dem Force-Push neu geklont werden.

---

## Voraussetzungen

Installieren Sie `git filter-repo`:

```bash
pip install git-filter-repo
# Alternative für macOS:
brew install git-filter-repo
```

Überprüfung: `git filter-repo --version`

---

## Schritt-für-Schritt-Anleitung

### Schritt 1 — Dateien sichern

Kopieren Sie die sensiblen Dateien **außerhalb** des Repositories, bevor `filter-repo`
sie entfernt:

```bash
cp -r pfad/zu/sensiblen/ /tmp/veilgit_backup/
```

### Schritt 2 — Dateien aus der gesamten Git-Historie entfernen

```bash
git filter-repo --path pfad/zu/sensiblen/ --invert-paths
```

Für mehrere Pfade wiederholen Sie `--path`:

```bash
git filter-repo \
  --path docs/private/ \
  --path secrets/ \
  --invert-paths
```

Nach diesem Befehl sind die Dateien aus dem Arbeitsverzeichnis **und** aus jedem Commit
in der Historie entfernt.

### Schritt 3 — Entfernung überprüfen

```bash
git log --all --oneline -- pfad/zu/sensiblen/
# darf keine Ausgabe erzeugen
```

### Schritt 4 — Dateien ins Arbeitsverzeichnis zurückspielen

```bash
cp -r /tmp/veilgit_backup/ pfad/zu/sensiblen/
```

### Schritt 5 — veilgit-Filter neu initialisieren

`git filter-repo` setzt `.git/config` zurück. Registrieren Sie die veilgit-Filter erneut:

```bash
python veil_setup.py . --reinit
```

### Schritt 6 — Konfiguration und verschlüsselte Dateien stagen

```bash
# Zuerst die veilgit-Konfiguration stagen
git add .gitattributes .veil/

# Die wiederhergestellten Dateien stagen — der Clean-Filter verschlüsselt sie bei git add
git add pfad/zu/sensiblen/

git commit -m "chore: sensible Dateien retroaktiv verschlüsseln"
```

### Schritt 7 — Die neu geschriebene Historie force-pushen

```bash
git push --force-with-lease origin main
```

`--force-with-lease` ist sicherer als `--force`: Es schlägt fehl, wenn der Remote Commits
enthält, die Sie lokal nicht haben, und verhindert so versehentliches Überschreiben.

### Schritt 8 — Mitarbeiter benachrichtigen

Alle bestehenden Klone weichen nach dem Force-Push ab. Jeder Mitarbeiter muss neu klonen:

```bash
git clone <repo_url>
cd <repo>
bash .veil/setup_veil.sh /pfad/zum/privaten_schluessel.txt
```

---

## Verschlüsselung überprüfen

Bestätigen Sie nach dem Commit, dass Git nur verschlüsselten Inhalt speichert:

```bash
git show HEAD:pfad/zu/sensiblen/datei.md | xxd | head -3
# Die ersten Bytes müssen den age-Verschlüsselungs-Header zeigen, kein Klartext
```

---

## Hinweise zum GitHub-Cache

GitHub kann für kurze Zeit zwischengespeicherte Objekte der alten Historie aufbewahren.
Für maximale Sicherheit (z. B. vor der Veröffentlichung des Repositories) kontaktieren Sie
den [GitHub-Support](https://support.github.com), um nach dem Force-Push einen Cache-Bereinigung
anzufordern.

---

*Generiert von veilgit. Weitere Informationen finden Sie in der Projekt-README.*
