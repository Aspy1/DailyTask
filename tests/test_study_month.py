"""一个月备考模拟的确定性断言（同时是第三步的场景样例）。"""

from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.study_month_simulation import DAYS, _run_month, render
from src.models.study import StudyModel


def test_month_simulation_totals_and_reviews() -> None:
    with TemporaryDirectory() as tmp:
        result = _run_month(StudyModel(Path(tmp) / "study.json"))

    # 30 天：22 个工作日 × 4 段 + 8 个周末 × 2 段
    assert result["sessions"] == 22 * 4 + 8 * 2
    assert sum(result["totals"].values()) == 22 * 280 + 8 * 180
    assert result["totals"]["math"] > result["totals"]["english"]
    assert result["mistakes_added"] == 22 * 2 + 8 * 2
    assert result["reviews_done"] > 0
    assert result["due_end"] == 0
    assert result["summary"]["days_left"] == 178
    assert result["summary"]["studied_days_30"] == DAYS
    assert len(result["mocks"]) >= 4
    assert result["mocks"][-1]["score"] >= result["mocks"][0]["score"]


def test_month_report_mentions_scenario() -> None:
    with TemporaryDirectory() as tmp:
        report = render(_run_month(StudyModel(Path(tmp) / "study.json")))
    assert "考研 11408 一个月模拟" in report
    assert "数学一" in report and "408" in report
    assert "这个月软件帮到了什么" in report
    assert "模拟中暴露的缺口" in report
