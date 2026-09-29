import subprocess
from typing import Any

import pytest

from hwbench.collectors import UnsupportedPlatformError, get_collector
from hwbench.collectors.linux import _exec
from hwbench.collectors.linux.cpu import LinuxCpuCollector


class _Proc:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def run(args: list[str], **kwargs: Any) -> _Proc:
        calls.append({"args": args, **kwargs})
        return _Proc('{"ok": true}')

    monkeypatch.setattr(_exec.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(_exec.subprocess, "run", run)
    return calls


def test_run_forces_c_locale_and_timeout(fake_run: list[dict[str, Any]]) -> None:
    assert _exec.run_json(["lscpu", "-J"]) == {"ok": True}
    call = fake_run[0]
    assert call["env"]["LC_ALL"] == "C"
    assert call["timeout"] > 0
    assert call["check"] is False


def test_missing_tool_returns_none_without_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_exec.shutil, "which", lambda name: None)

    def boom(*a: Any, **k: Any) -> None:
        raise AssertionError("ne doit pas être appelé")

    monkeypatch.setattr(_exec.subprocess, "run", boom)
    assert _exec.run_text(["nvidia-smi"]) is None


def test_timeout_and_invalid_json_return_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_exec.shutil, "which", lambda name: "/usr/bin/x")

    def timeout(*a: Any, **k: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(_exec.subprocess, "run", timeout)
    assert _exec.run_text(["x"]) is None

    monkeypatch.setattr(_exec.subprocess, "run", lambda *a, **k: _Proc("not json"))
    assert _exec.run_json(["x"]) is None


def test_failed_command_without_output_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_exec.shutil, "which", lambda name: "/usr/bin/x")
    monkeypatch.setattr(_exec.subprocess, "run", lambda *a, **k: _Proc("", returncode=1))
    assert _exec.run_text(["x"]) is None


def test_read_sysfs_missing_or_forbidden(tmp_path) -> None:
    assert _exec.read_sysfs(tmp_path / "absent") is None
    f = tmp_path / "value"
    f.write_text("42\n")
    assert _exec.read_sysfs(f) == "42"
    assert _exec.list_dir(tmp_path / "absent") == []


def test_registry_selects_linux_implementation() -> None:
    assert isinstance(get_collector("cpu", "Linux"), LinuxCpuCollector)


def test_registry_windows_not_yet_supported() -> None:
    with pytest.raises(UnsupportedPlatformError):
        get_collector("cpu", "Windows")
