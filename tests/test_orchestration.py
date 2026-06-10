"""Unit tests for orchestration helpers (T060)."""

from pathlib import Path

import pytest

import veil_setup


@pytest.mark.unit
def test_print_final_summary_output_format(capsys: pytest.CaptureFixture[str]) -> None:
    veil_setup.set_current_language("cs")
    config = veil_setup.VeilConfig(
        key_path="~/.config/age/myrepo_key.txt",
        recipient_primary="age1" + "q" * 58,
        patterns=["*.md", "*.txt"],
    )
    repo_path = Path("/tmp/myrepo")
    veil_setup.print_final_summary(repo_path, config)
    captured = capsys.readouterr()
    assert "Hotovo. Systém veilgit byl nastaven" in captured.out
    assert str(repo_path) in captured.out
    assert "*.md" in captured.out
    assert ".veil/config.toml" in captured.out
    assert config.recipient_primary in captured.out
    assert config.key_path in captured.out
    assert "Další kroky" in captured.out
