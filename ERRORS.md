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
| parse_date 截断/normalize_time/具体时间丢失/一律 23:00 | #020 | 数据 |
| 下周X/相对日期晚一周/days_ahead | #021 | AI |
| 考试提醒/exams.json 读不到/只扫 tasks | #022 | 数据 |
| 重复提醒/14-7-3 阈值/一次发 3 封 | #023 | 数据 |
| DEFAULT_ 浅拷贝/实例间共享 list/预期外条目 | #024 | 数据 |
| external 广播无域名/子串匹配/面板不就地刷新 | #025 | 数据 |
| save_all 漏模型/退出丢数据 | #026 | 数据 |
| `args.quantity or 1`/0 被当缺省值 | #027 | AI |
| 检查器误报/#020 被当颜色/误报豁免 | #028 | 工具 |
| 菜单不可达/emit more/主题切换没入口/死代码入口 | #029 | UI |
| 右键菜单位置偏/自研菜单/exec 不返回/last_action 失效 | #030 | UI |

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

---

### #020 | 2026-10-16 | 作业的"具体时间"被静默丢弃，一律变 23:00

**症状**: `--due 2026-10-20T14:30`、`下午3点`、`晚上8点半` 入库全变 `2026-10-20T23:00:00`；
连带 DDL 倒计时、6 小时邮件、日程 DDL 线全部错位。

**根因**: `cmd_add_task` 里 `due = parse_date(raw)` 先跑，而 `parse_date` 只保留 `raw[:10]`
（把时间截掉了）；随后的 `normalize_time(due)` 早已拿不到时间，只能补 23:00。
`normalize_time` / `_shift_hour` 的中文时段分支实际上成了**死代码**。

**修复**: 新增 `_normalize_due(raw)`——**先取时间（ISO 或中文时段），再归一化日期**，
只给日期时才补 23:00；无时间表达的旧路径保持不变。

**涉及**: `scripts/actions.py`

**教训**: **归一化/校验函数有先后顺序**。当前置函数会丢信息时，后置函数的分支就会变成死代码——
而且不报错。凡"解析→再加工"的链条，都要用真实样例断言最终落盘值。

---

### #021 | 2026-10-16 | "下周X" 比正确日期晚一周

**症状**: 今天周五问"下周一"→ 算出 10 天后（下下周一）；"下周五"→ 14 天后。
只有"下周六/日"是对的。

**根因**: `7 - today.weekday() + wd` 本身已经落在**下一个自然周**，后面又写了一句
`if days_ahead <= 7: days_ahead += 7` → 周一到周五全被多推一周。

**修复**: 删掉那句自增；补上 `range(7)` 参数化测试，逐星期核对。
**涉及**: `scripts/actions.py`

**教训**: 日期偏移公式必须**对 7 个星期几都跑一遍**才发现"部分正确"；只测一个例子会漏。

---

### #022 | 2026-10-16 | 考试提醒/日报读错数据源，考试模块等于没提醒

**症状**: 用 AI 建的考试（写进 `exams.json`）从不会触发 14/7/3 天提醒，也不进每日摘要。

**根因**: `ReminderService._check_exam_email` 与 `send_digest._digest_exams` 都只遍历
`tasks.pending`，并且靠"标题里含『考试』"来猜是不是考试——那是考试模块出现**之前**的做法。

**修复**: 两处都改为**合并**：`exams.json`（权威）∪ 旧数据里标题/标签含「考试」的任务，
按 `(名称, 日期)` 去重（同一场考试两种形态只提醒一次）。

**涉及**: `src/services/reminder_service.py`、`scripts/send_digest.py`

**教训**: 新增数据模块时，要 grep 一遍**谁在按老路子消费同类数据**，否则新模块会"沉默地不生效"。

---

### #023 | 2026-10-16 | 同一场考试一次发 3 封邮件（阈值轰炸）

**症状**: 剩 3 天考试 → `14/7/3` 三个阈值同时命中，连发 3 封；托盘同刷 3 条。

**根因**: `for d in EXAM_DAYS: if days_left <= d and d not in emailed:` —— 三个阈值各自判定，
`<=` 让它们在同一时刻同时成立。

**修复**: 每次检查**只发一封**，把本次命中的阈值一并登记（`emailed.update(hit)`）；
到 7 天、3 天时各自再发一次（测试覆盖了"阈值随时间推进"）。

**涉及**: `src/services/reminder_service.py`

**教训**: 多级阈值提醒要明确"每级各发一次"还是"只发最近一级"，并写成测试；
`<=` 判定多条阈值必然叠加。

---

### #024 | 2026-10-16 | `DEFAULT_*` 浅拷贝导致实例之间共享数据

**症状**: 新建的模型实例"凭空多出"另一个实例（甚至别的数据目录）刚加过的条目。

**根因**: `BaseJsonModel._ensure_file` 用 `dict(self._default_data)`（**浅**拷贝），
于是 `self._data["items"]` 就是模块级常量 `DEFAULT_INVENTORY["items"]` 那个**同一个 list**；
`add_item` append 之后，常量被永久污染，后续所有实例继承之。

**修复**: 改 `copy.deepcopy(self._default_data)`；测试断言"模块级常量未被污染 + 新实例为空"。

**涉及**: `src/models/base.py`

**教训**: 默认值里的嵌套容器必须深拷贝。发现方式：写测试时第二个用例莫名多出第一条用例的数据。

---

### #025 | 2026-10-16 | `external` 广播不带域名 → 面板不就地刷新

**症状**: TG bot 写入 `tasks.json`（或习惯/考试/记账/库存）后，界面不更新，切页才更新——
README 宣称的"外部修改即时可见"不成立。

**根因**: `MainWorkspace._on_data_changed` 按域名字符串匹配（`"task" in action`），
而外部改动广播的是 `"external"`，谁都不匹配；`ReminderService` 同理，DDL 计数也不重算。

**修复**: `action in ("external", "internal")` 视为"不知道改了哪个域" → 全刷；
其余仍按域名增量刷新（并有测试守住"单域广播不许连带刷其它面板"）。

**涉及**: `src/ui/components/main_workspace.py`、`src/services/reminder_service.py`

**教训**: 广播协议里出现的**特殊值**（`external` / `ai_action` / `internal`）必须逐个显式处理，
不能假设消费方都按"域名子串"匹配。

---

### #026 | 2026-10-16 | `save_all()` 漏了 2 个模型

**症状**: 退出/重启前若考试或库存只在内存里改过，改动会丢。

**根因**: `DataManager.save_all()` 只保存 5 个模型（courses/tasks/habits/expenses/daily_logs），
漏了后加的 `exams` 与 `inventory`。

**修复**: 补全 7 个；测试直接从磁盘回落断言 7 个模型都写到了。
**涉及**: `src/services/data_manager.py`

**教训**: "全部"类的函数要对着**模型清单**写测试，否则新增模型时静默漏掉。

---

### #027 | 2026-10-16 | `args.quantity or 1` 把「0 件（已用完）」当成缺省值

**症状**: `add_item --quantity 0` 记为 1 件、状态"充足"。

**根因**: `or` 把合法的 `0` 当假值；且 argparse `default=1` 让"没传"与"传 0"无法区分。

**修复**: CLI 默认值改 `None`，`qty = 1 if args.quantity is None else args.quantity`。
**涉及**: `scripts/actions.py`（同 `ERRORS #005` 的取值陷阱）

**教训**: 只要有"0/False 是合法值"的参数，就不能用 `or` 兜底，也不能用同类型默认值表达"未传"。

---

### #028 | 2026-10-16 | 检查器误报：把 `ERRORS #020` 当成颜色字面量

**症状**: 代码注释里写 `（ERRORS #020）` 会让 UI 令牌检查器报 `[COLOR] #020`。

**根因**: `RE_HEX = #[0-9a-fA-F]{3,8}` 无法区分"3 位十六进制颜色"与"问题编号"。

**修复**: 加豁免规则 `(ERRORS|ERR|条目|问题|issue)\s*#\d+`，并补测试（真颜色仍要报）。
**涉及**: `scripts/check_ui_tokens.py`

**教训**: 检查器一旦误报，团队就会开始绕过它（加 ignore 注释 / 干脆不写引用）。
误报要按"规则误报"修，而不是改文案迁就。

---

### #029 | 2026-10-16 | 菜单不可达：`emit("more")` 从来没人发

**症状**: 深浅色主题切换在界面上找不到入口。

**根因**: `MainWindow._on_sidebar_nav` 里 `if key == "more": self._show_more_menu()`，
但侧边栏从来没有 `more` 这个导航项 —— 处理分支与唯一入口都成了死代码
（与 `#001` 的"声明但未 emit"同一类）。

**修复**: 侧边栏底部加「更多…」导航项；测试断言 `about`/`more` 被特判且不当作面板 key。

**涉及**: `src/ui/components/sidebar.py`

**教训**: 判断分支的另一端（谁触发）也要有守卫。新增导航键/信号时，两边一起加测试。

---

### #030 | 2026-10-16 | 自研右键菜单：位置会偏 + `exec()` 永不返回（5 个菜单点了没反应）

**症状**: 右键菜单有时不贴着鼠标出现；课程表 / 日程里 DDL 线 / 日程里日常卡片 三处右键
"点了没反应"；反复右键后行为越来越怪。

**根因（两层）**:
1. **定位**：`ContextMenu.exec()` 用 `self.screen()`（取的是菜单**自己**所在屏，不是光标所在屏）
   并把全局坐标与屏幕**宽/高**比较（而不是屏幕矩形的右/下边界），且只做右下翻转。
   单屏 + 100% 缩放时"碰巧"正确；多屏 / 非零原点 / 缩放 ≠100% 就会偏。
2. **更严重**：`exec()` 用 `destroyed` 信号结束内嵌事件循环，而关闭菜单走的是 `close()`
   （只隐藏、不销毁控件）→ **`exec()` 永不返回**（实测：`WA_DeleteOnClose=False`，
   只有 `deleteLater()` 才返回）。于是读 `menu.last_action` 的菜单（课程表、日程 DDL、
   日程日常、任务面板筛选）**后续处理代码永不执行**；而回调风格的菜单看起来正常，
   掩盖了 bug；每次打开还遗留一个内嵌事件循环。

**修复**: 换回 `QMenu`（`NoDropShadowWindowHint` 实测能清掉 Windows 的 `CS_DROPSHADOW`，
所以"去掉原生阴影"这个当初手搓的理由不再成立），并抽出模板集合 `src/ui/widgets/menu.py`：
`new_menu` + 三种锚点（`show_at_cursor` / `show_at` / `show_below`）+ `add_action`；
菜单结果改用 `exec()` 的返回值或回调。删 `context_menu.py`。

**教训**: **"我造一个更可控的控件"之前先确认 Qt 原生真的做不到**（当年为了去阴影手搓，
结果丢掉了翻转/多屏/键盘导航，还引入了永不返回的循环）。
另外：**用信号结束内嵌事件循环时，必须确认那条路径真的会发出该信号**。

