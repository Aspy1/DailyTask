### ai_service.py

**职责**：AI 对话服务——管理大模型后端（Anthropic / DeepSeek）、Agent Loop 多轮工具调用、系统提示词构建（含课程/日程/习惯/余额上下文注入）、对话历史管理。

**架构层级**：Service Layer

**运行环境**：Windows

**依赖**：`PySide6.QtCore`（`QObject`, `Signal`, `QThread`）+ `anthropic` / `openai` SDK（按 provider 动态导入）

**设计要点**：
- **Agent Loop**：AI 回复 → 提取 `sh` 代码块 → 执行 `actions.py` 子进程 → 结果回传 AI → 循环，最多 5 轮
- **上下文注入**：每次对话自动注入当前日期、周次、单双周、课程表、日程、习惯、支出、余额、物品库存、假期调休
- **历史压缩**：超过 16 条消息时自动压缩，保留最近 8 轮对话

---

#### 跨文件引用矩阵

| 本文件引用 | 被引用文件 | 引用类型 | 用途 |
|---|---|---|---|
| `AnthropicProvider.__init__` | `anthropic.Anthropic` | 动态 import | Claude API 客户端 |
| `DeepSeekProvider.__init__` | `openai.OpenAI` | 动态 import | DeepSeek API 客户端 |
| `InstructionParser.execute` | `subprocess` | Import | 执行 `scripts/actions.py` |
| `AIService._build_system_prompt` | `DataManager.get_today_summary()` | 方法调用 | 当日摘要 |
| `AIService.__init__` | `SettingsManager` | 参数注入 | API key 和配置 |
| `AIService.__init__` | `DataManager` | 参数注入 | 数据访问（`self._dm`） |

---

#### 文件级常量

| 常量 | 值 | 说明 |
|---|---|---|
| （无显式常量） | — | `SYSTEM_PROMPT_BASE` 是模块级变量但非传统常量；AI 调用的 `temperature=0.3` 和 `max_tokens=4096` 硬编码在 `AIWorker.run()` 中（见禁止清单 R-005） |

---

#### 类实例变量

| 变量 | 类型 | 作用 |
|---|---|---|
| **AIService** | | |
| `self._settings` | `SettingsManager` | 配置读写（API key、model、余额） |
| `self._dm` | `DataManager` | 数据聚合（课程、任务、习惯、支出等） |
| `self._history` | `list[dict]` | 对话历史（`[{role, content}]`） |
| `self._thread` | `QThread \| None` | AI 工作线程 |
| `self._worker` | `AIWorker \| None` | AI 工作对象 |
| `self._auto_continue_count` | `int` | 自动继续计数（`send_message` 中重置为 0） |
| **AIWorker** | | |
| `self._provider` | `AIProvider` | AI 后端实例 |
| `self._model` | `str` | 模型名 |
| `self._system_prompt` | `str` | 系统提示词 |
| `self._messages` | `list[dict]` | 消息列表 |
| `self._dm` | `DataManager \| None` | 数据管理（用于指令执行后 reload） |
| `self._settings` | `SettingsManager \| None` | 配置（用于指令执行） |
| **AnthropicProvider** | | |
| `self._client` | `Anthropic` | Claude SDK 客户端 |
| **DeepSeekProvider** | | |
| `self._client` | `OpenAI` | OpenAI SDK 客户端（兼容 DeepSeek） |

---

#### 信号

| 信号 | 签名 | 触发时机 | 携带数据 |
|---|---|---|---|
| **AIWorker** | | | |
| `finished` | `Signal(str)` | Agent Loop 结束（无指令或达到最大轮次） | AI 回复全文 |
| `error` | `Signal(str)` | 异常 | 错误信息 |
| `finished_with_instructions` | `Signal(str, list)` | Agent Loop 中有指令需执行时 | 回复文本 + 指令列表 |
| **AIService** | | | |
| `response_received` | `Signal(str)` | AI 回复就绪（纯文本，已剥离 `sh` 代码块） | 显示文本 |
| `error_occurred` | `Signal(str)` | API 调用失败或未配置 | 错误信息 |
| `instructions_executed` | `Signal(str, list)` | 指令执行完毕 | 显示文本 + 指令列表 |

> **信号竞态说明**：`finished` 和 `finished_with_instructions` 设计为**互斥触发**——Agent Loop 中有指令时 emit `finished_with_instructions`，无指令时 emit `finished`，二者必居其一且仅一次。`AIService._send_to_ai` 同时连接两者是防护性设计，实际只有其一触发。

---

#### 函数合同

##### 协议类：`AIProvider.chat(system_prompt, messages, model, max_tokens, temperature) → str`

- **前置条件**：无（协议定义）
- **核心逻辑**：抽象方法，由 `AnthropicProvider` 和 `DeepSeekProvider` 实现
- **返回值**：AI 回复字符串

---

##### `AnthropicProvider.__init__(api_key: str)`

- **前置条件**：`anthropic` 包已安装
- **核心逻辑**：动态导入 `from anthropic import Anthropic`，创建客户端实例
- **副作用**：初始化 API 客户端
- **返回值**：无

##### `AnthropicProvider.chat(...) → str`

- **核心逻辑**：调用 `self._client.messages.create()`，传入 system prompt + messages
- **返回值**：`response.content[0].text`
- **异常行为**：无显式处理（异常向上传播）

---

##### `DeepSeekProvider.__init__(api_key: str, base_url: str)`

- **前置条件**：`openai` 包已安装
- **核心逻辑**：动态导入 `from openai import OpenAI`，创建兼容客户端
- **副作用**：初始化 API 客户端
- **返回值**：无

##### `DeepSeekProvider.chat(...) → str`

- **核心逻辑**：将 system prompt 作为首条消息插入，调用 `self._client.chat.completions.create()`
- **返回值**：`response.choices[0].message.content or ""`
- **异常行为**：无显式处理（异常向上传播）

---

##### `AIWorker.__init__(provider, model, system_prompt, messages, dm, settings, parent)`

- **前置条件**：`provider` 已创建
- **核心逻辑**：存储所有参数为实例变量
- **副作用**：无
- **返回值**：无

##### `AIWorker.run() → None`

- **前置条件**：在 `QThread` 中运行（`moveToThread` + `started.connect`）
- **核心逻辑**（Agent Loop，最多 5 轮）：
  1. 调用 `_provider.chat()` 获取 AI 回复
  2. 用 `InstructionParser.parse()` 提取 `sh` 代码块中的 `actions.py` 命令
  3. 若无指令 → emit `finished(text)` 并返回
  4. 执行指令 → 结果文本回传给 AI（作为新的 user 消息）
  5. 循环，达到 5 轮上限时 emit `finished(display)`（已剥离代码块）
- **副作用**：emit `finished` 或 `error` 信号
- **返回值**：无（通过信号）
- **异常行为**：捕获所有异常，emit `error(str(e))`

---

##### `InstructionParser.parse(text: str) → list[str]`（静态方法）

- **前置条件**：无
- **核心逻辑**：正则 ````sh\s*
?(.*?)```` 提取代码块 → 过滤含 `scripts/actions.py` 的行
- **返回值**：命令字符串列表
- **异常行为**：无

##### `InstructionParser.execute(commands, dm, settings) → list[str]`（静态方法）

- **前置条件**：命令为有效 shell 命令
- **核心逻辑**：
  1. `subprocess.run(cmd, shell=True, cwd=项目根目录, timeout=30)` 逐条执行
  2. 收集 stdout 或 stderr
  3. 若 `dm` 存在 → `dm.reload_all()` + `dm.data_changed.emit("ai_action")`
- **副作用**：
  - `reload_all()` 会阻塞当前线程直至文件读取完成。由于该函数在 `AIWorker` 的子线程中运行，**不会阻塞 UI**（符合 R-004），但会延迟下一轮 AI 回复
  - 每执行完一批指令（无论几条），仅 emit **一次** `data_changed`，不会造成信号风暴
- **返回值**：每条命令的输出列表
- **异常行为**：单条命令失败时返回 `"ERROR {e}"`，不中断其余命令

---

##### `AIService.__init__(settings, data_manager, parent)`

- **前置条件**：`SettingsManager` 和 `DataManager` 已初始化（`App.__init__` 中 → 禁止清单 R-001）
- **核心逻辑**：存储引用，初始化空历史
- **副作用**：无
- **返回值**：无

##### `AIService._make_provider() → AIProvider`

- **前置条件**：`_settings` 持有 API key
- **核心逻辑**：读取 `AI.provider` 配置 → `claude` 返回 `AnthropicProvider`，否则返回 `DeepSeekProvider`（使用 `AI.api_endpoint` 自定义 base_url）
- **返回值**：`AIProvider` 实例
- **异常行为**：无显式处理（API key 缺失时 SDK 抛异常）

##### `AIService.is_configured → bool`（属性）

- **核心逻辑**：`bool(self._settings.api_key)`
- **返回值**：API key 是否已配置

##### `AIService.send_message(text: str) → None`

- **前置条件**：`is_configured` 为 `True`
- **核心逻辑**：
  1. 检查 API key → 未配置时 emit `error_occurred`
  2. 重置 `_auto_continue_count = 0`
  3. 追加 user 消息到 `_history`
  4. 调用 `_auto_compress()`
  5. 调用 `_send_to_ai()`
- **副作用**：修改对话历史；可能压缩上下文
- **返回值**：无

##### `AIService._send_to_ai() → None`

- **前置条件**：`_history` 非空
- **核心逻辑**：
  1. 构建系统提示词（`_build_system_prompt()`）
  2. 创建 `AIWorker` 并移到 `QThread`
  3. 连接 6 对信号（`finished`/`error`/`finished_with_instructions` → `_on_*` + `quit` + `deleteLater`）
  4. 启动线程
- **副作用**：创建并启动工作线程
- **返回值**：无
- **异常行为**：provider 创建失败时 emit `error_occurred`

##### `AIService._build_system_prompt() → str`

- **前置条件**：`DataManager` 所有 Model 已加载
- **核心逻辑**：拼接 `SYSTEM_PROMPT_BASE` + 以下运行时上下文：
  - 当前日期、学期、周次、单双周
  - 课程列表（含双周标注）
  - 最近 10 天日程计划
  - 今日摘要（课程数/待办任务/待核销习惯/支出）
  - 最近 20 条支出记录
  - 习惯列表（ID/名称/周期/提醒时间/推迟状态）
  - 余额（校园卡/水卡/电费）
  - 物品库存（ID/名称/数量/位置/状态/标签）
  - 假期和调休信息
- **副作用**：无（只读聚合）
- **返回值**：完整系统提示词字符串

##### `AIService._build_expense_list() → str`

- **核心逻辑**：取最近 20 条支出，按日期降序排列，格式 `[id] 日期 分类 ¥金额 备注`
- **返回值**：格式化字符串

##### `AIService._build_habit_list() → str`

- **核心逻辑**：遍历习惯，格式化周期类型（每周/每N天）、提醒时间、推迟状态
- **返回值**：格式化字符串

##### `AIService._get_current_week() → int`

- **核心逻辑**：从学期 `start_date` 计算 `(today - start).days // 7 + 1`
- **返回值**：当前周次（最小 1）

##### `AIService._get_week_parity() → str`

- **返回值**：`"单周"` 或 `"双周"`

##### `AIService._build_parity_hint() → str`

- **核心逻辑**：列出所有非 `week_parity == "all"` 的课程及其单/双周属性
- **返回值**：格式化字符串

##### `AIService._build_inventory_list() → str`

- **核心逻辑**：遍历物品，格式 `[id] 名称 数量单位 [位置] - 状态 (标签)`
- **返回值**：格式化字符串

##### `AIService._build_holiday_info() → str`

- **核心逻辑**：列出假期排除日期和调休映射
- **返回值**：格式化字符串

##### `AIService._on_response(text: str) → None`

- **核心逻辑**：追加 assistant 消息到历史 → 剥离 `sh`/`json` 代码块 → emit `response_received(display)`
- **副作用**：修改对话历史
- **返回值**：无

##### `AIService._on_response_with_instructions(text, instructions) → None`

- **核心逻辑**：去除代码块保留自然语言 → 执行指令 → emit `instructions_executed(display, instructions)`
- **副作用**：修改对话历史；触发数据重载（`dm.reload_all()`）
- **返回值**：无

##### `AIService._on_error(error_msg: str) → None`

- **核心逻辑**：记录日志 → emit `error_occurred`
- **返回值**：无

##### `AIService.clear_history() → None`

- **副作用**：清空 `_history`
- **返回值**：无

##### `AIService._auto_compress() → None`

- **前置条件**：`_history` 超过 16 条消息
- **核心逻辑**：保留最近 16 条 → 首条替换为摘要 `"（之前的对话已被压缩。用户进行了日程管理、数据操作等。）"`
- **目的**：防止 Token 超限
- **副作用**：截断对话历史
- **返回值**：无

##### `AIService.compress_context() → None`

- **核心逻辑**：手动触发压缩 → 调用 `_auto_compress()`
- **返回值**：无

---

#### 禁止做的事

**R-AI-001：AI prompt 格式一致性**

`SYSTEM_PROMPT_BASE` 和所有注入 prompt（`_quick_arrange` 等）必须统一输出格式为 ```sh + python scripts/actions.py。禁止部分 prompt 要求 JSON、部分要求 sh。

**R-AI-002：避免指令重复执行**

`InstructionParser.execute()` 只在 Worker.run() 的 Agent Loop 内调用。`_on_response_with_instructions` 不得再次调用 execute。

- **禁止阻塞主线程**（引用 R-004）：严禁在 `AIService` 主线程中直接调用 AI API。所有网络请求必须通过 `AIWorker` 在 `QThread` 中执行。
- **禁止绕过 DataManager**（引用 R-002）：`InstructionParser.execute` 必须调用 `dm.reload_all()`，禁止直接操作 JSON 文件。
- **禁止修改系统提示词核心规则**：`SYSTEM_PROMPT_BASE` 中的指令格式、参数标准化规则严禁随意更改。
- **禁止无限制轮次**：Agent Loop 必须限制在 5 轮以内，防止死循环和 Token 消耗失控。

---

#### 操作步骤清单

##### 添加新的 AI 提供商

1. 实现 `AIProvider` 协议的 `chat` 方法
2. 在 `_make_provider()` 中添加新的分支逻辑
3. 在 `SettingsManager` 中添加对应的配置项
4. 更新 `SYSTEM_PROMPT_BASE` 中的可用命令说明

##### 添加新的可执行指令

1. 在 `scripts/actions.py` 中实现新命令
2. 在 `SYSTEM_PROMPT_BASE` 的"可用命令"部分添加示例
3. 测试 `InstructionParser.parse` 是否能正确提取

---

#### 术语映射

| 用户用语 | 代码/内部术语 | 所在位置 |
|---|---|---|
| AI 回复 | Assistant Message | `AIService._on_response` |
| 指令 / 工具调用 | Shell Command / \`\`\`sh | `InstructionParser.parse` |
| 多轮对话 | Agent Loop / Turn | `AIWorker.run` |
| 上下文压缩 | Context Compression | `AIService._auto_compress` |
| 自动修正 | Self-Correction | `AIWorker.run`（错误回传 AI 重试） |
| 上下文溢出 | Token Limit | `AIService._auto_compress` |

---

#### 决策记录

**DR-AI-001：使用 subprocess 执行指令而非直接函数调用**

- **原因**：隔离风险。即使 AI 生成了恶意或错误的命令，也只在子进程中运行，不会影响主程序稳定性。同时便于统一处理 stdout/stderr。
- **位置**：`InstructionParser.execute`
- **状态**：锁定

**DR-AI-002：剥离代码块仅显示自然语言**

- **原因**：用户体验。用户不需要看到复杂的 Shell 命令，只需要知道结果。
- **位置**：`_on_response` / `_on_response_with_instructions`
- **状态**：锁定

**DR-AI-003：限制最大轮次为 5**

**DR-AI-004：Shell 指令超时设置为 30 秒**

- **原因**：防止恶意或错误的命令占用系统资源导致死锁。
- **风险**：如果未来 `actions.py` 增加了耗时操作（如视频处理、大数据导出），必须调整此值或改为异步执行。
- **位置**：`InstructionParser.execute` — `subprocess.run(..., timeout=30)`
- **状态**：锁定

- **原因**：成本控制与性能。防止 AI 陷入死循环或消耗过多 Token。
- **位置**：`AIWorker.run`
- **状态**：锁定

---

> **待办**
>
> 1. `temperature=0.3`、`max_tokens=4096`、`timeout=30` 硬编码违反 R-005。`temperature` 和 `max_tokens` 待迁移至 `SettingsManager`；`timeout=30` 见 DR-AI-004。
> 2. `finished_with_instructions` 信号在 `AIWorker` 中定义但 `AIService._send_to_ai` 同时连接了 `finished` 和 `finished_with_instructions`——两者可能重复触发，需确认设计意图。
> 3. `InstructionParser.execute` 中 `data_changed.emit("ai_action")` 的参数与 DataManager 的 `"external"` 不一致——ai_action 是否应该是一个独立的变更来源标识？
