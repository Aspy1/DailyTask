"""Entry point for the student scheduler application."""

import logging
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_log_dir = Path(__file__).parent / "data"
_log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(_log_dir / "app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

from src.app import App


def main():
    app = App(sys.argv)
    if app.is_secondary:
        return
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

