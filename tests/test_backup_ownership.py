"""P0-1：备份**归属**与恢复校验（审计 2026-11-21）。

复现的故障：A 学期的 `tasks.json` 快照与 B 学期落在**同一个扁平备份池**里。
切到 B 之后 `restore --name tasks.json --yes` 命中的却是 A 的备份 ——
命令回 `OK`，B 的作业被替换成 A 的。课程 / 考试走同一条解析路径。

验收（审计原文）：
- 双学期合成夹具中，用 A 的备份恢复 B 必须**拒绝**，B 文件**逐字节一致**；
- 再覆盖合法恢复、迁移版本不匹配、读取损坏、同秒备份排序和失败后重试。
"""

import json
from pathlib import Path

from helpers import run

import scripts.actions_core as core

SEM_A = {"id": "sem_001", "name": "A 学期", "start_date": "2026-09-21",
         "total_weeks": 16, "period_count": 5, "exam_weeks": 1}
SEM_B = {"id": "sem_002", "name": "B 学期", "start_date": "2027-03-01",
         "total_weeks": 16, "period_count": 5, "exam_weeks": 1}


def _write_registry(sandbox, current: str) -> None:
    payload = {"_version": 1, "semesters": [SEM_A, SEM_B], "current_semester": current}
    (sandbox / "semesters.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _switch(sandbox, current: str, *names: str) -> None:
    """换学期 = 改注册表 + **重新载入**（与 `DataManager.switch_semester` 同口径）。

    不重新 `load()` 的话，`save()` 的路径守卫会先报"目标文件在本次操作期间变了"。
    """
    _write_registry(sandbox, current)
    for name in names:
        core.forget_loaded(name)
        if core._path(name).exists():
            core.load(name)


def _tasks(*titles: str) -> dict:
    return {"_version": 2, "tasks": [{"id": f"t_{i:03d}", "title": title,
                                      "status": "pending"} for i, title in enumerate(titles, 1)],
            "archived": []}


def _backups(sandbox) -> list:
    return sorted((sandbox / "backup" / "actions").glob("tasks.json.*.json"))


def _seed_a_with_backup(sandbox) -> None:
    """A 学期写两次 → 第二写之前 A 的快照进备份池。"""
    _write_registry(sandbox, "sem_001")
    core.save("tasks.json", _tasks("A 的作业"))
    core.save("tasks.json", _tasks("A 的作业", "A 的第二条"))


def test_restore_from_another_semester_is_refused(sandbox) -> None:
    """⭐ 用 A 的备份恢复 B：必须拒绝，B 的文件逐字节一致。"""
    _seed_a_with_backup(sandbox)
    _switch(sandbox, "sem_002", "tasks.json")
    target = core._path("tasks.json")
    core.save("tasks.json", _tasks("B 的作业"))
    before = target.read_bytes()

    out = run('restore --name "tasks.json" --yes')

    assert out.startswith("ERROR"), f"跨学期恢复必须被拒绝，实际：{out!r}"
    assert target.read_bytes() == before, "被拒时 B 的作业不得被 A 覆盖"


def test_restore_uses_the_owner_of_the_resolved_destination(sandbox, monkeypatch) -> None:
    from scripts import actions_backups_cli

    _seed_a_with_backup(sandbox)
    _switch(sandbox, "sem_002", "tasks.json")
    core.save("tasks.json", _tasks("B"))
    target = core._path("tasks.json")
    before = target.read_bytes()

    def resolve_then_switch(name: str) -> Path:
        destination = core._path(name)
        _switch(sandbox, "sem_001", "tasks.json")
        return destination

    monkeypatch.setattr(actions_backups_cli, "_path", resolve_then_switch)
    assert run('restore --name "tasks.json" --yes').startswith("ERROR")
    assert target.read_bytes() == before


def test_backup_retention_is_separate_for_each_semester(sandbox, monkeypatch) -> None:
    from scripts import actions_backup

    monkeypatch.setattr(actions_backup, "_max_backups", lambda: 1)
    _seed_a_with_backup(sandbox)
    _switch(sandbox, "sem_002", "tasks.json")
    core.save("tasks.json", _tasks("B"))
    core.save("tasks.json", _tasks("B", "B2"))
    assert {entry["semester_id"] for entry in actions_backup.read_index()} == {"sem_001", "sem_002"}


def test_restore_from_exam_snapshot_is_refused_too(sandbox) -> None:
    """课程 / 考试走同一条解析路径 —— 一并守住。"""
    _write_registry(sandbox, "sem_001")
    core.save("exams.json", {"_version": 1, "exams": [{"id": "e_001", "course_name": "A 的考试"}]})
    core.save("exams.json", {"_version": 1, "exams": [
        {"id": "e_001", "course_name": "A 的考试"}, {"id": "e_002", "course_name": "A 的另一场"}]})
    _switch(sandbox, "sem_002", "exams.json")
    target = core._path("exams.json")
    core.save("exams.json", {"_version": 1, "exams": [{"id": "e_001", "course_name": "B 的考试"}]})
    before = target.read_bytes()

    out = run('restore --name "exams.json" --yes')

    assert out.startswith("ERROR"), out
    assert target.read_bytes() == before


def test_restore_within_the_same_semester_still_works(sandbox) -> None:
    """反向回归：同学期的合法恢复不能被新校验误伤。"""
    _seed_a_with_backup(sandbox)
    target = core._path("tasks.json")
    assert len(json.loads(target.read_text(encoding="utf-8"))["tasks"]) == 2

    out = run('restore --name "tasks.json" --yes')

    assert out.startswith("OK"), out
    titles = [t["title"] for t in json.loads(target.read_text(encoding="utf-8"))["tasks"]]
    assert titles == ["A 的作业"], "应回到上一版"


def test_unknown_owner_requires_explicit_semester(sandbox) -> None:
    """旧快照来源未知（无清单条目）→ 要求人工选定归属，不得猜。"""
    _seed_a_with_backup(sandbox)
    backup = _backups(sandbox)[-1]
    index = backup.parent / "index.json"
    if index.exists():
        index.unlink()                       # 模拟"清单丢失 / 旧版本留下的快照"
    _switch(sandbox, "sem_002", "tasks.json")
    target = core._path("tasks.json")
    core.save("tasks.json", _tasks("B 的作业"))
    before = target.read_bytes()

    out = run('restore --name "tasks.json" --yes')
    assert out.startswith("ERROR") and "--semester" in out, out
    assert target.read_bytes() == before


def test_unknown_owner_is_accepted_when_ownership_is_explicit(sandbox) -> None:
    """用户明确声明归属，且与当前目标一致 → 允许（人工选定归属）。"""
    _seed_a_with_backup(sandbox)
    _write_registry(sandbox, "sem_001")
    target = core._path("tasks.json")
    index = target.parent.parent.parent / "backup" / "actions" / "index.json"
    if index.exists():
        index.unlink()

    out = run('restore --name "tasks.json" --semester sem_001 --yes')

    assert out.startswith("OK"), out
    titles = [t["title"] for t in json.loads(target.read_text(encoding="utf-8"))["tasks"]]
    assert titles == ["A 的作业"]


def test_backup_from_a_future_schema_version_is_refused(sandbox) -> None:
    """迁移版本不匹配：备份由**更新版应用**写的 → 拒绝（不是"内容损坏"）。"""
    import scripts.actions_backup as backups

    _seed_a_with_backup(sandbox)
    backup = _backups(sandbox)[-1]
    entries = backups.read_index()
    entry = next(e for e in entries if e["file"] == backup.name)
    entry["schema_version"] = entry["supported_version"] + 5
    entry["sha256"] = backups._sha256(backup)          # 内容本身没被动过
    backups._write_index(entries)
    target = core._path("tasks.json")
    before = target.read_bytes()

    out = run('restore --name "tasks.json" --yes')

    assert out.startswith("ERROR") and "版本" in out, out
    assert target.read_bytes() == before


def test_corrupted_backup_is_refused(sandbox) -> None:
    """读取损坏：备份内容被改过 → 校验 sha256 失败，宁可不恢复。"""
    _seed_a_with_backup(sandbox)
    backup = _backups(sandbox)[-1]
    backup.write_text('{"tasks": [}', encoding="utf-8")
    target = core._path("tasks.json")
    before = target.read_bytes()

    out = run('restore --name "tasks.json" --yes')

    assert out.startswith("ERROR"), out
    assert target.read_bytes() == before


def test_backups_in_the_same_second_keep_a_stable_order(sandbox) -> None:
    """同秒多份备份：最近的一份必须是**后写**的那份（文件名后缀会倒序）。"""
    _write_registry(sandbox, "sem_001")
    target = core._path("tasks.json")
    for round_ in range(3):
        core.save("tasks.json", _tasks(*[f"第 {round_}-{n} 条" for n in range(round_ + 1)]))
    core.save("tasks.json", _tasks("最新一版"))

    out = run('restore --name "tasks.json" --yes')

    assert out.startswith("OK"), out
    titles = [t["title"] for t in json.loads(target.read_text(encoding="utf-8"))["tasks"]]
    assert titles == ["第 2-0 条", "第 2-1 条", "第 2-2 条"], titles


def test_restore_can_be_retried_after_a_failure(sandbox) -> None:
    """失败后重试：校验失败不消耗备份，修好后还能正常恢复。"""
    _seed_a_with_backup(sandbox)
    backup = _backups(sandbox)[-1]
    pristine = backup.read_bytes()
    backup.write_text('{"tasks": [}', encoding="utf-8")
    assert run('restore --name "tasks.json" --yes').startswith("ERROR")

    backup.write_bytes(pristine)
    out = run('restore --name "tasks.json" --yes')

    assert out.startswith("OK"), out
    assert [t["title"] for t in
            json.loads(core._path('tasks.json').read_text(encoding='utf-8'))['tasks']] == ["A 的作业"]


def test_shared_files_are_not_treated_as_semester_scoped(sandbox) -> None:
    """`inventory.json` 是跨学期的：换学期后恢复不应被归属校验误伤。"""
    _write_registry(sandbox, "sem_001")
    core.save("inventory.json", {"_version": 1, "items": [{"id": "i_001", "name": "抽纸"}], "locations": []})
    core.save("inventory.json", {"_version": 1, "items": [
        {"id": "i_001", "name": "抽纸"}, {"id": "i_002", "name": "牙膏"}], "locations": []})
    _write_registry(sandbox, "sem_002")

    out = run('restore --name "inventory.json" --yes')

    assert out.startswith("OK"), out
    names = [i["name"] for i in
             json.loads((sandbox / "inventory.json").read_text(encoding="utf-8"))["items"]]
    assert names == ["抽纸"]


def test_list_backups_does_not_list_its_own_index(sandbox) -> None:
    _seed_a_with_backup(sandbox)
    out = run("list_backups")
    assert "index.json" not in out, out
