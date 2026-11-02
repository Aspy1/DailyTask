# 2026-11-02 AI 助手 harness 复审修复（8 条 review findings）

- 关联 issue：`ISSUE-0002-harness-ai`（review findings，fix 轮）
- 范围：只修 findings 指出的缺陷；不改 AI 监督语义的总体设计，不碰真实用户数据。
- 工作树未提交的其它改动保持原样；本 commit 只含这些修复。

## 1. 逐条修复

### M1 审计仍可能落备注原文（major）

- `ai_audit.py` 新增 `redact_command()`：把 `--note/--notes/--phone/--email/--account…`
  的值剥成 `***`，并处理 `--plans '[{"note":"…"}]'` 这类 JSON 载荷里的备注字段；
  `redact()` 对 `command` 键统一走这条路径。
- `AuditLog.request_user()`：用户原话只落 `user_text_sha256`（16 位）+ `user_text_len`；
  `ai_service._send_to_ai()` 改用该接口，不再写 `user_text` 原文。
- 回归：`tests/test_ai_audit.py`（命令 note、JSON note、user_text 指纹）、
  `tests/test_ai_guard.py`（执行门写日志时备注不落盘）。
- 同步/保留策略：`data/.gitignore` 增加 `ai_actions.jsonl` / `ai_actions.*.jsonl` / `ai_undo/`；
  `ARCHITECTURE.md` §8.2 明确它们是本地-only，`git_sync` 不推送；轮转 2MB×5，无按天清理。

### M2 replace_plans 仍可能 false success（major）

- `ai_verify.PLAN_FIELDS`：title/time_slot/type/note/course_name/course；
  `_check_replace_plans()` 逐条逐字段比对**用户显式传了**的字段，不再只比 title。
- `ai_verify_coverage`：`replace_plans` 的分母改为载荷里实际出现的子字段（不再笼统算 1 个
  `plans` 字段）；同标题不同 `time_slot` 现在返回 `MISMATCH`，不是 `VERIFIED 1/1`。
- 回归：`tests/test_ai_verify_coverage.py` 新增三个用例（子字段分母 / slot 不一致 / 全字段一致）。

### m3 审批弹窗超时被记成 DENIED（minor）

- `ApprovalBroker.resolve(..., reason=TIMEOUT)` 支持显式超时原因；
  `ApprovalPrompt` 在 `dialog.timed_out` 时传 `TIMEOUT`。
- 回归：`tests/test_ai_approval.py::test_prompt_timeout_is_recorded_as_timeout`（适配器层）。

### m4 undo index 无锁 / 固定临时名（minor）

- `SnapshotStore` 增加 `RLock`，`capture/finalize/latest/undo` 的读改写串行化；
  `_write_index()` 用 `uuid` 唯一临时名。
- 回归：`tests/test_ai_undo.py::test_index_survives_concurrent_capture_and_finalize`
  （6 线程 × 5 次 capture/finalize，index 完整、无 `.tmp` 残留）。

### m5 no-op 也显示“可撤销”（minor）

- `Snapshot.undoable` 要求 `written`（after_hash ≠ before_hash）；
  `_apply_undo()` 对 no-op 返回“没有改变文件，无需撤销”。
- 回归：`tests/test_ai_undo.py::test_noop_snapshot_is_not_undoable`。

### m6 报告/CSV 夸大审计字段（minor）

- 实际补齐：`action` 写 before/after/duration_ms；`approval` 写 before/after；
  `AIWorker._report()` 写 `claim_sha256 + claim_len + evidence`（不落模型原文）。
- 报告 §9.1/§9.5 与 `findings.csv` H4/H9 改为实际字段；H9 明确是 claim 指纹，不是原文。

### m7 list_backups 文档不一致 / 新数据文件未登记（minor）

- 保留 `list_backups` 为只读（它不写文件），修正 `findings.csv` 与 `findings.md`：
  只移除 `restore`。
- `ARCHITECTURE.md` §8 数据布局与 §8.2 登记 `ai_actions.jsonl` / `ai_undo/` 及同步/保留策略。

### m8 baseline 新债 / docx 计数过期（minor）

- `PLAN.md` 增加「2026-11-02 · Q-A1 baseline accepted exception（ISSUE-0002）」：
  列出 5 个尺寸项与 LOG-ONLY 34→36、拆分目标、只防新增原则；不是静默放行。
- `AIService` 经提取 `_audit_claim` / `_with_notes` / `_last_user_text` 后回到 418 行，
  baseline 不再加重；报告 §9.2 更新为 **1089 passed**，docx 在最终门禁后重新生成。

## 2. 验证（本机，venv Python 3.14.8）

| 命令 | 结果 |
| --- | --- |
| `pytest -q`（Restart fast gate，经 cmd） | **1089 passed** |
| `pytest -q tests/test_ai_*.py` | **179 passed** |
| `python scripts/ai_oversight_eval.py` | **12/12 passed** |
| `ruff check src scripts plugins tests` | All checks passed |
| `compileall -q src scripts tests plugins` | 退出码 0 |
| `scripts/check_ui_tokens.py --strict --check-px` | 112 文件，违规 0 |
| `scripts/check_quality.py --strict` | ✓ 全部通过（RADON/SIZE/LOG-ONLY 均未新增） |

## 3. 残余风险

- 审计里的 `claim_sha256` 只能证明“模型说过什么”，不能还原原文；这是隐私优先的取舍。
- `data/.gitignore` 属于**数据仓库**工作区，本 commit 不含它；下一次数据同步会带上该排除规则。
- 软审批仍不是强 I-HITL；同机进程理论上可绕过（issue 非目标，报告已声明）。
