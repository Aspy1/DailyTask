### expense_panel.py

**职责**：记账面板 — 收支记录、分类筛选、预算管理、月度汇总、今省计算

**架构层级**：UI Layer（面板）

**运行环境**：Windows

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `ExpensePanel` | `src.services.data_manager` | Import | 记账数据 |
| `ExpensePanel` | `src.ui.styles.theme` | Import | 颜色和字体 |

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
| `self._cat_btn` | `QPushButton` | 分类筛选按钮 |
| `self._time_btn` | `QPushButton` | 时间筛选按钮 |
| `self._sum_month` | `QLabel` | 月支出汇总 |
| `self._sum_today` | `QLabel` | 今日支出 |
| `self._sum_budget` | `QLabel` | 月度预算 |
| `self._sum_saved` | `QLabel` | 今省金额 |
| `self._amount_input` | `QLineEdit` | 金额输入 |
| `self._cat_combo` | `QComboBox` | 分类选择 |
| `self._note_input` | `QLineEdit` | 备注输入 |
| `self._sav_amount` | `QLineEdit` | 储蓄金额 |
| `self._sav_note` | `QLineEdit` | 储蓄备注 |
| `self._table` | `QTableWidget` | 支出记录表格 |
| `self._total_label` | `QLabel` | 总计标签 |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|---|
| `DataManager.data_changed` | `Signal(str)` | 支出增删改后 | `"expense"` |
| `DataManager.data_changed` | `Signal(str)` | 储蓄变动后 | `"saving"` |

---

#### 函数合同

##### `_btn_qss()` / `_input_qss()` / `_combo_qss()`

- **核心逻辑**：返回控件 QSS 样式字符串（使用 `get_colors()` token）
- **返回值**：`str`

##### `_summary_card(title, value, color_key)`

- **核心逻辑**：创建汇总卡片（标题 + 数值 + 颜色）
- **返回值**：`QFrame`

##### `_get_filtered()`

- **核心逻辑**：
  1. 按分类筛选（`category` 字段）
  2. 按时间范围筛选（`date` 字段）
  3. 返回过滤后的支出记录列表

##### `_refresh()`

- **核心逻辑**：重载数据 → 更新汇总卡片 → 重建表格
- **返回值**：无

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| 今省 | Today's Saving (`today_saved`) | 记账面板 |
| 月度预算 | `budget["monthly"]` | 记账面板 |
| 分类筛选 | `_cat_btn` + `QMenu` | 记账面板 |
