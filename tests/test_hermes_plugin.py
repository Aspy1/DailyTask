"""Hermes tool boundary tests without a live gateway or real user data."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

from scripts import actions
from scripts.hermes_plugin import register
from scripts.hermes_plugin import tools as plugin


class FakeContext:
    def __init__(self, settings: dict) -> None:
        self.settings = settings
        self.tools: dict[str, dict] = {}
        self.prompts: dict[str, dict] = {}

    def get_config(self, key: str, default: object = None) -> object:
        return self.settings.get(key, default)

    def register_tool(self, **kwargs: object) -> None:
        self.tools[kwargs["name"]] = kwargs

    def register_system_prompt_section(self, **kwargs: object) -> None:
        self.prompts[kwargs["id"]] = kwargs


@pytest.fixture
def context(sandbox: Path) -> FakeContext:
    workspace = sandbox / "workspace"
    workspace.mkdir()
    ctx = FakeContext({
        "workspace": str(workspace),
        "data_dir": str(sandbox / "isolated-data"),
        "instance_key": "hermes-plugin-test-instance",
    })
    register(ctx)
    return ctx


def _call(context: FakeContext, tool: str, arguments: object) -> dict:
    return json.loads(context.tools[tool]["handler"](arguments, session_id="test"))


def _result(payload: object, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, json.dumps(payload), "")


def test_registration_exposes_the_closed_tools(context: FakeContext) -> None:
    assert set(context.tools) == {"daily_task_query", "daily_task_update", "daily_task_documents"}
    for name, entry in context.tools.items():
        assert entry["toolset"] == "daily_task"
        assert entry["schema"]["name"] == name
        assert entry["schema"]["parameters"]["additionalProperties"] is False
    query = context.tools["daily_task_query"]["schema"]["parameters"]
    assert set(query["properties"]) == {"date"}
    update = context.tools["daily_task_update"]["schema"]["parameters"]
    assert set(update["properties"]) == {"action", "parameters"}
    assert update["required"] == ["action", "parameters"]
    assert set(update["properties"]["action"]["enum"]) == set(plugin.ACTION_FIELDS) - {"context"}
    assert update["properties"]["parameters"]["additionalProperties"] is False


def test_registration_does_not_read_operator_configuration() -> None:
    ctx = FakeContext({})
    ctx.get_config = Mock(side_effect=AssertionError("Registration must not read settings."))
    register(ctx)
    assert set(ctx.tools) == {"daily_task_query", "daily_task_update", "daily_task_documents"}
    assert "daily-task.instructions" in ctx.prompts
    ctx.get_config.assert_not_called()


@pytest.mark.parametrize(("tool", "arguments"), [
    ("daily_task_query", {}),
    ("daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}}),
])
def test_missing_configuration_is_reported_without_process(monkeypatch, tool: str, arguments: dict) -> None:
    ctx = FakeContext({})
    register(ctx)
    run = Mock()
    monkeypatch.setattr(plugin.subprocess, "run", run)
    result = _call(ctx, tool, arguments)
    assert result["ok"] is False and result["error"] == "invalid_configuration"
    assert "workspace" in result["message"]
    assert result["uncertain"] is False
    run.assert_not_called()


def test_relative_configuration_is_rejected_at_call_time(monkeypatch) -> None:
    ctx = FakeContext({"workspace": "relative-workspace"})
    register(ctx)
    run = Mock()
    monkeypatch.setattr(plugin.subprocess, "run", run)
    result = _call(ctx, "daily_task_query", {})
    assert result["error"] == "invalid_configuration"
    run.assert_not_called()


def test_operator_can_supply_settings_after_registration(sandbox: Path, monkeypatch) -> None:
    ctx = FakeContext({})
    register(ctx)
    ctx.settings["workspace"] = str(sandbox)
    run = Mock(return_value=_result({"ok": True, "action": "context"}))
    monkeypatch.setattr(plugin.subprocess, "run", run)
    assert _call(ctx, "daily_task_query", {})["ok"] is True
    assert run.call_args.kwargs["cwd"] == str(sandbox)


def test_prompt_is_limited_to_weixin_and_requires_verification(context: FakeContext) -> None:
    callback = context.prompts["daily-task.instructions"]["content"]
    assert callback({"platform": "telegram"}) == ""
    assert callback({}) == ""
    prompt = callback({"platform": "weixin"})
    for phrase in ("daily_task_query", "local time", "1-6", "inclusive",
                   "verified", "missing", "shell", "file"):
        assert phrase in prompt


def test_prompt_explains_verified_noop_without_repeating(context: FakeContext) -> None:
    prompt = context.prompts["daily-task.instructions"]["content"]({"platform": "weixin"})
    assert "verified_noop" in prompt
    assert "already satisfied" in prompt
    assert "do not repeat" in prompt.lower()


def test_action_fields_and_scalar_types_match_cli() -> None:
    parser = actions.build_parser()
    subparsers = next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction))
    for name, fields in plugin.ACTION_FIELDS.items():
        if name == "context":
            assert fields == ("date",)
            continue
        arguments = {item.dest: item for item in subparsers.choices[name]._actions if item.dest != "help"}
        assert set(fields) == set(arguments)
        for field, argument in arguments.items():
            value = 2 if argument.type is int else "sample"
            if argument.choices:
                value = argument.choices[0]
            required = {key: (2 if item.type is int else "sample")
                        for key, item in arguments.items() if item.required}
            required[field] = value
            assert plugin.validate_request(name, required)[field] == value


@pytest.mark.parametrize(("action", "parameters"), [
    ("delete_course", {"id": "c_001"}),
    ([], {}),
    ("context", {"data_dir": "elsewhere"}),
    ("context", {"date": "tomorrow"}),
    ("context", {"date": "2026-02-30"}),
    ("context", {"date": "20261120"}),
    ("add_task", {"title": "Title"}),
    ("complete_task", {"id": ["t_001"]}),
    ("add_course", {"name": "Course", "day": True}),
    ("add_course", {"name": "Course", "day": "2"}),
    ("add_course", {"name": "Course", "day": 2, "parity": "sometimes"}),
    ("add_plan", {"date": "2026-11-20", "title": {}, "slot": 1}),
    ("complete_plan", {"date": "2026-11-20", "index": 1.5}),
    ("complete_task", None),
])
def test_invalid_requests_are_rejected(action: object, parameters: object) -> None:
    with pytest.raises(ValueError):
        plugin.validate_request(action, parameters)


def test_validation_returns_a_copy_without_cli_defaults() -> None:
    source = {"title": "Title", "due": "2026-11-20"}
    validated = plugin.validate_request("add_task", source)
    assert validated == source and validated is not source
    assert "priority" not in validated


@pytest.mark.parametrize(("tool", "arguments"), [
    ("daily_task_query", {"workspace": "elsewhere"}),
    ("daily_task_query", []),
    ("daily_task_update", {"action": "context", "parameters": {}}),
    ("daily_task_update", {"action": "complete_task", "parameters": {"id": True}}),
    ("daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}, "cwd": "x"}),
    ("daily_task_update", {"action": "complete_task"}),
])
def test_invalid_tool_calls_never_start_process(context: FakeContext, monkeypatch, tool: str, arguments: object) -> None:
    run = Mock()
    monkeypatch.setattr(plugin.subprocess, "run", run)
    result = _call(context, tool, arguments)
    assert result["ok"] is False
    assert result["uncertain"] is False
    run.assert_not_called()


def test_fixed_process_contract_and_isolated_environment(context: FakeContext, monkeypatch) -> None:
    run = Mock(return_value=_result({"ok": True, "action": "context", "data": {"date": "2026-11-20"}}))
    monkeypatch.setattr(plugin.subprocess, "run", run)
    result = _call(context, "daily_task_query", {"date": "2026-11-20"})
    assert result["ok"] is True
    argv, = run.call_args.args
    workspace = Path(context.settings["workspace"])
    assert argv == [str(workspace / ".venv" / "Scripts" / "python.exe"),
                    str(workspace / "scripts" / "hermes_actions.py")]
    kwargs = run.call_args.kwargs
    assert kwargs["cwd"] == str(workspace)
    assert kwargs["shell"] is False
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["timeout"] == plugin.BRIDGE_TIMEOUT_SECONDS == 150
    assert len(kwargs["input"].splitlines()) == 1
    assert json.loads(kwargs["input"]) == {"action": "context", "parameters": {"date": "2026-11-20"}}
    assert kwargs["env"]["LIFE_ASSISTANT_DATA_DIR"] == context.settings["data_dir"]
    assert kwargs["env"]["LIFE_ASSISTANT_SINGLE_INSTANCE_KEY"] == context.settings["instance_key"]


def test_operator_python_setting_is_supported(sandbox: Path, monkeypatch) -> None:
    run = Mock(return_value=_result({"ok": True, "action": "context"}))
    monkeypatch.setattr(plugin.subprocess, "run", run)
    configured_python = str(sandbox / "operator-python.exe")
    ctx = FakeContext({"workspace": str(sandbox), "python": configured_python})
    register(ctx)
    assert _call(ctx, "daily_task_query", {})["ok"] is True
    assert run.call_args.args[0][0] == configured_python
    assert run.call_args.kwargs["env"]["LIFE_ASSISTANT_DATA_DIR"] == str(sandbox / "data")


@pytest.mark.parametrize("payload", [
    {"ok": True, "action": "complete_task", "verification": "verified"},
    {"ok": False, "action": "complete_task", "message": "Unknown task"},
])
def test_valid_bridge_results_are_preserved(context: FakeContext, monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(plugin.subprocess, "run", Mock(return_value=_result(payload)))
    result = _call(context, "daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}})
    assert result == payload


def test_verified_noop_is_an_accepted_receipt(context: FakeContext, monkeypatch) -> None:
    payload = {"ok": True, "action": "complete_task", "verification": "verified_noop",
               "message": "Task was already complete."}
    monkeypatch.setattr(plugin.subprocess, "run", Mock(return_value=_result(payload)))
    result = _call(context, "daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}})
    assert result == payload


@pytest.mark.parametrize(("tool", "arguments", "receipt_action", "ok"), [
    ("daily_task_query", {}, "complete_task", True),
    ("daily_task_query", {}, None, True),
    ("daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}}, "add_task", True),
    ("daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}}, "add_task", False),
])
def test_unrelated_receipts_are_rejected(context: FakeContext, monkeypatch, tool: str,
                                       arguments: dict, receipt_action: object, ok: bool) -> None:
    payload = {"ok": ok, "action": receipt_action, "verification": "verified"}
    monkeypatch.setattr(plugin.subprocess, "run", Mock(return_value=_result(payload)))
    result = _call(context, tool, arguments)
    assert result["ok"] is False
    assert result["error"] == "receipt_action_mismatch"
    assert result["action"] == ("context" if tool == "daily_task_query" else arguments["action"])
    assert result["uncertain"] is (tool == "daily_task_update")


@pytest.mark.parametrize("stdout", ["", "not json", "[]", "{}", '{"ok":1}', '{"ok":true}\n{}'])
def test_invalid_bridge_output_never_claims_success(context: FakeContext, monkeypatch, stdout: str) -> None:
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout, ""))
    monkeypatch.setattr(plugin.subprocess, "run", run)
    result = _call(context, "daily_task_query", {})
    assert result["ok"] is False
    assert run.call_count == 1


@pytest.mark.parametrize("returncode", [0, 1])
def test_writes_need_verified_success(context: FakeContext, monkeypatch, returncode: int) -> None:
    run = Mock(return_value=_result({"ok": True, "action": "complete_task"}, returncode))
    monkeypatch.setattr(plugin.subprocess, "run", run)
    result = _call(context, "daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}})
    assert result["ok"] is False
    assert result["uncertain"] is True
    assert result["retry_safe"] is False


def test_nonzero_exit_overrides_successful_payload(context: FakeContext, monkeypatch) -> None:
    run = Mock(return_value=_result({"ok": True, "action": "complete_task", "verification": "verified"}, 1))
    monkeypatch.setattr(plugin.subprocess, "run", run)
    result = _call(context, "daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}})
    assert result["ok"] is False and result["error"] == "bridge_failed"
    assert result["uncertain"] is True


def test_timeout_reports_unknown_outcome_without_retry(context: FakeContext, monkeypatch) -> None:
    run = Mock(side_effect=subprocess.TimeoutExpired("bridge", 150))
    monkeypatch.setattr(plugin.subprocess, "run", run)
    result = _call(context, "daily_task_update", {"action": "complete_task", "parameters": {"id": "t_001"}})
    assert result["ok"] is False and result["uncertain"] is True
    assert result["retry_safe"] is False
    assert "unknown" in result["message"].lower()
    assert run.call_count == 1


def test_start_failure_is_a_structured_result(context: FakeContext, monkeypatch) -> None:
    monkeypatch.setattr(plugin.subprocess, "run", Mock(side_effect=FileNotFoundError("missing")))
    result = _call(context, "daily_task_query", {})
    assert result["ok"] is False and result["uncertain"] is False


def test_calls_are_serialized(context: FakeContext, monkeypatch) -> None:
    first_entered, release_first, second_started = Event(), Event(), Event()
    calls = []

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(kwargs)
        if len(calls) == 1:
            first_entered.set()
            assert release_first.wait(3)
        else:
            second_started.set()
        return _result({"ok": True, "action": "context"})

    monkeypatch.setattr(plugin.subprocess, "run", run)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_call, context, "daily_task_query", {})
        assert first_entered.wait(3)
        second = executor.submit(_call, context, "daily_task_query", {})
        assert not second_started.wait(0.05)
        release_first.set()
        assert first.result()["ok"] and second.result()["ok"]
    assert second_started.is_set()
