"""性能基线测量（`MD-files/PERFORMANCE_WORKFLOW.md` §1-2）。

测三类场景，**同一轮同一口径**：

| 场景 | 起点 | 终点 |
|---|---|---|
| 启动 | 构造 `DataManager` | 首个面板可用 |
| 切页/换周 | 调用 `switch_to` / `_refresh` | 数据可见 |
| 作业操作 | 提交勾选 | 提交确认（落盘） |

用法：
    .venv\\Scripts\\python.exe scripts/perf_baseline.py            # 默认 1k/10k
    .venv\\Scripts\\python.exe scripts/perf_baseline.py --full     # 加 50k（压力档）
    .venv\\Scripts\\python.exe scripts/perf_baseline.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import perf_bench as bench  # noqa: E402  同目录脚本

from src.services.data_manager import DataManager  # noqa: E402


def _fresh_fixture(tier: int) -> tuple[Path, int]:
    """在临时目录生成一档数据 → (目录, 字节数)。"""
    root = Path(tempfile.mkdtemp(prefix=f"perf_{tier}_"))
    bench.write_fixture(root, tier)
    return root, bench.fixture_bytes(root)


def measure_startup(tier: int, repeat: int) -> bench.Sample:
    """冷进程内的"构造 DataManager → 模型可读"（不启动整个 App，见报告说明）。"""
    fixture, _size = _fresh_fixture(tier)

    def once() -> None:
        dm = DataManager(fixture)
        # 触达一次真实读取路径（手册：终点是"数据可见"）
        _ = len(dm.tasks.tasks)

    return bench.measure(once, label=f"启动·载入 {tier} 条", repeat=repeat, warmup=3)


def measure_task_filter(tier: int, repeat: int) -> bench.Sample:
    """作业面板的**数据筛选 + 分页切片**（不含 Qt 控件构建）。"""
    fixture, _size = _fresh_fixture(tier)
    dm = DataManager(fixture)

    def once() -> None:
        pending = dm.tasks.pending
        # 面板 `_get_filtered` 的核心：按状态过滤 + 分页切片
        page = pending[:100]
        assert len(page) <= 100

    return bench.measure(once, label=f"作业筛选·{tier} 条", repeat=repeat)


def measure_save(tier: int, repeat: int) -> bench.Sample:
    """单条作业的**保存**（整份 JSON 写盘，手册 §1 的"已有合成单文件保存基线"）。"""
    fixture, _size = _fresh_fixture(tier)
    dm = DataManager(fixture)
    counter = {"n": 0}

    def once() -> None:
        counter["n"] += 1
        dm.tasks.tasks[0]["title"] = f"改动 {counter['n']}"
        assert dm.tasks.save() is True

    return bench.measure(once, label=f"作业保存·{tier} 条", repeat=repeat)


def measure_schedule_refresh(tier: int, repeat: int) -> bench.Sample:
    """日程日视图的数据构建（时段归类 + 指纹），不含控件重建。"""
    from src.models.course import schedule_date

    fixture, _size = _fresh_fixture(tier)
    dm = DataManager(fixture)
    target = schedule_date()
    today = target.isoformat()

    def once() -> None:
        courses = dm.courses.get_courses_for_date(target)
        plans = dm.daily_logs.get_plans(today)
        _ = [c for c in courses if c]
        _ = [p for p in plans if p]
        _ = dm.habits.habits

    return bench.measure(once, label=f"日程取数·{tier} 条", repeat=repeat)


SCENARIOS = (
    ("启动", measure_startup, 20),
    ("作业筛选", measure_task_filter, 50),
    ("作业保存", measure_save, 50),
    ("日程取数", measure_schedule_refresh, 50),
)


def run(tiers: tuple[int, ...], *, json_out: Path | None = None) -> dict:
    print("— 环境 —")
    profile = bench.machine_profile()
    profile["commit"] = bench.git_commit()
    for key, value in profile.items():
        print(f"  {key}: {value}")

    payload: dict = {"environment": profile, "tiers": {}}
    samples: dict[str, bench.Sample] = {}
    for tier in tiers:
        _fixture, size = _fresh_fixture(tier)
        payload.setdefault("tier_bytes", {})[str(tier)] = size
        print(f"\n— 数据档 {tier:,} 条（{size / 1024 / 1024:.2f} MiB）—")
        rows = []
        for name, fn, repeat in SCENARIOS:
            sample = fn(tier, repeat)
            rows.append((name, sample))
            samples[f"{tier}/{sample.label}"] = sample
            print(f"  {sample.label:<28} 中位 {sample.median:8.2f} ms  "
                  f"P95 {sample.p95:8.2f} ms  最大 {sample.worst:8.2f} ms  "
                  f"失败 {sample.failures}")
        payload["tiers"][str(tier)] = {name: s.as_row() for name, s in rows}

    archived = bench.archive("baseline-scenarios", payload, samples=samples)
    print(f"\n已归档 {archived}")
    print(f"已刷新清单 {bench.write_manifest()}")
    if json_out is not None:
        json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"已写入 {json_out}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="加 50k 压力档")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    tiers = bench.DATA_TIERS if args.full else bench.DATA_TIERS[:2]
    run(tiers, json_out=args.json)
    return 0


def _main_with_qt() -> int:
    """需要 Qt 的场景先建 QApplication（离屏）。"""
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    return main()


if __name__ == "__main__":
    sys.exit(_main_with_qt())
