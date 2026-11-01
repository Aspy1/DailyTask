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
| 下拉箭头旋转错乱/闪烁/动画做在 QSS 与几何上 | #031 | UI |
| 圆角框周围有角点/原生方框/QSS 圆角台阶 | #032 | UI |
| ruff S110 漏检具名 except-pass/静默吞异常逃过门禁 | #033 | 工具 |
| 规范只有散文没有门禁/CODE_STANDARDS 现状栏失真/审计 | #034 | 流程 |
| PowerShell Select-String 通配符静默漏文件/误判死代码/删错模块 | #035 | 流程 |
| zh_HK 区域 CJK 数字/日期控件显示〇〢〣/QDateEdit 乱码 | #036 | 环境 |
| 周次计算散在 5 处/状态栏"第32/16周"/AI 取错学期 | #037 | 数据 |
| setCellWidget 覆盖同一格/撞课静默少一门课/冲突未提示 | #038 | UI |
| 测试套件偶发 access violation/嵌套事件循环/双重释放 | #039 | 测试 |
| 数据无学期归属/切学期课表不变/学期数据混在一个文件 | #040 | 数据 |
| 天气缓存并发写坏/启动路径解析崩溃/子进程编码 | #041 | 数据 |
| AI 命令不校验参数直接落盘/备份目录 import 时固化 | #042 | 数据 |
| AI 回复被输出上限截断 → 命令整段静默作废 | #043 | AI |
| 运行中的应用整份写回 settings.ini → 外部改配置被回滚 | #044 | 配置 |
| 小节/大节混淆 → 导入课表时段整体偏移 | #045 | AI |
| `update_*` 注入默认值 → 改掉没传的字段 | #046 | 数据 |
| 局部变量与导入的工厂同名 → 遮蔽 → 22 个测试崩 | #047 | 代码 |
| 搬函数后测试 patch 的模块级名字没跟着搬 → 模态框挂死 900s | #048 | 测试 |
| 按方法名锚定插入 → 插进了另一个类 | #049 | 工具 |
| 只跑单元测试就以为 git 同步好了 → 两个真 bug | #050 | 验证 |
| 编辑时 `newString` 写成 `oldString` 的前缀 → 静默删掉一个换行 | #051 | 工具 |
| 测试依赖真实时钟 → 吃饭提醒窗口内 CI 变红 | #052 | 测试 |
| actions 写入缺 `_version` → 第一次 UI 保存被误判冲突 | #053 | 数据 |
| 自绘 ToggleSwitch 没有 clicked → 启动即崩 | #054 | UI/信号 |
| 补跑逐分钟扫几天 → 启动卡死 | #055 | 性能 |
| 邮件在主线程同步 SMTP → UI 冻结 | #056 | 线程 |
| 日视图 hash 漏 done / prompt 借 data_changed | #057 | UI |
| QThread 自定义 finished 遮蔽基类 → 运行中被 deleteLater | #058 | 线程 |
| 只插入行内第一个控件 → 天气预报只剩日期 | #059 | UI |

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

---

### #031 | 2026-10-16 | 下拉箭头"旋转错乱 + 一直闪"，于是全项目禁掉了动画

**症状**: 给下拉菜单做展开动画时，小三角方向转不对，还持续闪烁；当时**不得已**把动画整条禁掉
（`AllTheFiles.md` R-008「禁止动画调试」），代价是界面完全没有过渡。

**根因**:
1. 箭头是 **QSS 画出来的**（`::down-arrow { image: ... }` 或字符），而 **QSS 没有 transform**，
   想旋转只能靠改图片或重绘 → 做不出正确插值。
2. 动画被加在**菜单几何**（高度/位置）上 → 每帧触发 layout + 重绘，箭头跟着抖 → 闪烁。
3. 两者叠加：一个动不了、一个动起来就闪。

**正确做法**（2026-10-16 恢复动画时采用）:
- 需要旋转就把箭头做成**固定尺寸控件里的 QPixmap**（`QTransform` 旋转后 `setPixmap`），
  或自绘 `paintEvent` + 自定义 `rotation` 属性用 `QPropertyAnimation` 插值；
  **只动这一个属性，绝不动控件尺寸**。
- 通用原则：动画只用 **opacity / 位移**，不动画化布局尺寸；时长 ≤180ms + `OutCubic`。

**教训**: 一次失败的技术尝试不该升级成"整个能力禁用"。当时正确的问题是
"QSS 不能 transform + 不能动几何"，而不是"动画不行"。

---

### #032 | 2026-10-16 | 圆角框周围有"角点"

**症状**: 输入框、按钮的圆角之外露出方形角点（历史遗留，`R-008` 里
"QComboBox 禁止 border-radius（产生角点）"就是同一现象）。

**根因（两个，可叠加）**:
1. **原生方框**：`QLineEdit` / `QComboBox` / `QAbstractSpinBox` 默认 `frame=True`，
   Windows 上这个原生框是**直角**的，QSS 的圆角盖不住它 → 四个角露出来。
2. **高 DPI 下的圆角台阶**：非整数缩放（125% / 150%）时 QSS 圆角按设备像素取整，
   圆弧被量化成台阶，看上去也像角点。

**修复**:
- 原因 1：`theme.install_rounded_frame_fixer()` 全局钩子，凡是样式表带 `border-radius`
  的输入类控件在 `Show` 时 `setFrame(False)`（不用改几十处调用点）
- 原因 2（若仍可见）：改用自绘 `QPainter` + `Antialiasing` 画圆角背景，
  QSS 里把背景设透明（`Q-H17`）

**教训**: QSS 的 `border-radius` 只是"画一个圆角矩形"，**不会裁剪控件本身**。
凡是"外观交给 QSS、但控件还有原生装饰"的组合，都要把原生装饰关掉。

---

### #033 | 2026-10-16 | ruff `S110` 漏检具名 `except-pass`

**症状**: `Q-I2` 声称"用 `ruff --select S110` 检查静默吞异常"，且 `ruff` 全绿；
但代码里仍有两处 `except (RuntimeError, AttributeError): pass` 无人发现。

**根因**: `S110`（try-except-pass）**只匹配裸 `except:` 与 `except Exception:`**，
对**具名元组** `except (A, B): pass` 不报。于是"规范指定的检查方法"天生存在盲区，
越是把异常收窄（Q-I1 鼓励的方向），越容易躲过 S110。

**验证**（最小复现）: 一个文件里写三种 `try/except/pass`，`ruff --select S110` 只报后两种。

**修复**: 门禁改用 **AST** 判定 `ExceptHandler.body == [Pass]`（`scripts/check_quality.py` 的 `SILENT` 项），
要求为 0；两处存量改用 `contextlib.suppress(...)`。

**教训**: "规范写了检查方法" ≠ "该方法真的能拦住"。凡是**用来把关的检查器**，
都要用**合成违规**验证它确实会报（`tests/test_quality_gates.py` 就干这个）。

---

### #034 | 2026-10-16 | 规范只有散文约束，`现状` 栏大面积失真

**症状**: `AGENTS.md` + `CODE_STANDARDS.md` 看着很完备（64 条 Q 规则），
但审计发现 **CI 实际只跑 3 项**（ruff / 令牌 / pytest），真正有门禁的规则只有约 **16 条（25%）**；
`现状` 栏里 6 条已修的 `✗` 没更新，3 条 `✔` 其实只是"某次手工测量过"（vulture/radon/覆盖率）。

**根因**: 把"规范"当成了文档工作。写了"如何检查"，但没把检查**落成脚本并接进 CI**，
于是规范随时间变成愿望清单；`现状` 栏靠人手同步，必然漂移。

**修复**（2026-10-16，见 `PLAN P6`）:
- `scripts/check_quality.py` 把可自动化的规则变成门禁（9 类检查）+ 接进 CI；
  能绝对化的必须为 0，有历史债的走 `scripts/quality_baseline.json`（**只防新增**）。
- 新增 `Q-F4`：每条规则要么有可运行检查，要么显式标注"人工 / 工具未装"。
- `tests/test_quality_gates.py` 守卫门禁本身（探测器有效性 + 仓库当前干净）。

**教训**: **约束只有变成门禁才成立**。文档是"给人读的意图"，门禁是"防回归的事实"；
两者缺一，规范都会烂。判断一个项目"规范可靠不可靠"，看 CI 里跑什么，而不是看文档写了什么。

---

### #035 | 2026-10-16 | 用 shell 通配符搜引用**静默漏文件**，据此删错模块

**症状**: 判断"`api_service.py` 是否死代码"时，用
`Select-String -Path src/**/*.py -Pattern "api_service"` 搜索，**输出为空** →
据此认定"整个模块无人引用"并 `git rm`。实际它被 `src/ui/widgets/api_test_dialog.py`
与 `src/ui/panels/settings_panel.py` 使用（"API 测试"弹窗靠它）。删除后 import 直接崩，
被并行工作的子代理发现。

**根因**: PowerShell 的 `-Path` 通配符与 bash 的 glob **语义不同**（`**` 不保证递归），
文件多了以后部分路径静默不参与匹配 —— 不报错、只给空结果，正好伪装成"无引用"。

**正确做法**:
- 搜引用**一律用 `grep` 工具**（ripgrep 语义明确），不要用 shell 通配符拼路径；
- 删模块/删函数前，用**两种以上**方式确认零引用（如同时搜模块名、类名、函数名）；
- 不确定时的安全顺序是"**先改后删**"：先把调用方迁走、跑测试，再删。

**教训**: "搜索返回空" 与 "确实不存在" 是两件事。**工具不会告诉你它漏了文件**，
所以关键判断不能只依赖一次搜索，尤其当后果是不可逆的删除。

---

### #036 | 2026-10-16 | 本机区域 `zh_HK` 让日期/数字控件显示 CJK 数字

**症状**: `QDateEdit` 显示 `〢〇〢〦-〡〇-〡〩`、`QSpinBox` 显示 `〢〇` —— 用户完全看不懂
（〇〡〢〣 是汉字/杭州码数字）。而且 **`widget.text()` 返回的就是这些字符**，不是渲染假象。

**根因**: 本机系统区域是 **`zh_HK`**，该区域在 CLDR 里用 **CJK 数字**；
Qt 的日期/数字控件按区域格式化 → 直接输出 CJK 数字。
与样式表、字体、DPI 都无关（不挂 QSS 也一样）。

**为什么拖到现在**: 项目里早有两处**各自打补丁**（`inventory_panel` / `schedule_view`
给单个控件 `setLocale(English, US)`），所以老控件没事；但**新增**日期/数字控件就会再中一次
（`habit_panel` 的 QSpinBox、`semester_dialog` 的 QDateEdit 都中过）。

**修复**: `ui/styles/theme.py: configure_locale()` 设默认区域为 `en_US`，
并由 **`init_theme()` 调用** —— 任何 UI 入口都会经过它，不会再漏
（`App.__init__` 也显式调一次）。守卫见 `tests/test_locale.py`。

**教训**: 依赖系统区域的东西（数字、日期、货币格式）**必须显式固定**，
不能"继承本机"。而且**逐个控件打补丁不是修复**——只要新增控件就会复发，
要修就修在所有人都必经的那一处。

---

### #037 | 2026-10-16 | 同一个"第几周"算了 5 遍，口径各不相同

**症状**: 学期过期后状态栏显示 **"第 32 / 16 周"**（第 32 周不存在）；
AI 提示词里的"第 N 周 / 单双周"在多个学期时算的是**别的学期**。

**根因**: "目标日期是第几周"这件事在 5 个地方各算一遍，且口径不同：

| 位置 | 旧口径 |
|---|---|
| `MainWindow._update_date`（状态栏） | 只钳下界 → 32/16 |
| `CoursePanel._week_number` | 钳上界（与状态栏不一致） |
| `AIService._get_current_week` | **忽略 `current_semester`**，取列表第一个学期 |
| `CourseModel.get_courses_for_date` | 超范围返回空；但 `date.fromisoformat` 遇坏数据**抛异常** |
| `send_digest._week_number_for` | 超范围返回 None（第三套） |

**修复**: 抽出纯函数模块 `src/models/semester.py`（无 Qt、无 IO），
提供 `semester_status()`（显示口径，已结束钳到总周数）与
`week_number_for()`（取课表口径，超范围返回 None）；
模型、状态栏、课程表面板、AI、邮件摘要**全部改为调用它**。
同时把"合法性检测"（14 个问题码）也放在这里，UI 只负责翻译。

**教训**: 同一事实的**多个计算点**必然漂移 —— 不是"谁写错了"，而是"没有单一真值"。
发现两处算同一件事时，第一件事是把它们合并，而不是把两边都改对。

---

### #038 | 2026-10-16 | `setCellWidget` 覆盖同一格 → 撞课静默少一门课

**症状**: 选修课多 / 有重修时，**同一时段有两门课**，但周视图上只显示**一门** ——
另一门被静默覆盖，用户既不知道撞课，也就想不到要请假。

**根因**: 渲染是"逐门课调用 `self.setCellWidget(row, col, chip)`"。
`QTableWidget` 一个格子只能有一个 cell widget，**后放的直接覆盖先放的**
（同理 `setSpan` 也会互相打架）。`_cell_courses[(row, col)] = course` 也只留最后一门，
右键菜单因此只能作用到其中一门。

**修复**:
- 抽纯规则 `models/course_rules.py`：`conflicts_by_cell(courses, week, period_count)`
  （`end` 是闭区间、要按周次/单双周/排除周过滤）；
- 周视图：冲突格改画**一个列出两门课的块**（`_ConflictChip`，按两门课合起来的节次跨度 `setSpan`），
  右键菜单逐门课提供"查看事项"；
- 日视图：该时段卡片加一行"⚠ 本时段有两门课，记得请假"。

**教训**: "一个容器只能放一个孩子"的 API（`setCellWidget` / 单值 dict 映射）在
**一对多**场景下会静默丢数据 —— 这种覆盖**不报错、不警告**。
凡是"按坐标/键存一份"的地方，都要先问一句"这里会不会有两个"。

---

### #039 | 2026-10-16 | 测试套件偶发 `access violation`（崩点每次不同）

**症状**: 整套 pytest 跑下来**随机崩进程**（`Windows fatal exception: access violation`），
崩点每次都不同（先是 `menu.exec()`，后是某个 `processEvents()`），隔离单跑那个文件却 0/12 崩。

**排查过程（值得复用）**:
1. 用"**多轮跑 + 统计崩溃率**"把偶发变成可观测量（实测约 25%）；
2. 用 `-v` 定位到崩溃**紧跟**在某几个测试之后 → 说明不是某条测试的问题，而是**累积状态**；
3. 做**对照实验**：给 teardown 加 `gc.collect()` → 崩溃率从 25% 变 **100%** ——
   这个"变坏"恰好指出真因在**销毁路径**。

**根因（两层）**:
- **真因**：我的 teardown fixture 对顶层控件 `deleteLater()` 后**强制处理** `DeferredDelete`
  → C++ 对象被删掉，但 **Python 仍持有包装器** → 之后 Python 侧销毁**再删一次** → 双重释放。
  崩溃只在"之后某处起了事件循环/GC"时暴露，所以崩点看起来毫无规律。
- **暴露点**：任何**嵌套事件循环**（`QMenu.exec()`、`processEvents()`）都会把这个问题翻出来。

**修复**:
1. teardown 只做 `sendPostedEvents(DeferredDelete)`（处理**被测代码自己** `deleteLater()` 的对象，
   它们的 Python 引用已清），**不**替 Python 删除仍被持有的对象、也**不** `close()` 顶层控件
   （`closeEvent` 有副作用且慢）；
2. 菜单那条测试改为**确定性断言**（`isinstance(menu, QMenu)` + `close()` 后仍存在），
   不再起事件循环 —— 崩溃因此失去暴露点，套件稳定。
3. 顺带把 `detect-secrets` 全仓扫描从单测挪到只测**比对逻辑**（8.9s → 0.01s）。

**验证**: 8 轮 × 2 种配置 **0 崩溃**（此前 25%～7/8）。

**教训**:
- **偶发崩溃要量化**（多轮跑 + 崩溃率），否则永远只能"再跑一次试试"；
- **不要替 Python 删除它仍持有的 C++ 对象**：PySide6 的销毁是"最后一个引用消失时删一次"，
  你提前删掉就是双重释放；
- **崩溃点 ≠ 根因**：崩在 `menu.exec()`，真因是累积状态 + 双重释放。

---

### #040 | 2026-10-16 | 数据没有学期归属 → 切学期课表永远不变

**症状**: 切换学期后课表**完全不变**。用户指出："现在切换学期不会修改应当显示的课程表。"

**根因**: `courses.json` 里 `courses[]` 是**一个全局列表**，每条课程只有
`day_of_week` / `weeks{start,end}` / `week_parity`，**没有任何学期字段**；
`tasks.json` / `exams.json` 同理。于是切学期只改了 `start_date`（"周次→日期"的映射），
24 门课在哪个学期都会出现 —— 这不是"忘了刷新"，而是**模型里根本没有"这份数据属于哪个学期"**。

**修复**（用户拍板）：
- **按学期分文件**：`data/semesters/<学期id>/{courses,tasks,exams}.json`；
  学期注册表独立为 `data/semesters.json`（`semesters[]` + `current_semester`）。
- **继承 vs 换新**（用户口径）：课程表 / 作业 / 考试**换新**；
  有什么 / 记账 / 习惯 / 日程计划**继承**。
- 路径解析收口到 `models/semester_paths.resolve()`（应用、`actions.py`、`send_digest.py`、
  `build_index.py`、测试助手共用一份）；
  切学期收口到 `DataManager.switch_semester()`（重定向三个模型 + 重载 + 通知界面）。
- `models/semester.py` 拆出 `SemesterRegistry`（注册表模型）；`CourseModel` 保留**同名转发**
  学期接口，所以界面/AI 的 40 处调用点一行没改。
- 旧布局一次性迁移（先写新文件 → 校验 → 再删旧文件），实测 24 课 / 2 作业 / 6 考试**零丢失**。

**教训**: "切换 X 不生效"要先问**"数据模型里有没有 X 这个维度"**，而不是去查刷新逻辑。
数据维度缺失时，任何界面层的补丁都只是把问题藏起来。

---

### #041 | 2026-10-16 | 天气缓存被并发写坏 → **应用启动即崩**

**症状**（全量验收第一遍就撞上）：`App` 构造到设置面板就抛
`json.decoder.JSONDecodeError: Extra data: line 82 column 2` → **应用完全起不来**。

**根因（两层，缺一不可）**：
1. **写方**：`weather_service.WeatherWorker._record_request` 用
   `stats_file.write_text(json.dumps(stats, indent=2))` —— **非原子、无锁**，
   而 now / 7d 两个 worker 会**并发写同一文件** → 内容互相截断，
   实测形态是"完整对象后面多出一个 `}`"；
2. **读方**：`settings_panel._update_weather_stats()` 在**启动路径**上
   `json.loads(stats_file.read_text())` —— **没有任何保护** → 一个缓存文件坏掉就让整个应用起不来。

**修复**：
- 新增 `services/weather_store.py`（唯一实现）：
  `read_json_safe()`（损坏时用 `raw_decode` **救回第一个完整对象**，永不抛）、
  `write_json_atomic()`（`.tmp` + `os.replace`）、
  `record_request()`（读-改-写**全程加锁**）；
- 天气统计/缓存与设置面板的读写**全部收口**到它；
- 用户那份坏文件已备份 + 救回重写（9 天日统计 / 3 个月统计全保住）。

**同一轮发现的同类问题**：`GitSync._GitWorker` 用 `subprocess.run(..., text=True)`
**没指定编码** → 默认走本机区域编码（gbk），而 git 输出可能带非 ASCII
（仓库里有中文文件名）→ `UnicodeDecodeError` 让整次同步失败。已改
`encoding="utf-8", errors="replace"`。

**教训**:
- **派生缓存的读写同样要原子 + 加锁**："反正是缓存"不是不做保护的理由 ——
  它坏掉会连累读它的**启动路径**；
- **启动路径上的外部文件解析必须容错**：UI 不能因为一个缓存文件就起不来；
- 子进程读输出**一律显式指定编码**：`text=True` 不等于 UTF-8（本机是 gbk）。

---

### #042 | 2026-10-16 | AI 命令不校验参数 / 备份目录在 import 时固化

**症状 A**：`scripts/actions.py` 的进程内执行器只做 `--key value` 解析就写文件 ——
`--day 9`、`--slots 3-99`、`--due 2026-02-30` 全部照写不误；拼错的 `--titel` 还会被
**静默忽略**（"看起来执行成功，其实参数没生效"）。AI 传错参数是**必然**，不是偶然。

**症状 B**（本轮自测抓到）：备份目录写成模块级
`BACKUP_DIR = DATA / "backup" / "actions"` —— `DATA` 在测试里被替换（sandbox fixture）
后，备份仍写到**旧位置**，于是**测试的备份落进了用户真实 `data/`**。

**修复**：
- 校验与执行**分离**：`_validate_args()`（规格表 `SPECS`）在 handler **之前**跑，
  失败只回 `ERROR ...`、一个字节都不写；未知参数直接拒绝；
- 写入改为「结构守卫 → 写前备份 → `.tmp` → 回读自检 → `os.replace`」；
  `restore --name X --yes` 提供手动回滚；`load()` 遇坏文件**明说**，
  而不是当成空数据继续写（那等于清空用户数据）；
- 备份目录改成 `_backup_dir()` **每次现算**；sandbox fixture 改为同时 patch
  `actions_core.DATA`（真正决定写入位置的那个）。

**教训**：
- 入口统一校验 > 每条命令各自校验 —— 后者只要有一条漏了就是数据事故；
- 凡是**从 `DATA` 派生的路径**都别在 import 时固化；可替换的配置必须现算。

---

### #043 | 2026-10-16 | AI 回复被输出上限截断 → 命令**整段静默作废**

**症状**（用户报"让 AI 导入本学期课程表，迟迟未回复，命令行也没见 200 OK"）：
- 日志最后一行只有 `POST .../chat/completions "HTTP/1.1 200 OK"`，之后**再无输出**；
- py-spy 抓栈：主线程 idle、**没有 AI 工作线程** → 应用没卡死，请求早就结束了；
- 但数据**一条没变**（无备份、课表仍 0 门）→ 命令一条都没执行。

**根因**：模型对"导入 24 门课"这类请求会输出很长的 ```sh 块（实测 40–58s、
约 1700 completion tokens），一旦撞上输出上限就被**截断** —— 而
`InstructionParser.parse` 的正则要求**必须有收尾 ```**，于是整段丢弃：
既没有命令执行，也没有任何提示。用户看到的就是"AI 没反应"。

**修复**：
- `parse` 容忍**未收尾**的块：把已经写完的完整命令行交出去执行
  （每行都过 `actions.py` 严格校验，非法行会被拒绝 → 安全）；
- `AIWorker` 检测"围栏数量为奇数 = 疑似截断"→ 让模型**分批续跑**（每轮 ≤8 条），
  并在提示词里写死这条规则；
- 补**生命周期日志**：`AI turn N: 耗时 | 字符数 | 疑似截断 | 命令数`
  —— 用户就是盯着日志等的（"怎么没有 200 OK"）；
- 给模型客户端设 **120s 超时**（SDK 默认 10 分钟，卡住时用户会干等且无提示）；
- 空回复不再静默：界面给明确提示。

**教训**：
- **解析失败必须可见**：`parse` 返回空列表时不能默默结束，要记日志/给用户提示；
- 任何"等外部结果"的路径都要有**超时 + 进度日志**，否则一次慢响应就等于"应用坏了"；
- 大任务要**分批**：一次输出越长越容易撞上限，分批还能顺带给出进度感。

**同族问题（同一晚用户再次报障：连续返回空内容）**：推理型模型会先花几百到上千
token 思考，`max_tokens=4096` 时会被**推理吃光** → `finish_reason=length` 而
`content` 为空。此时围栏数为 0 → **不算"截断"** → 上一轮加的分批逻辑**从不触发**，
界面只剩空白。修复：空回复也走"要求继续"分支（提示语明确要求"直接输出命令、
每轮 ≤8 条"）；`max_tokens` 改读设置且默认提到 **8192**；provider 每轮打印
`finish_reason` + 推理 token（一眼能看出是预算问题）。

**第三轮（用户贴出日志：`补全 8192（推理 8192）` × 5 轮）**：模型**整份预算都给了推理**
（content 恒为空），而我那版"空回复就重试"让它**空转 5 轮 ≈ 3.5 分钟** —— 重试逻辑
把问题放大了。修复：
- 空回复**只重试一次**（连续两次都空就是模型/网关陷在思考里，继续刷只是让用户白等）；
- **从推理里抢救**：content 为空但 `reasoning_content` 有内容时，直接把推理文本当回复
  交出去（命令仍由 `actions.py` 严格校验）—— 用户至少不会看到空白；
- OpenCode 端点加 `reasoning_effort="none"`：实测推理 token **归零**、输出更长、
  24 门课导入从 44–58s 降到 **11s**（端点若不认这个参数会自动去掉重试）；
- 界面的空回复提示改成可操作的（建议换模型）。

**教训（补充）**：重试必须**有上限且分类**：对"模型陷在思考里"这种确定性失败，
重试 5 次和重试 1 次结果一样，只是把用户的等待乘以 5。

---

### #044 | 2026-10-16 | 运行中的应用把 `settings.ini` **整份写回** → 外部改配置被静默回滚

**症状**：脚本把 `AI.model` 改成 `deepseek-v4.1-flash`、`max_tokens` 改成 8192，
脚本**回读确认成功**；几分钟后再读又变回旧值，而 `settings.ini` 的修改时间正好是"现在"。

**根因**：`ReminderService._check()` 每 60s 执行
`settings.set("Email","last_reminder_check",…); settings.save()`，而
`SettingsManager.save()` 用 configparser **写整份文件** —— 写的是**内存里那份**
（应用启动时载入的）。于是外部对文件的修改会被周期性**静默回滚**。

**规避**：改配置只能在**应用内**（设置面板）或**应用关闭时**做；外部脚本改完必须
提醒用户重启，且**别用"外部改配置"来验证功能**（会得到假象 —— 本次探针就读回了旧模型）。

**教训**：长期运行的进程若持有配置的内存副本并周期性整份写回，那么"改文件"就不是
生效路径；要么提供 UI/接口，要么先停进程。

---

### #045 | 2026-10-17 | 小节 vs 大节混淆 → 导入课表**时段整体偏移**

**症状**：用户让 AI 导入整学期课表，导入后"从 10:25 开始的课整体向下移了一节"
（第三节 10:25 显示成 13:30、第五节 13:30 显示成 18:30）。

**根因**：用户课表按**小节**排（一天 8 小节），本应用一天只有 **6 个大节**
（大节 1 = 08:30-10:05 = 小节 1+2）。AI 把"第几节"**1:1** 当成 `--slots`：

| 课表 | 正确 slots | AI 写的 |
|---|---|---|
| 第一节 | 1 | 1 ✓（碰巧对） |
| 第三节 | **2** | 3 ✗ |
| 第五节 | **3** | 5 ✗ |
| 第七节 | 4 | 4 ✓（碰巧对） |

换算规则：`大节 = ceil(小节 / 2)`；课表同时给了时间时用**时间**判断。

**修复**：提示词加"小节 → 大节"对照表 + 换算规则 + "同时给时间就用时间判断"；
用新增的 `update_course --slots` 修正已导入的 15 门课。

**教训**：外部数据（课表/Excel）的"节次"口径**必须**在提示词里写清对照关系 ——
模型只能按你给的口径猜；没写就必然猜错，而且错得**系统性**（整列偏移）。

---

### #046 | 2026-10-17 | `update_*` 被注入默认值 → **改掉没传的字段**

**症状**：`update_item --id i_001 --location "柜子"` 会把该物品的**数量重置成 1**；
新加的 `update_course --slots` 同样会把 `week_parity` 重置成 `all`。

**根因**：`_build_action_namespace()` 会给**所有**命令补 argparse 默认值
（`quantity: 1`、`parity: 'all'`…），而 `update_*` 的语义是"**只改显式传入的字段**" →
handler 里 `if args.quantity is not None` 之类判断被默认值骗过。

**修复**：`update_course` / `update_item` **不注入默认值**；相关 handler 一律改
`getattr(args, "x", None)`（旧实现直接 `args.quantity` → 属性不存在时
`AttributeError`，日志里 `ERROR 'Namespace' object has no attribute 'unit'` 同源）。

**教训**：默认值注入与"部分更新"语义天然冲突 —— 二者同时存在时，必须让**更新类命令
不参与默认值注入**，否则每次"只改一个字段"都会静默改掉别的字段。

---

### #047 | 2026-10-17 | 局部变量与导入的工厂同名 → **遮蔽** → 22 个测试崩

**症状**：把日程视图的时段卡改成 `card("panel", …)` 后，`python -m pytest` 里
**22 个测试失败**，报 `UnboundLocalError` / ruff 报
`F823 Local variable 'card' referenced before assignment`。

**根因**：那一行我写成了

```python
card = card("panel", pad="spacing_none")   # ← 左边把导入的 card() 遮蔽了
```

Python 看到函数体里有 `card = …` 就把 `card` 判为**局部名**，于是右边那次调用
读的是"尚未赋值的局部变量" → 崩。**同一个名字既是工厂又是容器**是祸根。

**修复**：局部改名 `slot_card`（工厂名保持 `card` 不动，调用点更自然）。

**教训**：
- 导入的**工厂函数**名（`card()`）与"装它的变量"别同名 —— 尤其在同一个函数里；
- 这类遮蔽**静态检查就能抓**（ruff `F823`）→ 改完先跑 `ruff`，别等到跑测试；
- 反过来看也成立：如果让 22 个测试挂了才发现，说明**验证顺序**应该固定为
  `compileall → ruff → pytest`（本仓库 §3 步骤 6 就是这个顺序）。

---

### #048 | 2026-10-17 | 搬函数时，被 patch 的**模块级名字**没跟着搬 → 模态框挂死

**症状**：把"快速安排"的撤销逻辑从 `schedule_view.py` 搬到 `schedule_actions.py` 之后，
`pytest` 在 `test_undo_refuses_when_plans_changed_since_arrange` 上**挂死**（900s 超时），
**没有任何报错**。

**根因**：`_undo_arrange` 以前在 `schedule_view` 里调 `QMessageBox.warning(...)`，测试用
`monkeypatch.setattr(sv_module, "QMessageBox", _StubBox)` 把它换掉。逻辑搬走后，调用点
变成了 `schedule_actions` 里的 `QMessageBox` —— 而 patch 还打在旧模块上 → **真的弹出了
模态框**，离屏测试里没人点它，于是永久阻塞。

**修复**：patch 目标改成 `schedule_actions`，并在测试里注释说明为什么是这个模块。

**教训**：
- 移动函数时，凡是"被测试替换的**模块级名字**"（Qt 类、常量、logger）都要一起搬 patch 目标；
- **模态框 + 离屏测试 = 挂死**（不是失败）→ 测试里凡是会弹 Qt 对话框的路径必须显式 patch；
- 更稳的写法：让被测逻辑**返回状态码**，把弹窗留给薄薄一层 UI 包装
  （本次就是这么改的 —— `undo_arrange()` 返回 `bool`，视图只管按钮与提示）。

---

### #049 | 2026-10-17 | 按方法名锚定插入，结果插进了**另一个类**

**症状**：给 `MainWindow` 加一个槽函数，插入点选 `def closeEvent(...)` —— 编辑报成功，
但启动时 `AttributeError: 'MainWindow' object has no attribute '_on_save_conflict'`，
8 个测试连带失败。

**根因**：`main_window.py` 里的 `closeEvent` 属于 **`WeatherDetailDialog`**（634 行起），
不是 `MainWindow`（40 行起）。**同名方法在别的类里也有一份**，锚定时没看归属。

**修复**：改锚 `MainWindow._on_data_changed`（同文件里唯一）。

**教训**：
- 按名字锚定插入位置前，先 `grep -n "^class \|def <名字>"` 确认**它在哪个类里**；
- 一个文件多个类时，`closeEvent` / `__init__` / `paintEvent` 这类方法名**不唯一是常态**；
- 症状是"属性不存在"而不是语法错 → 说明插到别处了：先看 grep 结果，别急着改逻辑。

---

### #050 | 2026-10-17 | git 同步：单元测试全绿，真环境跑出两个 bug

**背景**：改完 Git 同步（审查 #4）后，10 条单元测试全过 ✓。但用一个**临时仓库 + 本地
裸仓库当远端**真跑三种场景，立刻暴露两个单元测试测不出的问题：

1. `git add -A -- <清单路径>` 对**不存在的路径**直接
   `fatal: pathspec 'data/daily_logs.json' did not match any files` → 命令链中断 →
   **整次同步失败**。新机器 / 新克隆上必然踩（本地那些文件还没生成）。
   → 改成 `sync_paths()` **只列存在的**；一个都没有时退回数据目录本身。
2. `git push` 的 "Everything up-to-date" 走的是 **stderr**（推送进度也走 stderr）→
   只看 `stdout` 会把"本来就没待推送"**误报成"推送了提交"**。
   → 改成合并 `stdout + stderr` 判断。

**教训**：
- 涉及**外部进程**（git / 编译器 / 打包器）时，"函数返回什么"可以单测，
  但"那个进程实际怎么表现"（退出码、输出走 stdout 还是 stderr、路径不存在时的行为）
  **必须真跑一遍** —— 这两条都是纯函数测不到的；
- 代价极低：临时目录 + `git init --bare` 当远端，几十行就能把三种状态跑全；
- 顺带：真跑一遍也验证了"审查报的 bug 确实修好了"（未推送提交数 1 → 0），
  而不是"测试过了所以大概好了"。

---

### #051 | 2026-10-17 | 编辑时 `newString` 写成 `oldString` 的前缀 → 静默删掉一个换行

**症状**：想"在某个 `def` 之前插入一个新方法"，编辑报**成功**，但结果是把下一行
（docstring）接到了 `def` 那一行的末尾 → 语法错误。本会话犯了**三次**（`base.py`、
`data_manager.py`、`main_workspace.py` 各一次 —— 前两次记进本条之后**又犯了一次**，
所以这条规则要当硬约束执行）。

**根因**：`oldString` 写成了 `def foo(self) -> None:\n`，而 `newString` 写成
`def foo(self) -> None:`（少了结尾换行）—— 那次编辑的唯一效果就是**删掉一个换行**。

**教训**：
- `newString` 绝不要写成 `oldString` 的前缀；要**插入**内容就把**下一行也包进
  `oldString`**，再在 `newString` 里完整写回来；
- 这类错误**编译就能发现**（`compileall` 报语法错）→ "改完先 compile"不是形式主义；
- 想插新函数时，最稳的锚是"下一个函数的完整签名 + 它的第一行"。

---

### #053 | 2026-11-01 | actions 写入缺 `_version` → 第一次 UI 保存被误判成"外部改动"

**症状**：走查里 AI/CLI 刚写完 `tasks/habits/daily_logs/inventory`，用户在界面做第一次修改时
`save()` 返回 False，改动只落到 `backup/save_conflict/`，磁盘不变。

**根因**：`actions_core.save()` **不写 `_version`**；`BaseJsonModel.load()` 读盘后在**内存**里
补 `_version=1`，然后才计算磁盘指纹 → 内存指纹 ≠ 磁盘指纹，`save()` 永远判"冲突"。

**修复**：
- `load()` 在补默认值**之前**算磁盘指纹（指纹 = 磁盘原文）；
- `actions_core.save()` 按模型 `DEFAULT_*["_version"]` 写版本（唯一真值）；
- `flush_on_exit()` 对旧文件缺失的 `_version` 做同口径归一。

**涉及**：`models/base.py`、`scripts/actions_core.py`、`services/data_manager.py`
**教训**：**指纹的基准必须与磁盘字节一致**。任何"读入后规范化再算指纹"的写法，
都会把"规范化"误判成"外部改动"。

---

### #054 | 2026-11-01 | 自绘 `ToggleSwitch` 没有 `clicked` → 真实应用启动即崩

**症状**：设置页有插件时启动 `main.py` 抛
`AttributeError: 'ToggleSwitch' object has no attribute 'clicked'`；
离屏走查的沙箱没有插件，所以没暴露。

**根因**：上一轮按 `QCheckBox` 的惯例把 `toggled` 改成 `clicked`，但 `ToggleSwitch` 是自绘
`QWidget`，只暴露 `toggled`，且 `setChecked()` **不发**信号（正是为了防回环）。

**修复**：设置页插件开关改回 `toggled`；注释写明该控件 `setChecked()` 是静默的。
`QCheckBox`（插件面板）仍用 `clicked`。

**教训**：**按控件族遵守信号约定**。用 `QCheckBox` 的规则套自绘控件前，先看它暴露了哪些信号；
"沙箱没这个数据/插件"的走查不能替代真实启动。

---

### #055 | 2026-11-01 | 提醒补跑逐分钟扫几天 → 启动卡死

**症状**：应用关了几天再打开，`ReminderService.start()` 逐分钟遍历
`last_check → now`（最多 N 天 × 习惯数），主线程迟迟不进事件循环。

**修复**：补跑窗口上限 **12 小时**（`CATCHUP_MAX_MINUTES`）；超出直接跳过并记日志。
同时 `last_reminder_check` 改为每 5 分钟落一次盘，不再每分钟写 `settings.ini`。

**教训**：凡是"从上次时间补到现在"的循环，都必须有**窗口上限**；否则用户的
"几天没开"会变成启动耗时。

---

### #056 | 2026-11-01 | 邮件在主线程同步 SMTP → UI 冻结最长 10s

**症状**：提醒 tick 或设置页「发送测试邮件」时界面卡住；SMTP 超时 10s 就等于 10s 未响应。

**修复**：新增 `services/email_sender.py`（后台串行队列）：提醒服务只**入队**，
退出时 `shutdown()` 最多等 2s；设置页用 `EmailTestWorker(QThread)`，结果信号回主线程。

**教训**：**网络/外部进程一律不放在 UI 线程**，包括"只是发一封邮件"。

---

### #057 | 2026-11-01 | 日视图 hash 漏 `done` + prompt 借 `data_changed`

**症状**：
1. 习惯打卡 / 计划完成后，日视图卡片仍显示 ○ / 未划线（内容指纹没变，hash 增量刷新跳过重建）；
2. 课程右键「布置了作业」没有填充 AI 输入框，反而触发了全界面刷新。

**根因**：
1. `_content_hash()` 没把 `done` 纳入指纹；
2. `_handle_course_action("fill")` 把 prompt 塞进 `data_changed.emit("fill_prompt:…")`，
   没有任何消费者。

**修复**：`done` 进入指纹；新增 `ScheduleView.fill_ai_prompt` 信号 →
`MainWorkspace` → `MainWindow` 展开 AI 面板并填入。

**教训**：**hash 增量刷新要把"显示相关的所有字段"纳入指纹**；
新增 UI 事件要走**正式信号**，不要借用 `data_changed` 这种"数据域"通道。

---

### #052 | 2026-10-31 | 测试依赖**真实时钟**：吃饭提醒窗口内 CI 变红

**症状**：本地全绿、CI `check (3.12)` 红，只有一条：
`tests/test_hints.py::test_today_hints_reads_the_cache`
`assert [Hint(key='dinner@...', blink=True)] == []`。
本地再跑一遍又绿 —— 典型的"跟时间有关"。

**根因**：A2 给 `today_hints()` 加了吃饭提示（11:40 / 16:40 起 90 分钟内出现）。
那条测试原来断言"空目录 → 空列表"，跑在吃饭窗口里就必然多出一条 ✗。
`now` 参数本来就是为这种测试留的，只是老测试没传。

**修复**：测试传固定时刻 `today_hints(dir, now=MORNING)`（09:00，不在任何吃饭窗口）。
同类：`test_outing_hints` 只断言"某条在/不在"，多一条不影响 → 不必改。

**教训**：
- **凡是"按当前时刻出结果"的函数，测试一律传 `now`**；不传就等于让跑测试的时刻决定成败；
- 本地绿 ≠ CI 绿 —— 与时间相关的断言先问一句"如果现在是 11:45 会怎样"；
- 加时间窗口类功能时，`grep -rn "today_hints\|now=" tests/` 把老测试一并改掉。

---

### #058 | 2026-11-01 | QThread 自定义 `finished` 遮蔽基类信号 → 线程运行中被销毁

**症状**：点天气「刷新」后退出/刷新，控制台出现
`QThread: Destroyed while thread '' is still running`，偶发崩溃。

**根因**：`WeatherWorker` / `_ApiWorker` / `_GitWorker` 都继承 `QThread` 并声明了
`finished = Signal(...)`。同名信号**遮蔽**了 `QThread.finished`，于是
`worker.finished.connect(worker.deleteLater)` 连到的是 `run()` 内刚发出的结果信号——
此时线程还没真正结束，QThread 对象被删 → Qt 报 "Destroyed while running"。

**修复**：结果信号改名 `result` / `failed` / `done`；回收统一连基类 `QThread.finished`；
`WeatherService.shutdown()` 先停定时器再 `wait()` 线程；`MainWindow.shutdown()` 在退出时调用。
结构测试：`tests/test_weather_dialog.py::test_qthread_subclasses_do_not_shadow_finished`。

**教训**：**子类不要复用 Qt 基类的信号名**（`finished` / `error` / `clicked` 等）。
QThread 的清理只能等 `QThread.finished`，结果信号发出 ≠ 线程结束。

---

### #059 | 2026-11-01 | 天气「未来3天」只显示日期

**症状**：打开天气详情，未来三天只有日期列，天气文字、温度、降雨都不显示。

**根因**：`_build_forecast_rows()` 每行建了 `QHBoxLayout`，但只把
`row_layout.itemAt(0).widget()`（日期 QLabel）插进主布局；其余三个标签没有父控件/布局，
永远不会显示。

**修复**：每行包一个 `QWidget` 容器，把**整行**插进主布局；补测试断言日期/天气/温度
都非空且 `isVisible()`。

**教训**：**布局里"加了一个控件的子控件"不等于加了整行**；容器要么 `insertLayout`，
要么先包 QWidget。截图审查必须覆盖弹窗内容，不能只看主面板。
