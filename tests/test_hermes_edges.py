"""Cover defaults, read-only queries, and receipts lost after dispatch."""

import json
import os
import subprocess
import sys
import time
import uuid

import pytest

from scripts import hermes_actions as bridge


def test_optional_course_defaults_match_the_cli(sandbox, monkeypatch) -> None:
    monkeypatch.setenv("LIFE_ASSISTANT_SINGLE_INSTANCE_KEY", f"HermesEdges-{uuid.uuid4().hex}")
    result = bridge.dispatch_request(
        {"action": "add_course", "parameters": {"name": "123", "day": 2}},
        data_dir=sandbox,
    )
    assert result["ok"] is True, result


@pytest.mark.parametrize("receipt", ["empty", "crash", "malformed", "unicode"])
def test_missing_trusted_receipt_reports_uncertainty(sandbox, monkeypatch, receipt) -> None:
    def execute(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        if receipt == "unicode":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        return subprocess.CompletedProcess(
            argv, 1 if receipt == "crash" else 0,
            "garbled receipt" if receipt == "malformed" else "", "",
        )

    monkeypatch.setattr(bridge.subprocess, "run", execute)
    result = bridge.dispatch_request(
        {"action": "add_task", "parameters": {"title": "A", "due": "2026-11-23"}},
        data_dir=sandbox,
    )
    assert result["ok"] is False
    assert result.get("uncertain") is True
    assert result["retry_safe"] is False


def test_empty_context_does_not_create_a_semester(sandbox) -> None:
    result = bridge.dispatch_request({"action": "context", "parameters": {}}, data_dir=sandbox)
    assert result["ok"] is True
    assert list(sandbox.iterdir()) == []


def test_corrupt_registry_is_reported_without_repair(sandbox) -> None:
    registry = sandbox / "semesters.json"
    registry.write_text("{broken", encoding="utf-8")
    before = registry.read_bytes()
    result = bridge.dispatch_request({"action": "context", "parameters": {}}, data_dir=sandbox)
    assert result["ok"] is False
    assert registry.read_bytes() == before
    assert list(sandbox.iterdir()) == [registry]


def test_context_separates_current_time_from_requested_plan_date(sandbox) -> None:
    result = bridge.dispatch_request(
        {"action": "context", "parameters": {"date": "2030-01-01"}}, data_dir=sandbox,
    )
    assert result["ok"] is True
    assert result["data"]["date"] == "2030-01-01"
    assert result["data"]["now"][:10] == result["data"]["today"]
    assert result["data"]["today"] != result["data"]["date"]


def test_explicit_data_directory_is_also_passed_to_cli(sandbox, monkeypatch) -> None:
    selected: list[str] = []

    def execute(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        selected.append(kwargs["env"]["LIFE_ASSISTANT_DATA_DIR"])
        return subprocess.CompletedProcess(argv, 0, "ERROR rejected", "")

    monkeypatch.setenv("LIFE_ASSISTANT_DATA_DIR", str(sandbox.parent / "unrelated"))
    monkeypatch.setattr(bridge.subprocess, "run", execute)
    bridge.dispatch_request(
        {"action": "add_task", "parameters": {"title": "A", "due": "2026-11-23"}},
        data_dir=sandbox,
    )
    assert selected == [str(sandbox.resolve())]


def test_bridge_delegates_to_running_application_receiver(sandbox, qapp) -> None:
    from PySide6.QtNetwork import QLocalServer

    from scripts.actions import run_argv_in_process
    from src.services.single_instance import decode_request, encode_reply

    key = f"HermesDelegate-{os.getpid()}-{uuid.uuid4().hex}"
    server = QLocalServer()
    assert server.listen(key)
    environment = {**os.environ, "LIFE_ASSISTANT_DATA_DIR": str(sandbox),
                   "LIFE_ASSISTANT_SINGLE_INSTANCE_KEY": key}
    process = subprocess.Popen(
        [sys.executable, str(bridge.ROOT / "scripts" / "hermes_actions.py")],
        cwd=bridge.ROOT, env=environment, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", shell=False,
    )
    process.stdin.write(json.dumps({
        "action": "add_task", "parameters": {"title": "123 'quoted'", "due": "2026-11-23"},
    }))
    process.stdin.close()
    connection = None
    buffer = b""
    requests: list[list[str]] = []
    deadline = time.monotonic() + 15
    try:
        while process.poll() is None and time.monotonic() < deadline:
            qapp.processEvents()
            if connection is None and server.hasPendingConnections():
                connection = server.nextPendingConnection()
            if connection is not None:
                buffer += bytes(connection.readAll())
                if b"\n" in buffer and not requests:
                    argv = decode_request(buffer.split(b"\n", 1)[0].decode("utf-8"))
                    assert argv is not None
                    requests.append(argv)
                    connection.write(encode_reply(True, run_argv_in_process(argv)))
                    connection.flush()
            time.sleep(0.01)
        assert process.poll() == 0
        result = json.loads(process.stdout.read())
        assert result["ok"] is True, result
        assert len(requests) == 1
        assert requests[0][0] == "add_task"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        server.close()
        QLocalServer.removeServer(key)
