### main_window.py

**职责**：主窗口 — 8 面板容器、状态栏（DDL/课程/习惯实时显示）、侧边栏切换

**架构层级**：UI Layer（根容器）

**运行环境**：Windows，依赖 `PySide6.QtWidgets`

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| *（待补）* | | | |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| *（待补）* | | |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| *（待补）* | | |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|
| *（待补）* | | | |

---

#### 函数合同

> *（待补：27 个方法需逐函数编写合同）*

---

#### 决策记录

**DR-UI-ARRANGE-02：response_received 经 _on_ai_response 中转（兜底检查）**

- **原因**：`_arrange_pending` 主清路径是 `_on_instructions_done`（通过 `finished_with_instructions`），但若 AI 无指令纯文本响应，需兜底路径清标记。直接连 `ai_panel.append_message_ai` 会跳过检查。
- **位置**：`main_window._connect_ai` L266-267 + `_on_ai_response`
- **状态**：锁定


#### 禁止做的事

- *（待补）*

---

#### 操作步骤清单

##### 新增面板

1. 创建 `src/ui/panels/xxx_panel.py`，继承 `QWidget`
2. 在 `main_workspace.py` 的 `PANELS` dict 注册
3. 在 `sidebar.py` 对应的 `SECTION` list 添加条目
4. 更新本文件索引和 README.md

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| *（待补）* | | |

---

> **注意**：本文档为批量生成骨架。管理面板: 8 个。信号数: 0。
