# veilgit — transparentní šifrování v git repozitáři

## Co je veilgit

veilgit instaluje do repozitáře git `clean`/`smudge` filtry, které při `git add`
komprimují a šifrují vybrané soubory (`age` + `gzip`). Lokálně zůstávají čitelné,
na vzdáleném úložišti jsou uložené zašifrované.

## Zprovoznění po git clone

1. Nainstaluj `age` a `gzip`.
2. Získej privátní age klíč (mimo repozitář).
3. Spusť inicializační skript z kořene repozitáře:
   - Linux/macOS: `bash .veil/setup_veil.sh <cesta_k_privatnimu_klici>`
   - Windows: `python .veil/setup_veil.py <cesta_k_privatnimu_klici>`
4. Ověř filtry: `git config --get-regexp '^filter\.veil\.'`

## Přidání nového spolupracovníka

1. Přidej jeho veřejný age klíč (`age1...`) do `.veil/config.toml` a git filtrů.
2. Sdílej `.veil/setup_veil.sh` nebo `.veil/setup_veil.py` — nikdy privátní klíč.
3. Spolupracovník si vygeneruje vlastní klíč a přidá se jako recipient.

## Záloha klíče

Uchovej privátní klíč na bezpečném místě (heslem chráněný disk, správce hesel).
Bez klíče nelze zašifrovaná data obnovit.

## Bezpečnost

- Privátní klíč nikdy necommituj do gitu.
- Veřejný klíč (recipient) je bezpečné sdílet.
- Historie commitů na GitHubu může obsahovat zašifrované bloby trvale.

## Odkaz na projekt

https://github.com/FiloSottile/age — šifrovací nástroj
Projekt veilgit: viz README v repozitáři nástroje `veil_setup.py`
