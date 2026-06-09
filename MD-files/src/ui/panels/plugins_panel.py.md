### plugins_panel.py

**职责**：插件管理面板 — 列出已安装插件，支持启用/禁用/打开

**架构层级**：UI Layer（面板）

**运行环境**：Windows

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `PluginsPanel` | `src.ui.styles.theme` | Import | 颜色和字体 |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| （无显式常量） | — | |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self._pm` | `PluginManager` | 插件管理器 |
| `self._settings` | `SettingsManager` | 配置实例 |
| `self._ai_service` | `AIService` | AI 服务实例 |
| `self._data_manager` | `DataManager` | 数据管理器 |
| `self._open_plugin_windows` | `list` | 保持打开的插件窗口引用（防 GC） |
| `self._scroll` | `QScrollArea` | 滚动区域 |
| `self._list_layout` | `QVBoxLayout` | 插件列表布局 |

---

#### 信号

无 Qt 信号

---

#### 函数合同

##### `_c(key)`

- **核心逻辑**：简写 `get_colors()` 的 token 访问
- **返回值**：颜色值

##### `refresh()`

- **核心逻辑**：重新加载插件列表 → 重建 UI
- **返回值**：无

##### `_toggle(plugin_name, enable)`

- **核心逻辑**：调用 `PluginManager.enable/disable` → 刷新列表
- **副作用**：修改插件状态

##### `_open(plugin_name)`

- **核心逻辑**：创建插件窗口 → `self._open_plugin_windows.append(widget)` 持有引用
- **⚠️ 关键**：`append(widget)` 防止 Python GC 回收窗口导致立即关闭
- **返回值**：无

---

#### 禁止做的事

- **禁止移除 `self._open_plugin_windows.append(widget)`**：否则插件窗口会在打开后立即被 GC 关闭

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| 插件启用/禁用 | `_toggle` | `plugins_panel.py` |
| 打开插件 | `_open` | `plugins_panel.py` |
