"""Unit tests for TOML config read/write and detection."""

import sys
from pathlib import Path

import pytest

import veil_setup


def _parse_toml(content: str) -> dict:
    if sys.version_info >= (3, 11):
        import tomllib

        return tomllib.loads(content)
    import tomli

    return tomli.loads(content)


@pytest.mark.unit
def test_toml_writer_roundtrip_basic_config() -> None:
    config = veil_setup.VeilConfig(
        version="1",
        key_path="~/.config/age/repo_key.txt",
        recipient_primary="age1" + "q" * 58,
        recipient_others=["age1" + "z" * 58],
        patterns=["*.md", "secrets/**"],
        exclude_patterns=["*.tmp"],
    )
    serialized = veil_setup.TomlWriter.serialize(config)
    parsed = _parse_toml(serialized)
    assert parsed["veil"]["version"] == "1"
    assert parsed["veil"]["key_path"] == "~/.config/age/repo_key.txt"
    assert parsed["veil"]["recipients"]["primary"] == "age1" + "q" * 58
    assert parsed["veil"]["recipients"]["others"] == ["age1" + "z" * 58]
    assert parsed["veil"]["patterns"]["patterns"] == ["*.md", "secrets/**"]
    assert parsed["veil"]["exclude"]["patterns"] == ["*.tmp"]


@pytest.mark.unit
def test_toml_writer_empty_others_and_exclude() -> None:
    config = veil_setup.VeilConfig(
        recipient_primary="age1" + "q" * 58,
        recipient_others=[],
        exclude_patterns=[],
    )
    serialized = veil_setup.TomlWriter.serialize(config)
    parsed = _parse_toml(serialized)
    assert parsed["veil"]["recipients"]["others"] == []
    assert parsed["veil"]["exclude"]["patterns"] == []


@pytest.mark.unit
def test_toml_writer_preserves_tilde_in_key_path() -> None:
    config = veil_setup.VeilConfig(key_path="~/.config/age/k.txt")
    serialized = veil_setup.TomlWriter.serialize(config)
    parsed = _parse_toml(serialized)
    assert parsed["veil"]["key_path"] == "~/.config/age/k.txt"


@pytest.mark.unit
def test_read_config_missing_file_returns_none() -> None:
    assert veil_setup.read_config(Path("/nonexistent/config.toml")) is None


@pytest.mark.unit
def test_read_config_valid_toml_returns_veil_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[veil]
version = "1"
key_path = "~/.config/age/repo_key.txt"

[veil.recipients]
primary = "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
others = ["age1zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"]

[veil.patterns]
patterns = ["*.md"]

[veil.exclude]
patterns = []
""".strip(),
        encoding="utf-8",
    )
    config = veil_setup.read_config(config_path)
    assert config is not None
    assert config.version == "1"
    assert config.key_path == "~/.config/age/repo_key.txt"
    assert config.patterns == ["*.md"]


@pytest.mark.unit
def test_read_config_missing_key_raises_value_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[other]\nvalue = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required \\[veil\\]"):
        veil_setup.read_config(config_path)


@pytest.mark.unit
def test_detect_existing_config_no_file(tmp_path: Path) -> None:
    assert veil_setup.detect_existing_config(tmp_path) is False


@pytest.mark.unit
def test_detect_existing_config_file_present(tmp_path: Path) -> None:
    veil_dir = tmp_path / ".veil"
    veil_dir.mkdir()
    (veil_dir / "config.toml").write_text('[veil]\nversion = "1"\n', encoding="utf-8")
    assert veil_setup.detect_existing_config(tmp_path) is True


@pytest.mark.unit
def test_write_config_dry_run_no_file_created(tmp_path: Path) -> None:
    config = veil_setup.VeilConfig(recipient_primary="age1" + "q" * 58)
    ctx = veil_setup.DryRunContext(enabled=True)
    veil_setup.write_config(config, tmp_path / ".veil", ctx)
    assert not (tmp_path / ".veil" / "config.toml").exists()
    assert ctx.recorded_actions()


@pytest.mark.unit
def test_write_config_creates_parseable_toml(tmp_path: Path) -> None:
    config = veil_setup.VeilConfig(
        recipient_primary="age1" + "q" * 58,
        patterns=["*.md"],
    )
    ctx = veil_setup.DryRunContext(enabled=False)
    veil_setup.write_config(config, tmp_path / ".veil", ctx)
    content = (tmp_path / ".veil" / "config.toml").read_text(encoding="utf-8")
    parsed = _parse_toml(content)
    assert parsed["veil"]["patterns"]["patterns"] == ["*.md"]
