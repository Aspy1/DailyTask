"""2026-10-16 全量验收后的小修守卫（1/3/4/5 项）。

对应验收报告里的 4 条次要问题：
1. 状态栏只在 30s 定时器上刷新 → 切学期后显示旧数字
3. i18n 门禁范围漏掉应用入口 `src/app.py`
4. 日志：git 失败原因可能为空 / logger 命名不一致
5. 习惯面板没有空态提示
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtWidgets import QLabel

from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager

ROOT = Path(__file__).resolve().parent.parent


def _monday() -> date:
    today = date.today()
    return today - timedelta(days=today.isoweekday() - 1)


# ── 1) 状态栏随数据变化立即刷新 ─────────────────────────────

def test_statusbar_refreshes_on_data_changed(qapp, tmp_path) -> None:
    """切学期（`data_changed`）后状态栏要**立即**更新，不能等 30s 定时器。"""
    from src.services.ai_service import AIService
    from src.ui.main_window import MainWindow

    dm = DataManager(tmp_path)
    dm.semesters._data["semesters"] = [{
        "id": "s", "start_date": _monday().isoformat(),
        "total_weeks": 16, "period_count": 5, "exam_weeks": 1}]
    dm.semesters._data["current_semester"] = "s"
    dm.courses.add_course({"name": "今天的课", "day_of_week": date.today().isoweekday(),
                           "time_slots": [{"start": 1, "end": 1}]})
    dm.courses.save()

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    mw = MainWindow(settings, AIService(settings, dm), dm, None)
    mw._refresh_status()
    assert "节课" in mw._course_info_label.text(), mw._course_info_label.text()

    dm.create_semester("空学期", date(2027, 3, 2))       # 新学期没有课 → 发 data_changed
    assert mw._course_info_label.text() != "共1节课", "状态栏应已随 data_changed 刷新"
    assert mw._course_info_label.text() == "今日无课", mw._course_info_label.text()


# ── 3) i18n 度量范围包含应用入口 ────────────────────────────

def test_i18n_metric_covers_app_entry() -> None:
    """`src/app.py` 也有用户可见文案（托盘菜单/气泡），度量范围必须包含它。"""
    import scripts.check_quality as cq

    files = {f.as_posix() for f in cq._ui_py_files()}
    assert any(f.endswith("/src/app.py") for f in files), files
    assert any("/src/ui/" in f for f in files)


def test_app_entry_has_no_hardcoded_ui_text() -> None:
    """入口文件里不应再有裸中文界面文案（托盘「同步到 GitHub」等已走 `tr()`）。"""
    import scripts.check_quality as cq

    app_file = ROOT / "src" / "app.py"
    assert cq._count_cn_in_file(app_file) == 0, "app.py 仍有未国际化的中文字面量"


# ── 4) 日志：git 失败原因 / logger 命名 ─────────────────────

def test_git_failure_message_includes_reason_from_stdout(tmp_path) -> None:
    """回归：只看 `stderr` 会得到"冒号后什么都没有"的日志，原因可能只在 stdout。

    （用 ASCII 输出，避免把"子进程编码"混进这条断言 —— 那是另一条修复。）
    """
    from src.services.git_sync import _GitWorker

    worker = _GitWorker(tmp_path, [[sys.executable, "-c",
                                    "print('reason-on-stdout'); raise SystemExit(3)"]])
    seen: list[tuple] = []
    worker.finished.connect(lambda ok, msg: seen.append((ok, msg)))
    worker.run()                                   # 同步跑，避免线程
    assert seen and seen[0][0] is False
    assert "reason-on-stdout" in seen[0][1], seen[0][1]


def test_git_worker_survives_non_ascii_output(tmp_path) -> None:
    """回归：`text=True` 不指定编码 → 本机 gbk 遇非 ASCII 输出会 UnicodeDecodeError。"""
    from src.services.git_sync import _GitWorker

    worker = _GitWorker(tmp_path, [[sys.executable, "-c",
                                    "print('中文输出 规划书.md'); raise SystemExit(0)"]])
    seen: list[tuple] = []
    worker.finished.connect(lambda ok, msg: seen.append((ok, msg)))
    worker.run()
    assert seen and seen[0][0] is True, seen          # 不该因为编码而失败


def test_loggers_use_module_names() -> None:
    """logger 命名统一为 `__name__`（短名会让日志过滤不一致）。"""
    bad = []
    for f in (ROOT / "src").rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if re.match(r"\s*logger = logging\.getLogger\((?!__name__)", line):
                bad.append(f"{f.as_posix()}: {line.strip()}")
    assert not bad, bad


# ── 5) 习惯面板空态 ────────────────────────────────────────

def test_habit_panel_shows_empty_hint(qapp, tmp_path) -> None:
    """今天没有要做的日常时要有空态提示（此前整页空白，看着像坏了）。"""
    from src.ui.panels.habit_panel import HabitPanel

    dm = DataManager(tmp_path)
    other_day = date.today().isoweekday() % 7 + 1      # 不是今天的星期
    dm.habits.add_habit({"name": "周六才做", "schedule": {"type": "weekly", "days": [other_day]}})

    panel = HabitPanel(dm)
    panel._refresh()
    texts = [w.text() for w in panel.findChildren(QLabel)]
    assert any("今天没有要做的日常" in t for t in texts), texts[:10]


def test_habit_panel_hides_empty_hint_when_cards_exist(qapp, tmp_path) -> None:
    from src.ui.panels.habit_panel import HabitPanel

    dm = DataManager(tmp_path)
    dm.habits.add_habit({"name": "每天", "schedule": {"type": "daily"}})

    panel = HabitPanel(dm)
    panel._refresh()
    texts = [w.text() for w in panel.findChildren(QLabel)]
    assert not any("今天没有要做的日常" in t for t in texts)
    assert [w for w in panel.findChildren(QLabel) if w.text()]        # 有内容
