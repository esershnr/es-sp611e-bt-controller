"""Unit tests for background process management and startup task registration."""

import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from sp611e_cli import background as bg


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(bg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(bg, "PID_FILE", tmp_path / "openrgb.pid")
    monkeypatch.setattr(bg, "OUTPUT_LOG", tmp_path / "openrgb.out.log")
    yield


def test_pid_file_roundtrip_and_alive_check() -> None:
    assert bg.read_pid() is None
    bg.write_pid(os.getpid())
    assert bg.read_pid() == os.getpid()
    assert bg.is_process_alive(os.getpid()) is True
    assert bg.running_pid() == os.getpid()
    bg.remove_pid(12345)  # wrong owner -> keeps file
    assert bg.read_pid() == os.getpid()
    bg.remove_pid(os.getpid())
    assert bg.read_pid() is None


def test_stale_pid_file_is_cleaned_up() -> None:
    bg.write_pid(999999)
    with patch.object(bg, "is_process_alive", return_value=False):
        assert bg.running_pid() is None
    assert bg.read_pid() is None


def test_is_process_alive_rejects_bad_pids() -> None:
    assert bg.is_process_alive(0) is False
    assert bg.is_process_alive(-1) is False


def test_program_command_frozen_vs_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert bg.program_command() == [sys.executable, "-m", "sp611e_cli"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert bg.program_command() == [sys.executable]
    assert bg.startup_command().endswith("openrgb --background")


def test_spawn_status_and_graceful_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A spawned child that honours the PID-file protocol is reported and stopped gracefully."""
    child = (
        "import os, sys, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from sp611e_cli import background as bg\n"
        "bg.PID_FILE = __import__('pathlib').Path(sys.argv[2])\n"
        "bg.CONFIG_DIR = bg.PID_FILE.parent\n"
        "assert bg.is_background_child()\n"
        "pid = os.getpid(); bg.write_pid(pid)\n"
        "print('child up', flush=True)\n"
        "while not bg.stop_requested(pid): time.sleep(0.05)\n"
        "print('child stopping', flush=True)\n"
        "bg.remove_pid(pid)\n"
    )
    src_dir = str(Path(bg.__file__).resolve().parents[1])
    monkeypatch.setattr(bg, "program_command", lambda: [sys.executable, "-c", child, src_dir, str(bg.PID_FILE)])

    pid = bg.spawn_background([])
    assert bg.running_pid() == pid
    assert bg.is_process_alive(pid)

    with pytest.raises(bg.BackgroundError, match="zaten"):
        bg.spawn_background([])

    stopped = bg.stop_background(timeout=5.0)
    assert stopped == pid
    deadline = time.monotonic() + 5
    while bg.is_process_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not bg.is_process_alive(pid)
    assert bg.running_pid() is None
    assert bg.stop_background() is None

    out = bg.OUTPUT_LOG.read_text(encoding="utf-8")
    assert "child up" in out and "child stopping" in out


def test_spawn_reports_child_pid_even_if_it_exits_early(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bg, "program_command", lambda: [sys.executable, "-c", "pass"])
    pid = bg.spawn_background(["x"])
    assert isinstance(pid, int) and pid > 0


def test_startup_install_uninstall_use_schtasks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("USERDOMAIN", "PC")
    monkeypatch.setenv("USERNAME", "alice")
    calls = []
    xml_seen = []

    def _fake_run(args):
        calls.append(args)
        rc = 0
        if args[0] == "/Create":
            xml_seen.append(Path(args[args.index("/XML") + 1]).read_text(encoding="utf-16"))
        if args[0] == "/Query":
            created = any(c[0] == "/Create" for c in calls[:-1])
            deleted = any(c[0] == "/Delete" for c in calls[:-1])
            rc = 0 if created and not deleted else 1
        return subprocess.CompletedProcess(args, rc, stdout="", stderr="")

    monkeypatch.setattr(bg, "_run_schtasks", _fake_run)

    assert bg.startup_installed() is False
    assert bg.install_startup(delay_seconds=75) == bg.STARTUP_TASK_NAME
    create = next(c for c in calls if c[0] == "/Create")
    assert create[create.index("/TN") + 1] == bg.STARTUP_TASK_NAME
    assert not Path(create[create.index("/XML") + 1]).exists()  # temp file cleaned up
    xml = xml_seen[0]
    assert "<UserId>PC" + chr(92) + "alice</UserId>" in xml
    assert "<Delay>PT75S</Delay>" in xml
    assert "<LogonType>InteractiveToken</LogonType>" in xml
    assert "openrgb --background</Arguments>" in xml
    assert bg.startup_installed() is True
    assert bg.uninstall_startup() is True
    assert bg.uninstall_startup() is False


def test_startup_install_falls_back_to_bare_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("USERDOMAIN", "PC")
    monkeypatch.setenv("USERNAME", "alice")
    users = []

    def _fake_run(args):
        xml = Path(args[args.index("/XML") + 1]).read_text(encoding="utf-16")
        user = xml.split("<UserId>")[1].split("</UserId>")[0]
        users.append(user)
        rc = 1 if chr(92) in user else 0
        return subprocess.CompletedProcess(args, rc, stdout="", stderr="ERROR: no mapping")

    monkeypatch.setattr(bg, "_run_schtasks", _fake_run)
    assert bg.install_startup() == bg.STARTUP_TASK_NAME
    assert users == ["PC" + chr(92) + "alice", "alice"]


def test_startup_install_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        bg, "_run_schtasks",
        lambda args: subprocess.CompletedProcess(args, 1, stdout="", stderr="ERROR: Access is denied."),
    )
    with pytest.raises(bg.BackgroundError, match="Access is denied"):
        bg.install_startup()


def test_startup_requires_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(bg.BackgroundError, match="Windows"):
        bg.install_startup()
    assert bg.startup_installed() is False
