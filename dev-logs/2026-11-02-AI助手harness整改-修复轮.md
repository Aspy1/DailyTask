# 2026-11-02 AI 助手 harness 整改 · 修复轮（3 个失败测试 + 14 条 ruff）

- 关联 issue：`ISSUE-0002-harness-ai`（已人工审核通过）；上一阶段只读审计见
  `dev-logs/2026-11-02-AI助手harness审计.md`
- 范围：**只修已有整改代码的缺陷**（`ai_policy/approval/guard/audit/undo/ledger` 一族）。
  不新增功能、不改提示词口径、不碰 `data/`、不 `git add`/`commit`/`push`、不生成 docx。
- 接手时基线：`pytest -q tests/test_ai_*.py` = **3 failed / 123 passed**；
  `ruff check src scripts tests` = **14 errors**。

## 1. 三个失败测试：成因与修复

### 1.1 `test_ai_approval.py::test_deny_returns_no_gesture`

- 成因：`ApprovalBroker.resolve()` 把 `reason` 先赋成字面量 `"approved"`，只在"手势无效"
  分支里改。用户点「拒绝」时 `granted=False` 但 `reason` 仍是 `approved` →
  审计日志里"用户拒绝"和"已批准"分不开，`ApprovalOutcome.denied_by_user` 永远为假。
- 修复：`src/services/ai_approval.py::ApprovalBroker.resolve()` 按结论显式分派
  `DENIED`（拒绝；交来的 gesture 一并作废、不写回 outcome）/ `APPROVED`（有合法手势）/
  `INVALID_GESTURE`（伪造手势 → 拒绝）。超时仍由 `request()` 返回 `TIMEOUT`（= 拒绝）。
- 新增回归：
  - `test_deny_is_still_a_denial_when_a_gesture_is_handed_in`（拒绝 + 手里有 gesture 仍是
    `DENIED`，且 gesture 被作废）；
  - `test_denied_high_risk_action_writes_nothing_and_is_audited`（**端到端**：`ai_guard.run_batch`
    对 `delete_item` 被拒 → 执行器一次都没被调用、`inventory.json` 原样不动、审计里
    `approval.reason == "denied"`）。

### 1.2 `test_ai_audit.py::test_secret_key_names_are_redacted_but_ordinary_keys_are_not`

- 成因：`AuditLog.append(kind, **fields)` 的 `kind` 是普通参数，
  `append("misc", kind="action")` 直接 `TypeError: got multiple values for argument 'kind'`。
- 修复：`src/services/ai_audit.py::AuditLog.append()` 改为
  `append(self, kind: str = "", /, **fields)` —— `kind` 是**位置限定参数**，
  `kind=` 变成普通字段（显式字段优先）。记录 schema 仍是 `{"ts", "kind", ...}`。
- 脱敏口径**未放宽**：`redact()` / `_PII_KEYS` / `_SECRET_KEYS` 一行未改，键名只认**完整**
  敏感名（`kind` / `key_count` 不误伤，`api_key` / `token` 照旧 `***`）。
- 顺带补注解（`ANN201/ANN003`）：`redact()`、`append()`、`request/action/approval()`。

### 1.3 `test_ai_ledger.py::test_worker_shows_the_fact_block_even_when_clean`

- 成因：`ai_guard._run_one()` 写的是 `label = ai_verify.label_of(...) if data_dir else ""`。
  没有数据目录（脚本 / 部分单测 / 刚启动）时对象名被清空 → 事实行退化成
  「记入：未核对」，用户看不出是哪件东西（H4：账本缺对象身份）。
- 修复：`src/services/ai_guard.py` —— 一律调用 `label_of(command, data_dir)`；
  它在 `data_dir` 为空时**退回命令里本来就有的参数**（`--name` 等），不读盘。`describe()`
  （审批框展示）同口径。
- 未改验收口径（**没有数据就不许说"验收通过"**）：
  - 无数据目录 → 「记入 抽纸：未核对」；
  - 有数据目录 → 「记入 抽纸：验收通过，但只核对了 1/2 字段 ——「抽纸」在清单里」。
  覆盖标签（`（n/m 字段）`）与 partial/unverified 的措辞全部保留。

## 2. ruff：14 → 0（不改规则、不加 broad ignore）

| 规则 | 位置 | 处理 |
| --- | --- | --- |
| ANN003 | `ai_approval.py:180` `new_request(**kwargs)` | 补 `**kwargs: object` |
| ANN201 | `ai_audit.py:65` `redact()` | 补 `value: Any` / `-> Any` |
| ANN003 ×3 | `ai_audit.py` `append/request/action/approval` | 补 `**fields: Any` |
| F841 | `ai_instructions.py:111` | 删掉未使用的 `dropped` 局部变量 |
| I001 + F401 ×2 | `ai_service.py` 头部 import | 删 `hashlib`/`json`；`ai_prompts` 的混排 `as` 导入按项目既有口径拆成单句（`combine-as-imports=false`），并注明别名为何必要（`_build_system_prompt` 里有同名局部变量，写成 `course_list = course_list(...)` 会 `UnboundLocalError`） |
| I001 | `ai_verify_coverage.py:21` | `_CHECKS` 排到 `FAILED` 之前（ruff isort 口径） |
| RUF046 | `ai_approval_dialog.py:88` | `int(round(x))` → `round(x)` |
| ANN202 | `tests/test_ai_approval.py:99` `_dialog()` | 补返回注解（`TYPE_CHECKING` 导入 `ApprovalDialog`，运行时仍是字符串注解） |
| S106 | `tests/test_ai_audit.py:57` `token="abc"` | 逐处 `# noqa: S106` + 理由（故意的假令牌，本测试就是在验它被脱敏） |

## 3. 连带修掉的两条既有失败（同一功能引入，被既有测试拦下）

1. `tests/test_data_events.py::test_every_emitted_event_is_registered`：
   `AIService.undo_last_action()` 发 `data_changed.emit("ai_undo")` 但没在
   `main_workspace.EVENT_PANELS` 登记 → 补 `"ai_undo": ALL_PANELS`（撤销可能回退任意文件，按全刷）。
2. `tests/test_prompt_consistency.py::test_every_implemented_command_is_advertised[restore]`：
   H2/P0 已把 `restore` 从 AI 工具集移除（`ai_policy._FORBIDDEN_OPS`，保留 CLI 手动），
   该测试仍要求"有 handler 就必须宣传"。改为 `MANUAL_ONLY = {"restore"}`：
   排除出正向参数化，并**反向**新增 `test_manual_only_commands_are_never_advertised`
   （比原来更严：谁再把 `restore` 写回提示词，这条会红）。

## 4. 顺带降低复杂度（radon C 级 → 0）

- `ai_ledger.fact_line()`（C 11）拆成 `_fact_head()` + `_fact_verdict()`，输出逐字不变；
- `ai_guard._intent_after()`（C 11）改成 `_AFTER_PREVIEW` 派发表 + `_pick()`（展示用预览，语义不变）。

## 5. 验证（本机，`PYTHONIOENCODING=utf-8`，venv Python 3.14.8）

| 命令 | 结果 |
| --- | --- |
| `pytest -q tests/test_ai_*.py` | **127 passed**（接手时 3 failed / 123 passed） |
| `pytest -q`（全量） | **1033 passed / 2 failed** —— 两条都是 `tests/test_quality_gates.py` 的存量 SIZE/LOG-ONLY 债，见 §6 |
| `ruff check src scripts tests` | **All checks passed**（14 → 0） |
| `compileall -q src scripts tests` | 通过 |
| `scripts/check_ui_tokens.py --strict --check-px` | 通过（违规 0） |
| `scripts/check_quality.py --strict` | **6 项违规**（全是 §6 的存量债；radon/import-linter/vulture/silent/id-gen 均已通过） |

## 6. 剩余项（未修，属存量尺寸债；不是本轮 3 个缺陷的一部分）

`scripts/check_quality.py --strict` 仍报 6 项，全部由**本次整改新增的代码**落在**已经很大**的类里造成：

```
SIZE  class:AIService@src/services/ai_service.py = 422 行（上限 400，baseline 无此项）
SIZE  class:MainWindow@src/ui/main_window.py = 537 行（baseline 520 → 超 17）
SIZE  func:__init__@src/ui/components/ai_panel.py = 87 行（baseline 79 → 超 8）
SIZE  func:_build_system_prompt@src/services/ai_service.py = 73 行（上限 60）
SIZE  func:run@src/services/ai_service.py = 63 行（上限 60）
LOG-ONLY 日志是块内唯一语句 36 处 > baseline 34（新增 2 处）
```

它们需要**把代码搬出这些类**（例如把 `<data>` 上下文拼装搬到 `ai_prompts`、把审批弹窗 +
撤销接线收进独立的 UI 辅助类），属于结构性重构，本轮未做（避免改动 `MainWindow` 里
与 AI 无关的并发改动，也避免用 `--write-baseline` 把新债记进台账）。
`tests/test_quality_gates.py` 的两条测试因此仍红：`test_repository_passes_quality_gate`、
`test_baseline_is_not_behind_current_state`。

## 7. 关联条目

- `ERRORS.md`：本轮没有踩到新坑（三个缺陷都是"取值/签名/兜底条件写错"，不是环境问题）。
- `MD-files/ARCHITECTURE.md`：`ai_undo` 事件已并入"数据事件 → 面板"映射，架构文档里的
  事件表若列举过 `ai_action`，建议下次一并补 `ai_undo`（本轮未改文档，避免与并发改动冲突）。
