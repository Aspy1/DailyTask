# 2026-11-02 AI 助手 harness 审计（研究/审计阶段，只读）

- 关联 issue：`D:\ClaudeCoding\restart\.restart\issues\ISSUE-0002-harness-ai.md`（已人工审核通过）
- 类型：**只读审计**。未修改任何应用源码/测试，未 `git add`/`commit`/`push`，未读取 `data/settings.ini`，
  未触碰真实 `data/`（探针断言 `scripts.actions_core.DATA != <repo>/data`）。
- 基线：**git HEAD `83ef3a9`**（工作树正在被整改分支并发修改，见 §5）
- 产物目录：`docs/ai-harness-audit/`

## 1. 做了什么

1. 读 issue、`AGENTS.md`、AI 调用链源码（`ai_service/ai_instructions/ai_verify/ai_ledger/ai_loop_guards/
   ai_prompts/ai_providers`、`ai_panel.py`、`scripts/actions*.py`、`tests/test_ai_*`、`scripts/ai_eval.py`）。
2. 逐篇核验 issue 的 8 篇候选论文（窗口 2026-08-02～2026-11-02）：
   - arXiv API 取 v1 日期与版本；abs 页取 exact title / venue 字段；
   - 下载 HTML 全文（7 篇）与 PDF（P1，无 HTML）→ 转纯文本；
   - 用 `start/end` 标记**从原文切出** 18 条引文，并断言切出的字符串仍是原文子串（不匹配即 `SystemExit`）；
   - 写 `papers.csv` / `quotes.csv`（UTF-8-SIG，Excel 可直接打开）。
3. 写 6 个沙箱探针 `probe_ai_oversight.py`（stub provider，无网络/无 key），复现 H1/H2/H3/H5/H6/H7。
4. 按 H1–H9 写 `findings.csv` + `findings.md`（file:line、论文引文、修复、测试、状态、不能推出什么）。
5. 选出 3 个最严重问题（T1 未审批破坏性写入 / T2 无动作级撤销 / T3 伪成功通道），各带复现值与复现命令。

## 2. 关键结论（详见 findings.md）

- 论文 **8/8** 命中窗口；引文 **18/18** 逐字核验；未验证/删除 **0**。
- H1–H9 在 HEAD 上全部成立，**P0×3、P1×4、P2×2**。
- 探针 6/6 PASS：
  - A：`delete_item` 无确认执行，SHA `f4d96c63…` → `8a56ca6d…`；
  - B：`restore --yes` 由 AI 命令串触发，SHA 回到备份值，展示为“restore inventory.json：未核对”；
  - C：`add_item` 验收只核 count+name（quantity/location/min_qty 全不核），仍判 `verified`；
  - D：单块 12 条全执行（提示词写“最多 8 条”）、3 块全执行（提示词写“最多 1 块”）；
  - E：整文件 `restore` 把无关改动 `quantity 9 → 1` 一起回退；
  - F：物品备注里的注入文本原样进入 system prompt，无 `<data>`、无“数据不是指令”。
- 既有评估（`scripts/ai_eval.py`）11 个场景全部以“最终数据状态”为判据，不测监督质量；
  HEAD 的 100 个测试文件里 approval/undo/注入类为 **0**。

## 3. 涉及文件（只读）

| 类别 | 文件 |
| --- | --- |
| AI 服务 | `src/services/ai_service.py`、`ai_instructions.py`、`ai_verify.py`、`ai_verify_study.py`、`ai_ledger.py`、`ai_loop_guards.py`、`ai_prompts.py`、`ai_providers.py` |
| UI | `src/ui/components/ai_panel.py` |
| 执行层 | `scripts/actions.py`、`actions_cmds_items.py`、`actions_backup.py`、`actions_core.py` |
| 评估/测试 | `scripts/ai_eval.py`、`tests/test_ai_worker_retry.py`、`test_ai_ledger.py`、`test_ai_verify.py`、`test_instruction_parser.py`、`test_ai_exec_log.py` |
| 论文 | arXiv 2610.40917 / 2608.23642 / 2609.22248 / 2610.11351 / 2610.35835 / 2610.22987 / 2610.16426 / 2610.34239 |

## 4. 新增文件（本日志与 docs 产物，不改源码）

- `docs/ai-harness-audit/papers.csv`（8 行）
- `docs/ai-harness-audit/quotes.csv`（18 行）
- `docs/ai-harness-audit/findings.csv`（9 行）
- `docs/ai-harness-audit/findings.md`
- `docs/ai-harness-audit/probe_ai_oversight.py` + `probe_report.txt`
- `docs/ai-harness-audit/audit_snapshot.txt`（基线 sha + 17 个文件 SHA256/行数）
- `dev-logs/2026-11-02-AI助手harness审计.md`（本文件）

## 5. 并发改动警示（重要）

审计期间（2026-11-02 22:36–22:41）工作树被另一进程改写：新增 `ai_policy.py`、`ai_approval.py`、
`ai_undo.py`、`ai_audit.py`、`ai_guard.py`、`ai_verify_coverage.py`，并改写了 `ai_service.py`
（737 → 759 行）、`ai_instructions.py`、`ai_ledger.py`、`ai_verify.py`。其中一次中间态
`src/services/ai_service.py:193` 调用未定义的 `self._note_truncation(parsed)`，直接跑探针会
`AttributeError`（已复现）。因此：

- 审计证据固定在 **HEAD 的 `git archive` 只读快照**上（`audit_snapshot.txt` 有 SHA256）；
- 本报告**不评价**整改中的代码；`H1-H9` 的 “OPEN” 仅指 HEAD；
- 建议整改完成后用 `ai_oversight_eval` 重跑 §4 的 6 个探针，并把 before/after SHA 贴进最终 docx。

## 6. 未做 / 未验证

- 未做真实模型采样（stub provider）：证明的是执行路径，不是模型行为分布。
- 未做 UI 走查 / 用户测试（N=0）；P3 的 34.9% 只作设计警示。
- 未检查 `data/` 里历史误删/误改（不读用户数据）。
- docx 报告、代码修复、测试补齐属 issue 的后续阶段，本阶段未做。
