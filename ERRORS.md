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
| 分类/全部分类/只显示其他/categories/fallback | #003 | L87-L97 |
| parse_date/这周五/中午12点/中文时间/日期解析 | #004 | L102-L113 |
| fill_ai_prompt/右键菜单/填充AI/AI面板不展开 | #004 | L115-L122 |
| run_in_process/Namespace/AttributeError/默认值/argparse | #005 | L127-L146 |

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

**教训**: Widget 全量销毁+重建是 PySide6 最高频的性能杀手——`deleteLater()` + `insertWidget()` 触发完整 layout pass + QSS 重解析 + paint。hash-based 跳过可减少 80%+ 的重建次数。

---

### #003 | 2026-06-09 | 分类 filter 只显示"其他"

L87-L97

**症状**: 点击"全部分类"只弹出一个选项"其他"，五个分类全不显示。

**根因**: `InventoryModel.categories` property 的 fallback 硬编码为 `["其他"]`——当 JSON 文件中无 `categories` 键时（旧版本数据文件），返回此单元素列表。filter 从 property 读分类 → 只得到一个"其他"。

**修复**: `inventory.py` `categories` property：缺键时从 `DEFAULT_INVENTORY["categories"]` 读取完整列表并写入 `_data`（自动修复旧数据文件）。

**涉及文件**: `src/models/inventory.py`

**教训**: property 的 fallback 值不应硬编码业务数据。应引用常量（`DEFAULT_INVENTORY["categories"]`）作为权威来源，确保 fallback 与初始值一致。

**补充说明**: 此 bug 之前被另一个设计掩盖——filter 原本从已有物品提取分类（`set(it["category"] for it in items)`），只显示有物品的分类。该行为是设计选择而非 bug，但掩盖了 property fallback 的硬编码问题。

---

### #004 | 2026-06-10 | 中文日期解析失败 + AI 面板不展开

L102-L122

**症状 1**: AI 收到的作业 DDL 是"这周五中午12点"，任务虽然创建了但 `due_date` 字段是垃圾值 `"这周五中午12点T23:00:00"`。

**根因 1**: `parse_date()` 的"本周X"正则 `(?:本周)?周(.)` 不匹配"这周X"（`这`≠`本`）。时间"中午12点"完全未处理，`normalize_time()` 只追加默认 T23:00:00。

**修复 1**: `parse_date`: `(?:这|本)?周(.)` 同时匹配"这周"和"本周"。`normalize_time`: 新增中文时间提取——中午/下午/上午/晚上 + 数字点 ± 半 → HH:MM:SS。

**症状 2**: 课程表右键"布置了作业"等操作后，AI 面板不自动出现，用户看不到已填充的提示词。

**根因 2**: `fill_input()` 只设置文本不展开面板。AI 面板初始 splitter 宽度为 0（隐藏）。

**修复 2**: `_connect_course_table` 改为连接 `_on_course_fill_ai` 方法，先 `_on_ai_toggle(True)` 展开面板再 `fill_input(prompt)`。

**涉及文件**: `scripts/actions.py`, `src/ui/main_window.py`, `src/ui/components/main_workspace.py`

**补充**: 修复后 task 面板仍不刷新——`_on_data_changed` 只对 `"task" in action` 刷新 task_panel，AI 操作发 `"ai_action"` 不匹配。task/expense/habit 三面板均遗漏 `is_ai` 检查。已在所有面板统一加 `or is_ai`。

**教训**: 正则边界条件（`这` vs `本`）和 UI 可见性（隐藏面板填充不可见）是"静默失败"的高发区。

---

### #005 | 2026-06-10 | run_in_process 缺 argparse 默认值导致全线 crash

L127-L146

**症状**: AI 说"已添加任务"但任务未创建，tasks.json 无记录。后续发现 add_plan 等也受影响——所有不传可选参数的 AI 命令静默失败。

**根因**: `run_in_process()` 手动 `shlex.split` 解析命令行构建 `argparse.Namespace`，但只设置了 CLI 中明确出现的 `--key value`。argparse 的 `default=` 机制完全被绕过。如 `--priority medium` 未出现在命令中 → Namespace 无 `priority` 属性 → `args.priority or "medium"` 先求值 `args.priority` 即抛 `AttributeError`（`or` 保护无效——Python 求值顺序）。

**修复**: `run_in_process()` 中在调用 handler 前遍历所有已知可选参数的默认值 dict，用 `hasattr` 检查 + `setattr` 补全。共覆盖 22 个可选参数（priority/schedule/duration/slot/type/weeks/slots/parity/category/quantity/min_qty/tags/notes/location/scope/teacher/course/reminder/unit/status/due/note）。

**模拟验证**: 全部 16 条命令（add_task/complete_task/add_exam/add_habit/log_habit/add_plan/replace_plans/delete_plan/add_course/delete_course/add_item/update_item/need_restock/lookup_item/status/delete_item）零 crash。

**涉及文件**: `scripts/actions.py`

**教训**: 手动实现 arg parser 时必须同步 argparse 的 `default=` 值。`args.xxx or default` 不防 AttributeError——Python 先求值左侧才到 `or`。正确写法：`getattr(args, 'xxx', default)` 或预填充 Namespace。——连接了但永远不走。新增信号时必须在 emit 侧加搜索确认：`grep 'emit'` 能找到所有发射点。
