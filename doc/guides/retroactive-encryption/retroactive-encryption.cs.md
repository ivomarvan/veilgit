# Retroaktivní šifrování: Odstranění prostého textu z historie gitu

## Problém

`veil_setup.py` zjistil, že soubory odpovídající vybraným vzorům již existují v historii
gitu jako prostý text. To znamená, že kdokoli s přístupem k repozitáři si je může přečíst,
i když od teď nastavíte šifrování.

Šifrování od tohoto bodu chrání pouze **budoucí** commity. Chcete-li odstranit prostý text
z minulé historie, musíte přepsat historii gitu pomocí nástroje `git filter-repo`.

> **⚠ Varování:** Přepis historie je nevratný a týká se všech spolupracovníků.
> Všechny existující klony musí být po force-push znovu naklonovány.

---

## Předpoklady

Nainstalujte `git filter-repo`:

```bash
pip install git-filter-repo
# alternativa pro macOS:
brew install git-filter-repo
```

Ověření: `git filter-repo --version`

---

## Postup krok za krokem

### Krok 1 — Záloha souborů

Zkopírujte citlivé soubory **mimo** repozitář dříve, než je `filter-repo` odstraní:

```bash
cp -r cesta/k/citlivym/ /tmp/veilgit_zaloha/
```

### Krok 2 — Odstranění souborů z celé historie gitu

```bash
git filter-repo --path cesta/k/citlivym/ --invert-paths
```

Pro více cest opakujte `--path`:

```bash
git filter-repo \
  --path docs/private/ \
  --path secrets/ \
  --invert-paths
```

Po tomto příkazu jsou soubory odstraněny z pracovního adresáře **i** z každého commitu
v historii.

### Krok 3 — Ověření odstranění

```bash
git log --all --oneline -- cesta/k/citlivym/
# nesmí vrátit žádný výstup
```

### Krok 4 — Obnovení souborů do pracovního adresáře

```bash
cp -r /tmp/veilgit_zaloha/ cesta/k/citlivym/
```

### Krok 5 — Opětovná inicializace veilgit filtrů

`git filter-repo` resetuje `.git/config`. Znovu zaregistrujte veilgit filtry:

```bash
python veil_setup.py . --reinit
```

### Krok 6 — Přidání konfigurace a šifrovaných souborů do indexu

```bash
# Nejdříve přidejte konfiguraci veilgit
git add .gitattributes .veil/

# Přidejte obnovené soubory — clean filtr je při git add zašifruje
git add cesta/k/citlivym/

git commit -m "chore: retroaktivně zašifrovat citlivé soubory"
```

### Krok 7 — Force-push přepsané historie

```bash
git push --force-with-lease origin main
```

`--force-with-lease` je bezpečnější než `--force`: selže, pokud remote obsahuje commity,
které nemáte lokálně, čímž zabrání náhodnému přepsání.

### Krok 8 — Upozornění spolupracovníků

Všechny existující klony se po force-push rozcházejí. Každý spolupracovník musí znovu
naklonovat repozitář:

```bash
git clone <url_repozitare>
cd <repo>
bash .veil/setup_veil.sh /cesta/k/jejich/soukromemu_klici.txt
```

---

## Ověření šifrování

Po commitu ověřte, že git ukládá pouze šifrovaný obsah:

```bash
git show HEAD:cesta/k/citlivym/soubor.md | xxd | head -3
# první bajty musí být hlavička age šifrování, ne prostý text
```

---

## Poznámky ke cache GitHubu

GitHub může po určitou dobu uchovávat objekty odkazující na starou historii.
Pro maximální bezpečnost (např. před zveřejněním repozitáře) kontaktujte
[GitHub Support](https://support.github.com) a požádejte o vyčištění cache po force-push.

---

*Vygenerováno nástrojem veilgit. Více informací viz README projektu.*
