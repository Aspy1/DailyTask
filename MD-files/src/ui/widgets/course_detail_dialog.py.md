### course_detail_dialog.py

**职责**：展示特定课程在特定日期范围内的日程（Plans）和作业（Tasks），提供只读视图。

**架构层级**：UI Layer（对话框）

**运行环境**：Windows，依赖 `PySide6.QtWidgets`

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `CourseDetailDialog` | `DataManager` | 参数注入 | 数据访问（`self._dm`） |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| （无显式常量） | — | |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self._dm` | `DataManager` | 数据访问 |
| `self._course_name` | `str` | 当前查看的课程名称 |
| `self._today` | `date` | 当前日期 |
| `self._sched_list` | `QListWidget` | 日程列表控件 |
| `self._task_list` | `QListWidget` | 作业列表控件 |

---

#### 信号

无

---

#### 函数合同

##### `__init__(dm, course_name, today, parent=None)`

- **前置条件**：`DataManager` 已初始化
- **核心逻辑**：存储引用 → 创建两个 `QListWidget` → 调用 `_refresh()`
- **副作用**：创建 UI 控件
- **返回值**：无

##### `_refresh()`

- **前置条件**：`self._dm` 已加载，`self._course_name` 存在于数据中
- **核心逻辑**：分别遍历 `daily_logs.plans` 和 `tasks.active`，通过 `course_name` 字段进行过滤
- **副作用**：清空并重建两个 `QListWidget`
- **显示规则**：过去的日程标灰（`Qt.GlobalColor.gray`），完成的作业标灰
- **返回值**：无

##### `refresh_theme()`

- **核心逻辑**：重新应用当前主题样式
- **注意**：被动刷新，通常由全局主题切换信号触发
- **返回值**：无

---

#### 禁止做的事

- **禁止直接修改数据**：不得在此对话框中直接修改 `tasks` 或 `plans` 的状态（如勾选完成），应通过 Signal 通知上级处理

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| *（待补）* | | |
