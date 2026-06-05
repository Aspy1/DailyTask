"""Task data model."""

from datetime import datetime, timedelta
from pathlib import Path

from src.models.base import BaseJsonModel


DEFAULT_TASKS = {
    "_version": 2,
    "tasks": [],
    "archived": [],
}


class TaskModel(BaseJsonModel):
    GENERIC_TAGS = {"作业", "考试", "pre", "ppt", "报告", "复习", "项目", "论文", "实验", "小组作业"}

    def __init__(self, file_path: Path):
        super().__init__(file_path, DEFAULT_TASKS)
        self._auto_archive()
        self._repair_course_names()

    def _repair_course_names(self) -> None:
        changed = False
        for t in self._data.get("tasks", []):
            if t.get("course_name"):
                continue
            tags = t.get("tags", [])
            for tag in tags:
                if tag not in self.GENERIC_TAGS:
                    t["course_name"] = tag
                    changed = True
                    break
            if not t.get("course_name"):
                title = t.get("title", "")
                for tag in tags:
                    if tag in title and tag not in self.GENERIC_TAGS:
                        t["course_name"] = tag
                        changed = True
                        break
        if changed:
            self.save()

    @property
    def tasks(self) -> list[dict]:
        return self._data.get("tasks", [])

    @property
    def archived(self) -> list[dict]:
        return self._data.get("archived", [])

    @property
    def pending(self) -> list[dict]:
        return [t for t in self.tasks if t.get("status") == "pending"]

    @property
    def completed(self) -> list[dict]:
        return [t for t in self.tasks if t.get("status") == "completed"]

    def add(self, task: dict) -> str:
        tasks = self._data.setdefault("tasks", [])
        task_id = task.get("id", f"t_{len(tasks) + 1:03d}")
        task["id"] = task_id
        task.setdefault("status", "pending")
        task.setdefault("priority", "medium")
        task.setdefault("course_name", "")
        task.setdefault("notes", "")
        task.setdefault("created_at", datetime.now().isoformat())
        task.setdefault("reminded", False)
        tasks.append(task)
        return task_id

    def complete(self, task_id: str) -> bool:
        for task in self._data.get("tasks", []):
            if task["id"] == task_id:
                task["status"] = "completed"
                task["completed_at"] = datetime.now().isoformat()
                self._auto_archive()
                return True
        return False

    def uncomplete(self, task_id: str) -> bool:
        for task in self._data.get("tasks", []):
            if task["id"] == task_id:
                task["status"] = "pending"
                task["completed_at"] = None
                return True
        return False

    def update_notes(self, task_id: str, notes: str) -> bool:
        return self.update(task_id, {"notes": notes})

    def delete(self, task_id: str) -> bool:
        tasks = self._data.get("tasks", [])
        for i, task in enumerate(tasks):
            if task["id"] == task_id:
                tasks.pop(i)
                return True
        return False

    def update(self, task_id: str, changes: dict) -> bool:
        for task in self._data.get("tasks", []):
            if task["id"] == task_id:
                task.update(changes)
                task["updated_at"] = datetime.now().isoformat()
                return True
        return False

    def get_overdue(self) -> list[dict]:
        now = datetime.now().isoformat()
        return [
            t for t in self.tasks
            if t.get("status") == "pending" and t.get("due_date", "") < now
        ]

    def _auto_archive(self) -> None:
        """Move completed tasks to archive 3 days after completion."""
        now = datetime.now()
        threshold = (now - timedelta(days=3)).isoformat()
        active = []
        for t in self._data.get("tasks", []):
            if t.get("status") == "completed":
                completed_at = t.get("completed_at", "")
                if completed_at and completed_at < threshold:
                    self._data.setdefault("archived", []).append(t)
                    continue
            active.append(t)
        self._data["tasks"] = active

    @property
    def active(self) -> list[dict]:
        """Tasks that are not archived — pending + recently completed."""
        return self.tasks
