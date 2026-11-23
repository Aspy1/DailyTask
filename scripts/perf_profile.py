"""用 cProfile 定位保存路径的耗时分布（手册 §2.2：Python CPU 高 → cProfile）。

只跑**一个**明确场景，输出累计耗时与调用次数；不记录任何用户内容。

⚠ 本文件**必须**在设好 `sys.path` 与 `QT_QPA_PLATFORM` 之后再 import 项目模块，
所以模块级 import 位置靠后 —— 这是有意为之（ruff E402 在此豁免）。
"""

# ruff: noqa: E402

import cProfile
import io
import os
import pstats
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import perf_bench as bench

from src.services.data_manager import DataManager

TIER = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
REPEAT = int(sys.argv[2]) if len(sys.argv) > 2 else 10

root = Path(tempfile.mkdtemp(prefix="perf_prof_"))
bench.write_fixture(root, TIER)
dm = DataManager(root)
counter = {"n": 0}


def workload() -> None:
    for _ in range(REPEAT):
        counter["n"] += 1
        dm.tasks.tasks[0]["title"] = f"改动 {counter['n']}"
        dm.tasks.save()


profiler = cProfile.Profile()
profiler.enable()
workload()
profiler.disable()

stream = io.StringIO()
stats = pstats.Stats(profiler, stream=stream).sort_stats("cumulative")
stats.print_stats(22)
text = stream.getvalue()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(f"=== {TIER} 条 × {REPEAT} 次保存 ===")
print(text)
