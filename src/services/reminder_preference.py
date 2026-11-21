"""Publish the desktop's non-secret reminder preference for local jobs."""

import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

logger = logging.getLogger(__name__)


def _path(data_dir: Path) -> Path:
    return data_dir / "backup" / "reminder-preference"


def publish_reminder_preference(data_dir: Path, enabled: bool) -> None:
    target = _path(data_dir)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            pending = Path(handle.name)
            try:
                handle.write(b"on" if enabled else b"off")
                handle.close()
                os.replace(pending, target)
            finally:
                pending.unlink(missing_ok=True)
    except OSError:
        logger.warning("Unable to publish the reminder preference", exc_info=True)


def reminders_enabled(data_dir: Path) -> bool:
    try:
        return _path(data_dir).read_bytes() != b"off"
    except FileNotFoundError:
        return True
