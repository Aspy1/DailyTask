"""Launch the operator's installed Hermes messaging gateway."""

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment

DEFAULT_HOME = Path("D:/Dev/hermes-home")
_MAX_STATE_BYTES = 65_536
_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 258
_WINDOWS_EPOCH_CENTISECONDS = 1_164_447_360_000
_FILETIME_PER_CENTISECOND = 100_000


def _gateway_home(home: Path | None) -> Path:
    return home if home is not None else Path(os.environ.get("HERMES_HOME") or DEFAULT_HOME)


def _running_process_birth(pid: int) -> int | None:
    if os.name != "nt":
        return None
    kernel = ctypes.WinDLL("kernel32")
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, False, pid)
    if not handle:
        return None
    process = wintypes.HANDLE(handle)
    try:
        if kernel.WaitForSingleObject(process, 0) != _WAIT_TIMEOUT:
            return None
        created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(process, ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            return None
        ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return round(ticks / _FILETIME_PER_CENTISECOND) - _WINDOWS_EPOCH_CENTISECONDS
    finally:
        kernel.CloseHandle(process)


def gateway_online(home: Path | None = None) -> bool:
    """Check Hermes' local serving state against the Windows process identity."""
    directory = _gateway_home(home)
    if not directory.is_absolute():
        return False
    try:
        with (directory / "gateway_state.json").open("rb") as state:
            payload = state.read(_MAX_STATE_BYTES + 1)
        record = json.loads(payload) if len(payload) <= _MAX_STATE_BYTES else None
    except (OSError, ValueError):
        return False
    if not isinstance(record, dict) or record.get("gateway_state") not in ("running", "degraded"):
        return False
    pid, birth = record.get("pid"), record.get("start_time")
    if type(pid) is not int or not 0 < pid < 2**32 or type(birth) is not int:
        return False
    return _running_process_birth(pid) == birth


def _start_detached(executable: Path, arguments: list[str], home: Path) -> bool:
    process = QProcess()
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert("HERMES_HOME", str(home))
    process.setProcessEnvironment(environment)
    process.setWorkingDirectory(str(home))
    process.setProgram(str(executable))
    process.setArguments(arguments)
    return process.startDetached()


def launch_gateway(home: Path | None = None, *, restart: bool = False) -> str:
    home = _gateway_home(home)
    executable = home / "bin" / "hermes.exe"
    if not home.is_absolute() or not executable.is_file():
        return "missing"
    arguments = ["gateway", "run"]
    if restart:
        arguments.append("--replace")
    return "launched" if _start_detached(executable, arguments, home) else "failed"
