"""Unit tests for check_dependencies() and DryRunContext."""

from typing import Optional
from unittest import mock

import pytest

import veil_setup


@pytest.mark.unit
def test_check_dependencies_all_present_returns_ok() -> None:
    with mock.patch("veil_setup.shutil.which", return_value="/usr/bin/tool"):
        veil_setup.check_dependencies()


@pytest.mark.unit
def test_check_dependencies_missing_age_exits() -> None:
    def which_side_effect(name: str) -> Optional[str]:
        if name == "age":
            return None
        return f"/usr/bin/{name}"

    with mock.patch("veil_setup.shutil.which", side_effect=which_side_effect):
        with pytest.raises(SystemExit) as exc_info:
            veil_setup.check_dependencies()
        assert exc_info.value.code != 0


@pytest.mark.unit
def test_check_dependencies_missing_gzip_exits() -> None:
    def which_side_effect(name: str) -> Optional[str]:
        if name == "gzip":
            return None
        return f"/usr/bin/{name}"

    with mock.patch("veil_setup.shutil.which", side_effect=which_side_effect):
        with pytest.raises(SystemExit):
            veil_setup.check_dependencies()


@pytest.mark.unit
def test_check_dependencies_platform_message_linux_debian(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def which_side_effect(name: str) -> Optional[str]:
        if name == "age":
            return None
        return f"/usr/bin/{name}"

    with mock.patch("veil_setup.shutil.which", side_effect=which_side_effect):
        with mock.patch("veil_setup.os.path.exists") as exists_mock:
            exists_mock.side_effect = lambda path: path == "/etc/debian_version"
            with pytest.raises(SystemExit):
                veil_setup.check_dependencies()
    captured = capsys.readouterr()
    assert "apt install age" in captured.err


@pytest.mark.unit
def test_check_dependencies_platform_message_linux_arch(capsys: pytest.CaptureFixture[str]) -> None:
    def which_side_effect(name: str) -> Optional[str]:
        if name == "age":
            return None
        return f"/usr/bin/{name}"

    with mock.patch("veil_setup.shutil.which", side_effect=which_side_effect):
        with mock.patch("veil_setup.os.path.exists") as exists_mock:
            exists_mock.side_effect = lambda path: path == "/etc/arch-release"
            with pytest.raises(SystemExit):
                veil_setup.check_dependencies()
    captured = capsys.readouterr()
    assert "pacman -S age" in captured.err


@pytest.mark.unit
def test_check_dependencies_platform_message_macos(capsys: pytest.CaptureFixture[str]) -> None:
    def which_side_effect(name: str) -> Optional[str]:
        if name == "age":
            return None
        return f"/usr/bin/{name}"

    with mock.patch("veil_setup.shutil.which", side_effect=which_side_effect):
        with mock.patch("veil_setup.sys.platform", "darwin"):
            with pytest.raises(SystemExit):
                veil_setup.check_dependencies()
    captured = capsys.readouterr()
    assert "brew install age" in captured.err


@pytest.mark.unit
def test_dry_run_context_enabled_records_write_file(tmp_path: pytest.TempPathFactory) -> None:
    ctx = veil_setup.DryRunContext(enabled=True)
    target = tmp_path / "foo.txt"
    ctx.write_file(target, "bar")
    assert any("foo.txt" in action for action in ctx.recorded_actions())
    assert not target.exists()


@pytest.mark.unit
def test_dry_run_context_enabled_records_run_command() -> None:
    ctx = veil_setup.DryRunContext(enabled=True)
    with mock.patch("veil_setup.subprocess.run") as run_mock:
        ctx.run_command(["git", "config", "x", "y"])
        run_mock.assert_not_called()
    assert any("git config" in action for action in ctx.recorded_actions())


@pytest.mark.unit
def test_dry_run_context_disabled_calls_real_write(tmp_path: pytest.TempPathFactory) -> None:
    ctx = veil_setup.DryRunContext(enabled=False)
    target = tmp_path / "foo.txt"
    ctx.write_file(target, "bar")
    assert target.read_text(encoding="utf-8") == "bar"
