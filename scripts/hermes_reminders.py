"""Render scheduled Weixin messages; empty output means nothing is due."""

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import semester_paths
from src.models.course import schedule_date
from src.services.paths import get_data_dir
from src.services.reminder_preference import reminders_enabled
from src.services.reminder_rules import (
    DDL_EMAIL_HOURS,
    DDL_REMIND_DAYS,
    collect_exam_items,
    ddl_email_body,
    ddl_email_due,
    ddl_reminder_body,
    ddl_reminder_due,
    exam_reminder_due,
    meal_slot_due,
)


def _read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Expected a business data object.")
    return value


def _active_term(data_dir: Path) -> tuple[str, Path]:
    registry = _read_object(semester_paths.registry_path(data_dir))
    term = registry.get("current_semester") or ""
    if not isinstance(term, str) or term in (".", "..") or Path(term).name != term:
        raise ValueError("Invalid semester identifier.")
    root = (data_dir / semester_paths.SEMESTER_DIR).resolve()
    folder = semester_paths.semester_dir(data_dir, term).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("Invalid semester folder.")
    return term, folder


def _pending_tasks(folder: Path) -> list[dict]:
    return [task for task in _read_object(folder / "tasks.json").get("tasks", [])
            if task.get("status") == "pending"]


def _homework(pending: list[dict], now: datetime, sent: set[str], enabled: bool) -> list[str]:
    messages = []
    dated = ddl_email_due(pending, now, {key.removeprefix("urgent:") for key in sent
                                      if key.startswith("urgent:")})
    if dated:
        sent.update(f"urgent:{task.get('id', '')}" for task in dated)
        messages.append(f"【作业紧急提醒 · {DDL_EMAIL_HOURS} 小时内】\n{ddl_email_body(dated)}")
    if enabled:
        due = ddl_reminder_due(pending, schedule_date(now), sent)
        if due:
            sent.update(f"{task.get('id', '')}@{task['due_date'][:10]}" for task, _days in due)
            messages.append(f"【作业截止提醒 · {DDL_REMIND_DAYS} 天内】\n{ddl_reminder_body(due)}")
    return messages


def _exams(folder: Path, pending: list[dict], now: datetime, sent: set[str]) -> list[str]:
    rows = _read_object(folder / "exams.json").get("exams", [])
    messages = []
    for item in collect_exam_items(rows, pending):
        prefix = f"{item['key']}:"
        prior = {int(key.removeprefix(prefix)) for key in sent if key.startswith(prefix)}
        remaining, hits = exam_reminder_due(item, schedule_date(now), prior)
        if hits:
            sent.update(f"{prefix}{day}" for day in hits)
            messages.append(f"【考试提醒】\n「{item['name']}」还有 {remaining} 天考试\n日期: {item['date']}")
    return messages


def _messages(kind: str, data_dir: Path, folder: Path | None, now: datetime, sent: set[str]) -> list[str]:
    if kind == "meal":
        due = meal_slot_due(now, sent)
        sent.update(key for key, _label in due)
        return [f"{label}时间到了 🍚" for _key, label in due]
    if folder is None:
        return []
    pending = _pending_tasks(folder)
    if kind == "homework":
        return _homework(pending, now, sent, reminders_enabled(data_dir))
    return _exams(folder, pending, now, sent)


def run_reminders(kind: str, data_dir: Path, ledger: Path, now: datetime) -> str:
    if kind not in ("homework", "exam", "meal"):
        raise ValueError("Unknown reminder kind.")
    term, folder = ("", None) if kind == "meal" else _active_term(data_dir)
    if not term and kind != "meal":
        return ""
    namespace = f"{kind}:{term}"
    if kind != "exam":
        namespace += f":{now.date()}"
    with closing(sqlite3.connect(ledger)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS emitted (namespace TEXT, key TEXT, expiry TEXT, "
                   "PRIMARY KEY(namespace, key))")
        db.execute("DELETE FROM emitted WHERE expiry < ?", (now.date().isoformat(),))
        previous = {key for key, in db.execute("SELECT key FROM emitted WHERE namespace = ?", (namespace,))}
        sent = previous.copy()
        messages = _messages(kind, data_dir, folder, now, sent)
        expiry = (now.date() + timedelta(days=16 if kind == "exam" else 1)).isoformat()
        db.executemany("INSERT INTO emitted VALUES (?, ?, ?)",
                       ((namespace, key, expiry) for key in sent - previous))
    return "\n\n".join(messages)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("homework", "exam", "meal"))
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    message = run_reminders(args.kind, get_data_dir(), args.ledger, datetime.now())
    if message:
        print(message)


if __name__ == "__main__":
    main()
