"""P1：轮询不能漏掉**亚秒级**内容更新（审计 2026-11-21）。

审计原文：*"轮询也漏掉了 mtime 只改变 50 毫秒的内容更新"*。
旧实现 `abs(st_mtime - last) > 0.1` —— 两个 float 秒相减，再套 0.1s 阈值，
同一秒内的外部写入（脚本 / skill / 另一个实例）**整个漏掉**，界面一直显示旧数据。

改为 `st_mtime_ns`（整数纳秒）+ **存在状态**探针：
缺失也算一种状态（0），删除/重建不会再因为"没有 mtime"被吞掉。
"""

import json
import os

from src.models.task import TaskModel
from src.services.data_manager import DataManager


def _write(path, titles: list[str]) -> None:
    payload = {"_version": 2,
               "tasks": [{"id": f"t_{i:03d}", "title": t, "status": "pending"}
                         for i, t in enumerate(titles, 1)],
               "archived": []}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _touch_after(path, titles: list[str], delta: float) -> None:
    """写入，然后把 mtime 设成**「当前探针 + delta」**（确定性，不依赖真实时钟）。

    不 `sleep`：判据是"纳秒不同就重载"，不该因为机器快慢偶发通过/失败。
    """
    dm_mtime = path.stat().st_mtime_ns if path.exists() else 0
    _write(path, titles)
    stamp = dm_mtime + int(delta * 1e9)
    os.utime(path, ns=(stamp, stamp))


def test_same_second_write_is_detected(qapp, tmp_path) -> None:
    """⭐ 50ms 后的外部写入必须被检出（旧阈值 0.1s 会漏）。

    用 `os.utime` **显式**设 mtime 而不是 `sleep`：判据是"纳秒不同就重载"，
    不该因为机器快慢而偶发通过/偶发失败。
    """
    dm = DataManager(tmp_path)
    _write(dm.tasks.file_path, ["初始"])
    dm.reload_all()
    _touch_after(dm.tasks.file_path, ["初始", "外部加的"], 0.05)

    dm._auto_reload()

    assert [t["title"] for t in dm.tasks.tasks] == ["初始", "外部加的"], \
        "同秒内的写入被漏掉了"


def test_probe_uses_nanosecond_precision(qapp, tmp_path) -> None:
    """探针必须是 `st_mtime_ns`（整数纳秒），不是 float 秒。"""
    dm = DataManager(tmp_path)

    value = dm._file_mtimes["tasks"]

    assert isinstance(value, int) and value > 10**15, f"不是纳秒时间戳：{value!r}"


def test_deliberate_same_size_rewrite_is_seen(qapp, tmp_path) -> None:
    """内容长度不变、只改内容：mtime 变了就必须重载（不能按大小判）。"""
    dm = DataManager(tmp_path)
    _write(dm.tasks.file_path, ["AAAA"])
    dm.reload_all()

    _touch_after(dm.tasks.file_path, ["BBBB"], 0.02)
    dm._auto_reload()

    assert [t["title"] for t in dm.tasks.tasks] == ["BBBB"]


def test_delete_then_recreate_is_detected(qapp, tmp_path) -> None:
    """⭐ 删除 → 重建：缺失期间探针记 0，重建后再比必须仍然不等。"""
    dm = DataManager(tmp_path)
    _write(dm.tasks.file_path, ["原始"])
    dm.reload_all()

    dm.tasks.file_path.unlink()
    dm._auto_reload()
    _write(dm.tasks.file_path, ["重建的"])
    dm._auto_reload()

    assert [t["title"] for t in dm.tasks.tasks] == ["重建的"], \
        "删除重建被当成'没变化'"


def test_missing_file_does_not_emit_spurious_changes(qapp, tmp_path) -> None:
    """文件一直缺失：不能每一轮都当成"有变化"（否则界面每秒全刷一次）。"""
    dm = DataManager(tmp_path)
    dm.tasks.file_path.unlink(missing_ok=True)
    dm._capture_mtimes()

    events: list[str] = []
    dm.data_changed.connect(events.append)
    dm._auto_reload()

    assert events == [], f"缺失文件不该反复触发刷新：{events!r}"


def test_unreadable_file_is_retried_next_round(qapp, tmp_path, monkeypatch) -> None:
    """暂时读不出来 → **不更新探针**，下一轮还要再来（不能一错就放弃）。"""
    dm = DataManager(tmp_path)
    _write(dm.tasks.file_path, ["原始"])
    dm.reload_all()
    _write(dm.tasks.file_path, ["新的"])

    real_read = type(dm.tasks.file_path).read_text
    calls = {"n": 0}

    def flaky(self, *args: object, **kwargs: object) -> str:
        calls["n"] += 1
        if calls["n"] <= 5:
            raise PermissionError("被占用")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(type(dm.tasks.file_path), "read_text", flaky, raising=False)
    dm._auto_reload()
    assert [t["title"] for t in dm.tasks.tasks] == ["原始"], "读不出来时保留内存态"

    monkeypatch.undo()
    dm._auto_reload()
    assert [t["title"] for t in dm.tasks.tasks] == ["新的"], "下一轮必须重试成功"


def test_startup_read_failure_recovers_without_a_timestamp_change(qapp, tmp_path, monkeypatch) -> None:
    dm = DataManager(tmp_path)
    path = dm.tasks.file_path
    _write(path, ["saved"])
    read = type(path).read_text

    def busy(candidate, *args: object, **kwargs: object) -> str:
        if candidate == path:
            raise PermissionError("sharing violation")
        return read(candidate, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(type(path), "read_text", busy)
        reopened = DataManager(tmp_path)
    assert reopened.tasks._write_blocked
    reopened._auto_reload()
    assert not reopened.tasks._write_blocked
    assert [task["title"] for task in reopened.tasks.tasks] == ["saved"]


def test_semester_switch_still_wins_over_freshness(qapp, tmp_path) -> None:
    """换学期优先于逐文件刷新（既有语义不能被新探针改坏）。"""
    dm = DataManager(tmp_path)
    events: list[str] = []
    dm.data_changed.connect(events.append)
    registry = dm.semesters.data
    registry.setdefault("semesters", []).append(
        {"id": "sem_extra", "name": "另一个", "start_date": "2027-03-01",
         "total_weeks": 16, "period_count": 5, "exam_weeks": 1})
    registry["current_semester"] = "sem_extra"
    dm.semesters.save()

    dm._auto_reload()

    assert "semester" in events, events
    assert dm._bound_semester == "sem_extra"


def test_task_model_alone_reports_reload(qapp, tmp_path) -> None:
    """单模型层面：`st_mtime_ns` 变化后 `reload()` 读得到新内容。"""
    target = tmp_path / "tasks.json"
    _write(target, ["一"])
    model = TaskModel(target)
    _touch_after(target, ["二"], 0.05)

    model.reload()

    assert [t["title"] for t in model.tasks] == ["二"]
