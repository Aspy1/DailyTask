# ARCHITECTURE.md — 项目运作原理

> **定位**：本项目"如何运作"的权威说明——分层、启动顺序、数据流、信号链、并发模型、不变量、数据 schema。
> 只写**代码表达不了的东西**（跨文件时序、不变量、为什么、外部契约）；函数签名/参数/字段结构不在此重复。
> 相关文档：`AGENTS.md`（流程/环境）· `CODE_STANDARDS.md`（规范）· `PLAN.md`（计划/体检）· `ERRORS.md`（坑）。
>
> 最后更新：2026-10-15

---

## 1. 定位与技术栈

AI 驱动的 PySide6 桌面日程管理应用（学生向）。单进程、无服务端；数据为本地 JSON。

| 层 | 技术 |
|---|---|
| UI | PySide6（Qt Widgets），QSS 主题，手风琴侧边栏 |
| 服务 | 纯 Python + QObject/QThread |
| 模型 | 自研 `BaseJsonModel`（原子写入 + 版本号） |
| 存储 | `data/*.json`（本地文件） |
| AI | DeepSeek / Anthropic / **OpenCode Go**（可切换），Agent Loop 多轮 |
| 数据操作 | `scripts/actions.py`（命令）+ `actions_core.py`（读写/校验/备份）+ `actions_cli.py`（argparse） |
| 移动端 | 外部 TG bot 直接读写同一个 `data/`（零同步） |

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
2. `setApplicationName`、`setQuitOnLastWindowClosed(False)`
3. Windows：`SetCurrentProcessExplicitAppUserModelID`（任务栏图标归属）
4. 构建图标（`_make_icon`，可选 `resources/image.png`）
5. `SettingsManager(DATA_DIR/"settings.ini").load()`
6. `i18n.load(language)` —— 语言包 = `src/i18n/zh-CN.json` + `src/i18n/zh-CN.d/*.json`（按模块分片，
   合并加载）；语言包缺失时**回退 zh-CN**（不抛异常）。UI 文本一律 `tr("键")`，见 `CODE_STANDARDS Q-N5`
7. `init_theme(app, theme_mode)` + `setStyleSheet`
8. `set_autostart(auto_start)`（写注册表 Run 项）
9. **`DataManager(DATA_DIR)`** —— 创建 7 个 Model，并启动 **3s 轮询 QTimer**
10. `AIService(settings, data_manager)`
11. `ReminderService(settings, data_manager)` + 连接 `reminder_notify` / `ddl_alert`
12. `GitSync(repo=DATA_DIR.parent, data_dir)` + 连接 `data_changed` / `sync_status`
13. `PluginManager(plugins_dir)` + `load_plugins()`（只扫描，不导入插件代码）
14. **`MainWindow(...)`** —— 内部创建 `WeatherService`，并 `ai_service.set_weather_service(...)`
15. `_setup_tray(icon)`（托盘先于窗口显示）
16. `_window.show()`
17. `_flash_timer` 初始化（**在 `show()` 之后**；因为 `_on_ddl_alert` 依赖它）
18. `ReminderService.start()`（补跑 catch-up + 首轮检查 + 连接 `data_changed`）
19. `QLocalServer.listen` + `newConnection → _on_second_instance`（唤醒已有窗口）

## 4. 数据流：三条路径并存（重要）

| | 路径 A：UI | 路径 B：AI / TG | 路径 C：外部修改 |
|---|---|---|---|
| 入口 | Panel 直接调 Model（如 `dm.courses.update_course(...)`） | `scripts/actions.py` 命令 | 其它进程（TG bot）写文件 |
| 持久化 | `model.save()` → `atomic_write()` | 脚本内 `open()/json.dump()` **直接写** | —— |
| 通知 | `dm.data_changed.emit("<域>")` | `InstructionParser.execute` 调 `dm.reload_all()` + `emit("ai_action")` | `DataManager._auto_reload` 每 3s 比对 mtime（差 >0.1s）→ `reload()` + `emit("external")` |

**`data_changed(str)` 参数约定**：域名字符串（`course` / `task` / `habit` / `exam` / `expense` / `plan` / `inventory`）
或特殊值 `external` / `ai_action` / `internal`。

**消费方**：
- `MainWorkspace._on_data_changed` —— 按子串匹配刷新面板（`"task" in action or is_ai`）
- `GitSync.on_data_changed` —— 启动 30s 防抖计时，随后 `git add data/*.json && commit && push`
- `ReminderService._on_data_changed` —— 仅当 `"task" in action` 时重算 DDL 计数

> ⚠ **架构债**：路径 A 与 B 是**两套真值来源**（Model 内存态 vs 磁盘文件），靠 3s 轮询"对账"。
> 见 `CODE_STANDARDS Q-E2`、`PLAN B-*`。

## 5. 跨模块信号总览

| 发射者 | 信号 | 接收者 | 作用 |
|---|---|---|---|
| `ReminderService` | `reminder_notify(str,str)` | `App._show_reminder_notify` | 托盘通知 |
| `ReminderService` | `ddl_alert(int)` | `App._on_ddl_alert` → `MainWindow.set_ddl_alert` | DDL 计数 + 托盘闪烁 |
| `DataManager` | `data_changed(str)` | `GitSync` / `MainWorkspace` / `ReminderService` | 数据变更广播 |
| `GitSync` | `sync_status(str)` | `App._on_sync_status` | 托盘 tooltip |
| `AIService` | `response_received(str)` | `MainWindow._on_ai_response` | AI 文本回复 |
| `AIService` | `error_occurred(str)` | `MainWindow._on_ai_error` | AI 错误 |
| `AIService` | `instructions_executed(str,list)` | `MainWindow._on_instructions_done` | 指令执行结果 |
| `ScheduleView` | `arrange_requested(str)` | `MainWindow._on_quick_arrange` | 快速安排 prompt |
| `ScheduleView` | `course_table_requested` / `task_focus_requested(str)` | `MainWorkspace` | 日/周 切换通知 / 跨面板跳转 |
| `Sidebar` | `nav_changed(str)` / `ai_toggled(bool)` | `MainWindow` | 导航 / AI 面板开关 |
| `CourseTable` | `fill_ai_prompt(str)` | `MainWindow._on_course_fill_ai` | 右键填充 AI 提示词 |
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
| `QThread` + `AIWorker` | `services/ai_service.py` | AI 请求 + Agent Loop（最多 5 轮）+ 执行指令 |
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
- ✅ **系统提示词构建不再同步发网络请求**：余额/天气缓存改由一次性守护线程预热
  （`AIService._warm_context_cache`），`_build_system_prompt` 只读缓存；预热不触碰主线程属主的 `WeatherService`
- 🔄 `actions.run_in_process` 仍用 `contextlib.redirect_stdout`（已加锁串行化；彻底修复需 handler 返回字符串）

## 7. 关键不变量

1. **单例**：`SettingsManager` / `DataManager` / `AIService` 只在 `App.__init__` 实例化（`CODE_STANDARDS`/`AGENTS.md` R-001）。
2. **原子写入**：所有持久化走 `BaseJsonModel.atomic_write()`——写 `.tmp` → 备份 `.bak` → `os.replace`（PermissionError 重试 5×50ms）。
   AI 那条路径（`scripts/actions_core.save()`）同样原子：结构守卫 → 写前备份到
   `data/backup/actions/` → `.tmp` → 回读自检 → `os.replace`（`ERRORS #042`）。
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
8. **提醒出口单一**：所有提醒（托盘 / 邮件）都走 `ReminderService._notify()`，
   受设置 `General/reminder_enabled` 总开关控制（默认开）；"什么算命中"是**纯函数**
   （`services/reminder_rules.py`）。规则：点名课前 30 分钟、作业 3 天内 + 6 小时内、
   考试 14/7/3 天、习惯提前 5 分钟、余额低于阈值、用户在日程里定的自定义提醒。
8. **课程时段规则单一**：`models/course_rules.py`（`is_active_week` / `slots_of` /
   `conflicts_by_cell`）。`time_slots` 的 `end` 是**闭区间**；**同一时段允许两门课**，
   冲突要检出并提示请假（见 `ERRORS #038`）。
9. **按学期分文件**：课程表 / 作业 / 考试各自在 `data/semesters/<当前学期>/` 下，
   "有什么 / 记账 / 习惯 / 日程计划"跨学期共享（用户口径）。
   切学期**只能**走 `DataManager.switch_semester()` —— 它把三个模型重定向到新文件；
   直接改 `semesters.json` 的指针不会换数据（`ERRORS #040`）。
   旧布局由 `semester_paths.migrate_legacy()` 一次性迁移（先写新文件、校验、再删旧文件）。
10. **`data/` 是用户数据**（含密钥 `settings.ini`），不进发行版（`Q-P2`）。

## 8. 数据文件 schema 总表

**布局（按学期分文件）**：

```
data/
├── semesters.json                     学期注册表：semesters[] + current_semester（共享）
├── semesters/<学期id>/
│   ├── courses.json                   该学期课程表（含 holidays）
│   ├── tasks.json                     该学期作业
│   └── exams.json                     该学期考试
├── habits.json / expenses.json / inventory.json / daily_logs.json    跨学期共享
└── search_index.json / weather_*.json / scenes_meta.json             派生或遗留
```

> 路径解析**只有一处**：`models/semester_paths.resolve()`（应用、`actions.py`、`send_digest.py`、
> `build_index.py`、测试助手都调它）。切学期必须走 `DataManager.switch_semester()`
> —— 它会把 `courses/tasks/exams` **重定向**到新学期的文件（`ERRORS #040`）。

| 文件 | `_version` | 顶层键 | 关键字段 |
|---|---|---|---|
| `semesters.json` | 1 | `semesters[]` `current_semester` | semester: `id,name,start_date(YYYY-MM-DD),total_weeks(1-30，默认 16),exam_weeks(0-6，默认 1),period_count(1-12)` |
| `semesters/<id>/courses.json` | 1 | `courses[]` `holidays{excluded[],makeup{}}` | course: `id,name,teacher,day_of_week(1-7),weeks{start,end},time_slots[{start,end,location}],week_parity(all/odd/even),excluded_weeks[],notes` |
> `time_slots` 的 `end` 是**闭区间**：单节连堂写 `{"start": 1, "end": 1}`。
> **同一时段允许两门课**（选修过多 / 重修）→ 由 `course_rules.conflicts_by_cell()` 检出并提示请假（`ERRORS #038`）。
> **会点名的课**在 `course["reminders"]`：`{"attendance": bool, "lead_minutes": 30}`——
> 由课程右键菜单开关（界面不猜哪门课点名，只有用户知道），`reminder_rules.attendance_due()` 据此在开课前提醒。
| `semesters/<id>/tasks.json` | 2 | `tasks[]` `archived[]` | task: `id,title,course_name,due_date,status(pending/completed),priority,tags[],notes,created_at,completed_at,reminded` |
| `semesters/<id>/exams.json` | 1 | `exams[]` | exam: `id,course_name,exam_date,scope,location,notes,tags[],created_at,updated_at` |
| `habits.json` | 2 | `habits[]` `attached_task_templates[]` `logs{date:{hid:{completed,completed_at,note}}}` | habit: `id,name,schedule{type(daily/weekly/monthly/interval),days[],value,times_per_day,start_date},duration_minutes,reminder_time,streak,longest_streak,postpone_until,canceled_on[]` |
| `expenses.json` | 1 | `categories[{id,name}]` `budget{monthly,by_category}` `records[]` | record: `id,amount,date,category,note,created_at` |
| `daily_logs.json` | 4 | `logs{}` `plans{date:[...]}` `savings{date:[...]}` `reminders[]` | plan: `title,time_slot(1-6),type(custom/course_note),note,course_name,created_at`；reminder: `id,item_type,item_name,item_date,notify_time` |
| `inventory.json` | 1 | `items[]` `categories[]` | item: `id,name,category,group,quantity,unit,status(充足/不足/需购),min_quantity,location,notes,tags[],instances[],doses_per_unit` |
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

## 10. 已知架构债（指向权威清单）

| 债务 | 权威位置 |
|---|---|
| 双写路径（Model 内存态 vs 磁盘） | `CODE_STANDARDS Q-E2`、`PLAN B-*` |
| 线程安全（跨线程改 Model、类属性缓存、terminate） | `CODE_STANDARDS §B`、`PLAN P3-①` |
| 三套天气实现 | `CODE_STANDARDS Q-A3` |
| ID 生成两套并存（`len()+1` / max+1） | `CODE_STANDARDS Q-A1`/`Q-E2`、`PLAN` |
| 74 处盲捕获/静默吞异常 | `CODE_STANDARDS §I`、`PLAN P3-②` |
| 覆盖率 1% | `CODE_STANDARDS Q-F1`、`dev-logs/2026-10-15-现状基线.md` |
