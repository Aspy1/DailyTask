# ERRORS.md — 已踩过的坑

> 查阅方式：**先扫索引，锁定条目号，再跳转**。不要通读全文。
> 每条 ≤20 行；新增请追加编号并登记索引。
> 关联：`MD-files/ARCHITECTURE.md`（运作原理）· `MD-files/CODE_STANDARDS.md`（规范）。
>
> 【2026-10-15】本文件已合并原 `MD-files/ERRORS.md`（13 条）→ 现为**唯一**避坑记录；
> 索引不再写死行号（原按行号跳转，条目一动即失效）。

## 索引

| 关键词 | 条目 | 类别 |
|---|---|---|
| 调整按钮/undo/save/安排/arrange_pending/信号未 emit | #001 | 信号链 |
| prompt 格式/JSON 与 sh 冲突/指令重复执行 | #001 | AI |
| 启动慢/首屏/show 顺序 | #002 | 性能 |
| 未响应/卡顿/_refresh/deleteLater/全量重建 | #002 | 性能 |
| subprocess/actions.py/启动开销 | #002 | 性能 |
| 分类只显示"其他"/categories fallback | #003 | 数据 |
| parse_date/这周五/中午12点/中文时间 | #004 | AI |
| fill_ai_prompt/右键填充/AI 面板不展开 | #004 | UI |
| run_in_process/Namespace/AttributeError/argparse 默认值 | #005 | AI |
| content.replace 批量替换/递归/_update_breadcrumb | #006 | 流程 |
| clicked 传参/checked=False 覆盖默认参数 | #007 | 信号 |
| `_file_path`/`file_path` 属性名 | #008 | 数据 |
| f-string 花括号未转义 | #009 | 流程 |
| sep4 未定义/分隔符编号混乱 | #010 | UI |
| "未知操作"/执行器未注册 action | #011 | AI |
| 信号冲突/两个 handler 接同一信号 | #012 | 信号 |
| 替换文本未精确匹配/旧代码残留/文件变大 | #013 | 流程 |
| execute_code 忘记 import | #014 | 环境 |
| Windows bash/MSYS/exit 126/缺 DLL | #015 | 环境 |
| 语法检查缺失/连锁报错 | #016 | 流程 |
| DDL 计数按精确时间而非按天 | #017 | 数据 |
| 状态栏残留占位 widget | #018 | UI |
| mousePressEvent 右键也触发点击 | #019 | UI |

---

## 条目

### #001 | 2026-06-08 | 调整按钮点后"..."挂死，撤销/保存按钮不出现

**症状**: 点"调整" → 按钮变"..."且 disabled → AI 确实改了数据 → 但按钮永不恢复，撤销/保存从不出现。

**根因（三重链）**:
1. `AIWorker.finished_with_instructions` 信号**声明但从未 emit**
2. `_quick_arrange` 的 prompt 要求 JSON 输出，与 `SYSTEM_PROMPT_BASE` 要求的 ```sh 冲突
3. `_arrange_pending` 只在 `_on_instructions_done`（死代码）里重置

**修复**: Worker 追踪 `all_instructions` 并在有指令时 emit；prompt 改为 ```sh + `actions.py` 命令；
`response_received` 经 `_on_ai_response` 中转兜底清 `_arrange_pending`；去掉重复执行。

**涉及**: `ai_service.py` `schedule_view.py` `main_window.py`

**教训**: **声明但未 emit 的 Qt 信号 = typo-like bug**。新增信号必须 `grep 'emit'` 确认有发射点。

---

### #002 | 2026-06-08 | 启动延迟 + AI 操作后 UI "未响应"

**根因（三源）**:
1. `show()` 在 `__init__` 末尾，之前已等 JSON 加载 + MainWindow 全量构建
2. `schedule_view._refresh()` 每次销毁全部卡片再重建（layout pass + QSS 重解析 + paint）
3. `InstructionParser.execute()` 每条指令都 `subprocess.run("python scripts/actions.py")`

**修复**: `show()` 提前；`_refresh()` 改 hash 增量（未变则跳过）；新增 `actions.run_in_process()` 内存调用替代 subprocess。

**涉及**: `app.py` `schedule_view.py` `scripts/actions.py` `ai_service.py`

**教训**: Widget 全量销毁+重建是 PySide6 最高频的性能杀手。

---

### #003 | 2026-06-09 | 分类 filter 只显示"其他"

**根因**: `InventoryModel.categories` property 的 fallback 硬编码为 `["其他"]`；旧数据文件无 `categories` 键时只返回这一项。

**修复**: 缺键时从 `DEFAULT_INVENTORY["categories"]` 读完整列表并写回（自动修复旧数据）。

**教训**: property 的 fallback 不应硬编码业务数据，应引用权威常量。

---

### #004 | 2026-06-10 | 中文日期解析失败 + AI 面板不展开

**症状 1**: DDL "这周五中午12点" → `due_date` 变成垃圾值 `"这周五中午12点T23:00:00"`。
**根因 1**: `parse_date` 的 `(?:本周)?周(.)` 不匹配"这周X"；"中午12点"未处理。
**修复 1**: 正则改 `(?:这|本)?周(.)`；`normalize_time` 支持 中午/下午/上午/晚上 + N点(半)。

**症状 2**: 课程表右键后 AI 面板不出现，看不到已填充的提示词。
**修复 2**: 改连 `_on_course_fill_ai`，先展开 AI 面板再 `fill_input`。

**补充**: task/expense/habit 三面板对 `ai_action` 不刷新 → 统一加 `or is_ai`。

**教训**: 正则边界（这/本）+ UI 可见性（隐藏面板填充不可见）是"静默失败"高发区。

---

### #005 | 2026-06-10 | `run_in_process` 缺 argparse 默认值导致全线 crash

**症状**: AI 说"已添加任务"但未创建；所有不传可选参数的命令静默失败。
**根因**: 手搓 `shlex`→`Namespace` 只设命令行里出现的参数，绕过 argparse 的 `default=`。
`args.priority or "medium"` 先求值 `args.priority` → `AttributeError`（`or` 不保护）。
**修复**: 调用 handler 前用默认值 dict 遍历补齐 22 个可选参数。

**教训**: 手写 parser 必须同步 argparse 默认值；`args.x or d` 不防 `AttributeError`，应 `getattr(args,'x',d)`。

---

### #006 | 2026-06-12 | `content.replace` 批量替换导致递归 + `AttributeError`

**症状**: 启动崩溃 `AttributeError: 'InventoryPanel' object has no attribute '_bc_cat'`；
修复后 `RecursionError`（自调用）。
**根因**: 把多处 `self._breadcrumb.hide()` 批量替换为 `_update_breadcrumb()`，
其中一处是 `_update_breadcrumb` 自身的 `else` 分支 → 自调用死循环；另一处在控件未创建时调用。
**修复**: 还原 else 分支的 `hide()`；移除 `__init__` 中的过早调用。

**教训**: `content.replace()` 批量替换极其危险，**涉及自身引用的改动必须精确定位**（见 `CODE_STANDARDS` §4）。

---

### #007 | clicked 信号传参污染

**症状**: 点"调整"按钮，`_quick_arrange(days)` 的 `days` 变成 `False`（快照显示"未来 False 天"）。
**根因**: `QPushButton.clicked` 自动传 `checked=False` 覆盖了默认参数。
**修复**: `btn.clicked.connect(lambda: self._quick_arrange())`。

---

### #008 | `_file_path` → `file_path` 属性名错误

**症状**: `AttributeError: 'DailyLogModel' object has no attribute '_file_path'`。
**根因**: `BaseJsonModel` 的属性名是 `file_path`，不是 `_file_path`。

---

### #009 | f-string 内花括号未转义

**症状**: JSON 示例 `{"action":"add_plan"}` 被当作 f-string 插值解析。
**修复**: f-string 内的花括号必须双写 `{{"action":"add_plan"}}`（见 R-008）。

---

### #010 | 分隔符变量编号混乱（`sep4` 未定义）

**症状**: `UnboundLocalError: cannot access local variable 'sep4'`。
**根因**: 往已有 sep1–sep4 的状态栏插入新组件，只改局部编号，后面仍引用旧变量名。
**修复**: 新增分隔符用独立命名（如 `sep_exam`），或整体重写该段。

---

### #011 | AI 输出"未知操作: xxx"

**症状**: AI 生成 `replace_plans` 指令，执行器报"未知操作"。
**根因**: prompt 里文档化了该操作，但执行器未注册对应分支。
**修复**: prompt 提到的每个 action 都必须在执行器实现（现由 `tests/test_prompt_consistency.py` 把关）。

---

### #012 | 信号冲突（两个 handler 接同一信号）

**症状**: "快速安排"点击没反应。
**根因**: `quick_adjust_requested` 同时被 `_on_quick_adjust`（填充 AI 输入框）与 `_on_quick_arrange`（直接发 AI）连接，产生竞争。
**修复**: 新建独立信号 `arrange_requested`，不再共享。

---

### #013 | 替换文本未精确匹配导致代码残留

**症状**: 多次替换后文件越来越大、含大量死代码。
**根因**: `old_string` 与文件实际文本不完全一致（空格/换行差异），工具静默跳过。
**修复**: `git checkout` 回滚干净版 → 精确行级替换 → 编译验证。

---

### #014 | 工具调用忘记 import（环境）

**症状**: `NameError: name 'os' is not defined`。
**根因**: 每次独立进程执行代码，不共享之前的 import。
**修复**: 每个代码块开头写全 import。

---

### #015 | Windows bash（MSYS）工具故障（环境）

**症状**: 文件/终端工具全报 exit code 126 "builtin: not found"。
**根因**: w64devkit 缺运行时 DLL。
**应对**: 文件操作改用 Python `open()`（见 `AGENTS.md` §4）。

---

### #016 | 语法检查缺失导致连锁错误

**症状**: 改 A 文件 → 提交 → B 文件报错（B 依赖 A 的改动）。
**修复**: 每次改完全量 `compileall`（见 `AGENTS.md` §3 步骤 6）。

---

### #017 | DDL 计数按精确时间而非按天

**症状**: 下午 3 点查看，3 天后 23:00 截止的作业不计入 DDL。
**根因**: `datetime.now() + timedelta(days=3)` 精确到时分秒。
**修复**: 改用 `date` 比较（`date.today() + timedelta(days=3)`）。

---

### #018 | 状态栏残留占位 widget

**症状**: "备考1科"与日期之间有空白。
**根因**: `_shopping_label`/`sep4` 不再更新数据，但永久 widget 仍挂在 `QStatusBar`。
**修复**: 从 `_setup_statusbar` 彻底移除不用的 widget。
> 关联现状：`main_window._shopping_label` 至今仍是"从未创建"的悬空引用（`CODE_STANDARDS Q-A4`）。

---

### #019 | `mousePressEvent` 右键也触发点击

**症状**: 右键点 DDL 线或状态栏标签也会跳转。
**根因**: `ClickLabel.mousePressEvent` 未区分鼠标按键。
**修复**: 加 `if ev.button() == Qt.MouseButton.LeftButton:` 判断。
