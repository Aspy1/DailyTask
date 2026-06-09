### daily_log.py

**职责**：日程计划、时间槽、储蓄管理

**架构层级**：Model Layer

**继承**：`BaseJsonModel` — 原子写入、版本迁移机制见 `base.py.md`

**运行环境**：跨平台，无外部依赖

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `DailyLogModel` | `src.models.base` | Import | 继承 `BaseJsonModel` |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| （无显式常量） | — | 继承 `BaseJsonModel` 的 `.tmp`/`.bak` 约定 |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self.file_path` | `Path` | JSON 文件路径（继承自 `BaseJsonModel`） |
| `self._data` | `dict` | 全量数据字典（继承自 `BaseJsonModel`） |

---

#### 信号

无（Model 层不继承 `QObject`）

---

#### 函数合同

##### `__init__(self, file_path: Path, default_data=None)`

- **前置条件**：无（由 DataManager 传入 file_path）
- **核心逻辑**：调用 `super().__init__(file_path, default_data)` 委托给 `BaseJsonModel`
- **副作用**：可能创建 JSON 文件或读取磁盘
- **返回值**：无
##### `get_log(self, day: str | None = None) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `set_log(self, day: str, log: dict) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `is_logged_today(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `today(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `get_plans(self, day: str | None = None) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `add_plan(self, plan: dict, day: str | None = None) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `get_today_plans(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `delete_plan(self, day: str, index: int) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `get_savings(self, day: str | None = None) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `add_saving(self, amount: float, note: str = "", day: str | None = None) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `delete_saving(self, day: str, index: int) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `today_savings_total(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `add_reminder(self, item_type: str, item_name: str, item_date: str, notify_time: str) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `get_reminders(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `delete_reminder(self, reminder_id: str) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `find_reminder(self, item_type: str, item_name: str, item_date: str) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `delete_reminders_by_item(self, item_type: str, item_name: str, item_date: str) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `month_savings_total(self, year: int | None = None, month: int | None = None) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理

##### `today`（属性）
- **getter**：返回 `self._data` 中对应字段
- **setter**：设置对应字段（不自动保存）


---

#### 禁止做的事

- **禁止绕过 `BaseJsonModel` 直接写文件**（引用 R-002）：所有持久化走 `save()` → `atomic_write()`
- **禁止在 Model 层 emit 信号**：Model 不继承 `QObject`，变更通知由 `DataManager` 统一管理

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| *（待补）* | | |

---

> **注意**：本文档为批量生成骨架。详细函数合同、术语映射需逐文件补充。
