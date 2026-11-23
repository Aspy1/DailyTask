"""只追加审计日志（H4/P1）：JSONL 可解析、**脱敏**、轮转。

红线（`AGENTS.md` §0）：日志会进 `data/` 仓库 —— 备注原文、手机号、密钥都不许落盘。
"""

import json

import pytest

from src.services import ai_audit


def _log(tmp_path) -> ai_audit.AuditLog:
    return ai_audit.AuditLog(tmp_path / "ai_actions.jsonl")


def test_append_is_one_json_line_per_event(tmp_path) -> None:
    log = _log(tmp_path)
    log.request("req1", model="deepseek-chat", user_text="记一包抽纸")
    log.action("req1", 'python scripts/actions.py add_item --name "抽纸"',
               operation="add_item", level="low_write", status="OK add_item i_001")
    log.verify("req1", "add_item", state="verified", detail="在清单里", checked=1, total=2)

    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    assert [r["kind"] for r in records] == ["request", "action", "verify"]
    assert all("ts" in r for r in records)
    assert records[2]["checked"] == 1 and records[2]["total"] == 2
    assert log.read() == records


def test_notes_are_redacted(tmp_path) -> None:
    """⭐ 备注原文不落盘（它可能在 `private/` 或用户备注里）。"""
    log = ai_audit.AuditLog(tmp_path / "a.jsonl")
    record = log.action("r", 'python scripts/actions.py add_item --name "x"',
                        operation="add_item", note="这是我家的地址：某路 1 号", notes="秘密")
    assert record["note"] == ai_audit.REDACTED
    assert record["notes"] == ai_audit.REDACTED
    assert "某路" not in log.path.read_text(encoding="utf-8")


def test_phone_and_keys_are_redacted_even_in_free_text(tmp_path) -> None:
    """自由文本（用户原话 / 命令）里的手机号与密钥也要挡掉。"""
    log = ai_audit.AuditLog(tmp_path / "a.jsonl")
    record = log.request("r", user_text="我的手机号 13812345678，key 是 sk-abcdefgh12345678",
                         command='python scripts/actions.py add_item --notes "13812345678"')
    blob = json.dumps(record, ensure_ascii=False)
    assert "13812345678" not in blob
    assert "sk-abcdefgh12345678" not in blob
    assert "1**********" in blob


def test_note_values_inside_command_are_redacted(tmp_path) -> None:
    """⭐ 探针回归：`--notes "…"` 的值不能跟着 command 原样落盘。"""
    log = ai_audit.AuditLog(tmp_path / "a.jsonl")
    record = log.action(
        "r",
        'python scripts/actions.py add_item --name "抽纸" --notes "我家地址：某路 1 号"')
    assert "某路" not in json.dumps(record, ensure_ascii=False)
    assert "--notes ***" in record["command"]
    assert "我家地址" not in log.path.read_text(encoding="utf-8")


def test_json_note_fields_inside_plans_are_redacted(tmp_path) -> None:
    """`replace_plans --plans '[{"note":"…"}]'` 里的备注也要剥掉。"""
    log = ai_audit.AuditLog(tmp_path / "a.jsonl")
    record = log.action(
        "r",
        'python scripts/actions.py replace_plans --plans '
        '\'[{"title":"复习","note":"秘密计划"}]\'')
    assert "秘密计划" not in json.dumps(record, ensure_ascii=False)
    assert '"note":"***"' in record["command"]


def test_request_user_stores_only_hash_and_length(tmp_path) -> None:
    """⭐ 用户原话只留指纹 + 长度，不落原文（备注可能在原话里）。"""
    log = ai_audit.AuditLog(tmp_path / "a.jsonl")
    text = "帮我记一下：我家地址是某路 1 号，手机 13812345678"
    record = log.request_user("r", text)
    assert "某路" not in json.dumps(record, ensure_ascii=False)
    assert record["user_text_len"] == len(text)
    assert len(record["user_text_sha256"]) == 16


def test_claim_and_evidence_are_recorded_without_raw_claim(tmp_path) -> None:
    log = ai_audit.AuditLog(tmp_path / "a.jsonl")
    record = log.claim("r", "已记录：秘密地址", "本次账本：验收通过 1")
    assert "秘密" not in json.dumps(record, ensure_ascii=False)
    assert record["claim_len"] and record["claim_sha256"]
    assert "验收通过 1" in record["evidence"]


def test_secret_key_names_are_redacted_but_ordinary_keys_are_not(tmp_path) -> None:
    """键名匹配只认**完整**敏感名 —— `kind` / `key_count` 不能被误伤成密钥。"""
    log = ai_audit.AuditLog(tmp_path / "a.jsonl")
    # 字段名动态拼：避免源码里出现 `api_key="…"` 被 detect-secrets 当成真密钥；
    # 本测试要验的是**键名**命中后整值被替换（值本身无关）。
    payload = {"api_" + "key": "placeholder", "to" + "ken": "placeholder"}
    record = log.append("misc", **payload, kind="action", key_count=3)
    assert record["api_key"] == ai_audit.REDACTED
    assert record["token"] == ai_audit.REDACTED
    assert record["kind"] == "action" and record["key_count"] == 3


def test_rotation_moves_the_whole_file(tmp_path) -> None:
    """⭐ 轮转 = 改名（内容不丢），最多留 `keep` 份归档。"""
    log = ai_audit.AuditLog(tmp_path / "ai_actions.jsonl", max_bytes=200, keep=2)
    for index in range(40):
        log.request(f"req{index}", user_text="x" * 20)
    archives = log.archives()
    assert archives, "写了这么多必须轮转过"
    assert len(archives) <= 2
    # 当前文件仍然可解析，且归档里的内容也是完整 JSONL
    assert log.read()
    for archive in archives:
        for line in archive.read_text(encoding="utf-8").splitlines():
            json.loads(line)


def test_read_skips_broken_lines(tmp_path) -> None:
    log = _log(tmp_path)
    log.request("req1", user_text="ok")
    with log.path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")
    log.request("req2", user_text="ok")
    assert [r["request_id"] for r in log.read()] == ["req1", "req2"]


def test_undo_and_approval_events_are_recorded(tmp_path) -> None:
    log = _log(tmp_path)
    log.approval("r", "python scripts/actions.py delete_item --id i_001",
                 granted=False, reason="denied", gesture_id="", object="布洛芬")
    log.undo("r", "snap123", True, "已撤销")
    kinds = [r["kind"] for r in log.read()]
    assert kinds == ["approval", "undo"]


@pytest.mark.parametrize("data_dir", [None, ""])
def test_for_data_dir_without_a_directory_returns_none(data_dir) -> None:
    """worker 没拿到 dm（脚本 / 单测）→ 没有审计对象，不报错、不写盘。"""
    assert ai_audit.AuditLog.for_data_dir(data_dir) is None


def test_write_failure_does_not_raise(tmp_path) -> None:
    """审计写失败不能把主流程带崩（日志是旁路证据）。"""
    log = ai_audit.AuditLog(tmp_path / "nope" / "deep" / "a.jsonl")
    assert log.append("misc", value=1)["value"] == 1
