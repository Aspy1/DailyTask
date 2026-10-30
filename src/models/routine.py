"""「近期安排」（每日固定任务）数据模型。

**不是习惯**（用户 2026-10-30 口径）：习惯是长期坚持、有连续天数；这里是
"备考六级 → 每天背单词"这类**有生命周期**的事 —— 考完就删掉，所以：
**不做连续天数** ✗，只记**每天**的三态（空 / ✔ / ✗）。

数据结构（`data/routines.json`）::

    {
      "_version": 1,
      "items": [{"id": "r_001", "title": "背单词", "note": "六级词汇 50 个",
                 "order": 0, "created_at": "..."}],
      "logs": {"2026-10-30": {"r_001": "done"}}
    }

`logs[日期][条目 id]` 只存**当天**做过的状态；某天没点就没有这个键（= 空态）。
"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.models.base import BaseJsonModel, next_id

DEFAULT_ROUTINES = {
    "_version": 1,
    "items": [],
    "logs": {},
}

# 三态：空 → ✔ → ✗ → 空（点一次/两次/三次，用户 2026-10-30 口径）
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"
NEXT_STATUS = {"": STATUS_DONE, STATUS_DONE: STATUS_SKIPPED, STATUS_SKIPPED: ""}

# 界面可以通过 `update_routine()` 改的字段（id / order 只能由模型自己维护）。
ROUTINE_FIELDS = ("title", "note")

logger = logging.getLogger(__name__)


def _today() -> str:
    return date.today().isoformat()


class RoutineModel(BaseJsonModel):
    """近期安排的条目 + 按天状态。"""

    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_ROUTINES)

    # ── 条目 ────────────────────────────────────────────────

    @property
    def items(self) -> list[dict]:
        """按 `order` 排好的条目（拖动排序直接改这个字段）。"""
        return sorted(self._data.get("items", []), key=lambda i: i.get("order", 0))

    @property
    def logs(self) -> dict:
        return self._data.setdefault("logs", {})

    def add(self, title: str, note: str = "") -> str:
        """新增一条，返回 id（排在最后）。"""
        items = self._data.setdefault("items", [])
        rid = next_id("r", (i.get("id", "") for i in items))
        order = max((i.get("order", 0) for i in items), default=-1) + 1
        items.append({
            "id": rid,
            "title": title,
            "note": note,
            "order": order,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        return rid

    def update_routine(self, rid: str, changes: dict[str, Any]) -> bool:
        """改标题 / 备注（只接受 `ROUTINE_FIELDS`；id / order 由模型自己维护）。"""
        for item in self._data.get("items", []):
            if item.get("id") == rid:
                for key, value in changes.items():
                    if key in ROUTINE_FIELDS:
                        item[key] = value
                return True
        return False

    def remove(self, rid: str) -> bool:
        items = self._data.get("items", [])
        for idx, item in enumerate(items):
            if item.get("id") == rid:
                items.pop(idx)
                self._renumber()
                return True
        return False

    def move(self, rid: str, new_index: int) -> bool:
        """把 `rid` 移到第 `new_index` 位（0 起）；越界自动夹到两端。"""
        items = self._data.get("items", [])
        ids = [i.get("id", "") for i in items]
        if rid not in ids:
            return False
        ids.remove(rid)
        target = max(0, min(new_index, len(ids)))
        ids.insert(target, rid)
        by_id = {i.get("id", ""): i for i in items}
        self._data["items"] = [by_id[i] for i in ids]
        self._renumber()
        return True

    def _renumber(self) -> None:
        for idx, item in enumerate(self._data.get("items", [])):
            item["order"] = idx

    # ── 按天状态 ────────────────────────────────────────────

    def status_on(self, rid: str, day: str | None = None) -> str:
        """某天的状态：`""`（空）/ `"done"` / `"skipped"`。"""
        return self.logs.get(day or _today(), {}).get(rid, "")

    def cycle_status(self, rid: str, day: str | None = None) -> str:
        """空 → ✔ → ✗ → 空，返回**切换后**的状态。"""
        day_log = self.logs.setdefault(day or _today(), {})
        nxt = NEXT_STATUS.get(day_log.get(rid, ""), "")
        if nxt:
            day_log[rid] = nxt
        else:
            day_log.pop(rid, None)
        return nxt

    def day_counts(self, day: str | None = None) -> dict[str, int]:
        """某天的 `{done, skipped, total}`（给工具栏计数用）。"""
        day_log = self.logs.get(day or _today(), {})
        total = len(self._data.get("items", []))
        done = sum(1 for v in day_log.values() if v == STATUS_DONE)
        skipped = sum(1 for v in day_log.values() if v == STATUS_SKIPPED)
        return {"done": done, "skipped": skipped, "total": total}
