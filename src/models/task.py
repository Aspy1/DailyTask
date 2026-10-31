"""Task data model."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import ClassVar

from src.models.base import BaseJsonModel, next_id

DEFAULT_TASKS = {
    "_version": 2,
    "tasks": [],
    "archived": [],
}


class TaskModel(BaseJsonModel):
    GENERIC_TAGS: ClassVar[set[str]] = {"作业", "考试", "pre", "ppt", "报告", "复习", "项目", "论文", "实验", "小组作业"}

    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_TASKS)
        repaired = self._repair_course_names()
        # `_auto_archive()` 改的是**内存**，不落盘的话退出时 `flush_on_exit()` 会把它
        # 当成"磁盘被外部改过"→ 写一份冲突副本，真正的归档永远不生效。
        archived = self._auto_archive()
        if repaired or archived:
            self.save()

    def _repair_course_names(self) -> bool:
        """老数据里 `course_name` 缺失 → 从标签/标题补；返回是否有改动（由调用方保存）。"""
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
        return changed

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
        # Generate unique ID — check existing tasks + archived
        existing_ids = {t.get("id", "") for t in tasks}
        existing_ids.update(t.get("id", "") for t in self._data.get("archived", []))
        if "id" in task and task["id"] in existing_ids:
            task["id"] = ""  # Force regeneration
        if not task.get("id"):
            # 统一走 `next_id()`（最大后缀 +1）。旧实现是"最小空位"，删掉 t_002 后
            # 新任务会复用 t_002，历史引用（提醒/账本）会指向另一条任务。
            task["id"] = next_id("t", existing_ids)
        task_id = task["id"]
        task.setdefault("status", "pending")
        task.setdefault("priority", "medium")
        task.setdefault("course_name", "")
        task.setdefault("notes", "")
        task.setdefault("created_at", datetime.now().isoformat())
        task.setdefault("reminded", False)
        tasks.append(task)
        return task_id

    def complete(self, task_id: str) -> bool:
        tasks_list = self._data.get("tasks", [])
        for task in tasks_list:
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

    def _auto_archive(self) -> bool:
        """Move completed tasks to archive 3 days after completion. Returns changed."""
        now = datetime.now()
        threshold = (now - timedelta(days=3)).isoformat()
        active = []
        changed = False
        for t in self._data.get("tasks", []):
            if t.get("status") == "completed":
                completed_at = t.get("completed_at", "")
                if completed_at and completed_at < threshold:
                    self._data.setdefault("archived", []).append(t)
                    changed = True
                    continue
            active.append(t)
        self._data["tasks"] = active
        return changed

    @property
    def active(self) -> list[dict]:
        """Tasks that are not archived — pending + recently completed."""
        return self.tasks
