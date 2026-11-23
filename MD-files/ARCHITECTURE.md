# ARCHITECTURE.md — 项目运作原理

> **定位**：本项目"如何运作"的权威说明——分层、启动顺序、数据流、信号链、并发模型、不变量、数据 schema。
> 只写**代码表达不了的东西**（跨文件时序、不变量、为什么、外部契约）；函数签名/参数/字段结构不在此重复。
> 相关文档：`AGENTS.md`（流程/环境）· `CODE_STANDARDS.md`（规范）· `PLAN.md`（计划/体检）· `ERRORS.md`（坑）。
>
> 最后更新：2026-11-20

---

## 1. 定位与技术栈

AI 驱动的 PySide6 桌面日程管理应用（学生向）。单进程、无服务端；数据为本地 JSON。

| 层 | 技术 |
|---|---|
| UI | PySide6（Qt Widgets），QSS 主题，手风琴侧边栏 |
| 服务 | 纯 Python + QObject/QThread |
| 模型 | 自研 `BaseJsonModel`（原子写入 + 版本号） |
| 存储 | `data/*.json`（本地文件） |
| AI | Hermes 负责模型与工具调用。桌面提供网关的启动控制和本机进程状态 |
| 数据操作 | `scripts/actions.py`（命令）+ `actions_core.py`（读写/校验/备份）+ `actions_cli.py`（argparse） |
| 移动端 | Hermes 微信网关 → 专用原生工具 → `hermes_actions.py` → `actions.py` CLI |

入口：`main.py` → `src/app.py:App(QApplication)`。

## 2. 分层与依赖方向

```
i18n  ←──────────────┐
                     │
ui ──→ services ──→ models ──→ base(BaseJsonModel)
 │                      ↑
 └──→ scripts/actions.py（独立，直接读写 JSON）
```

**规则**：依赖单向 `ui → services → models`；`scripts/` 独立可执行。
**现状**：`✔` 2026-10-16 —— 曾记录的反向依赖（服务层 `import src.ui.styles.theme`）已随代码演进移除；
现由 `.importlinter` 的 layers 契约常驻守卫（`lint-imports`：1 kept / 0 broken）。

## 3. 启动顺序（实际，`src/app.py:App.__init__`）

> ⚠ 旧的 `AllTheFiles.md` 记录的是另一套顺序，与当前代码不符；**以本节为准**。

1. 单实例探测：`QLocalSocket.connectToServer` → 成功则 `is_secondary=True` 直接返回
   （key 默认 `StudentSchedulerSingleInstance`；测试可用 `LIFE_ASSISTANT_SINGLE_INSTANCE_KEY`
   换独立管道 —— 真实应用在跑时，同名管道的连接可能被它接走）
2. `setApplicationName`、`setQuitOnLastWindowClosed(False)`
3. Windows：`SetCurrentProcessExplicitAppUserModelID`（任务栏图标归属）
4. 构建图标（`_make_icon`，可选 `resources/image.png`）
5. `SettingsManager(DATA_DIR/"settings.ini").load()`
6. `i18n.load(language)` —— 语言包 = `src/i18n/zh-CN.json` + `src/i18n/zh-CN.d/*.json`（按模块分片，
   合并加载）；语言包缺失时**回退 zh-CN**（不抛异常）。UI 文本一律 `tr("键")`，见 `CODE_STANDARDS Q-N5`
7. `init_theme(app, theme_mode)` + `setStyleSheet`
8. `set_autostart(auto_start)`（写注册表 Run 项）
9. **`DataManager(DATA_DIR)`** —— 创建 11 个 Model（含按学期的 3 个、共享的 6 个、
   `semesters` 注册表与私有 `membership_contacts`），并启动 **3s 轮询 QTimer**
10. `ReminderService(settings, data_manager)` + 连接 `reminder_notify` / `ddl_alert`
12. `GitSync(repo=DATA_DIR.parent, data_dir)` + 连接 `data_changed` / `sync_status`
13. `PluginManager(plugins_dir)` + `load_plugins()`（只扫描，不导入插件代码）
14. **`MainWindow(...)`** —— 内部创建 `WeatherService`。设置里的 Hermes 控制只在用户点击时发起独立网关进程
   - **面板按需构造**（2026-11-23，方案 A-1）：`MainWorkspace` 只立即构造首屏需要的
     日程视图 / 占位页 / 设置页；其余 7 个面板用 `PanelSlot` 代理槽进栈，**首次进入才构造**
     （`_panel_map` 的索引与键集不变）。构造前到达的事件由槽攒着，建好后补刷。
     回退：环境变量 `LIFE_ASSISTANT_LAZY_PANELS=0` → 启动即全构造（与改造前一致）。
15. `_setup_tray(icon)`（托盘先于窗口显示）
16. `_window.show()`
17. `_flash_timer` 初始化（**在 `show()` 之后**；因为 `_on_ddl_alert` 依赖它）
18. `ReminderService.start()`（补跑 catch-up + 首轮检查 + 连接 `data_changed`）
19. `QLocalServer.listen` + `newConnection → _on_second_instance`（唤醒已有窗口）

## 4. 数据流：三条路径并存（重要）

| | 路径 A：UI | 路径 B：AI / TG | 路径 C：外部修改 |
|---|---|---|---|
| 入口 | Panel 直接调 Model（如 `dm.courses.update_course(...)`） | `scripts/actions.py` 命令 | 其它进程（TG bot）写文件 |
| 持久化 | `model.save()` → `atomic_write()` | `actions_core.save()`（写前备份 + 指纹校验 + 原子写） | —— |
| 通知 | `dm.data_changed.emit("<域>")` | `InstructionParser.execute` 调 `dm.reload_all()` + `emit("ai_action")` | `DataManager._auto_reload` 每 3s 比对 mtime（差 >0.1s）→ `reload()` + `emit("external")` |

**`data_changed(str)` 参数约定**：域名字符串（`course` / `task` / `habit` / `exam` / `expense` / `plan` /
`inventory` / `study`）或特殊值 `external` / `ai_action` / `internal`。

**消费方**：
- `MainWorkspace._on_data_changed` —— 按 `EVENT_PANELS` **显式映射**刷新（未登记事件保守全刷；
  日程视图总是刷）。**默认同步**：用户点完 / 外部写入到达就当场刷新 ——
  `tests/test_data_flow.py` 钉住"晚一拍是回归"这条语义。只有**批量事件**
  （`ai_action` / `ai_undo`，一次操作连发多个）才走 `RefreshCoalescer` 合并成一次重绘。
  三套标识符必须经表翻译（见 §9）：`KEY_TO_DOMAIN`（导航键→域名）、
  `ATTR_TO_KEY`（属性名→导航键）、`EVENT_PANELS`（域名→面板集合）；
  拿导航键直接比域名会**静默不刷**（`ERRORS #067`）。
- `GitSync.on_data_changed` —— 启动 30s 防抖计时，随后 `git add -A -- <用户数据清单> && commit && push`
  （范围见 `git_sync.DATA_FILES` / `DATA_DIRS` —— **唯一清单**，自动与手动同步共用；
  手动同步**不再** `git add -A`，源码由开发时显式提交。派生文件不进库，见 `.gitignore`）
- `ReminderService._on_data_changed` —— 仅当 `"task" in action` 时重算 DDL 计数

> ⚠ **架构债**：路径 A 与 B 是**两套真值来源**（Model 内存态 vs 磁盘文件），靠 3s 轮询"对账"。
> 见 `CODE_STANDARDS Q-E2`、`PLAN B-*`。
> 探针已改为 `st_mtime_ns`（2026-11-21 P1）：亚秒级外部写入不再漏检，缺失/重建也算一种状态。
> 通知**按域**发（`DataManager.DOMAIN_OF`：`tasks.json` → `task`），只有没登记域名的文件
> 才退回 `external` 全刷。

### 4.1 Hermes 微信入口（2026-11-20）

Hermes 使用独立运行时，项目不依赖 Hermes Python 包。仓库维护
`scripts/hermes_plugin/`，部署副本加载 `daily_task_query`、`daily_task_update` 与 `daily_task_documents`。
模型输入为受限 JSON；工作区、解释器、测试数据目录及通信 key 只能由操作者配置。
微信工具集显式选择 `daily_task`，模型不能通过该入口调用通用终端或文件编辑工具。

工具以固定 argv、`shell=False` 启动项目 venv 的 `scripts/hermes_actions.py`，
JSON 只经 stdin 传递。写操作复用 `ai_guard.run_batch` 的策略、快照、审计与回读验收，
执行器再用项目解释器启动 `actions.py` CLI，保留运行中应用的单实例委派。
命名管道已连接但未获得可信回执时拒绝直接写入；没有应用时走原有原子写入及写前备份。
CLI 与委派接受端均识别 `--key=value`，文本中的空格、引号和 `--` 不改变参数边界；
只有 SPECS 中的整数字段会转换类型，数字标题仍为字符串。

当前开放 `add_task / complete_task / add_course / update_course / add_plan / complete_plan`，
库存写操作开放 `add_item / update_item / consume`。查询默认返回当前学期课程、作业状态和指定日期日程；
`scope=inventory` 返回“有什么”条目及提醒，`scope=restock` 只返回当前需处理的续费/补买提醒。
提醒以模型的日期派生状态为准，仅包括学校侧且未豁免的项目；会员到期 7 日内（包括自动续费）
提示续费，另识别预计用尽日期、商品保质期和低库存。
查询使用 `semester_paths` 的纯路径函数，不调用会创建或修复注册表的 `resolve()`。
不读取设置、私有联系人或附件文件。更新课程只传显式字段，保留未传字段。
`delete_item` 需要交互式人工审批，微信桥没有审批界面，因此不对微信暴露；课程、作业和日程
也不提供删除、整日覆盖或恢复操作。

库存 `add_item / update_item / consume` 与其它写操作一样经固定 Actions CLI、
`ai_guard`、写前快照和回读验收。`update_item` 按显式提交的每个字段核验，
覆盖数量、名称、备注、标签、会员和账单等字段；成功回执须包含 `verified` 或 `verified_noop`，后者表示状态已经满足。
`coverage.checked/total` 保留既有验收覆盖度，新增作业/课程/日程通常只验收标题/名称，
不能宣称所有字段都已核对。模型必须根据回执汇报；失去回执或超时标记 `uncertain`，
应先查询，不自动重试写操作。单条 CLI 超时 90 秒，外层桥接超时 150 秒；
插件用进程内锁串行调用，快照与 UI 并发操作仍沿用现有指纹冲突保护。
微信查询按需返回库存提醒；不会定时主动向微信推送。桌面端另有每日一次的补货/续费通知。
普通文档由插件在显式配置的目录内处理，与应用数据写入链隔离。桌面入口不再实例化原创 AI 助手。
工作区库存扩展需复制插件源码到部署目录并重启网关后才会在微信生效；部署与隔离测试要求见 [HERMES.md](HERMES.md)。

微信定时提醒由 Hermes Cron 调用免模型脚本。脚本只读业务数据，复用邮件与首页规则，
在 Hermes 端独立去重，桌面只额外发布普通作业提醒开关。部署入口及频率见 [HERMES.md](HERMES.md)。

## 5. 跨模块信号总览

| 发射者 | 信号 | 接收者 | 作用 |
|---|---|---|---|
| `ReminderService` | `reminder_notify(str,str)` | `App._show_reminder_notify` | 托盘通知 |
| `ReminderService` | `ddl_alert(int)` | `App._on_ddl_alert` → `MainWindow.set_ddl_alert` | DDL 计数 + 托盘闪烁 |
| `DataManager` | `data_changed(str)` | `GitSync` / `MainWorkspace` / `ReminderService` | 数据变更广播 |
| `GitSync` | `sync_status(str)` | `App._on_sync_status` | 托盘 tooltip |
| `ScheduleView` | `course_table_requested` / `task_focus_requested(str)` | `MainWorkspace` | 日/周 切换通知 / 跨面板跳转 |
| `MainWorkspace` | `panel_changed(str)` | `Sidebar.set_active` | 程序化跳转（状态栏/课程）同步左侧高亮 |
| `Sidebar` | `nav_changed(str)` | `MainWindow` | 导航 |
| `WeatherService` | `weather_updated(dict)` / `forecast_updated(list)` | `MainWindow` / `WeatherDetailDialog` | 天气刷新 |
| `QLocalServer` | `newConnection` | `App._on_second_instance` | 第二实例唤醒 |

> **`data_changed(str)` 的消费约定（`ERRORS #025`）**：`external` / `internal` **不带域名**，
> 消费方必须当作"不知道改了什么"处理 —— `MainWorkspace` 全刷、`ReminderService` 重算 DDL；
> 只有具体域名（`task` 等）才允许走"按子串匹配只刷一个面板"的增量路径。

> **考试数据的两个来源（`ERRORS #022`）**：`exams.json` 是权威来源，但历史数据把考试
> 建成普通任务（标题/标签含「考试」）。提醒与日报都按 `(名称, 日期)` 合并去重后消费。

## 6. 并发模型

| 线程载体 | 位置 | 职责 |
|---|---|---|
| `QThread` + `AIWorker` | `services/ai_service.py` | AI 请求 + Agent Loop（最多 5 轮 **且总时长 ≤ `AI.max_seconds`=90s**）+ 执行指令 |
| `QThread`(`WeatherWorker`) | `services/weather_service.py` | 和风天气 HTTP |
| `QThread`(`_GitWorker`) | `services/git_sync.py` | `git add/commit/push` 子进程 |
| `QThread`(`_ApiWorker`) | `services/api_service.py` | "API 测试"弹窗：委托 `openmeteo` / `deepseek` |

> Open-Meteo / DeepSeek 余额的**同步**实现分别在 `services/openmeteo.py` 与 `services/deepseek.py`
> （每能力一套适配，`Q-A3`）；`api_service` 只负责起线程 + 发信号。

**主线程定时器**：`DataManager._auto_reload`（3s，比对 8 个文件 mtime —— 含 `semesters.json`）、
`ReminderService._check`（60s）、`MainWindow._status_timer`（30s）、`WeatherService` 自动更新（10min / 1min 轮询）。

**已知线程安全问题**（见 `CODE_STANDARDS §B`；2026-10-16 两轮整改后状态）：
- ✅ AI worker 不再触碰 Model：`InstructionParser.execute` 只跑命令，重载/通知由主线程 `_on_response_with_instructions` 负责
- ✅ 余额/天气缓存由类属性改为实例属性；`RUF012` 清零
- ✅ `QThread.terminate()` 已移除（改按 `sender()` 丢弃过期结果）
- ✅ `weather_service` 按接口类型管理 worker；`git_sync` 等均 `deleteLater`
- ✅ **QThread 结果信号不遮蔽基类 `finished`**（`ERRORS #058`）：`WeatherWorker.result` /
  `_ApiWorker.result` / `_GitWorker.done`；回收统一连 `QThread.finished`；
  `WeatherService.shutdown()` / `MainWindow.shutdown()` 在退出前 `wait()` 线程
- ✅ 天气派生缓存（`weather_cache.json`）启动即加载，离线也能显示状态栏与详情；
  `WeatherService(settings, data_dir=...)` 可注入沙箱目录（测试不碰真实 `data/`）
- ✅ **系统提示词构建不再同步发网络请求**：余额/天气缓存改由一次性守护线程预热
  （`AIService._warm_context_cache`），`_build_system_prompt` 只读缓存；预热不触碰主线程属主的 `WeatherService`
- 🔄 `actions.run_in_process` 仍用 `contextlib.redirect_stdout`（已加锁串行化；彻底修复需 handler 返回字符串）
- ✅ **写入只有一个写者**（`PLAN.md` P17 阶段 3，2026-10-17）：CLI 写前用单实例通道探应用 ——
  在跑就把命令交给应用执行（`run_argv_in_process` + `reload_all()`），不在跑才自己写，
  连上但没回应则**拒绝**（不静默直写）。保存冲突另有**内容指纹**兜底（见 §7 不变量 2）

## 7. 关键不变量

1. **单例**：`SettingsManager` / `DataManager` 只在 `App.__init__` 实例化（`CODE_STANDARDS`/`AGENTS.md` R-001）。
2. **原子写入**：所有持久化走 `BaseJsonModel.atomic_write()`——写 `.tmp` → 备份 `.bak` → `os.replace`（PermissionError 重试 5×50ms）。
   AI 那条路径（`scripts/actions_core.save()`）同样原子：结构守卫 → 写前备份到
   `data/backup/actions/` → `.tmp` → 回读自检 → `os.replace`（`ERRORS #042`）。
   **退出 / 重启**走 `DataManager.flush_on_exit()`：磁盘内容 == 内存 → 不重写；其余交给
   `BaseJsonModel.save()`，由 `_disk_fingerprint` 区分"启动自愈"与真实外部改动 ——
   自愈安全落盘，真实外部改动**不覆盖**，我方版本留到 `data/backup/save_conflict/`
   （`ERRORS #061`）。`save_all()` 是**无条件**写，只给"明确没有外部写入"的场合（测试 / 验收脚本）。
   **保存冲突检测**：`BaseJsonModel.save()` 写前比对**磁盘内容指纹**（sha256 + `sort_keys`），
   不一致 → **不写** + `on_conflict` 回调 → `DataManager` 留副本并发 `save_conflict`
   （`MainWindow` 弹窗）。用指纹而不是 `_rev` 号：后者要求每个写入方配合维护，
   `actions_core` / skill / 手工编辑都会漏。
   **提交回执（2026-11-21 P0）**：`actions_core.save()` 在**目标文件锁内**产生
   `{operation_id, target, before_sha, after_sha, version, changed_fields}`（线程局部，
   实现见 `scripts/actions_receipt.py`）。撤销以回执为准，**不再**在命令执行完之后读盘 ——
   Hermes 通过 CLI 和桌面委派协议收到同一提交回执。缺少回执、实际目标或写前指纹
   与快照不符时，撤销被禁用。旧回执不从事后读取的磁盘状态补推。
   登记失败 → `ai_undo/pending.json` 旁标 + `pending_repair`，界面如实报"撤销记录待修复"。
3. **显式保存**：Model 改内存态后**不会自动落盘**，必须显式 `save()`。
4. **日期语义**：`course.schedule_date()` —— **0:00–1:00 视为前一天**；跨模块统一用它，不要直接用 `date.today()`。
5. **时区**：全部本地时间，无 tz 处理；`due_date` 形如 `YYYY-MM-DDThh:mm:ss`，日期型为 `YYYY-MM-DD`。
6. **ID 生成**：统一走 `models/base.next_id()`（最大后缀 +1）；禁用 `len()+1`（R-008）。
7. **学期口径单一**：所有"第几周 / 学期是否结束"的判断**只能**走 `models/semester.py`
   （`semester_status()` / `week_number_for()`），模型与脚本（含 `send_digest.py`）都调它。
   状态：`none`（无学期）/ `invalid`（数据不合法，算不出周次）/ `not_started` / `active` /
   **`exam`（期末周）** / `expired`。学期 = **16 教学周（默认）+ 1 期末周（默认）**；
   `teaching_end_date` 是教学周最后一天，`end_date` 含期末周。
   历史上这里散过 5 处各算各的（状态栏不钳上界 → 显示"第 32 / 16 周"、AI 忽略
   `current_semester`、摘要第三套算法），见 `ERRORS #037`。
8. **提醒出口单一**：所有提醒都走 `ReminderService._notify()`；"什么算命中"是**纯函数**
   （`services/reminder_rules.py`）。总开关 `General/reminder_enabled`（默认开）控制
   托盘与普通提醒；**紧急邮件例外** —— 考试 14/7/3 天、作业 6 小时内用 `mandatory=True`
   **永远发**（漏掉的代价远大于被打扰，用户明确要求）。规则：点名课前 30 分钟、
   作业 3 天内 / 6 小时内、考试 14/7/3 天、习惯提前 5 分钟、余额低于阈值、自定义提醒、
   **午饭 / 晚饭 11:40 / 16:40**（整点后 90 分钟内算数，每天各一次；同一时刻首页那条
   提示会**低频闪烁**，见 `services/hints.py` 的 `meal_hints()`）、**月付 / 分期到期**
   （`models/billing.due_today()`：每月 `due_day` 号扣一次，**补扣**同月一次；
   服务层自动记一笔支出 + 邮件，期数扣完自动停用 —— 用户 2026-10-31 口径）。
9. **课程时段规则单一**：`models/course_rules.py`（`is_active_week` / `slots_of` /
   `conflicts_by_cell`）。`time_slots` 的 `end` 是**闭区间**；**同一时段允许两门课**，
   冲突要检出并提示请假（见 `ERRORS #038`）。
10. **按学期分文件**：课程表 / 作业 / 考试各自在 `data/semesters/<当前学期>/` 下，
   "有什么 / 记账 / 习惯 / 日程计划"跨学期共享（用户口径）。
   切学期**只能**走 `DataManager.switch_semester()` —— 它把三个模型重定向到新文件；
   直接改 `semesters.json` 的指针不会换数据（`ERRORS #040`）。
   旧布局由 `semester_paths.migrate_legacy()` 一次性迁移（先写新文件、校验、再删旧文件）。
11. **算数只在代码里**（用户口径 2026-10-31）：收入 / 预计支出 / 结余这类数字由
   `services/finance.py` 的**纯函数**算（过去 3 个整月中位数），界面注明依据；
   **AI 只解释、不许自己算** ✗ —— 它只能调 `finance_summary` 读结果。
12. **`data/` 是用户数据**（含密钥 `settings.ini`），不进发行版（`Q-P2`）。
13. **备考统计只在代码里**（2026-11-01）：学习分钟 / 待复习 / 模考趋势 / 倒计时全部由
   `StudyModel.summary()` 现算，不落派生值；AI 只能调 `study_summary` 读结果，
   **不许自己加总/估算**（与财务 A4 同一口径）。
14. **版本与损坏**（2026-10-17，审查 #5；2026-11-21 分类收敛）：`migrate()` **逐步**执行且
    **缺一步就拒绝**（`MigrationUnavailable`，不写文件）—— 不许"找不到迁移函数也把 `_version`
    抬上去"。文件**缺失** → 建默认值；**损坏** → 改名留档（`*.corrupt-<时间戳>.json`）+
    用默认值继续 + ERROR 日志（`DataManager._log_recoveries`）；**版本比本程序新** → 只警告、不改动。
    "损坏"的口径统一在 `BaseJsonModel._schema_problem()`：**根不是对象**、`_version` 类型不对、
    顶层键类型不符、非法 UTF-8、非法 JSON 都归这里 —— 原来只有 `JSONDecodeError` 会被捕获，
    另外三种从别处炸开（既不留档也没有默认值兜底）。
    **暂时不可读**（`OSError` 重试后仍失败）是**另一类**：抛 `Unreadable`，**不留档**
    （否则会把好文件永久改名），用默认值继续并禁止写入；`reload()` 成功即解除封锁。
15. **备份有归属**（2026-11-21 P0）：按学期的三个文件在 A/B 两个学期下**同名**，
    扁平备份池分不清来源 → 用 A 的快照 `restore` B 会把 B 覆盖掉。
    清单（`data/backup/actions/index.json`）记 `semester_id` / `schema_version` / `sha256` / `seq`；
    `restore` 在**目标锁内**依次校验归属 → 版本 → 内容指纹，通过才提交。
    来源未知的旧快照要求 `--semester` 显式声明归属；轮转按 `seq`（不能按文件名，同秒的
    `-10` 会排到 `-2` 前面）。

## 8. 数据文件 schema 总表

**布局（按学期分文件）**：

```
data/
├── semesters.json                     学期注册表：semesters[] + current_semester（共享）
├── semesters/<学期id>/
│   ├── courses.json                   该学期课程表（含 holidays）
│   ├── tasks.json                     该学期作业
│   └── exams.json                     该学期考试
├── habits.json / routines.json / expenses.json / inventory.json / daily_logs.json    跨学期共享
├── study.json                         考研备考：学习记录 / 错题 / 模考（跨学期）
├── attachments/<task_id>/             作业附件实体（JSON 只存元数据；不存绝对路径）
├── private/memberships.json           会员手机号（**私有**：不进仓库、不进 AI 提示词）
├── ai_actions.jsonl                   AI 审计（JSONL，脱敏；**本地-only**，不进数据仓库）
├── ai_undo/                           动作级撤销快照（index.json + blobs/；**本地-only**）
└── search_index.json / weather_*.json / scenes_meta.json             派生或遗留
```

> 路径解析**只有一处**：`models/semester_paths.resolve()`（应用、`actions.py`、`send_digest.py`、
> `build_index.py`、测试助手都调它）。切学期必须走 `DataManager.switch_semester()`
> —— 它会把 `courses/tasks/exams` **重定向**到新学期的文件（`ERRORS #040`）。

### 8.1 作业附件与详细备注（2026-11-02）

- `tasks.json` 的 task 复用 `notes`（纯文本，`QPlainTextEdit`，上限 20,000 字符）与
  `attachments[]` 元数据；元数据只含 `name/stored_name/size/sha256/added_at`，**不存绝对路径**，
  所以整个 `data/` 搬到沙箱或另一台机器后仍可解析。
- 文件实体由 `services/attachments.py::AttachmentStore` 管理，根目录为
  `DataManager.data_dir / "attachments"`（不是模块级 `get_data_dir()`）。每个任务一个子目录；
  添加时复制、按 sha256 在**同一任务内**去重，单文件 25MB、每任务 20 个上限。
- 路径安全 fail-closed：只取 basename、清洗非法字符/Windows 保留名/结尾点号，落盘前
  `resolve()` 必须仍在 root 内；目录/符号链接/不存在/不可读的源拒绝。打开走
  `QDesktopServices`，不拼 shell 命令；文件缺失只显示“已丢失”并提示，不抛异常。
- 删除顺序固定为**先提交索引、再删文件**：`TaskDetailDialog` 先把 `tasks.save()` 的结果作为
  提交条件，失败时不删任何附件，并恢复内存中的 `notes/attachments/updated_at`（避免下一次
  退出时把内存态写成冲突副本）；失败只影响磁盘清理，不影响已提交的索引。
- UI：`TaskPanel` 第 5 列“详情”或双击打开 `TaskDetailDialog`；有备注/附件时显示指示点。
  附件行支持打开/移除；移除先进入内存待删列表，保存成功后才 `unlink`。
- 附件字节和绝对路径**不进入 AI 提示词**；任务 JSON 只暴露名称/数量/大小。附件是否进入
  `git_sync` 的数据同步范围沿用数据仓库策略，当前不在此模块内另开写路径。

### 8.2 AI 监督产物（本地-only）

- AI 写入仍**只走** `scripts/actions.py`（R-002）；`services/ai_guard.py` 在它外面依次做
  `策略 → 审批 → 快照 → 执行 → 回读验收 → 审计`，不改变用户数据 schema。
- `ai_actions.jsonl`：append-only JSONL，事件类型 `request / action / approval / verify / undo / claim`。
  `command` 里的 `--note/--notes` 值与 JSON `note` 字段在 `ai_audit.redact_command()` 里剥成 `***`；
  用户原话只存 `user_text_sha256` + `user_text_len`；模型的最终自述只存 `claim_sha256` + 长度。
  轮转 `2MB × 5`，没有按天清理。
- `ai_undo/index.json` + `blobs/`：每条写命令执行前留目标文件快照；撤销要求当前文件指纹等于
  `after_hash`（stale 拒绝），且 `after_hash != before_hash`（no-op 不提供撤销）；保留最近 50 条。
- 两者都在 `data/.gitignore`，`git_sync` 的 `git add -A -- data/` 不会带上 —— 它们是**本地**
  审计/撤销证据，不随私有数据仓库同步/推送；需要长期归档时应另做导出（当前不做）。


| 文件 | `_version` | 顶层键 | 关键字段 |
|---|---|---|---|
| `semesters.json` | 1 | `semesters[]` `current_semester` | semester: `id,name,start_date(YYYY-MM-DD),total_weeks(1-30，默认 16),exam_weeks(0-6，默认 1),period_count(1-12)` |
| `semesters/<id>/courses.json` | 1 | `courses[]` `holidays{excluded[],makeup{}}` | course: `id,name,teacher,day_of_week(1-7),weeks{start,end},time_slots[{start,end,location}],week_parity(all/odd/even),excluded_weeks[],notes` |
> `time_slots` 的 `end` 是**闭区间**：单节连堂写 `{"start": 1, "end": 1}`。
> **同一时段允许两门课**（选修过多 / 重修）→ 由 `course_rules.conflicts_by_cell()` 检出并提示请假（`ERRORS #038`）。
> **会点名的课**在 `course["reminders"]`：`{"attendance": bool, "lead_minutes": 30}`——
> 由课程右键菜单开关（界面不猜哪门课点名，只有用户知道），`reminder_rules.attendance_due()` 据此在开课前提醒。
| `semesters/<id>/tasks.json` | 2 | `tasks[]` `archived[]` | task: `id,title,course_name,due_date,status(pending/completed),priority,tags[],notes,attachments[],created_at,completed_at,reminded`；attachments: `name,stored_name,size,sha256,added_at`（无绝对路径） |
| `semesters/<id>/exams.json` | 1 | `exams[]` | exam: `id,course_name,exam_date,scope,location,notes,tags[],created_at,updated_at` |
| `habits.json` | 2 | `habits[]` `attached_task_templates[]` `logs{date:{hid:{completed,completed_at,note}}}` | habit: `id,name,schedule{type(daily/weekly/monthly/interval),days[],value,times_per_day,start_date},duration_minutes,reminder_time,streak,longest_streak,postpone_until,canceled_on[]` |
| `expenses.json` | 1 | `categories[{id,name}]` `budget{monthly,by_category}` `records[]` `finance{balance,monthly_income,fixed_expenses,updated_at}` | record: `id,amount,date,category,note,created_at`；分类里多一条 **`subscription`=「订阅/分期」**（月付/分期到期自动记的那些走它，A1）；`finance` 是**用户设的初始值**，"预计本月支出"等**算出来的**一律现算（`services/finance.py`，A4），不落盘 |
| `routines.json` | 1 | `items[]` `logs{date:{rid:"done"/"skipped"}}` | routine: `id,title,note,order,created_at` —— **「近期安排」**（2026-10-30 A3）：不是习惯、没有连续天数，三态按天存（空/✔/✗），`order` 就是拖动后的顺序 |
| `daily_logs.json` | 4 | `logs{}` `plans{date:[...]}` `savings{date:[...]}` `reminders[]` | plan: `title,time_slot(1-6),type(custom/course_note),note,course_name,created_at`；**`category(study/life)`**（日程顶部的学习/生活筛选，视图状态 + 用户可改）、**`done`/`completed_at`**（2026-10-18 加）；reminder: `id,item_type,item_name,item_date,notify_time` |
| `study.json` | 1 | `target_date` `daily_goal_minutes` `subjects[]` `sessions[]` `mistakes[]` `mocks[]` | session: `id,date,subject,minutes,note,created_at`；mistake: `id,subject,topic,question,answer,note,stage,interval_days,reviewed_count,next_review,mastered`（阶梯 `1/2/4/7/15/30` 天）；mock: `id,date,subject,score,full_score,duration_minutes,note`。**所有统计现算**（`StudyModel.summary()`），不落派生值 |
| `inventory.json` | 1 | `items[]` `categories[]` `locations[]` | item: `id,name,category,group,quantity,unit,status(充足/不足/需购),min_quantity,min_doses,doses_per_unit,location,notes,tags[],instances[],ignore_low_stock`；**到期类**：`membership{username,expires_on,auto_renew,renew_months}`、`runs_out_on`+`remind_before_days`（预计用完）、`expires_on`+`remind_before_days`（保质期）、**`stock_target`**（常备量，剩 1/4 提醒）；**月付/分期**（A1，2026-10-31）：`billing_type(monthly/installment)` + `amount`（每期金额）+ `due_day`（每月几号）+ `installments`（期数，月付填 0 = 不限期）+ `paid_count` + `billing_active` + `last_charged_on`；**衣物**：`worn_since`+`wash_after_days`+`needs_wash`（见 §11） |
> **位置就是归属**（2026-10-18）：换季把部分衣物**寄回家**、来年寄回，所以"在哪一边"要能表达 ——
> 但**不单独存字段**，一律由 `location` 推导（`InventoryModel.side_of()`）：位置是「家」→ 家侧，
> 其余（宿舍格位 / 「学校」/ 空）→ 学校侧。
> - 词表 `locations[]` = 宿舍格位 + **「学校」「家」**两个粗格位（由 `set_locations` 维护）
> - **没说位置时默认「学校」**（虚拟品类如会员留空）—— 这条规则是**常量**，不依赖界面状态
> - 界面的"看哪边"切换是**纯视图状态**（`InventoryPanel._side`），不写数据文件、不进同步
> - **补货只看学校侧**（`need_restock` 与补货提醒都不列"家"那批）
> - 为什么不存 `dataset` 字段 / 不让模型判断"家里"指哪边：flash 模型中文不稳，靠它理解
>   "家里"**必错**（2026-10-18 探针实测：把"家里抽纸"记成了寄回家的那批）——
>   改成"抄位置"这种机械规则后，模型只需要会复制字符串
> **会员（虚拟品类，2026-10-18）**：会员要和账号绑定 → item 里的 `membership`：
> `{username, expires_on(YYYY-MM-DD), auto_renew(bool), renew_months(月数)}`。
> - **到期日决定状态**：过期 → 需购（要续费）；`RENEW_WARNING_DAYS`（7）天内 → 不足（要到期了）；
>   否则充足（有效）。**自动续费开着也照常按到期日算** —— 那个开关只是记着。
> - 会员的状态**随时间变** → 读盘时重算（`InventoryModel.load()`）；界面 / 提示词 / 补货一律走
>   `effective_status()`（**只对会员重算**，非会员保留手动 `--status` 的结果）
> - ⚠ **手机号不在这个文件里**：单独放 `data/private/memberships.json`
>   （`.gitignore` + `git_sync.PRIVATE_FILES` 双保险），**也不进 AI 提示词** ——
>   进了提示词就等于发给模型服务商。手机号只在面板弹窗里录；`--membership` 里带手机号会被拒绝。
> **物品的可写字段只有一份清单**（`inventory.ITEM_FIELDS`，2026-10-19）：`add_item` / `update_item`
> 都读它，**不许各写一份**。原来两个方法各有一份白名单 ✗，后加的字段（`membership` /
> `expires_on` / `runs_out_on` / `stock_target` / `worn_since` …）只加进了**命令路径**
> （`scripts/actions_cmds_items.py` 直接改 dict，不经过模型）→ **会员弹窗填完到期日一保存就没了** ✗，
> 而 `update_item` 仍返回 `True` 谎报成功。⚠ 命令路径的测试（`test_actions_*`）**全走 CLI**，
> 覆盖不到模型的这两个方法 ✗ —— 这是它能潜伏这么久的原因。清单外的键现在会**告警**。
| `settings.ini` `[Weather]` | — | `lat` `lon` | 天气位置（原「场景存档」已弃用，位置迁到此处；`scenes_meta.json` 为遗留文件，不再读取） |
| `settings.ini` | — | `General` `AI` `Semester` `Window` `Backup` `Email` `Balance` `Weather` | 含密钥，**gitignore** |
| `weather_cache.json` / `weather_stats.json` / `search_index.json` | — | 派生/缓存 | 易变，非权威 |

## 9. 扩展点

- **新增面板**：`src/ui/panels/xxx_panel.py` → `ui/components/main_workspace.py` 的 `_panel_map`/`panels` 注册 →
  `ui/components/sidebar.py` 加入条目 → 更新 `README.md`。
  （注意：**课程表不是独立面板**，它是 `ScheduleView` 内部的"周"页，见 `ScheduleView.course_panel`。）
- **新增数据模型**：`src/models/xxx.py`（继承 `BaseJsonModel`）→ `DataManager.__init__` 实例化 → 若要 AI 可操作，补 `scripts/actions.py` 命令。
- **新增 AI 命令**：`scripts/actions.py`（handler）→ `scripts/actions_cli.py`（argparse）→
  `actions_core.SPECS`（参数规格：必填/范围/枚举）→ `SYSTEM_PROMPT_BASE` → TG skill。
  **五处必须一致**，由 `tests/test_prompt_consistency.py`（命令 ↔ 提示词双向）与
  `tests/test_actions_validation.py`（`SPECS` ↔ CLI 参数白名单）把关。
  **AI 传错参数是必然而非偶然**：校验统一在 `run_in_process` / CLI 入口做，handler 里不要再兜底。
- **新增插件**：`plugins/<name>/plugin.py` + `IsOpen.able`（约定见 `Q-N`/`PLAN I-13`）。
- **新增延迟面板**：在 `main_workspace.py` 的 `_add_panels()` 里放**类**而不是实例，
  并在 `ATTR_TO_KEY` / `KEY_TO_DOMAIN` 各补一行 —— 两张表都要有，否则"切页能进、
  事件不刷"（`ERRORS #067`）；`tests/test_lazy_panels.py` 会逐键核对。

### 9.1 性能原型（**未接线**，仅供后续评估）

两者都**不在生产调用链上**，但都有测试守着；改动它们不需要动任何 UI 入口。

| 原型 | 位置 | 结论 |
|---|---|---|
| 周视图 Web 页（方案 B） | `src/ui/widgets/week_web_prototype.py` | **不采用**：首帧 1.53 s（WebEngine 渲染进程冷启动），与"启动不能等"的目标冲突。换周注入本身 0.3 ms 极快，适合只读重绘面板 |
| 作业 SQLite 存储（方案 C） | `src/services/task_store_sqlite.py` | **整体切换不批准**（按预算判定 2/4 达标：列表 −152%、导入 −43% 超预算）；**仅切写入批准**（单条完成 +100%）。判据见 `scripts/perf_sqlite_decision.py` |

测量设施：`scripts/perf_bench.py`（合成档位 + 中位 / P95 / 失败数 + `archive()`）+
`perf_baseline.py` / `perf_profile.py` / `perf_panel_bench.py` /
`perf_panel_costs.py` / `perf_sqlite_bench.py` / `perf_week_web.py` /
`perf_memory.py`（进程树私有提交量）/ `perf_sqlite_decision.py`（预算判据）。
**原始样本归档在 `dev-logs/perf-data/`**（每份产物都带逐次耗时 + 环境指纹 + 提交号，
清单见该目录的 `INDEX.md`；`tests/test_perf_artifacts.py` 守着"不许只有汇总"）。
首轮结论见 `dev-logs/2026-11-23-性能改造对比报告.md`。

## 10. 已知架构债（指向权威清单）

| 债务 | 权威位置 |
|---|---|
| 双写路径（Model 内存态 vs 磁盘） | `CODE_STANDARDS Q-E2`、`PLAN B-*` |
| 线程安全（跨线程改 Model、类属性缓存、terminate） | `CODE_STANDARDS §B`、`PLAN P3-①` |
| 三套天气实现 | `CODE_STANDARDS Q-A3` |
| ID 生成两套并存（`len()+1` / max+1） | `CODE_STANDARDS Q-A1`/`Q-E2`、`PLAN` |
| 盲捕获/静默吞异常 | `CODE_STANDARDS §I`（UI 层已改成**逐处** `# noqa: BLE001` + 理由，不再整目录豁免）|
| 测试覆盖率 / 门禁状态 | **不记数**：以 CI 与 `scripts/check_quality.py` 的实时输出为准（写进文档必漂）|
| 单条写入仍是整份 JSON 重写（10k 条约 168 ms） | `dev-logs/2026-11-23-性能改造对比报告.md` §3.3 |

## 11. 「今日提示」与到期/衣物判定（2026-10-18/19 新增）

**一个概念，多个规则来源，两种消费者**——这些建议**全部由代码算**，不经过模型：

```
规则（services/hints.py，纯函数）                产出          消费者
  weather_hints  天气 → 带伞/加衣/防暑        ┐
  wash_hints     衣物该洗（needs_wash_now）   ├→ Hint ─→ ① 日程界面顶部「提示条」（可点掉）
  budget_hints   本月预计超支（services/budget）│           ② 需要"每天一次"的走托盘 + 邮件
  outing_hints   今天有课/有安排 → 出门三条   ┘
```

**三条不变量**：

1. **不让模型判断"从数据推出来的建议"**——规则全在 `services/hints.py` 里写成纯函数（好测、
   无网络、无 LLM）。模型只负责**执行用户的话**，不负责**替用户发现该做什么**。
2. 提示是**视图状态**：点掉只影响今天这一次显示，**不写任何数据文件**（和"看哪一边"同类）。
   `Hint.key` 是幂等键——同一条今天只出现一次。
3. **提示条必须能换行**：`HintBar` 继承 `FlowGrid`（自然宽度流式）。提示会随数据变多
   （天气 + 该洗 + 预算 + 出门 = 可能 6 条），横排会把最后几条**挤出屏幕**
   （2026-10-19 渲染实测抓到，见 `dev-logs/2026-10-19-提示条不换行的bug.md`）。

`hints.today_hints(data_dir)` 读**派生缓存与数据文件**（`weather_cache.json` / `inventory.json` /
`expenses.json` / `daily_logs.json` / `courses.json`）——读不到就**不提示**，不报错。

**到期/衣物的判定链**（`models/inventory.py:derive_status`，优先级从高到低）：
会员到期 → 保质期到期 → 预计用完 → 数量阈值。前两类是**日期字段**（`runs_out_on` /
`expires_on`），衣物是**日期 + 间隔**（`worn_since` + `wash_after_days`）——
**都不存"还剩几天""穿了几天"这类计数器**（计数器会随"没开应用"而漂）。

**提醒复用同一个 tick**：喝水提醒（`water_reminder_due`，免打扰 23:00–07:00）**不另开定时器**，
挂在 `ReminderService` 每分钟的 tick 上判定。所有"每天最多一次"的推送（含补货）都受**总提醒开关**控制。

## 12. AI Agent Loop 的可靠性契约（2026-10-18 重做）

一次 AI 请求的实际流程（`AIWorker.run`）：

```
用户一句话
  └→ 组装 system prompt + 快照 → 模型（第 1 轮）
       └→ 模型回文本 + sh 命令块
            └→ 代码逐条执行（scripts/actions.py）
                 └→ 回读数据**验收**（ai_verify，所有写命令都有验收器）
                      └→ 把命令结果 + 验收结论回喂给模型 → 第 2 轮 …
                      └→ 直到：模型说结束 / 没有写命令 / 轮次或时间预算耗尽
```

**核心不变量：汇报权归代码。** 判断"做完了没有"**只看命令自己的结果**（`OK` / `ERROR`），
**不看模型的措辞**——模型说"已完成"不算完成，只有命令返回 `OK` 才算。
（α 测试实测：仅此一条，同一模型的落库量从 6 件 → 47 件。）

配套的四条（`services/ai_loop_guards.py` + `ai_service.py`）：

| 约定 | 做法 |
|---|---|
| **记账类命令不算用户可见效果** | `add_location` / `set_locations` 只是内部登记，不能拿来凑"我做了事" |
| **部分完成是常态** | 被轮次/时限切断时必须**量化上报**（"执行 N 条、写命令成功 K 条"），不笼统说"部分完成" |
| **重复阶梯** | 同一批命令重复出现时逐级加码提醒（`repeat_nudge`），不是无限重发同样的提示 |
| **守护状态可诊断** | 每批记录 `本批重复=N` + 触发护栏时的首句，出问题能回看 |
| **每条写命令都要验收** | `ai_verify._CHECKS` 覆盖全部写命令（新增命令漏验收器会被测试拦下）；`ai_ledger` 把事实写在模型说明之前 |
| **验收与写入同一口径** | 验收器比的是**落盘值**：写入端归一化过的字段（课程名 `match_course_from`、日期 `parse_date`）验收端必须调同一个函数；拿命令原文比对归一化后的字段会误报"找不到"（ERRORS #060） |

**提示不是安全机制**：写数据的强制点在 `scripts/actions.py`（同名同位置硬护栏），
prompt 里的话只是"劝"，护栏才是"挡"。

**反模式表进 CI**：`tests/test_agent_reliability_checklist.py` 把可机械化的自查项钉成测试
（设计依据：`Agent Reliability Engineering Design Guide` §2.3/§4/§6.3/§9.3/§12.1/§13.4/§14）。
α 逐条判定与病根见 `dev-logs/2026-10-18-α测试结论与处置.md`、`dev-logs/2026-10-18-AI可靠性-代码说了算.md`。
