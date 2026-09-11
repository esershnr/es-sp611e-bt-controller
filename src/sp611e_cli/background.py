"""Run the OpenRGB bridge as a detached background process and manage autostart.

Pieces:
- PID file (~/.sp611e/openrgb.pid): written when a background bridge starts,
  removed when it exits. Deleting the file is also the *stop signal*: the
  running bridge watches it and shuts down gracefully (BLE disconnect) when
  it disappears, so stop_background() never has to kill the process unless
  it stops responding.
- spawn_background(): re-launches the current program without a console
  window; stdout/stderr go to ~/.sp611e/openrgb.out.log.
- Task Scheduler (Windows): install_startup()/uninstall_startup() register
  "run `sp611e openrgb --background` at logon" via schtasks.
"""

import getpass
import html
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import List, Optional

from sp611e_cli.config import CONFIG_DIR

PID_FILE: Path = CONFIG_DIR / "openrgb.pid"
OUTPUT_LOG: Path = CONFIG_DIR / "openrgb.out.log"
STARTUP_TASK_NAME: str = "SP611E OpenRGB Bridge"

# Set in the child's environment so it knows to maintain the PID file.
BACKGROUND_ENV: str = "SP611E_BACKGROUND"

# PyInstaller bootloader variables (6.x plus the legacy 4/5 name); see spawn_background().
PYINSTALLER_ENV_VARS = (
    "_PYI_APPLICATION_HOME_DIR",
    "_PYI_ARCHIVE_FILE",
    "_PYI_PARENT_PROCESS_LEVEL",
    "_PYI_SPLASH_IPC",
    "_MEIPASS2",
)


class BackgroundError(Exception):
    """Raised when a background/startup operation fails."""


# --- PID file ---------------------------------------------------------------


def read_pid() -> Optional[int]:
    """Return the PID stored in the PID file, or None if absent/invalid."""
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_pid(pid: int) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid), encoding="utf-8")


def remove_pid(pid: Optional[int] = None) -> None:
    """Delete the PID file (only if it still belongs to `pid`, when given)."""
    if pid is not None and read_pid() != pid:
        return
    try:
        PID_FILE.unlink()
    except OSError:
        pass


def is_process_alive(pid: int) -> bool:
    """Check whether a process with this PID exists (without signalling it)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # os.kill(pid, 0) would TERMINATE the process on Windows; query it instead.
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def running_pid() -> Optional[int]:
    """PID of a live background bridge, or None (a stale PID file is cleaned up)."""
    pid = read_pid()
    if pid is None:
        return None
    if is_process_alive(pid):
        return pid
    remove_pid(pid)
    return None


def is_background_child() -> bool:
    """True inside a process launched by spawn_background()."""
    return os.environ.get(BACKGROUND_ENV) == "1"


# --- spawning ---------------------------------------------------------------


def program_command() -> List[str]:
    """Command prefix that re-invokes this program (frozen exe or `python -m sp611e_cli`)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "sp611e_cli"]


def spawn_background(args: List[str]) -> int:
    """Start `<program> <args>` detached from this console; returns the child's PID.

    Raises:
        BackgroundError: If a bridge is already running or the process cannot start.
    """
    existing = running_pid()
    if existing is not None:
        raise BackgroundError(f"Arka planda zaten bir köprü çalışıyor (PID {existing}). Önce: sp611e openrgb --stop")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, **{BACKGROUND_ENV: "1"})
    # PyInstaller onefile: the bootloader passes these to its own child so it
    # reuses the extracted _MEIxxxx directory. If our detached child inherits
    # them it shares *our* directory, which is deleted when this process exits
    # and lazily-imported modules (e.g. winrt.*) then vanish from under it.
    # Strip them so the child extracts its own copy.
    for key in PYINSTALLER_ENV_VARS:
        env.pop(key, None)
    kwargs: dict = {"stdin": subprocess.DEVNULL, "env": env, "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True

    try:
        out = open(OUTPUT_LOG, "a", encoding="utf-8")
    except OSError as exc:
        raise BackgroundError(f"Çıktı dosyası açılamadı ({OUTPUT_LOG}): {exc}") from exc
    with out:
        try:
            proc = subprocess.Popen(program_command() + list(args), stdout=out, stderr=subprocess.STDOUT, **kwargs)
        except OSError as exc:
            raise BackgroundError(f"Arka plan süreci başlatılamadı: {exc}") from exc

    # The child writes the PID file itself once it is up (under a venv launcher
    # its real PID differs from proc.pid). Wait briefly so callers get the
    # right number; if the child dies first (e.g. config error) report proc.pid.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        pid = read_pid()
        if pid is not None:
            return pid
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    return proc.pid


def stop_background(timeout: float = 15.0) -> Optional[int]:
    """Ask the background bridge to stop (by removing its PID file); kill it if it lingers.

    Returns:
        The PID that was stopped, or None if nothing was running.
    """
    pid = running_pid()
    if pid is None:
        return None

    remove_pid(pid)  # graceful stop signal, see watch_stop_signal()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_process_alive(pid):
            return pid
        time.sleep(0.2)

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
        else:
            import signal

            os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        raise BackgroundError(f"Süreç {pid} durdurulamadı: {exc}") from exc
    return pid


def stop_requested(pid: int) -> bool:
    """For the background child: True once its PID file is gone or belongs to someone else."""
    return read_pid() != pid


# --- Windows Task Scheduler --------------------------------------------------


def _require_windows() -> None:
    if sys.platform != "win32":
        raise BackgroundError("Oturum açılışında otomatik başlatma yalnızca Windows'ta (Görev Zamanlayıcı) desteklenir.")


def _run_schtasks(args: List[str]) -> subprocess.CompletedProcess:
    try:
        # Console tools print in the OEM code page (e.g. cp857 on Turkish Windows), not the ANSI one.
        return subprocess.run(
            ["schtasks"] + args, capture_output=True, text=True, encoding="oem", errors="replace", check=False
        )
    except OSError as exc:
        raise BackgroundError(f"schtasks çalıştırılamadı: {exc}") from exc


def startup_command() -> str:
    """The command line the scheduled task runs."""
    parts = program_command() + ["openrgb", "--background"]
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


def _task_user_candidates() -> List[str]:
    """Account names to try in the task XML (DOMAIN\\user first, then bare user)."""
    user = os.environ.get("USERNAME") or getpass.getuser()
    domain = os.environ.get("USERDOMAIN")
    candidates = [f"{domain}\\{user}"] if domain else []
    candidates.append(user)
    return candidates


def startup_task_xml(user: str, delay_seconds: int) -> str:
    """Task Scheduler XML: run at this user's logon, interactive, least privilege."""
    parts = program_command() + ["openrgb", "--background"]
    command = html.escape(parts[0])
    arguments = html.escape(" ".join(f'"{p}"' if " " in p else p for p in parts[1:]))
    user_xml = html.escape(user)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>SP611E LED şeridini OpenRGB ile senkronlayan köprüyü arka planda başlatır (sp611e openrgb --background).</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user_xml}</UserId>
      <Delay>PT{max(0, delay_seconds)}S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user_xml}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>
    <Hidden>false</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def install_startup(delay_seconds: int = 15) -> str:
    """Register a logon task that starts the background bridge; returns the task name.

    Uses an XML definition with an explicit LogonTrigger/Principal UserId:
    unlike `schtasks /SC ONLOGON`, that does not require administrator
    rights. The task runs only while the user is logged on (no password
    needed) and waits `delay_seconds` so Bluetooth/OpenRGB can come up; the
    bridge retries on its own anyway, so exact ordering does not matter.
    """
    _require_windows()
    last_error = ""
    for user in _task_user_candidates():
        with tempfile.NamedTemporaryFile("w", suffix=".xml", encoding="utf-16", delete=False) as fh:
            fh.write(startup_task_xml(user, delay_seconds))
            xml_path = fh.name
        try:
            result = _run_schtasks(["/Create", "/F", "/TN", STARTUP_TASK_NAME, "/XML", xml_path])
        finally:
            try:
                os.unlink(xml_path)
            except OSError:
                pass
        if result.returncode == 0:
            return STARTUP_TASK_NAME
        last_error = (result.stderr or result.stdout).strip()
    raise BackgroundError(f"Görev oluşturulamadı: {last_error}")


def uninstall_startup() -> bool:
    """Remove the logon task; returns False if it did not exist."""
    _require_windows()
    if not startup_installed():
        return False
    result = _run_schtasks(["/Delete", "/F", "/TN", STARTUP_TASK_NAME])
    if result.returncode != 0:
        raise BackgroundError(f"Görev silinemedi: {(result.stderr or result.stdout).strip()}")
    return True


def startup_installed() -> bool:
    """True if the logon task exists."""
    if sys.platform != "win32":
        return False
    return _run_schtasks(["/Query", "/TN", STARTUP_TASK_NAME]).returncode == 0
