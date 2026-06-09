### data_manager.py

**职责**：中央数据枢纽——持有所有 Model 实例，3 秒轮询检测外部文件变更并自动重载，通过 `data_changed` 信号驱动 UI 刷新和 Git 同步。

**架构层级**：Service Layer（核心枢纽）

**继承**：`QObject` — 信号机制的基础

**类型注解**：方法返回值（`→ None`, `→ dict`）和变量（`dict[str, float]`）均使用 Python 类型提示

**运行环境**：Windows

**依赖**：`PySide6.QtCore`（`QObject`, `Signal`, `QTimer`）+ 7 个 Model 类（`src.models.*`）

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `DataManager.__init__` | `src.models.course` | Import | `CourseModel` |
| `DataManager.__init__` | `src.models.task` | Import | `TaskModel` |
| `DataManager.__init__` | `src.models.habit` | Import | `HabitModel` |
| `DataManager.__init__` | `src.models.expense` | Import | `ExpenseModel` |
| `DataManager.__init__` | `src.models.daily_log` | Import | `DailyLogModel` |
| `DataManager.__init__` | `src.models.exam` | Import | `ExamModel` |
| `DataManager.__init__` | `src.models.inventory` | Import | `InventoryModel` |
| `_auto_reload` | `PySide6.QtCore.QTimer` | Import | 3s 定时器 |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self.data_dir` | `Path` | 数据目录路径 |
| `self.courses` | `CourseModel` | 课程数据 |
| `self.tasks` | `TaskModel` | 作业数据 |
| `self.habits` | `HabitModel` | 日常习惯数据（`_inventory` 指向 `self.inventory`） |
| `self.expenses` | `ExpenseModel` | 记账数据 |
| `self.daily_logs` | `DailyLogModel` | 日程日志 |
| `self.exams` | `ExamModel` | 考试数据 |
| `self.inventory` | `InventoryModel` | 物品库存 |
| `self._file_mtimes` | `dict[str, float]` | 文件修改时间缓存，用于检测外部变更 |
| `self._reload_timer` | `QTimer` | 3s 轮询定时器 |
---

#### 文件级常量

| 常量 | 值 | 说明 |
|---|---|---|
| （无） | — | 无显式文件级常量 |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|---|
| `data_changed` | `Signal(str)` | 外部文件变更被检测到时 | `"external"` |

---

#### 函数合同

##### `__init__(data_dir: Path, parent=None)`

- **前置条件**：`SettingsManager` 已初始化（提供数据路径）
- **核心逻辑**：
  1. 创建 `data_dir` 目录（如不存在）
  2. 初始化 7 个 Model 实例，绑定对应 JSON 文件：

     | Model | JSON 文件 |
     |---|---|
     | `CourseModel` | `courses.json` |
     | `TaskModel` | `tasks.json` |
     | `HabitModel` | `habits.json` |
     | `ExpenseModel` | `expenses.json` |
     | `DailyLogModel` | `daily_logs.json` |
     | `ExamModel` | `exams.json` |
     | `InventoryModel` | `inventory.json` |
  3. 建立 `habits._inventory → self.inventory`（习惯消耗物品的跨 Model 引用）
  4. 记录所有文件的初始 `mtime`
  5. 方法内动态导入 `from PySide6.QtCore import QTimer`，启动 3s 定时器轮询文件变更
- **副作用**：创建所有 Model 实例；启动 `QTimer`
- **返回值**：无

##### `reload_all() → None`

- **前置条件**：所有 Model 已初始化
- **核心逻辑**：依次调用 7 个 Model 的 `.reload()` 方法，重读磁盘 JSON 文件，最后更新 `_capture_mtimes()`
- **副作用**：覆盖内存中的数据（以磁盘为准）
- **返回值**：`None`

##### `save_all() → None`

- **前置条件**：所有 Model 已初始化
- **核心逻辑**：依次调用 **5 个** Model 的 `.save()` 方法（`courses`, `tasks`, `habits`, `expenses`, `daily_logs`），将内存数据写入磁盘 JSON
- **副作用**：覆盖磁盘文件
- **返回值**：`None`
- **注意**：`exams` 和 `inventory` 不在此列表中。`inventory` 由 `scripts/actions.py` 直接写入 JSON；`exams` 未持久化保存（可能为代码遗漏）

##### `_capture_mtimes() → None`

- **前置条件**：Model 已初始化
- **核心逻辑**：遍历 7 个 Model，读取各 JSON 文件的 `st_mtime`，存入 `self._file_mtimes`
- **副作用**：更新内部时间戳缓存
- **返回值**：`None`
- **异常行为**：`OSError` 时静默跳过（文件可能暂时不存在）

##### `_auto_reload() → None`

- **前置条件**：`_reload_timer` 正在运行
- **核心逻辑**：
  1. 遍历 7 个 Model，比较当前 `st_mtime` 与缓存值
  2. 差值 > 0.1s 则调用 `.reload()` 并更新缓存
  3. 任一文件变更时 emit `data_changed.emit("external")`
- **副作用**：可能触发数据重载和信号发射
- **返回值**：`None`
- **约定**：3s 间隔 + 0.1s 阈值（`diff > 0.1`），防止文件系统浮点精度导致的微小抖动误判为文件变更

##### `get_today_summary() → dict`

- **前置条件**：所有 Model 已初始化
- **核心逻辑**：聚合返回当日摘要：
  ```python
  {
      "pending_tasks": int,       # 待完成作业数
      "pending_habits": int,      # 待打卡日常数
      "today_expense": float,     # 今日支出
      "budget_remaining": float,  # 月度预算余额 → expenses.budget.get("monthly", 0) - month_total()
      "today_courses": list,      # 今日有课的 Course 对象列表
  }
  ```
- **副作用**：无（只读）
- **返回值**：`dict`（5 字段）

---
1. save_all()中 exams的状态描述存在矛盾

文档现状：在函数合同 save_all()的“注意”中提到：“exams未持久化保存（可能为代码遗漏）”。

代码现状：代码中确实没有 self.exams.save()。

问题：文档在“类实例变量”中明确列出了 self.exams并绑定了 exams.json，但在 save_all()中却将其排除。这到底是“设计如此”（例如 exams是只读或临时数据）还是“代码 Bug”？

建议：如果是设计如此，请在文档中明确说明原因（例如：“exams数据由外部系统维护，本模块仅加载不回写”），以消除歧义。

2. _auto_reload中的“容差”逻辑未明确量化

文档现状：描述为“3s 间隔 + 0.1s 容差，避免浮点精度误触发”。

代码现状：通常是判断 (new_mtime - old_mtime) > 0.1。

建议：这个表述很好，但可以更精确一点。建议改为：“设定 0.1 秒的阈值（diff > 0.1），防止因文件系统浮点数精度导致的微小抖动误判为文件变更。”

3. get_today_summary()的返回值细节

文档现状：列出了返回的字典结构，其中 "today_courses": list。

代码现状：通常这个 List 里包含的是 Course 对象或字典。

建议：为了更严谨，可以补充说明该 List 的内容是什么（例如：“today_courses: 今日有课的课程对象列表”）。

4. 异常处理策略的完整性

文档现状：在 _capture_mtimes()中提到了 “OSError时静默跳过”。

代码现状：通常 reload()或 save()也可能包含异常处理。

建议：确认是否所有文件 IO 操作都有类似的容错处理，并在文档中统一体现“静默失败”的策略（这对于后台轮询服务很重要）

---

> **待办**
> 
> 1. `save_all()` 中 exams 未被保存是设计还是遗漏？——写到 `exams` Model 文档时确定
> 2. 静默失败策略（OSError 容错）是否覆盖所有 Model 的 `reload()` / `save()`？——审计各 Model 后统一文档表述

