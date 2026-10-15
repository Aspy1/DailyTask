"""send_digest.build_digest 的冒烟测试（此前无任何覆盖）。"""

import json
from datetime import date, timedelta

from scripts.send_digest import build_digest


def _write(data_dir, name, obj) -> None:
    (data_dir / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_build_digest_sections(tmp_path) -> None:
    today = date.today()
    _write(tmp_path, "courses.json", {"courses": [
        {"name": "算法", "day_of_week": today.isoweekday(),
         "time_slots": [{"start": 1, "end": 2}], "weeks": {"start": 1, "end": 20}},
    ], "semesters": [{"id": "s", "start_date": (today - timedelta(days=7)).isoformat(),
                     "total_weeks": 20}], "current_semester": "s", "holidays": {}})
    _write(tmp_path, "tasks.json", {"tasks": [
        {"id": "t_001", "title": "作业A", "status": "pending",
         "due_date": (today + timedelta(days=1)).isoformat()},
        {"id": "t_002", "title": "考试B", "status": "pending", "tags": ["考试"],
         "due_date": (today + timedelta(days=3)).isoformat()},
    ], "archived": []})
    _write(tmp_path, "habits.json", {"habits": [
        {"id": "h_001", "name": "跑步", "schedule": {"type": "daily", "times_per_day": 1}},
    ], "logs": {}, "attached_task_templates": []})
    _write(tmp_path, "daily_logs.json", {"plans": {today.isoformat(): [
        {"title": "复习", "time_slot": 3}]}, "logs": {}, "savings": {}, "reminders": []})
    _write(tmp_path, "expenses.json", {"records": [
        {"id": "e_001", "amount": 12.5, "date": today.isoformat()}],
        "budget": {"monthly": 1500}, "categories": []})
    _write(tmp_path, "inventory.json", {"items": [
        {"id": "i_001", "name": "洗衣液", "status": "need"}], "categories": []})
    _write(tmp_path, "exams.json", {"exams": [
        {"id": "e_001", "course_name": "大学物理",
         "exam_date": (today + timedelta(days=5)).isoformat()}]})

    text = build_digest(tmp_path)

    assert "【每日日程】" in text
    assert "── 今日课程 ──" in text and "算法" in text
    assert "── 今日计划 ──" in text and "复习" in text
    assert "── 今日习惯 ──" in text and "跑步" in text
    assert "── 即将截止的任务（3天内）──" in text and "作业A" in text
    assert "── 考试提醒 ──" in text and "考试B" in text
    assert "大学物理" in text and "还有 5 天" in text      # exams.json 来源
    assert "── 支出 ──" in text and "12.5" in text
    assert "── 购物需求 ──" in text and "洗衣液" in text


def test_digest_exam_from_exams_json_only(tmp_path) -> None:
    """回归：考试模块（exams.json）此前完全进不了摘要，只认 tasks 里的「考试」。"""
    today = date.today()
    _write(tmp_path, "tasks.json", {"tasks": [], "archived": []})
    _write(tmp_path, "exams.json", {"exams": [
        {"id": "e_001", "course_name": "线性代数",
         "exam_date": (today + timedelta(days=3)).isoformat()}]})
    text = build_digest(tmp_path)
    assert "── 考试提醒 ──" in text and "线性代数" in text
    assert "还有 3 天" in text


def test_digest_dedupes_same_exam_in_both_sources(tmp_path) -> None:
    """同一场考试同时存在于 exams.json 与 tasks 时，考试分区只列一次。"""
    today = date.today()
    day = (today + timedelta(days=2)).isoformat()
    _write(tmp_path, "tasks.json", {"tasks": [
        {"id": "t_001", "title": "高等数学", "status": "pending", "tags": ["考试"],
         "due_date": day}], "archived": []})
    _write(tmp_path, "exams.json", {"exams": [
        {"id": "e_001", "course_name": "高等数学", "exam_date": day}]})
    text = build_digest(tmp_path)
    exam_section = text.split("── 考试提醒 ──")[1]
    assert exam_section.count("高等数学") == 1, text


def test_digest_ignores_far_exams(tmp_path) -> None:
    today = date.today()
    _write(tmp_path, "exams.json", {"exams": [
        {"id": "e_001", "course_name": "遥远的考试",
         "exam_date": (today + timedelta(days=40)).isoformat()}]})
    text = build_digest(tmp_path)
    assert "遥远的考试" not in text


def test_build_digest_empty_data(tmp_path) -> None:
    for name in ("courses.json", "tasks.json", "habits.json",
                 "daily_logs.json", "expenses.json", "inventory.json"):
        _write(tmp_path, name, {})
    text = build_digest(tmp_path)          # 全空数据不应抛异常
    assert "【每日日程】" in text
    assert "（无课）" in text
