"""考研备考命令：学习 / 错题 / 模考 / 汇总 / 目标。"""

from datetime import date, timedelta

from helpers import read_json, run


def test_log_study_and_summary(sandbox) -> None:
    out = run('log_study --subject "数学一" --minutes 90 --note "极限"')
    assert out.startswith("OK"), out
    data = read_json(sandbox, "study.json")
    session = data["sessions"][0]
    assert session["subject"] == "math" and session["minutes"] == 90
    assert data["_version"] == 1

    summary = run("study_summary")
    assert "今日学习 90 分钟" in summary
    assert "数学一" in summary
    assert "倒计时" in summary


def test_add_and_review_mistake(sandbox) -> None:
    assert run('add_mistake --subject "408" --topic "页面置换"').startswith("OK")
    mid = read_json(sandbox, "study.json")["mistakes"][0]["id"]
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert read_json(sandbox, "study.json")["mistakes"][0]["next_review"] == tomorrow

    out = run(f'review_mistake --id {mid}')
    assert out.startswith("OK"), out
    mistake = read_json(sandbox, "study.json")["mistakes"][0]
    assert mistake["stage"] == 1 and mistake["reviewed_count"] == 1
    assert mistake["next_review"] == (date.today() + timedelta(days=2)).isoformat()

    assert run(f"master_mistake --id {mid}").startswith("OK")
    assert read_json(sandbox, "study.json")["mistakes"][0]["mastered"] is True


def test_add_mock_and_latest(sandbox) -> None:
    assert run('add_mock --subject "408" --score 100 --duration 180').startswith("OK")
    assert run('add_mock --subject "数学一" --score 120 --full-score 150').startswith("OK")
    data = read_json(sandbox, "study.json")
    assert data["mocks"][-1]["score"] == 120
    summary = run("study_summary")
    assert "最近模考" in summary and "120/150" in summary


def test_set_target_and_goal(sandbox) -> None:
    out = run('study_set_target --date 2027-12-25 --daily-goal 300')
    assert out.startswith("OK"), out
    data = read_json(sandbox, "study.json")
    assert data["target_date"] == "2027-12-25"
    assert data["daily_goal_minutes"] == 300


def test_list_mistakes_due_only(sandbox) -> None:
    run('add_mistake --subject "math" --topic "极限"')
    # 今天新增的错题默认明天复习 → 今天 due=yes 应该为空
    out = run("list_mistakes --due yes")
    assert "NO_MISTAKE" in out or "FOUND 0" in out


def test_invalid_subject_and_date_are_refused_without_writing(sandbox) -> None:
    assert run('log_study --subject "玄学" --minutes 30').startswith("ERROR")
    assert run('log_study --subject "math" --minutes 0').startswith("ERROR")
    assert run('add_mock --subject "math" --score 120 --date 2026-02-30').startswith("ERROR")
    assert not (sandbox / "study.json").exists() or not read_json(sandbox, "study.json")["sessions"]
