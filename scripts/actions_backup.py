"""写入前的自动备份与轮转（从 `actions_core.py` 拆出，那里逼近 800 行上限）。

目录选 `data/backup/`：它在 `.gitignore` 里（不会被 GitSync 推到 GitHub），
而 `data/*.json` 本身有 git 历史兜底 —— 两者互补。

⚠ `DATA` **必须每次现算**（延迟 import `actions_core` 取它的当前值）：测试的
`sandbox` fixture 会替换 `actions_core.DATA`，固化过一次的代价是备份写进用户真实
`data/`（2026-10-16 实测发生过）。
"""

import configparser
import shutil
from datetime import datetime
from pathlib import Path

DEFAULT_MAX_BACKUPS = 10


def _backup_dir() -> Path:
    """备份目录（每次现算，见模块说明）。"""
    import scripts.actions_core as core

    return core.DATA / "backup" / "actions"


def _max_backups() -> int:
    """保留份数：读设置里的 `Backup.max_backups`（该键此前存在但无人使用）。

    用 configparser **只读**打开 settings.ini：绝不能为了读一个数字而让
    SettingsManager 去补默认值 / 回写这个含密钥的文件。
    """
    import scripts.actions_core as core

    try:
        parser = configparser.ConfigParser()
        parser.read(core.DATA / "settings.ini", encoding="utf-8")
        return max(1, min(int(parser.get("Backup", "max_backups", fallback="10")), 100))
    except (OSError, ValueError, configparser.Error):
        return DEFAULT_MAX_BACKUPS


def _backup_file(p: Path) -> Path | None:
    """把 `p` 的**当前内容**存一份到备份目录，并按份数上限轮转。"""
    if not p.exists():
        return None
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{p.name}.{stamp}.json"
    n = 2
    while dest.exists():                      # 同一秒内多次写入也不互相覆盖
        dest = backup_dir / f"{p.name}.{stamp}-{n}.json"
        n += 1
    shutil.copy2(p, dest)
    olds = sorted(backup_dir.glob(f"{p.name}.*.json"))
    for old in olds[:-_max_backups()]:
        old.unlink(missing_ok=True)
    return dest
