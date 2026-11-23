"""各面板**单独构造成本**分布（手册 §2.2：先定位再决定方案）。

方案 A 的对照结果是负收益，需要证据说明"延迟构建省下的到底是哪一块、有多大"，
否则无法判断是该换方案还是该放弃。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import perf_bench as bench  # noqa: E402

from src.services.data_manager import DataManager  # noqa: E402
from src.services.settings_manager import SettingsManager  # noqa: E402


class _Plugins:
    def list_plugins(self) -> list:
        return []

    def is_enabled(self, _name: str) -> bool:
        return False

    def toggle(self, _name: str, _enabled: bool) -> None:
        return None


def _timed(label: str, fn, repeat: int = 5) -> float:
    """返回中位数（ms）。"""
    sample = bench.measure(fn, label=label, repeat=repeat, warmup=1)
    return sample.median


def main() -> int:
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    root = Path(tempfile.mkdtemp(prefix="perf_cost_"))
    bench.write_fixture(root, 200)
    settings = SettingsManager(root / "settings.ini")
    settings.load()
    dm = DataManager(root)

    from src.ui.panels.exam_panel import ExamPanel
    from src.ui.panels.expense_panel import ExpensePanel
    from src.ui.panels.habit_panel import HabitPanel
    from src.ui.panels.inventory_panel import InventoryPanel
    from src.ui.panels.routine_panel import RoutinePanel
    from src.ui.panels.settings_panel import SettingsPanel
    from src.ui.panels.study_panel import StudyPanel
    from src.ui.panels.task_panel import TaskPanel
    from src.ui.widgets.schedule_view import ScheduleView

    print("— 各面板单独构造成本（中位数，ms）—")
    rows = []
    for name, factory in (
        ("ScheduleView（首屏）", lambda: ScheduleView(dm)),
        ("TaskPanel", lambda: TaskPanel(dm)),
        ("ExamPanel", lambda: ExamPanel(dm)),
        ("HabitPanel", lambda: HabitPanel(dm)),
        ("RoutinePanel", lambda: RoutinePanel(dm)),
        ("StudyPanel", lambda: StudyPanel(dm)),
        ("ExpensePanel", lambda: ExpensePanel(dm)),
        ("InventoryPanel", lambda: InventoryPanel(dm)),
        ("SettingsPanel", lambda: SettingsPanel(settings, _Plugins(), dm)),
    ):
        cost = _timed(name, factory)
        rows.append((name, cost))
        print(f"  {name:<24}{cost:8.2f}")

    total = sum(c for _n, c in rows)
    deferred = sum(c for n, c in rows if n != "ScheduleView（首屏）")
    print(f"\n  合计 {total:8.2f} ms")
    print(f"  首屏之外（可延迟）≈ {deferred:8.2f} ms"
          f"（占 {deferred / total * 100:.0f}%）")

    print("\n— 数据层单独成本 —")
    print(f"  DataManager 构造 {_timed('dm', lambda: DataManager(root)):8.2f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
