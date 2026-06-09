### course_panel.py

**职责**：课程表面板 — 周视图课程表，支持翻周、重命名课程、删除课程

**架构层级**：UI Layer（面板）

**运行环境**：Windows

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `CoursePanel` | `src.services.data_manager` | Import | 课程数据 |
| `CoursePanel` | `src.ui.styles.theme` | Import | 颜色和字体 |
| `CoursePanel` | `src.ui.widgets.course_table` | Import | 课程表表格控件 |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| （无显式常量） | — | |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self._dm` | `DataManager` | 数据管理器 |
| `self._week_label` | `QLabel` | 周次标签 |
| `self._table` | `CourseTable` | 课程表表格控件 |
| `self._count_label` | `QLabel` | 课程数量标签 |
| `self._current_week_offset` | `int` | 当前周偏移量 |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|---|
| `DataManager.data_changed` | `Signal(str)` | 课程增删改后 | `"update_course"` 或 `"delete_course"` |

---

#### 函数合同

##### `_week_number()`（属性）

- **核心逻辑**：根据学期开始日期计算当前周次：`(today - start_date).days // 7 + 1`
- **返回值**：`int`

##### `_prev_week()` / `_next_week()`

- **核心逻辑**：调整 `_current_week_offset` → 刷新课程表
- **返回值**：无

##### `_go_today()`

- **核心逻辑**：重置偏移为 0 → 刷新课程表
- **返回值**：无

##### `_rename_course(course_id, new_name)`

- **核心逻辑**：调用 `self._dm.courses` 更新课程名 → 保存 → emit `"update_course"`
- **副作用**：修改数据；触发信号

##### `_delete_course(course_id)`

- **核心逻辑**：调用 `self._dm.courses` 删除课程 → 保存 → emit `"delete_course"`
- **副作用**：删除数据；触发信号

##### `_refresh()`

- **核心逻辑**：重载课程数据 → 更新表格和计数标签
- **返回值**：无

---

#### 禁止做的事

- **禁止绕过 DataManager 修改课程数据**：所有增删改通过 `self._dm.courses` 方法

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| 周次 | `_week_number` | `course_panel.py` |
| 课程表 | `CourseTable` | `course_table.py` |
