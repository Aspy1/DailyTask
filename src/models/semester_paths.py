"""按学期分文件的**数据布局**（唯一的路径解析与迁移处）。

```
data/
├── semesters.json                     学期注册表：semesters[] + current_semester（共享）
├── semesters/<学期id>/
│   ├── courses.json                   该学期课程表（含节假日）
│   ├── tasks.json                     该学期作业
│   └── exams.json                     该学期考试
├── habits.json                        日常（跨学期共享）
├── expenses.json                      记账（跨学期共享）
├── inventory.json                     有什么（跨学期共享）
└── daily_logs.json                    日程计划 / 存钱 / 自定义提醒（跨学期共享）
```

**为什么这样分**（用户口径）：课程表 / 作业 / 考试是"这一学期的事" —— 切换学期就该换一份数据；
而"有什么 / 记账 / 习惯 / 日程计划"是长期资产，跨学期延续。
此前课程/作业/考试**没有任何学期归属**，切学期只改"周次→日期"的映射，课表永远不变。

本模块只做**路径与迁移**，不依赖 Qt、不 import 模型（避免环）。
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from src.models.semester import DEFAULT_SEMESTER_ID, default_semester

logger = logging.getLogger(__name__)

REGISTRY_NAME = "semesters.json"
SEMESTER_DIR = "semesters"
PER_SEMESTER_NAMES = ("courses.json", "tasks.json", "exams.json")


def registry_path(data_dir: Path) -> Path:
    return data_dir / REGISTRY_NAME


def semester_dir(data_dir: Path, semester_id: str) -> Path:
    return data_dir / SEMESTER_DIR / (semester_id or DEFAULT_SEMESTER_ID)


def is_per_semester(name: str) -> bool:
    return Path(name).name in PER_SEMESTER_NAMES


def read_registry(data_dir: Path) -> dict:
    """读注册表：缺文件 → 空 dict；**坏 JSON → 留档后按空处理**（不静默覆盖，审查 #5）。"""
    path = registry_path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        keep = _quarantine(path)
        logger.error("学期注册表无法解析，现场已留档到 %s（将重建一份）", keep)
        return {}


def _quarantine(path: Path) -> Path:
    """把坏文件改名留档，返回留档路径 —— **保留现场**，绝不直接覆盖（审查 #5）。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    keep = path.with_name(f"{path.stem}.corrupt-{stamp}{path.suffix}")
    try:
        os.replace(path, keep)
    except OSError:
        keep = path                         # 没搬成 → 返回原路径
        logger.error("留档失败：%s", path, exc_info=True)
    return keep


def read_current_id(data_dir: Path) -> str:
    return str(read_registry(data_dir).get("current_semester") or "")


def ensure_current(data_dir: Path) -> str:
    """保证存在一个"当前学期"，返回其 id（幂等）。

    用于：全新目录（CLI / 测试 / 首次运行）第一次写按学期的文件时。
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    registry = read_registry(data_dir)
    semesters = registry.get("semesters") or []
    current = str(registry.get("current_semester") or "")
    if current and any(s.get("id") == current for s in semesters):
        return current
    if not semesters:
        semesters = [default_semester()]
    current = semesters[-1].get("id") or DEFAULT_SEMESTER_ID
    registry.update({"_version": registry.get("_version", 1),
                     "semesters": semesters, "current_semester": current})
    registry_path(data_dir).write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="")
    logger.info("已建立默认学期 %s（%s）", current, data_dir)
    return current


def resolve(data_dir: Path, name: str) -> Path:
    """把文件名解析成实际路径：按学期的进 `<data>/semesters/<当前学期>/`，其余在根下。"""
    if not is_per_semester(name):
        return data_dir / name
    return semester_dir(data_dir, ensure_current(data_dir)) / Path(name).name


def _read_legacy(data_dir: Path) -> tuple[dict, list[dict], str] | None:
    """读旧布局的 courses.json；不可用时返回 None。"""
    old_path = data_dir / "courses.json"
    if not old_path.exists():
        return None
    try:
        old = json.loads(old_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.error("迁移失败：%s 无法解析，保持原样", old_path, exc_info=True)
        return None
    semesters = old.get("semesters") or []
    current = str(old.get("current_semester") or "")
    if not semesters:
        semesters = [default_semester()]
        current = DEFAULT_SEMESTER_ID
    elif not any(s.get("id") == current for s in semesters):
        current = semesters[-1].get("id") or DEFAULT_SEMESTER_ID
    return old, semesters, current


def _write_new_layout(data_dir: Path, old: dict, semesters: list[dict],
                      current: str) -> Path:
    """写新布局（注册表 + 当前学期的三个文件），返回学期目录。"""
    target = semester_dir(data_dir, current)
    target.mkdir(parents=True, exist_ok=True)
    (target / "courses.json").write_text(json.dumps({
        "_version": 1,
        "courses": old.get("courses", []),
        "holidays": old.get("holidays", {"excluded": [], "makeup": {}}),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
    for name in ("tasks.json", "exams.json"):
        source = data_dir / name
        if source.exists():
            (target / name).write_text(source.read_text(encoding="utf-8"),
                                       encoding="utf-8", newline="")
    registry_path(data_dir).write_text(json.dumps({
        "_version": 1, "semesters": semesters, "current_semester": current,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
    return target


def migrate_legacy(data_dir: Path) -> bool:
    """旧布局 → 新布局（**幂等**；已迁移过返回 False）。

    旧布局：`courses.json` 里同时放 `semesters` / `current_semester` / `courses` / `holidays`，
    `tasks.json` / `exams.json` 在 `data/` 根下。

    安全顺序：**先写新文件 → 再校验 → 最后删旧文件**（中途失败不丢数据；
    即使误删，git 历史里也有）。
    """
    if registry_path(data_dir).exists():
        return False
    parsed = _read_legacy(data_dir)
    if parsed is None:
        return False                      # 全新目录：交给 ensure_current()
    old, semesters, current = parsed

    target = _write_new_layout(data_dir, old, semesters, current)
    if not (target / "courses.json").exists():
        logger.error("迁移校验失败，保留旧文件")
        return False
    (data_dir / "courses.json").unlink()
    for name in ("tasks.json", "exams.json"):
        (data_dir / name).unlink(missing_ok=True)
    logger.info("数据已迁移到按学期布局：%s → %s", data_dir, target)
    return True
