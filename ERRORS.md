# ERRORS.md — 已踩过的坑

> 索引优先查阅。Agent 禁止通读全文——先扫索引，锁定了条目号再跳转。

## 索引

> 格式: 条目 → L{起始}-{结束} 行号范围

| 关键词 | 条目 | 行号 |
|---|---|---|
| 调整按钮/undo/save/安排/整理/.../arrange_pending | #001 | L28-L50 |
| 信号/emit/finished_with_instructions/Agent Loop | #001 | L33-L38 |
| prompt格式/JSON/sh冲突/_quick_arrange/输出格式 | #001 | L40-L43 |
| 指令重复执行/double-exec/_on_response_with_instructions | #001 | L45-L47 |

---

## 条目

### #001 | 2026-06-08 | 调整按钮点后"..."挂死，撤销/保存按钮不出现

L28-50 完整条目

**症状**: 点击日程视图的"调整"按钮 → 按钮变为"..."并 disabled → AI 确实执行了数据修改 → 但按钮永远不恢复，撤销/保存按钮从不出现

**根因（三重链）**:
1. `AIWorker.finished_with_instructions` 信号声明但从未 emit — Worker.run() 内部执行指令后只发 `finished`
2. `_quick_arrange` 的 prompt 要求 JSON 输出格式，但 `SYSTEM_PROMPT_BASE` 要求 `\`\`\`sh 代码块 — AI 收到冲突指令
3. `_arrange_pending` 只在 `_on_instructions_done`（永不被调用的死代码）里重置

**修复**:
- `src/services/ai_service.py` L134: Worker.run() 新增 `all_instructions` 追踪，有指令时 emit `finished_with_instructions`
- `src/ui/widgets/schedule_view.py` L282-287: prompt 从 JSON 格式改为 `\`\`\`sh` + `python scripts/actions.py` 命令
- `src/ui/main_window.py` L266-267: `response_received` 改为经 `_on_ai_response` 中转，兜底清 `_arrange_pending`
- `src/services/ai_service.py` L430-442: `_on_response_with_instructions` 去掉 `InstructionParser.execute()` 重复执行

**涉及文件**: `ai_service.py`, `schedule_view.py`, `main_window.py`

**教训**: 声明但未 emit 的 Qt 信号是 typo-like bug——连接了但永远不走。新增信号时必须在 emit 侧加搜索确认：`grep 'emit'` 能找到所有发射点。
