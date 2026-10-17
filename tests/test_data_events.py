"""数据事件 → 面板刷新的映射不漂移（审查 2026-10-17 #6）。

起因：`"semester"` 不在"全刷"集合里，而按**子串**匹配（`key in action`）又匹配不上任何
面板 → **切学期后作业/考试面板不刷新**，要等切页才更新。同类问题还有 `"saving"`
（存钱也显示在记账面板，却匹配不上）——而 `task_status` / `update_course` 只是**碰巧**
含了 `task` / `course` 才生效。

现在改成显式映射（`main_workspace.EVENT_PANELS`），本测试守住它：全仓
`data_changed.emit("…")` 用到的事件名都必须在表里登记。
"""

import re
from pathlib import Path

from src.ui.components.main_workspace import ALL_PANELS, EVENT_PANELS

SRC = Path(__file__).resolve().parent.parent / "src"

# 动态事件名（带 payload）—— 显式放行，别让新事件偷偷混进来。
# `fill_prompt:<文本>`：日程视图借 `data_changed` 传 AI 提示词，**不是数据变更**
# （而且全仓没有消费者）→ 待整改为专用信号，见 PLAN.md P19。
DYNAMIC_PREFIXES = ("fill_prompt:",)


def _emitted_events() -> set[str]:
    pattern = re.compile(r'data_changed\.emit\(\s*"([^"]*)"')
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def test_every_emitted_event_is_registered() -> None:
    emitted = _emitted_events()
    assert emitted, "一个事件都没扫到 —— 正则要改"
    unknown = {e for e in emitted
               if e not in EVENT_PANELS and not e.startswith(DYNAMIC_PREFIXES)}
    assert not unknown, f"这些事件没在 EVENT_PANELS 登记：{sorted(unknown)}"


def test_semester_switch_refreshes_tasks_and_exams() -> None:
    """审查报的漏刷：切学期必须让作业 / 考试面板刷新。"""
    assert {"task", "exam"} <= EVENT_PANELS["semester"]


def test_saving_refreshes_expense_panel() -> None:
    """`saving`（存钱）也显示在记账面板 —— 子串匹配时代它谁都匹配不上。"""
    assert "expense" in EVENT_PANELS["saving"]


def test_all_panels_covers_every_key_used_by_handler() -> None:
    """`ALL_PANELS` 必须覆盖 `_on_data_changed` 里用到的每个面板键。"""
    used = {"task", "expense", "habit", "exam", "inventory"}
    assert used <= ALL_PANELS
