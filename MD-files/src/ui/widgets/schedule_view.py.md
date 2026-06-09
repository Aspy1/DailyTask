### schedule_view.py

**职责**：展示单日或多日混合日程（课程、习惯、计划、DDL）。提供"快速安排"功能，利用 AI 重新规划日程，并支持撤销/保存。

**架构层级**：UI Layer（自定义控件）

**运行环境**：Windows，依赖 `PySide6.QtWidgets`

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `ScheduleView` | `DataManager` | 参数注入 | 数据访问（`self._dm`） |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| `_arrange_backup_path` | `daily_logs.json.bak` | AI 调整前的备份路径 |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self._dm` | `DataManager` | 数据访问 |
| `self._day_offset` | `int` | 当前显示的天数偏移 |
| `self._undo_btn` | `QPushButton` | 撤销按钮 |
| `self._save_btn` | `QPushButton` | 保存按钮 |
| `self._arrange_btn` | `QPushButton` | 调整按钮 |
| `self._date_label` | `QLabel` | 日期标签 |
| `self._content` | `QWidget` | 内容容器 |
| `self._content_layout` | `QLayout` | 内容布局 |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|---|
| `course_table_requested` | `Signal()` | — | 请求切换到课程表面板 |
| `task_focus_requested` | `Signal(str)` | 点击 DDL 时触发 | `course_name` |
| `quick_adjust_requested` | `Signal(str)` | ⚠️ 已弃用/未使用（待核实） | — |
| `arrange_requested` | `Signal(str)` | 点击"调整"按钮时触发 | 构建好的日程快照 Prompt |

---

#### 函数合同

##### `__init__(dm, parent=None)`

- **前置条件**：`DataManager` 已初始化
- **核心逻辑**：存储引用 → 创建日期导航栏和内容区 → 调用 `_refresh()`
- **副作用**：创建 GUI 控件
- **返回值**：无

##### `_target_date()`（属性）

- **核心逻辑**：`date.today() + timedelta(days=self._day_offset)`
- **返回值**：当前目标日期

##### `_prev_day()` / `_next_day()` / `_go_today()`

- **核心逻辑**：调整 `_day_offset` → 调用 `_refresh()`
- **返回值**：无

##### `_build_snapshot(days=3) → str`

- **核心逻辑**：构建给 AI 看的上下文，包含：
  - DDL（红线标注）
  - 考试
  - 每日课程
  - 习惯
  - 已有计划
  - 空闲时段
- **返回值**：格式化后的字符串

##### `_quick_arrange()`

- **前置条件**：AI 服务已配置
- **核心逻辑**：
  1. 调用 `_build_snapshot` 生成 Prompt
  2. 备份文件：`shutil.copy2(daily_logs.json, daily_logs.json.bak)`
  3. 发送 `arrange_requested` 信号
  4. 禁用按钮，等待 AI 响应
- **副作用**：创建备份文件；修改按钮状态；emit 信号

##### `on_arrange_done(success, msg)`

- **前置条件**：由 `MainWindow` 在收到 AI 回复并执行 `actions.py` 后调用
- **核心逻辑**：
  - 成功：显示"撤销"和"保存"按钮
  - 失败：恢复按钮状态，弹窗报错
- **返回值**：无

##### `_undo_arrange()`

- **核心逻辑**：将 `daily_logs.json.bak` 覆盖回 `daily_logs.json`，并调用 `reload_all()`
- **副作用**：回滚数据文件
- **风险点**：如果备份文件不存在，操作失败

##### `_save_arrange()`

- **核心逻辑**：删除 `.bak` 文件，隐藏撤销/保存按钮
- **副作用**：删除备份文件

##### `_course_menu(pos)` / `_habit_menu(pos)` / `_plan_menu(pos)`

- **核心逻辑**：在指定位置弹出对应类型的右键菜单
- **返回值**：无

##### `_refresh()`

- **核心逻辑**：重新渲染日程内容（课程/计划/DDL）
- **返回值**：无

##### `refresh_theme()`

- **核心逻辑**：被动刷新，由全局主题切换信号触发
- **返回值**：无

##### `_add_email_reminder_dialog()`

- **核心逻辑**：弹出邮件提醒设置对话框
- **返回值**：无

##### `_remove_email_reminder()`

- **核心逻辑**：移除邮件提醒
- **返回值**：无

##### `_has_email_reminder() → bool`

- **核心逻辑**：查询是否已设置邮件提醒
- **返回值**：`bool`

---

#### 禁止做的事

**R-UI-ARRANGE-01：调整 prompt 禁用 JSON 格式**

`_quick_arrange` 的 prompt 必须输出 \`\`\`sh + python scripts/actions.py 命令。SYSTEM_PROMPT_BASE 全局约束 AI 输出 sh 块，JSON 格式会导致 `InstructionParser` 提取不到指令，日程不更新。

**R-UI-ARRANGE-02：勿在 _quick_arrange 中直接修改数据**

`_quick_arrange` 只生成 prompt 并发射信号。数据修改由 AI 通过 Worker Agent Loop 执行。直接修改会绕过备份/撤销机制。

- **严禁在 `_quick_arrange` 中直接修改 `daily_logs` 数据**：必须通过 `actions.py` 执行
- **严禁在没有备份的情况下覆盖 `daily_logs.json`**：必须先 `shutil.copy2` 创建 `.bak`

---

#### 决策记录

**DR-UI-ARRANGE-01：调整 prompt 使用 sh 而非 JSON 格式**

- **原因**：`SYSTEM_PROMPT_BASE` 全局约束 AI 输出 \`\`\`sh 代码块，`InstructionParser` 只提取 \`\`\`sh 块。JSON 格式与全局规则冲突导致输出不可解析。
- **位置**：`schedule_view._quick_arrange` L282-287
- **状态**：锁定

**DR-UI-002：使用 .bak 文件进行 AI 调整回滚**

- **原因**：AI 生成的计划可能不合理，用户需要一键回到调整前的状态。
- **位置**：`_quick_arrange` 和 `_undo_arrange`
- **状态**：锁定

---

#### 术语映射

| 术语 | 含义 | 位置 |
|---|---|---|
| 调整 / 快速安排 | Quick Arrange — 一键让 AI 为未来 N 天排日程 | `_quick_arrange` 按钮 |
| 快照 | Snapshot — 包含课程/DDL/考试/习惯/空闲时段的完整上下文文本 | `_build_snapshot` |
| 撤销/保存 | Undo/Save — 调整完成后出现的操作按钮 | `_undo_btn` / `_save_btn` |

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| 快速安排 | Quick Arrange / AI 调整 | `_quick_arrange` |
| 撤销调整 | Undo Arrange / 回滚 | `_undo_arrange` |
