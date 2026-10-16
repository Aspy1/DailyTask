"""学期功能的 UI 与集成守卫：状态文案、面板周标签、对话框、AI 口径、邮件摘要口径。"""

from datetime import date, timedelta

from src.models import semester as sem
from src.services.data_manager import DataManager
from src.ui.components.semester_text import issue_text, semester_state_text


def _status(state: str, **extra: object) -> dict:
    base = {"state": state, "week": None, "total_weeks": 20, "issues": []}
    base.update(extra)
    return base


# ── 文案映射 ────────────────────────────────────────────────

def test_state_text_matches_state(qapp) -> None:
    assert semester_state_text(_status(sem.STATE_NONE)) == "未设置学期"
    assert semester_state_text(_status(sem.STATE_INVALID)) == "学期数据异常"
    assert semester_state_text(_status(sem.STATE_NOT_STARTED)) == "学期未开始"
    assert semester_state_text(_status(sem.STATE_EXPIRED)) == "学期已结束"
    assert semester_state_text(_status(sem.STATE_ACTIVE, week=3)) == "第 3 / 20 周"


def test_every_issue_code_has_text(qapp) -> None:
    """问题码必须有对应文案，否则界面会显示裸码（`tr` 的兜底行为）。"""
    codes = [
        sem.ISSUE_ID_MISSING, sem.ISSUE_START_MISSING, sem.ISSUE_START_UNPARSABLE,
        sem.ISSUE_START_OUT_OF_RANGE, sem.ISSUE_TOTAL_MISSING, sem.ISSUE_TOTAL_OUT_OF_RANGE,
        sem.ISSUE_PERIOD_OUT_OF_RANGE, sem.ISSUE_CURRENT_MISSING, sem.ISSUE_NO_SEMESTER,
        sem.ISSUE_DUPLICATE_IDS, sem.ISSUE_OVERLAP, sem.ISSUE_COURSE_WEEKS,
        sem.ISSUE_COURSE_DAY, sem.ISSUE_COURSE_SLOTS,
    ]
    for code in codes:
        text = issue_text(code)
        assert text != f"semester.issue.{code}", f"{code} 缺文案"
        assert text


# ── 课程表面板的周标签 ──────────────────────────────────────

def test_week_label_says_expired_instead_of_nonsense_week(qapp, tmp_path) -> None:
    """回归：过期学期不得显示"第 32 / 16 周"这种没意义的数字。"""
    dm = DataManager(tmp_path)
    dm.courses._data["semesters"] = [{
        "id": "old", "start_date": (date.today() - timedelta(days=32 * 7)).isoformat(),
        "total_weeks": 20, "period_count": 5}]
    dm.courses._data["current_semester"] = "old"

    from src.ui.panels.course_panel import CoursePanel

    panel = CoursePanel(dm)
    panel._refresh()
    label = panel._week_label.text()
    assert "学期已结束" in label
    assert "第 20 / 20 周" in label          # 仍告诉用户在看哪一周
    assert "32" not in label


def test_week_label_active_shows_plain_week(qapp, tmp_path) -> None:
    dm = DataManager(tmp_path)
    dm.courses._data["semesters"] = [{
        "id": "s", "start_date": (date.today() - timedelta(days=7)).isoformat(),
        "total_weeks": 20, "period_count": 5}]
    dm.courses._data["current_semester"] = "s"

    from src.ui.panels.course_panel import CoursePanel

    panel = CoursePanel(dm)
    panel._refresh()
    assert panel._week_label.text() == "第 2 / 20 周"


# ── 对话框 ──────────────────────────────────────────────────

def test_dialog_creates_semester_and_sets_current(qapp, tmp_path) -> None:
    from src.models.semester import season_start_for
    from src.ui.widgets.semester_dialog import SemesterDialog

    dm = DataManager(tmp_path)
    dialog = SemesterDialog(dm)
    assert dialog._switch_combo.count() == 0          # 还没有学期
    # 默认开始日按季节预设（秋 9/21 / 春 3/2），总周数 16 + 期末周 1
    assert dialog._start_input.date().toPython() == season_start_for(date.today())
    assert dialog._weeks_input.value() == 16
    assert dialog._exam_input.value() == 1

    dialog._name_input.setText("2026 秋")
    dialog._periods_input.setValue(6)
    dialog._on_create()

    assert dm.courses.current_semester
    created = dm.courses.get_semester(dm.courses.current_semester)
    assert created["name"] == "2026 秋"
    assert created["total_weeks"] == 16
    assert created["exam_weeks"] == 1
    assert created["period_count"] == 6
    assert dialog._switch_combo.count() == 1          # 列表已刷新


def test_dialog_switch_semester(qapp, tmp_path) -> None:
    from src.ui.widgets.semester_dialog import SemesterDialog

    dm = DataManager(tmp_path)
    first = dm.courses.create_semester("旧", date(2020, 2, 24))
    second = dm.courses.create_semester("新", date.today())

    dialog = SemesterDialog(dm)
    dialog._switch_combo.setCurrentIndex(
        [dialog._switch_combo.itemData(i) for i in range(dialog._switch_combo.count())]
        .index(first))
    dialog._on_switch()
    assert dm.courses.current_semester == first
    assert second != first


def test_state_text_covers_exam_week(qapp) -> None:
    assert semester_state_text(_status(sem.STATE_EXAM)) == "期末周"


# ── 口径一致：AI 提示词与邮件摘要 ───────────────────────────

def test_ai_current_week_respects_current_semester(tmp_path) -> None:
    """回归：旧实现取 `semesters` 里**第一个**学期，多个学期时算错。"""
    from src.services.ai_service import AIService
    from src.services.settings_manager import SettingsManager

    dm = DataManager(tmp_path)
    dm.courses._data["semesters"] = [
        {"id": "old", "start_date": "2020-02-24", "total_weeks": 20, "period_count": 5},
        {"id": "new", "start_date": (date.today() - timedelta(days=7)).isoformat(),
         "total_weeks": 20, "period_count": 5},
    ]
    dm.courses._data["current_semester"] = "new"

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    service = AIService(settings, dm)
    assert service._get_current_week() == 2
    assert service._get_week_parity() == "双周"


def test_digest_week_number_matches_model(tmp_path) -> None:
    """邮件摘要与桌面端**同一份实现**（此前是第三套算法）。"""
    from scripts.send_digest import _week_number_for

    start = date.today() - timedelta(days=7)
    data = {
        "current_semester": "s",
        "semesters": [{"id": "s", "start_date": start.isoformat(),
                       "total_weeks": 20, "period_count": 5}],
    }
    assert _week_number_for(data, date.today()) == 2

    expired = {
        "current_semester": "s",
        "semesters": [{"id": "s", "start_date": "2020-02-24",
                       "total_weeks": 20, "period_count": 5}],
    }
    assert _week_number_for(expired, date.today()) is None

    broken = {"current_semester": "s",
              "semesters": [{"id": "s", "start_date": "xx", "total_weeks": 20}]}
    assert _week_number_for(broken, date.today()) is None
