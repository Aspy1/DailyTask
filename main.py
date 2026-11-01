"""Entry point for the student scheduler application."""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.services.paths import get_data_dir  # noqa: E402

_log_dir = get_data_dir()
_log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(_log_dir / "app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
# 第三方库的 INFO 太吵（httpx 每次请求都打一行，实测占日志 100+ 行），降到 WARNING
for _noisy in ("httpx", "httpcore", "urllib3", "requests"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# 未捕获异常（主线程 + 子线程）统一进 app.log，用户报障时可直接查
from src.services.error_hook import install_exception_hooks  # noqa: E402

install_exception_hooks()

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

# ⚠ 下面的 import 必须在日志配置**之后**（这样各模块 logger 才会写进 app.log）
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

from src.app import App  # noqa: E402


def main() -> None:
    app = App(sys.argv)
    if app.is_secondary:
        return
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

