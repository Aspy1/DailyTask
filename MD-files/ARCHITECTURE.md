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
| AI | DeepSeek / Anthropic（可切换），Agent Loop 多轮 |
| 数据操作 | `scripts/actions.py`（CLI + 内存调用） |
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
**已知违规**：`src/services/api_service.py:10` `import src.ui.styles.theme`（服务层反向依赖 UI 层）→ `CODE_STANDARDS Q-A2`。

## 3. 启动顺序（实际，`src/app.py:App.__init__`）

> ⚠ 旧的 `AllTheFiles.md` 记录的是另一套顺序，与当前代码不符；**以本节为准**。

1. 单实例探测：`QLocalSocket.connectToServer` → 成功则 `is_secondary=True` 直接返回
2. `setApplicationName`、`setQuitOnLastWindowClosed(False)`
3. Windows：`SetCurrentProcessExplicitAppUserModelID`（任务栏图标归属）
4. 构建图标（`_make_icon`，可选 `resources/image.png`）
5. `SettingsManager(DATA_DIR/"settings.ini").load()`
6. `i18n.load(language)`
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
| `ScheduleView` | `course_table_requested` / `task_focus_requested(str)` | `MainWorkspace` | 跨面板跳转 |
| `Sidebar` | `nav_changed(str)` / `ai_toggled(bool)` | `MainWindow` | 导航 / AI 面板开关 |
| `CourseTable` | `fill_ai_prompt(str)` | `MainWindow._on_course_fill_ai` | 右键填充 AI 提示词 |
| `WeatherService` | `weather_updated(dict)` / `forecast_updated(list)` | `MainWindow` / `WeatherDetailDialog` | 天气刷新 |
| `QLocalServer` | `newConnection` | `App._on_second_instance` | 第二实例唤醒 |

## 6. 并发模型

| 线程载体 | 位置 | 职责 |
|---|---|---|
| `QThread` + `AIWorker` | `services/ai_service.py` | AI 请求 + Agent Loop（最多 5 轮）+ 执行指令 |
| `QThread`(`WeatherWorker`) | `services/weather_service.py` | 和风天气 HTTP |
| `QThread`(`_GitWorker`) | `services/git_sync.py` | `git add/commit/push` 子进程 |
| `QThread`(`_ApiWorker`) | `services/api_service.py` | Open-Meteo / DeepSeek 余额 |

**主线程定时器**：`DataManager._auto_reload`（3s，比对 7 个文件 mtime）、`ReminderService._check`（60s）、
`MainWindow._status_timer`（30s）、`WeatherService` 自动更新（10min / 1min 轮询）。

**已知线程安全问题**（见 `CODE_STANDARDS §B`）：
- `AIWorker` 在工作线程里调 `dm.reload_all()` 直接改 Model 内存态，主线程同时在读 → 竞态（`Q-B2`）
- `ai_service` 的余额/天气缓存是**类属性**（跨实例共享可变状态，`Q-B2`）
- `actions.run_in_process` 用 `contextlib.redirect_stdout`（进程级全局，`Q-B4`）
- `api_service` 用 `QThread.terminate()`（`Q-B3`）
- `QThread` 反复 `new` 不 `deleteLater`（`Q-B5`）

## 7. 关键不变量

1. **单例**：`SettingsManager` / `DataManager` / `AIService` 只在 `App.__init__` 实例化（`CODE_STANDARDS`/`AGENTS.md` R-001）。
2. **原子写入**：所有持久化走 `BaseJsonModel.atomic_write()`——写 `.tmp` → 备份 `.bak` → `os.replace`（PermissionError 重试 5×50ms）。
   **注意**：`scripts/actions.py` 不走这条路径，直接 `open()/json.dump()`。
3. **显式保存**：Model 改内存态后**不会自动落盘**，必须显式 `save()`。
4. **日期语义**：`course.schedule_date()` —— **0:00–1:00 视为前一天**；跨模块统一用它，不要直接用 `date.today()`。
5. **时区**：全部本地时间，无 tz 处理；`due_date` 形如 `YYYY-MM-DDThh:mm:ss`，日期型为 `YYYY-MM-DD`。
6. **ID 生成**：**目前有两套**（`len()+1` 与 max+1 并存），见下节债务。
7. **`data/` 是用户数据**（含密钥 `settings.ini`），不进发行版（`Q-P2`）。

## 8. 数据文件 schema 总表

| 文件 | `_version` | 顶层键 | 关键字段 |
|---|---|---|---|
| `courses.json` | 3 | `semesters[]` `current_semester` `courses[]` `holidays{excluded[],makeup{}}` | course: `id,name,teacher,day_of_week(1-7),weeks{start,end},time_slots[{start,end,location}],week_parity(all/odd/even),notes` |
| `tasks.json` | 2 | `tasks[]` `archived[]` | task: `id,title,course_name,due_date,status(pending/completed),priority,tags[],notes,created_at,completed_at,reminded` |
| `habits.json` | 2 | `habits[]` `attached_task_templates[]` `logs{date:{hid:{completed,completed_at,note}}}` | habit: `id,name,schedule{type(daily/weekly/monthly/interval),days[],value,times_per_day,start_date},duration_minutes,reminder_time,streak,longest_streak,postpone_until,canceled_on[]` |
| `exams.json` | 1 | `exams[]` | exam: `id,course_name,exam_date,scope,location,notes,tags[],created_at,updated_at` |
| `expenses.json` | 1 | `categories[{id,name}]` `budget{monthly,by_category}` `records[]` | record: `id,amount,date,category,note,created_at` |
| `daily_logs.json` | 4 | `logs{}` `plans{date:[...]}` `savings{date:[...]}` `reminders[]` | plan: `title,time_slot(1-6),type(custom/course_note),note,course_name,created_at`；reminder: `id,item_type,item_name,item_date,notify_time` |
| `inventory.json` | 1 | `items[]` `categories[]` | item: `id,name,category,group,quantity,unit,status(充足/不足/需购),min_quantity,location,notes,tags[],instances[],doses_per_unit` |
| `scenes_meta.json` | — | `current_scene` `scenes{}` | scene: `id,name,scene_type,description,location{lat,lon}` |
| `settings.ini` | — | `General` `AI` `Semester` `Window` `Backup` `Email` `Balance` `Weather` | 含密钥，**gitignore** |
| `weather_cache.json` / `weather_stats.json` / `search_index.json` | — | 派生/缓存 | 易变，非权威 |

## 9. 扩展点

- **新增面板**：`src/ui/panels/xxx_panel.py` → `ui/components/main_workspace.py` 的 `PANELS` 注册 → `ui/components/sidebar.py` 加入条目 → 更新 `README.md`。
- **新增数据模型**：`src/models/xxx.py`（继承 `BaseJsonModel`）→ `DataManager.__init__` 实例化 → 若要 AI 可操作，补 `scripts/actions.py` 命令。
- **新增 AI 命令**：`scripts/actions.py`（handler + argparse + `run_in_process` 的 handler/`_defaults`）→ `SYSTEM_PROMPT_BASE` → TG skill。**三处必须一致**，由 `tests/test_prompt_consistency.py` 把关。
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
