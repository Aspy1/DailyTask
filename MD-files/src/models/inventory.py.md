### inventory.py

**职责**：物品 CRUD、位置追踪、状态管理、需购提醒

**架构层级**：Model Layer

**继承**：`BaseJsonModel` — 原子写入、版本迁移机制见 `base.py.md`

**运行环境**：跨平台，无外部依赖

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `InventoryModel` | `src.models.base` | Import | 继承 `BaseJsonModel` |

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
##### `items(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `categories(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `add_item(self, data: dict) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `update_item(self, iid: str, data: dict) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `delete_item(self, iid: str) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `consume(self, iid: str, amount: int = 1) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `remaining_doses(self, iid: str) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `need_restock(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `all_tags(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理
##### `stock_count(self) → ...`

- **前置条件**：Model 已初始化
- **核心逻辑**：参见源码
- **副作用**：修改 `self._data`
- **返回值**：*（待补）*
- **异常行为**：无显式处理

##### `items`（属性）
- **getter**：返回 `self._data` 中对应字段
- **setter**：设置对应字段（不自动保存）

##### `categories`（属性）
- **getter**：返回 `self._data` 中对应字段
- **setter**：设置对应字段（不自动保存）

##### `need_restock`（属性）
- **getter**：返回 `self._data` 中对应字段
- **setter**：设置对应字段（不自动保存）

##### `all_tags`（属性）
- **getter**：返回 `self._data` 中对应字段
- **setter**：设置对应字段（不自动保存）

##### `stock_count`（属性）
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
