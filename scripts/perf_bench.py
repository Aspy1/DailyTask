"""性能测量设施（`MD-files/PERFORMANCE_WORKFLOW.md` §1-2 的落点，PLAN I-15 的前置）。

**为什么单独成模块**：手册要求"同一轮固定条件、交替跑基线与候选、保留原始样本"，
而一次性脚本做不到这三点。这里给出可复用的三件事：

1. `synthetic_data(n)` —— 固定数据档（1k / 10k / 50k），含手册要求的边界样本
   （空学期、长备注、重复课程名、大批已完成、历史数据）；
2. `measure(fn, repeat)` —— 单调时钟取样，返回中位数 / P95 / 最大 / 失败数；
3. `report(...)` —— 同一场景下基线与候选并排输出（**同一口径、同一样本量**）。

**只存测量口径，不存用户内容**（手册 §2.2 的注意事项）：样本里只留
操作类型、耗时、数量、版本与错误类别。
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# 手册 §1.2 的三档数据量（单文件 5 万条用于压力测试）
DATA_TIERS = (1_000, 10_000, 50_000)

# 原始样本的**归档目录**（手册 §5："保留原始样本"，报告里的每个数字都要能追到文件）
ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "dev-logs" / "perf-data"


@dataclass
class Sample:
    """一次测量的一组样本（**同一口径**：同样的场景、同样的数据档）。"""

    label: str
    durations_ms: list[float] = field(default_factory=list)
    failures: int = 0

    @property
    def n(self) -> int:
        return len(self.durations_ms)

    @property
    def median(self) -> float:
        return statistics.median(self.durations_ms) if self.durations_ms else 0.0

    @property
    def p95(self) -> float:
        """P95（小样本时取最近秩，不插值 —— 与手册"逐笔检查尾部"一致）。"""
        if not self.durations_ms:
            return 0.0
        ordered = sorted(self.durations_ms)
        index = min(len(ordered) - 1, max(0, round(0.95 * (len(ordered) - 1))))
        return ordered[index]

    @property
    def worst(self) -> float:
        return max(self.durations_ms) if self.durations_ms else 0.0

    def as_row(self) -> dict:
        return {"label": self.label, "n": self.n, "median_ms": round(self.median, 2),
                "p95_ms": round(self.p95, 2), "max_ms": round(self.worst, 2),
                "failures": self.failures}


def measure(fn: Callable[[], object], *, label: str, repeat: int = 50,
            warmup: int = 5, before_each: Callable[[], object] | None = None) -> Sample:
    """用 `perf_counter_ns()` 计时（手册 §2.1：单调时钟，入口到完成）。

    `warmup` 不计入样本：手册要求"先做 5 次试跑检查计时是否完整"。
    """
    prepare = before_each or (lambda: None)
    for _ in range(warmup):
        prepare()
        try:
            fn()
        except Exception:      # noqa: BLE001 — 预热失败不算样本，正式跑会记失败数
            break
    sample = Sample(label=label)
    for _ in range(repeat):
        prepare()
        started = time.perf_counter_ns()
        try:
            fn()
        except Exception:      # noqa: BLE001 — 失败计入 failures，不中断整轮
            sample.failures += 1
            continue
        sample.durations_ms.append((time.perf_counter_ns() - started) / 1e6)
    return sample


def machine_profile() -> dict:
    """环境指纹（手册 §1.1）：提交号、Windows、Python、Qt、CPU 架构、DPI。"""
    profile = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "cpu_count": __import__("os").cpu_count(),
    }
    try:
        import PySide6
        from PySide6.QtCore import qVersion

        profile["pyside6"] = PySide6.__version__
        profile["qt"] = qVersion()
    except Exception:          # noqa: BLE001 — 无 Qt 环境时只记 Python 指标
        profile["qt"] = "unavailable"
    return profile


def git_commit() -> str:
    """当前提交号（基线/候选各记一份，手册 §5 的对照要求）。"""
    import subprocess

    try:
        # 参数写死，无外部输入（S603/S607 不适用）
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ── 合成数据工厂（手册 §1.2）───────────────────────────────

def synthetic_tasks(count: int) -> dict:
    """`count` 条作业：含手册要求的边界样本。

    - 1/3 已完成（大批已完成任务）
    - 1/5 带长备注（长备注）
    - 重复课程名（同一门课的多次作业）
    - 历史数据（往期截止日）与跨学期混合
    """
    tasks = []
    courses = ["高等数学", "数据结构", "操作系统", "计算机网络", "算法设计"]
    for i in range(1, count + 1):
        course = courses[i % len(courses)]                 # 重复课程名
        completed = i % 3 == 0                             # 大批已完成
        day = 1 + (i % 28)
        month = 1 + (i % 12)
        tasks.append({
            "id": f"t_{i:06d}",
            "title": f"作业 {i}",
            "course_name": course,
            "due_date": f"20{20 + i % 6:02d}-{month:02d}-{day:02d}T23:59:00",
            "status": "completed" if completed else "pending",
            "priority": "medium",
            "tags": [course],
            "notes": ("长备注 " * 200) if i % 5 == 0 else "",
            "attachments": [],
            "reminded": False,
            "created_at": f"2026-01-{day:02d}T08:00:00",
            "completed_at": f"2026-02-{day:02d}T09:00:00" if completed else None,
        })
    return {"_version": 2, "tasks": tasks, "archived": []}


def synthetic_courses(count: int = 30) -> dict:
    """课程表：`count` 门课，覆盖 5 天 × 若干节次（周视图压力）。"""
    courses = []
    for i in range(1, count + 1):
        slot = 1 + (i % 5)
        courses.append({
            "id": f"c_{i:03d}",
            "name": f"课程 {i}",
            "teacher": f"老师 {i}",
            "day_of_week": 1 + (i % 7),
            "weeks": {"start": 1, "end": 16},
            "week_parity": "all",
            "time_slots": [{"start": slot, "end": slot, "location": f"A{100 + i}"}],
            "excluded_weeks": [],
            "reminders": {"attendance": False, "lead_minutes": 30},
        })
    return {"_version": 1, "courses": courses,
            "holidays": {"excluded": [], "makeup": {}}}


def write_fixture(root: Path, count: int, *, semester: str = "sem_perf") -> Path:
    """把合成数据写进隔离目录（**绝不碰真实 `data/`**）。"""
    root.mkdir(parents=True, exist_ok=True)
    registry = {"_version": 1, "semesters": [
        {"id": semester, "name": "性能测试学期", "start_date": "2026-09-21",
         "total_weeks": 16, "period_count": 6, "exam_weeks": 1}],
        "current_semester": semester}
    _dump(root / "semesters.json", registry)
    folder = root / "semesters" / semester
    _dump(folder / "tasks.json", synthetic_tasks(count))
    _dump(folder / "courses.json", synthetic_courses())
    _dump(folder / "exams.json", {"_version": 1, "exams": []})
    for name, payload in (
        ("habits.json", {"_version": 2, "habits": [], "logs": {}}),
        ("routines.json", {"_version": 1, "items": [], "logs": {}}),
        ("expenses.json", {"_version": 1, "categories": [],
                           "budget": {"monthly": 0, "by_category": {}},
                           "records": [], "finance": {}}),
        ("daily_logs.json", {"_version": 4, "logs": {}, "plans": {},
                             "savings": {}, "reminders": []}),
        ("inventory.json", {"_version": 1, "items": [], "categories": [],
                            "locations": []}),
        ("study.json", {"_version": 1, "sessions": [], "mistakes": [],
                        "mocks": [], "subjects": []}),
    ):
        _dump(root / name, payload)
    return root


def _dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fixture_bytes(root: Path) -> int:
    """这档数据的实际字节数（手册 §1.2 要求"记录实际字节数"）。"""
    return sum(f.stat().st_size for f in root.rglob("*.json") if f.is_file())


# ── 报告 ────────────────────────────────────────────────────

def compare(base: Sample, cand: Sample, *, unit: str = "ms") -> dict:
    """基线与候选并排 → 改善百分比（**负数表示变慢**）。"""
    def delta(before: float, after: float) -> float:
        return round((before - after) / before * 100, 1) if before else 0.0

    return {
        "label": base.label,
        "unit": unit,
        "baseline": base.as_row(),
        "candidate": cand.as_row(),
        "median_improvement_pct": delta(base.median, cand.median),
        "p95_improvement_pct": delta(base.p95, cand.p95),
    }


def format_table(rows: list[dict]) -> str:
    """纯文本表（`dev-logs/` 报告直接贴）—— 不写 Markdown，避免与文档规范混杂。"""
    lines = [f"{'场景':<40}{'基线中位':>10}{'候选中位':>10}{'改善':>8}"]
    for row in rows:
        lines.append(f"{row['label']:<40}{row['baseline']['median_ms']:>10.2f}"
                     f"{row['candidate']['median_ms']:>10.2f}"
                     f"{row['median_improvement_pct']:>7.1f}%")
    return "\n".join(lines)


# ── 原始样本归档（手册 §5：「保留原始样本」）─────────────────
#
# 只存汇总（中位/P95）不够复核：P95 的秩、最大值、失败分布都在**原始样本**里。
# 所以每次跑基准都落一份完整 JSON（每个样本的逐次耗时 + 环境指纹 + 提交号），
# 报告里引用的数字必须能在这个目录里找到对应文件。

def archive(name: str, payload: dict, *, samples: dict[str, Sample] | None = None) -> Path:
    """把一次基准的**完整结果**写进 `dev-logs/perf-data/<name>.json`。

    `samples` 里的逐次耗时也一并落盘 —— 这是"逐笔检查尾部"（手册 §2.1）的依据。
    """
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    target = ARTIFACT_DIR / f"{name}.json"
    document = {
        "_note": "性能基准原始输出（scripts/perf_bench.py archive）。"
                 "含逐次样本，供复核中位/P95/尾部。",
        "environment": {**machine_profile(), "commit": git_commit()},
        "results": payload,
    }
    if samples:
        document["raw_samples"] = {
            label: {"n": s.n, "failures": s.failures,
                    "durations_ms": [round(value, 3) for value in s.durations_ms]}
            for label, s in samples.items()
        }
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="")
    return target


def write_manifest() -> Path:
    """`perf-data/INDEX.md`：这个目录里每份产物的用途（免得变成无人认领的 json）。"""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(ARTIFACT_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows.append(f"| {path.name} | （无法解析） | — |")
            continue
        env = doc.get("environment") or {}
        note = str(doc.get("_note") or "").split("。")[0]
        rows.append(f"| `{path.name}` | {note} | {env.get('commit', '?')} |")
    text = "\n".join([
        "# perf-data — 性能基准原始输出",
        "",
        "由 `scripts/perf_bench.py` 的 `archive()` 写入；报告"
        "`dev-logs/2026-11-23-性能改造对比报告.md` 引用这里的数字。",
        "**不要手工编辑**：改测量就重跑对应脚本。",
        "",
        "| 文件 | 内容 | 提交 |",
        "|---|---|---|",
        *rows,
        "",
    ])
    target = ARTIFACT_DIR / "INDEX.md"
    target.write_text(text, encoding="utf-8", newline="")
    return target
