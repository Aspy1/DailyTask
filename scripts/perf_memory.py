"""进程树内存测量（`MD-files/PERFORMANCE_WORKFLOW.md` §2.2 / §3.4 要求）。

手册明确：*"Qt 或 Chromium 的原生内存需使用系统指标，`tracemalloc` 只用于 Python 分配。
记录内存口径，例如进程树私有提交量，避免把共享页的工作集重复相加。"*

所以这里用 **Windows 作业对象 / 进程计数器** 取：
- 进程树**私有提交量**（Private Commit，`PrivateUsage`）：不重复计算共享页；
- Python 侧 `tracemalloc` 峰值单独记，用于定位"是不是 Python 对象泄漏"；
- 子进程数（WebEngine 会带渲染子进程）。

用法：
    .venv\\Scripts\\python.exe scripts/perf_memory.py
    .venv\\Scripts\\python.exe scripts/perf_memory.py --json out.json
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tempfile
import tracemalloc
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_bench import Sample

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def _private_commit(pid: int) -> int | None:
    """进程的**私有提交量**（字节）；打不开（权限 / 已退出）→ None。"""
    handle = _kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    try:
        counters = _PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        ok = _psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), ctypes.sizeof(counters))
        return int(counters.PrivateUsage) if ok else None
    finally:
        _kernel32.CloseHandle(handle)


def _children(pid: int) -> list[int]:
    """子进程 pid（用 `wmic` 的继任者 `Get-CimInstance` 太重 → 走 `tasklist` 不可靠；
    这里用 Win32 Toolhelp 快照，零依赖）。"""
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260),
        ]

    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, -1):
        return []
    found: list[int] = []
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if _kernel32.Process32First(snapshot, ctypes.byref(entry)):
            while True:
                if entry.th32ParentProcessID == pid:
                    found.append(int(entry.th32ProcessID))
                if not _kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                    break
    finally:
        _kernel32.CloseHandle(snapshot)
    return found


def tree_private_commit(pid: int | None = None) -> dict:
    """整棵进程树的私有提交量（**不重复计算共享页**）。"""
    root = os.getpid() if pid is None else pid
    pids = [root, *_children(root)]
    per = {p: _private_commit(p) for p in pids}
    total = sum(v or 0 for v in per.values())
    return {"root_pid": root, "processes": len(pids),
            "private_commit_mb": round(total / 1024 / 1024, 1),
            "per_process_mb": {str(p): round((v or 0) / 1024 / 1024, 1)
                               for p, v in per.items()}}


def _workspace() -> tuple[object, Path]:
    """构造一个工作区（与 perf_panel_bench 同口径）。"""
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.components.main_workspace import MainWorkspace

    class _Plugins:
        def list_plugins(self) -> list:
            return []

        def is_enabled(self, _name: str) -> bool:
            return False

        def toggle(self, _name: str, _enabled: bool) -> None:
            return None

    root = Path(tempfile.mkdtemp(prefix="perf_mem_"))
    benchmark_dir = Path(tempfile.mkdtemp(prefix="perf_mem_data_"))
    import perf_bench as bench

    bench.write_fixture(benchmark_dir, 200)
    settings = SettingsManager(benchmark_dir / "settings.ini")
    settings.load()
    dm = DataManager(benchmark_dir)
    return MainWorkspace(settings, dm, _Plugins()), root


def measure_workspace_memory(lazy: bool, rounds: int = 5, *,
                             force_build: bool = False) -> tuple[dict, Sample]:
    """两种模式下：稳态私有提交量 + Python 峰值 → `(汇总, 逐轮样本)`。

    `force_build=True` → 构造后**把每个面板都建出来**（模拟"用户逐页浏览过"）。
    这样才可比：延迟模式在"没人点过"时当然更省，但那不是稳态。

    ⚠ 返回**逐轮样本**（每建一个工作区记一次私有提交量）而不只是最后那个数：
    手册 §5 要求"保留原始样本"，只交汇总无法复核离散程度。
    """
    from src.ui.components import panel_factory

    panel_factory.LAZY_PANELS = lazy
    tracemalloc.start()
    workspaces = []
    sample = Sample(label=f"内存·{'延迟' if lazy else '全构造'}"
                          f"·{'稳态' if force_build else '起点'}")
    for _ in range(rounds):
        ws, _root = _workspace()
        if force_build:
            for key in ("tasks", "exams", "daily", "routines",
                        "study", "expenses", "inventory"):
                ws.switch_to(key)
        workspaces.append(ws)
        # 每轮记一次：私有提交量（MiB）—— 逐轮样本才有"离群值"可看
        sample.durations_ms.append(tree_private_commit()["private_commit_mb"])
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    info = tree_private_commit()
    info.update({"lazy": lazy, "rounds": rounds, "forced": force_build,
                 "python_current_mb": round(current / 1024 / 1024, 2),
                 "python_peak_mb": round(peak / 1024 / 1024, 2),
                 "snapshots": len(workspaces)})
    del workspaces
    return info, sample


def _run_isolated(lazy: bool, force_build: bool, rounds: int) -> dict:
    """在**全新子进程**里测一次（同一进程内连跑两种模式会互相污染：Qt 对象回收不及时、
    allocator 复用 → 后跑的那次永远更高，实测见过 +20~+33 MiB 的假差异）。

    返回值里带 `per_round_mb`（逐轮私有提交量）—— 跨进程只能传纯数据，
    回到主进程后再包成 `Sample` 归档。
    """
    import subprocess

    code = (
        "import json, sys;"
        f"sys.path.insert(0, {str(ROOT)!r});"
        f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
        "import perf_memory as m;"
        "from PySide6.QtWidgets import QApplication;"
        "_a = QApplication.instance() or QApplication([]);"
        f"info, sample = m.measure_workspace_memory(lazy={lazy!r}, rounds={rounds},"
        f"                                          force_build={force_build!r});"
        "info['per_round_mb'] = list(sample.durations_ms);"
        "print('RESULT' + json.dumps(info, ensure_ascii=False))"
    )
    env = {**os.environ, "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen")}
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,  # noqa: S603
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=300)
    for line in (proc.stdout or "").splitlines():
        if line.startswith("RESULT"):
            return json.loads(line[len("RESULT"):])
    raise RuntimeError(f"子进程没给出结果：{proc.stdout[-400:]} {proc.stderr[-400:]}")


def _as_sample(info: dict, label: str) -> Sample:
    """把跨进程取回的纯数据包成 `Sample`（归档时要逐次耗时）。"""
    sample = Sample(label=label)
    sample.durations_ms = list(info.get("per_round_mb") or [])
    return sample


def main() -> int:
    import perf_bench as bench
    from PySide6.QtWidgets import QApplication

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _app = QApplication.instance() or QApplication([])

    print("— 进程树内存（私有提交量口径，不重复计算共享页）—")
    print("  每次测量都在**全新子进程**里跑（同进程连跑两种模式会互相污染）")

    print("\n[1] 稳态：构造后把全部面板都建出来（用户逐页看过一遍）")
    eager = _run_isolated(lazy=False, force_build=True, rounds=5)
    lazy = _run_isolated(lazy=True, force_build=True, rounds=5)
    for name, data in (("全构造", eager), ("首屏延迟", lazy)):
        print(f"  {name}: 私有提交 {data['private_commit_mb']} MiB | "
              f"Python 峰值 {data['python_peak_mb']} MiB")
    steady_delta = round(lazy["private_commit_mb"] - eager["private_commit_mb"], 1)
    print(f"  稳态差异：{steady_delta:+.1f} MiB（预期 ≈0：最终都持有同样的 8 个面板）")

    print("\n[2] 起点：构造后**不点任何页**")
    eager_idle = _run_isolated(lazy=False, force_build=False, rounds=5)
    lazy_idle = _run_isolated(lazy=True, force_build=False, rounds=5)
    for name, data in (("全构造", eager_idle), ("首屏延迟", lazy_idle)):
        print(f"  {name}: 私有提交 {data['private_commit_mb']} MiB | "
              f"Python 峰值 {data['python_peak_mb']} MiB")
    idle_delta = round(lazy_idle["private_commit_mb"] - eager_idle["private_commit_mb"], 1)
    print(f"  起点差异：{idle_delta:+.1f} MiB")

    payload = {"steady": {"eager": eager, "lazy": lazy, "delta_mb": steady_delta},
               "idle": {"eager": eager_idle, "lazy": lazy_idle, "delta_mb": idle_delta}}
    samples = {
        "稳态·全构造": _as_sample(eager, "稳态·全构造"),
        "稳态·首屏延迟": _as_sample(lazy, "稳态·首屏延迟"),
        "起点·全构造": _as_sample(eager_idle, "起点·全构造"),
        "起点·首屏延迟": _as_sample(lazy_idle, "起点·首屏延迟"),
    }
    archived = bench.archive("memory-panels", payload, samples=samples)
    print(f"\n已归档 {archived}")
    print(f"已刷新清单 {bench.write_manifest()}")
    out = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else None
    if out is not None:
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    ap.parse_args()
    sys.exit(main())
