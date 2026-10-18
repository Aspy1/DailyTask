"""考试的**可写清单**（`EXAM_FIELDS`）守卫 —— 同 `inventory.py` 那份。

2026-10-19：`inventory` 因为 `add_item` / `update_item` 各写一份白名单而**静默丢字段**
（会员弹窗存不上 ✗）。`exam` 当时是同一形状（两处恰好同步 ✓），这里钉成一份并加测试，
免得以后加字段时再漂移。
"""

from src.models.exam import EXAM_FIELDS, ExamModel

VALUES = {
    "course_name": "计算机系统结构",
    "exam_date": "2026-11-05",
    "scope": "第 1–6 章",
    "location": "教三 201",
    "notes": "带计算器",
    "tags": ["期中"],
}


def test_add_exam_keeps_every_writable_field(tmp_path) -> None:
    m = ExamModel(tmp_path / "exams.json")
    eid = m.add_exam(dict(VALUES))
    exam = m.exams[0]
    assert exam["id"] == eid
    for key, value in VALUES.items():
        assert exam.get(key) == value, f"add_exam 丢了字段 {key}"


def test_update_exam_persists_every_writable_field(tmp_path) -> None:
    m = ExamModel(tmp_path / "exams.json")
    m.add_exam({"course_name": "占位"})
    for key, value in VALUES.items():
        assert m.update_exam("e_001", {key: value}) is True
        assert m.exams[0].get(key) == value, f"update_exam 丢了字段 {key}"


def test_exam_fields_has_no_duplicates() -> None:
    assert len(EXAM_FIELDS) == len(set(EXAM_FIELDS))
