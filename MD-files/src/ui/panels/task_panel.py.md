### task_panel.py

**职责**：以表格形式展示作业列表，支持按课程、时间、完成状态筛选，支持分页和 DDL 高亮。

**架构层级**：UI Layer（面板）

**运行环境**：Windows，依赖 `PySide6.QtWidgets`

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `TaskPanel.__init__` | `src.services.data_manager` | Import | 获取任务数据 |
| `TaskPanel.__init__` | `src.ui.styles.theme` | Import | 获取颜色 |
| `_parse_due` | `datetime` | Import | 解析截止日期 |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| `PAGE_SIZE` | `10` | 每页显示的任务数 |
| `TIME_BUCKETS` | `list` | 时间筛选器选项（今天、明天、本周等） |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self._dm` | `DataManager` | 数据管理器 |
| `self._page` | `int` | 当前页码 |
| `self._selected_courses` | `set[str]` | 选中的课程集合 |
| `self._time_bucket` | `str \| None` | 当前时间筛选桶 |
| `self._status_filter` | `str` | 状态筛选（pending/completed/all） |
| `self._highlight_ddl` | `bool` | 是否高亮 DDL |
| `self._table` | `QTableWidget` | 任务表格 |

---

#### 信号

无 Qt 信号，但调用 `self._dm.tasks.complete/uncomplete` 会触发 `DataManager` 的 `data_changed` 信号（参数为 `"internal"`）。


---

#### 函数合同

##### `_get_filtered()`

- **核心逻辑**：
  1. 若 `self._selected_courses` 非空，过滤 `course_name` 在集合中的任务
  2. 若 `self._time_bucket` 非空，调用 `_match_time_bucket` 过滤
  3. 若 `self._status_filter` 为 `pending`，过滤 `done=False`；为 `completed` 则过滤 `done=True`；为 `all` 则不限制
- **返回值**：过滤后的任务列表

##### `_match_time_bucket(due_str, bucket)`

- **核心逻辑**：判断给定的 `due_str` 是否属于 `bucket`（如 `"today"`, `"overdue"`）
- **返回值**：`bool`

##### `_refresh()`

- **核心逻辑**：清空表格 → 获取过滤后的任务 → 分页 → 逐行填充表格
- **分页逻辑**：`start = self._page * PAGE_SIZE`，`end = start + PAGE_SIZE`，仅渲染 `[start:end]` 区间的任务
- **特殊逻辑**：如果 `self._highlight_ddl` 为 `True` 且任务在 3 天内到期，使用 `QLabel` 和富文本显示红色高亮
- **返回值**：无

##### `_on_check(task_id, checked)`

- **核心逻辑**：调用 `self._dm.tasks.complete/uncomplete`，保存数据，emit `data_changed` 信号
- **副作用**：修改数据；触发信号

---

#### 禁止做的事

- **禁止在表格中直接修改 `tasks.json` 文件**：必须通过 `DataManager`
- **禁止使用 `toggled` 信号连接复选框**：必须使用 `clicked(bool)`（引用 R-008）

---

#### 决策记录

**DR-TASK-001：使用 QLabel 实现富文本高亮**

- **原因**：`QTableWidgetItem` 不支持部分文本着色，必须使用 `setCellWidget` 嵌入 `QLabel`。
- **位置**：`_refresh` 函数内
- **状态**：锁定

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| DDL 高亮 | `highlight_ddl` | `task_panel.py` |
| 时间筛选桶 | `time_bucket` | `task_panel.py` |
| 分页 | `_page` | `task_panel.py` |
| 任务表格 | `_table` | `task_panel.py` |
