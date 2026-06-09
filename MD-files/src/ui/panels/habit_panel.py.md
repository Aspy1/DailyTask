### habit_panel.py

**职责**：日常习惯面板 — 卡片网格展示，打卡/推迟/跳过操作，周期管理（每日/每周/每月），关联物品消耗

**架构层级**：UI Layer（面板）

**运行环境**：Windows

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `HabitPanel` | `src.services.data_manager` | Import | 习惯数据 |
| `HabitPanel` | `src.ui.styles.theme` | Import | 颜色和字体 |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| `CARD_MIN_WIDTH` | — | 习惯卡片最小宽度 |
| `CARD_HEIGHT` | — | 习惯卡片高度 |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| **`_HabitCard`** | | |
| `self._hid` | `str` | 习惯 ID |
| `self._active` | `bool` | 是否激活 |
| `self._done` | `bool` | 今日是否已完成 |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|---|
| `toggled` | `Signal(str)` | 打卡/取消打卡 | `habit_id` |
| `edit_requested` | `Signal(str)` | 点击编辑 | `habit_id` |
| `postpone_clicked` | `Signal(str)` | 点击推迟 | `habit_id` |
| `skip_clicked` | `Signal(str)` | 点击跳过 | `habit_id` |
| `habit_logged` | `Signal(str)` | 打卡记录写入 | `habit_id` |
| `DataManager.data_changed` | `Signal(str)` | 习惯变更后 | `"habit"` |

---

#### _HabitCard 状态渲染规则（核心）

| 状态 | 条件 | 背景色 | 标签文字 | 按钮 |
|---|---|---|---|---|
| 已完成 | `done=True` | Surface | "已完成" | 无 |
| 未激活（过期） | `active=False` | Surface | "每周X" / 周期描述 | 无 |
| 激活-每日 | `active=True`, `is_daily` | Card BG | "连续X天" 或 "今日未打卡" | 完成 / 推迟 / 跳过 |
| 激活-每周 | `active=True`, `is_weekly` | Card BG | "每周X" | 完成 / 推迟 / 跳过 |
| 激活-间隔 | `active=True`, `is_interval` | Card BG | "每X天" | 完成 / 推迟 / 跳过 |

---

#### 函数合同

##### `_HabitCard._describe_schedule()` / `_build_description()`

- **核心逻辑**：根据周期类型生成描述文字（"每周X" / "每X天"）
- **返回值**：`str`

##### `_HabitCard.mouseDoubleClickEvent()` / `contextMenuEvent()`

- **核心逻辑**：双击打卡 / 右键菜单（编辑/推迟/跳过）
- **返回值**：无

##### `_FlowGrid`

- **核心逻辑**：自定义流式布局，`setSpacing()` 控制间距，`sizeHint()` 计算最优尺寸

##### `HabitDialog`

- **周期类型**：三种 —— 每日（`daily`）/ 每周（`weekly`，选择星期几）/ 每月（`monthly`）
- **附加事项**（`attached_tasks`）：绑定到该习惯的关联任务
- **消耗物品**（`linked_items`）：打卡时自动扣减库存的物品（与 `attached_tasks` 是不同的概念）

##### `HabitPanel._refresh()`

- **核心逻辑**：遍历习惯 → 根据 `_HabitCard` 状态表创建卡片 → `_FlowGrid` 布局
- **返回值**：无

---

#### 禁止做的事

- **禁止移除或简化 `_HabitCard` 的 5 种状态渲染分支**：这是 UI 核心逻辑，修改会导致显示异常
- **禁止混淆 `attached_tasks` 和 `linked_items`**：前者是关联任务，后者是消耗物品

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| 习惯卡片 | `_HabitCard` | `habit_panel.py` |
| 打卡 | `toggled` / `habit_logged` | `habit_panel.py` |
| 推迟 | `postpone_clicked` | `habit_panel.py` |
| 跳过 | `skip_clicked` | `habit_panel.py` |
| 消耗物品 | `linked_items` | `habit_panel.py` |
