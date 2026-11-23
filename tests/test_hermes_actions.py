"""Exercise the restricted Hermes bridge against isolated application data."""

import json
import os
import subprocess
import uuid
from datetime import date, timedelta
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


def test_inventory_query_returns_renewal_and_restock_alerts_without_private_contacts(
        sandbox, monkeypatch) -> None:
    today = date.today()
    renewal_date = (today + timedelta(days=3)).isoformat()
    (sandbox / "inventory.json").write_text(json.dumps({
        "_version": 1,
        "items": [
            {"id": "i_001", "name": "音乐会员", "category": "订阅",
             "quantity": 1, "unit": "个", "location": "", "status": "充足",
             "membership": {"username": "alice", "expires_on": renewal_date,
                             "auto_renew": True, "renew_months": 12}},
            {"id": "i_002", "name": "纸巾", "category": "日常消耗品",
             "quantity": 0, "unit": "包", "location": "学校", "status": "需购"},
            {"id": "i_003", "name": "家中洗手液", "category": "日常消耗品",
             "quantity": 0, "unit": "瓶", "location": "家", "status": "需购"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    private = sandbox / "private"
    private.mkdir()
    (private / "memberships.json").write_text(
        '{"contacts": {"i_001": "PRIVATE_PHONE_SENTINEL"}}', encoding="utf-8")
    original_open = Path.open

    def checked_open(path: Path, *args: object, **kwargs: object) -> object:
        assert private not in path.parents
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as scope:
        scope.setattr(Path, "open", checked_open)
        result = _dispatch(sandbox, "context", scope="inventory")

    assert result["ok"] is True, result
    data = result["data"]
    items = {item["id"]: item for item in data["items"]}
    assert items["i_001"]["status"] == "不足"  # Recompute from expiry, ignore stale stored status.
    assert items["i_002"]["status"] == "需购"
    assert "PRIVATE_PHONE_SENTINEL" not in json.dumps(result, ensure_ascii=False)
    reminders = {item["id"]: item for item in data["reminders"]}
    assert reminders["i_001"]["type"] == "renewal"
    assert reminders["i_001"]["due_on"] == renewal_date
    assert reminders["i_001"]["auto_renew"] is True
    assert reminders["i_002"]["type"] == "restock"
    assert "i_003" not in reminders  # Home-side supplies are intentionally excluded.


def test_restock_query_returns_only_actionable_alerts(sandbox) -> None:
    assert run('add_item --name "纸巾" --quantity 0 --unit "包"').startswith("OK")

    result = _dispatch(sandbox, "context", scope="restock")

    assert result["ok"] is True, result
    assert [item["name"] for item in result["data"]["reminders"]] == ["纸巾"]
    assert "items" not in result["data"]


def test_inventory_mutations_use_verified_actions_cli(sandbox) -> None:
    expires = (date.today() + timedelta(days=5)).isoformat()
    membership = json.dumps({"username": "music-account", "expires_on": expires,
                             "auto_renew": True, "renew_months": 12}, ensure_ascii=False)
    added = _dispatch(sandbox, "add_item", name="音乐会员", category="订阅",
                      quantity=1, membership=membership)
    _assert_verified(added, "add_item")
    item = read_json(sandbox, "inventory.json")["items"][0]
    assert item["membership"]["expires_on"] == expires

    updated = _dispatch(sandbox, "update_item", id=item["id"], location="家")
    _assert_verified(updated, "update_item")
    assert read_json(sandbox, "inventory.json")["items"][0]["location"] == "家"

    added_item = _dispatch(sandbox, "add_item", name="牙膏", category="日常消耗品",
                           quantity=2, unit="盒", doses_per_unit=12, notes="薄荷味",
                           tags="口腔,常用")
    _assert_verified(added_item, "add_item")
    toothpaste_id = read_json(sandbox, "inventory.json")["items"][1]["id"]
    updated_content = _dispatch(sandbox, "update_item", id=toothpaste_id,
                                name="牙膏（薄荷）", category="日常消耗品",
                                quantity=3, notes="新备注", location="宿舍", tags="日用,薄荷")
    _assert_verified(updated_content, "update_item")
    assert updated_content["coverage"]["checked"] == updated_content["coverage"]["total"]
    queried = _dispatch(sandbox, "context", scope="inventory")
    toothpaste = next(row for row in queried["data"]["items"] if row["id"] == toothpaste_id)
    assert toothpaste["name"] == "牙膏（薄荷）"
    assert toothpaste["quantity"] == 3 and toothpaste["remaining_doses"] == 36
    assert toothpaste["unit"] == "盒" and toothpaste["notes"] == "新备注"
    assert toothpaste["tags"] == ["日用", "薄荷"] and toothpaste["location"] == "宿舍"
    consumed = _dispatch(sandbox, "consume", id=toothpaste_id, amount=1)
    _assert_verified(consumed, "consume")
    updated_stock = read_json(sandbox, "inventory.json")["items"][1]
    assert updated_stock["quantity"] == 2 and updated_stock["remaining_doses"] == 35

    # Deletion requires interactive approval, which is unavailable on the WeChat bridge.
    rejected = _dispatch(sandbox, "delete_item", id=item["id"])
    assert rejected["ok"] is False
    assert "Unsupported" in rejected["message"]
    assert len(read_json(sandbox, "inventory.json")["items"]) == 2


def test_inventory_update_can_clear_notes_and_tags(sandbox) -> None:
    assert run('add_item --name "充电线" --group "随身" --notes "备用" '
               '--tags "USB-C,短线"').startswith("OK")
    item_id = read_json(sandbox, "inventory.json")["items"][0]["id"]

    result = _dispatch(sandbox, "update_item", id=item_id, group="", notes="", tags="")

    _assert_verified(result, "update_item")
    item = read_json(sandbox, "inventory.json")["items"][0]
    assert item["group"] == ""
    assert item["notes"] == ""
    assert item["tags"] == []


def test_inventory_update_verifies_all_supported_content_fields(sandbox) -> None:
    from src.models.inventory import runs_out_date, worn_since_date

    assert run('add_item --name "背包" --quantity 1').startswith("OK")
    item_id = read_json(sandbox, "inventory.json")["items"][0]["id"]
    membership = json.dumps({"username": "travel-account",
                             "expires_on": (date.today() + timedelta(days=30)).isoformat(),
                             "auto_renew": False, "renew_months": 12}, ensure_ascii=False)
    instances = json.dumps([{"tags": ["red"], "notes": "front pocket"}],
                           ensure_ascii=False)

    result = _dispatch(
        sandbox, "update_item", id=item_id, name="旅行背包", group="出行",
        category="衣物", quantity=2, status="不足", min_qty=3, min_doses=4,
        location="书架2", notes="蓝色", runs_out_months=2, worn_days=5,
        needs_wash="yes", expires=(date.today() + timedelta(days=60)).isoformat(),
        remind_before=9, stock_target=8, tags="旅行,红色", unit="只",
        doses_per_unit=6, instances=instances, membership=membership,
        billing_type="monthly", amount=9.5, due_day=15, installments=0)

    _assert_verified(result, "update_item")
    assert result["coverage"]["checked"] == result["coverage"]["total"]
    item = read_json(sandbox, "inventory.json")["items"][0]
    assert item["name"] == "旅行背包" and item["group"] == "出行"
    assert item["category"] == "衣物" and item["location"] == "书架2"
    assert item["quantity"] == 2 and item["remaining_doses"] == 12
    assert item["min_quantity"] == 3 and item["min_doses"] == 4
    assert item["status"] == "不足" and item["status_locked"] is True
    assert item["notes"] == "蓝色" and item["tags"] == ["旅行", "红色"]
    assert item["unit"] == "只" and item["doses_per_unit"] == 6
    assert item["instances"] == json.loads(instances)
    assert item["membership"] == json.loads(membership)
    assert item["runs_out_on"] == runs_out_date(2)
    assert item["worn_since"] == worn_since_date(5)
    assert item["needs_wash"] is True
    assert item["expires_on"] == (date.today() + timedelta(days=60)).isoformat()
    assert item["remind_before_days"] == 9 and item["stock_target"] == 8
    assert item["billing_type"] == "monthly" and item["amount"] == 9.5
    assert item["due_day"] == 15 and item["installments"] == 0

    cleared = _dispatch(sandbox, "update_item", id=item_id,
                        membership=json.dumps({}, ensure_ascii=False), billing_type="none")
    _assert_verified(cleared, "update_item")
    item = read_json(sandbox, "inventory.json")["items"][0]
    assert "membership" not in item
    assert not {"billing_type", "amount", "due_day", "installments",
                "paid_count", "billing_active", "last_charged_on"} & set(item)


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
    assert argv[2:4] == ["--commit-receipt", "add_task"]
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
