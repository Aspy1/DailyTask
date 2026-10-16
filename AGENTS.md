# AGENTS.md — 生活助手项目约束

> 本文件是本项目对 AI Agent 的**最高优先级约束**，每次操作前自动加载。
> 适用于 OpenCode、Claude Code 等任何在本项目工作的 Agent。
> 与全局指令（`~/.config/opencode`、`~/.claude`）冲突时，以本文件为准——项目级规则更具体。

---

## 0. 工作区约束

- **工作区根**：`D:\ClaudeCoding\日程规划`（即 git 仓库根）。
- **默认只在工作区内读写。** 任何工作区外的改动，先说明理由并征得同意：
  - 全局/用户配置：`~/.config/opencode/`、`~/.claude/`、Windows 注册表
  - 依赖与工具目录：`D:\Dev\`（见 §2）
  - 其它项目：`D:\ClaudeCoding\` 下的其它仓库（如 `tank`）
- **`data/` 是用户真实数据**：不得为测试而改动。测试一律用隔离目录
  （现成设施：`tests/conftest.py` 的 `sandbox` fixture）。
- **密钥**：`data/settings.ini` 含真实 API Key 与邮箱授权码。
  禁止读取/打印/复制其内容，禁止使其进入 git。
- **不触碰来路不明的文件或改动**：可能是用户正在进行的工作，先调查再决定。

## 1. 必须读取的文件（开发任何功能前，按序）

1. **本文件 `AGENTS.md`** — 流程、工作区、环境、DoD
2. **`MD-files/ARCHITECTURE.md`** — 项目如何运作：分层、启动顺序、三条数据路径、信号链、并发模型、不变量、数据 schema
   - 涉及数据流、信号、并发、架构决策时必读
3. **`MD-files/CODE_STANDARDS.md`** — 代码与工程规范（Q-xxx）：**写代码 / 审查 / 重构时必读**；违规项以 `PLAN.md` 为准排期
4. **`ERRORS.md`** — 已踩过的坑（先查索引，再跳到条目）
5. **要修改的源文件** — 全文通读
6. **`MD-files/AllTheFiles.md`** — 索引、术语映射、决策记录（DR-xxx）、操作步骤清单
7. **`design/INDEX.md`** — **只在动 UI 时**：UI 规范总入口（令牌 / 样式工厂 / 菜单与动效模板 /
   弹窗规范 / 原型 / 审查记录）。规范不存在时**先问用户**再创建（见 §3「UI 规范入口」）

## 2. 工作环境与依赖

| 项 | 值 |
|---|---|
| 解释器 | 项目 venv：`.venv\Scripts\python.exe`（Python 3.14.8） |
| Python 下限 | `>=3.12`（见 `pyproject.toml`） |
| 启动应用 | `.venv\Scripts\python.exe main.py` |
| 跑测试 | `.venv\Scripts\python.exe -m pytest` |
| 依赖声明 | `requirements.txt`（区间）· `requirements.lock.txt`（精确复现）· `requirements-dev.txt`（开发） |

- **不要用 PATH 上的 `python`**：本机它是 WindowsApps 占位符（已损坏，返回 9009）。
  所有命令一律用上面的 venv 解释器。
- **装依赖顺序**：先看 `D:\Dev` 是否已有现成的工具/解释器，有就直接用；没有再装。
  本项目 venv 基于 `D:\Dev\Python314` 创建，符合该约定；venv 属项目产物，不搬进 `D:\Dev`。
- **新增/升级依赖**：必须同步更新 `requirements.txt`，并重新生成 `requirements.lock.txt`。
- **已知环境坑**：`openai`/`anthropic` 构造客户端会经
  `httpx2 → truststore → platform.system() → cmd 子进程`；CPU 被其它项目占满时可能假死
  （非本项目缺陷）。运行应用时避免同时跑满 CPU 的重任务。
- 控制台中文乱码时设 `PYTHONIOENCODING=utf-8`。

## 3. 开发 / Bug 修复流程

### 复杂度分档

分档由以下可检查的条件判定，取最高命中档位：

| 条件 | 档位 |
|---|---|
| 只改了字符串字面量、CSS 色值、QLabel 文案、无函数签名变化 | L1 |
| 修改了 ≥2 个 .py 文件 | L3 |
| 新增/修改/删除了 `Signal()` 声明或 `.emit(` 调用 | L3 |
| 修改了任何函数的参数列表或返回值类型 | L2 |
| 修改了 `__init__` 方法 | L2 |
| 修改了系统提示词（`SYSTEM_PROMPT`、`_build_system_prompt`） | L3 |
| 修改了 `scripts/actions.py` 的命令集（handler / argparse / `run_in_process`） | L3 |
| 修改了 `QThread` / `subprocess` 调用 | L3 |
| 修改了数据 schema（`_version`、`migrate()`、JSON 字段结构） | L3 |
| 修改 ≥80 行代码（单个文件内） | L2 |
| 不命中以上任何条件 | L1 |

| 档位 | 必做步骤 |
|---|---|
| L1 轻 | 步骤 6 + 7 |
| L2 中 | 步骤 1, 3, 5, 6, 7 |
| L3 重 | 全部 8 步：1→2→3→4→5→6→7→8 |

### 步骤清单

1. **读代码 + 模拟流程**：通读涉及的源文件，模拟数据/信号/线程全链路
2. **查文档**：`ARCHITECTURE.md` + `ERRORS.md` 索引 + `CODE_STANDARDS.md`
3. **描述**：写清 bug 成因/功能执行流程（逐环节，不概括多个 bug）
4. **列 todo**
5. **改代码 + 写日志**：改完后在 `dev-logs/YYYY-MM-DD-主题.md` 记录变更清单
6. **验证**：`compileall` → `ruff check src scripts plugins tests` → `pytest` → `scripts/check_ui_tokens.py` → 改后模拟（见 §4）
   - 这组命令与 CI（`.github/workflows/ci.yml`）一致，提交前必须全绿
7. **补文档**：更新 `ARCHITECTURE.md` / `CODE_STANDARDS.md` / `ERRORS.md`（如有新坑）
8. **总结**：提炼犯错原因、决策原因

### 完成定义（DoD）

一处改动只有同时满足以下各项才算完成：

- 语法检查通过；`pytest` 全绿（新行为补了对应测试）
- 改后模拟通过（import 完整、变量已定义、信号已连接、控件已初始化）
- 相关文档已同步（ARCHITECTURE / CODE_STANDARDS / ERRORS）
- `dev-logs/` 有本次记录
- 已按 §7 提交

### 新增文件规范

- `ERRORS.md`：单文件，索引 + 条目格式。先查索引再跳转条目。每条 ≤20 行。
- `dev-logs/`：按 `YYYY-MM-DD-主题.md` 平铺。含涉及文件、变更清单、关联条目。
- `tests/`：pytest 平铺；涉及数据写入的测试必须用 `sandbox` fixture。

### UI 规范入口（动 UI 前必做）

**改任何 UI 之前，先读 `design/INDEX.md`**（UI 规范总入口：令牌 / 样式工厂 / 菜单与动效模板 /
弹窗规范 / 原型 / 审查记录，各自列了权威位置）。

- 表里**有**对应规范 → 按权威位置改，**不要另建一套**（例如输入框只能委托 `theme.input_qss()`）
- 表里**没有** → **先问用户**：是新增规范，还是已有规范够用？**确认后**再创建，
  并把新条目补进 `design/INDEX.md`（保持"一个入口"）
- 颜色/字号/圆角**只能**改 `src/ui/styles/tokens.json`；改完跑 `scripts/gen_design_tokens.py`
  （`Q-H8`，有同步测试守卫）
- 硬编码颜色会被 `scripts/check_ui_tokens.py` 拦下

> 为什么放在这里而不是 `design/INDEX.md`：`INDEX.md` 是"规范清单"，本文件是"流程约束"。
> 两者都在 §1 的必读清单里（第 7 条），但职责不同。

## 4. 文件修改规则

**编辑方式**

- 优先用精确编辑（`edit`/patch），**禁止 `content.replace()` 式批量替换**——
  替换目标出现在被替换函数自身内部时会造成递归/逻辑错误（见 `ERRORS.md #006`）。
- 涉及自身引用、多处相同文本的改动，必须逐处精确定位。
- 禁止删除/覆盖来路不明的文件；先调查再动。

**编码与行尾**

- 源码与文档统一 **UTF-8（无 BOM）**；不要整文件重写导致行尾/编码漂移。
- 仓库存储 LF、检出 CRLF；不要人为改动既有行尾风格。

**数据写入**

- 禁止在 UI/服务层直接用 `open()`/`json.dump()` 写 `data/*.json`（见 R-002）。
- 不要手工编辑 `data/*.json`（应用会 3s 轮询并 reload）；外部数据修正走 skill 或 `actions.py`。

**安全**

- 不读取、不打印、不提交 `data/settings.ini` 的内容（含密钥）。
- 不提交 `.venv/`、`__pycache__/`、`.pytest_cache/`、`*.bak`（已在 `.gitignore`）。

**改前检查**

- 改代码前必须语法检查：`.venv\Scripts\python.exe -m compileall <文件或目录>`。

## 5. 代码审查要求

- **改前模拟**：修改涉及 UI 交互（点击→弹窗→信号链路）或数据流（读→写→刷新）时，
  必须先模拟完整执行流程再动手。
- **改后模拟**：修改完成后必须再跑一遍——检查 import 是否完整、变量是否定义、
  信号是否连接、UI 控件是否正确初始化。`NameError: name 'X' is not defined` 是改后漏检的典型。
- 声明但未 emit 的 Qt 信号 = typo-like bug。新增信号后必须 `grep 'emit'` 确认有发射点。
- AI prompt 注入点（`SYSTEM_PROMPT`、`_build_system_prompt`、各 panel 的动态 prompt）必须格式一致；
  prompt 里宣传的命令必须与 `scripts/actions.py` 的实现对齐（有测试 `tests/test_prompt_consistency.py` 把关）。
- 跨线程信号链（Worker → Service → MainWindow）必须两端都能追踪到 emit → connect → slot。
- 已知高频坑（详见 `ERRORS.md` 与 §6 R-008）：`len()+1` 生成 ID、硬编码 hex、
  类名 QSS 选择器、`toggled` 复选框回环。

## 6. 架构红线

> 完整定义与理由见 `MD-files/AllTheFiles.md` → 项目级禁止清单。此处为速查。

- **R-001** 单例：`SettingsManager`、`DataManager`、`AIService` 仅 `App.__init__` 实例化。
  （现状：`WeatherService`/`ApiService` 尚有面板级实例化，属待整改。）
- **R-002** 数据写入路径：只有两条合法写入路径——UI 走 `DataManager`/Model 的 `save()`（原子写入）；
  AI/TG 走 `scripts/actions.py`。**除这两处外**，禁止直接 `open()`/`json.dump()` 写 `data/*.json`。
- **R-003** 信号与槽类型匹配（如 `ddl_alert(int)` 不能连无参槽）。
- **R-004** 主线程安全：`App.__init__` 与所有 UI 槽函数禁止阻塞（`time.sleep`、同步网络请求、大文件遍历），
  耗时操作放 `QThread`。（现状：`AIService` 取余额/天气有主线程同步请求，属待整改。）
- **R-005** 魔法数字：阈值不得硬编码，改阈值需同步文档。
- **R-006** 单实例逻辑不可改（`QLocalServer` Key 与超时）。
- **R-007** 托盘闪烁不可移除。
- **R-008** UI 约束：QSS 仅 `#objectName`（禁类名选择器）；`QComboBox` 禁 `border-radius`；
  复选框用 `clicked(bool)` 不用 `toggled`；颜色走 `get_colors()` token 禁硬编码 hex；
  ID 生成禁 `len()+1`；数据集操作禁止 LLM 直改结构化文件；UI 文本走 `i18n`。

## 7. 提交规范

- 每次功能修改后 **commit + push**；message ≤60 字符英文，形如
  `fix: ...` / `feat: ...` / `docs: ...` / `chore: ...`。
- **只提交与本次改动相关的文件**。不要手动提交：
  - 易变数据（`data/weather_cache.json`、`data/weather_stats.json` 等，由应用自动 sync）
  - `.venv/`、缓存目录、密钥文件
- 提交前确认 `git status`，避免夹带无关改动。

## 8. 文档维护规则

- 文档体系固定见 `CODE_STANDARDS Q-G3`；**不再维护逐文件 `.py.md`**。
- 改动影响运作原理 → 同步 `MD-files/ARCHITECTURE.md`。
- 新增/修改规范 → 更新 `MD-files/CODE_STANDARDS.md`，并在 `PLAN.md` 登记。
- 新增文件/目录 → 同步 `README.md`（并清理过期的 `AllTheFiles.md` 条目）。
- 文档未覆盖的内容不编造，标注 `*（待补）*`。
