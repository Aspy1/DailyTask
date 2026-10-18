"""日程视图右键菜单里的**动作**：弹窗与数据修改。

从 `schedule_view.py` 搬出来的原因：那个文件 969 行（超「单文件 ≤800」），
且 `_add_email_reminder_dialog` 单个函数 63 行（超「单函数 ≤60」）。
搬出后视图只留一行委托，动作本身在这里（纯 Qt 弹窗 + 数据写入）。

依赖方向：本模块不 import `schedule_view`（避免环），调用方把 `dm` / `parent` 传进来。
"""

import copy
import logging
from datetime import datetime, timedelta

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from src.i18n.loader import tr
from src.ui.styles.theme import get_colors
from src.ui.widgets.dialog_shell import action_row

logger = logging.getLogger(__name__)


def plans_snapshot(daily_logs) -> dict:
    """取 `plans` 的深拷贝（快速安排的撤销快照）。

    只记 `plans`，**不是**整份 `daily_logs.json` —— 撤销时不该连带回滚期间产生的
    打卡记录（`logs`）与自定义提醒（`reminders`）（审查 2026-10-17 #3）。
    """
    return copy.deepcopy(daily_logs.data.get("plans", {}))


def undo_arrange(parent, dm, before: dict | None, after: dict | None,
                 scope: tuple[str, ...] | list[str] | None = None) -> bool:
    """只回滚**本次安排覆盖的那些日期**，逐日校验冲突。返回是否真的回滚了。

    ⚠ 不能整体写回 `before`：等待 AI 的期间用户可能给**别的日期**加了计划，
    整体回滚会把那些无关计划一起删掉（审查 2026-10-17 #4）。
    ⚠ 写盘被拒（磁盘又被改动）→ 返回 `False`，让调用方**保留快照**以便重试（审查 #4）。
    """
    if before is None or after is None:
        QMessageBox.information(parent, tr("widget.schedule.msg_undo_title"),
                                tr("widget.schedule.msg_no_backup"))
        return False
    days = list(scope) if scope else sorted(set(before) | set(after))
    # 先按磁盘刷新：内存里可能还是安排前的旧值，直接写回会丢掉期间的其它改动
    dm.daily_logs.reload()
    plans = dm.daily_logs.data.get("plans", {})
    stale = [d for d in days if plans.get(d) != after.get(d)]
    if stale:
        # 这些日期在安排之后又被改过 → 拒绝，不动任何数据（不静默选一边）
        logger.warning("撤销被拒：这些日期在安排之后又被改过 %s", stale)
        QMessageBox.warning(parent, tr("widget.schedule.msg_undo_title"),
                            tr("widget.schedule.msg_undo_stale"))
        return False
    for day in days:
        if day in before:
            plans[day] = copy.deepcopy(before[day])
        else:
            plans.pop(day, None)      # 安排新增的那天 → 撤销就把它去掉
    saved = dm.daily_logs.save()
    if not saved:
        logger.warning("撤销写盘被拒（磁盘又被改动），保留快照以便重试")
        return False
    return True


def set_plan_category(dm, target_date, item: dict, category: str) -> bool:
    """按内容匹配把当天的某条计划标成学习 / 生活；返回是否找到。

    用户用例表第 13 条：规则给默认（`daily_log.plan_category`），**这里是他手动改**的入口
    —— 改过就存下来，以后以存的为准。
    """
    date_str = target_date.isoformat()
    for i, p in enumerate(dm.daily_logs.get_plans(date_str)):
        if p == item.get("plan"):
            dm.daily_logs.set_plan_category(date_str, i, category)
            dm.daily_logs.save()
            dm.data_changed.emit("plan")
            return True
    return False


def has_email_reminder(dm, item_type: str, item_name: str, item_date: str) -> bool:
    """该条目是否已有自定义邮件提醒。"""
    return dm.daily_logs.find_reminder(item_type, item_name, item_date) is not None


def remove_email_reminder(dm, item_type: str, item_name: str, item_date: str) -> None:
    """删除该条目的全部邮件提醒。"""
    if dm.daily_logs.delete_reminders_by_item(item_type, item_name, item_date) > 0:
        dm.daily_logs.save()


def delete_plan_at(dm, target_date, item: dict) -> bool:
    """按内容匹配删除当天的某条计划；返回是否删掉了。"""
    date_str = target_date.isoformat()
    plans = dm.daily_logs.get_plans(date_str)
    for i, p in enumerate(plans):
        if p == item.get("plan"):
            dm.daily_logs.delete_plan(date_str, i)
            dm.daily_logs.save()
            dm.data_changed.emit("plan")
            return True
    return False


def set_plan_done(dm, target_date, item: dict, done: bool) -> bool:
    """按内容匹配把当天的某条计划标记为**已完成 / 未完成**；返回是否找到。

    以前右键的「标记完成」直接**删掉**那条计划（看不出做过什么）。现在它是真的
    打 `done` 标记，卡片上会显示成已完成（用户口径 2026-10-18）。
    """
    date_str = target_date.isoformat()
    plans = dm.daily_logs.get_plans(date_str)
    for i, p in enumerate(plans):
        if p == item.get("plan"):
            dm.daily_logs.set_plan_done(date_str, i, done)
            dm.daily_logs.save()
            dm.data_changed.emit("plan")
            return True
    return False


def add_email_reminder_dialog(dm, parent, item_type: str, item_name: str,
                              item_date: str) -> None:
    """弹时间选择框，保存一条自定义邮件提醒。"""
    c = get_colors()
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("widget.schedule.dlg_add_email_reminder"))
    dlg.setMinimumWidth(320)
    dlg.setStyleSheet(f"""
        QDialog {{ background-color: {c['card_bg']}; }}
        QLabel {{ color: {c['fg_primary']}; font-size: 13px; }}
        QDateTimeEdit {{ background-color: {c['bg_elevated']}; color: {c['fg_primary']};
            border-radius: 8px; padding: 6px 10px; font-size: 13px; }}
        QPushButton {{ background-color: {c['accent']}; color: white; border: none;
            border-radius: 8px; padding: 6px 18px; font-size: 13px; font-weight: 600; }}
        QPushButton:hover {{ opacity: 0.9; }}
    """)
    layout = QVBoxLayout(dlg)
    layout.setSpacing(12)

    layout.addWidget(QLabel(tr("widget.schedule.dlg_email_for_item", name=item_name)))
    layout.addWidget(QLabel(tr("widget.schedule.dlg_email_date", date=item_date)))

    dt = QDateTimeEdit()
    # 日期控件固定 en_US 区域：本机 zh_HK 会让年份显示成 CJK 数字（ERRORS #036）
    dt.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    dt.setCalendarPopup(True)
    dt.setDateTime(_default_notify_datetime(item_date))
    dt.setDisplayFormat("yyyy-MM-dd HH:mm")
    layout.addWidget(dt)

    layout.addWidget(action_row(tr("widget.schedule.btn_confirm"), dlg.accept,
                                on_cancel=dlg.reject))

    if dlg.exec() == QDialog.DialogCode.Accepted:
        selected = dt.dateTime().toPython()
        if selected <= datetime.now():
            QMessageBox.warning(parent, tr("widget.schedule.msg_invalid_time_title"),
                                tr("widget.schedule.msg_invalid_time_body"))
            return
        dm.daily_logs.add_reminder(item_type, item_name, item_date, selected.isoformat())
        dm.daily_logs.save()


def _default_notify_datetime(item_date: str) -> datetime:
    """默认提醒时间：30 分钟后；若看的是未来日期，则用当天 08:00。"""
    default = datetime.now() + timedelta(minutes=30)
    try:
        target = datetime.fromisoformat(item_date + "T08:00:00")
        if target.date() > datetime.now().date():
            default = target
    # 边界捕获：item_date 可能是空/异常格式，退回"30 分钟后"即可
    except ValueError:
        logger.debug("默认提醒时间解析失败: %s", item_date, exc_info=True)
    return default
