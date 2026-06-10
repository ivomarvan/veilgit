"""Unit tests for age key management helpers."""

import subprocess
from pathlib import Path
from unittest import mock

import pytest

import veil_setup


@pytest.mark.unit
def test_default_key_path_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "linux")
    path = veil_setup.default_key_path("myrepo")
    assert path.name == "myrepo_key.txt"
    assert path.parent.as_posix().endswith(".config/age")


@pytest.mark.unit
def test_default_key_path_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "darwin")
    path = veil_setup.default_key_path("myrepo")
    assert path.name == "myrepo_key.txt"
    assert path.parent.as_posix().endswith(".config/age")


@pytest.mark.unit
def test_default_key_path_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")
    path = veil_setup.default_key_path("myrepo")
    assert path.name == "myrepo_key.txt"
    assert "age" in path.parts
    assert "AppData" in path.as_posix()


@pytest.mark.unit
def test_validate_age_public_key_valid() -> None:
    assert veil_setup.validate_age_public_key("age1" + "q" * 58) is True


@pytest.mark.unit
def test_validate_age_public_key_invalid_prefix() -> None:
    assert veil_setup.validate_age_public_key("xyz1" + "q" * 58) is False


@pytest.mark.unit
def test_validate_age_public_key_too_short() -> None:
    assert veil_setup.validate_age_public_key("age1" + "q" * 57) is False


@pytest.mark.unit
def test_validate_age_public_key_invalid_charset() -> None:
    assert veil_setup.validate_age_public_key("age1" + "A" * 58) is False


@pytest.mark.unit
def test_generate_key_dry_run_no_subprocess(tmp_path: Path) -> None:
    ctx = veil_setup.DryRunContext(enabled=True)
    key_path = tmp_path / "key.txt"
    with mock.patch("veil_setup.subprocess.run") as run_mock:
        public_key = veil_setup.generate_key(key_path, ctx)
        run_mock.assert_not_called()
    assert public_key == veil_setup.DRY_RUN_PLACEHOLDER_PUBLIC_KEY


@pytest.mark.unit
def test_generate_key_parses_public_key_from_stderr(tmp_path: Path) -> None:
    ctx = veil_setup.DryRunContext(enabled=False)
    key_path = tmp_path / "key.txt"
    completed = subprocess.CompletedProcess(
        args=["age-keygen"],
        returncode=0,
        stdout="",
        stderr="# public key: age1abc\n",
    )
    with mock.patch("veil_setup.subprocess.run", return_value=completed):
        public_key = veil_setup.generate_key(key_path, ctx)
    assert public_key == "age1abc"


@pytest.mark.unit
def test_generate_key_parses_public_key_from_new_format(tmp_path: Path) -> None:
    ctx = veil_setup.DryRunContext(enabled=False)
    key_path = tmp_path / "key.txt"
    completed = subprocess.CompletedProcess(
        args=["age-keygen"],
        returncode=0,
        stdout="Public key: age1xyz\n",
        stderr="",
    )
    with mock.patch("veil_setup.subprocess.run", return_value=completed):
        public_key = veil_setup.generate_key(key_path, ctx)
    assert public_key == "age1xyz"


@pytest.mark.unit
def test_validate_existing_key_missing_file(tmp_path: Path) -> None:
    assert veil_setup.validate_existing_key(tmp_path / "missing.txt") is False


@pytest.mark.unit
def test_validate_existing_key_valid_content(tmp_path: Path) -> None:
    key_file = tmp_path / "key.txt"
    key_file.write_text("AGE-SECRET-KEY-1ABC...\n", encoding="utf-8")
    assert veil_setup.validate_existing_key(key_file) is True


@pytest.mark.unit
def test_validate_existing_key_wrong_content(tmp_path: Path) -> None:
    key_file = tmp_path / "key.txt"
    key_file.write_text("not a key\n", encoding="utf-8")
    assert veil_setup.validate_existing_key(key_file) is False


@pytest.mark.unit
def test_print_security_warning_contains_key_phrases(capsys: pytest.CaptureFixture[str]) -> None:
    veil_setup.set_current_language("cs")
    veil_setup.print_security_warning()
    captured = capsys.readouterr()
    assert "Soukromý klíč" in captured.out
    assert "obnovit" in captured.out
