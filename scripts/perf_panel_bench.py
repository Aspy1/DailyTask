"""方案 A 的对照测量（`MD-files/PERFORMANCE_WORKFLOW.md` §3.4 决策记录用）。

**同一轮、同一数据档、同一脚本**交替跑两种模式：
`LAZY_PANELS=0`（改造前：全构造）vs `LAZY_PANELS=1`（首屏延迟构建）。

用法：
    .venv\\Scripts\\python.exe scripts/perf_panel_bench.py
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
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import perf_bench as bench  # noqa: E402

from src.services.data_manager import DataManager  # noqa: E402
from src.services.settings_manager import SettingsManager  # noqa: E402


class _Plugins:
    """插件管理器替身（真实实现会扫目录并加载插件代码）。"""

    def list_plugins(self) -> list:
        return []

    def is_enabled(self, _name: str) -> bool:
        return False

    def toggle(self, _name: str, _enabled: bool) -> None:
        return None


def _prepare(tier: int = 200) -> tuple[object, DataManager]:
    """**计时区之外**的准备：合成数据 + 数据层。返回 (settings, dm)。

    ⚠ 手册 §1.3 要求"定义操作起止点"：数据落盘与 `DataManager` 初始化是**场景前置**，
    不能算进"工作区构造"里 —— 否则磁盘 I/O 会把面板构造的差异整块盖掉
    （第一版就踩了这个坑：量出来两种模式都 ~104 ms，看不出任何差别）。

    `tier` 只影响 `DataManager` 的载入成本（面板构造本身与条数无关）——
    带上它是为了满足手册 §1.2「三档都要测」的要求，能直接看出这个结论。
    """
    root = Path(tempfile.mkdtemp(prefix=f"perf_panel_{tier}_"))
    bench.write_fixture(root, tier)
    settings = SettingsManager(root / "settings.ini")
    settings.load()
    return settings, DataManager(root)


def _build_workspace(lazy: bool, prepared: tuple[object, DataManager] | None = None) -> object:
    """按模式构造一个工作区（**只构造工作区**，数据层由调用方备好）。"""
    from src.ui.components import panel_factory
    from src.ui.components.main_workspace import MainWorkspace

    panel_factory.LAZY_PANELS = lazy
    settings, dm = prepared if prepared is not None else _prepare()
    return MainWorkspace(settings, dm, _Plugins())


def measure_build(lazy: bool, repeat: int, tier: int = 200) -> bench.Sample:
    """冷构造一个 `MainWorkspace`（首屏之外的面板是否构造）。"""
    label = "工作区构造·全构造" if not lazy else "工作区构造·首屏延迟"
    prepared = _prepare(tier)
    return bench.measure(lambda: _build_workspace(lazy, prepared), label=label,
                         repeat=repeat, warmup=2)


def measure_first_task_switch(lazy: bool, repeat: int, tier: int = 200) -> bench.Sample:
    """首次切到作业面板（延迟模式下这一刀包含构造成本）。"""
    label = "首次切作业·全构造" if not lazy else "首次切作业·延迟模式"
    prepared = _prepare(tier)

    def once() -> None:
        ws = _build_workspace(lazy, prepared)
        ws.switch_to("tasks")

    return bench.measure(once, label=label, repeat=repeat, warmup=2)


def measure_repeat_switch(lazy: bool, repeat: int, tier: int = 200) -> bench.Sample:
    """已打开过作业页后的**重复**切页（不该有构造成本）。"""
    prepared = _prepare(tier)
    ws = _build_workspace(lazy, prepared)
    ws.switch_to("tasks")
    label = "重复切作业·全构造" if not lazy else "重复切作业·延迟模式"
    return bench.measure(lambda: ws.switch_to("tasks"), label=label,
                         repeat=repeat, warmup=3)


def measure_all_panels(lazy: bool, repeat: int, tier: int = 200) -> bench.Sample:
    """把 10 个导航项全切一遍（用户真的逐页浏览）。"""
    keys = ("schedule", "tasks", "exams", "daily", "routines",
            "study", "expenses", "inventory", "meals", "settings")
    label = "全页切换·全构造" if not lazy else "全页切换·延迟模式"
    prepared = _prepare(tier)

    def once() -> None:
        ws = _build_workspace(lazy, prepared)
        for key in keys:
            ws.switch_to(key)

    return bench.measure(once, label=label, repeat=repeat, warmup=2)


SCENARIOS = (
    (measure_build, 50),
    (measure_first_task_switch, 50),
    (measure_repeat_switch, 100),
    (measure_all_panels, 50),
)


def run(json_out: Path | None = None, tiers: tuple[int, ...] = (200,)) -> dict:
    """按数据档跑全部场景（手册 §1.2：三档都要测）。

    ⚠ 面板构造本身与条数无关，真正随条数变的是 `DataManager` 载入 ——
    所以这里把**构造**与**载入**分开报，让"50k 档没测"这个疑问直接消失。
    """
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    print("— 环境 —")
    profile = bench.machine_profile()
    profile["commit"] = bench.git_commit()
    for key in ("commit", "platform", "python", "qt", "cpu_count"):
        print(f"  {key}: {profile.get(key)}")

    payload: dict = {"environment": profile, "tiers": {}}
    samples: dict[str, bench.Sample] = {}
    for tier in tiers:
        print(f"\n═══ 数据档 {tier:,} 条 ═══")
        rows = []
        for fn, repeat in SCENARIOS:
            base = fn(False, repeat, tier)
            cand = fn(True, repeat, tier)
            row = bench.compare(base, cand)
            rows.append(row)
            samples[f"{tier}/{row['label']}·全构造"] = base
            samples[f"{tier}/{row['label']}·首屏延迟"] = cand
            print(f"\n  {row['label']}")
            print(f"    基线 中位 {base.median:8.2f} ms  P95 {base.p95:8.2f} ms  "
                  f"最大 {base.worst:8.2f} ms  失败 {base.failures}")
            print(f"    候选 中位 {cand.median:8.2f} ms  P95 {cand.p95:8.2f} ms  "
                  f"最大 {cand.worst:8.2f} ms  失败 {cand.failures}")
            print(f"    改善 中位 {row['median_improvement_pct']:+.1f}%  "
                  f"P95 {row['p95_improvement_pct']:+.1f}%")
        payload["tiers"][str(tier)] = rows

    archived = bench.archive("panel-lazy-construction", payload, samples=samples)
    print(f"\n已归档 {archived}")
    print(f"已刷新清单 {bench.write_manifest()}")
    if json_out is not None:
        json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"已写入 {json_out}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--full", action="store_true", help="加 10k / 50k 档（手册 §1.2）")
    args = ap.parse_args()
    tiers = bench.DATA_TIERS if args.full else (200,)
    run(args.json, tiers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
