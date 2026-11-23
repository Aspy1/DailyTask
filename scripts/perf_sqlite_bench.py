"""JSON vs SQLite 性能对照（方案 C，`MD-files/PERFORMANCE_WORKFLOW.md` §3.3-2）。

同一份合成数据、同一台机器，比较五类存储操作：

    按学期列表 / 未完成筛选 / 分页 / 单条完成 / 批量导入

用法：
    .venv\\Scripts\\python.exe scripts/perf_sqlite_bench.py
    .venv\\Scripts\\python.exe scripts/perf_sqlite_bench.py --full   # 加 50k
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

from src.services import task_store_sqlite as store  # noqa: E402


def _json_tasks(root: Path, count: int) -> tuple[Path, dict]:
    """把合成作业写成 JSON（与生产同格式），返回 (路径, payload)。"""
    bench.write_fixture(root, count)
    path = root / "semesters" / "sem_perf" / "tasks.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _sqlite_db(root: Path, count: int) -> tuple[object, dict]:
    """同数据建库（建库/导入成本不在测量区内）。"""
    payload = bench.synthetic_tasks(count)
    db = store.connect(root / "tasks.db")
    store.import_tasks(db, "sem_perf", payload["tasks"])
    return db, payload


def _json_pending(payload: dict) -> list[dict]:
    return [t for t in payload["tasks"] if t.get("status") == "pending"]


def _json_page(tasks: list[dict], offset: int, limit: int) -> list[dict]:
    """JSON 侧的分页：先全排序再切片（生产中就是这样）。"""
    ordered = sorted(tasks, key=lambda t: (t.get("due_date", ""), t.get("id", "")))
    return ordered[offset:offset + limit]


def compare_tier(count: int, repeat: int) -> tuple[list[dict], dict[str, bench.Sample]]:
    cache = ROOT / ".pytest_cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="perf_sqlite_", dir=cache) as root:
        return _compare_tier(Path(root), count, repeat)


def _compare_tier(root: Path, count: int, repeat: int) -> tuple[list[dict], dict[str, bench.Sample]]:
    """同一**操作边界**下对照：两侧都必须"从磁盘取到结果"。

    ⚠ 第一版对照过一次**不公平**的版本：JSON 侧复用已解析好的内存 dict，
    而 SQLite 每次都真的查库 —— 于是"未完成筛选"量出 JSON 0.04ms vs SQLite 3.2ms
    这种荒谬数字（差了 8000%）。生产里 JSON 每次都要整份解析，必须把这一步算进去。

    返回 `(逐项对照行, 原始样本)` —— 原始样本要归档，才能复核 P95 与尾部。
    """
    path, _payload = _json_tasks(root, count)
    db, sqlite_payload = _sqlite_db(root, count)
    task_id = "t_000002"
    setups = {"单条完成": (
        lambda: _freshly_reset(path, task_id),
        lambda: _reset_sql_task(db, task_id),
    )}
    samples: dict[str, bench.Sample] = {}
    try:
        cases = (
            ("按学期列表",
             lambda: _read_json_all(path)["tasks"],
             lambda: store.list_tasks(db, "sem_perf")),
            ("未完成筛选",
             lambda: _json_pending(_read_json_all(path)),
             lambda: store.pending_tasks(db, "sem_perf")),
            ("分页 100 条",
             lambda: _json_page(_read_json_all(path)["tasks"], 200, 100),
             lambda: store.page_tasks(db, "sem_perf", offset=200, limit=100)),
            ("单条完成",
             lambda: _require_update(_json_complete_file(path, task_id)),
             lambda: _require_update(store.complete_task(
                 db, "sem_perf", task_id, COMPLETED_AT))),
            ("批量导入",
             lambda: _json_import(path),
             lambda: store.import_tasks(db, "sem_perf", sqlite_payload["tasks"])),
        )
        rows = []
        for label, json_fn, sql_fn in cases:
            json_setup, sql_setup = setups.get(label, (None, None))
            base = bench.measure(json_fn, label=f"{label}·JSON", repeat=repeat,
                                 before_each=json_setup)
            cand = bench.measure(sql_fn, label=f"{label}·SQLite", repeat=repeat,
                                 before_each=sql_setup)
            if base.failures or cand.failures:
                raise RuntimeError(f"Invalid storage benchmark samples: {label}")
            samples[f"{count}/{label}·JSON"] = base
            samples[f"{count}/{label}·SQLite"] = cand
            rows.append(bench.compare(base, cand))
        return rows, samples
    finally:
        db.close()


def _read_json_all(path: Path) -> dict:
    """JSON 侧的真实读取：**整份解析**（生产里每次 load 都这样）。"""
    return json.loads(path.read_text(encoding="utf-8"))


def _freshly_reset(path: Path, task_id: str) -> str:
    """测量前把那条作业**改回 pending**，否则第二次起就是 no-op（会低估成本）。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    for task in payload["tasks"]:
        if task["id"] == task_id:
            task["status"] = "pending"
            task["completed_at"] = None
            break
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return task_id


COMPLETED_AT = "2026-06-01T10:00:00"


def _reset_sql_task(db, task_id: str) -> None:
    with store.transaction(db) as tx:
        cursor = tx.execute(
            "UPDATE tasks SET status = 'pending', completed_at = NULL "
            "WHERE semester_id = ? AND task_id = ?", ("sem_perf", task_id))
        _require_update(cursor.rowcount == 1)


def _require_update(updated: bool) -> None:
    if not updated:
        raise RuntimeError("Completion benchmark did not update a task")


def _json_complete_file(path: Path, task_id: str) -> bool:
    """JSON 侧的单条完成：读整份 → 改一条 → 整份写回（这就是它的真实成本）。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    hit = False
    for task in payload["tasks"]:
        if task["id"] == task_id and task.get("status") != "completed":
            task["status"] = "completed"
            task["completed_at"] = COMPLETED_AT
            hit = True
            break
    if hit:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return hit


def _json_import(path: Path) -> int:
    """JSON 侧"导入"= 整份序列化写盘（这就是它保存一条的成本）。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(payload["tasks"])


def run(tiers: tuple[int, ...], json_out: Path | None = None) -> dict:
    print("— 环境 —")
    profile = bench.machine_profile()
    profile["commit"] = bench.git_commit()
    for key in ("commit", "platform", "python", "qt", "cpu_count"):
        print(f"  {key}: {profile.get(key)}")

    payload: dict = {"environment": profile, "tiers": {}}
    samples: dict[str, bench.Sample] = {}
    for tier in tiers:
        print(f"\n— 数据档 {tier:,} 条 —")
        rows, raw = compare_tier(tier, 20 if tier >= 50_000 else 50)
        payload["tiers"][str(tier)] = rows
        samples.update(raw)
        for row in rows:
            b, c = row["baseline"], row["candidate"]
            print(f"  {row['label']:<20} JSON {b['median_ms']:8.2f} ms   "
                  f"SQLite {c['median_ms']:8.2f} ms   "
                  f"改善 {row['median_improvement_pct']:+7.1f}%   "
                  f"P95 {row['p95_improvement_pct']:+7.1f}%")

    archived = bench.archive("sqlite-comparison", payload, samples=samples)
    print(f"\n已归档 {archived}")
    print(f"已刷新清单 {bench.write_manifest()}")
    if json_out is not None:
        json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"已写入 {json_out}")
    return payload


def main() -> int:
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    tiers = bench.DATA_TIERS if args.full else bench.DATA_TIERS[:2]
    run(tiers, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
