### course_table.py

**职责**：课程表表格控件 — 7×6 周网格显示课程，右键菜单操作（布置作业/改名/删除/查看事项）

**架构层级**：UI Layer（自定义控件）

**运行环境**：Windows，依赖 `PySide6.QtWidgets`

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `CourseTable` | `DataManager` | 参数注入 | 课程数据（`self._dm`） |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| `DAY_LABELS` | `["周一", "周二", ...]` | 星期标签 |
| `COURSE_BG_TINTS` | `list[str]` | 课程背景色数组 |
| `CELL_TEXT` | `str` | 单元格文字颜色 |
| `COURSE_ACTIONS` | `dict` | 右键菜单预设项 |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self._period_count` | `int` | 时段数量（默认 6） |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|---|
| `fill_ai_prompt` | `Signal(str)` | 右键菜单选择"布置了作业"等预设项时 | 经过 `_build_context_prompt` 格式化后的 Prompt 字符串 |
| `course_rename_requested` | `Signal(str)` | 右键点击"修改课程名称" | `course_id` |
| `course_delete_requested` | `Signal(str)` | 右键点击"删除这门课" | `course_id` |
| `view_course_tasks` | `Signal(str)` | 右键点击"查看关于这门课的事项" | `course_name` |

---

#### 函数合同

##### `__init__(dm, parent=None)`

- **前置条件**：`DataManager` 已初始化
- **核心逻辑**：存储引用 → 构建表格布局 → 调用 `_build_labels()` 和 `set_courses()`
- **副作用**：创建 GUI 控件
- **返回值**：无

##### `build_course_context_menu(pos)`

- **核心逻辑**：在指定位置弹出右键菜单，包含预设的 `COURSE_ACTIONS` 选项
- **副作用**：根据选择 emit 对应信号
- **返回值**：无

##### `_build_context_prompt(course_id, action)`

- **核心逻辑**：根据课程数据和操作类型，构建格式化的 AI Prompt 字符串
- **返回值**：`str`

##### `_build_labels()`

- **核心逻辑**：根据时段配置生成如 `08:00\n08:45` 格式的时段标签
- **返回值**：无（设置 GUI 标签）

##### `period_count`（属性）

- **返回值**：`self._period_count`

##### `set_courses()`

- **核心逻辑**：
  1. 双层循环：外层遍历课程，内层遍历课程的 `time_slots`
  2. 使用哈希算法 `hash(cid) % len(COURSE_BG_TINTS)` 为不同课程分配固定的背景色
  3. 合并逻辑：如果同一单元格已有内容（如两门课背靠背），使用 `\n` 拼接文本
- **返回值**：无

##### `_format_cell(period, day)`

- **核心逻辑**：格式化指定单元格的显示内容
- **返回值**：格式化字符串

##### `_set_cell(period, day, text, bg_color)`

- **核心逻辑**：设置单元格文字和背景色
- **返回值**：无

##### `_on_context_menu(action_key, course_id)`

- **核心逻辑**：处理右键菜单选择 → emit 对应信号
- **返回值**：无

---

#### 禁止做的事

- **禁止硬编码右键菜单文本**：应通过 `COURSE_ACTIONS` 字典统一管理，便于 i18n 迁移
- **禁止修改哈希颜色算法**：`hash(cid) % len(COURSE_BG_TINTS)` 保证同一课程颜色稳定，修改会导致视觉不一致

---

#### 决策记录

**DR-UI-001：使用哈希确定课程颜色**

- **原因**：避免每次渲染随机变色，保持视觉稳定性。
- **位置**：`set_courses` 中的 `color_idx` 计算
- **状态**：锁定

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| *（待补）* | | |
