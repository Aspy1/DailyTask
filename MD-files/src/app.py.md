### app.py

**职责**：应用入口、生命周期管理、单实例锁、系统托盘、服务编排

**架构层级**：Application Layer（入口）

**运行环境**：Windows（主要），Python 3.9+

**依赖概述**：`App.__init__` 是整个文件的依赖中枢，编排所有 Service / Manager / Window 类。

**系统与环境依赖**：`QLocalServer` / `QLocalSocket`（单实例锁）、`ctypes.windll.shell32`（Windows 任务栏 ID）

**服务与数据层**：`SettingsManager` → `DataManager` → `AIService` → `ReminderService` → `GitSync` → `PluginManager`

**UI 层**：`init_theme`（样式）、`MainWindow`（主窗口）

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `App.__init__` | `src.services.settings_manager` | Import | 配置读写 |
| `App.__init__` | `src.services.data_manager` | Import | 数据聚合 |
| `App.__init__` | `src.ui.main_window` | Import | UI 容器 |
| `App._setup_tray` | `PySide6.QtWidgets.QMenu` | Import | 托盘菜单 |
| `App._restart` | `PySide6.QtCore.QProcess` | Import | 进程重启 |
| `set_autostart` | `winreg` | Import | 注册表操作 |
| `_make_icon` | `PySide6.QtGui.QPainter` | Import | 绘图 |
| 模块级 | `src.i18n.loader` | `from ... import t as i18n, tr` | 界面文本国际化（`tr("app.name")` 等） |

#### 文件级常量

| 常量 | 值 | 说明 |
|---|---|---|
| `DATA_DIR` | `../data` | JSON 数据目录（见 [全局常量](#全局常量)） |
| `SINGLE_INSTANCE_KEY` | `StudentSchedulerSingleInstance` | LocalServer 管道名 |
| `APP_REGISTRY_NAME` | `StudentScheduler` | 注册表项名称 |
| `REGISTRY_RUN_KEY` | `...\Run` | 开机自启路径 |
| `_ICON_PATH` | `../image.png` | 首选图标路径 |

| `_RESOURCES_DIR` | `{PROJECT_ROOT}/resources/` | 资源文件目录 |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self.is_secondary` | `bool` | 标记是否为第二个实例（拦截重复启动） |
| `self._icon_normal` | `QIcon` | 普通状态托盘图标（蓝色） |
| `self._icon_alert` | `QIcon` | 警示状态托盘图标（红色 #e74856） |
| `self._ddl_count` | `int` | 当前紧急 DDL 数量 |
| `self._flash_timer` | `QTimer` | 托盘闪烁定时器（800ms 间隔） |
| `self._flash_on` | `bool` | 闪烁状态交替标记 |
| `self._window` | `MainWindow` | 主窗口引用 |
| `self._instance_server` | `QLocalServer` | 单实例监听服务器 |
| `self._plugin_manager` | `PluginManager` | 插件管理器实例 |
| `self._settings` | `SettingsManager` | 配置读写（全局单例，禁止外部实例化） |
| `self._data_manager` | `DataManager` | 数据核心（全局单例，禁止外部实例化） |
| `self._ai_service` | `AIService` | AI 逻辑（全局单例，禁止外部实例化） |
| `self._reminder` | `ReminderService` | 提醒服务 |
| `self._git_sync` | `GitSync` | Git 自动同步 |
| `self._tray` | `QSystemTrayIcon` | 系统托盘图标 |

---

#### 信号连接（`__init__` 内）

| 信号发射者 | 连接代码 | 接收槽 |
|---|---|---|
| `self._reminder` | `.reminder_notify.connect(self._show_reminder_notify)` | 托盘消息通知 |
| `self._reminder` | `.ddl_alert.connect(self._on_ddl_alert)` | DDL 预警闪烁 |
| `self._data_manager` | `.data_changed.connect(self._git_sync.on_data_changed)` | 数据变更触发同步 |
| `self._git_sync` | `.sync_status.connect(self._on_sync_status)` | 同步状态回传托盘 |
| `self._flash_timer` | `.timeout.connect(self._flash_tick)` | 闪烁动画 |
| `self._instance_server` | `.newConnection.connect(self._on_second_instance)` | 新实例唤醒 |
| `self._tray` | `.activated.connect(self._on_tray_activated)` | 托盘左键单击 |

---

#### 函数合同

##### `_get_startup_command() → str`

- **前置条件**：无
- **核心逻辑**：构建用于自启的命令行字符串。优先使用 `pythonw.exe`（无控制台窗口），若不存在则回退 `sys.executable`
- **返回值**：`"pythonw.exe" "main.py"` 或 `"python.exe" "main.py"` 格式的完整命令行
- **副作用**：无（纯计算）
- **调用者**：`set_autostart()`

##### `set_autostart(enabled: bool)`

- **前置条件**：Windows 平台；具有注册表当前用户项的写权限
- **核心逻辑**：
  1. 打开 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
  2. 若 `enabled=True`，写入 `_get_startup_command()` 返回值
  3. 若 `enabled=False`，尝试删除名为 `StudentScheduler` 的值
- **副作用**：修改系统注册表
- **返回值**：`None`
- **异常行为**：捕获 `OSError` 静默失败，不弹窗，不中断启动

##### `__init__(args: list[str])`

- **前置条件**：必须是第一个应用实例
- **核心逻辑**：见 [初始化顺序](#初始化顺序) 14 步序列
- **副作用**：创建所有全局单例（`SettingsManager`、`DataManager`、`AIService`、`ReminderService`、`GitSync`、`PluginManager`、`MainWindow`）
- **返回值**：无（构造函数）
- **异常行为**：若单实例检测到已有实例运行，设置 `self.is_secondary = True` 并立即 `return`，不创建任何资源

##### `_make_icon(color: str = "#007acc") → QIcon`

- **前置条件**：无
- **核心逻辑**：
  1. 检查 `image.png` 是否存在
  2. 若存在，缩放至 48×48 并返回 `QIcon`
  3. 若不存在，创建 64×64 的 `QPixmap`（透明背景），使用 `QPainter` 绘制：
     - 圆角矩形：坐标 `(4, 4)`，大小 `56×56`，圆角半径 `12px`
     - 中心字符 `"S"`：字体 `SimHei 28pt bold`，白色 `#ffffff`
  4. 返回 64×64 的 `QIcon`（Qt 会自动按需缩放）
- **返回值**：`QIcon` 对象
- **约定**：兜底图标 64×64 原始尺寸（Qt 自动缩放），外部图标缩放到 48×48（Windows 任务栏最佳尺寸）

##### `_on_ddl_alert(count: int)`

- **前置条件**：`_flash_timer` 已初始化；`_window` 已存在
- **核心逻辑**：
  ```python
  self._ddl_count = count
  self._window.set_ddl_alert(count)
  if count > 0:
      if not self._flash_timer.isActive():
          self._flash_timer.start(800)
  else:
      self._flash_timer.stop()
      self._tray.setIcon(self._icon_normal)
  ```
- **副作用**：启动或停止定时器；修改托盘图标；调用 `MainWindow.set_ddl_alert()`
- **返回值**：`None`
- **信号来源**：接收自 `ReminderService` 的 `ddl_alert(int)` 信号

##### `_flash_tick()`

- **前置条件**：`_flash_timer` 正在运行
- **核心逻辑**：
  ```python
  self._flash_on = not self._flash_on
  if self._flash_on:
      self._tray.setIcon(self._icon_alert)   # 红色警示图标
  else:
      self._tray.setIcon(self._icon_normal)  # 蓝色普通图标
  ```
- **副作用**：切换托盘图标样式
- **返回值**：`None`

##### `_show_reminder_notify(title: str, body: str)`

- **前置条件**：无（防御式检查内置）
- **核心逻辑**：
  1. `hasattr(self, "_tray")` 检查托盘是否已创建
  2. `self._tray.supportsMessages()` 检查系统是否支持通知
  3. 两项均满足时调用 `_tray.showMessage(title, body, Information, 8000)` 显示 8 秒托盘通知
- **防御设计**：即使信号在 `_tray` 创建前到达也不会崩溃
- **副作用**：弹出系统通知气泡
- **返回值**：`None`
- **信号来源**：接收自 `ReminderService.reminder_notify(str, str)`

##### `_manual_sync()`

- **前置条件**：`_git_sync` 已初始化
- **核心逻辑**：调用 `self._git_sync.sync_now()` 立即触发同步
- **副作用**：可能触发 `sync_status` 信号
- **返回值**：`None`

##### `_on_sync_status(status: str)`

- **前置条件**：`_tray` 已创建
- **核心逻辑**：根据 4 种状态更新托盘 Tooltip 和通知：

  | 状态 | Tooltip | 额外操作 |
  |---|---|---|
  | `syncing` | `应用名 — 同步中...` | |
  | `done` | `应用名 — 已同步 ✓` | 弹出"同步完成"通知 |
  | `idle` | `应用名` | |
  | `error`（前缀匹配） | `应用名 — 同步失败` | `status.startswith("error")`（如 `error: network failed`） |

- **副作用**：修改托盘 Tooltip；`done` 状态时弹出通知气泡
- **返回值**：`None`
- **信号来源**：接收自 `GitSync.sync_status(str)`

##### `_bring_to_front()`

- **前置条件**：`_window` 已创建
- **核心逻辑**：
  1. 若窗口最小化 → `showNormal()`
  2. `show()` + `raise_()` + `activateWindow()` 确保窗口置顶激活
- **副作用**：恢复并激活窗口
- **返回值**：`None`

##### `_setup_tray(icon: QIcon)`

- **前置条件**：`_window` 已创建（菜单项需要触发窗口操作）
- **核心逻辑**：构建托盘菜单（显示/隐藏/同步到 GitHub/重启/退出），连接 `activated` 信号，显示托盘图标
- **副作用**：创建系统托盘图标和右键菜单
- **返回值**：`None`

##### `_on_tray_activated(reason)`

- **前置条件**：托盘图标已显示
- **核心逻辑**：仅响应 `QSystemTrayIcon.ActivationReason.Trigger`（左键单击），调用 `_bring_to_front()`
- **副作用**：激活主窗口
- **返回值**：`None`
- **说明**：不处理双击（`DoubleClick`）和中键（`MiddleClick`）

##### `_restart()`

- **前置条件**：无
- **核心逻辑**：
  1. 调用 `save_all()` 持久化数据
  2. 关闭 `QLocalServer` 释放端口锁
  3. 使用 `QProcess.startDetached` 启动新 Python 进程（复用当前 `sys.executable` 和 `sys.argv`，见 DR-004）
  4. 调用 `self.quit()` 结束当前进程
- **副作用**：进程替换
- **返回值**：`None`

##### `_on_second_instance()`

- **前置条件**：`_instance_server` 已监听
- **核心逻辑**：
  1. 从 `_instance_server` 获取待处理连接
  2. 断开 socket 连接
  3. 在 `finally` 块中调用 `sock.deleteLater()` 释放 socket 对象
  4. 调用 `_bring_to_front()` 唤醒主窗口
- **副作用**：释放 socket 资源；激活最小化窗口
- **返回值**：`None`
- **资源释放**：必须在 `finally` 块中调用 `deleteLater()`，防止 Qt 对象句柄泄漏

##### `quit()`

- **前置条件**：无
- **核心逻辑**：保存数据 → 关闭窗口 → 退出事件循环
- **副作用**：保存数据，关闭窗口，退出事件循环
- **返回值**：`None`

---