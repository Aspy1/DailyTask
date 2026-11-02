# 2026-11-02 AI 助手 harness 验收补齐（H9 + P-A～P-D + oversight eval）

- 关联 issue：`ISSUE-0002-harness-ai`（L3）
- 上一轮：`dev-logs/2026-11-02-AI助手harness整改-修复轮.md`（3 个失败测试 + ruff 收口）
- 本轮范围：补齐验收清单里**缺失的自动化证据**，不改既有策略口径，不碰真实 `data/`、
  不读 `data/settings.ini`、不 commit/push。

## 1. 接手时的缺口

全量 pytest 已绿（1036 passed），但 issue 的测试计划仍缺：

1. `tests/test_ai_guard.py`、`tests/test_ai_injection.py` 在注释里被引用，文件不存在；
2. P-A/P-B/P-C/P-D 没有端到端回归（只有零散的 policy/approval 单测）；
3. 验收覆盖（checked/total）没有直接测试；
4. H8 要求的 `ai_oversight_eval` 不存在；
5. H9 只做了"事实块/说明块分离"，【说明】没有"模型自述，未核验"标注；
6. `findings.csv` 只有 HEAD 基线状态（OPEN），没有工作树修复状态。

## 2. 变更清单

| 文件 | 变更 |
| --- | --- |
| `src/services/ai_ledger.py` | H9：`render_facts()` 的模型文本改为 `【说明】（模型自述，未核验；以【已执行】为准）` |
| `src/services/ai_guard.py` | 审批拒绝/无界面时补 `action` 审计行；无 broker 时也写 `approval` 行（审计闭环） |
| `src/services/ai_prompts.py` | `DATA_BOUNDARY` 举例改用全角标签，保证整段 prompt 只有 1 个可计数数据区 |
| `scripts/ai_oversight_eval.py` | 新增：12 个监督场景（未授权/绕过/拒绝/超时/允许/撤销/stale/注入/上限/伪成功/覆盖/脱敏） |
| `tests/test_ai_guard.py` | 新增：P-A/P-B/P-C、审批允许/拒绝/超时/伪造、撤销接线、worker + stub provider |
| `tests/test_ai_injection.py` | 新增：P-D 边界、围栏、真实 system prompt、restore 阻塞 |
| `tests/test_ai_parser_cap.py` | 新增：H6 单轮 8 / 整请求 24 / 单块 / 非法行 |
| `tests/test_ai_verify_coverage.py` | 新增：H5 checked/total、未核对、false success、登记完整性 |
| `tests/test_ai_oversight_eval.py` | 新增：评估必须全绿、H8 维度齐全、CLI 退出码 0 |
| `tests/test_ai_ledger.py` | 新增/扩展：H9 未核验标注 |
| `scripts/check_quality.py` · `MD-files/CODE_STANDARDS.md` · `README.md` | `docs/` 纳入 Q-P1 顶层白名单并登记 |
| `docs/ai-harness-audit/findings.csv` | 增加 `status_worktree` / `verification` 两列 |
| `docs/ai-harness-audit/oversight_eval_report.txt` | 评估输出 12/12 PASS |
| `dev-logs/2026-11-02-AI助手harness审计与整改报告.md` | 矩阵状态改为 `OPEN（HEAD）→ FIXED（工作树）`；补 §9.5 P-A～P-D 证据 |

## 3. 验证（本机，venv Python 3.14.8，`PYTHONIOENCODING=utf-8`）

| 命令 | 结果 |
| --- | --- |
| `pytest -q tests/test_ai_*.py` | **167 passed** |
| `pytest -q`（全量） | **1075 passed / 0 failed** |
| `python scripts/ai_oversight_eval.py` | **12/12 passed** |
| `ruff check src scripts plugins tests` | **All checks passed** |
| `compileall -q src scripts tests plugins` | 退出码 0 |
| `scripts/check_ui_tokens.py --strict --check-px` | 112 文件，违规 0 |
| `scripts/check_quality.py --strict` | ✓ 全部通过（新增/加重 0） |

## 4. 验收映射

| 验收项 | 证据 |
| --- | --- |
| P-A 未审批数据 SHA 不变 | `test_ai_guard.py::test_high_write_without_ui_is_blocked_and_sha_unchanged` |
| P-B `restore --yes` 不执行 | `test_ai_guard.py::test_restore_is_blocked_and_sha_unchanged` |
| P-C 12 条只执行 8 条 | `test_ai_parser_cap.py`、`test_ai_guard.py::test_only_eight_of_twelve_commands_run`、`test_worker_reports_truncation_for_twelve_commands` |
| P-D 注入不能造成未审批写入 | `test_ai_injection.py` 全部 |
| 撤销/审计/验收覆盖/命令上限 | `test_ai_undo.py`、`test_ai_audit.py`、`test_ai_verify_coverage.py`、`test_ai_parser_cap.py` |
| H8 监督质量评估 | `scripts/ai_oversight_eval.py`（12/12 PASS） |
| H9 自述标注 | `test_ai_ledger.py::test_render_facts_marks_model_text_as_unverified` |
| docx 可重开/zip/无坏图/无密钥手机号 | `md2docx.py` 重新生成 + zipfile/python-docx 校验 |

## 5. 残余项

- 单机软审批仍不是强 I-HITL；同机进程理论上可绕过（issue 非目标，报告已声明）。
- `ai_oversight_eval` 的 executor 是 stub：测执行门语义，不测每个 handler 的业务副作用。
- `check_quality` 的 SIZE/LOG-ONLY 存量债仍在 baseline（本轮未新增）。
- 工作树未 commit；用户原有的 attachments/notes 改动未触碰。

## 6. 关联条目

- `ERRORS.md`：本轮无新坑。
- `MD-files/ARCHITECTURE.md`：监督闭环的数据路径（审批/快照/审计）已在上一轮记录；
  本轮只补测试与文档，不改变架构。
