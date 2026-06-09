### exam_panel.py

**职责**：考试面板 — 管理考试日期/范围/地点，按紧迫度着色（_ExamCard 颜色阈值）

**架构层级**：UI Layer（面板）

**运行环境**：Windows

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `ExamPanel` | `src.services.data_manager` | Import | 考试数据 |
| `ExamPanel` | `src.ui.styles.theme` | Import | 颜色和字体 |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| （无显式常量） | — | |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| **`_ExamCard`** | | |
| `self._exam` | `dict` | 考试数据字典 |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|---|
| `DataManager.data_changed` | `Signal(str)` | 考试增删改后 | `"exam"` |

---

#### 函数合同

##### `_ExamCard.__init__(exam)`

- **核心逻辑**：根据 `days_left` 判断紧迫度并设置颜色：
  - `< 0`：已过期
  - `== 0`：今天考试
  - `<= 7`：红色（紧迫）
  - `<= 15`：橙色（临近）
  - `> 15`：正常
- **副作用**：创建卡片 UI

##### `_ExamCard.contextMenuEvent()`

- **核心逻辑**：右键菜单（编辑/删除）
- **返回值**：无

##### `ExamPanel._add_exam()`

- **核心逻辑**：弹出 `ExamDialog` → 收集数据 → 保存 → emit `"exam"`
- **副作用**：修改数据；触发信号

##### `ExamPanel._delete_exam(exam_id)`

- **核心逻辑**：删除考试 → 保存 → emit `"exam"`
- **副作用**：删除数据；触发信号

##### `ExamPanel._refresh()` / `refresh_theme()`

- **核心逻辑**：重建考试卡片列表 / 刷新主题
- **返回值**：无

---

#### 禁止做的事

- **禁止修改 `_ExamCard` 中的颜色阈值逻辑**（`<0`, `==0`, `<=7`, `<=15`），这是考试紧迫度的视觉标准

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| 考试紧迫度 | `days_left` 颜色阈值 | `exam_panel.py` |
| 考试卡片 | `_ExamCard` | `exam_panel.py` |
