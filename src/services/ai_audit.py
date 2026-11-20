"""AI 动作的**只追加审计日志**（H4/P1，2026-11-02）。

为什么需要：原来的"账本"只有**计数摘要**（"验收通过 2"），既没有动作身份，也没有对象与字段；
事情过去之后再问"刚才 AI 到底改了什么、改前是什么、谁批的"就答不上来。审计日志把每次
**请求 / 动作 / 审批 / 验收 / 撤销** 各写一行 JSONL（append-only），是事后核查的唯一凭据。

设计约束（`docs/ai-harness-audit` 的 findings H4）：

- **只追加**：不用 `w`/`r+` 打开；只有轮转时才把整份文件改名（内容不丢）。
- **脱敏**：note / 备注类字段、手机号、密钥（`sk-…` / `Bearer …`）一律写成 `***`；
  命令里的 `--note/--notes` 值与 JSON `"note"` 字段也在这里剥掉（不能只靠字段名）。
  用户原话**只存 sha256 前缀 + 长度**，不落原文。
  ⚠ 这条是红线：日志会进 `data/` 仓库，不能把用户隐私再复制一份。
- **可解析**：一行一条 JSON，坏行只跳过（读侧不抛异常，免得一个坏行毁掉整份日志）。
- **轮转**：超过 `max_bytes` 就 `ai_actions.jsonl → ai_actions.1.jsonl → …`，最多留 `keep` 份。
  没有按天清理；保留上限 = `max_bytes × (keep + 1)`，且日志/快照都在 `data/.gitignore` 里
  （本地审计产物，不跟着数据仓库同步）。

⚠ 本模块**不**暴露给模型：没有对应的 `actions.py` 命令，提示词里也不提
（`tests/test_ai_policy.py::test_audit_and_undo_are_not_ai_commands` 守着）。
"""

import hashlib
import json
import logging
import os
import re
import shlex
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REDACTED = "***"
DEFAULT_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_KEEP = 5

# 字段名命中即整值脱敏（值不落盘）
_PII_KEYS = frozenset({
    "note", "notes", "notes_text", "remark", "remarks",
    "phone", "mobile", "tel", "telephone", "phone_number",
    "username", "user_name", "account", "email",
})
_SECRET_KEYS = frozenset({
    "api_key", "apikey", "key", "secret", "token", "access_token",
    "password", "passwd", "authorization", "cookie", "auth",
})

# 自由文本里的隐私/密钥（用户消息里也可能带）
_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer ***"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "1**********"),
)
_MAX_TEXT = 400

# 命令里的敏感参数：`--notes "…"` / `--phone=…`。长键名优先，避免 `--note` 先吃掉 `--notes`。
_PII_FLAGS = tuple(sorted(_PII_KEYS, key=len, reverse=True))
# `--plans '[{"title":…,"note":"…"}]'` 这类 JSON 载荷里的备注字段
_JSON_PII_RE = re.compile(
    r'(?i)("(?:' + "|".join(re.escape(name) for name in _PII_FLAGS) + r')"\s*:\s*)'
    r'"(?:[^"\\]|\\.)*"'
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _redact_text(text: str) -> str:
    """自由文本脱敏（手机号 / 密钥），并截断到 `_MAX_TEXT`（日志不做全文存档）。"""
    out = str(text)
    for pattern, repl in _TEXT_PATTERNS:
        out = pattern.sub(repl, out)
    return out[:_MAX_TEXT]


def _redact_command_parts(parts: list[str]) -> list[str]:
    """Remove complete sensitive argv values before producing an audit display."""
    out: list[str] = []
    hide_next = False
    for part in parts:
        if hide_next:
            out.append(REDACTED)
            hide_next = False
            continue
        flag, separator, _value = part.partition("=")
        name = flag[2:].lower().replace("-", "_") if flag.startswith("--") else ""
        if name in _PII_KEYS or name in _SECRET_KEYS:
            out.append(f"{flag}={REDACTED}" if separator else flag)
            hide_next = not separator
        else:
            out.append(_JSON_PII_RE.sub(lambda match: f'{match.group(1)}"***"', part))
    return out


def redact_command(command: str) -> str:
    """Redact argv values; malformed quoting hides the entire untrusted command."""
    try:
        parts = shlex.split(str(command or ""))
    except ValueError:
        return REDACTED
    # Keep the existing '--notes ***' display while quoting all other arguments.
    out = " ".join(part if part == REDACTED else shlex.quote(part)
                   for part in _redact_command_parts(parts))
    return _redact_text(out)


def user_summary(text: str) -> dict[str, Any]:
    """用户原话 → `{sha256 前缀, 长度}`（审计只留指纹，不留原文）。"""
    raw = str(text or "")
    return {
        "user_text_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
        "user_text_len": len(raw),
    }


def _redact_pair(key: object, item: Any, depth: int) -> Any:
    """单个字段的脱敏规则（键名 → 值）。"""
    name = str(key).lower()
    if name in _PII_KEYS or name in _SECRET_KEYS:
        return REDACTED
    if name == "command" and isinstance(item, str):
        return redact_command(item)
    return redact(item, depth + 1)


def redact(value: Any, _depth: int = 0) -> Any:
    """递归脱敏：命中敏感键 → `***`；字符串 → 去密钥/手机号；其余原样。

    ⚠ 键名匹配**只认完整键名**（`note` / `api_key` …）—— 不做子串匹配，
    否则 `kind`、`key_count` 这类字段会被误判成密钥。
    """
    if _depth > 6:                                  # 防御异常结构，不做无限递归
        return REDACTED
    if isinstance(value, dict):
        return {str(key): _redact_pair(key, item, _depth) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, _depth + 1) for item in value[:50]]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _archive_path(path: Path, index: int) -> Path:
    """`ai_actions.jsonl` + 1 → `ai_actions.1.jsonl`。"""
    return path.with_name(f"{path.stem}.{index}{path.suffix}")


class AuditLog:
    """append-only JSONL 审计日志（线程安全、自动轮转、写入即脱敏）。"""

    def __init__(self, path: Path, max_bytes: int = DEFAULT_MAX_BYTES,
                 keep: int = DEFAULT_KEEP) -> None:
        self.path = Path(path)
        self.max_bytes = int(max_bytes)
        self.keep = max(1, int(keep))
        self._lock = threading.Lock()

    @classmethod
    def for_data_dir(cls, data_dir, name: str = "ai_actions.jsonl") -> "AuditLog | None":
        """按数据目录建日志；`data_dir` 为空（如 worker 没拿到 dm）→ None（调用方跳过）。"""
        if not data_dir:
            return None
        return cls(Path(data_dir) / name)

    # ── 写 ────────────────────────────────────────────────
    def append(self, kind: str = "", /, **fields: Any) -> dict:
        """写一行：`{"ts": …, "kind": kind, ...}`（返回**已脱敏**的记录，便于测试断言）。

        ⚠ 事件类型是**位置限定参数**（`/`）：调用方仍可用 `kind=` 这个**字段**显式覆盖它
        （`append("misc", kind="action")` → `kind == "action"`）。没有 `/` 时这种调用会撞成
        `TypeError: got multiple values for argument 'kind'` —— 而 `kind` 本身既不是 PII
        也不是密钥，不该被"脱敏口径"牵连（见 `redact`：键名只认**完整**敏感名）。
        """
        event = str(fields.pop("kind", kind) or kind)
        record = redact({"ts": _now(), "kind": event, **fields})
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed(len(line.encode("utf-8")))
                with self.path.open("a", encoding="utf-8", newline="") as fh:
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())   # append-only 的意义在于"崩了也还在"
            except OSError:
                logger.error("审计日志写入失败（不影响主流程）：%s", self.path, exc_info=True)
        return record

    def _rotate_if_needed(self, incoming: int) -> None:
        """当前文件 + 本行超过 `max_bytes` → 轮转（改名，不重写内容）。"""
        if self.max_bytes <= 0 or not self.path.exists():
            return
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size + incoming <= self.max_bytes:
            return
        _archive_path(self.path, self.keep).unlink(missing_ok=True)
        for index in range(self.keep - 1, 0, -1):
            src = _archive_path(self.path, index)
            if src.exists():
                os.replace(src, _archive_path(self.path, index + 1))
        try:
            os.replace(self.path, _archive_path(self.path, 1))
        except OSError:
            logger.error("审计日志轮转失败：%s", self.path, exc_info=True)

    # ── 便捷写法（事件类型固定，便于 grep / 统计）──────────
    def request(self, request_id: str, **fields: Any) -> dict:
        return self.append("request", request_id=request_id, **fields)

    def request_user(self, request_id: str, text: str, **fields: Any) -> dict:
        """请求起点：用户原话只写指纹 + 长度（不落原文）。"""
        return self.request(request_id, **user_summary(text), **fields)

    def claim(self, request_id: str, text: str, evidence: str = "") -> dict:
        """模型自述：只写指纹/长度；`evidence` 是代码生成的账本摘要（可读）。"""
        raw = str(text or "")
        return self.append("claim", request_id=request_id,
                           claim_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
                           claim_len=len(raw), evidence=_redact_text(evidence))

    def action(self, request_id: str, command: str, **fields: Any) -> dict:
        return self.append("action", request_id=request_id, command=command, **fields)

    def approval(self, request_id: str, command: str, granted: bool,
                 reason: str, gesture_id: str = "", **fields: Any) -> dict:
        return self.append("approval", request_id=request_id, command=command,
                           granted=bool(granted), reason=reason,
                           gesture_id=gesture_id, **fields)

    def verify(self, request_id: str, command: str, state: str, detail: str = "",
               checked: int = 0, total: int = 0) -> dict:
        return self.append("verify", request_id=request_id, command=command,
                           state=state, detail=detail, checked=checked, total=total)

    def undo(self, request_id: str, snapshot_id: str, ok: bool, detail: str = "") -> dict:
        return self.append("undo", request_id=request_id, snapshot_id=snapshot_id,
                           ok=bool(ok), detail=detail)

    # ── 读（只给测试 / 事后工具用）────────────────────────
    def read(self) -> list[dict]:
        """逐行解析；坏行跳过并计数（**不抛异常**）。"""
        if not self.path.exists():
            return []
        out: list[dict] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            logger.error("审计日志读取失败：%s", self.path, exc_info=True)
            return []
        for line in lines:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("审计日志有坏行，已跳过：%s", self.path)
        return out

    def archives(self) -> list[Path]:
        """轮转出来的归档文件（新的在前）。"""
        return [p for p in (_archive_path(self.path, i) for i in range(1, self.keep + 1))
                if p.exists()]
