# 2026-10-18/19 测试的"今天"要用 `schedule_date()`，不是 `date.today()`

## 现象

2026-10-19 **00:30** 本地跑 `pytest` → **5 个测试红** ✗，而 **CI 全绿** ✓（CI 跑 UTC，不在这个时段）。
用 `git stash` 回到改动前验证 → **同样红** ✓ → 与当天改动无关 ✓。

```
tests/test_reminder_exams.py（3 个）
tests/test_ui_fixes.py::test_statusbar_refreshes_on_data_changed
tests/test_course_conflicts.py::test_day_view_warns_about_conflict
```

## 根因

```python
# src/models/course.py
def schedule_date() -> date:
    """Effective date: 0:00–1:00 AM still counts as the previous day."""
    now = datetime.now()
    if now.hour < 1:
        return (now - timedelta(days=1)).date()      # ← 凌晨 1 点前算**前一天**
    return now.date()
```

这是**有意设计**（凌晨还在学的那个晚上算"今天"）✓，生产代码到处用它 ✓；
而**测试**用的是 `date.today()` ✗ → 在 **00:00–01:00** 这段里两者差一天 ✗ →
"考试 14 天提醒"被算成 15 天 ✗ → 阈值不命中 ✗。

## 修法

测试改成**与生产同源**：`date.today()` → `schedule_date()` ✓
（`test_reminder_exams.py` 的 `_add_exam`、`test_ui_fixes.py` 的 `_monday`、
`test_course_conflicts.py` 的三处 ✓）。

⚠ **一处例外**：`test_habit_panel_shows_empty_hint` 里"不是今天的星期"要按**真实今天**算 ✓
—— 习惯面板用的是真实今天，不是"日程的有效今天" ✗（改错了会红 ✓）。

## 教训

1. **测试与生产必须用同一个"今天"** ✗ —— 两边各写一个 `date.today()` 就是两颗定时炸弹 ✓
2. **本地红 / CI 绿** 的第一嫌疑是**时区与时段**（CI 跑 UTC ✗）
3. 判定"是不是我弄的"最省事的办法：`git stash` 回到改动前跑一遍 ✓（这次 30 秒就排除了 ✓）
4. 附带：`sed -i 's/.../.../'` 批量替换**踩了坑** ✗ —— 把 `from datetime import date, timedelta`
   截成了 `from datetime import date` + 把 `timedelta` 塞进了另一个 import ✗。批量替换要看**整行** ✓。

## 验证
**627 passed**（本地 00:xx，正是之前红的时段 ✓）；门禁全绿；CI 三 job 全绿。
