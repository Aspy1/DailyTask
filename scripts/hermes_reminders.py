"""Render scheduled Weixin messages; empty output means nothing is due."""

import argparse
import json
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import semester_paths
from src.models.course import schedule_date
from src.services import hermes_ledger
from src.services.hermes_ledger import (  # noqa: F401 — 排查/测试入口（再导出）
    delivery_diagnostics,
    ledger_states,
)
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


def run_reminders(kind: str, data_dir: Path, ledger: Path, now: datetime,
                  scheduler: tuple[Path, str] | None = None) -> str:
    """产出本轮提醒 → 返回要投递的文本（空 = 没有）。

    **账本三态（审计 2026-11-21 P2）**：产出只记 `pending`，
    只接受对应 Hermes 执行 ID 的投递结果；一直没确认的过期后是
    `uncertain`（记警告、提示人工核对，**不自动重试** —— 我们的消息没有幂等键）。
    """
    if kind not in ("homework", "exam", "meal"):
        raise ValueError("Unknown reminder kind.")
    term, folder = ("", None) if kind == "meal" else _active_term(data_dir)
    if not term and kind != "meal":
        return ""
    namespace = f"{kind}:{term}"
    if kind != "exam":
        namespace += f":{now.date()}"
    with closing(hermes_ledger.open_ledger(ledger)) as db, db:
        execution = hermes_ledger.begin(db, now.date(), scheduler)
        sent = hermes_ledger.done_keys(db, namespace)
        fresh = set(sent)
        messages = _messages(kind, data_dir, folder, now, fresh)
        if messages:
            hermes_ledger.emit_keys(db, namespace, fresh - sent, now,
                                    days=16 if kind == "exam" else 1, execution=execution)
        hermes_ledger.warn_uncertain(db)
    return "\n\n".join(messages)


def _scheduler_binding(ledger: Path, kind: str) -> tuple[Path, str] | None:
    """Discover the existing locally installed, dedicated Hermes reminder job."""
    if ledger.name != "daily-task-reminders.sqlite":
        return None
    jobs = _read_object(ledger.parent / "jobs.json").get("jobs", [])
    script = f"daily-task-reminder-{kind}.py"
    matches = [job["id"] for job in jobs if job.get("script") == script and job.get("no_agent")
               and isinstance(job.get("id"), str) and str(job.get("deliver", "")).startswith("weixin:")]
    if len(matches) != 1:
        return None
    return ledger.parent / "executions.db", matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("homework", "exam", "meal"))
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    message = run_reminders(args.kind, get_data_dir(), args.ledger, datetime.now(),
                            scheduler=_scheduler_binding(args.ledger, args.kind))
    if message:
        print(message)


if __name__ == "__main__":
    main()
