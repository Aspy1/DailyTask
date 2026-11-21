from datetime import datetime

from scripts.hermes_reminders import run_reminders


def test_meals_send_once_per_window_across_runs(sandbox) -> None:
    ledger = sandbox / "ledger.sqlite"
    assert run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 39)) == ""
    assert "午饭" in run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 11, 40))
    assert run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 12, 0)) == ""
    assert "晚饭" in run_reminders("meal", sandbox, ledger, datetime(2026, 11, 21, 17, 0))
    assert run_reminders("meal", sandbox, ledger, datetime(2026, 11, 22, 13, 11)) == ""


def test_deadline_and_exam_rules_share_desktop_boundaries(sandbox) -> None:
    import json

    from src.models.semester_paths import semester_dir
    from src.services.reminder_preference import publish_reminder_preference

    folder = semester_dir(sandbox, "s1")
    folder.mkdir(parents=True)
    (sandbox / "semesters.json").write_text(json.dumps({"current_semester": "s1"}))
    tasks = [
        {"id": "t1", "title": "urgent", "status": "pending", "due_date": "2026-11-21T14:00"},
        {"id": "t2", "title": "normal", "status": "pending", "due_date": "2026-11-24T15:00"},
        {"id": "t3", "title": "legacy exam", "status": "pending", "due_date": "2026-11-24T09:00"},
    ]
    (folder / "tasks.json").write_text(json.dumps({"tasks": tasks}))
    (folder / "exams.json").write_text(json.dumps({
        "exams": [{"course_name": "legacy exam", "exam_date": "2026-11-24"}],
    }))
    now = datetime(2026, 11, 21, 8, 0)
    ledger = sandbox / "ledger.sqlite"
    publish_reminder_preference(sandbox, False)
    first = run_reminders("homework", sandbox, ledger, now)
    assert "urgent" in first and "normal" not in first
    publish_reminder_preference(sandbox, True)
    second = run_reminders("homework", sandbox, ledger, now)
    assert "normal" in second and "6 小时" not in second
    assert run_reminders("homework", sandbox, ledger, now) == ""
    exam = run_reminders("exam", sandbox, ledger, now)
    assert exam.count("legacy exam") == 1 and "3 天" in exam
    assert run_reminders("exam", sandbox, ledger, datetime(2026, 11, 22, 8, 0)) == ""
