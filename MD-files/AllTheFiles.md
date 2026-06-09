# AllTheFiles.md

> **R-000** Hermes Agent 只能浏览、评价、美化本文件使其符合 Markdown 规范；不得在未许可的状态下修改任何文本内容。用户许可修改时，必须保留原有文本并在修改处前面注明；添加内容时必须在添加处前面注明。

本文档是整个项目的权威参考——函数、变量、方法、调用顺序、加载顺序、import 关系、依赖关系。后续功能开发前必须查阅。凡出现在本文档的文件，代表我已亲自审查并注释过。

> 最后更新：2026-06-09

> ⚠️ **禁止清单**：见 [项目级禁止清单](#项目级禁止清单)

---

## 目录

### 项目级章节（独立于各个文件，只出现一次）

| 章节 | 内容 |
|---|---|
| [索引](#索引) | 全项目文件树 |
| [全局常量](#全局常量) | 跨文件共用的阈值、路径、颜色系统 |
| [初始化顺序](#初始化顺序) | 14 步严格启动序列 |
| [数据路径](#数据路径) | 路径 A (UI→DataManager) vs 路径 B (AI→actions.py) |
| [信号总览](#信号总览) | 跨文件信号：发射者→签名→接收者 |
| [术语映射](#术语映射) | 用户用语 ↔ 代码类名 ↔ JSON 文件 |
| [操作步骤清单](#操作步骤清单) | 新增面板/服务/模型的标准化流程 |
| [决策记录](#决策记录) | 关键设计选择及其理由 |
| [项目级禁止清单](#项目级禁止清单) | R-001 ~ R-008 架构红线与代码约束 |

### 文件详情（每个文件通用格式）

每个文件按以下模板编写（权威格式见 [FORMAT_SPEC.md](FORMAT_SPEC.md)）：

```
### <文件名>
**职责**：一句话
#### 跨文件引用矩阵
#### 文件级常量 / 约定
#### 类实例变量
#### 信号
#### 函数合同
#### 禁止做的事
#### 操作步骤清单
#### 术语映射
#### 决策记录
```

---

## 索引

> 图例：✓ = 已写文档  |  【已审】 = 用户审核通过  |  无标记 = 骨架待补

├── src/
│   ├── [app.py](#apppy)            # ✓ 【已审】 应用入口 · 托盘 · 单实例
│   ├── models/
│   │   ├── base.py                 # ✓ 【已审】 BaseJsonModel (原子写入)
│   │   ├── course.py               # ✓ 课程 · 学期 · 假期
│   │   ├── task.py                 # ✓ 作业 · DDL
│   │   ├── habit.py                # ✓ 日常 · 周期 · 打卡
│   │   ├── expense.py              # ✓ 支出 · 预算 · 余额
│   │   ├── exam.py                 # ✓ 考试 · 日期 · 范围
│   │   └── daily_log.py            # ✓ 日程计划 · 储蓄
│   ├── services/
│   │   ├── ai_service.py           # ✓ 【已审】 AI 对话 · sh 命令解析
│   │   ├── data_manager.py         # ✓ 【已审】 数据聚合 · 3s 自动 reload
│   │   ├── reminder_service.py     # ✓ 提醒 · 邮件 · DDL
│   │   ├── settings_manager.py     # ✓ 配置读写
│   │   ├── git_sync.py             # ✓ Git 自动同步
│   │   └── plugin_manager.py       # ✓ 插件加载
│   └── ui/
│       ├── main_window.py          # ✓ 主窗口 · 状态栏
│       ├── components/
│       │   ├── sidebar.py          #     手风琴侧边栏
│       │   ├── main_workspace.py   #     面板切换
│       │   ├── ai_panel.py         #     AI 助手聊天面板
│       │   └── function_tabs.py    #     功能标签
│       ├── panels/
│       │   ├── course_panel.py     # 【已审】 课程表 (周网格 7×6)
│       │   ├── task_panel.py       # 【已审】 作业 (三态筛选)
│       │   ├── exam_panel.py       # 【已审】 考试
│       │   ├── habit_panel.py      # 【已审】 日常 (卡片网格)
│       │   ├── expense_panel.py    # 【已审】 记账 (6 分类)
│       │   ├── settings_panel.py   # 【已审】 设置
│       │   └── plugins_panel.py    # 【已审】 插件管理
│       ├── widgets/
│       │   ├── schedule_view.py    # 【已审】 日程视图
│       │   ├── course_table.py     # 【已审】 课程表表格
│       │   └── course_detail_dialog.py     # 【已审】
│       └── styles/
│           └── theme.py            # 【已审】 设计令牌 · QSS
├── scripts/
│   ├── actions.py                  # ✓ 统一数据操作脚本
│   ├── build_index.py              # 模糊搜索索引生成
│   └── send_digest.py              # GitHub Actions 邮件摘要
├── plugins/pomodoro/               # 番茄钟插件
├── data/                           # JSON 数据文件
├── DESIGN_TOKENS.md                # 设计规范
├── 规划书.md                        # 开发规划
├── 接口文档.md                      # API 文档
└── 修改说明.md                      # 变更日志

---

## 全局常量

| 常量 | 值 | 作用域 |
|---|---|---|
| `DATA_DIR` | `../data` | JSON 数据目录 |
| `DDL_CRITICAL` | ≤3 天 | task_panel.py 红色阈值 |
| `DDL_WARNING` | ≤7 天 | task_panel.py 橙色阈值 |
| `EXAM_CRITICAL` | ≤7 天 | exam_panel.py 红色阈值 |
| `EXAM_WARNING` | ≤15 天 | exam_panel.py 橙色阈值 |
| `TRAY_FLASH_INTERVAL` | 800ms | app.py 托盘闪烁间隔 |
| `DATA_RELOAD_INTERVAL` | `3000` (ms) | `data_manager.py` 自动重载轮询间隔（见 R-005） |
| 颜色系统 | `get_colors()` → token 字典 | theme.py（见禁止清单 R-008） |
| `RESOURCES_DIR` | `{PROJECT_ROOT}/resources/` | 资源文件目录 |

---

## 初始化顺序

> 以下顺序不可颠倒。每个步骤的备注说明依赖关系。

| 步骤 | 操作 | 关键代码 | 备注 |
|------|------|----------|------|
| 1 | 单实例检测 | `QLocalSocket.connectToServer` | 若连接成功则退出 |
| 2 | 设置 AppID | `SetCurrentProcessExplicitAppUserModelID("LifeAssistant.StudentScheduler")` | Windows 任务栏图标归属 |
| 3 | 加载配置 | `SettingsManager.load()` | 读取 INI |
| 4 | 加载语言 | `i18n.load()` | 依赖 Settings |
| 5 | 初始化主题 | `init_theme()` | 加载 QSS |
| 6 | 同步自启 | `set_autostart()` | 写入注册表 |
| 7 | 初始化 DataManager | `DataManager(DATA_DIR)` | **核心枢纽** |
| 8 | 初始化 Services | `AIService`, `ReminderService`... | 依赖 DataManager |
| 9 | 初始化 PluginManager | `PluginManager()` | 扫描插件目录 |
| 10 | 初始化 MainWindow | `MainWindow()` | 依赖所有 Services |
| 11 | 启动定时器 | `ReminderService.start()` | UI 就绪后启动 |
| 12 | 设置托盘 | `_setup_tray()` | 依赖 MainWindow |
| 13 | 监听新实例 | `QLocalServer.listen()` | 用于唤醒 |
| 14 | 显示窗口 | `show()` | |

---

## 数据路径

项目有两条独立的数据操作路径，不可混用：

| | 路径 A (UI 操作) | 路径 B (AI / TG 操作) |
|---|---|---|
| 入口 | Panel 控件 → `DataManager.add_*()` | AI 解析 → `scripts/actions.py` 子进程 |
| 写入 | `DataManager` → JSON 文件 | `actions.py` → JSON 直接写入 |
| 通知 | `DataManager` 自动 emit `data_changed` | `DataManager` 每 3s 检测文件 mtime → 差异 > 0.1s 则重载 Model 并 emit `data_changed("external")` |
| 规则 | 见禁止清单 R-002 | 见禁止清单 R-002 |

配置路径：`%APPDATA%/StudentScheduler/settings.ini`（由 `SettingsManager` 处理）

资源路径：`{PROJECT_ROOT}/resources/`

> **注意**：`DataManager` 每 `DATA_RELOAD_INTERVAL`（3000ms）轮询一次文件 `mtime`。若检测到 `mtime` 变化且差值 **> 100ms**，则判定为外部修改并触发 `data_changed`。3000ms 是轮询间隔，100ms 是变化判定阈值——两者独立。若 `actions.py` 在同一秒内多次写入，需确保时间间隔 > 100ms，否则可能漏触发。

---

## 信号总览

| 发射者 | 信号签名 | 接收者 | 槽函数 | 作用 |
|---|---|---|---|---|
| `ReminderService` | `reminder_notify(str, str)` | App | `_show_reminder_notify` | 显示托盘通知 |
| `ReminderService` | `ddl_alert(int)` | App | `_on_ddl_alert` | 触发托盘闪烁 |
| `ScheduleView` | `arrange_requested(str)` | MainWindow | `_on_quick_arrange` | 发送快照 prompt 到 AI |
| `DataManager` | `data_changed(str)` | GitSync | `on_data_changed` | 触发 Git 提交 |
| `DataManager` | `data_changed(str)` | MainWindow → Panels | `refresh_*()` | 全局 UI 刷新 |

> **参数约定**（`data_changed(str)`）：
> - `"external"` — 文件被外部程序修改（`DataManager._auto_reload` 检测到 mtime 变化）
> - `"ai_action"` — AI 通过 `actions.py` 修改（`InstructionParser.execute` 触发）
> - `"internal"` — UI 直接调用 `DataManager` 方法修改
> - `"update_course"` / `"delete_course"` — 课程面板操作
> - `"exam"` — 考试面板操作
> - `"expense"` / `"saving"` — 记账面板操作
> - `"habit"` — 习惯面板操作
| `GitSync` | `sync_status(str)` | App | `_on_sync_status` | 更新托盘 Tooltip |
| `QLocalServer` | `newConnection()` | App | `_on_second_instance` | 唤醒窗口 |
| `AIService` | `response_received(str)` | `ai_panel.py` | 显示回复 | AI 回复文本（已剥离代码块） |
| `AIService` | `error_occurred(str)` | `ai_panel.py` | 显示错误 | 错误信息 |
| `AIService` | `instructions_executed(str, list)` | `ai_panel.py` | 显示结果 | 显示文本 + 指令列表 |

> 注：`QTimer → timeout() → _flash_tick` 为 app.py 内部信号，详见 app.py 函数合同。

---

## 术语映射

| 用户用语 | 代码/内部术语 | 所在文件 |
|---|---|---|
| 开机自启 | Auto-start / Registry Run | `app.py` |
| 托盘 / 右下角图标 | System Tray / Tray Icon | `app.py` |
| 单实例 | Single Instance Lock | `app.py` |
| 调整 / 快速安排 | Quick Arrange | `schedule_view.py` → `main_window.py` → `ai_service.py` |
| 同步 | Git Sync | `git_sync.py` |
| 提醒 / DDL | Reminder / Alert | `reminder_service.py` |
| 数据 / 数据管理 | DataManager | `data_manager.py` |
| AI 回复 | Assistant Message | `ai_service.py` |
| 指令 / 工具调用 | Shell Command | `ai_service.py` |
| 多轮对话 | Agent Loop | `ai_service.py` |
| 上下文压缩 | Context Compression | `ai_service.py` |
| 自动修正 | Self-Correction | `ai_service.py` |
| 上下文溢出 | Token Limit | `ai_service.py` |
| 原子写入 | Atomic Write | `base.py` |
| 版本迁移 | Version Migration | `base.py` |
| 数据保存 | `save()` / `atomic_write()` | `base.py` |
| 数据加载 | `load()` / `reload()` | `base.py` |
| 版本升级 | `migrate()` | `base.py` |
| 数据损坏恢复 | `.bak` 手动恢复 | `base.py` |
| 快速安排 | Quick Arrange / AI 调整 | `schedule_view.py` |
| 撤销调整 | Undo Arrange / 回滚 | `schedule_view.py` |

---

## 操作步骤清单

### 修改应用图标
1. 替换 `image.png`（推荐 256×256 或 512×512 PNG）
2. 若需修改兜底图标样式，编辑 `_make_icon` 中的绘制逻辑
3. 更新 `DESIGN_TOKENS.md` 记录颜色值

### 添加新的全局服务
1. 在 `src/services/` 下创建新类
2. 在 `App.__init__` 中按顺序初始化该服务
3. 连接必要的信号（如 `data_changed`）
4. 在 `App.quit()` 中确保资源释放

### 修改自启逻辑
1. 修改 `set_autostart` 函数
2. 确保 `App.__init__` 中调用了该函数
3. 测试注册表写入与删除

### 新增面板
1. 创建 `src/ui/panels/xxx_panel.py`，继承 `QWidget`
2. 在 `main_workspace.py` 的 `PANELS` dict 注册
3. 在 `sidebar.py` 对应的 `SECTION` list 添加条目
4. 更新本文件的索引和 README.md
5. commit + push

### 新增数据模型
1. 创建 `src/models/xxx.py`，继承 `BaseJsonModel`
2. 在 `data_manager.py` 初始化对应 Model 实例
3. 在 `data_manager.py` 添加 `add_*` / `update_*` / `delete_*` 方法
4. 更新 `scripts/actions.py` 支持对应操作
5. 更新本文件索引和 README.md

### 添加新的 AI 提供商
1. 实现 `AIProvider` 协议的 `chat` 方法
2. 在 `AIService._make_provider()` 中添加分支
3. 在 `SettingsManager` 中添加配置项
4. 更新 `SYSTEM_PROMPT_BASE` 命令说明

### 添加新的可执行指令
1. 在 `scripts/actions.py` 中实现新命令
2. 在 `SYSTEM_PROMPT_BASE` 的"可用命令"部分添加示例
3. 测试 `InstructionParser.parse` 是否能正确提取

### 修复数据损坏
1. 检查 `.json` 文件是否损坏（`JSONDecodeError`）
2. 查找同目录下的 `.bak` 备份文件
3. 手动将 `.bak` 复制为 `.json`
4. 重启应用触发 `load()`

---

## 决策记录

**DR-001：使用 QLocalServer 而非 QSharedMemory 做单实例锁**

- **原因**：`QSharedMemory` 在 Windows 崩溃后会残留锁，导致下次启动误判已有实例运行。
- **位置**：`App.__init__` — `QLocalServer` + `QLocalSocket`
- **状态**：锁定（不可回退）
**DR-UI-ARRANGE-01：调整 prompt 使用 sh 而非 JSON 格式**

- **原因**：`SYSTEM_PROMPT_BASE` 全局约束 AI 输出 ```sh 代码块，`InstructionParser` 只提取 ```sh 块。JSON 格式与全局规则冲突导致输出不可解析。
- **位置**：`schedule_view._quick_arrange` L282-287
- **状态**：锁定

**DR-UI-ARRANGE-02：response_received 经 _on_ai_response 中转（兜底检查）**

- **原因**：`_arrange_pending` 主清路径是 `_on_instructions_done`，但若 AI 无指令纯文本响应，需兜底路径清标记。
- **位置**：`main_window._connect_ai` L266-267 + `_on_ai_response`
- **状态**：锁定


**DR-002：QPushButton + QMenu 代替 QComboBox 做筛选**

- **原因**：`QComboBox` 的 `border-radius` 在 Windows PySide6 上产生角点，`QPushButton` 无此问题。
- **位置**：`task_panel.py`、`habit_panel.py`
- **状态**：锁定

**DR-003：Agent Loop 多轮执行，用户只看到最终自然语言**

- **原因**：避免终端原始 JSON 和 Shell 命令污染聊天界面。
- **位置**：`ai_service.py` — `AIWorker.run` + `AIService._on_response`
- **状态**：锁定

**DR-004：重启时复用 `sys.argv`**

- **原因**：确保新进程继承原进程的启动参数（如调试模式、特定配置文件路径），维持运行环境一致性。
- **位置**：`App._restart()` — `QProcess.startDetached(sys.executable, sys.argv)`

**DR-BASE-001**：`os.replace` 原子写入 — 防断电损坏。详见 `base.py.md`

**DR-BASE-002**：Windows Defender / Search Indexer 重试 5×50ms — 防 `PermissionError`。详见 `base.py.md`

**DR-BASE-003**：版本迁移框架 — `_version` + `migrate()`。详见 `base.py.md`

**DR-AI-001**：AI 指令通过 subprocess 执行（非直接函数调用）— 隔离风险。详见 `ai_service.py.md`

**DR-AI-002**：剥离代码块仅显示自然语言 — 用户体验。详见 `ai_service.py.md`

**DR-AI-003**：Agent Loop 限制最大 5 轮 — 成本控制。详见 `ai_service.py.md`

**DR-UI-001**：使用哈希确定课程颜色 — 避免随机变色。详见 `course_table.py.md`

**DR-SETTINGS-001**：插件窗口列表持有引用 — 防 GC 关闭。详见 `settings_panel.py.md`

**DR-TASK-001**：QLabel 富文本实现 DDL 高亮 — QTableWidgetItem 不支持。详见 `task_panel.py.md`

**DR-UI-002**：`.bak` 文件实现 AI 调整回滚 — 一键撤销。详见 `schedule_view.py.md`

**DR-AI-004**：Shell 指令超时设置为 30 秒 — 防止死锁。详见 `ai_service.py.md`

---

## 项目级禁止清单

**R-001：单例模式**

`SettingsManager`、`DataManager`、`AIService` 必须且仅能在 `App.__init__` 中实例化。任何子模块不得自行创建这些实例——`DataManager` 统一管理所有 Model，重复实例化将导致 Model 数据不同步。

**R-002：数据写入路径**

UI 写操作的唯一合法入口是 `DataManager.save_all()` 和各 Model 的 `save()` 方法。AI/TG 操作走 `scripts/actions.py` 路径。禁止直接使用 `open()` 或 `json.dump()` 写入 `data/*.json`。

**R-003：信号与槽类型匹配**

连接信号时必须确认参数类型一致。`ddl_alert(int)` 只能连接接收 `int` 的槽，不能使用无参槽函数处理。

**R-004：主线程安全**

`App.__init__` 及所有 UI 槽函数中禁止阻塞操作（`time.sleep`、同步网络请求、大文件遍历）。耗时操作必须放入 `QThread`。

**R-005：魔法数字**

禁止在代码中硬编码阈值。包括但不限于：

| 硬编码位置 | 值 | 待处理 |
|---|---|---|
| `App._on_ddl_alert` | 800ms 闪烁间隔 | 已文档化 |
| `AIWorker.run` | `temperature=0.3`, `max_tokens=4096` | 待迁移至 SettingsManager |
| `InstructionParser.execute` | `timeout=30` (秒) | 见 DR-AI-004 |
| `AIService._auto_compress` | 历史压缩阈值 16 条 | 待评估是否可配 |
| `theme.py` | `SIZE_CAPTION`, `SIZE_BODY` 等字体大小 | 待文档化 |

修改任何阈值需同步更新本文档。

**R-006：单实例逻辑不可改**

不要更改 `QLocalServer` 的 Key 或超时时间。

**R-007：托盘闪烁不可移除**

`_flash_timer` 和 `_on_ddl_alert` 是核心 UX 特性，不可移除。

**R-008：UI 代码约束**

- QSS 选择器：仅允许 `#objectName`，**禁止类名选择器**（Windows PySide6 不生效）
- QComboBox：**禁止 `border-radius`**（产生角点），筛选用 `QPushButton + QMenu` 代替
- 复选框信号：**禁止 `toggled`**，必须用 `clicked(bool)`（避免 `setChecked` 触发回环）
- 颜色：**禁止硬编码 hex**，必须通过 `get_colors()` 获取 token 字典，引用 `c['key']`
- f-string：`{c['key']}` 外层必须用双引号，QSS 花括号双写 `{{ }}`
- 动画：**禁止动画调试**，侧边栏用 `show()` / `hide()` 即时切换
- ID 生成：**禁止 `len() + 1`**，必须遍历现有 ID + archived 找最大编号 + 1
- 数据集操作：**禁止 LLM 直接修改结构化文件**（JSON/Markdown），必须通过脚本接口
- 字符串硬编码：UI 显示文本应通过 `i18n` / `tr()` 获取，**禁止硬编码中文**

---

## 文件详情

| 文件 | 文档 |
|---|---|
| `app.py` | [src/app.py.md](src/app.py.md) ✅ — 应用入口 · 托盘 · 单实例 |
| `data_manager.py` | [src/services/data_manager.py.md](src/services/data_manager.py.md) ✅ — 中央数据枢纽 |
| `ai_service.py` | [src/services/ai_service.py.md](src/services/ai_service.py.md) ✅ — AI 对话 · Agent Loop |
| `models/base.py` | [src/models/base.py.md](src/models/base.py.md) ✅ — 原子写入 · 版本迁移 |
| `models/course.py` | [src/models/course.py.md](src/models/course.py.md) — 课程 · 学期 · 假期 |
| `models/task.py` | [src/models/task.py.md](src/models/task.py.md) — 作业 · DDL |
| `models/habit.py` | [src/models/habit.py.md](src/models/habit.py.md) — 日常 · 打卡 |
| `models/expense.py` | [src/models/expense.py.md](src/models/expense.py.md) — 记账 · 预算 |
| `models/exam.py` | [src/models/exam.py.md](src/models/exam.py.md) — 考试 · 范围 |
| `models/daily_log.py` | [src/models/daily_log.py.md](src/models/daily_log.py.md) — 日程 · 储蓄 |
| `models/inventory.py` | [src/models/inventory.py.md](src/models/inventory.py.md) — 物品 · 库存 |
| `services/settings_manager.py` | [src/services/settings_manager.py.md](src/services/settings_manager.py.md) — 配置读写 |
| `services/reminder_service.py` | [src/services/reminder_service.py.md](src/services/reminder_service.py.md) — 提醒 · DDL |
| `services/git_sync.py` | [src/services/git_sync.py.md](src/services/git_sync.py.md) — Git 同步 |
| `services/plugin_manager.py` | [src/services/plugin_manager.py.md](src/services/plugin_manager.py.md) — 插件管理 |
| `main_window.py` | [src/ui/main_window.py.md](src/ui/main_window.py.md) — 主窗口 |
| `scripts/actions.py` | [scripts/actions.py.md](scripts/actions.py.md) — 统一 CLI |
| components / panels / widgets / styles / i18n | 骨架已生成（标记为*待补*） |

---

> **格式规范**：[FORMAT_SPEC.md](FORMAT_SPEC.md)
> **项目约束**：[AGENTS.md](../AGENTS.md)
