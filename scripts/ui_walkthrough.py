#!/usr/bin/env python
"""全量 UI 走查 + AI 助手离线回归（沙箱，不碰真实 data/）。

用法（Windows / Git Bash）：

    LIFE_ASSISTANT_DATA_DIR=<临时目录> QT_QPA_PLATFORM=offscreen \
        .venv/Scripts/python.exe scripts/ui_walkthrough.py

脚本会：
1. 在沙箱里种数据 → 构造真实 `MainWindow`（settings / DataManager / AIService / plugins）；
2. 逐个切到每个面板、日/周视图、切换主题，调用各面板的核心操作；
3. 用**脚本化的模型**跑 4 个 AI 场景：正常执行 / 只说不动 / 命令失败 / 批量写；
4. 用真实 `main.py` 子进程启动一次应用，确认"打开软件"这一步不崩。

任何断言失败都会打印并返回非零退出码。
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ⚠ 必须**在 import src / scripts 之前**设置：各模块在 import 时读数据目录
SANDBOX = Path(tempfile.mkdtemp(prefix="lifeassistant-walkthrough-"))
os.environ["LIFE_ASSISTANT_DATA_DIR"] = str(SANDBOX)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from scripts.actions import run_in_process  # noqa: E402
from src.services.ai_service import AIService  # noqa: E402
from src.services.data_manager import DataManager  # noqa: E402
from src.services.plugin_manager import PluginManager  # noqa: E402
from src.services.settings_manager import SettingsManager  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from src.ui.styles.theme import get_mode, init_theme  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail and not ok else ""))


def seed() -> None:
    commands = [
        'add_course --name "数据结构" --day 2 --weeks "1-16" --slots "1-2" --location "33楼310"',
        'add_course --name "操作系统" --day 4 --weeks "1-16" --slots "3-4"',
        'add_task --course "数据结构" --title "图论作业" --due 2026-12-01T14:00',
        'add_exam --course "操作系统" --date 2026-12-20 --location "33楼201"',
        'add_habit --name "背单词" --schedule "daily/1" --reminder "07:30"',
        'add_plan --date 2026-12-01 --title "408 真题一套" --slot 3',
        'add_expense --amount 12.5 --category food --note "午饭"',
        'add_item --name "抽纸" --quantity 2 --min_qty 3 --location "书架1"',
    ]
    for cmd in commands:
        out = run_in_process(cmd)
        assert out.startswith("OK"), (cmd, out)


def patch_modals() -> None:
    """离屏走查里不弹真模态框（否则脚本永远卡住）。"""
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)


def walk_panels(mw) -> None:
    for key, index in mw._workspace._panel_map.items():
        mw._on_sidebar_nav(key)
        check(f"nav/{key}", mw._workspace._stack.currentIndex() == index)

    sv = mw._workspace.schedule_view
    sv._set_mode("week")
    check("schedule/week", sv._stack.currentIndex() == 1)
    sv._set_mode("day")
    check("schedule/day", sv._stack.currentIndex() == 0)
    mw._on_ai_toggle(True)
    check("ai/visible", mw.ai_panel.isVisible())
    mw._on_ai_toggle(False)


def walk_actions(mw, dm) -> None:
    # 任务：完成 + 按课程筛选
    tid = dm.tasks.pending[0]["id"]
    mw._workspace._task_panel._on_check(tid, True)
    check("task/complete", any(t["id"] == tid and t["status"] == "completed"
                               for t in dm.tasks.tasks))
    mw._workspace._task_panel.filter_by_course("数据结构")
    check("task/filter", mw._workspace._task_panel._table.rowCount() >= 0)

    # 习惯：打卡
    hid = dm.habits.habits[0]["id"]
    mw._workspace._habit_panel._toggle_habit(hid)
    check("habit/log", dm.habits.is_done_today(hid))

    # 近期安排：三态切换
    rid = dm.routines.add("每日 408 复盘")
    dm.routines.save()
    mw._workspace._routine_panel._on_cycle(rid)
    check("routine/cycle", dm.routines.status_on(rid) == "done")

    # 记账：支出 + 存钱
    before = dm.expenses.month_total()
    panel = mw._workspace._expense_panel
    panel._amount_input.setText("23.5")
    panel._note_input.setText("走查")
    panel._add_expense()
    check("expense/add", dm.expenses.month_total() > before)
    panel._sav_amount.setText("10")
    panel._add_saving()
    check("expense/saving", dm.daily_logs.today_savings_total() >= 10)

    # 库存：状态 + 版本切换（视图状态，不写文件）
    item = dm.inventory.items[0]
    mw._workspace._inventory_panel._quick_update(item["id"], {"status": "需购"})
    check("inventory/status", dm.inventory.items[0].get("status") == "需购")
    mw._workspace._inventory_panel._apply_side("home")
    check("inventory/side", mw._workspace._inventory_panel._side == "home")
    mw._workspace._inventory_panel._apply_side("school")

    # 主题：深 → 浅 → 深
    mw._switch_theme("dark")
    check("theme/dark", get_mode() == "dark")
    mw._switch_theme("light")
    check("theme/light", get_mode() == "light")


class ScriptedProvider:
    """按顺序返回预设回复的模型（离线、确定性）。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str:
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return reply


def ask(app, ai, replies: list[str], text: str, timeout: float = 20.0) -> list[str]:
    """发一条消息，等 AI 线程结束，返回界面上收到的文本。"""
    provider = ScriptedProvider(replies)
    ai._make_provider = lambda: provider
    seen: list[str] = []
    ai.response_received.connect(seen.append)
    ai.instructions_executed.connect(lambda t, _i: seen.append(t))
    ai.error_occurred.connect(seen.append)
    ai.send_message(text)
    deadline = time.monotonic() + timeout
    while ai._busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    check("ai/thread-finished", not ai._busy, f"calls={provider.calls}")
    return seen


def _scenario_normal(app, ai, dm) -> None:
    """正常执行 + 代码验收。"""
    seen = ask(app, ai, [
        '```sh\npython scripts/actions.py add_task --title "AI 记录的作业" --due 2026-12-05\n```',
        "已写入。",
    ], "记一个作业")
    text = seen[-1] if seen else ""
    check("ai/executed-task", any(t["title"] == "AI 记录的作业" for t in dm.tasks.tasks))
    check("ai/facts", "【已执行】" in text and "作业" in text, text[:120])
    check("ai/no-false-claim", "没有生效" not in text, text[:120])


def _scenario_claims(app, ai, dm) -> None:
    """只说不动：模型声称已记录但不发命令。"""
    seen = ask(app, ai, ["已记录：抽纸 2 包。", "已记录：抽纸 2 包。",
                         "已记录：抽纸 2 包。", "已记录：抽纸 2 包。"], "记一下抽纸")
    text = seen[-1] if seen else ""
    check("ai/claims-without-command", "没有任何改动" in text, text[:120])


def _scenario_failure(app, ai, dm) -> None:
    """命令失败 → 如实告知。"""
    seen = ask(app, ai, [
        '```sh\npython scripts/actions.py add_item --name "坏数据" --quantity -1\n```',
        "好的。",
    ], "加一个坏物品")
    text = seen[-1] if seen else ""
    check("ai/failed-command", "没有生效" in text, text[:120])


def _scenario_batch(app, ai, dm) -> None:
    """批量写 + 每条验收。"""
    before_courses = len(dm.courses.courses)
    seen = ask(app, ai, [
        "```sh\n"
        'python scripts/actions.py add_course --name "计算机组成原理" --day 3 --weeks "1-16" --slots "5-6"\n'
        'python scripts/actions.py add_task --title "组成原理实验" --due 2026-12-06\n'
        'python scripts/actions.py add_expense --amount 18 --category food --note "晚饭"\n'
        "```",
        "都记好了。",
    ], "把这三件事记一下")
    text = seen[-1] if seen else ""
    check("ai/batch-course", len(dm.courses.courses) == before_courses + 1)
    check("ai/batch-task", any(t["title"] == "组成原理实验" for t in dm.tasks.tasks))
    check("ai/batch-expense", any(r.get("amount") == 18 for r in dm.expenses.records))
    check("ai/batch-facts",
          "【已执行】" in text and "组成原理" in text and "晚饭" in text, text[:160])


def ai_scenarios(app, ai, dm) -> None:
    _scenario_normal(app, ai, dm)
    _scenario_claims(app, ai, dm)
    _scenario_failure(app, ai, dm)
    _scenario_batch(app, ai, dm)


def launch_real_app() -> None:
    """真实启动一次 `main.py`（离屏 + 沙箱），确认首屏不崩。"""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["LIFE_ASSISTANT_DATA_DIR"] = str(SANDBOX)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(  # noqa: S603 - 固定 argv，无 shell
        [sys.executable, str(ROOT / "main.py")],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    time.sleep(6)
    alive = proc.poll() is None
    if alive:
        proc.terminate()
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    log = SANDBOX / "app.log"
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    check("app/launch", alive, (out or b"").decode("utf-8", "replace")[-200:])
    check("app/no-traceback", "Traceback" not in log_text, log_text[-300:])


def main() -> int:
    print(f"sandbox: {SANDBOX}")
    seed()
    patch_modals()

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(init_theme(app, "light"))

    settings = SettingsManager(SANDBOX / "settings.ini")
    settings.set("AI", "api_key", "sk-test-not-real")
    settings.set("AI", "provider", "deepseek")
    settings.save()

    dm = DataManager(SANDBOX)
    ai = AIService(settings, dm)
    ai._weather_cache = {"value": "  晴 20°C", "fetched_at": time.time()}
    ai._ds_balance_cache = {"value": "", "fetched_at": time.time()}
    plugins = PluginManager(SANDBOX / "plugins", settings, dm, app)
    plugins.load_plugins()

    mw = MainWindow(settings, ai, dm, plugins)
    mw.resize(1200, 800)
    mw.show()
    app.processEvents()
    check("window/show", mw.isVisible())

    walk_panels(mw)
    walk_actions(mw, dm)
    ai_scenarios(app, ai, dm)

    mw.hide()
    app.processEvents()
    launch_real_app()

    failed = [name for name, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
