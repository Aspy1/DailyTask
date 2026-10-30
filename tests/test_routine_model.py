"""「近期安排」模型：排序、三态、按天存（用户 2026-10-30 口径）。

要点与习惯**刻意不同**：没有连续天数、状态只属于当天。
"""

from datetime import date, timedelta

from src.models.routine import RoutineModel


def _model(tmp_path) -> RoutineModel:
    return RoutineModel(tmp_path / "routines.json")


def test_add_keeps_insertion_order(tmp_path) -> None:
    m = _model(tmp_path)
    a = m.add("背单词", "六级 50 个")
    b = m.add("跑步")
    assert [i["id"] for i in m.items] == [a, b]
    assert [i["order"] for i in m.items] == [0, 1]
    assert m.items[0]["note"] == "六级 50 个"


def test_ids_survive_deletion(tmp_path) -> None:
    """R-008：删掉中间一条后再新增，不能与既有 id 撞车。"""
    m = _model(tmp_path)
    a = m.add("A")
    b = m.add("B")
    m.remove(a)
    c = m.add("C")
    assert len({a, b, c}) == 3
    assert c != a


def test_move_reorders_and_renumbers(tmp_path) -> None:
    m = _model(tmp_path)
    a = m.add("A")
    b = m.add("B")
    c = m.add("C")
    assert m.move(c, 0) is True
    assert [i["id"] for i in m.items] == [c, a, b]
    assert [i["order"] for i in m.items] == [0, 1, 2]


def test_move_clamps_out_of_range(tmp_path) -> None:
    m = _model(tmp_path)
    a = m.add("A")
    m.add("B")
    m.move(a, 99)
    assert m.items[-1]["id"] == a


def test_cycle_is_empty_done_skipped_empty(tmp_path) -> None:
    m = _model(tmp_path)
    rid = m.add("背单词")
    assert m.status_on(rid) == ""
    assert m.cycle_status(rid) == "done"
    assert m.cycle_status(rid) == "skipped"
    assert m.cycle_status(rid) == ""
    assert m.status_on(rid) == "", "第三次点击要把当天记录清掉"


def test_status_is_per_day(tmp_path) -> None:
    """按天存：昨天的 ✔ 不影响今天（这是和"连续天数"划清界限的地方）。"""
    m = _model(tmp_path)
    rid = m.add("背单词")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    m.cycle_status(rid, yesterday)
    assert m.status_on(rid, yesterday) == "done"
    assert m.status_on(rid) == ""


def test_day_counts(tmp_path) -> None:
    m = _model(tmp_path)
    a = m.add("A")
    b = m.add("B")
    m.add("C")
    m.cycle_status(a)                 # done
    m.cycle_status(b)
    m.cycle_status(b)                 # skipped
    assert m.day_counts() == {"done": 1, "skipped": 1, "total": 3}


def test_remove_restores_contiguous_order(tmp_path) -> None:
    m = _model(tmp_path)
    m.add("A")
    b = m.add("B")
    m.add("C")
    m.remove(b)
    assert [i["order"] for i in m.items] == [0, 1]


def test_update_routine_only_accepts_writable_fields(tmp_path) -> None:
    m = _model(tmp_path)
    rid = m.add("旧标题")
    assert m.update_routine(rid, {"title": "新标题", "order": 5, "id": "x"}) is True
    assert m.items[0]["title"] == "新标题"
    assert m.items[0]["order"] == 0
    assert m.items[0]["id"] == rid


def test_save_and_reload_roundtrip(tmp_path) -> None:
    m = _model(tmp_path)
    rid = m.add("背单词", "六级")
    m.cycle_status(rid)
    m.save()

    again = _model(tmp_path)
    assert again.status_on(rid) == "done"
    assert again.items[0]["title"] == "背单词"
