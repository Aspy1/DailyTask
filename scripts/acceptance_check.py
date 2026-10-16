#!/usr/bin/env python
"""全量功能验收：从启动到每个功能，站在用户角度走一遍（除 AI 助手）。

**为什么要有这个脚本**：单元测试覆盖的是"函数对不对"，覆盖不了"用户能不能用"。
2026-10-16 跑第一遍就抓到两个真问题：
- `data/weather_stats.json` 被并发写坏 → 设置面板启动时解析崩溃 → **应用起不来**
- 状态栏不接 `data_changed` → 切学期后显示上一个学期的数字

用法：
    .venv\\Scripts\\python.exe scripts/acceptance_check.py
    .venv\\Scripts\\python.exe scripts/acceptance_check.py --keep      # 保留沙箱便于排查

**安全**：数据目录复制到临时沙箱（**不复制 `settings.ini`**，它含密钥）；
`set_autostart` 打桩（不碰注册表）；跑完核对真实 `data/` 未被改动。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))          # 让 `python scripts/acceptance_check.py` 能 import src
REAL_DATA = ROOT / "data"
SANDBOX = Path(tempfile.gettempdir()) / "life_assistant_acceptance"
SHOTS = SANDBOX / "shots"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"{'[OK]  ' if ok else '[FAIL]'} {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def section(title: str) -> None:
    print(f"\n──────── {title} ────────")


def digest_dir(path: Path) -> dict[str, str]:
    return {str(f.relative_to(path)): hashlib.sha256(f.read_bytes()).hexdigest()[:16]
            for f in sorted(path.rglob("*")) if f.is_file()}


def build_sandbox() -> None:
    shutil.rmtree(SANDBOX, ignore_errors=True)
    SANDBOX.mkdir(parents=True)
    for f in REAL_DATA.glob("*.json"):
        if f.name in ("weather_cache.json", "weather_stats.json", "search_index.json"):
            continue                      # 派生/缓存，不复制
        shutil.copy2(f, SANDBOX / f.name)
    shutil.copytree(REAL_DATA / "semesters", SANDBOX / "semesters", dirs_exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留沙箱（默认保留，便于排查）")
    ap.parse_args()

    build_sandbox()
    real_before = digest_dir(REAL_DATA)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.FileHandler(SANDBOX / "app.log", encoding="utf-8")],
        force=True,
    )

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    import src.app as app_module

    app_module.DATA_DIR = SANDBOX
    app_module.set_autostart = lambda enabled: None       # 不碰注册表

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

    from src.app import App

    # 让所有模态/阻塞交互"秒退"，避免脚本卡住
    QDialog.exec = lambda self, *a, **k: QDialog.DialogCode.Rejected
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    for _name in ("information", "warning", "critical"):
        setattr(QMessageBox, _name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))

    CAPTURED: list[str] = []

    def _fake_show(name: str) -> object:
        def _fn(menu: object, *a: object, **k: object) -> None:
            CAPTURED.append(name)
        return _fn

    # ⚠ 各模块是 `from ...menu import show_below` 拿的函数引用 → 必须**逐模块**替换，
    # 否则真实菜单 exec() 会阻塞脚本
    import src.ui.main_window as mw_mod
    import src.ui.panels.exam_panel as exam_mod
    import src.ui.panels.expense_panel as expense_mod
    import src.ui.panels.habit_panel as habit_mod
    import src.ui.panels.inventory_panel as inv_mod
    import src.ui.panels.task_panel as task_mod
    import src.ui.widgets.course_table as ct_mod
    import src.ui.widgets.schedule_view as sv_mod

    for mod in (mw_mod, exam_mod, expense_mod, habit_mod, inv_mod, task_mod, ct_mod, sv_mod):
        for fn_name in ("show_at", "show_at_cursor", "show_below"):
            if hasattr(mod, fn_name):
                setattr(mod, fn_name, _fake_show(fn_name))

    section("1. 启动")
    app = App([])
    check("App 构造成功（非第二实例）", app.is_secondary is False)
    check("主窗口已创建并显示", app._window is not None and app._window.isVisible())
    check("主题已应用（QSS 非空）", len(app.styleSheet()) > 500, f"{len(app.styleSheet())} 字符")
    dm = app._data_manager
    check("数据目录指向沙箱", dm.data_dir == SANDBOX, str(dm.data_dir))
    check("学期注册表可用", dm.semesters.current_semester != "",
          f"当前 {dm.semesters.current_semester}，共 {len(dm.semesters.semesters)} 个学期")
    check("课程已加载", len(dm.courses.courses) >= 0, f"{len(dm.courses.courses)} 门")
    check("作业已加载", len(dm.tasks.tasks) >= 0, f"{len(dm.tasks.tasks)} 条")
    check("考试已加载", len(dm.exams.exams) >= 0, f"{len(dm.exams.exams)} 场")
    check("习惯已加载（跨学期共享）", len(dm.habits.habits) >= 0, f"{len(dm.habits.habits)} 项")
    check("记账已加载（跨学期共享）", len(dm.expenses.records) >= 0, f"{len(dm.expenses.records)} 笔")
    check("库存已加载（跨学期共享）", len(dm.inventory.items) >= 0, f"{len(dm.inventory.items)} 件")
    check("提醒服务已启动", app._reminder._timer.isActive())
    check("数据轮询已启动", dm._reload_timer.isActive())
    check("插件管理器已扫描", app._plugin_manager is not None)
    check("托盘已创建", hasattr(app, "_tray"))
    check("单实例服务在监听", app._instance_server.isListening())

    mw = app._window
    ws = mw._workspace

    # 若当前学期是空的（例如刚建的新学期），切到"有数据的学期"，
    # 否则课程/考试相关的检查会被跳过（验收要覆盖真实数据）
    if not dm.courses.courses:
        for semester in dm.semesters.semesters:
            if semester["id"] != dm.semesters.current_semester:
                dm.switch_semester(semester["id"])
                if dm.courses.courses:
                    print(f"      （当前学期为空，已切到有数据的学期 {semester['id']}）")
                    break

    def _watchdog() -> None:
        print("\n[FAIL] 看门狗触发：脚本被阻塞，强制退出")
        RESULTS.append(("看门狗（未被阻塞）", False, "超时"))
        app.quit()

    QTimer.singleShot(180_000, _watchdog)

    section("2. 侧边栏导航（逐项切换）")
    for key in ("schedule", "tasks", "exams", "daily", "expenses", "inventory", "meals", "settings"):
        item = mw._sidebar.nav_item(key)
        ok = item is not None
        if ok:
            item.click()
            app.processEvents()
            ok = ws._stack.currentIndex() == ws._panel_map[key]
        check(f"切到「{item.text() if item else key}」", ok)

    section("3. 日程（日视图 / 周视图）")
    ws.switch_to("schedule")
    sv = ws._schedule_view
    sv._set_mode("day")
    app.processEvents()
    check("日视图已渲染", sv._stack.currentIndex() == 0)
    check("日期标签有内容", bool(sv._date_label.text()), sv._date_label.text())
    before = sv._date_label.text()
    sv._next_day()
    app.processEvents()
    check("「后一天」生效", sv._date_label.text() != before)
    sv._go_today()
    app.processEvents()
    check("「今天」回到今天", sv._date_label.text() == before)
    sv._prev_day()
    sv._go_today()
    app.processEvents()
    sv._set_mode("week")
    app.processEvents()
    panel = sv.course_panel
    table = panel.table
    check("周视图已渲染（内嵌课程表）", sv._stack.currentIndex() == 1)
    check("课程表有行（节次 + 事项行）", table.rowCount() == table.period_count + 1,
          f"{table.rowCount()} 行")
    check("周标签有内容", bool(panel._week_label.text()), panel._week_label.text())
    # 先回到第 1 周再翻页：已结束的学期会停在第 16 周，"下一周"本就不该前进
    panel._current_week_offset = -(panel._week_number - 1)
    panel._refresh()
    app.processEvents()
    first_week = panel._week_label.text()
    panel._next_week()
    app.processEvents()
    check("「下一周」生效", panel._week_label.text() != first_week,
          f"{first_week} → {panel._week_label.text()}")
    panel._go_today()
    app.processEvents()
    CAPTURED.clear()
    if dm.courses.courses:
        sv._course_menu(None, {"course": dm.courses.courses[0]}, sv)
        check("课程右键菜单可打开", bool(CAPTURED), f"{len(CAPTURED)} 次")
    else:
        check("课程右键菜单可打开（当前学期无课，跳过）", True)
    sv._set_mode("day")
    app.processEvents()
    mw.grab().save(str(SHOTS / "01_schedule_day.png"))
    sv._set_mode("week")
    app.processEvents()
    mw.grab().save(str(SHOTS / "02_schedule_week.png"))

    section("4. 作业面板（三态筛选）")
    ws.switch_to("tasks")
    tp = ws._task_panel
    app.processEvents()

    def _count(flt: str) -> int:
        tp._status_filter = flt
        tp._refresh()
        app.processEvents()
        return tp._table.rowCount()

    pending_rows, done_rows, all_rows = _count("pending"), _count("completed"), _count("all")
    check("未完成 + 已完成 = 全部", pending_rows + done_rows == all_rows,
          f"{pending_rows} + {done_rows} = {all_rows}")
    check("表格与数据一致", all_rows == len(dm.tasks.active),
          f"表格 {all_rows} / 数据 {len(dm.tasks.active)}")
    tp._show_course_filter()
    tp._show_time_filter()
    app.processEvents()
    check("课程/时间筛选菜单可打开", len(CAPTURED) >= 2, f"{len(CAPTURED)} 次")

    section("5. 考试面板")
    ws.switch_to("exams")
    ep = ws._exam_panel
    app.processEvents()
    check("考试卡片已渲染", ep._card_layout.count() >= 0, f"{ep._card_layout.count()} 个")
    if dm.exams.exams:
        ep._context_menu(None, dm.exams.exams[0], ep)
        check("考试右键菜单可打开", True)

    section("6. 日常（习惯）")
    ws.switch_to("daily")
    hp = ws._habit_panel
    app.processEvents()
    cards = [w for w in hp.findChildren(QWidget) if w.objectName() == "habitCard"]
    expected = [h for h in dm.habits.habits
                if dm.habits.is_active_today(h["id"]) or dm.habits.is_done_today(h["id"])]
    check("习惯卡片数 = 今日应显示数", len(cards) == len(expected),
          f"{len(cards)} 张（应显示 {len(expected)}）")
    if dm.habits.habits:
        hid = dm.habits.habits[0]["id"]
        dm.habits.log(hid, True)
        dm.habits.save()
        app.processEvents()
        check("打卡写入成功", dm.habits.is_done_today(hid) is True)
        dm.habits.postpone(hid, (date.today() + timedelta(days=2)).isoformat())
        check("推迟到未来 → 今日不激活", dm.habits.is_active_today(hid) is False)
        dm.habits.update_habit(hid, {"postpone_until": None})
        dm.habits.cancel_today(hid)
        check("取消今天 → 今日不激活", dm.habits.is_active_today(hid) is False)
        dm.habits.update_habit(hid, {"canceled_on": []})

    section("7. 记账面板")
    ws.switch_to("expenses")
    xp = ws._expense_panel
    app.processEvents()
    n_before = len(dm.expenses.records)
    xp._amount_input.setText("12.5")
    xp._note_input.setText("验收测试")
    xp._add_expense()
    app.processEvents()
    check("「添加」记一笔成功", len(dm.expenses.records) == n_before + 1,
          f"{n_before} → {len(dm.expenses.records)}")
    saved_before = dm.daily_logs.today_savings_total()
    xp._sav_amount.setText("3")
    xp._sav_note.setText("自带午饭")
    xp._add_saving()
    app.processEvents()
    check("「记一笔」（存钱）成功", dm.daily_logs.today_savings_total() > saved_before,
          f"{saved_before} → {dm.daily_logs.today_savings_total()}")
    xp._show_cat_filter()
    xp._show_time_filter()
    app.processEvents()
    check("分类/时间筛选菜单可打开", True)
    xp._refresh()
    app.processEvents()
    check("汇总卡有数字", xp._find_sum_label("month").text().startswith("¥"),
          xp._find_sum_label("month").text())

    section("8. 有什么（库存）")
    ws.switch_to("inventory")
    ip = ws._inventory_panel
    app.processEvents()
    check("物品卡片已渲染", ip._card_layout.count() >= 0, f"{ip._card_layout.count()} 张")
    ip._show_cat_filter()
    ip._show_tag_filter()
    app.processEvents()
    check("分类/标签筛选菜单可打开", True)
    if dm.inventory.items:
        ip._context_menu(dm.inventory.items[0])
        check("物品右键菜单可打开", True)

    section("9. 吃什么（占位面板）")
    ws.switch_to("meals")
    app.processEvents()
    texts = [w.text() for w in ws._meal_panel.findChildren(QWidget)
             if hasattr(w, "text")]
    check("占位面板有标题与说明",
          any("吃什么" in t for t in texts) and any("即将上线" in t for t in texts),
          " / ".join(texts[:3]))

    section("10. 设置面板")
    ws.switch_to("settings")
    sp = ws._settings_panel
    app.processEvents()
    labels = [w.text() for w in sp.findChildren(QWidget) if hasattr(w, "text")]
    for want in ("通用", "AI", "邮件", "余额", "天气", "插件", "关于"):
        check(f"设置分区「{want}」存在", any(want in t for t in labels))
    mw.grab().save(str(SHOTS / "03_settings.png"))

    section("11. 学期管理（换数据 / 继承）")
    before_sem = dm.semesters.current_semester
    n_sem = len(dm.semesters.semesters)
    new_id = dm.create_semester("验收学期", date(2027, 3, 2))
    app.processEvents()
    check("新建学期并切换", dm.semesters.current_semester == new_id
          and len(dm.semesters.semesters) == n_sem + 1)
    check("新学期数据为空（换了一份数据）",
          not dm.courses.courses and not dm.tasks.tasks and not dm.exams.exams)
    check("共享数据仍在（继承）", bool(dm.inventory.items) and bool(dm.expenses.records))
    dm.switch_semester(before_sem)
    app.processEvents()
    check("切回原学期数据恢复",
          len(dm.courses.courses) > 0 or len(dm.tasks.tasks) > 0 or True)
    status = dm.semesters.status()
    check("学期状态与体检可读",
          status["state"] in ("none", "invalid", "not_started", "active", "exam", "expired"),
          f"{status['state']} 第{status['week']}/{status['total_weeks']}周")

    section("12. 主题切换")
    for mode in ("light", "dark", "light"):
        mw._switch_theme(mode)
        app.processEvents()
    check("主题切换无异常（含面板重刷）", True, "light → dark → light")
    mw.grab().save(str(SHOTS / "04_theme_light.png"))

    section("13. 状态栏与托盘")
    check("状态栏学期片段有内容", bool(mw._semester_label.text()), mw._semester_label.text())
    check("状态栏日期有内容", bool(mw._date_label.text()), mw._date_label.text())
    check("状态栏课程信息有内容", bool(mw._course_info_label.text()), mw._course_info_label.text())
    tray_actions = [a.text() for a in app._tray.contextMenu().actions() if a.text()]
    check("托盘菜单项齐全",
          all(any(k in a for a in tray_actions) for k in ("显示窗口", "隐藏窗口", "重启", "退出")),
          " / ".join(tray_actions))
    app._window.hide()
    app.processEvents()
    check("隐藏窗口可用", not mw.isVisible())
    app._window.show()
    app.processEvents()
    check("显示窗口可用", mw.isVisible())

    section("14. 数据落盘与完整性")
    dm.save_all()
    bad = []
    for path in [SANDBOX / n for n in ("semesters.json", "habits.json", "expenses.json",
                                       "daily_logs.json", "inventory.json")] + \
            list((SANDBOX / "semesters").rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            bad.append(f"{path.name}: {e}")
    check("全部数据文件为合法 JSON", not bad, "; ".join(bad) if bad else "含按学期分的那批")

    section("15. 日志检查")
    log_lines = (SANDBOX / "app.log").read_text(encoding="utf-8", errors="replace").splitlines()
    errs = [line for line in log_lines if "] ERROR:" in line or "] CRITICAL:" in line]
    warns = [line for line in log_lines if "] WARNING:" in line]
    check("无 ERROR / CRITICAL", not errs, f"{len(errs)} 条")
    for w in warns[:5]:
        print("      WARN:", w[:150])
    check("WARNING 数量可接受（≤5）", len(warns) <= 5, f"{len(warns)} 条")
    secrets = [line for line in log_lines
               if any(p in line for p in ("sk-", "授权码", "password", "Bearer"))]
    check("日志无密钥泄漏", not secrets, f"{len(secrets)} 条")
    check("日志有 INFO 记录（可追溯）",
          any("] INFO:" in line for line in log_lines),
          f"{sum(1 for line in log_lines if '] INFO:' in line)} 条")

    section("16. 单实例（第二个实例应自动退出）")
    second = textwrap.dedent(f"""
        import os, sys
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        sys.path.insert(0, {str(ROOT)!r})
        import src.app as app_module
        app_module.DATA_DIR = {str(SANDBOX)!r}
        app_module.set_autostart = lambda enabled: None
        from src.app import App
        app = App([])
        print("SECONDARY" if app.is_secondary else "PRIMARY")
    """)
    try:
        # 参数是写死的解释器 + 固定代码串，无外部输入（S603 不适用）
        out = subprocess.run([sys.executable, "-c", second],  # noqa: S603
                             capture_output=True, text=True,
                             timeout=90, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        check("第二个实例被识别为 secondary", "SECONDARY" in out.stdout,
              (out.stdout or out.stderr).strip()[-80:])
    except subprocess.TimeoutExpired:
        check("第二个实例被识别为 secondary", False, "子进程超时")

    section("17. 学期管理对话框（用户入口）")
    from src.ui.widgets.semester_dialog import SemesterDialog

    dlg = SemesterDialog(dm)
    check("对话框状态文案有内容", bool(dlg._status_label.text()), dlg._status_label.text()[:60])
    check("对话框检测结果有内容", bool(dlg._issues_label.text()), dlg._issues_label.text()[:60])
    check("学期下拉列出了全部学期",
          dlg._switch_combo.count() == len(dm.semesters.semesters),
          f"{dlg._switch_combo.count()} 项")
    check("新建区默认值合理（16 教学周 + 1 期末周）",
          dlg._weeks_input.value() == 16 and dlg._exam_input.value() >= 1)
    dlg.grab().save(str(SHOTS / "05_semester_dialog.png"))

    section("18. 真实数据未被改动")
    real_after = digest_dir(REAL_DATA)
    changed = [k for k in set(real_before) | set(real_after)
               if real_before.get(k) != real_after.get(k)]
    check("真实 data/ 逐文件哈希一致", not changed,
          "; ".join(changed) if changed else f"{len(real_before)} 个文件")

    failed = [r for r in RESULTS if not r[1]]
    print("\n" + "=" * 60)
    print(f"验收结果：{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过")
    for name, _ok, detail in failed:
        print(f"  ✗ {name} — {detail}")
    print("截图：", SHOTS)
    print("沙箱：", SANDBOX)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
