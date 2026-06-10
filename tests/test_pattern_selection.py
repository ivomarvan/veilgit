"""Unit tests for pattern selection and add/remove pattern helpers."""

from pathlib import Path

import pytest

import veil_setup


@pytest.mark.unit
def test_glob_preview_empty_dir_returns_empty_list(tmp_path: Path) -> None:
    assert veil_setup.glob_preview("*.md", tmp_path) == []


@pytest.mark.unit
def test_glob_preview_matches_md_files_only(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    assert veil_setup.glob_preview("*.md", tmp_path) == ["a.md"]


@pytest.mark.unit
def test_glob_preview_nested_pattern(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("a", encoding="utf-8")
    assert veil_setup.glob_preview("docs/*.md", tmp_path) == ["docs/a.md"]


@pytest.mark.unit
def test_select_patterns_single_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = iter(["*.md", "a", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    repo = Path("/tmp/unused")
    result = veil_setup.select_patterns_interactive(repo)
    assert result == ["*.md"]


@pytest.mark.unit
def test_select_patterns_retry_on_n(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = iter(["*.md", "n", "*.txt", "a", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    repo = Path("/tmp/unused")
    result = veil_setup.select_patterns_interactive(repo)
    assert result == ["*.txt"]


@pytest.mark.unit
def test_select_patterns_skip_on_s(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = iter(["*.md", "s", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    repo = Path("/tmp/unused")
    result = veil_setup.select_patterns_interactive(repo)
    assert result == []


@pytest.mark.unit
def test_select_patterns_empty_input_ends_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    repo = Path("/tmp/unused")
    result = veil_setup.select_patterns_interactive(repo)
    assert result == []


@pytest.mark.unit
def test_select_patterns_final_summary_printed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    veil_setup.set_current_language("cs")
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    inputs = iter(["*.md", "a", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    veil_setup.select_patterns_interactive(tmp_path)
    captured = capsys.readouterr()
    assert "Souhrn vybraných vzorů" in captured.out
    assert "*.md" in captured.out


@pytest.mark.unit
def test_add_pattern_new_returns_true() -> None:
    config = veil_setup.VeilConfig()
    assert veil_setup.add_pattern(config, "*.md") is True
    assert config.patterns == ["*.md"]


@pytest.mark.unit
def test_add_pattern_duplicate_returns_false() -> None:
    config = veil_setup.VeilConfig(patterns=["*.md"])
    assert veil_setup.add_pattern(config, "*.md") is False
    assert config.patterns == ["*.md"]


@pytest.mark.unit
def test_remove_pattern_present_returns_true() -> None:
    config = veil_setup.VeilConfig(patterns=["*.md", "*.txt"])
    assert veil_setup.remove_pattern(config, "*.md") is True
    assert config.patterns == ["*.txt"]


@pytest.mark.unit
def test_remove_pattern_not_present_returns_false() -> None:
    config = veil_setup.VeilConfig(patterns=["*.txt"])
    assert veil_setup.remove_pattern(config, "*.md") is False
    assert config.patterns == ["*.txt"]
