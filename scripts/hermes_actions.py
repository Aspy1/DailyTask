"""Expose a small JSON boundary to Hermes while retaining the actions CLI writer."""

import json
import os
import shlex
import subprocess
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.actions import _build_action_namespace, build_parser  # noqa: E402
from scripts.actions_core import ActionError, _validate_args  # noqa: E402
from scripts.actions_receipt import RECEIPT_FLAG, unpack  # noqa: E402
from scripts.hermes_plugin.tools import validate_request  # noqa: E402
from src.models import semester_paths  # noqa: E402
from src.models.inventory import (  # noqa: E402
    ITEM_FIELDS,
    RENEW_WARNING_DAYS,
    SIDE_SCHOOL,
    InventoryModel,
    days_until,
    membership_days_left,
    renewal_due,
)
from src.services import ai_audit, ai_guard, ai_undo  # noqa: E402
from src.services.paths import DATA_DIR_ENV, get_data_dir  # noqa: E402

CLI_TIMEOUT_SECONDS = 90
MAX_REQUEST_BYTES = 32_768
TASK_FIELDS = (
    "id", "title", "course_name", "due_date", "status", "priority", "tags", "notes",
)
COURSE_FIELDS = (
    "id", "name", "day_of_week", "weeks", "time_slots", "week_parity",
    "location", "teacher",
)
PLAN_FIELDS = ("title", "time_slot", "type", "course_name", "note", "done")
SEMESTER_FIELDS = ("id", "name", "start_date", "end_date", "total_weeks",
                   "exam_weeks", "period_count")
INVENTORY_FIELDS = ("id", *ITEM_FIELDS, "remaining_doses", "created_at", "updated_at")
MEMBERSHIP_FIELDS = ("username", "expires_on", "auto_renew", "renew_months")


def _read_object(path: Path) -> dict:
    """Read existing business data strictly; queries must never create or repair it."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Invalid object in {path.name}; no changes made")
    return value


def _rows(value: object, fields: tuple[str, ...]) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("Invalid business data list; no changes made")
    return [{key: row[key] for key in fields if key in row} for row in value]


def _semester_context(data_dir: Path) -> tuple[dict, dict, dict]:
    registry = _read_object(semester_paths.registry_path(data_dir))
    current = registry.get("current_semester") or ""
    entries = _rows(registry.get("semesters"), SEMESTER_FIELDS)
    semester = next((row for row in entries if row.get("id") == current), {})
    if not current:
        return {}, {}, {}
    if not semester or not isinstance(current, str):
        raise ValueError("Invalid current semester; no changes made")
    # resolve() calls ensure_current(), which can write. Use its pure path helper.
    folder = semester_paths.semester_dir(data_dir, current).resolve()
    if not folder.is_relative_to((data_dir / semester_paths.SEMESTER_DIR).resolve()):
        raise ValueError("Invalid semester path; no changes made")
    return semester, _read_object(folder / "courses.json"), _read_object(folder / "tasks.json")


def _context(parameters: dict, data_dir: Path) -> dict:
    now = datetime.now().astimezone()
    day = parameters.get("date") or date.today().isoformat()
    scope = parameters.get("scope", "planner")
    if scope in ("inventory", "restock"):
        inventory = _inventory_context(data_dir, now.date())
        if scope == "restock":
            return {"today": now.date().isoformat(),
                    "reminders": inventory["reminders"],
                    "renewal_warning_days": RENEW_WARNING_DAYS}
        return {"today": now.date().isoformat(), **inventory}
    semester, courses, tasks = _semester_context(data_dir)
    logs = _read_object(data_dir / "daily_logs.json")
    plans = logs.get("plans") or {}
    if not isinstance(plans, dict):
        raise ValueError("Invalid plans object; no changes made")
    return {
        "date": day,
        "today": now.date().isoformat(), "now": now.isoformat(timespec="seconds"),
        "semester": semester,
        "courses": _rows(courses.get("courses"), COURSE_FIELDS),
        "tasks": _rows(tasks.get("tasks"), TASK_FIELDS),
        "plans": [dict(row, index=index) for index, row in
                  enumerate(_rows(plans.get(day), PLAN_FIELDS))],
    }


def _inventory_context(data_dir: Path, today: date) -> dict:
    """Build a read-only inventory projection and actionable reminder list."""
    data = _read_object(data_dir / "inventory.json")
    items = _rows(data.get("items"), INVENTORY_FIELDS)
    projected: list[dict] = []
    reminders: list[dict] = []
    for item in items:
        item["status"] = InventoryModel.effective_status(item, today)
        membership = InventoryModel.membership_of(item)
        item["membership"] = {key: membership[key] for key in MEMBERSHIP_FIELDS
                                 if key in membership}
        item["stock"] = InventoryModel.stock_text(item)
        projected.append(item)
        if InventoryModel.side_of(item) != SIDE_SCHOOL or item.get("ignore_low_stock"):
            continue
        if item["status"] not in ("不足", "需购"):
            continue
        if reminder := _inventory_reminder(item, today):
            reminders.append(reminder)
    return {"items": projected, "reminders": reminders,
            "categories": _string_values(data.get("categories")),
            "locations": _string_values(data.get("locations")),
            "renewal_warning_days": RENEW_WARNING_DAYS}


def _string_values(value: object) -> list[str]:
    """Return only string values from an optional inventory vocabulary list."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _inventory_reminder(item: dict, today: date) -> dict | None:
    """Classify one due inventory entry without reading private membership contacts."""
    membership = InventoryModel.membership_of(item)
    expires_on = str(membership.get("expires_on") or "")
    membership_days = membership_days_left(item, today)
    if renewal_due(item, today):
        return _reminder_record(item, "renewal", expires_on, membership_days,
                                auto_renew=bool(membership.get("auto_renew")))
    for field, reason, lead in (
        ("runs_out_on", "estimated_depletion", RENEW_WARNING_DAYS),
        ("expires_on", "product_expiry",
         int(item.get("remind_before_days") or RENEW_WARNING_DAYS)),
    ):
        due_on = str(item.get(field) or "")
        days_left = days_until(due_on, today)
        if days_left is not None and days_left <= lead:
            return _reminder_record(item, "restock", due_on, days_left, reason=reason)
    return _reminder_record(item, "restock", "", None, reason="low_stock")


def _reminder_record(item: dict, kind: str, due_on: str, days_left: int | None,
                     **extra: object) -> dict:
    """Return a minimal reminder row for Hermes without unrelated item details."""
    return {"id": item.get("id", ""), "name": item.get("name", ""),
            "type": kind, "status": item.get("status", ""),
            "stock": item.get("stock", ""), "due_on": due_on,
            "days_remaining": days_left, **extra}


def _cli_arguments(action: str, parameters: dict) -> list[str]:
    # Use argparse's declared spellings (`--runs-out-months` vs `runs_out_months`),
    # while equals keeps option-like user text a single literal value.
    parser = build_parser()
    subparsers = next(item for item in parser._actions
                      if getattr(item, "choices", None) is not None)
    action_parser = subparsers.choices[action]
    option_names = {argument.dest: next(
        (option for option in argument.option_strings if option.startswith("--")),
        f"--{argument.dest.replace('_', '-')}",
    ) for argument in action_parser._actions if argument.option_strings}
    options = [f"{option_names[key]}={value}" for key, value in parameters.items()]
    namespace = _build_action_namespace([action, *options])
    _validate_args(action, namespace)
    return [action, *options]


def _execute_cli(argv: list[str], data_dir: Path, outcome: dict) -> str:
    environment = os.environ.copy()
    environment[DATA_DIR_ENV] = str(data_dir)
    environment["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(  # noqa: S603 - Fixed interpreter/script; allowlisted options, no shell.
            [sys.executable, str(ROOT / "scripts" / "actions.py"), RECEIPT_FLAG, *argv],
            cwd=ROOT, env=environment, shell=False, capture_output=True,
            text=True, encoding="utf-8", timeout=CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # A delegated UI operation may still complete after this process was killed.
        outcome["uncertain"] = True
        return "ERROR action timed out; query current state before retrying"
    except UnicodeError:
        outcome["uncertain"] = True
        return "ERROR invalid CLI output encoding; query current state before retrying"
    except OSError as error:
        return f"ERROR unable to launch actions CLI: {error}"
    result = completed.stdout.strip()
    if completed.returncode:
        outcome["uncertain"] = True
        return f"ERROR actions CLI exited {completed.returncode}; query before retrying"
    if not result:
        outcome["uncertain"] = True
        return "ERROR actions CLI returned no receipt; query before retrying"
    try:
        result = unpack(result)
    except ValueError:
        outcome["uncertain"] = True
        return "ERROR invalid CLI commit receipt; query before retrying"
    from src.services.single_instance import BAD_REPLY_MESSAGE, REFUSE_MESSAGE

    if result in (f"ERROR {REFUSE_MESSAGE}", f"ERROR {BAD_REPLY_MESSAGE}"):
        outcome["uncertain"] = True
    if not result.startswith(("OK ", "ERROR ", "ALREADY ")):
        outcome["uncertain"] = True
        return "ERROR unrecognized CLI receipt; query current state before retrying"
    return result


def _write(action: str, parameters: dict, data_dir: Path, request_id: str) -> dict:
    argv = _cli_arguments(action, parameters)
    command = shlex.join(["python", "scripts/actions.py", *argv])
    audit = ai_audit.AuditLog.for_data_dir(data_dir)
    undo = ai_undo.SnapshotStore.for_data_dir(data_dir)
    outcome: dict = {}
    if audit is not None:
        audit.request(request_id, source="hermes", operation=action)
    batch = ai_guard.run_batch(
        [command], data_dir=data_dir, audit=audit, undo=undo, request_id=request_id,
        executor=lambda _command: _execute_cli(argv, data_dir, outcome),
    )
    run = batch.runs[0]
    verdict = run.verdict
    success = run.executed and verdict.resolves and not outcome.get("uncertain")
    return {
        "ok": bool(success), "action": action,
        "message": verdict.as_text() if success else (run.blocked_reason or run.result),
        "verification": verdict.state,
        "coverage": {"checked": verdict.checked, "total": verdict.total,
                     "fields": list(verdict.fields)},
        "request_id": request_id, "snapshot_id": run.snapshot_id,
        "uncertain": bool(outcome.get("uncertain")),
        "retry_safe": False,
    }


def dispatch_request(request: object, *, data_dir: Path | None = None,
                     request_id: str = "") -> dict:
    """Validate a JSON request, then query or execute one allowlisted operation."""
    action = ""
    try:
        if not isinstance(request, dict) or set(request) != {"action", "parameters"}:
            raise ValueError("Expected exactly action and parameters")
        action = request["action"]
        parameters = validate_request(action, request["parameters"])
        selected = Path(data_dir).resolve() if data_dir is not None else get_data_dir()
        if action == "context":
            scope = parameters.get("scope", "planner")
            label = "inventory and reminders" if scope != "planner" else "planner context"
            return {"ok": True, "action": action, "message": f"Current {label}",
                    "data": _context(parameters, selected)}
        return _write(action, parameters, selected, request_id or uuid.uuid4().hex)
    except (ActionError, ValueError, TypeError, OSError) as error:
        return {"ok": False, "action": action if isinstance(action, str) else "",
                "message": str(error), "retry_safe": False}


def main() -> None:
    """Consume one bounded JSON request and emit one JSON receipt on stdout."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("Request exceeds 32768 bytes")
        result = dispatch_request(json.loads(raw))
    except (ValueError, UnicodeError) as error:
        result = {"ok": False, "action": "", "message": str(error)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
