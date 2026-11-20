"""Exercise the restricted Hermes bridge against isolated application data."""

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from helpers import read_json, run

from scripts import hermes_actions as bridge

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
DAY = "2026-11-23"


@pytest.fixture(autouse=True)
def _isolate_cli(sandbox, monkeypatch) -> None:
    """Prevent child processes from reaching a running production application."""
    monkeypatch.setenv("LIFE_ASSISTANT_DATA_DIR", str(sandbox))
    monkeypatch.setenv("LIFE_ASSISTANT_SINGLE_INSTANCE_KEY",
                       f"HermesActionsTest-{os.getpid()}-{uuid.uuid4().hex}")


def _dispatch(sandbox, action: str, **parameters: object) -> dict:
    return bridge.dispatch_request(
        {"action": action, "parameters": parameters},
        data_dir=sandbox, request_id="hermes-bridge-test")


def _files(sandbox) -> dict[str, bytes]:
    return {str(path.relative_to(sandbox)): path.read_bytes()
            for path in sandbox.rglob("*") if path.is_file()}


def _business_files(sandbox) -> dict[str, bytes]:
    return {name: content for name, content in _files(sandbox).items()
            if name.endswith(".json") and not {"backup", "ai_undo"}.intersection(Path(name).parts)}


def _assert_verified(result: dict, action: str) -> None:
    assert result["ok"] is True, result
    assert result["action"] == action
    assert result["verification"] == "verified"
    assert isinstance(result["message"], str) and result["message"]


@pytest.mark.parametrize("title", ["算法 作业", """作业 'single' "double"; & $(whoami)"""])
def test_add_task_uses_real_cli_and_verifies_written_fields(sandbox, title) -> None:
    result = _dispatch(sandbox, "add_task", title=title, course="算法",
                       due=DAY, priority="high", tags="复习,必做",
                       notes="PRIVATE_NOTE_SENTINEL")

    _assert_verified(result, "add_task")
    task = read_json(sandbox, "tasks.json")["tasks"][0]
    assert task["title"] == title
    assert task["course_name"] == "算法"
    assert task["due_date"].startswith(DAY)
    assert task["priority"] == "high"
    assert task["tags"] == ["复习", "必做"]
    assert task["notes"] == "PRIVATE_NOTE_SENTINEL"
    audit = sandbox / "ai_actions.jsonl"
    assert audit.exists()
    assert "PRIVATE_NOTE_SENTINEL" not in audit.read_text(encoding="utf-8")


def test_add_course_uses_real_cli(sandbox) -> None:
    result = _dispatch(sandbox, "add_course", name="机器学习", day=2,
                       weeks="2-14", slots="2-3", location="A201",
                       teacher="王老师", parity="even")

    _assert_verified(result, "add_course")
    course = read_json(sandbox, "courses.json")["courses"][0]
    assert course["name"] == "机器学习"
    assert course["day_of_week"] == 2
    assert course["weeks"] == {"start": 2, "end": 14}
    assert course["week_parity"] == "even"
    assert course["time_slots"] == [{"start": 2, "end": 3, "location": "A201"}]


def test_update_course_preserves_omitted_fields_and_creates_backup(sandbox) -> None:
    assert run('add_course --name "机器学习" --day 2 --weeks 2-14 '
               '--slots 2-3 --location A201 --teacher "王老师" '
               '--parity even').startswith("OK")
    original = read_json(sandbox, "courses.json")["courses"][0]

    result = _dispatch(sandbox, "update_course", id=original["id"], location="B302")

    _assert_verified(result, "update_course")
    course = read_json(sandbox, "courses.json")["courses"][0]
    assert course["location"] == "B302"
    assert course["time_slots"][0] == {"start": 2, "end": 3, "location": "B302"}
    for field in ("id", "name", "day_of_week", "weeks", "teacher", "week_parity"):
        assert course[field] == original[field], field
    backups = list((sandbox / "backup" / "actions").glob("courses.json.*.json"))
    assert any(json.loads(path.read_text(encoding="utf-8"))["courses"][0] == original
               for path in backups)


def test_add_plan_uses_real_cli_and_selected_date(sandbox) -> None:
    result = _dispatch(sandbox, "add_plan", date=DAY, title="复习 机器学习",
                       slot=3, course="机器学习", note="复习第三章")

    _assert_verified(result, "add_plan")
    plan = read_json(sandbox, "daily_logs.json")["plans"][DAY][0]
    assert plan["title"] == "复习 机器学习"
    assert plan["time_slot"] == 3
    assert plan["course_name"] == "机器学习"
    assert plan["note"] == "复习第三章"


def test_complete_operations_use_ids_and_indices_from_context(sandbox) -> None:
    assert run(f'add_task --title "作业" --due {DAY}').startswith("OK")
    assert run(f'add_plan --date {DAY} --title "复习"').startswith("OK")
    task_id = read_json(sandbox, "tasks.json")["tasks"][0]["id"]

    _assert_verified(_dispatch(sandbox, "complete_task", id=task_id), "complete_task")
    _assert_verified(_dispatch(sandbox, "complete_plan", date=DAY, index=0),
                     "complete_plan")

    assert read_json(sandbox, "tasks.json")["tasks"] == []
    assert read_json(sandbox, "tasks.json")["archived"][0]["id"] == task_id
    assert read_json(sandbox, "daily_logs.json")["plans"][DAY][0]["done"] is True


def test_context_returns_business_ids_without_reading_private_files(sandbox, monkeypatch) -> None:
    assert run('add_course --name "机器学习" --day 2').startswith("OK")
    assert run(f'add_task --title "作业" --due {DAY}').startswith("OK")
    assert run(f'add_plan --date {DAY} --title "当日日程"').startswith("OK")
    assert run('add_plan --date 2026-11-24 --title "其他日期"').startswith("OK")
    (sandbox / "settings.ini").write_text("SECRET_CONTEXT_SENTINEL", encoding="utf-8")
    (sandbox / "private").mkdir()
    (sandbox / "private" / "secret.txt").write_text("PRIVATE_SENTINEL", encoding="utf-8")
    before = _files(sandbox)
    original_open = Path.open

    def checked_open(path: Path, *args: object, **kwargs: object) -> object:
        assert path.name != "settings.ini"
        assert sandbox / "private" not in path.parents
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as scope:
        scope.setattr(Path, "open", checked_open)
        result = _dispatch(sandbox, "context", date=DAY)

    assert result["ok"] is True, result
    data = result["data"]
    assert data["date"] == DAY
    assert data["semester"]
    assert data["courses"][0]["id"] == "c_001"
    assert data["tasks"][0]["id"] == "t_001"
    assert [plan["title"] for plan in data["plans"]] == ["当日日程"]
    assert "SENTINEL" not in json.dumps(result)
    assert _files(sandbox) == before


@pytest.mark.parametrize("payload", [
    {"action": "delete_course", "parameters": {"id": "c_001"}},
    {"action": "restore", "parameters": {"name": "tasks.json", "yes": True}},
    {"action": "terminal", "parameters": {"command": "whoami"}},
    {"action": "context", "parameters": {"path": "settings.ini"}},
    {"action": "add_task", "parameters": {"title": [], "due": DAY}},
    {"action": "add_course", "parameters": {"name": "A", "day": True}},
    {"action": "context", "parameters": {}, "command": "whoami"},
    {"action": "add_task", "parameters": "--title A --due 2026-11-23"},
])
def test_invalid_request_is_rejected_before_subprocess_and_without_writes(
        sandbox, monkeypatch, payload) -> None:
    before = _files(sandbox)

    def forbidden_run(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid requests must not start a child process")

    monkeypatch.setattr(bridge.subprocess, "run", forbidden_run)
    result = bridge.dispatch_request(payload, data_dir=sandbox)

    assert result["ok"] is False
    assert _files(sandbox) == before


def test_bad_business_date_does_not_modify_existing_business_data(sandbox) -> None:
    assert run(f'add_task --title "existing" --due {DAY}').startswith("OK")
    before = _business_files(sandbox)

    result = _dispatch(sandbox, "add_task", title="invalid", due="not-a-date")

    assert result["ok"] is False
    assert _business_files(sandbox) == before


def test_cli_receives_fixed_argv_and_literal_shell_characters(sandbox, monkeypatch) -> None:
    title = """作业 'single' "double"; echo HERMES_INJECTION $(whoami) &"""
    calls: list[tuple[list[str], dict]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "ERROR simulated", "")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    result = _dispatch(sandbox, "add_task", title=title, due=DAY)

    assert result["ok"] is False
    assert len(calls) == 1
    argv, options = calls[0]
    assert isinstance(argv, list)
    assert Path(argv[0]).resolve() == PYTHON.resolve()
    assert Path(argv[1]).resolve() == (ROOT / "scripts" / "actions.py").resolve()
    assert argv[2] == "add_task"
    assert f"--title={title}" in argv
    assert f"--due={DAY}" in argv
    assert options["shell"] is False
    assert Path(options["cwd"]).resolve() == ROOT.resolve()
    assert options["env"]["LIFE_ASSISTANT_DATA_DIR"] == str(sandbox)
    assert options["env"]["LIFE_ASSISTANT_SINGLE_INSTANCE_KEY"] == os.environ[
        "LIFE_ASSISTANT_SINGLE_INSTANCE_KEY"]


@pytest.mark.parametrize("stdout", ["ERROR task not found", "OK add_task t_001"])
def test_exit_zero_and_unverified_ok_never_claim_success(sandbox, monkeypatch, stdout) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    result = _dispatch(sandbox, "add_task", title="not-written", due=DAY)

    assert result["ok"] is False
    assert result.get("verification") != "verified"
    assert not read_json(sandbox, "tasks.json").get("tasks")


def test_subprocess_timeout_reports_uncertainty_without_retry(sandbox, monkeypatch) -> None:
    calls: list[list[str]] = []

    def timeout(argv: list[str], **kwargs: object) -> None:
        calls.append(argv)
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(bridge.subprocess, "run", timeout)
    result = _dispatch(sandbox, "add_task", title="uncertain", due=DAY)

    assert len(calls) == 1
    assert result["ok"] is False
    assert result["uncertain"] is True
    assert result["retry_safe"] is False


def test_main_accepts_json_stdin_and_returns_one_json_result(sandbox) -> None:
    result = subprocess.run(
        [str(PYTHON), str(ROOT / "scripts" / "hermes_actions.py")],
        input=json.dumps({"action": "add_plan",
                          "parameters": {"date": DAY, "title": "微信日程"}},
                         ensure_ascii=False),
        cwd=ROOT, env=dict(os.environ), capture_output=True, text=True,
        encoding="utf-8", timeout=30, shell=False)

    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    _assert_verified(response, "add_plan")
    assert read_json(sandbox, "daily_logs.json")["plans"][DAY][0]["title"] == "微信日程"
