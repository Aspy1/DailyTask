"""Launch the operator's installed Hermes messaging gateway."""

import os
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment

DEFAULT_HOME = Path("D:/Dev/hermes-home")


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
    if home is None:
        home = Path(os.environ.get("HERMES_HOME") or DEFAULT_HOME)
    executable = home / "bin" / "hermes.exe"
    if not home.is_absolute() or not executable.is_file():
        return "missing"
    arguments = ["gateway", "run"]
    if restart:
        arguments.append("--replace")
    return "launched" if _start_detached(executable, arguments, home) else "failed"
