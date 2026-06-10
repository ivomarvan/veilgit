# veilgit — Projektové zadání (brief)

## Přehled projektu

**Název projektu:** veilgit  
**Název hlavního skriptu:** `veil_setup.py`  
**Jazyk:** Python 3.8+  
**Závislosti:** pouze standardní knihovna (`argparse`, `pathlib`, `subprocess`, `shutil`, `sys`, `os`, `re`, `glob`, `tomllib` / `tomli` fallback — viz sekce závislostí)  
**Primární platforma:** Linux (základní). Sekundárně macOS. Windows není prioritou, ale kód nesmí být záměrně nefunkční.

Linux + macOS jako first-class citizens, Windows s best-effort podporou.

### Co projekt dělá

`veil_setup.py` je interaktivní instalační skript, který do jiného git repozitáře (dále jen "cílový repozitář") zavede systém **transparentního šifrování vybraných souborů při publikaci na GitHub**.

Po nastavení jsou soubory odpovídající zvoleným vzorům v repozitáři uloženy šifrovaně (formát `.gz.age`). Lokálně jsou viditelné jako plaintext — šifrování a dešifrování probíhá automaticky přes **git `clean`/`smudge` filtry** (`.gitattributes` + `git config`). Uživatel si soubory commituje normálně; git se o šifrování postará sám.

Šifrovací nástroj: **`age`** (https://github.com/FiloSottile/age).  
Komprese: **`gzip`** (vždy před šifrováním, ne po).

---

## Architektura řešení v cílovém repozitáři

Po spuštění `veil_setup.py <cesta-k-repo>` skript do cílového repozitáře přidá:

```
.gitattributes                  ← clean/smudge filtry pro šifrované vzory
.veil/
    config.toml                 ← konfigurace: vzory souborů, cesta ke klíči, verze
    setup_veil.sh               ← inicializační skript pro nového uživatele po git clone
    README_VEIL.md              ← dokumentace: jak systém funguje, jak zprovoznit po klonu
```

Soubor `.veil/config.toml` je sám označen jako šifrovaný (skript ho přidá do `.gitattributes`), takže do repozitáře jde pouze v zašifrované podobě.

---

## Princip šifrování: git clean/smudge filtry

`clean` filtr se spustí při `git add` — komprimuje a šifruje soubor:
```
gzip -9 | age -r <public_key>
```

`smudge` filtr se spustí při `git checkout` — dešifruje a dekomprimuje soubor:
```
age --decrypt -i <private_key_path> | gzip -d
```

Konfigurace se zapíše do `.git/config` cílového repozitáře (lokálně, nepushuje se):
```ini
[filter "veil"]
    clean  = gzip -9 | age -r <recipient_public_key>
    smudge = age --decrypt -i <private_key_path> | gzip -d
    required = true
```

Do `.gitattributes` cílového repozitáře se přidají řádky ve tvaru:
```
*.md filter=veil
*.txt filter=veil
secrets/** filter=veil
```

---

## Rozhraní příkazové řádky (`argparse`)

```
veil_setup.py <repo_path> [volby]
```

### Poziční argument

| Argument | Popis |
|---|---|
| `repo_path` | Cesta k cílovému git repozitáři |

### Volitelné přepínače

| Přepínač | Popis |
|---|---|
| `--dry-run` | **Ladící režim:** vypíše všechny plánované akce, nic nezapíše ani neprovede. Simuluje celý průběh. |
| `--add-pattern` | Přidá vzor do existující konfigurace (nekonfigurace znovu od začátku, jen přidá) |
| `--remove-pattern` | Odebere vzor z existující konfigurace |
| `--reinit` | Znovu zapíše git config filtry (užitečné po klonu na novém stroji) |
| `--show-config` | Vypíše aktuální konfiguraci ze `.veil/config.toml` |
| `--version` | Vypíše verzi `veil_setup.py` |

### `--dry-run` — detailní chování

Při `--dry-run`:
- Skript projde **celým interaktivním průběhem** (dotazy, výpisy, verifikace souborů) jako při normálním spuštění
- Každou akci, která by normálně zapisovala soubor nebo spouštěla příkaz, místo toho **vypíše na stdout** ve formátu:
  ```
  [DRY-RUN] Zapsal by: .gitattributes
  [DRY-RUN] Spustil by: git config filter.veil.clean "gzip -9 | age -r age1xyz..."
  [DRY-RUN] Vytvořil by adresář: .veil/
  ```
- Na konci vypíše **souhrn všech akcí**, které by byly provedeny
- Žádný soubor se nevytvoří, nezmění ani nesmaže
- Žádný příkaz se nespustí (ani `git config`, ani `age-keygen`)

---

## Interaktivní průběh skriptu (normální spuštění)

### Krok 0: Kontrola závislostí

Skript na začátku zkontroluje dostupnost:
- `age` (šifrování)
- `age-keygen` (generování klíčů)
- `gzip` (komprese)
- `git` (správa repozitáře)

Pro každý chybějící nástroj vypíše **konkrétní instalační instrukci** podle detekované platformy:

| Platforma | Detekce | Instrukce pro `age` |
|---|---|---|
| Linux (Debian/Ubuntu) | `os.path.exists('/etc/debian_version')` | `sudo apt install age` |
| Linux (Fedora/RHEL) | `os.path.exists('/etc/redhat-release')` | `sudo dnf install age` |
| Linux (Arch) | `os.path.exists('/etc/arch-release')` | `sudo pacman -S age` |
| macOS | `sys.platform == 'darwin'` | `brew install age` |
| Obecný Linux | fallback | odkaz na https://github.com/FiloSottile/age/releases |

Pokud chybí závislost, skript **vypíše instrukci a ukončí se** (nepokoušet se instalovat automaticky).

### Krok 1: Detekce existující konfigurace

Skript zkontroluje, zda `.veil/config.toml` v cílovém repozitáři existuje.
- Pokud ano: vypíše aktuální konfiguraci a zeptá se, zda pokračovat v úpravě (s `--reinit` rovnou přeskočí na inicializaci filtrů)
- Pokud ne: začíná čistá instalace

### Krok 2: Interaktivní volba vzorů souborů

Skript v cyklu:
1. Vypíše nápovědu: "Zadejte glob vzor nebo regulární výraz popisující soubory, které chcete šifrovat (např. `*.md`, `secrets/**`, `docs/*.txt`). Prázdný vstup ukončí zadávání."
2. Přijme vzor od uživatele
3. **Okamžitě ověří** — vypíše seznam souborů, které vzor aktuálně v cílovém repozitáři odpovídá (relativní cesty). Pokud vzor nic nenachází, upozorní (ale nevyhodí chybu).
4. Zeptá se: "Je výběr správný? (a=přidat / n=zadat znovu / s=přeskočit tento vzor)"
5. Po potvrzení přidá vzor do seznamu
6. Cyklus pokračuje, dokud uživatel nezadá prázdný vstup

Na konci zobrazí **souhrnný seznam** všech vzorů a souborů, které pokrývají, a zeptá se na finální potvrzení.

**Formát vzorů:** akceptují se glob vzory kompatibilní s `.gitattributes` (ne Python regex). Skript je nekonvertuje — ukládá je přímo ve tvaru pro `.gitattributes`.

### Krok 3: Správa klíčů

Skript zkontroluje, zda uživatel již má age klíč.

**Výchozí cesta ke klíči:**
- Linux/macOS: `~/.config/age/<jmeno_repo>_key.txt`

Možnosti:
1. **Vygenerovat nový klíč** — skript spustí `age-keygen -o <cesta>` a zobrazí vygenerovaný **veřejný klíč** (recipient)
2. **Použít existující klíč** — uživatel zadá cestu k existujícímu klíči; skript ji ověří (soubor existuje, je čitelný, obsahuje validní age klíč formát)

Po získání klíče skript:
- Zobrazí **bezpečnostní upozornění** (viz sekce níže)
- Pokračuje ke konfiguraci

**Bezpečnostní upozornění (vždy zobrazit před zápisem):**
```
BEZPEČNOST:
  - Soukromý klíč NIKDY nepřidávej do git repozitáře.
  - Zálohu klíče uchovej na bezpečném místě (heslem chráněný disk, správce hesel).
  - Bez klíče nelze zašifrovaná data obnovit.
  - Veřejný klíč (recipient) je bezpečné sdílet — slouží jen k šifrování.
  - Historie commitů na GitHubu obsahuje .gz.age soubory navždy — i po smazání souboru
    z repozitáře. Měj to na paměti.
```

### Krok 4: Podpora více příjemců (volitelné)

Skript se zeptá: "Chceš přidat další příjemce (spolupracovníky), kteří budou moci data dešifrovat? (a/N)"

Pokud ano:
- V cyklu přijímá veřejné age klíče dalších příjemců (ve formátu `age1...`)
- Ověří formát klíče (regex: `^age1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}$`)
- Každý přidaný klíč se zapíše do `config.toml` i do `git config` jako další `-r` argument

### Krok 5: Zápis konfigurace a inicializace

Skript zapíše / aktualizuje:

1. **`.veil/config.toml`** — příklad obsahu:
   ```toml
   [veil]
   version = "1"
   key_path = "~/.config/age/myrepo_key.txt"
   
   [veil.recipients]
   primary = "age1xyz..."
   others = ["age1abc...", "age1def..."]
   
   [veil.patterns]
   patterns = ["*.md", "*.txt", "secrets/**"]
   
   [veil.exclude]
   patterns = []
   ```

2. **`.gitattributes`** — přidá (nebo aktualizuje existující) záznamy:
   ```
   # veilgit managed — do not edit manually
   *.md filter=veil diff=veil
   *.txt filter=veil diff=veil
   .veil/config.toml filter=veil diff=veil
   ```
   Skript **neodstraní** existující záznamy v `.gitattributes`, jen přidá chybějící. Označí spravované záznamy komentářem.

3. **`.git/config` cílového repozitáře** — git filtry (lokální, nepushuje se):
   ```ini
   [filter "veil"]
       clean  = gzip -9 | age -r age1xyz... [-r age1abc...]
       smudge = age --decrypt -i ~/.config/age/myrepo_key.txt | gzip -d
       required = true
   [diff "veil"]
       textconv = age --decrypt -i ~/.config/age/myrepo_key.txt | gzip -d
   ```

4. **`.veil/setup_veil.sh`** — shell skript pro inicializaci na novém stroji:
   ```bash
   #!/usr/bin/env bash
   # Spusť tento skript po git clone pro aktivaci šifrování.
   # Vyžaduje: age, gzip. Viz .veil/README_VEIL.md.
   # Použití: bash .veil/setup_veil.sh <cesta_k_privatnimu_klici>
   ```
   Skript zapíše git config filtry do lokálního `.git/config`.
   Akceptuje cestu ke klíči jako argument.

5. **`.veil/README_VEIL.md`** — dokumentace systému:
   - Co je veilgit a jak funguje
   - Jak zprovoznit repozitář po `git clone` (krok za krokem)
   - Jak přidat nového spolupracovníka
   - Jak zálohat klíč
   - Upozornění na bezpečnost
   - Odkaz na projekt veilgit

### Krok 6: Finální souhrn

Skript vypíše:
```
Hotovo. Systém veilgit byl nastaven v repozitáři: /cesta/k/repo

Zašifrované vzory: *.md, *.txt, .veil/config.toml
Veřejný klíč (recipient): age1xyz...
Soukromý klíč: ~/.config/age/myrepo_key.txt

Další kroky:
  1. Přidej .gitattributes do commitu: git add .gitattributes .veil/
  2. Při příštím 'git add' se soubory automaticky zašifrují.
  3. Sdílej .veil/setup_veil.sh se spolupracovníky (ne klíč!).
```

---

## Idempotentnost

Skript lze bezpečně spustit znovu na již nakonfigurovaném repozitáři:
- Existující vzory v `config.toml` se nezmaží — nové se přidají
- Existující záznamy v `.gitattributes` se nepřepíší — chybějící se doplní
- Git config filtry se přepíší (aktualizace)
- Uživatel je informován, co se změnilo a co zůstalo beze změny

---

## Závislosti projektu `veilgit`

### Runtime závislosti (co musí být na systému)
- `age` (šifrování) — **musí mít uživatel**
- `age-keygen` (součást balíčku `age`)
- `gzip` (standardně přítomný na Linuxu/macOS)
- `git`

### Python závislosti skriptu `veil_setup.py`
- **Žádné externí knihovny.** Pouze standardní knihovna:
  - `argparse`, `pathlib`, `subprocess`, `shutil`, `sys`, `os`, `re`, `glob`, `textwrap`
  - `tomllib` (Python 3.11+) nebo `tomli` jako fallback pro starší verze
    - Skript detekuje verzi Pythonu a importuje správně:
      ```python
      try:
          import tomllib
      except ImportError:
          try:
              import tomli as tomllib
          except ImportError:
              tomllib = None  # pro zápis TOML stačí vlastní minimální serializer
      ```
    - **Pro zápis TOML** skript použije vlastní minimální serializér (TOML je dostatečně jednoduchý pro danou strukturu), aby se vyhnul závislosti na `tomli`.

---

## Multiplatformnost

| Funkce | Linux | macOS | Windows |
|---|---|---|---|
| Detekce platformy | `sys.platform`, `/etc/*-release` | `sys.platform == 'darwin'` | `sys.platform == 'win32'` |
| Cesta ke klíči | `~/.config/age/` | `~/.config/age/` | `%APPDATA%\age\` |
| Instrukce pro instalaci `age` | `apt`/`dnf`/`pacman` | `brew` | odkaz na releases |
| `setup_veil.sh` | plně funkční | plně funkční | negeneruje se, místo toho `setup_veil.py` |
| Oddělovač cest | `/` | `/` | `\` (pathlib řeší automaticky) |

**Poznámka k Windows:**
- Skript nesmí záměrně selhat na Windows, ale `setup_veil.sh` se na Windows negeneruje
- Místo toho se vygeneruje `setup_veil.py` (čistý Python, bez bashe)
- `gzip` a `age` jsou na Windows dostupné (WSL nebo nativní binárky), ale instalační instrukce jsou odlišné

---

## Struktura repozitáře `veilgit`

```
veilgit/
├── veil_setup.py          ← hlavní skript
├── README.md              ← dokumentace projektu veilgit
├── requirements.txt       ← prázdný nebo jen `tomli>=2.0; python_version < "3.11"`
├── LICENSE
└── doc/
    └── project-progress/
        └── brief.md       ← tento soubor
```

---

## Testování a ladění

- Primárním nástrojem pro ladění je `--dry-run`
- Doporučené ruční testování:
  1. Vytvořit prázdný testovací git repozitář: `git init /tmp/test_repo`
  2. Spustit: `python veil_setup.py /tmp/test_repo --dry-run`
  3. Ověřit výpis akcí
  4. Spustit bez `--dry-run` a ověřit vytvořené soubory
  5. Přidat testovací `*.md` soubor, `git add`, `git commit` — ověřit, že v `.git/objects` je zašifrovaný obsah
  6. `git checkout` — ověřit, že soubor je čitelný

---

## Bezpečnostní poznámky pro implementátora

1. **Skript nesmí logovat ani tisknout soukromý klíč ani jeho obsah** — jen veřejný klíč (recipient)
2. **Soubor klíče nesmí skript nikdy přidávat do `.gitignore` jako jediný řádek pro celou cestu** — klíč je mimo repozitář, to je dostatečné
3. Výstup `age-keygen` jde na stderr (veřejný klíč) a do souboru — skript parsuje ze stderr řádek začínající `# public key:`
4. `required = true` v git config filtru zajistí, že pokud `age` není dostupný, `git` odmítne operaci — toto chování je žádoucí

---

## Verze

`veil_setup.py` verze `0.1.0`  
Datum zadání: 2026-06-10
