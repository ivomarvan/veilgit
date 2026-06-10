# veilgit — Design Rules

Binding invariants for `veil_setup.py`. These rules take precedence over general coding
guidelines when they conflict.

---

## 1. Translation Table Consistency

Every user-facing string belongs to the `TRANSLATIONS` dict in `veil_setup.py`.
The helper `_t(de, fr, sp, cs, pl)` enforces the exact set of supported languages:

```python
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("en", "de", "fr", "sp", "cs", "pl")
```

**Rule:** adding, removing, or changing any English key (or its English default text) requires
updating **all five** non-English translations in the same change.

```python
# ❌ — French and Polish translations missing
"Confirm setup": _t(
    "Setup bestätigen",   # de
    "",                   # fr — MISSING
    "Confirmar ajustes",  # sp
    "Potvrdit nastavení", # cs
    "",                   # pl — MISSING
),

# ✅ — all five languages present and meaningful
"Confirm setup": _t(
    "Setup bestätigen",      # de
    "Confirmer la config",   # fr
    "Confirmar ajustes",     # sp
    "Potvrdit nastavení",    # cs
    "Potwierdź konfigurację", # pl
),
```

A translation entry with an empty string `""` is only acceptable as a deliberate
placeholder marked with a `# TODO: translate` comment.

If `SUPPORTED_LANGUAGES` is extended with a new language code, **every existing entry**
in `TRANSLATIONS` must receive the new column, and `_t()` must be updated to accept it.

---

## 2. README.md Must Stay in Sync

`README.md` is the canonical reference for end users. It must be updated **in the same
change** as any modification to `veil_setup.py` that affects:

| Change type | README section to update |
|-------------|--------------------------|
| New or removed CLI flag | `## CLI modes` table |
| New supported language | `## Language` — supported codes list, resolution order |
| Changed language resolution order | `## Language` — resolution order |
| New prerequisite tool | `## Prerequisites` |
| Changed version constant `VERSION` | (no dedicated section needed — reflects in `--version` output) |

```python
# ❌ — added --export flag in veil_setup.py but README CLI table unchanged

# ✅ — added --export flag and updated README ## CLI modes table in the same edit
```
