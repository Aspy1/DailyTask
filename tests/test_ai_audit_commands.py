"""Audit command redaction must hide complete shell-quoted parameter values."""

import json
import shlex

import pytest

from src.services import ai_audit


@pytest.mark.parametrize("flag", ["note", "notes"])
@pytest.mark.parametrize("style", ["separate", "equals"])
@pytest.mark.parametrize("note", [
    "PRIVATE_HEAD PRIVATE_TAIL",
    "Alice's PRIVATE_SINGLE_TAIL",
    'She said "PRIVATE_DOUBLE_TAIL" privately',
    "PRIVATE_HEAD 'single' \"double\" PRIVATE_MIXED_TAIL",
    "--title=PRIVATE_OPTION_HEAD PRIVATE_OPTION_TAIL",
    "--due PRIVATE_OPTION_TAIL",
    "",
])
def test_full_note_value_is_redacted_after_shell_join(flag: str, style: str, note: str) -> None:
    values = [f"--{flag}={note}"] if style == "equals" else [f"--{flag}", note]
    command = shlex.join([
        "python", "scripts/actions.py", "add_task", "--title=public",
        *values, "--due=2026-11-23",
    ])

    result = ai_audit.redact_command(command)

    assert "PRIVATE_" not in result
    assert "public" in result
    assert "--due=2026-11-23" in result
    tokens = shlex.split(result)
    if style == "equals":
        assert f"--{flag}=***" in tokens
    else:
        assert tokens[tokens.index(f"--{flag}") + 1] == "***"


@pytest.mark.parametrize("command", [
    'python scripts/actions.py add_task --notes "PRIVATE_HEAD PRIVATE_TAIL',
    "python scripts/actions.py add_task '--notes=PRIVATE_HEAD PRIVATE_TAIL",
    'python scripts/actions.py add_task --notes \"PRIVATE_HEAD\"tail PRIVATE_TAIL\\',
])
def test_malformed_quotes_cannot_leak_unparsed_note_tails(command: str) -> None:
    assert "PRIVATE_" not in ai_audit.redact_command(command)


def test_json_notes_are_redacted_after_shell_join() -> None:
    plans = [{"title": "public", "note": "Alice's \"PRIVATE_JSON_TAIL\" note"}]
    command = shlex.join([
        "python", "scripts/actions.py", "replace_plans",
        f"--plans={json.dumps(plans)}",
    ])

    result = ai_audit.redact_command(command)

    assert "PRIVATE_" not in result
    payload = next(part.partition("=")[2] for part in shlex.split(result)
                   if part.startswith("--plans="))
    assert json.loads(payload) == [{"title": "public", "note": "***"}]


def test_note_tails_never_enter_action_or_verification_audit(sandbox) -> None:
    command = shlex.join([
        "python", "scripts/actions.py", "add_task", "--title=public",
        "--notes=PRIVATE_HEAD 'single' \"double\" PRIVATE_AUDIT_TAIL",
    ])
    log = ai_audit.AuditLog(sandbox / "ai_actions.jsonl")

    log.action("request", command, operation="add_task")
    log.verify("request", command, state="verified")

    assert "PRIVATE_" not in log.path.read_text(encoding="utf-8")
    assert [record["kind"] for record in log.read()] == ["action", "verify"]
