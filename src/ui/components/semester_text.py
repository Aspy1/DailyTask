"""学期状态的**显示文案**（模型只产出问题码，翻译集中在 UI 层 —— `Q-N5`）。

`models/semester.py` 是纯函数、不产生用户可见文案；状态栏 / 课程表 / 对话框
都从这里取文案，保证同一状态在三处说法一致。
"""

from src.i18n.loader import tr
from src.models.semester import (
    STATE_ACTIVE,
    STATE_EXPIRED,
    STATE_INVALID,
    STATE_NONE,
    STATE_NOT_STARTED,
)

# 需要用户处理的三种状态（UI 用来标色 / 提示）
ALERT_STATES = frozenset({STATE_EXPIRED, STATE_INVALID, STATE_NOT_STARTED})


def semester_state_text(status: dict) -> str:
    """状态 → 一句文案。"""
    state = status.get("state", STATE_NONE)
    if state == STATE_ACTIVE:
        return tr("semester.state.active", week=status.get("week") or 1,
                  total=status.get("total_weeks") or "?")
    return {
        STATE_NONE: tr("semester.state.none"),
        STATE_INVALID: tr("semester.state.invalid"),
        STATE_NOT_STARTED: tr("semester.state.not_started"),
        STATE_EXPIRED: tr("semester.state.expired"),
    }.get(state, tr("semester.state.none"))


def issue_text(code: str) -> str:
    """问题码 → 文案（未知码原样返回，便于发现漏配的键）。"""
    return tr(f"semester.issue.{code}")
