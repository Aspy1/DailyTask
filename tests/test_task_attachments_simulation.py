"""端到端**模拟**：种子作业 → 加附件 / 重复 / 拒绝 / 缺失 / 删除 → 换一个 DataManager 重读。

这不是"单元测试的重复"，而是把一次真实的用户流程按顺序走完：
`TaskModel.add()` 只改内存、`save()` 才落盘、附件文件与 JSON 的先后顺序、
以及"换一个 `DataManager`（= 重启应用）之后还能不能读回来"。

产出：末尾打印一份摘要（`pytest -q -s` 可见），供人工核对。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path

from src.models import semester_paths
from src.services.attachments import AttachmentError
from src.services.data_manager import DataManager
from src.ui.panels import task_detail_dialog as tdd
from src.ui.panels.task_detail_dialog import TaskDetailDialog


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _tasks(tmp_path: Path) -> dict:
    return json.loads(semester_paths.resolve(tmp_path, "tasks.json").read_text(encoding="utf-8"))


def test_full_attachment_lifecycle_simulation(tmp_path, qapp, monkeypatch, capsys) -> None:
    monkeypatch.setattr(tdd.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dm = DataManager(tmp_path)
    inbox = tmp_path / "inbox"

    # ① 种子：3 条作业，其中一条带备注
    ids = [
        dm.tasks.add({"title": "算法实验报告", "course_name": "算法",
                      "due_date": "2026-12-01T23:59:00"}),
        dm.tasks.add({"title": "物理习题", "course_name": "物理",
                      "due_date": "2026-12-03T23:59:00", "notes": "第 5 章 1-8 题"}),
        dm.tasks.add({"title": "英语作文", "course_name": "英语"}),
    ]
    dm.tasks.save()

    task_a = next(t for t in dm.tasks.active if t["id"] == ids[0])
    task_b = next(t for t in dm.tasks.active if t["id"] == ids[1])

    # ② 添加：两个不同文件 + 一个重复内容
    spec = _write(inbox / "实验报告要求.pdf", b"%PDF spec" * 100)
    data = _write(inbox / "数据.csv", b"a,b\n1,2\n")
    dup = _write(inbox / "数据-副本.csv", b"a,b\n1,2\n")

    dialog = TaskDetailDialog(dm, task_a)
    dialog._notes.setPlainText("先写实验思路，再补数据表。")
    assert dialog._add_path(spec) is True
    assert dialog._add_path(data) is True
    assert dialog._add_path(dup) is True            # 同内容 → 复用同一条
    duplicate_count = len(dialog._entries)

    # ③ 拒绝：超限 / 目录
    rejected: list[str] = []
    dm.attachments.max_bytes = 8
    for bad in (_write(inbox / "big.bin", b"x" * 64), inbox):
        try:
            dm.attachments.add(task_a["id"], bad, dialog._entries)
        except AttachmentError as exc:
            rejected.append(exc.code)
    dm.attachments.max_bytes = 25 * 1024 * 1024

    # ④ 保存（索引落盘）→ 文件应在
    dialog._on_save()
    stored_a = next(t for t in dm.tasks.active if t["id"] == ids[0])
    assert len(stored_a["attachments"]) == 2

    # ⑤ 缺失：手工删掉一个文件 → 打开时只提示、不抛异常
    missing_entry = stored_a["attachments"][1]
    (tmp_path / "attachments" / ids[0] / missing_entry["stored_name"]).unlink()
    opened: list[Path] = []
    monkeypatch.setattr(tdd, "open_path", lambda p: opened.append(p) or True)
    checker = TaskDetailDialog(dm, stored_a)
    checker._on_open(missing_entry)
    missing_detected = opened == []

    # ⑥ 删除：先提交索引，再删文件
    kept_entry = stored_a["attachments"][0]
    remover = TaskDetailDialog(dm, stored_a)
    remover._on_remove(kept_entry)
    remover._on_save()
    kept_path = tmp_path / "attachments" / ids[0] / kept_entry["stored_name"]

    # ⑦ 第二条作业也挂两个附件（另一个目录）
    other = _write(inbox / "习题答案.txt", b"answers")
    first_b = dm.attachments.add(task_b["id"], _write(inbox / "other.txt", b"o"))
    second = dm.attachments.add(task_b["id"], other)
    dm.tasks.update(task_b["id"], {"attachments": [first_b, second]})
    dm.tasks.save()

    # ⑧ "重启"：换一个 DataManager 从磁盘重读
    reloaded = DataManager(tmp_path)
    tasks = {t["id"]: t for t in reloaded.tasks.active}
    summary = {
        "tasks": len(tasks),
        "task_a_attachments": len(tasks[ids[0]]["attachments"]),
        "task_a_notes": tasks[ids[0]]["notes"],
        "task_b_attachments": len(tasks[ids[1]]["attachments"]),
        "duplicate_collapsed_to": duplicate_count,
        "rejected": rejected,
        "missing_detected": missing_detected,
        "deleted_file_gone": not kept_path.exists(),
        "orphans": reloaded.attachments.orphan_report(tasks.values()),
    }
    print("\n[附件模拟摘要] " + json.dumps(summary, ensure_ascii=False, sort_keys=True))

    assert summary["tasks"] == 3
    assert summary["task_a_attachments"] == 1                  # 加 2 删 1
    assert summary["task_a_notes"] == "先写实验思路，再补数据表。"
    assert summary["task_b_attachments"] == 2
    assert summary["duplicate_collapsed_to"] == 2              # 3 次添加 → 2 条
    assert summary["rejected"] == ["too_large", "rejected"]
    assert summary["missing_detected"] is True
    assert summary["deleted_file_gone"] is True
    assert summary["orphans"] == {"task_dirs": [], "files": []}
    # 落盘的 JSON 里不含绝对路径
    assert str(tmp_path) not in json.dumps(_tasks(tmp_path), ensure_ascii=False)
    assert "模拟摘要" in capsys.readouterr().out


def test_simulation_of_save_failure_keeps_files(tmp_path, qapp, monkeypatch, capsys) -> None:
    """第二幕：磁盘被外部改动（`save()` 返回 False）时，删附件不能动文件。"""
    monkeypatch.setattr(tdd.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dm = DataManager(tmp_path)
    task_id = dm.tasks.add({"title": "期末项目"})
    dm.tasks.save()
    task = next(t for t in dm.tasks.active if t["id"] == task_id)
    entry = dm.attachments.add(task_id, _write(tmp_path / "inbox" / "plan.md", b"# plan"))
    dm.tasks.update(task_id, {"attachments": [entry]})
    dm.tasks.save()
    path = tmp_path / "attachments" / task_id / entry["stored_name"]

    dialog = TaskDetailDialog(dm, task)
    dialog._on_remove(entry)
    monkeypatch.setattr(dm.tasks, "save", lambda: False)
    dialog._on_save()

    print(f"\n[保存失败模拟] 文件保留={path.is_file()} 条目数="
          f"{len(_tasks(tmp_path)['tasks'][0]['attachments'])}")
    assert path.is_file()
    assert len(_tasks(tmp_path)["tasks"][0]["attachments"]) == 1
    assert "文件保留=True" in capsys.readouterr().out
