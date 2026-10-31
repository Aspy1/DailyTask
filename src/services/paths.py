"""数据目录解析（**唯一入口**）：默认 `<repo>/data`，可用环境变量覆盖。

为什么要覆盖：全量回归/验收需要**真实启动应用**，但不能碰用户真实的 `data/`
（含密钥与全部个人数据）。设置 `LIFE_ASSISTANT_DATA_DIR=<临时目录>` 后，
应用、CLI（`scripts/actions.py`）、天气缓存与设置面板都指向同一个沙箱。

⚠ 这是**进程启动前**的环境变量：各模块在 import 时读它一次（与 Qt/日志初始化一致）。
"""

import os
from pathlib import Path

DATA_DIR_ENV = "LIFE_ASSISTANT_DATA_DIR"


def default_data_dir() -> Path:
    """仓库根下的 `data/`。"""
    return Path(__file__).resolve().parents[2] / "data"


def get_data_dir() -> Path:
    """当前生效的数据目录（环境变量优先）。"""
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    return Path(override).expanduser().resolve() if override else default_data_dir()


DATA_DIR = get_data_dir()
