"""考研备考模型：学习统计 / 错题间隔复习 / 模考 / 目标倒计时。

全部用固定日期，避免测试依赖真实时钟。
"""

from datetime import date, timedelta

from src.models.study import REVIEW_INTERVALS, StudyModel


def _model(tmp_path) -> StudyModel:
    return StudyModel(tmp_path / "study.json")


def test_defaults_and_subjects(tmp_path) -> None:
    model = _model(tmp_path)
    assert {s["id"] for s in model.subjects} == {"math", "english", "politics", "cs408"}
    assert model.target_date
    assert model.countdown(date(2027, 6, 1)) is not None


def test_sessions_today_and_week(tmp_path) -> None:
    model = _model(tmp_path)
    monday = date(2027, 6, 7)          # 周一
    model.add_session("数学一", 90, day=monday)
    model.add_session("math", 30, day=monday)
    model.add_session("408", 60, day=monday + timedelta(days=1))

    assert model.minutes_on(monday) == 120
    assert model.minutes_on(monday, "math") == 120
    assert model.week_minutes(monday) == 180
    assert model.week_by_subject(monday) == {
        "math": 120, "english": 0, "politics": 0, "cs408": 60}

    series = model.daily_minutes(7, monday + timedelta(days=1))
    assert len(series) == 7 and series[monday.isoformat()] == 120


def test_streak_counts_consecutive_goal_days(tmp_path) -> None:
    model = _model(tmp_path)
    model.set_daily_goal(60)
    day = date(2027, 6, 1)
    for offset in range(3):
        model.add_session("math", 60, day=day + timedelta(days=offset))
    assert model.study_streak(day + timedelta(days=2)) == 3
    # 今天还没达标 → 从昨天往前数
    assert model.study_streak(day + timedelta(days=3)) == 3


def test_mistake_review_ladder_reaches_mastered(tmp_path) -> None:
    model = _model(tmp_path)
    start = date(2027, 6, 1)
    mid = model.add_mistake("408", "页面置换", day=start)
    mistake = next(m for m in model.mistakes if m["id"] == mid)
    assert mistake["next_review"] == (start + timedelta(days=1)).isoformat()
    assert mistake["stage"] == 0

    cursor = start
    for _ in REVIEW_INTERVALS:
        cursor += timedelta(days=1)          # 到期后复习
        model.review_mistake(mid, cursor)
        cursor = date.fromisoformat(mistake["next_review"]) if mistake["next_review"] else cursor

    assert mistake["mastered"] is True
    assert mistake["next_review"] is None
    assert model.due_reviews(cursor) == []


def test_due_reviews_includes_overdue(tmp_path) -> None:
    model = _model(tmp_path)
    day = date(2027, 6, 1)
    mid = model.add_mistake("math", "极限", day=day)
    assert model.due_reviews(day) == []
    due = model.due_reviews(day + timedelta(days=3))
    assert [m["id"] for m in due] == [mid]


def test_master_mistake_and_open_list(tmp_path) -> None:
    model = _model(tmp_path)
    mid = model.add_mistake("english", "长难句", day=date(2027, 6, 1))
    assert model.master_mistake(mid) is True
    assert model.open_mistakes() == []


def test_mocks_latest_and_history(tmp_path) -> None:
    model = _model(tmp_path)
    model.add_mock("math", 95, day=date(2027, 6, 7))
    model.add_mock("math", 120, day=date(2027, 6, 21))
    model.add_mock("408", 100, full_score=150, day=date(2027, 6, 14))

    latest = model.latest_mock("math")
    assert latest["score"] == 120 and latest["date"] == "2027-06-21"
    assert [m["score"] for m in model.mock_history("math")] == [95, 120]
    assert model.latest_mock()["subject"] == "math"


def test_summary_and_countdown(tmp_path) -> None:
    model = _model(tmp_path)
    model.set_target("2027-12-25")
    model.set_daily_goal(200)
    day = date(2027, 6, 1)
    model.add_session("math", 100, day=day)
    model.add_session("cs408", 100, day=day)
    model.add_mistake("math", "极限", day=day)
    model.add_mock("math", 110, day=day)

    summary = model.summary(day)
    assert summary["days_left"] == (date(2027, 12, 25) - day).days
    assert summary["today_minutes"] == 200
    assert summary["week_minutes"] == 200
    assert summary["due_count"] == 0
    assert summary["latest_mock"]["score"] == 110
    assert summary["streak"] == 1
