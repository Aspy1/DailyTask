"""ID 生成守卫（R-008：禁止用 `len()+1` 生成 ID）。

`len()+1` 的缺陷：删过条目后列表长度不再等于最大序号，新 ID 会与既有 ID 撞车
（删掉 `c_002` 后再新增，len 仍为 2 → 又生成 `c_002`）。
"""

from src.models.base import next_id
from src.models.course import CourseModel
from src.models.expense import ExpenseModel
from src.models.habit import HabitModel


def test_next_id_starts_at_one() -> None:
    assert next_id("c", []) == "c_001"


def test_next_id_uses_max_suffix_not_length() -> None:
    # 长度 2、最大序号 5 → 必须是 006（len()+1 会给出 003，撞上 c_003）
    assert next_id("c", ["c_001", "c_005"]) == "c_006"


def test_next_id_width_is_configurable() -> None:
    assert next_id("rem", ["rem_0009"], width=4) == "rem_0010"


def test_next_id_ignores_non_numeric_and_empty_suffixes() -> None:
    assert next_id("h", ["h_abc", "", "h_003"]) == "h_004"


def test_course_ids_do_not_collide_after_delete(tmp_path) -> None:
    m = CourseModel(tmp_path / "courses.json")
    first = m.add_course({"name": "A"})
    second = m.add_course({"name": "B"})
    third = m.add_course({"name": "C"})
    assert (first, second, third) == ("c_001", "c_002", "c_003")

    assert m.delete_course(second) is True
    again = m.add_course({"name": "D"})            # 旧实现会重新生成 c_003
    assert again == "c_004"
    ids = [c["id"] for c in m.courses]
    assert len(ids) == len(set(ids)) == 3, ids


def test_expense_ids_do_not_collide_after_delete(tmp_path) -> None:
    m = ExpenseModel(tmp_path / "expenses.json")
    a = m.add({"amount": 1})
    b = m.add({"amount": 2})
    c = m.add({"amount": 3})
    assert (a, b, c) == ("e_001", "e_002", "e_003")
    assert m.delete(b) is True
    assert m.add({"amount": 4}) == "e_004"


def test_habit_ids_do_not_collide_after_delete(tmp_path) -> None:
    m = HabitModel(tmp_path / "habits.json")
    a = m.add_habit({"name": "A"})
    b = m.add_habit({"name": "B"})
    assert (a, b) == ("h_001", "h_002")
    assert m.delete_habit(a) is True
    assert m.add_habit({"name": "C"}) == "h_003"


def test_explicit_id_is_respected(tmp_path) -> None:
    """调用方给了 id 就不能被覆盖（actions.py 会显式传 id）。"""
    m = CourseModel(tmp_path / "courses.json")
    assert m.add_course({"id": "c_900", "name": "X"}) == "c_900"
    assert m.add_course({"name": "Y"}) == "c_901"      # 接在显式 id 之后
