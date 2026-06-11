# Retroaktywne szyfrowanie: usunięcie tekstu jawnego z historii git

## Problem

`veil_setup.py` wykrył, że pliki pasujące do wybranych wzorców już istnieją w historii git
jako tekst jawny. Oznacza to, że każda osoba mająca dostęp do repozytorium może je
odczytać, nawet po skonfigurowaniu szyfrowania.

Szyfrowanie od tego momentu chroni tylko **przyszłe** commity. Aby usunąć tekst jawny z
przeszłej historii, musisz przepisać historię git za pomocą `git filter-repo`.

> **⚠ Ostrzeżenie:** Przepisanie historii jest nieodwracalne i dotyczy wszystkich
> współpracowników. Wszystkie istniejące klony muszą zostać sklonowane ponownie po
> force-push.

---

## Wymagania wstępne

Zainstaluj `git filter-repo`:

```bash
pip install git-filter-repo
# Alternatywa dla macOS:
brew install git-filter-repo
```

Weryfikacja: `git filter-repo --version`

---

## Instrukcja krok po kroku

### Krok 1 — Kopia zapasowa plików

Skopiuj wrażliwe pliki **poza** repozytorium, zanim `filter-repo` je usunie:

```bash
cp -r sciezka/do/wrazliwych/ /tmp/veilgit_backup/
```

### Krok 2 — Usunięcie plików z całej historii git

```bash
git filter-repo --path sciezka/do/wrazliwych/ --invert-paths
```

Dla wielu ścieżek powtórz `--path`:

```bash
git filter-repo \
  --path docs/private/ \
  --path secrets/ \
  --invert-paths
```

Po tym poleceniu pliki znikają z katalogu roboczego **i** z każdego commitu w historii.

### Krok 3 — Weryfikacja usunięcia

```bash
git log --all --oneline -- sciezka/do/wrazliwych/
# nie powinno zwracać żadnego wyniku
```

### Krok 4 — Przywrócenie plików do katalogu roboczego

```bash
cp -r /tmp/veilgit_backup/ sciezka/do/wrazliwych/
```

### Krok 5 — Ponowna inicjalizacja filtrów veilgit

`git filter-repo` resetuje `.git/config`. Zarejestruj ponownie filtry veilgit:

```bash
python veil_setup.py . --reinit
```

### Krok 6 — Dodanie konfiguracji i zaszyfrowanych plików do indeksu

```bash
# Najpierw dodaj konfigurację veilgit
git add .gitattributes .veil/

# Dodaj przywrócone pliki — filtr clean szyfruje je podczas git add
git add sciezka/do/wrazliwych/

git commit -m "chore: retroaktywnie zaszyfruj wrażliwe pliki"
```

### Krok 7 — Force-push przepisanej historii

```bash
git push --force-with-lease origin main
```

`--force-with-lease` jest bezpieczniejszy niż `--force`: kończy się niepowodzeniem, jeśli
zdalne repozytorium ma commity, których nie masz lokalnie, zapobiegając przypadkowemu
nadpisaniu.

### Krok 8 — Powiadomienie współpracowników

Wszystkie istniejące klony rozchodzą się po force-push. Każdy współpracownik musi ponownie
sklonować repozytorium:

```bash
git clone <url_repozytorium>
cd <repo>
bash .veil/setup_veil.sh /sciezka/do/ich_klucza_prywatnego.txt
```

---

## Weryfikacja szyfrowania

Po commicie sprawdź, czy git przechowuje tylko zaszyfrowaną zawartość:

```bash
git show HEAD:sciezka/do/wrazliwych/plik.md | xxd | head -3
# pierwsze bajty powinny pokazywać nagłówek szyfrowania age, nie tekst jawny
```

---

## Uwagi dotyczące pamięci podręcznej GitHub

GitHub może przez krótki czas przechowywać obiekty z pamięci podręcznej odwołujące się do
starej historii. Dla maksymalnego bezpieczeństwa (np. przed upublicznieniem repozytorium)
skontaktuj się z [pomocą techniczną GitHub](https://support.github.com), aby po force-push
zażądać wyczyszczenia pamięci podręcznej.

---

*Wygenerowano przez veilgit. Więcej informacji znajdziesz w README projektu.*
