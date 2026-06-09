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
| 启动慢/show/首屏 | #002 | L55-L60 |
| 未响应/卡顿/_refresh/deleteLater/全量重建 | #002 | L62-L70 |
| subprocess/子进程/actions.py/启动开销 | #002 | L73-L82 |

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

---

### #002 | 2026-06-08 | 启动延迟 + AI 操作后 UI "未响应"

L55-82

**症状**: 启动后有明显黑屏等待；点击"调整"或 AI 操作后窗口短暂冻结、"未响应"。

**根因（三重源）**:
1. `app.py`: `self._window.show()` 在 init 末尾（L163），之前已等了 JSON 加载 + MainWindow 全量构建
2. `schedule_view._refresh()`: 每次都 `while layout.count > 1: takeAt → deleteLater` 销毁全部卡片再从头 `insertWidget` 重建——即使只改了一个时段的数据
3. `InstructionParser.execute()`: 每条 AI 指令执行 `subprocess.run("python scripts/actions.py ...")` ——完整 Python 启动 + import + JSON 读写 + 退出

**修复**:
- `app.py` L144-163: `show()` 移到 MainWindow 创建后立即执行，tray/reminder/instance 在窗口可见后初始化
- `schedule_view.py` L332-591: `_refresh()` 改为增量更新——用 `hashlib.md5` 对每时段内容做 hash，hash 未变则跳过（不销毁不重建），新增 `_slot_cards`/`_slot_hashes` dict 追踪
- `scripts/actions.py`: 新增 `run_in_process(cmd_str)` ——`shlex.split` 解析命令 → 构建 `argparse.Namespace` → 直接调 handler，用 `contextlib.redirect_stdout` 捕获输出
- `ai_service.py` InstructionParser.execute: 优先 `from scripts.actions import run_in_process` 内存调用，ImportError 时 fallback 到 subprocess

**涉及文件**: `app.py`, `schedule_view.py`, `scripts/actions.py`, `ai_service.py`

**教训**: Widget 全量销毁+重建是 PySide6 最高频的性能杀手——`deleteLater()` + `insertWidget()` 触发完整 layout pass + QSS 重解析 + paint。hash-based 跳过可减少 80%+ 的重建次数。——连接了但永远不走。新增信号时必须在 emit 侧加搜索确认：`grep 'emit'` 能找到所有发射点。
