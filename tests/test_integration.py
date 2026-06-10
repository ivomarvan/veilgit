"""Integration tests for the full veil_setup.py flow (T060)."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

import veil_setup

SCRIPT = Path(__file__).resolve().parent.parent / "veil_setup.py"


def _run_veil(
    repo_path: Path,
    *extra_args: str,
    stdin: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repo_path), "--lang", "cs", *extra_args],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def _init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)


def _minimal_flow_stdin(key_path: Path, *, continue_existing: bool = False) -> str:
    lines: List[str] = []
    if continue_existing:
        lines.append("a")
    lines.extend(
        [
            "",  # end pattern entry
            "1",  # generate new key
            str(key_path),
            "n",  # no additional recipients
        ]
    )
    return "\n".join(lines) + "\n"


def _pattern_flow_stdin(key_path: Path, *, continue_existing: bool = False) -> str:
    lines: List[str] = []
    if continue_existing:
        lines.append("a")
    lines.extend(
        [
            "*.md",
            "a",
            "",
            "1",
            str(key_path),
            "n",
        ]
    )
    return "\n".join(lines) + "\n"


def _existing_key_flow_stdin(
    key_path: Path,
    public_key: str,
    *,
    continue_existing: bool = False,
) -> str:
    lines: List[str] = []
    if continue_existing:
        lines.append("a")
    lines.extend(
        [
            "",
            "2",
            str(key_path),
            public_key,
            "n",
        ]
    )
    return "\n".join(lines) + "\n"


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.skipif(shutil.which("age") is None, reason="age not on PATH")
def test_dry_run_creates_no_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    key_path = tmp_path / "test.key"
    before = {p.relative_to(repo) for p in repo.rglob("*") if p.is_file()}
    result = _run_veil(repo, "--dry-run", stdin=_minimal_flow_stdin(key_path))
    assert result.returncode == 0, result.stderr
    after = {p.relative_to(repo) for p in repo.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.skipif(shutil.which("age") is None, reason="age not on PATH")
def test_dry_run_output_contains_dry_run_markers(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    key_path = tmp_path / "test.key"
    result = _run_veil(repo, "--dry-run", stdin=_minimal_flow_stdin(key_path))
    assert any(line.startswith("[DRY-RUN]") for line in result.stdout.splitlines())


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.skipif(shutil.which("age") is None, reason="age not on PATH")
def test_dry_run_final_summary_in_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    key_path = tmp_path / "test.key"
    result = _run_veil(repo, "--dry-run", stdin=_minimal_flow_stdin(key_path))
    assert "Hotovo. Systém veilgit byl nastaven" in result.stdout


@pytest.mark.integration
def test_version_flag_exits_0() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


@pytest.mark.integration
def test_help_flag_exits_0() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.skipif(shutil.which("age") is None, reason="age not on PATH")
def test_full_flow_creates_expected_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    key_path = tmp_path / "repo_key.txt"
    result = _run_veil(repo, stdin=_pattern_flow_stdin(key_path))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (repo / ".veil" / "config.toml").is_file()
    assert (repo / ".gitattributes").is_file()
    assert (repo / ".veil" / "README_VEIL.md").is_file()
    if sys.platform != "win32":
        assert (repo / ".veil" / "setup_veil.sh").is_file()


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.skipif(shutil.which("age") is None, reason="age not on PATH")
def test_idempotent_second_run_no_duplicates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    key_path = tmp_path / "repo_key.txt"
    first = _run_veil(repo, stdin=_pattern_flow_stdin(key_path))
    assert first.returncode == 0, first.stderr + first.stdout
    config = veil_setup.read_config(repo / ".veil" / "config.toml")
    assert config is not None
    second = _run_veil(
        repo,
        stdin=_existing_key_flow_stdin(key_path, config.recipient_primary, continue_existing=True),
    )
    assert second.returncode == 0, second.stderr + second.stdout
    content = (repo / ".gitattributes").read_text(encoding="utf-8")
    assert content.count("*.md filter=veil diff=veil") == 1


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.skipif(shutil.which("age") is None, reason="age not on PATH")
def test_final_summary_format(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    key_path = tmp_path / "repo_key.txt"
    result = _run_veil(repo, stdin=_pattern_flow_stdin(key_path))
    assert "Hotovo. Systém veilgit byl nastaven" in result.stdout
    assert "*.md" in result.stdout
    assert str(key_path) in result.stdout or "~" in result.stdout
