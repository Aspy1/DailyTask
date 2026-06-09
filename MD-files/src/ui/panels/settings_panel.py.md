### settings_panel.py

**职责**：设置面板 — AI 配置（提供商/API Key/模型）、邮箱配置（SMTP 测试）、插件管理（启用/禁用）

**架构层级**：UI Layer（面板）

**运行环境**：Windows，依赖 `PySide6.QtWidgets`

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `SettingsPanel` | `src.services.settings_manager` | Import | 配置读写 |
| `SettingsPanel` | `src.services.ai_service` | Import | AI 服务实例 |
| `SettingsPanel` | `src.services.plugin_manager` | Import | 插件管理 |
| `SettingsPanel` | `src.ui.styles.theme` | Import | 获取颜色和字体 |
| `_send_test_email` | `smtplib`, `email.mime.text` | Import | 发送邮件 |

---

#### 文件级常量 / 约定

| 常量/约定 | 值 | 说明 |
|---|---|---|
| （无显式常量） | — | |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| `self._settings` | `SettingsManager` | 配置实例 |
| `self._ai_service` | `AIService` | AI 服务实例 |
| `self._plugin_manager` | `PluginManager` | 插件管理器 |
| `self._provider_combo` | `QComboBox` | AI 提供商选择 |
| `self._api_key_input` | `QLineEdit` | API Key 输入 |
| `self._model_combo` | `QComboBox` | 模型选择 |
| `self._status_label` | `QLabel` | AI 配置状态显示 |
| `self._open_plugin_windows` | `list` | 保持打开的插件窗口引用 |

---

#### 信号

无 Qt 信号，但有关键的回调函数和副作用。

---

#### 函数合同

##### `_build_ai_card()`

- **核心逻辑**：构建 AI 设置 UI，连接 `currentIndexChanged` 到 `_on_provider_changed`
- **返回值**：无

##### `_on_provider_changed()`

- **核心逻辑**：根据选择的提供商（DeepSeek / Claude），动态更新 Endpoint、Key Placeholder 和 Model 列表
- **返回值**：无

##### `_save_ai_settings()`

- **核心逻辑**：将 UI 数据写入 `SettingsManager`，调用 `save()`，更新状态标签
- **副作用**：写配置；更新 UI
- **返回值**：无

##### `_send_test_email()`

- **前置条件**：邮箱地址和授权码已填写
- **核心逻辑**：使用 SMTP 协议发送测试邮件
- **副作用**：发起网络请求
- **异常行为**：捕获所有异常，弹窗提示失败

##### `_toggle_plugin(name, enable)`

- **核心逻辑**：调用 `PluginManager.enable/disable`，刷新插件列表
- **副作用**：修改插件状态

---

#### 禁止做的事

- **禁止直接修改 `settings.ini` 文件**：必须通过 `SettingsManager`
- **禁止在 `_send_test_email` 中阻塞主线程**（引用 R-004）：目前是同步发送，需留意

---

#### 决策记录

**DR-SETTINGS-001：插件窗口使用列表持有引用**

- **原因**：如果不持有引用，Python 的垃圾回收机制会立即关闭窗口。
- **位置**：`self._open_plugin_windows.append(widget)`
- **状态**：锁定

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| *（待补）* | | |
