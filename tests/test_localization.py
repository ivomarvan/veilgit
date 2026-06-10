"""Unit tests for localization — language resolution (E020.T010)."""

from __future__ import annotations

from unittest import mock

import pytest

import veil_setup


@pytest.mark.unit
def test_resolve_language_cli_overrides_all() -> None:
    with mock.patch("veil_setup.detect_os_language", return_value="de"):
        result = veil_setup.resolve_language("fr", "cs")
    assert result == "fr"


@pytest.mark.unit
def test_resolve_language_config_overrides_os() -> None:
    with mock.patch("veil_setup.detect_os_language", return_value="de"):
        result = veil_setup.resolve_language(None, "cs")
    assert result == "cs"


@pytest.mark.unit
def test_resolve_language_os_detection_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "linux")
    monkeypatch.setenv("LANG", "cs_CZ.UTF-8")
    result = veil_setup.resolve_language(None, None)
    assert result == "cs"


@pytest.mark.unit
def test_resolve_language_os_detection_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "win32")
    with mock.patch("veil_setup.locale.getdefaultlocale", return_value=("cs_CZ", "cp1250")):
        result = veil_setup.resolve_language(None, None)
    assert result == "cs"


@pytest.mark.unit
def test_resolve_language_fallback_to_en(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "linux")
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    with mock.patch("veil_setup.detect_os_language", return_value=None):
        result = veil_setup.resolve_language(None, None)
    assert result == "en"


@pytest.mark.unit
def test_toml_writer_adds_language_comment() -> None:
    config = veil_setup.VeilConfig(recipient_primary="age1" + "q" * 58)
    serialized = veil_setup.TomlWriter.serialize(config)
    assert '# language = "en" # Set default language (en, de, fr, sp, cs, pl)' in serialized


@pytest.mark.unit
def test_toml_writer_emits_language_when_set() -> None:
    config = veil_setup.VeilConfig(
        recipient_primary="age1" + "q" * 58,
        language="cs",
    )
    serialized = veil_setup.TomlWriter.serialize(config)
    assert 'language = "cs"' in serialized
    assert veil_setup.LANGUAGE_TOML_COMMENT not in serialized


@pytest.mark.unit
def test_translation_function_known_key() -> None:
    veil_setup.set_current_language("cs")
    assert veil_setup._("Missing required tool: ") == "Chybí požadovaný nástroj: "


@pytest.mark.unit
def test_translation_function_fallback_en() -> None:
    veil_setup.set_current_language("cs")
    assert veil_setup._("This key does not exist in translations.") == (
        "This key does not exist in translations."
    )


@pytest.mark.unit
def test_translation_function_unsupported_lang() -> None:
    veil_setup.set_current_language("xx")
    assert veil_setup._("Missing required tool: ") == "Missing required tool: "


@pytest.mark.unit
def test_peek_cli_language_long_and_short_form() -> None:
    assert veil_setup.peek_cli_language(["--lang", "pl", "repo"]) == "pl"
    assert veil_setup.peek_cli_language(["-l", "cs"]) == "cs"
    assert veil_setup.peek_cli_language(["--lang=de"]) == "de"
    assert veil_setup.peek_cli_language(["repo"]) is None


@pytest.mark.unit
def test_cli_help_polish(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        veil_setup.main(["--lang", "pl", "--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "Ścieżka do docelowego repozytorium git" in output
    assert "opcje" in output


@pytest.mark.unit
def test_cli_missing_repo_shows_polish_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        veil_setup.main(["--lang", "pl"])
    assert exc_info.value.code == 2
    output = capsys.readouterr().out
    assert "Język komunikacji" in output
