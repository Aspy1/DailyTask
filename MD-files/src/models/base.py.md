### base.py

**职责**：所有 JSON 数据模型的基类——提供原子写入（防断电损坏）、Windows Defender 重试、版本迁移框架。

**架构层级**：Model Layer（基础设施）

**运行环境**：跨平台（Windows 上的 `PermissionError` 重试为 Windows Defender 特化处理）

**继承链**：`BaseJsonModel` → `CourseModel` / `TaskModel` / `HabitModel` / `ExpenseModel` / `DailyLogModel` / `ExamModel` / `InventoryModel`

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| （无项目内引用） | — | — | 纯标准库（`json`, `os`, `shutil`, `time`, `pathlib`） |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| 临时文件后缀 | `.tmp` | 原子写入的中间文件 |
| 备份文件后缀 | `.bak` | 写入前的备份文件 |
| 重试次数 | `5` | Windows 文件锁重试上限 |
| 重试间隔 | `0.05` (s) | `PermissionError` 时等待时间（违反 R-005，见待办） |
| 版本字段 | `_version` | JSON 中的版本标识键 |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self.file_path` | `Path` | 绑定的 JSON 文件路径 |
| `self._default_data` | `dict` | 默认数据模板（文件不存在时使用），默认为 `{"_version": 1}` |
| `self._data` | `dict` | 内存中的数据字典 |

---

#### 信号

无（`BaseJsonModel` 不继承 `QObject`，纯数据层）

---

#### 函数合同

##### `__init__(file_path: Path, default_data: dict | None = None)`

- **前置条件**：无
- **核心逻辑**：
  1. 存储 `file_path` 和 `_default_data`（默认 `{"_version": 1}`）
  2. 调用 `_ensure_file()` —— 如文件存在则 `load()`，否则创建默认数据并 `save()`
- **副作用**：可能创建文件或读取磁盘
- **返回值**：无

##### `_ensure_file() → None`

- **核心逻辑**：
  1. 若 `file_path` 不存在 → 创建父目录 → 初始化 `_data = _default_data` → `save()`
  2. 若存在 → `load()`
- **副作用**：可能创建目录和文件；可能读取磁盘
- **返回值**：无

##### `load() → dict`

- **核心逻辑**：`open(file_path)` → `json.load(f)` → 存入 `self._data`
- **副作用**：覆盖内存中的数据
- **返回值**：加载的 `dict`
- **异常行为**：无显式处理（`json.JSONDecodeError` 或文件不存在时将向上传播）

##### `reload() → None`

- **核心逻辑**：调用 `self.load()`，丢弃内存中未保存的修改
- **副作用**：以磁盘数据覆盖内存
- **返回值**：无

##### `save() → None`

- **核心逻辑**：委托给 `atomic_write()`
- **返回值**：无

##### `atomic_write() → None`

- **前置条件**：`self._data` 已就绪
- **核心逻辑**（原子写入 + 防损坏）：
  1. 写入临时文件 `file_path.tmp`
  2. 若原文件存在 → 复制到 `file_path.bak`（备份）
  3. `os.replace(tmp, file_path)` 原子替换（Windows 上为原子操作）
  4. **Windows Defender 重试**：若触发 `PermissionError`，以 50ms 间隔重试最多 5 次
  5. 成功后删除 `.bak` 备份
  6. 若中间任何步骤失败 → 尝试从 `.bak` 恢复原文件
- **副作用**：
  - 写入磁盘（`.tmp` → 替换 → 删除 `.bak`）
  - 最多可能阻塞 250ms（5 × 50ms 重试）
- **返回值**：无
- **异常行为**：
  - `PermissionError`：5 次重试后仍失败则向上抛出
  - **主动异常恢复**：若写入过程中发生任何异常（非仅崩溃），代码会尝试将 `.bak` 复制回原文件以恢复到上一状态，随后重新抛出异常
  - `.bak` 恢复失败时不阻塞异常传播（原异常仍会向上抛出）

##### `migrate(target_version: int) → None`

- **前置条件**：`self._data["_version"]` 已定义
- **核心逻辑**：
  1. 检查当前版本是否 < 目标版本
  2. 查找 `_migrate_v{current}_to_v{target}()` 方法
  3. 若存在则调用，更新 `_data["_version"]`
  4. 调用 `save()` 持久化
- **副作用**：修改 `_version` 字段；保存到磁盘
- **返回值**：无
- **异常行为**：无显式处理（迁移方法中的错误向上传播）

##### `data`（属性 getter/setter）

- **getter**：返回 `self._data`
- **setter**：设置 `self._data = value`
- **副作用**：setter 不自动保存——调用方需手动 `save()`

##### `version`（属性 getter）

- **核心逻辑**：返回 `self._data.get("_version", 1)`
- **返回值**：`int`
- **副作用**：无（只读）

---

#### 禁止做的事

- **禁止绕过原子写入**（引用 R-002）：子类不得重写 `save()` 为直接 `json.dump()`。所有写入必须经过 `atomic_write()`。
- **禁止手动调用 `atomic_write`**：外部调用必须通过 `save()`，以确保未来架构调整（如加密、压缩）不受影响。
- **禁止在子类中覆盖 `atomic_write`**：若需自定义存储逻辑（如数据库），应创建新的基类，而非修改此原子性保证。
- **禁止修改 `.tmp` / `.bak` 后缀逻辑**：临时文件和备份文件的命名约定不可更改，否则恢复机制失效。
- **禁止增大重试间隔**：50ms × 5 次是针对 Windows Defender 的调优值，增大间隔会造成不必要的 UI 卡顿。

---

#### 操作步骤清单

##### 添加新的数据模型

1. 创建 `src/models/xxx.py`
2. 继承 `BaseJsonModel`
3. 定义默认数据结构（`default_data`）
4. 如需版本迁移，实现 `_migrate_vX_to_vY` 方法

##### 修复数据损坏

1. 检查 `.json` 文件是否损坏（`JSONDecodeError`）
2. 查找同目录下的 `.bak` 备份文件
3. 手动将 `.bak` 复制为 `.json`
4. 重启应用触发 `load()`

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| 数据保存 | `save()` / `atomic_write()` | `base.py` |
| 数据加载 | `load()` / `reload()` | `base.py` |
| 版本升级 | `migrate()` | `base.py` |
| 原子写入 | Atomic Write | `BaseJsonModel.atomic_write` |
| 数据备份 | `.bak` backup file | `atomic_write` |
| 数据损坏恢复 | `.bak` → `.json` 手动恢复 | `操作步骤清单` |

---

#### 决策记录

**DR-BASE-001：使用 `os.replace` 而非 `shutil.move`**

- **原因**：`os.replace` 在 Windows 上是原子操作（NTFS 特性），能最大程度保证文件不会处于半写状态；`shutil.move` 在某些跨设备场景下可能不是原子的。`.bak` 备份提供写入失败时的最后恢复手段。
- **位置**：`BaseJsonModel.atomic_write`
- **状态**：锁定（不可回退为直接 `json.dump`）

**DR-BASE-002：Windows Defender / Search Indexer 重试 5 次 × 50ms**

- **原因**：Windows Defender 或文件索引服务（Search Indexer）经常在短时间内锁定刚写入的文件，导致 `PermissionError`。重试是解决此问题的行业标准方案。50ms 间隔 + 5 次重试覆盖绝大多数扫描窗口。
- **位置**：`BaseJsonModel.atomic_write`
- **状态**：锁定

**DR-BASE-003：版本迁移框架（`_version` + `migrate()`）**

- **原因**：JSON 数据格式演进时，通过 `_migrate_vX_to_vY()` 方法链式升级，避免手动修复已部署的数据文件。
- **位置**：`BaseJsonModel.migrate` + `_data["_version"]`
- **状态**：锁定

---

> **待办**
>
> 1. `time.sleep(0.05)` 硬编码在 `atomic_write()` 中，属于魔法数字（违反 R-005）。建议提取为类常量 `_RETRY_DELAY = 0.05`。





遗漏点：base.py.md中 atomic_write的异常恢复逻辑不完整
try:
    # ... 写入 .tmp, 复制 .bak, os.replace ...
except Exception:
    # 若中间任何步骤失败 -> 尝试从 .bak 恢复原文件
    if backup_path.exists():
        shutil.copy2(backup_path, file_path)
    raise  # 注意：这里 raise 了
    文档现状​ (base.py.md函数合同)：

异常行为：

PermissionError：5 次重试后仍失败则向上抛出

写入过程中崩溃：.bak文件保留在磁盘上，下次启动时可手动恢复