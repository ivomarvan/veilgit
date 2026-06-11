#!/usr/bin/env python3
"""Install transparent age+gzip encryption into a git repository via git filters."""

import argparse
import dataclasses
import fnmatch
import locale
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    import tomllib  # type: ignore[import-not-found]
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

VERSION = "0.1.0"

SUPPORTED_LANGUAGES: Tuple[str, ...] = ("en", "de", "fr", "sp", "cs", "pl")
DEFAULT_LANGUAGE = "en"
LANGUAGE_TOML_COMMENT = '# language = "en" # Set default language (en, de, fr, sp, cs, pl)'

_current_language: str = DEFAULT_LANGUAGE

REQUIRED_TOOLS: Tuple[str, ...] = ("age", "age-keygen", "gzip", "git")

AGE_PUBLIC_KEY_RE = re.compile(r"^age1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{58}$")

DRY_RUN_PLACEHOLDER_PUBLIC_KEY = "age1" + "q" * 58

GLOB_PATTERN_PROMPT = (
    "Enter glob patterns for files to encrypt (e.g. *.md, secrets/**). Empty input finishes."
)

CLI_DESCRIPTION = (
    "Install transparent age+gzip encryption into a git repository via clean/smudge filters."
)

SECURITY_WARNING_KEY = (
    "SECURITY:\n"
    "  - Never add the private key to the git repository.\n"
    "  - Back up the key securely (password-protected disk, password manager).\n"
    "  - Encrypted data cannot be recovered without the key.\n"
    "  - The public key (recipient) is safe to share — it is only used for encryption.\n"
    "  - GitHub commit history may retain .gz.age blobs permanently — even after file deletion.\n"
    "    Keep this in mind."
)


def get_current_language() -> str:
    """Return the active communication language code."""
    return _current_language


def set_current_language(lang: str) -> None:
    """Set the active communication language code."""
    global _current_language
    _current_language = lang


def _normalize_language_code(locale_str: Optional[str]) -> Optional[str]:
    """Extract a supported two-letter language code from a locale string."""
    if not locale_str:
        return None
    code = locale_str.split(".")[0].split("_")[0].lower()
    if code in SUPPORTED_LANGUAGES:
        return code
    return None


def detect_os_language() -> Optional[str]:
    """Detect the OS locale and return a supported language code, if any."""
    if sys.platform == "win32":
        try:
            default_locale = locale.getdefaultlocale()
            if default_locale and default_locale[0]:
                return _normalize_language_code(default_locale[0])
        except (ValueError, locale.Error):
            return None
        return None
    lang_env = os.environ.get("LANG") or os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
    return _normalize_language_code(lang_env)


def resolve_language(
    cli_lang: Optional[str],
    config_lang: Optional[str],
) -> str:
    """Resolve language using priority: CLI > config > OS > default."""
    if cli_lang:
        return cli_lang
    if config_lang:
        return config_lang
    os_lang = detect_os_language()
    if os_lang:
        return os_lang
    return DEFAULT_LANGUAGE


def init_language(args: argparse.Namespace, repo_path: Optional[Path] = None) -> None:
    """Resolve and store the active language from CLI, config, and OS."""
    config_lang: Optional[str] = None
    if repo_path is not None:
        config = read_config(repo_path / ".veil" / "config.toml")
        if config is not None and config.language:
            config_lang = config.language
    set_current_language(resolve_language(args.lang, config_lang))


def _t(de: str, fr: str, sp: str, cs: str, pl: str) -> Dict[str, str]:
    """Build a non-English translation map for a single message key."""
    return {"de": de, "fr": fr, "sp": sp, "cs": cs, "pl": pl}


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "Missing required tool: ": _t(
        "Fehlendes Werkzeug: ",
        "Outil requis manquant : ",
        "Herramienta requerida: ",
        "Chybí požadovaný nástroj: ",
        "Brak wymaganego narzędzia: ",
    ),
    "Install: ": _t(
        "Installation: ",
        "Installation : ",
        "Instalación: ",
        "Instalace: ",
        "Instalacja: ",
    ),
    "Not configured": _t(
        "Nicht konfiguriert",
        "Non configuré",
        "No configurado",
        "Není nakonfigurováno",
        "Nieskonfigurowane",
    ),
    "(none)": _t("(keine)", "(aucun)", "(ninguno)", "(žádné)", "(brak)"),
    GLOB_PATTERN_PROMPT: _t(
        "Glob-Muster für zu verschlüsselnde Dateien eingeben (z.B. *.md). Leere Eingabe beendet.",
        "Entrez des motifs glob (ex. *.md). Entrée vide pour terminer.",
        "Introduce patrones glob (p. ej. *.md). Entrada vacía para terminar.",
        "Zadejte glob vzor popisující soubory, které chcete šifrovat "
        "(např. *.md, secrets/**, docs/*.txt). Prázdný vstup ukončí zadávání.",
        "Podaj wzorce glob (np. *.md). Puste wejście kończy.",
    ),
    "Pattern: ": _t("Muster: ", "Motif : ", "Patrón: ", "Vzor: ", "Wzorzec: "),
    "Matching files:": _t(
        "Passende Dateien:",
        "Fichiers correspondants :",
        "Archivos coincidentes:",
        "Odpovídající soubory:",
        "Pasujące pliki:",
    ),
    "Warning: pattern matches no existing files.": _t(
        "Warnung: Muster trifft auf keine Dateien zu.",
        "Attention : aucun fichier ne correspond.",
        "Aviso: el patrón no coincide con ningún archivo.",
        "Upozornění: vzor neodpovídá žádnému existujícímu souboru.",
        "Ostrzeżenie: wzorzec nie pasuje do żadnego pliku.",
    ),
    "Is the selection correct? (a=add / n=retry / s=skip): ": _t(
        "Ist die Auswahl korrekt? (a=hinzufügen / n= wiederholen / s=überspringen): ",
        "Sélection correcte ? (a=ajouter / n=réessayer / s=ignorer) : ",
        "¿Selección correcta? (a=añadir / n=reintentar / s=omitir): ",
        "Je výběr správný? (a=přidat / n=zadat znovu / s=přeskočit): ",
        "Czy wybór jest poprawny? (a=dodaj / n=ponów / s=pomiń): ",
    ),
    "Invalid choice. Enter a, n, or s.": _t(
        "Ungültige Wahl. a, n oder s eingeben.",
        "Choix invalide. Entrez a, n ou s.",
        "Opción no válida. Introduce a, n o s.",
        "Neplatná volba. Zadejte a, n nebo s.",
        "Nieprawidłowy wybór. Wpisz a, n lub s.",
    ),
    "Summary of selected patterns:": _t(
        "Zusammenfassung der Muster:",
        "Résumé des motifs :",
        "Resumen de patrones:",
        "Souhrn vybraných vzorů:",
        "Podsumowanie wybranych wzorców:",
    ),
    "  (none)": _t("  (keine)", "  (aucun)", "  (ninguno)", "  (žádné)", "  (brak)"),
    "  - {pattern} -> {count} file(s)": _t(
        "  - {pattern} -> {count} Datei(en)",
        "  - {pattern} -> {count} fichier(s)",
        "  - {pattern} -> {count} archivo(s)",
        "  - {pattern} -> {count} soubor(ů)",
        "  - {pattern} -> {count} plik(ów)",
    ),
    SECURITY_WARNING_KEY: _t(
        "SICHERHEIT:\n"
        "  - Privaten Schlüssel NIE ins Git-Repository legen.\n"
        "  - Schlüssel sicher sichern.\n"
        "  - Ohne Schlüssel keine Wiederherstellung.\n"
        "  - Öffentlichen Schlüssel teilen ist sicher.\n"
        "  - GitHub-Historie kann .gz.age dauerhaft behalten.",
        "SÉCURITÉ :\n"
        "  - Ne jamais ajouter la clé privée au dépôt git.\n"
        "  - Sauvegardez la clé en lieu sûr.\n"
        "  - Sans clé, pas de récupération.\n"
        "  - La clé publique peut être partagée.\n"
        "  - L'historique GitHub peut conserver les .gz.age.",
        "SEGURIDAD:\n"
        "  - Nunca añadas la clave privada al repositorio git.\n"
        "  - Guarda la clave de forma segura.\n"
        "  - Sin clave no hay recuperación.\n"
        "  - La clave pública se puede compartir.\n"
        "  - El historial de GitHub puede retener .gz.age.",
        "BEZPEČNOST:\n"
        "  - Soukromý klíč NIKDY nepřidávej do git repozitáře.\n"
        "  - Zálohu klíče uchovej na bezpečném místě (heslem chráněný disk, správce hesel).\n"
        "  - Bez klíče nelze zašifrovaná data obnovit.\n"
        "  - Veřejný klíč (recipient) je bezpečné sdílet — slouží jen k šifrování.\n"
        "  - Historie commitů na GitHubu obsahuje .gz.age soubory navždy — i po smazání souboru\n"
        "    z repozitáře. Měj to na paměti.",
        "BEZPIECZEŃSTWO:\n"
        "  - Nigdy nie dodawaj klucza prywatnego do repozytorium git.\n"
        "  - Przechowuj kopię klucza bezpiecznie.\n"
        "  - Bez klucza nie odzyskasz danych.\n"
        "  - Klucz publiczny można udostępniać.\n"
        "  - Historia GitHub może zachować .gz.age.",
    ),
    "Default key path: {path}": _t(
        "Standard-Schlüsselpfad: {path}",
        "Chemin de clé par défaut : {path}",
        "Ruta de clave predeterminada: {path}",
        "Výchozí cesta ke klíči: {path}",
        "Domyślna ścieżka klucza: {path}",
    ),
    "1) Generate a new key": _t(
        "1) Neuen Schlüssel erzeugen",
        "1) Générer une nouvelle clé",
        "1) Generar una clave nueva",
        "1) Vygenerovat nový klíč",
        "1) Wygeneruj nowy klucz",
    ),
    "2) Use an existing key": _t(
        "2) Vorhandenen Schlüssel verwenden",
        "2) Utiliser une clé existante",
        "2) Usar una clave existente",
        "2) Použít existující klíč",
        "2) Użyj istniejącego klucza",
    ),
    "Choice [1/2]: ": _t(
        "Wahl [1/2]: ",
        "Choix [1/2] : ",
        "Opción [1/2]: ",
        "Volba [1/2]: ",
        "Wybór [1/2]: ",
    ),
    "Path for new key [{default}]: ": _t(
        "Pfad für neuen Schlüssel [{default}]: ",
        "Chemin de la nouvelle clé [{default}] : ",
        "Ruta de la clave nueva [{default}]: ",
        "Cesta pro nový klíč [{default}]: ",
        "Ścieżka nowego klucza [{default}]: ",
    ),
    "Public key (recipient): {key}": _t(
        "Öffentlicher Schlüssel (Empfänger): {key}",
        "Clé publique (destinataire) : {key}",
        "Clave pública (recipiente): {key}",
        "Veřejný klíč (recipient): {key}",
        "Klucz publiczny (odbiorca): {key}",
    ),
    "Path to existing key: ": _t(
        "Pfad zum vorhandenen Schlüssel: ",
        "Chemin de la clé existante : ",
        "Ruta de la clave existente: ",
        "Cesta k existujícímu klíči: ",
        "Ścieżka do istniejącego klucza: ",
    ),
    "Invalid key file. Enter a valid age private key path.": _t(
        "Ungültige Schlüsseldatei.",
        "Fichier de clé invalide.",
        "Archivo de clave no válido.",
        "Neplatný soubor klíče. Zadejte cestu k platnému age privátnímu klíči.",
        "Nieprawidłowy plik klucza.",
    ),
    "Invalid public key format.": _t(
        "Ungültiges Format des öffentlichen Schlüssels.",
        "Format de clé publique invalide.",
        "Formato de clave pública no válido.",
        "Neplatný formát veřejného klíče.",
        "Nieprawidłowy format klucza publicznego.",
    ),
    "Invalid choice. Enter 1 or 2.": _t(
        "Ungültige Wahl. 1 oder 2 eingeben.",
        "Choix invalide. Entrez 1 ou 2.",
        "Opción no válida. Introduce 1 o 2.",
        "Neplatná volba. Zadejte 1 nebo 2.",
        "Nieprawidłowy wybór. Wpisz 1 lub 2.",
    ),
    "Public key (recipient) for this key: ": _t(
        "Öffentlicher Schlüssel (Empfänger) für diesen Schlüssel: ",
        "Clé publique (destinataire) pour cette clé : ",
        "Clave pública (recipiente) para esta clave: ",
        "Veřejný klíč (recipient) pro tento klíč: ",
        "Klucz publiczny (odbiorca) dla tego klucza: ",
    ),
    "Add additional recipients who can decrypt data? (y/N): ": _t(
        "Weitere Empfänger hinzufügen? (j/N): ",
        "Ajouter d'autres destinataires ? (o/N) : ",
        "¿Añadir destinatarios adicionales? (s/N): ",
        "Chceš přidat další příjemce (spolupracovníky), kteří budou moci data dešifrovat? (a/N): ",
        "Dodać dodatkowych odbiorców? (t/N): ",
    ),
    "Enter public age keys (empty input finishes):": _t(
        "Öffentliche age-Schlüssel eingeben (leer beendet):",
        "Entrez les clés publiques age (entrée vide termine) :",
        "Introduce claves públicas age (entrada vacía termina):",
        "Zadej veřejné age klíče (prázdný vstup ukončí zadávání):",
        "Podaj publiczne klucze age (puste wejście kończy):",
    ),
    "Recipient: ": _t(
        "Empfänger: ",
        "Destinataire : ",
        "Recipiente: ",
        "Recipient: ",
        "Odbiorca: ",
    ),
    "Invalid key format. Expected age1... (61 characters).": _t(
        "Ungültiges Schlüsselformat. Erwartet age1... (61 Zeichen).",
        "Format invalide. Attendu age1... (61 caractères).",
        "Formato no válido. Se espera age1... (61 caracteres).",
        "Neplatný formát klíče. Očekáván řetězec age1... (61 znaků).",
        "Nieprawidłowy format. Oczekiwano age1... (61 znaków).",
    ),
    "This key was already added.": _t(
        "Dieser Schlüssel wurde bereits hinzugefügt.",
        "Cette clé a déjà été ajoutée.",
        "Esta clave ya fue añadida.",
        "Tento klíč už byl přidán.",
        "Ten klucz został już dodany.",
    ),
    "[DRY-RUN] Would write: {path}": _t(
        "[DRY-RUN] Würde schreiben: {path}",
        "[DRY-RUN] Écrirait : {path}",
        "[DRY-RUN] Escribiría: {path}",
        "[DRY-RUN] Zapsal by: {path}",
        "[DRY-RUN] Zapisałby: {path}",
    ),
    "[DRY-RUN] Would run: {cmd}": _t(
        "[DRY-RUN] Würde ausführen: {cmd}",
        "[DRY-RUN] Exécuterait : {cmd}",
        "[DRY-RUN] Ejecutaría: {cmd}",
        "[DRY-RUN] Spustil by: {cmd}",
        "[DRY-RUN] Uruchomiłby: {cmd}",
    ),
    "[DRY-RUN] Would create directory: {path}": _t(
        "[DRY-RUN] Würde Verzeichnis erstellen: {path}",
        "[DRY-RUN] Créerait le répertoire : {path}",
        "[DRY-RUN] Crearía directorio: {path}",
        "[DRY-RUN] Vytvořil by adresář: {path}",
        "[DRY-RUN] Utworzyłby katalog: {path}",
    ),
    "[DRY-RUN] Would set executable bit: {path}": _t(
        "[DRY-RUN] Würde Ausführungsbit setzen: {path}",
        "[DRY-RUN] Définirait le bit exécutable : {path}",
        "[DRY-RUN] Establecería bit ejecutable: {path}",
        "[DRY-RUN] Nastavil by executable bit: {path}",
        "[DRY-RUN] Ustawiłby bit wykonywalności: {path}",
    ),
    "Done. veilgit was configured in repository: {repo}": _t(
        "Fertig. veilgit wurde im Repository konfiguriert: {repo}",
        "Terminé. veilgit configuré dans le dépôt : {repo}",
        "Listo. veilgit configurado en el repositorio: {repo}",
        "Hotovo. Systém veilgit byl nastaven v repozitáři: {repo}",
        "Gotowe. veilgit skonfigurowany w repozytorium: {repo}",
    ),
    "Encrypted patterns: {patterns}": _t(
        "Verschlüsselte Muster: {patterns}",
        "Motifs chiffrés : {patterns}",
        "Patrones cifrados: {patterns}",
        "Zašifrované vzory: {patterns}",
        "Zaszyfrowane wzorce: {patterns}",
    ),
    "Private key: {path}": _t(
        "Privater Schlüssel: {path}",
        "Clé privée : {path}",
        "Clave privada: {path}",
        "Soukromý klíč: {path}",
        "Klucz prywatny: {path}",
    ),
    "Next steps:": _t(
        "Nächste Schritte:",
        "Prochaines étapes :",
        "Próximos pasos:",
        "Další kroky:",
        "Następne kroki:",
    ),
    "  1. Commit .gitattributes: git add .gitattributes .veil/": _t(
        "  1. .gitattributes committen: git add .gitattributes .veil/",
        "  1. Committez .gitattributes : git add .gitattributes .veil/",
        "  1. Haz commit de .gitattributes: git add .gitattributes .veil/",
        "  1. Přidej .gitattributes do commitu: git add .gitattributes .veil/",
        "  1. Dodaj .gitattributes do commita: git add .gitattributes .veil/",
    ),
    "  2. Files encrypt automatically on the next 'git add'.": _t(
        "  2. Dateien werden beim nächsten 'git add' automatisch verschlüsselt.",
        "  2. Les fichiers seront chiffrés au prochain 'git add'.",
        "  2. Los archivos se cifran automáticamente en el próximo 'git add'.",
        "  2. Při příštím 'git add' se soubory automaticky zašifrují.",
        "  2. Pliki szyfrowane automatycznie przy następnym 'git add'.",
    ),
    "  3. Share .veil/setup_veil.sh with collaborators (not the key!).": _t(
        "  3. .veil/setup_veil.sh mit Mitarbeitern teilen (nicht den Schlüssel!).",
        "  3. Partagez .veil/setup_veil.sh (pas la clé !).",
        "  3. Comparte .veil/setup_veil.sh (¡no la clave!).",
        "  3. Sdílej .veil/setup_veil.sh se spolupracovníky (ne klíč!).",
        "  3. Udostępnij .veil/setup_veil.sh współpracownikom (nie klucz!).",
    ),
    "Continue editing configuration? (y/N): ": _t(
        "Konfiguration weiter bearbeiten? (j/N): ",
        "Continuer la modification ? (o/N) : ",
        "¿Continuar editando la configuración? (s/N): ",
        "Pokračovat v úpravě konfigurace? (a/N): ",
        "Kontynuować edycję konfiguracji? (t/N): ",
    ),
    "Aborted.": _t("Abgebrochen.", "Annulé.", "Cancelado.", "Ukončeno.", "Przerwano."),
    "Planned actions summary (dry-run):": _t(
        "Zusammenfassung geplanter Aktionen (Dry-Run):",
        "Résumé des actions prévues (dry-run) :",
        "Resumen de acciones planificadas (dry-run):",
        "Souhrn plánovaných akcí (dry-run):",
        "Podsumowanie planowanych akcji (dry-run):",
    ),
    "Error: repo_path is required for --show-config.": _t(
        "Fehler: repo_path ist für --show-config erforderlich.",
        "Erreur : repo_path requis pour --show-config.",
        "Error: repo_path es obligatorio para --show-config.",
        "Chyba: repo_path je povinný pro --show-config.",
        "Błąd: repo_path jest wymagany dla --show-config.",
    ),
    "Error: repo_path is required for --add-pattern.": _t(
        "Fehler: repo_path ist für --add-pattern erforderlich.",
        "Erreur : repo_path requis pour --add-pattern.",
        "Error: repo_path es obligatorio para --add-pattern.",
        "Chyba: repo_path je povinný pro --add-pattern.",
        "Błąd: repo_path jest wymagany dla --add-pattern.",
    ),
    "Error: repo_path is required for --remove-pattern.": _t(
        "Fehler: repo_path ist für --remove-pattern erforderlich.",
        "Erreur : repo_path requis pour --remove-pattern.",
        "Error: repo_path es obligatorio para --remove-pattern.",
        "Chyba: repo_path je povinný pro --remove-pattern.",
        "Błąd: repo_path jest wymagany dla --remove-pattern.",
    ),
    "Error: repo_path is required for --reinit.": _t(
        "Fehler: repo_path ist für --reinit erforderlich.",
        "Erreur : repo_path requis pour --reinit.",
        "Error: repo_path es obligatorio para --reinit.",
        "Chyba: repo_path je povinný pro --reinit.",
        "Błąd: repo_path jest wymagany dla --reinit.",
    ),
    "Error: repository is not configured (.veil/config.toml missing).": _t(
        "Fehler: Repository nicht konfiguriert (.veil/config.toml fehlt).",
        "Erreur : dépôt non configuré (.veil/config.toml absent).",
        "Error: repositorio no configurado (falta .veil/config.toml).",
        "Chyba: repozitář není nakonfigurován (.veil/config.toml neexistuje).",
        "Błąd: repozytorium nieskonfigurowane (brak .veil/config.toml).",
    ),
    "Pattern added: {pattern}": _t(
        "Muster hinzugefügt: {pattern}",
        "Motif ajouté : {pattern}",
        "Patrón añadido: {pattern}",
        "Přidán vzor: {pattern}",
        "Wzorzec dodany: {pattern}",
    ),
    "Pattern already exists: {pattern}": _t(
        "Muster existiert bereits: {pattern}",
        "Motif déjà présent : {pattern}",
        "El patrón ya existe: {pattern}",
        "Vzor už existuje: {pattern}",
        "Wzorzec już istnieje: {pattern}",
    ),
    "Pattern removed: {pattern}": _t(
        "Muster entfernt: {pattern}",
        "Motif supprimé : {pattern}",
        "Patrón eliminado: {pattern}",
        "Odebrán vzor: {pattern}",
        "Wzorzec usunięty: {pattern}",
    ),
    "Pattern not found: {pattern}": _t(
        "Muster nicht gefunden: {pattern}",
        "Motif introuvable : {pattern}",
        "Patrón no encontrado: {pattern}",
        "Vzor nenalezen: {pattern}",
        "Nie znaleziono wzorca: {pattern}",
    ),
    "Git config filters were re-written.": _t(
        "Git-Config-Filter wurden neu geschrieben.",
        "Filtres git réécrits.",
        "Filtros git reescritos.",
        "Git config filtry byly znovu zapsány.",
        "Filtry git config zostały ponownie zapisane.",
    ),
    CLI_DESCRIPTION: _t(
        "Transparente age+gzip-Verschlüsselung per clean/smudge-Filter installieren.",
        "Installer le chiffrement age+gzip transparent via filtres clean/smudge.",
        "Instalar cifrado age+gzip transparente mediante filtros clean/smudge.",
        "Nainstaluje transparentní age+gzip šifrování do git repozitáře přes clean/smudge filtry.",
        "Instaluje przezroczyste szyfrowanie age+gzip w repozytorium git "
        "przez filtry clean/smudge.",
    ),
    "Path to the target git repository": _t(
        "Pfad zum Ziel-Git-Repository",
        "Chemin du dépôt git cible",
        "Ruta al repositorio git de destino",
        "Cesta k cílovému git repozitáři",
        "Ścieżka do docelowego repozytorium git",
    ),
    "Simulate the full setup flow without writing files or running commands": _t(
        "Vollständigen Setup-Ablauf simulieren ohne Dateien oder Befehle",
        "Simuler la configuration sans écrire de fichiers ni exécuter de commandes",
        "Simular la configuración sin escribir archivos ni ejecutar comandos",
        "Simulovat celý průběh nastavení bez zápisu souborů a spouštění příkazů",
        "Symuluj pełną konfigurację bez zapisu plików i uruchamiania poleceń",
    ),
    "Add a glob pattern to an existing configuration": _t(
        "Glob-Muster zur bestehenden Konfiguration hinzufügen",
        "Ajouter un motif glob à la configuration existante",
        "Añadir un patrón glob a la configuración existente",
        "Přidat glob vzor do existující konfigurace",
        "Dodaj wzorzec glob do istniejącej konfiguracji",
    ),
    "Remove a glob pattern from an existing configuration": _t(
        "Glob-Muster aus bestehender Konfiguration entfernen",
        "Supprimer un motif glob de la configuration existante",
        "Eliminar un patrón glob de la configuración existente",
        "Odebrat glob vzor z existující konfigurace",
        "Usuń wzorzec glob z istniejącej konfiguracji",
    ),
    "Re-write git config filters from existing .veil/config.toml": _t(
        "Git-Config-Filter aus .veil/config.toml neu schreiben",
        "Réécrire les filtres git depuis .veil/config.toml",
        "Reescribir filtros git desde .veil/config.toml existente",
        "Znovu zapsat git config filtry z existujícího .veil/config.toml",
        "Ponownie zapisz filtry git z istniejącego .veil/config.toml",
    ),
    "Print the current .veil/config.toml contents": _t(
        "Aktuellen Inhalt von .veil/config.toml ausgeben",
        "Afficher le contenu actuel de .veil/config.toml",
        "Mostrar el contenido actual de .veil/config.toml",
        "Vypsat aktuální obsah .veil/config.toml",
        "Wyświetl bieżącą zawartość .veil/config.toml",
    ),
    "Print veil_setup.py version and exit": _t(
        "veil_setup.py-Version ausgeben und beenden",
        "Afficher la version de veil_setup.py et quitter",
        "Mostrar la versión de veil_setup.py y salir",
        "Vypsat verzi veil_setup.py a ukončit",
        "Wyświetl wersję veil_setup.py i zakończ",
    ),
    "Communication language (en, de, fr, sp, cs, pl)": _t(
        "Kommunikationssprache (en, de, fr, sp, cs, pl)",
        "Langue de communication (en, de, fr, sp, cs, pl)",
        "Idioma de comunicación (en, de, fr, sp, cs, pl)",
        "Jazyk komunikace (en, de, fr, sp, cs, pl)",
        "Język komunikacji (en, de, fr, sp, cs, pl)",
    ),
    "Show this help message and exit": _t(
        "Diese Hilfe anzeigen und beenden",
        "Afficher cette aide et quitter",
        "Mostrar esta ayuda y salir",
        "Zobrazit tuto nápovědu a ukončit",
        "Wyświetl tę wiadomość pomocy i zakończ",
    ),
    "Install gzip using your system package manager.": _t(
        "Installieren Sie gzip über Ihren System-Paketmanager.",
        "Installez gzip via le gestionnaire de paquets de votre système.",
        "Instala gzip usando el gestor de paquetes de tu sistema.",
        "Nainstaluj gzip pomocí správce balíčků tvého systému.",
        "Zainstaluj gzip za pomocą menedżera pakietów systemu.",
    ),
    "Install git using your system package manager.": _t(
        "Installieren Sie git über Ihren System-Paketmanager.",
        "Installez git via le gestionnaire de paquets de votre système.",
        "Instala git usando el gestor de paquetes de tu sistema.",
        "Nainstaluj git pomocí správce balíčků tvého systému.",
        "Zainstaluj git za pomocą menedżera pakietów systemu.",
    ),
    "Install the tool using your system package manager.": _t(
        "Installieren Sie das Werkzeug über Ihren System-Paketmanager.",
        "Installez l'outil via le gestionnaire de paquets de votre système.",
        "Instala la herramienta usando el gestor de paquetes de tu sistema.",
        "Nainstaluj nástroj pomocí správce balíčků tvého systému.",
        "Zainstaluj narzędzie za pomocą menedżera pakietów systemu.",
    ),
    "# Run this script after git clone to activate encryption.": _t(
        "# Führen Sie dieses Skript nach git clone aus, um die Verschlüsselung zu aktivieren.",
        "# Exécutez ce script après git clone pour activer le chiffrement.",
        "# Ejecuta este script después de git clone para activar el cifrado.",
        "# Spusť tento skript po git clone pro aktivaci šifrování.",
        "# Uruchom ten skrypt po git clone, aby aktywować szyfrowanie.",
    ),
    "# Requires: age, gzip. See .veil/README_VEIL.md.": _t(
        "# Erfordert: age, gzip. Siehe .veil/README_VEIL.md.",
        "# Nécessite : age, gzip. Voir .veil/README_VEIL.md.",
        "# Requiere: age, gzip. Ver .veil/README_VEIL.md.",
        "# Vyžaduje: age, gzip. Viz .veil/README_VEIL.md.",
        "# Wymaga: age, gzip. Zobacz .veil/README_VEIL.md.",
    ),
    "# Usage: bash .veil/setup_veil.sh <path_to_private_key>": _t(
        "# Verwendung: bash .veil/setup_veil.sh <pfad_zum_privaten_schlüssel>",
        "# Utilisation : bash .veil/setup_veil.sh <chemin_vers_cle_privee>",
        "# Uso: bash .veil/setup_veil.sh <ruta_a_clave_privada>",
        "# Použití: bash .veil/setup_veil.sh <cesta_k_privatnimu_klici>",
        "# Użycie: bash .veil/setup_veil.sh <sciezka_do_klucza_prywatnego>",
    ),
    "veilgit filters activated.": _t(
        "veilgit-Filter aktiviert.",
        "Filtres veilgit activés.",
        "Filtros veilgit activados.",
        "veilgit filtry aktivovány.",
        "Filtry veilgit aktywowane.",
    ),
    "usage: ": _t("Verwendung: ", "Utilisation : ", "Uso: ", "použití: ", "użycie: "),
    "positional arguments": _t(
        "positionale Argumente",
        "arguments positionnels",
        "argumentos posicionales",
        "poziční argumenty",
        "argumenty pozycyjne",
    ),
    "options": _t("Optionen", "options", "opciones", "volby", "opcje"),
    # --- history-plaintext warning ---
    "⚠  WARNING: Files matching your patterns are already in git history (plain text):": _t(
        "⚠  WARNUNG: Dateien, die Ihren Mustern entsprechen, sind bereits"
        " als Klartext in der Git-Historie:",
        "⚠  AVERTISSEMENT : Des fichiers correspondant à vos motifs sont déjà"
        " dans l'historique git (texte clair) :",
        "⚠  ADVERTENCIA: Archivos que coinciden con tus patrones ya están"
        " en el historial de git (texto plano):",
        "⚠  VAROVÁNÍ: Soubory odpovídající vašim vzorům jsou již v historii gitu jako prostý text:",
        "⚠  OSTRZEŻENIE: Pliki pasujące do wzorców są już w historii git jako tekst jawny:",
    ),
    "  {file}  ({count} commit(s))": _t(
        "  {file}  ({count} Commit(s))",
        "  {file}  ({count} commit(s))",
        "  {file}  ({count} commit(s))",
        "  {file}  ({count} commit(s))",
        "  {file}  ({count} commit(s))",
    ),
    "Encrypting these files now protects future commits, but the existing history will remain readable.": _t(  # noqa: E501
        "Das Verschlüsseln dieser Dateien schützt zukünftige Commits,"
        " aber die bestehende Historie bleibt lesbar.",
        "Le chiffrement de ces fichiers protège les futurs commits,"
        " mais l'historique existant restera lisible.",
        "Cifrar estos archivos protege los commits futuros,"
        " pero el historial existente seguirá siendo legible.",
        "Šifrování těchto souborů chrání budoucí commity, ale stávající historie zůstane čitelná.",
        "Szyfrowanie tych plików chroni przyszłe commity,"
        " ale istniejąca historia pozostanie czytelna.",
    ),
    "  [c] Continue — encrypt from this point forward (history stays as-is)": _t(
        "  [c] Fortfahren — ab jetzt verschlüsseln (Historie bleibt unverändert)",
        "  [c] Continuer — chiffrer à partir de maintenant (l'historique reste inchangé)",
        "  [c] Continuar — cifrar desde este punto (el historial no cambia)",
        "  [c] Pokračovat — šifrovat od teď dál (historie zůstane beze změny)",
        "  [c] Kontynuuj — szyfruj od tego momentu (historia bez zmian)",
    ),
    "  [g] Guide — write step-by-step guide to .veil/RETROACTIVE_ENCRYPTION.md and exit": _t(
        "  [g] Anleitung — Schritt-für-Schritt-Anleitung nach"
        " .veil/RETROACTIVE_ENCRYPTION.md schreiben und beenden",
        "  [g] Guide — écrire le guide étape par étape dans"
        " .veil/RETROACTIVE_ENCRYPTION.md et quitter",
        "  [g] Guía — escribir guía paso a paso en .veil/RETROACTIVE_ENCRYPTION.md y salir",
        "  [g] Průvodce — zapsat průvodce do .veil/RETROACTIVE_ENCRYPTION.md a skončit",
        "  [g] Przewodnik — zapisz przewodnik do .veil/RETROACTIVE_ENCRYPTION.md i wyjdź",
    ),
    "  [q] Quit — abort setup without writing anything": _t(
        "  [q] Beenden — Setup abbrechen, ohne etwas zu schreiben",
        "  [q] Quitter — abandonner la configuration sans rien écrire",
        "  [q] Salir — cancelar la configuración sin escribir nada",
        "  [q] Ukončit — přerušit nastavení bez zápisu čehokoli",
        "  [q] Zakończ — przerwij konfigurację bez zapisywania",
    ),
    "Your choice (c/g/q): ": _t(
        "Ihre Wahl (c/g/q): ",
        "Votre choix (c/g/q) : ",
        "Tu elección (c/g/q): ",
        "Vaše volba (c/g/q): ",
        "Twój wybór (c/g/q): ",
    ),
    "Guide written: {path}": _t(
        "Anleitung geschrieben: {path}",
        "Guide écrit : {path}",
        "Guía escrita: {path}",
        "Průvodce zapsán: {path}",
        "Przewodnik zapisany: {path}",
    ),
    "No changes were made to your repository.": _t(
        "Es wurden keine Änderungen an Ihrem Repository vorgenommen.",
        "Aucune modification n'a été apportée à votre dépôt.",
        "No se realizaron cambios en tu repositorio.",
        "V repozitáři nebyly provedeny žádné změny.",
        "Nie wprowadzono żadnych zmian do repozytorium.",
    ),
    "Invalid choice. Enter c, g, or q.": _t(
        "Ungültige Wahl. Geben Sie c, g oder q ein.",
        "Choix invalide. Entrez c, g ou q.",
        "Opción no válida. Introduce c, g o q.",
        "Neplatná volba. Zadejte c, g nebo q.",
        "Nieprawidłowy wybór. Wpisz c, g lub q.",
    ),
}

README_VEIL_CONTENT = """# veilgit — transparent encryption in git repository

## What is veilgit

veilgit installs git `clean`/`smudge` filters into the repository, which
compress and encrypt selected files (`age` + `gzip`) during `git add`.
They remain readable locally, but are stored encrypted on the remote.

## Setup after git clone

1. Install `age` and `gzip`.
2. Obtain the private age key (outside the repository).
3. Run the initialization script from the repository root:
   - Linux/macOS: `bash .veil/setup_veil.sh <path_to_private_key>`
   - Windows: `python .veil/setup_veil.py <path_to_private_key>`
4. Verify filters: `git config --get-regexp '^filter\\.veil\\.'`

## Adding a new collaborator

1. Add their public age key (`age1...`) to `.veil/config.toml` and git filters.
2. Share `.veil/setup_veil.sh` or `.veil/setup_veil.py` — never the private key.
3. The collaborator generates their own key and adds themselves as a recipient.

## Key backup

Keep the private key in a safe place (password-protected disk, password manager).
Encrypted data cannot be recovered without the key.

## Security

- Never commit the private key to git.
- The public key (recipient) is safe to share.
- GitHub commit history may retain encrypted blobs permanently.

## Project link

https://github.com/FiloSottile/age — encryption tool
veilgit project: see README in the `veil_setup.py` tool repository
"""

TRANSLATIONS[README_VEIL_CONTENT] = _t(
    """# veilgit — transparente Verschlüsselung im Git-Repository

## Was ist veilgit

veilgit installiert git `clean`/`smudge`-Filter in das Repository, die
ausgewählte Dateien (`age` + `gzip`) während `git add` komprimieren und verschlüsseln.
Sie bleiben lokal lesbar, werden aber verschlüsselt auf dem Remote-Server gespeichert.

## Einrichtung nach git clone

1. Installiere `age` und `gzip`.
2. Besorge dir den privaten age-Schlüssel (außerhalb des Repositories).
3. Führe das Initialisierungsskript aus dem Repository-Root aus:
   - Linux/macOS: `bash .veil/setup_veil.sh <pfad_zum_privaten_schlüssel>`
   - Windows: `python .veil/setup_veil.py <pfad_zum_privaten_schlüssel>`
4. Überprüfe die Filter: `git config --get-regexp '^filter\\.veil\\.'`

## Hinzufügen eines neuen Mitarbeiters

1. Füge seinen öffentlichen age-Schlüssel (`age1...`) zu `.veil/config.toml`
   und den Git-Filtern hinzu.
2. Teile `.veil/setup_veil.sh` oder `.veil/setup_veil.py` — niemals den privaten Schlüssel.
3. Der Mitarbeiter generiert seinen eigenen Schlüssel und fügt sich als Empfänger hinzu.

## Schlüssel-Backup

Bewahre den privaten Schlüssel an einem sicheren Ort auf (passwortgeschütztes Laufwerk,
Passwort-Manager).
Ohne den Schlüssel können verschlüsselte Daten nicht wiederhergestellt werden.

## Sicherheit

- Committe niemals den privaten Schlüssel in git.
- Der öffentliche Schlüssel (Empfänger) kann sicher geteilt werden.
- Die GitHub-Commit-Historie kann verschlüsselte Blobs dauerhaft behalten.

## Projekt-Link

https://github.com/FiloSottile/age — Verschlüsselungstool
veilgit-Projekt: siehe README im `veil_setup.py` Tool-Repository
""",
    """# veilgit — chiffrement transparent dans le dépôt git

## Qu'est-ce que veilgit

veilgit installe des filtres git `clean`/`smudge` dans le dépôt, qui
compressent et chiffrent les fichiers sélectionnés (`age` + `gzip`) lors de `git add`.
Ils restent lisibles localement, mais sont stockés chiffrés sur le serveur distant.

## Configuration après git clone

1. Installez `age` et `gzip`.
2. Obtenez la clé privée age (en dehors du dépôt).
3. Exécutez le script d'initialisation depuis la racine du dépôt :
   - Linux/macOS : `bash .veil/setup_veil.sh <chemin_vers_cle_privee>`
   - Windows : `python .veil/setup_veil.py <chemin_vers_cle_privee>`
4. Vérifiez les filtres : `git config --get-regexp '^filter\\.veil\\.'`

## Ajouter un nouveau collaborateur

1. Ajoutez sa clé publique age (`age1...`) à `.veil/config.toml` et aux filtres git.
2. Partagez `.veil/setup_veil.sh` ou `.veil/setup_veil.py` — jamais la clé privée.
3. Le collaborateur génère sa propre clé et s'ajoute comme destinataire.

## Sauvegarde de la clé

Conservez la clé privée en lieu sûr (disque protégé par mot de passe,
gestionnaire de mots de passe).
Les données chiffrées ne peuvent pas être récupérées sans la clé.

## Sécurité

- Ne committez jamais la clé privée dans git.
- La clé publique (destinataire) peut être partagée en toute sécurité.
- L'historique des commits GitHub peut conserver les blobs chiffrés de façon permanente.

## Lien du projet

https://github.com/FiloSottile/age — outil de chiffrement
Projet veilgit : voir README dans le dépôt de l'outil `veil_setup.py`
""",
    """# veilgit — cifrado transparente en el repositorio git

## Qué es veilgit

veilgit instala filtros git `clean`/`smudge` en el repositorio, que
comprimen y cifran los archivos seleccionados (`age` + `gzip`) durante `git add`.
Siguen siendo legibles localmente, pero se almacenan cifrados en el remoto.

## Configuración después de git clone

1. Instala `age` y `gzip`.
2. Obtén la clave privada age (fuera del repositorio).
3. Ejecuta el script de inicialización desde la raíz del repositorio:
   - Linux/macOS: `bash .veil/setup_veil.sh <ruta_a_clave_privada>`
   - Windows: `python .veil/setup_veil.py <ruta_a_clave_privada>`
4. Verifica los filtros: `git config --get-regexp '^filter\\.veil\\.'`

## Añadir un nuevo colaborador

1. Añade su clave pública age (`age1...`) a `.veil/config.toml` y a los filtros git.
2. Comparte `.veil/setup_veil.sh` o `.veil/setup_veil.py` — nunca la clave privada.
3. El colaborador genera su propia clave y se añade como destinatario.

## Copia de seguridad de la clave

Guarda la clave privada en un lugar seguro (disco protegido con contraseña, gestor de contraseñas).
Los datos cifrados no se pueden recuperar sin la clave.

## Seguridad

- Nunca hagas commit de la clave privada en git.
- La clave pública (destinatario) es segura para compartir.
- El historial de commits de GitHub puede retener blobs cifrados permanentemente.

## Enlace del proyecto

https://github.com/FiloSottile/age — herramienta de cifrado
Proyecto veilgit: ver README en el repositorio de la herramienta `veil_setup.py`
""",
    """# veilgit — transparentní šifrování v git repozitáři

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
4. Ověř filtry: `git config --get-regexp '^filter\\.veil\\.'`

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
""",
    """# veilgit — przezroczyste szyfrowanie w repozytorium git

## Czym jest veilgit

veilgit instaluje filtry git `clean`/`smudge` w repozytorium, które
kompresują i szyfrują wybrane pliki (`age` + `gzip`) podczas `git add`.
Pozostają one czytelne lokalnie, ale są przechowywane w postaci zaszyfrowanej na zdalnym serwerze.

## Konfiguracja po git clone

1. Zainstaluj `age` i `gzip`.
2. Uzyskaj prywatny klucz age (poza repozytorium).
3. Uruchom skrypt inicjalizacyjny z katalogu głównego repozytorium:
   - Linux/macOS: `bash .veil/setup_veil.sh <sciezka_do_klucza_prywatnego>`
   - Windows: `python .veil/setup_veil.py <sciezka_do_klucza_prywatnego>`
4. Zweryfikuj filtry: `git config --get-regexp '^filter\\.veil\\.'`

## Dodawanie nowego współpracownika

1. Dodaj jego klucz publiczny age (`age1...`) do `.veil/config.toml` i filtrów git.
2. Udostępnij `.veil/setup_veil.sh` lub `.veil/setup_veil.py` — nigdy klucz prywatny.
3. Współpracownik generuje własny klucz i dodaje się jako odbiorca.

## Kopia zapasowa klucza

Przechowuj klucz prywatny w bezpiecznym miejscu (dysk chroniony hasłem, menedżer haseł).
Zaszyfrowanych danych nie można odzyskać bez klucza.

## Bezpieczeństwo

- Nigdy nie dodawaj klucza prywatnego do git.
- Klucz publiczny (odbiorca) można bezpiecznie udostępniać.
- Historia commitów GitHub może zachować zaszyfrowane bloby na stałe.

## Link do projektu

https://github.com/FiloSottile/age — narzędzie do szyfrowania
Projekt veilgit: zobacz README w repozytorium narzędzia `veil_setup.py`
""",
)


RETROACTIVE_ENCRYPTION_GUIDE_EN = """\
# Retroactive Encryption: Remove Plain Text from Git History

## Problem

veil_setup.py detected that files matching your chosen patterns already exist in git
history as plain text. Encrypting from this point protects only future commits.
To remove plain text from past history, rewrite the git history with git filter-repo.

WARNING: History rewrite is irreversible. All existing clones must be re-cloned
after you force-push the rewritten history.

## Prerequisites

Install git filter-repo:
  pip install git-filter-repo
  # macOS: brew install git-filter-repo

Verify: git filter-repo --version

## Steps

1. Back up the files OUTSIDE the repository:
   cp -r path/to/sensitive/ /tmp/veilgit_backup/

2. Remove files from the entire git history:
   git filter-repo --path path/to/sensitive/ --invert-paths
   (for multiple paths repeat --path for each)

3. Verify removal (must return no output):
   git log --all --oneline -- path/to/sensitive/

4. Restore files to the working directory:
   cp -r /tmp/veilgit_backup/ path/to/sensitive/

5. Re-initialize veilgit filters (filter-repo resets .git/config):
   python veil_setup.py . --reinit

6. Stage config and encrypted files:
   git add .gitattributes .veil/
   git add path/to/sensitive/       # clean filter encrypts on git add
   git commit -m "chore: retroactively encrypt sensitive files"

7. Force-push the rewritten history:
   git push --force-with-lease origin main
   (--force-with-lease is safer than --force)

8. Notify collaborators — they must re-clone:
   git clone <repo_url> && cd <repo>
   bash .veil/setup_veil.sh /path/to/their_private_key.txt

## Verify Encryption

   git show HEAD:path/to/sensitive/yourfile.md | xxd | head -3
   # first bytes must be the age encryption header, not plain text

## GitHub Cache

GitHub may retain cached objects for a short period. For maximum security before
making the repository public, contact GitHub Support to request a cache purge.

See also: doc/guides/retroactive-encryption/ for the full guide in your language.
"""

TRANSLATIONS[RETROACTIVE_ENCRYPTION_GUIDE_EN] = _t(
    """\
# Retroaktive Verschlüsselung: Klartext aus der Git-Historie entfernen

## Problem

veil_setup.py hat festgestellt, dass Dateien, die Ihren Mustern entsprechen, bereits als
Klartext in der Git-Historie vorhanden sind. Die Verschlüsselung ab jetzt schützt nur
zukünftige Commits. Um Klartext aus der Vergangenheit zu entfernen, muss die Historie mit
git filter-repo neu geschrieben werden.

WARNUNG: Das Neuschreiben der Historie ist unwiderruflich. Alle bestehenden Klone
müssen nach dem Force-Push neu geklont werden.

## Voraussetzungen

git filter-repo installieren:
  pip install git-filter-repo
  # macOS: brew install git-filter-repo

Überprüfung: git filter-repo --version

## Schritte

1. Dateien AUSSERHALB des Repositories sichern:
   cp -r pfad/zu/sensiblen/ /tmp/veilgit_backup/

2. Dateien aus der gesamten Git-Historie entfernen:
   git filter-repo --path pfad/zu/sensiblen/ --invert-paths
   (für mehrere Pfade --path wiederholen)

3. Entfernung prüfen (darf keine Ausgabe liefern):
   git log --all --oneline -- pfad/zu/sensiblen/

4. Dateien ins Arbeitsverzeichnis zurückspielen:
   cp -r /tmp/veilgit_backup/ pfad/zu/sensiblen/

5. veilgit-Filter neu initialisieren (filter-repo setzt .git/config zurück):
   python veil_setup.py . --reinit

6. Konfiguration und verschlüsselte Dateien stagen:
   git add .gitattributes .veil/
   git add pfad/zu/sensiblen/       # Clean-Filter verschlüsselt bei git add
   git commit -m "chore: sensible Dateien retroaktiv verschlüsseln"

7. Neu geschriebene Historie force-pushen:
   git push --force-with-lease origin main

8. Mitarbeiter benachrichtigen — sie müssen neu klonen:
   git clone <repo_url> && cd <repo>
   bash .veil/setup_veil.sh /pfad/zum/privaten_schluessel.txt

## Verschlüsselung prüfen

   git show HEAD:pfad/zu/sensiblen/datei.md | xxd | head -3
   # erste Bytes müssen den age-Header zeigen, kein Klartext

## GitHub-Cache

GitHub kann Objekte kurzzeitig im Cache halten. Kontaktieren Sie den GitHub-Support
für eine Cache-Bereinigung vor der Veröffentlichung des Repositories.

Siehe auch: doc/guides/retroactive-encryption/ für die vollständige Anleitung.
""",
    """\
# Chiffrement rétroactif : supprimer le texte clair de l'historique git

## Problème

veil_setup.py a détecté que des fichiers correspondant à vos motifs existent déjà dans
l'historique git en texte clair. Le chiffrement à partir de maintenant ne protège que les
futurs commits. Pour supprimer le texte clair du passé, réécrivez l'historique avec
git filter-repo.

AVERTISSEMENT : La réécriture est irréversible. Tous les clones existants doivent
être re-clonés après le force-push.

## Prérequis

Installer git filter-repo :
  pip install git-filter-repo
  # macOS : brew install git-filter-repo

Vérification : git filter-repo --version

## Étapes

1. Sauvegarder les fichiers EN DEHORS du dépôt :
   cp -r chemin/vers/sensibles/ /tmp/veilgit_backup/

2. Supprimer les fichiers de tout l'historique :
   git filter-repo --path chemin/vers/sensibles/ --invert-paths
   (répéter --path pour plusieurs chemins)

3. Vérifier la suppression (ne doit rien afficher) :
   git log --all --oneline -- chemin/vers/sensibles/

4. Restaurer les fichiers dans le répertoire de travail :
   cp -r /tmp/veilgit_backup/ chemin/vers/sensibles/

5. Réinitialiser les filtres veilgit (filter-repo réinitialise .git/config) :
   python veil_setup.py . --reinit

6. Indexer la configuration et les fichiers chiffrés :
   git add .gitattributes .veil/
   git add chemin/vers/sensibles/   # le filtre clean chiffre lors du git add
   git commit -m "chore: chiffrer rétroactivement les fichiers sensibles"

7. Force-pusher l'historique réécrit :
   git push --force-with-lease origin main

8. Informer les collaborateurs — ils doivent re-cloner :
   git clone <url_depot> && cd <repo>
   bash .veil/setup_veil.sh /chemin/vers/cle_privee.txt

## Vérifier le chiffrement

   git show HEAD:chemin/vers/sensibles/fichier.md | xxd | head -3
   # les premiers octets doivent montrer l'en-tête age, pas du texte clair

## Cache GitHub

GitHub peut conserver des objets en cache pendant un certain temps. Contactez le support
GitHub pour une purge avant de rendre le dépôt public.

Voir aussi : doc/guides/retroactive-encryption/ pour le guide complet.
""",
    """\
# Cifrado retroactivo: eliminar texto plano del historial de git

## Problema

veil_setup.py detectó que archivos que coinciden con tus patrones ya existen en el
historial de git como texto plano. Cifrar a partir de ahora solo protege los commits
futuros. Para eliminar el texto plano del pasado, reescribe el historial con git filter-repo.

ADVERTENCIA: La reescritura es irreversible. Todos los clones existentes deben
volver a clonarse después del force-push.

## Requisitos previos

Instalar git filter-repo:
  pip install git-filter-repo
  # macOS: brew install git-filter-repo

Verificación: git filter-repo --version

## Pasos

1. Hacer copia de seguridad de los archivos FUERA del repositorio:
   cp -r ruta/a/sensibles/ /tmp/veilgit_backup/

2. Eliminar archivos de todo el historial:
   git filter-repo --path ruta/a/sensibles/ --invert-paths
   (repetir --path para varias rutas)

3. Verificar la eliminación (no debe mostrar nada):
   git log --all --oneline -- ruta/a/sensibles/

4. Restaurar los archivos al directorio de trabajo:
   cp -r /tmp/veilgit_backup/ ruta/a/sensibles/

5. Reinicializar los filtros veilgit (filter-repo reinicia .git/config):
   python veil_setup.py . --reinit

6. Añadir al índice la configuración y los archivos cifrados:
   git add .gitattributes .veil/
   git add ruta/a/sensibles/        # el filtro clean cifra durante git add
   git commit -m "chore: cifrar retroactivamente archivos sensibles"

7. Force-push del historial reescrito:
   git push --force-with-lease origin main

8. Notificar a los colaboradores — deben volver a clonar:
   git clone <url_repo> && cd <repo>
   bash .veil/setup_veil.sh /ruta/a/clave_privada.txt

## Verificar el cifrado

   git show HEAD:ruta/a/sensibles/archivo.md | xxd | head -3
   # los primeros bytes deben mostrar la cabecera age, no texto plano

## Caché de GitHub

GitHub puede retener objetos en caché temporalmente. Contacta con el soporte de GitHub
para solicitar una purga antes de hacer público el repositorio.

Ver también: doc/guides/retroactive-encryption/ para la guía completa.
""",
    """\
# Retroaktivní šifrování: Odstranění prostého textu z historie gitu

## Problém

veil_setup.py zjistil, že soubory odpovídající vybraným vzorům již existují v historii
gitu jako prostý text. Šifrování od teď chrání pouze budoucí commity. Chcete-li odstranit
prostý text z minulosti, musíte přepsat historii gitu pomocí git filter-repo.

VAROVÁNÍ: Přepis historie je nevratný. Všechny existující klony musí být po
force-push znovu naklonovány.

## Předpoklady

Nainstalujte git filter-repo:
  pip install git-filter-repo
  # macOS: brew install git-filter-repo

Ověření: git filter-repo --version

## Postup

1. Zálohujte soubory MIMO repozitář:
   cp -r cesta/k/citlivym/ /tmp/veilgit_zaloha/

2. Odstraňte soubory z celé historie gitu:
   git filter-repo --path cesta/k/citlivym/ --invert-paths
   (pro více cest opakujte --path)

3. Ověřte odstranění (nesmí vrátit žádný výstup):
   git log --all --oneline -- cesta/k/citlivym/

4. Obnovte soubory do pracovního adresáře:
   cp -r /tmp/veilgit_zaloha/ cesta/k/citlivym/

5. Znovu inicializujte veilgit filtry (filter-repo resetuje .git/config):
   python veil_setup.py . --reinit

6. Přidejte konfiguraci a šifrované soubory do indexu:
   git add .gitattributes .veil/
   git add cesta/k/citlivym/        # clean filtr šifruje při git add
   git commit -m "chore: retroaktivně zašifrovat citlivé soubory"

7. Force-push přepsané historie:
   git push --force-with-lease origin main

8. Upozorněte spolupracovníky — musí znovu naklonovat:
   git clone <url_repozitare> && cd <repo>
   bash .veil/setup_veil.sh /cesta/k/soukromemu_klici.txt

## Ověření šifrování

   git show HEAD:cesta/k/citlivym/soubor.md | xxd | head -3
   # první bajty musí být hlavička age šifrování, ne prostý text

## Cache GitHubu

GitHub může objekty dočasně uchovávat v cache. Kontaktujte GitHub Support a požádejte
o vyčištění cache před zveřejněním repozitáře.

Viz také: doc/guides/retroactive-encryption/ pro úplného průvodce.
""",
    """\
# Retroaktywne szyfrowanie: usunięcie tekstu jawnego z historii git

## Problem

veil_setup.py wykrył, że pliki pasujące do wzorców istnieją już w historii git jako tekst
jawny. Szyfrowanie od tego momentu chroni tylko przyszłe commity. Aby usunąć tekst jawny
z przeszłości, przepisz historię git za pomocą git filter-repo.

OSTRZEŻENIE: Przepisanie historii jest nieodwracalne. Wszystkie istniejące klony muszą
zostać sklonowane ponownie po force-push.

## Wymagania wstępne

Zainstaluj git filter-repo:
  pip install git-filter-repo
  # macOS: brew install git-filter-repo

Weryfikacja: git filter-repo --version

## Kroki

1. Utwórz kopię zapasową plików POZA repozytorium:
   cp -r sciezka/do/wrazliwych/ /tmp/veilgit_backup/

2. Usuń pliki z całej historii git:
   git filter-repo --path sciezka/do/wrazliwych/ --invert-paths
   (powtórz --path dla wielu ścieżek)

3. Zweryfikuj usunięcie (nie powinno zwracać żadnego wyniku):
   git log --all --oneline -- sciezka/do/wrazliwych/

4. Przywróć pliki do katalogu roboczego:
   cp -r /tmp/veilgit_backup/ sciezka/do/wrazliwych/

5. Ponownie zainicjuj filtry veilgit (filter-repo resetuje .git/config):
   python veil_setup.py . --reinit

6. Dodaj konfigurację i zaszyfrowane pliki do indeksu:
   git add .gitattributes .veil/
   git add sciezka/do/wrazliwych/   # filtr clean szyfruje podczas git add
   git commit -m "chore: retroaktywnie zaszyfruj wrażliwe pliki"

7. Force-push przepisanej historii:
   git push --force-with-lease origin main

8. Powiadom współpracowników — muszą ponownie sklonować:
   git clone <url_repo> && cd <repo>
   bash .veil/setup_veil.sh /sciezka/do/klucza_prywatnego.txt

## Weryfikacja szyfrowania

   git show HEAD:sciezka/do/wrazliwych/plik.md | xxd | head -3
   # pierwsze bajty muszą pokazywać nagłówek szyfrowania age, nie tekst jawny

## Pamięć podręczna GitHub

GitHub może przez krótki czas przechowywać obiekty w pamięci podręcznej. Skontaktuj się
z pomocą techniczną GitHub w celu wyczyszczenia pamięci przed upublicznieniem repozytorium.

Zobacz też: doc/guides/retroactive-encryption/ — pełny przewodnik.
""",
)


def _(key: str) -> str:
    """Return the translated string for the current language; English key is the fallback."""
    lang = get_current_language()
    if lang == "en":
        return key
    if lang not in SUPPORTED_LANGUAGES:
        return key
    return TRANSLATIONS.get(key, {}).get(lang, key)


@dataclasses.dataclass
class DryRunContext:
    """Records or executes filesystem and subprocess actions depending on dry-run mode."""

    enabled: bool
    actions: List[str] = dataclasses.field(default_factory=list)

    def write_file(self, path: Union[str, Path], content: str) -> None:
        """Write a text file, or record the planned write in dry-run mode."""
        path_str = str(path)
        if self.enabled:
            message = _("[DRY-RUN] Would write: {path}").format(path=path_str)
            self.actions.append(message)
            print(message)
            return
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def run_command(self, cmd: List[str]) -> None:
        """Run a subprocess command, or record the planned command in dry-run mode."""
        cmd_str = " ".join(cmd)
        if self.enabled:
            message = _("[DRY-RUN] Would run: {cmd}").format(cmd=cmd_str)
            self.actions.append(message)
            print(message)
            return
        subprocess.run(cmd, check=True)

    def mkdir(self, path: Union[str, Path]) -> None:
        """Create a directory, or record the planned mkdir in dry-run mode."""
        path_str = str(path)
        if self.enabled:
            message = _("[DRY-RUN] Would create directory: {path}").format(path=path_str)
            self.actions.append(message)
            print(message)
            return
        Path(path).mkdir(parents=True, exist_ok=True)

    def recorded_actions(self) -> List[str]:
        """Return a copy of all recorded dry-run actions."""
        return list(self.actions)


def get_age_install_instruction() -> str:
    """Return a platform-specific instruction for installing the age tool."""
    if sys.platform == "darwin":
        return "brew install age"
    if os.path.exists("/etc/debian_version"):
        return "sudo apt install age"
    if os.path.exists("/etc/redhat-release"):
        return "sudo dnf install age"
    if os.path.exists("/etc/arch-release"):
        return "sudo pacman -S age"
    return "https://github.com/FiloSottile/age/releases"


def get_tool_install_instruction(tool: str) -> str:
    """Return an installation hint for a missing external tool."""
    if tool in ("age", "age-keygen"):
        return get_age_install_instruction()
    if tool == "gzip":
        return _("Install gzip using your system package manager.")
    if tool == "git":
        return _("Install git using your system package manager.")
    return _("Install the tool using your system package manager.")


def check_dependencies(_dry_run_ctx: Optional[DryRunContext] = None) -> None:
    """Check age, age-keygen, gzip, and git; exit with install instructions if missing."""
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if not missing:
        return
    for tool in missing:
        print(_("Missing required tool: ") + tool, file=sys.stderr)
        print(_("Install: ") + get_tool_install_instruction(tool), file=sys.stderr)
    raise SystemExit(1)


class LocalizedHelpFormatter(argparse.HelpFormatter):
    """Help formatter with section titles and usage prefix translated via _()."""

    def _format_usage(
        self,
        usage: Optional[str],
        actions: Any,
        groups: Any,
        prefix: Optional[str],
    ) -> str:
        if prefix is None:
            prefix = _("usage: ")
        return super()._format_usage(usage, actions, groups, prefix)

    def start_section(self, heading: Optional[str]) -> None:
        if heading is None:
            super().start_section(heading)
            return
        localized_headings = {
            "positional arguments": _("positional arguments"),
            "optional arguments": _("options"),
            "options": _("options"),
        }
        super().start_section(localized_headings.get(heading, heading))


class LocalizedArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that uses LocalizedHelpFormatter by default."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", LocalizedHelpFormatter)
        super().__init__(*args, **kwargs)


def peek_cli_language(argv: List[str]) -> Optional[str]:
    """Extract -l/--lang from argv before full argparse parsing."""
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in ("-l", "--lang"):
            if index + 1 < len(argv):
                candidate = argv[index + 1]
                if candidate in SUPPORTED_LANGUAGES:
                    return candidate
            return None
        if token.startswith("--lang="):
            candidate = token.split("=", 1)[1]
            if candidate in SUPPORTED_LANGUAGES:
                return candidate
        index += 1
    return None


def prepare_cli_language(argv: List[str]) -> None:
    """Set active language from CLI flags before argparse builds localized help."""
    set_current_language(resolve_language(peek_cli_language(argv), None))


def build_parser() -> LocalizedArgumentParser:
    """Build argparse parser with localized help strings."""
    parser = LocalizedArgumentParser(
        prog="veil_setup.py",
        description=_(CLI_DESCRIPTION),
        add_help=False,
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help=_("Show this help message and exit"),
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        help=_("Path to the target git repository"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=_("Simulate the full setup flow without writing files or running commands"),
    )
    parser.add_argument(
        "--add-pattern",
        metavar="PATTERN",
        help=_("Add a glob pattern to an existing configuration"),
    )
    parser.add_argument(
        "--remove-pattern",
        metavar="PATTERN",
        help=_("Remove a glob pattern from an existing configuration"),
    )
    parser.add_argument(
        "--reinit",
        action="store_true",
        help=_("Re-write git config filters from existing .veil/config.toml"),
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help=_("Print the current .veil/config.toml contents"),
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help=_("Print veil_setup.py version and exit"),
    )
    parser.add_argument(
        "-l",
        "--lang",
        choices=list(SUPPORTED_LANGUAGES),
        help=_("Communication language (en, de, fr, sp, cs, pl)"),
    )
    return parser


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for veil_setup.py."""
    argv_list = list(sys.argv[1:] if argv is None else argv)
    prepare_cli_language(argv_list)
    return build_parser().parse_args(argv_list)


@dataclasses.dataclass
class VeilConfig:
    """In-memory representation of .veil/config.toml."""

    version: str = "1"
    key_path: str = ""
    recipient_primary: str = ""
    recipient_others: List[str] = dataclasses.field(default_factory=list)
    patterns: List[str] = dataclasses.field(default_factory=list)
    exclude_patterns: List[str] = dataclasses.field(default_factory=list)
    language: Optional[str] = None


class TomlWriter:
    """Minimal TOML serializer for the fixed VeilConfig structure."""

    @staticmethod
    def _escape_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _format_string_list(values: List[str]) -> str:
        items = ", ".join(TomlWriter._escape_string(item) for item in values)
        return f"[{items}]"

    @classmethod
    def serialize(cls, config: VeilConfig) -> str:
        """Serialize VeilConfig to a TOML document string."""
        veil_lines = [
            "[veil]",
            f"version = {cls._escape_string(config.version)}",
            f"key_path = {cls._escape_string(config.key_path)}",
        ]
        if config.language:
            veil_lines.append(f"language = {cls._escape_string(config.language)}")
        else:
            veil_lines.append(LANGUAGE_TOML_COMMENT)
        lines = [
            *veil_lines,
            "",
            "[veil.recipients]",
            f"primary = {cls._escape_string(config.recipient_primary)}",
            f"others = {cls._format_string_list(config.recipient_others)}",
            "",
            "[veil.patterns]",
            f"patterns = {cls._format_string_list(config.patterns)}",
            "",
            "[veil.exclude]",
            f"patterns = {cls._format_string_list(config.exclude_patterns)}",
            "",
        ]
        return "\n".join(lines)


def _require_tomllib() -> Any:
    if tomllib is None:
        raise RuntimeError(
            "TOML parsing requires Python 3.11+ (tomllib) or the tomli package on older versions."
        )
    return tomllib


def _parse_veil_config(data: Dict[str, Any]) -> VeilConfig:
    if "veil" not in data:
        raise ValueError("Missing required [veil] section in config.toml")
    veil = data["veil"]
    recipients = veil.get("recipients", {})
    patterns_section = veil.get("patterns", {})
    exclude_section = veil.get("exclude", {})
    language_value = veil.get("language")
    language = str(language_value) if language_value else None
    return VeilConfig(
        version=str(veil.get("version", "1")),
        key_path=str(veil.get("key_path", "")),
        recipient_primary=str(recipients.get("primary", "")),
        recipient_others=list(recipients.get("others", [])),
        patterns=list(patterns_section.get("patterns", [])),
        exclude_patterns=list(exclude_section.get("patterns", [])),
        language=language,
    )


def read_config(path: Path) -> Optional[VeilConfig]:
    """Read VeilConfig from path; return None when the file does not exist."""
    if not path.is_file():
        return None
    parser = _require_tomllib()
    with path.open("rb") as handle:
        data = parser.load(handle)
    return _parse_veil_config(data)


def write_config(config: VeilConfig, veil_dir: Path, ctx: DryRunContext) -> None:
    """Write VeilConfig to veil_dir/config.toml through DryRunContext."""
    ctx.mkdir(str(veil_dir))
    content = TomlWriter.serialize(config)
    ctx.write_file(veil_dir / "config.toml", content)


def detect_existing_config(repo_path: Path) -> bool:
    """Return True when .veil/config.toml exists in the target repository."""
    return (repo_path / ".veil" / "config.toml").is_file()


def show_config(repo_path: Path) -> None:
    """Print the current configuration or a not-configured message."""
    config_path = repo_path / ".veil" / "config.toml"
    config = read_config(config_path)
    if config is None:
        print(_("Not configured"))
        return
    print(f"version: {config.version}")
    print(f"key_path: {config.key_path}")
    print(f"recipient_primary: {config.recipient_primary}")
    print(f"recipient_others: {', '.join(config.recipient_others) or _('(none)')}")
    print(f"patterns: {', '.join(config.patterns) or _('(none)')}")
    print(f"exclude_patterns: {', '.join(config.exclude_patterns) or _('(none)')}")


def _path_matches_pattern(relative_path: Path, pattern: str) -> bool:
    rel_posix = relative_path.as_posix()
    if "**" in pattern:
        return relative_path.match(pattern) or fnmatch.fnmatch(rel_posix, pattern)
    return fnmatch.fnmatch(rel_posix, pattern) or fnmatch.fnmatch(relative_path.name, pattern)


def glob_preview(pattern: str, repo_path: Path) -> List[str]:
    """Return sorted relative paths of files matching a gitattributes-style glob."""
    matches: List[str] = []
    if not repo_path.is_dir():
        return matches
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_path)
        if _path_matches_pattern(relative, pattern):
            matches.append(relative.as_posix())
    return sorted(matches)


def select_patterns_interactive(repo_path: Path) -> List[str]:
    """Interactively collect confirmed glob patterns from the user."""
    print(_(GLOB_PATTERN_PROMPT))
    confirmed: List[str] = []
    while True:
        pattern = input(_("Pattern: ")).strip()
        if not pattern:
            break
        matches = glob_preview(pattern, repo_path)
        if matches:
            print(_("Matching files:"))
            for match in matches:
                print(f"  - {match}")
        else:
            print(_("Warning: pattern matches no existing files."))
        while True:
            choice = (
                input(_("Is the selection correct? (a=add / n=retry / s=skip): ")).strip().lower()
            )
            if choice == "a":
                confirmed.append(pattern)
                break
            if choice == "n":
                break
            if choice == "s":
                break
            print(_("Invalid choice. Enter a, n, or s."))
        if choice == "n":
            continue
    print(_("Summary of selected patterns:"))
    if not confirmed:
        print(_("  (none)"))
    else:
        for pattern in confirmed:
            files = glob_preview(pattern, repo_path)
            print(_("  - {pattern} -> {count} file(s)").format(pattern=pattern, count=len(files)))
    return confirmed


def add_pattern(config: VeilConfig, pattern: str) -> bool:
    """Add pattern to config if not already present; return True when added."""
    if pattern in config.patterns:
        return False
    config.patterns.append(pattern)
    return True


def remove_pattern(config: VeilConfig, pattern: str) -> bool:
    """Remove pattern from config if present; return True when removed."""
    if pattern not in config.patterns:
        return False
    config.patterns.remove(pattern)
    return True


def default_key_path(repo_name: str) -> Path:
    """Return the default private key path for the given repository name."""
    filename = f"{repo_name}_key.txt"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "age" / filename
        return Path.home() / "AppData" / "Roaming" / "age" / filename
    return Path.home() / ".config" / "age" / filename


def validate_age_public_key(key: str) -> bool:
    """Validate an age recipient public key format."""
    return AGE_PUBLIC_KEY_RE.fullmatch(key) is not None


def validate_existing_key(key_path: Path) -> bool:
    """Return True when key_path contains a readable age private key file."""
    if not key_path.is_file():
        return False
    try:
        content = key_path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped.startswith("AGE-SECRET-KEY-")
    return False


def _parse_public_key_from_keygen_output(stderr: str, stdout: str = "") -> Optional[str]:
    """Extract the age public key from age-keygen output (supports old and new formats)."""
    for line in (stderr + stdout).splitlines():
        stripped = line.strip()
        if stripped.startswith("# public key:"):
            return stripped.split(":", 1)[1].strip()
        if stripped.startswith("Public key:"):
            return stripped.split(":", 1)[1].strip()
    return None


def generate_key(key_path: Path, ctx: DryRunContext) -> str:
    """Generate a new age key pair and return the public recipient key."""
    ctx.mkdir(str(key_path.parent))
    cmd = ["age-keygen", "-o", str(key_path)]
    if ctx.enabled:
        ctx.run_command(cmd)
        return DRY_RUN_PLACEHOLDER_PUBLIC_KEY
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    public_key = _parse_public_key_from_keygen_output(result.stderr, result.stdout)
    if public_key is None:
        raise RuntimeError("Could not parse public key from age-keygen output")
    return public_key


def print_security_warning() -> None:
    """Print the mandatory security warning block before writing configuration."""
    print(_(SECURITY_WARNING_KEY))


def prompt_key_management(repo_name: str, ctx: DryRunContext) -> Tuple[Path, str]:
    """Interactively obtain a private key path and its public recipient key."""
    default_path = default_key_path(repo_name)
    print(_("Default key path: {path}").format(path=default_path))
    print(_("1) Generate a new key"))
    print(_("2) Use an existing key"))
    while True:
        choice = input(_("Choice [1/2]: ")).strip()
        if choice == "1":
            key_path_input = input(
                _("Path for new key [{default}]: ").format(default=default_path)
            ).strip()
            key_path = Path(key_path_input or str(default_path)).expanduser()
            public_key = generate_key(key_path, ctx)
            print(_("Public key (recipient): {key}").format(key=public_key))
            return key_path, public_key
        if choice == "2":
            key_path_input = input(_("Path to existing key: ")).strip()
            key_path = Path(key_path_input).expanduser()
            if not validate_existing_key(key_path):
                print(_("Invalid key file. Enter a valid age private key path."))
                continue
            public_input = input(_("Public key (recipient) for this key: ")).strip()
            if not validate_age_public_key(public_input):
                print(_("Invalid public key format."))
                continue
            return key_path, public_input
        print(_("Invalid choice. Enter 1 or 2."))


def prompt_additional_recipients() -> List[str]:
    """Collect additional validated age public keys from the user."""
    answer = input(_("Add additional recipients who can decrypt data? (y/N): ")).strip().lower()
    if answer not in ("a", "ano", "y", "yes"):
        return []
    recipients: List[str] = []
    print(_("Enter public age keys (empty input finishes):"))
    while True:
        key = input(_("Recipient: ")).strip()
        if not key:
            break
        if not validate_age_public_key(key):
            print(_("Invalid key format. Expected age1... (61 characters)."))
            continue
        if key in recipients:
            print(_("This key was already added."))
            continue
        recipients.append(key)
    return recipients


GITATTRIBUTES_MANAGED_MARKER = "# veilgit managed — do not edit manually"
VEIL_CONFIG_GLOB = ".veil/config.toml"
GIT_FILTER_SECTION = 'filter "veil"'
GIT_DIFF_SECTION = 'diff "veil"'


def _build_clean_filter_command(config: VeilConfig) -> str:
    """Build the git clean filter command with one -r flag per recipient."""
    recipients = [config.recipient_primary, *config.recipient_others]
    recipient_flags = " ".join(f"-r {key}" for key in recipients if key)
    return f"gzip -9 | age {recipient_flags}".strip()


def _build_smudge_filter_command(config: VeilConfig) -> str:
    """Build the git smudge/textconv filter command using the private key path."""
    return f"age --decrypt -i {config.key_path} | gzip -d"


def _read_gitattributes_state(path: Path) -> Tuple[List[str], Set[str]]:
    """Split .gitattributes into preserved lines and managed veil patterns."""
    preserved: List[str] = []
    managed_patterns: Set[str] = set()
    if not path.is_file():
        return preserved, managed_patterns
    in_managed = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == GITATTRIBUTES_MANAGED_MARKER:
            in_managed = True
            continue
        if in_managed and "filter=veil" in line:
            pattern = line.split(" filter=")[0].strip()
            if pattern:
                managed_patterns.add(pattern)
            continue
        if in_managed and stripped == "":
            in_managed = False
            continue
        if not in_managed:
            preserved.append(line)
    return preserved, managed_patterns


def write_gitattributes(repo_path: Path, patterns: List[str], ctx: DryRunContext) -> None:
    """Add veil filter entries to .gitattributes idempotently."""
    path = repo_path / ".gitattributes"
    preserved, existing_patterns = _read_gitattributes_state(path)
    all_patterns = set(existing_patterns)
    all_patterns.update(patterns)
    all_patterns.add(VEIL_CONFIG_GLOB)

    while preserved and preserved[-1].strip() == "":
        preserved.pop()

    output_lines: List[str] = list(preserved)
    if output_lines:
        output_lines.append("")
    output_lines.append(GITATTRIBUTES_MANAGED_MARKER)
    for pattern in sorted(all_patterns):
        output_lines.append(f"{pattern} filter=veil diff=veil")
    output_lines.append("")
    ctx.write_file(path, "\n".join(output_lines))


def _remove_ini_sections(content: str, section_names: List[str]) -> str:
    """Remove INI sections by name from git config text."""
    if not content:
        return ""
    result: List[str] = []
    skip = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            skip = section in section_names
        if not skip:
            result.append(line)
    return "\n".join(result).rstrip()


def _render_veil_git_config_sections(config: VeilConfig) -> str:
    """Render [filter \"veil\"] and [diff \"veil\"] sections for .git/config."""
    clean = _build_clean_filter_command(config)
    smudge = _build_smudge_filter_command(config)
    return (
        f"[{GIT_FILTER_SECTION}]\n"
        f"\tclean = {clean}\n"
        f"\tsmudge = {smudge}\n"
        f"\trequired = true\n"
        f"[{GIT_DIFF_SECTION}]\n"
        f"\ttextconv = {smudge}\n"
    )


def write_git_config_filters(repo_path: Path, config: VeilConfig, ctx: DryRunContext) -> None:
    """Write or overwrite veil git filter sections in the target repo .git/config."""
    clean = _build_clean_filter_command(config)
    smudge = _build_smudge_filter_command(config)
    if ctx.enabled:
        ctx.run_command(["git", "-C", str(repo_path), "config", "filter.veil.clean", clean])
        ctx.run_command(["git", "-C", str(repo_path), "config", "filter.veil.smudge", smudge])
        ctx.run_command(["git", "-C", str(repo_path), "config", "filter.veil.required", "true"])
        ctx.run_command(["git", "-C", str(repo_path), "config", "diff.veil.textconv", smudge])
        return

    git_config_path = repo_path / ".git" / "config"
    existing = ""
    if git_config_path.is_file():
        existing = git_config_path.read_text(encoding="utf-8")
    merged = _remove_ini_sections(existing, [GIT_FILTER_SECTION, GIT_DIFF_SECTION])
    if merged:
        merged = merged.rstrip() + "\n\n"
    merged += _render_veil_git_config_sections(config)
    ctx.write_file(git_config_path, merged)


def _render_setup_sh_content(config: VeilConfig) -> str:
    """Render the post-clone bash setup script with embedded recipient keys."""
    clean = _build_clean_filter_command(config)
    return f"""#!/usr/bin/env bash
{_("# Run this script after git clone to activate encryption.")}
{_("# Requires: age, gzip. See .veil/README_VEIL.md.")}
{_("# Usage: bash .veil/setup_veil.sh <path_to_private_key>")}
set -euo pipefail
KEY_PATH="${{1:?Usage: bash $0 <path_to_private_key>}}"
REPO_ROOT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
cd "${{REPO_ROOT}}"
git config filter.veil.clean "{clean}"
git config filter.veil.smudge "age --decrypt -i ${{KEY_PATH}} | gzip -d"
git config filter.veil.required true
git config diff.veil.textconv "age --decrypt -i ${{KEY_PATH}} | gzip -d"
echo "{_("veilgit filters activated.")}"
"""


def write_setup_sh(veil_dir: Path, config: VeilConfig, ctx: DryRunContext) -> None:
    """Create .veil/setup_veil.sh on Linux and macOS with executable permissions."""
    if sys.platform == "win32":
        return
    path = veil_dir / "setup_veil.sh"
    ctx.write_file(path, _render_setup_sh_content(config))
    if ctx.enabled:
        message = _("[DRY-RUN] Would set executable bit: {path}").format(path=path)
        ctx.actions.append(message)
        print(message)
        return
    os.chmod(path, 0o755)


def _render_setup_py_content(config: VeilConfig) -> str:
    """Render the cross-platform Python post-clone setup script."""
    clean = _build_clean_filter_command(config)
    return f'''#!/usr/bin/env python3
"""Post-clone setup script for veilgit encryption filters."""
import subprocess
import sys
from pathlib import Path

CLEAN_CMD = "{clean}"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python setup_veil.py <path_to_private_key>")
        raise SystemExit(1)
    key_path = sys.argv[1]
    repo_root = Path(__file__).resolve().parent.parent
    smudge = f"age --decrypt -i {{key_path}} | gzip -d"
    commands = [
        ["git", "-C", str(repo_root), "config", "filter.veil.clean", CLEAN_CMD],
        ["git", "-C", str(repo_root), "config", "filter.veil.smudge", smudge],
        ["git", "-C", str(repo_root), "config", "filter.veil.required", "true"],
        ["git", "-C", str(repo_root), "config", "diff.veil.textconv", smudge],
    ]
    for cmd in commands:
        subprocess.run(cmd, check=True)
    print("{_("veilgit filters activated.")}")


if __name__ == "__main__":
    main()
'''


def write_setup_py(veil_dir: Path, config: VeilConfig, ctx: DryRunContext) -> None:
    """Create .veil/setup_veil.py as a cross-platform post-clone setup helper."""
    ctx.write_file(veil_dir / "setup_veil.py", _render_setup_py_content(config))


def write_readme_veil(veil_dir: Path, ctx: DryRunContext) -> None:
    """Create .veil/README_VEIL.md with usage and security documentation."""
    content = _(README_VEIL_CONTENT)
    ctx.write_file(veil_dir / "README_VEIL.md", content)


def print_final_summary(repo_path: Path, config: VeilConfig) -> None:
    """Print the Step 6 completion summary block."""
    patterns_display = list(config.patterns)
    if VEIL_CONFIG_GLOB not in patterns_display:
        patterns_display.append(VEIL_CONFIG_GLOB)
    patterns_str = ", ".join(patterns_display)
    print(_("Done. veilgit was configured in repository: {repo}").format(repo=repo_path))
    print()
    print(_("Encrypted patterns: {patterns}").format(patterns=patterns_str))
    print(_("Public key (recipient): {key}").format(key=config.recipient_primary))
    print(_("Private key: {path}").format(path=config.key_path))
    print()
    print(_("Next steps:"))
    print(_("  1. Commit .gitattributes: git add .gitattributes .veil/"))
    print(_("  2. Files encrypt automatically on the next 'git add'."))
    print(_("  3. Share .veil/setup_veil.sh with collaborators (not the key!)."))


def check_patterns_in_history(repo_path: Path, patterns: List[str]) -> Dict[str, int]:
    """Return {relative_path: commit_count} for tracked files matching patterns in git history.

    Args:
        repo_path: Root of the target git repository.
        patterns: List of .gitattributes-style glob patterns.

    Returns:
        Mapping from relative file path to the number of commits that touched it.
        Empty dict when no matches or when git is unavailable.
    """
    if not patterns:
        return {}
    try:
        # git ls-files resolves .gitattributes-style globs natively (supports **)
        ls_result = subprocess.run(
            ["git", "-C", str(repo_path), "ls-files"] + list(patterns),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return {}

    matched = [f for f in ls_result.stdout.splitlines() if f.strip()]
    if not matched:
        return {}

    history: Dict[str, int] = {}
    for file_path in matched:
        try:
            log_result = subprocess.run(
                ["git", "-C", str(repo_path), "log", "--oneline", "--follow", "--", file_path],
                capture_output=True,
                text=True,
                check=True,
            )
            count = len([line for line in log_result.stdout.splitlines() if line.strip()])
            if count > 0:
                history[file_path] = count
        except subprocess.CalledProcessError:
            pass

    return history


def _write_retroactive_guide(veil_dir: Path) -> Path:
    """Write the retroactive encryption guide in the current language to .veil/.

    Args:
        veil_dir: Path to the .veil/ directory inside the target repository.

    Returns:
        Path to the written guide file.
    """
    content = _(RETROACTIVE_ENCRYPTION_GUIDE_EN)
    guide_path = veil_dir / "RETROACTIVE_ENCRYPTION.md"
    veil_dir.mkdir(parents=True, exist_ok=True)
    guide_path.write_text(content, encoding="utf-8")
    return guide_path


def warn_history_plaintext(repo_path: Path, patterns: List[str], veil_dir: Path) -> bool:
    """Detect plain-text history hits, warn the user, and prompt for c/g/q.

    Called after pattern selection and before any files are written. When files
    matching the chosen patterns already exist in git history, the user is shown
    a warning and offered three choices:
      c — continue setup (encryption from this point; history unchanged)
      g — write the retroactive encryption guide to .veil/ and exit
      q — abort setup without writing anything

    Args:
        repo_path: Root of the target git repository.
        patterns: Confirmed list of encryption patterns.
        veil_dir: Path to the .veil/ directory (used for guide output).

    Returns:
        True if setup should proceed, False if the user chose g or q.
    """
    history = check_patterns_in_history(repo_path, patterns)
    if not history:
        return True

    print()
    print(_("⚠  WARNING: Files matching your patterns are already in git history (plain text):"))
    print()
    for file_path, count in sorted(history.items()):
        print(_("  {file}  ({count} commit(s))").format(file=file_path, count=count))
    print()
    print(
        _(
            "Encrypting these files now protects future commits,"
            " but the existing history will remain readable."
        )
    )
    print()
    print(_("Options:"))
    print(_("  [c] Continue — encrypt from this point forward (history stays as-is)"))
    print(_("  [g] Guide — write step-by-step guide to .veil/RETROACTIVE_ENCRYPTION.md and exit"))
    print(_("  [q] Quit — abort setup without writing anything"))
    print()

    while True:
        choice = input(_("Your choice (c/g/q): ")).strip().lower()
        if choice in ("c", "continue"):
            return True
        if choice in ("g", "guide"):
            guide_path = _write_retroactive_guide(veil_dir)
            print()
            print(_("Guide written: {path}").format(path=guide_path))
            print(_("No changes were made to your repository."))
            return False
        if choice in ("q", "quit"):
            print(_("Aborted."))
            return False
        print(_("Invalid choice. Enter c, g, or q."))


def run_interactive_setup(repo_path: Path, ctx: DryRunContext) -> None:
    """Execute the full interactive setup flow (steps 1–6)."""
    repo_path = repo_path.resolve()
    veil_dir = repo_path / ".veil"
    repo_name = repo_path.name

    config: VeilConfig
    if detect_existing_config(repo_path):
        show_config(repo_path)
        existing = read_config(veil_dir / "config.toml")
        config = existing if existing is not None else VeilConfig()
        answer = input(_("Continue editing configuration? (y/N): ")).strip().lower()
        if answer not in ("a", "ano", "y", "yes"):
            print(_("Aborted."))
            return
    else:
        config = VeilConfig()

    new_patterns = select_patterns_interactive(repo_path)
    for pattern in new_patterns:
        add_pattern(config, pattern)

    # Detect files already in git history as plain text; let user decide how to proceed.
    if config.patterns and not warn_history_plaintext(repo_path, config.patterns, veil_dir):
        return

    key_path, public_key = prompt_key_management(repo_name, ctx)
    config.key_path = str(key_path.expanduser())
    config.recipient_primary = public_key

    additional = prompt_additional_recipients()
    for recipient in additional:
        if recipient != config.recipient_primary and recipient not in config.recipient_others:
            config.recipient_others.append(recipient)

    print_security_warning()
    config.language = get_current_language()
    write_config(config, veil_dir, ctx)
    write_gitattributes(repo_path, config.patterns, ctx)
    write_git_config_filters(repo_path, config, ctx)
    write_setup_sh(veil_dir, config, ctx)
    write_setup_py(veil_dir, config, ctx)
    write_readme_veil(veil_dir, ctx)
    print_final_summary(repo_path, config)

    if ctx.enabled and ctx.recorded_actions():
        print()
        print(_("Planned actions summary (dry-run):"))
        for action in ctx.recorded_actions():
            print(f"  {action}")


def _load_or_exit(repo_path: Path) -> VeilConfig:
    config_path = repo_path / ".veil" / "config.toml"
    config = read_config(config_path)
    if config is None:
        print(
            _("Error: repository is not configured (.veil/config.toml missing)."),
            file=sys.stderr,
        )
        raise SystemExit(1)
    return config


def _handle_add_pattern(repo_path: Path, pattern: str, ctx: DryRunContext) -> None:
    config = _load_or_exit(repo_path)
    if add_pattern(config, pattern):
        write_config(config, repo_path / ".veil", ctx)
        print(_("Pattern added: {pattern}").format(pattern=pattern))
    else:
        print(_("Pattern already exists: {pattern}").format(pattern=pattern))


def _handle_remove_pattern(repo_path: Path, pattern: str, ctx: DryRunContext) -> None:
    config = _load_or_exit(repo_path)
    if remove_pattern(config, pattern):
        write_config(config, repo_path / ".veil", ctx)
        print(_("Pattern removed: {pattern}").format(pattern=pattern))
    else:
        print(_("Pattern not found: {pattern}").format(pattern=pattern))


def _handle_reinit(repo_path: Path, ctx: DryRunContext) -> None:
    config = _load_or_exit(repo_path)
    write_git_config_filters(repo_path, config, ctx)
    print(_("Git config filters were re-written."))


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for veil_setup.py — interactive setup and CLI modes."""
    argv_list = list(sys.argv[1:] if argv is None else argv)
    prepare_cli_language(argv_list)
    parser = build_parser()
    args = parser.parse_args(argv_list)
    repo_path = Path(args.repo_path).resolve() if args.repo_path else None
    if peek_cli_language(argv_list) is None:
        init_language(args, repo_path)

    if args.version:
        print(f"veil_setup.py {VERSION}")
        raise SystemExit(0)

    if args.show_config:
        if repo_path is None:
            print(_("Error: repo_path is required for --show-config."), file=sys.stderr)
            raise SystemExit(2)
        show_config(repo_path)
        raise SystemExit(0)

    if args.add_pattern:
        if repo_path is None:
            print(_("Error: repo_path is required for --add-pattern."), file=sys.stderr)
            raise SystemExit(2)
        check_dependencies()
        ctx = DryRunContext(enabled=args.dry_run)
        _handle_add_pattern(repo_path, args.add_pattern, ctx)
        raise SystemExit(0)

    if args.remove_pattern:
        if repo_path is None:
            print(_("Error: repo_path is required for --remove-pattern."), file=sys.stderr)
            raise SystemExit(2)
        check_dependencies()
        ctx = DryRunContext(enabled=args.dry_run)
        _handle_remove_pattern(repo_path, args.remove_pattern, ctx)
        raise SystemExit(0)

    if args.reinit:
        if repo_path is None:
            print(_("Error: repo_path is required for --reinit."), file=sys.stderr)
            raise SystemExit(2)
        check_dependencies()
        ctx = DryRunContext(enabled=args.dry_run)
        _handle_reinit(repo_path, ctx)
        raise SystemExit(0)

    if repo_path is None:
        parser.print_help()
        raise SystemExit(2)

    ctx = DryRunContext(enabled=args.dry_run)
    check_dependencies(ctx)
    run_interactive_setup(repo_path, ctx)


if __name__ == "__main__":
    main()
