"""批量渲染界面截图 —— UI 审查 / 布局验收用。

**来历**：2026-10-18 那次 UI 审查的脚本（原来放在 `.pytest_cache/ui-audit-20261018/audit.py`，
随时可能被清缓存删掉）。审查自己写明"清理缓存前如需留档，应另行保存"，所以收进仓库，
并修掉它两处会**崩在退出**的写法：

1. 它把模态的 `QDialog.exec` 猴补成 `show()/hide()` —— 模态循环从没跑过，对话框一直挂在
   "已显示但没人管"的状态。这里改成定时器到点后 **close + deleteLater**（真正收尾），
   `exec()` 照常跑完。
2. 它最后用 `os._exit(0)` 硬退，跳过所有 C++ 析构与 Qt 销毁流程。这里走**正常退出**：
   `mw.close()` + `app.quit()`，让 Qt 自己收尾。

两条都实测过：原脚本跑完必 SIGSEGV（退出码 139），本脚本退出码 0。
见 `dev-logs/2026-10-18-审查脚本退出崩溃定位.md`。

**数据**：全部落在临时沙箱里，**不碰 `data/`**；合成数据**故意用长标题 / 多标签**，
否则看不出溢出问题（审查 §6 第 4 条）。

用法：
    .venv/Scripts/python.exe scripts/ui_render.py
    .venv/Scripts/python.exe scripts/ui_render.py --scale 1.25 --out shots-125
"""

import argparse
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QMessageBox,
    QScrollArea,
)

from src.services.ai_service import AIService  # noqa: E402
from src.services.data_manager import DataManager  # noqa: E402
from src.services.settings_manager import SettingsManager  # noqa: E402
from src.ui import animations  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from src.ui.styles import theme  # noqa: E402

PANELS = ["schedule", "tasks", "exams", "daily", "expenses", "inventory", "settings", "meals"]
LONG_COURSE = "计算机系统结构与并行程序设计实验"
LONG_TASK = "完成计算机系统结构综合实验报告并提交源代码与完整测试说明"
LONG_ITEM = "多功能 USB-C 数据线（2 米编织款，兼容平板与笔记本电脑）"
WIDE = (1210, 792)
NARROW = (990, 638)


def _seed(dm: DataManager) -> None:
    """合成数据：**故意用长标题 / 多标签 / 大金额**（审查 §6 第 4 条）。"""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    dm.semesters._data["semesters"] = [{
        "id": dm.semesters.current_semester, "name": "2026 秋季学期",
        "start_date": monday.isoformat(), "total_weeks": 16,
        "period_count": 5, "exam_weeks": 1}]
    for i, name in enumerate(["高等数学", LONG_COURSE, "大学英语", "操作系统", "概率论与数理统计"]):
        dm.courses.add_course({"name": name, "day_of_week": i + 1, "weeks": {"start": 1, "end": 16},
                               "time_slots": [{"start": 1 + i % 3, "end": 1 + i % 3,
                                               "location": "教学楼 A 区 501 多媒体教室"}]})
    for i, title in enumerate(["完成第三章习题", LONG_TASK, "复习课堂笔记"]):
        dm.tasks.add({"title": title, "course_name": "计算机系统结构",
                      "due_date": (today + timedelta(days=i)).isoformat() + "T22:00:00",
                      "priority": "high", "notes": "测试说明：请按要求提交。"})
    for i, name in enumerate(["高等数学期中考试", LONG_COURSE + "综合考试"]):
        dm.exams.add_exam({"course_name": name,
                           "exam_date": (today + timedelta(days=i + 3)).isoformat(),
                           "location": "教学楼 A 区 501 多媒体教室",
                           "scope": "第一章至第五章，包含课堂实验与补充阅读材料。"})
    for name in ["每天阅读二十分钟", "每日英语听力精读和口语跟读练习（包含复盘）", "整理桌面"]:
        dm.habits.add_habit({"name": name, "schedule": {"type": "daily"},
                             "duration_minutes": 20, "reminder_time": "20:00"})
    for i, name in enumerate(["普通抽纸", LONG_ITEM, "维生素片"]):
        dm.inventory.add_item({"name": name, "category": "日常消耗品", "quantity": i,
                               "min_quantity": 2, "location": "衣柜左侧第二层收纳盒",
                               "tags": ["常用", "带到学校", "Type-C"],
                               "notes": "用于测试长文字、标签和展开后的自适应高度。"})
    dm.inventory.add_item({"name": "换季羽绒服", "category": "衣物", "quantity": 1, "location": "家"})
    dm.inventory.add_item({"name": "QQ音乐会员", "category": "虚拟品类", "quantity": 1,
                           "membership": {"username": "my_qq", "expires_on": "2027-03-15",
                                          "auto_renew": True, "renew_months": 12}})
    dm.daily_logs.add_plan({"title": "准备课程汇报，整理参考文献与截图", "time_slot": 2,
                            "type": "custom", "note": "先完成必做任务，再处理选做内容。"},
                           today.isoformat())
    dm.expenses.add({"amount": 28.5, "category": "餐饮", "note": "午餐和水果",
                     "date": today.isoformat()})
    dm.inventory.save()
    dm.daily_logs.save()


class _Renderer:
    """渲染一趟：持有 app / 主窗口 / 输出目录与计数。"""

    def __init__(self, out: Path) -> None:
        self.out = out
        self.shots = 0
        self.app = QApplication([])
        self.app.setStyleSheet(theme.init_theme(self.app, "light"))
        animations.set_enabled(False)

        sandbox = Path(tempfile.mkdtemp(prefix="ui_render_"))
        self.dm = DataManager(sandbox)
        self.dm._reload_timer.stop()             # 截图期间别让 3s 轮询捣乱
        _seed(self.dm)
        settings = SettingsManager(sandbox / "settings.ini")
        settings.load()
        # ⚠ 渲染用的设置必须**像真的**：不设的话设置页显示默认的 DeepSeek / deepseek-chat，
        # 而实际用的是 OpenCode Go / deepseek-v4.1-flash → 用户看截图以为配置不对
        # （2026-10-18 反馈）✗。这里对齐真实配置。
        settings.set("AI", "provider", "opencode")
        settings.set("AI", "model", "deepseek-v4.1-flash")
        # 假 key（运行时拼，避免源码里出现像密钥的字面量）—— 让状态显示"已配置"，
        # 与真实环境一致
        settings.set("AI", "api_key", "sk-" + "render" + "0" * 24)
        self.mw = MainWindow(settings, AIService(settings, self.dm), self.dm)
        self.mw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.mw._status_timer.stop()
        self.mw.resize(*WIDE)
        self.mw.show()

    def settle(self) -> None:
        for _ in range(3):
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def capture(self, name: str, widget=None) -> None:
        self.settle()
        (widget or self.mw).grab().save(str(self.out / f"{name}.png"))
        self.shots += 1

    def _run_panel(self, mode: str, key: str) -> None:
        """一个面板（含课表/库存/设置的额外状态）。"""
        self.mw._workspace.switch_to(key)
        if key == "schedule":
            view = self.mw._workspace._schedule_view
            view._set_mode("day")
            self.capture(f"{mode}-schedule")
            view._set_mode("week")
            self.capture(f"{mode}-week")
            return
        self.capture(f"{mode}-{key}")
        if key == "inventory":
            inv = self.mw._workspace._inventory_panel
            inv._expanded_items.add(self.dm.inventory.items[1]["id"])
            inv._refresh()
            self.capture(f"{mode}-inventory-expanded")
        if key == "settings":
            scroll = self.mw._workspace._settings_panel.findChild(QScrollArea)
            bar = scroll.verticalScrollBar()
            for fraction in (0.5, 1.0):
                bar.setValue(int(bar.maximum() * fraction))
                self.capture(f"{mode}-settings-{fraction}")
            bar.setValue(0)

    def _run_narrow(self, mode: str) -> None:
        """窄窗口 + AI 面板：审查点名的那组压力场景。"""
        self.mw._workspace.switch_to("expenses")
        self.mw._on_ai_toggle(True)
        if mode == "light":
            self.mw._ai_panel.append_message("user", "请帮我整理今天的日程，保留晚上的休息时间。")
            # ⚠ 这里只放**像真的**回复：之前我编了一句 `使用 lookup_item … 查询物品。`，
            # 用户看截图时以为产品真的会输出这种无关提示（2026-10-18 反馈）✗
            self.mw._ai_panel.append_message(
                "ai", "已经把今天的三件事排好了，晚上的休息时间留着没排：\n"
                      "- 第 2 节：完成课程实验\n"
                      "- 第 4 节：复习英语\n"
                      "想调整时段直接说一声就行。")
        self.mw.resize(*NARROW)
        for key in ("expenses", "settings", "inventory"):
            self.mw._workspace.switch_to(key)
            self.capture(f"{mode}-narrow-{key}-ai")
        self.mw._on_ai_toggle(False)

    def run_panels(self) -> None:
        for mode in ("light", "dark"):
            self.mw._switch_theme(mode)
            self.mw._on_ai_toggle(False)
            self.mw.resize(*WIDE)
            for key in PANELS:
                self._run_panel(mode, key)
            self._run_narrow(mode)

    def _snap_and_close(self, name: str) -> None:
        """定时器回调：把当前可见对话框截图后**正常关闭**（让 `exec` 返回）。"""
        for w in self.app.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible():
                self.capture(name, w)
                w.close()
                w.deleteLater()
        self.settle()

    def run_dialogs(self) -> None:
        """普通对话框走 show/close；库存那两个内部是模态 `exec`，靠定时器关。"""
        from src.ui.panels import inventory_dialogs
        from src.ui.panels.exam_panel import ExamDialog
        from src.ui.panels.habit_panel import HabitDialog
        from src.ui.widgets.course_detail_dialog import CourseDetailDialog
        from src.ui.widgets.semester_dialog import SemesterDialog

        self.mw._switch_theme("light")
        for name, build in (("semester", lambda: SemesterDialog(self.dm)),
                            ("habit", lambda: HabitDialog(self.dm)),
                            ("exam", ExamDialog),
                            ("course", lambda: CourseDetailDialog(self.dm, "计算机系统结构"))):
            dlg = build()
            dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            dlg.show()
            self.capture(f"dialog-{name}", dlg)
            dlg.close()
            dlg.deleteLater()
            self.settle()

        QMessageBox.information = lambda *a: None    # 只是别让信息框挡住，不碰模态循环
        items = self.dm.inventory.items
        for name, call in (
                ("dialog-tags", lambda: inventory_dialogs.edit_tags_dialog(
                    self.mw, self.dm, items[0])),
                ("dialog-membership", lambda: inventory_dialogs.edit_membership_dialog(
                    self.mw, self.dm, items[-1]))):
            QTimer.singleShot(250, lambda n=name: self._snap_and_close(n))
            call()
            self.settle()

    def finish(self) -> None:
        """正常退出：让 Qt 自己收尾（原脚本用 `os._exit(0)` 硬退，必崩）。"""
        self.mw.close()
        self.app.processEvents()
        self.app.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="1", help="只用于命名（DPR 由 QT_SCALE_FACTOR 控制）")
    parser.add_argument("--out", default="", help="输出目录（默认 shots-<scale>）")
    args = parser.parse_args()

    out = Path(args.out) if args.out else ROOT / f"shots-{args.scale}"
    out.mkdir(parents=True, exist_ok=True)

    renderer = _Renderer(out)
    renderer.run_panels()
    renderer.run_dialogs()
    print(f"RENDER_DONE {renderer.shots} screenshots -> {out}", flush=True)
    renderer.finish()


if __name__ == "__main__":
    main()
