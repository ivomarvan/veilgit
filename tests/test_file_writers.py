"""Unit tests for output file writers (T050)."""

import stat
from pathlib import Path

import pytest

import veil_setup


def _sample_config() -> veil_setup.VeilConfig:
    return veil_setup.VeilConfig(
        version="1",
        key_path="~/.config/age/repo_key.txt",
        recipient_primary="age1" + "q" * 58,
        recipient_others=["age1" + "z" * 58],
        patterns=["*.md"],
    )


@pytest.mark.unit
def test_write_gitattributes_creates_new_file(tmp_path: Path) -> None:
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_gitattributes(tmp_path, ["*.md"], ctx)
    content = (tmp_path / ".gitattributes").read_text(encoding="utf-8")
    assert "*.md filter=veil diff=veil" in content


@pytest.mark.unit
def test_write_gitattributes_always_adds_veil_config_toml(tmp_path: Path) -> None:
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_gitattributes(tmp_path, ["*.md"], ctx)
    content = (tmp_path / ".gitattributes").read_text(encoding="utf-8")
    assert ".veil/config.toml filter=veil diff=veil" in content


@pytest.mark.unit
def test_write_gitattributes_idempotent_no_duplicate(tmp_path: Path) -> None:
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_gitattributes(tmp_path, ["*.md"], ctx)
    veil_setup.write_gitattributes(tmp_path, ["*.md"], ctx)
    content = (tmp_path / ".gitattributes").read_text(encoding="utf-8")
    assert content.count("*.md filter=veil diff=veil") == 1


@pytest.mark.unit
def test_write_gitattributes_preserves_existing_lines(tmp_path: Path) -> None:
    gitattributes = tmp_path / ".gitattributes"
    gitattributes.write_text("*.log text\n", encoding="utf-8")
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_gitattributes(tmp_path, ["*.md"], ctx)
    content = gitattributes.read_text(encoding="utf-8")
    assert "*.log text" in content
    assert "*.md filter=veil diff=veil" in content


@pytest.mark.unit
def test_write_gitattributes_managed_comment_present(tmp_path: Path) -> None:
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_gitattributes(tmp_path, ["*.md"], ctx)
    content = (tmp_path / ".gitattributes").read_text(encoding="utf-8")
    assert veil_setup.GITATTRIBUTES_MANAGED_MARKER in content


@pytest.mark.unit
def test_write_git_config_filters_creates_filter_section(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    config = _sample_config()
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_git_config_filters(tmp_path, config, ctx)
    content = (tmp_path / ".git" / "config").read_text(encoding="utf-8")
    assert '[filter "veil"]' in content
    assert "clean" in content
    assert "smudge" in content
    assert "required = true" in content


@pytest.mark.unit
def test_write_git_config_filters_multiple_recipients(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    config = _sample_config()
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_git_config_filters(tmp_path, config, ctx)
    content = (tmp_path / ".git" / "config").read_text(encoding="utf-8")
    assert content.count("-r age1") == 2


@pytest.mark.unit
def test_write_git_config_filters_dry_run_no_write(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    config_file = git_dir / "config"
    config_file.write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
    original = config_file.read_text(encoding="utf-8")
    ctx = veil_setup.DryRunContext(enabled=True)
    veil_setup.write_git_config_filters(tmp_path, _sample_config(), ctx)
    assert config_file.read_text(encoding="utf-8") == original
    assert ctx.recorded_actions()


@pytest.mark.unit
def test_write_setup_sh_created_on_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "linux")
    veil_dir = tmp_path / ".veil"
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_setup_sh(veil_dir, _sample_config(), ctx)
    script = veil_dir / "setup_veil.sh"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash")
    assert "setup_veil.sh" in content


@pytest.mark.unit
def test_write_setup_sh_executable_bit_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "linux")
    veil_dir = tmp_path / ".veil"
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_setup_sh(veil_dir, _sample_config(), ctx)
    mode = (veil_dir / "setup_veil.sh").stat().st_mode
    assert mode & stat.S_IXUSR


@pytest.mark.unit
def test_write_setup_sh_not_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(veil_setup.sys, "platform", "win32")
    veil_dir = tmp_path / ".veil"
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_setup_sh(veil_dir, _sample_config(), ctx)
    assert not (veil_dir / "setup_veil.sh").exists()


@pytest.mark.unit
def test_write_setup_py_created_always(tmp_path: Path) -> None:
    veil_dir = tmp_path / ".veil"
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_setup_py(veil_dir, _sample_config(), ctx)
    script = veil_dir / "setup_veil.py"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert "Usage: python setup_veil.py" in content


@pytest.mark.unit
def test_write_readme_veil_creates_file(tmp_path: Path) -> None:
    veil_dir = tmp_path / ".veil"
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_readme_veil(veil_dir, ctx)
    readme = veil_dir / "README_VEIL.md"
    assert readme.is_file()
    content = readme.read_text(encoding="utf-8")
    assert "What is veilgit" in content
    assert "git clone" in content
    assert "collaborator" in content.lower()
    assert "Key backup" in content
    assert "Security" in content
