"""Exam model — stores exam dates and related info."""

from pathlib import Path
from datetime import datetime

from src.models.base import BaseJsonModel

DEFAULT_EXAMS = {
    "_version": 1,
    "exams": [],
}


class ExamModel(BaseJsonModel):
    def __init__(self, file_path: Path):
        super().__init__(file_path, DEFAULT_EXAMS)

    @property
    def exams(self) -> list[dict]:
        return self._data.get("exams", [])

    def add_exam(self, data: dict) -> str:
        exams = self._data.setdefault("exams", [])
        # Generate unique ID
        existing = set()
        for e in exams:
            try:
                num = int(e["id"].split("_")[1])
                existing.add(num)
            except (KeyError, ValueError):
                pass
        n = 1
        while n in existing:
            n += 1
        eid = f"e_{n:03d}"
        exam = {
            "id": eid,
            "course_name": data.get("course_name", ""),
            "exam_date": data.get("exam_date", ""),
            "scope": data.get("scope", ""),
            "location": data.get("location", ""),
            "notes": data.get("notes", ""),
            "tags": data.get("tags", []),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        exams.append(exam)
        return eid

    def update_exam(self, eid: str, data: dict) -> bool:
        for e in self.exams:
            if e["id"] == eid:
                for k in ("course_name", "exam_date", "scope", "location", "notes", "tags"):
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
