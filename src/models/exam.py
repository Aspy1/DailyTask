"""Exam model — stores exam dates and related info."""

import logging
from datetime import datetime
from pathlib import Path

from src.models.base import BaseJsonModel, next_id

DEFAULT_EXAMS = {
    "_version": 1,
    "exams": [],
}

# 考试的可写字段（**唯一清单**）—— `add_exam` / `update_exam` 都读它，不许各写一份 ✗。
# 为什么：`inventory.py` 就是吃了这个亏（2026-10-19：两份白名单漂移 → 会员弹窗存不上 ✗）。
EXAM_FIELDS = ("course_name", "exam_date", "scope", "location", "notes", "tags")


logger = logging.getLogger(__name__)


class ExamModel(BaseJsonModel):
    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_EXAMS)

    @property
    def exams(self) -> list[dict]:
        return self._data.get("exams", [])

    def add_exam(self, data: dict) -> str:
        exams = self._data.setdefault("exams", [])
        # 统一走 `next_id()`（最大后缀 +1）：删过考试后不能复用旧 id，
        # 否则提醒去重集合 / 备份回执会指向另一场考试（同 R-008）。
        eid = next_id("e", (e.get("id", "") for e in exams))
        exam = {"id": eid}
        for k in EXAM_FIELDS:
            exam[k] = data.get(k, [] if k == "tags" else "")
        exam["created_at"] = datetime.now().isoformat()
        exam["updated_at"] = datetime.now().isoformat()
        exams.append(exam)
        return eid

    def update_exam(self, eid: str, data: dict) -> bool:
        for e in self.exams:
            if e["id"] == eid:
                for k in EXAM_FIELDS:
                    if k in data:
                        e[k] = data[k]
                e["updated_at"] = datetime.now().isoformat()
                return True
        return False

    def delete_exam(self, eid: str) -> bool:
        exams = self._data.get("exams", [])
        for i, e in enumerate(exams):
            if e["id"] == eid:
                exams.pop(i)
                return True
        return False

    def get_upcoming(self, limit: int = 10) -> list[dict]:
        from datetime import date
        today = date.today().isoformat()
        upcoming = [e for e in self.exams if e.get("exam_date", "") >= today]
        upcoming.sort(key=lambda x: x.get("exam_date", ""))
        return upcoming[:limit]
