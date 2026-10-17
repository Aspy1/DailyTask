# CODE_STANDARDS.md — 代码与工程规范（定稿 v1.0）

> **定位**：本项目"优雅 / 行之有效 / 安全"的**规范性语句**集合，是**回头检查**与自动检查器的依据。
> 2026-10-15 定稿。后续只在有充分理由时增量修订，修订需在 `PLAN.md` 登记。
>
> 文档分工：
> - `AGENTS.md` —— 流程、工作区、环境、DoD（每次操作都读）
> - **本文件** —— 代码与工程规范（写代码 / 审查 / 重构时读）
> - `MD-files/ARCHITECTURE.md`（待建）—— 项目如何运作
> - `ERRORS.md` —— 已踩的具体坑
> - `PLAN.md` —— 待做的整改项与体检结果
>
> 每条格式：**规则 → 为什么 → 如何检查 → 现状**。
> `现状`：`✔ 达标` / `✗ 违规（见 PLAN）` / `🔄 进行中` / `? 未核查`。
> 章节：**A** 结构分层 · **B** 线程并发 · **C** 复杂度资源 · **D** 日志调试 · **E** 安全数据 ·
> **F** 测试 · **G** 文档 · **H** UI 与令牌 · **I** 异常处理 · **N** 命名约定 · **P** 目录结构。
>
> **2026-10-16 门禁对账**：`现状` 栏曾大面积失真（✔/✗ 都错报）。现已全量复核，并确立
> **Q-F4**：每条规则要么有可运行的检查（接进 CI），要么显式标注"人工 / 工具未装"。
> 门禁实现在 `scripts/check_quality.py`，存量债见 `scripts/quality_baseline.json`。

---

## A. 结构与分层

**Q-A1 单一职责：函数 ≤ 60 行、类 ≤ 400 行、单文件 ≤ 800 行**
- 阈值：**采用默认（2026-10-15 定）**。
- 为什么：超过认知上限后，改动成本与 bug 率非线性上升。
- 检查：`scripts/check_quality.py`（`SIZE` 项，2026-10-16 起接 CI）、`radon`、`vulture`。
- 现状：`✗` 2026-10-16 实测超限 **36 项**：文件 4（`habit_panel.py` 907、`schedule_view.py` 877、
  `main_window.py` 828、`actions.py` 825）；类 6（`ScheduleView` 844、`SettingsPanel` 705、
  `InventoryPanel` 713、`MainWindow` 552、`AIService` 475、`ReminderService` 420）；函数 ~26（多为 `__init__`）。
  **已记入 `scripts/quality_baseline.json` 防新增**；全量拆分见 `PLAN P3`。

**Q-A2 依赖单向：UI → Service → Model，禁止反向 import**
- 为什么：反向依赖使分层失效、难以测试。
- 检查：`import-linter`（`.importlinter` 的 layers 契约，已装进 `requirements-dev.txt` 并接入门禁）。
- 现状：`✔` 2026-10-16：`lint-imports` 报 **1 contract kept / 0 broken**（50 文件 129 依赖）。
  历史上唯一那处反向依赖（服务层 `import src.ui...`）已随代码演进移除；现已由门禁常驻守卫。

**Q-A3 同一外部能力只保留一套适配**
- 为什么：多套实现必然漂移，改一处漏一处。
- 检查：人工/关键字扫描。
- 检查：`tests/test_openmeteo.py`（守卫"天气码映射只存在于一个模块"、"Open-Meteo URL 只出现一处"、
  "ai_service 必须委托共享适配器"）；`import-linter`（`.importlinter`）守分层方向。
- 现状：`✔` 2026-10-16：天气 3 套实现已收拢 —— 和风（`weather_service.py`）、
  Open-Meteo（新 `services/openmeteo.py`）；`api_service.py`（整模块无人引用＝死代码，
  含第二套天气 + 重复的余额逻辑）**已删除**；`ai_service` 内联的 Open-Meteo 请求与重复的
  天气码映射也已移除，改为委托 `openmeteo.fetch_text_for_ai()`。

**Q-A4 禁止死代码**
- 为什么：误导读者、掩盖真实路径。
- 检查：`vulture src scripts plugins --min-confidence 80`（已接 CI：`scripts/check_quality.py` 的 `VULTURE` 项）。
- 现状：`✔` 2026-10-16：`main_window._shopping_label` 死代码路径（引用从未创建的控件）已删除；
  `vulture --min-confidence 80` 现为 **0**，并已纳入 CI 门禁。

**Q-A5 不用继承表达"部分复用"**
- 为什么：继承是 is-a，不是"借用几个方法"。
- 现状：`✔` 2026-10-16：`models/scene_archive.py` 已随「场景存档」功能一并删除（其位置职责并入天气设置）。

**Q-A6 类型注解**：新增/修改的函数必须有**返回类型**注解；非 UI 层的公开函数应补参数注解
- 检查：`ruff --select ANN201,ANN202,ANN204,ANN002,ANN003`（已并入规则集）；`ANN001`（参数注解）**暂不强制**
- 现状：`✔` 2026-10-16：返回类型已全量补齐（自动 126 处 + 手工 24 处）；
  存量参数注解约 229 处按"改到即补"处理

## B. 线程与并发

**Q-B1 Qt 对象只在创建它的线程访问；跨线程只经 signal/slot（队列连接）**
- 检查：人工 + `pytest-qt`。
- 现状：`?` 需核查 UI 与服务边界。

**Q-B2 共享可变状态必须加锁或明确单线程归属**
- 为什么：无锁的 dict 并发读写会产生撕裂读/丢失更新。
- 检查：人工审查 + 并发压测。
- 现状：`✔` 2026-10-16：AI worker 线程**不再触碰 Model**（`InstructionParser.execute` 只负责跑命令；
  `dm.reload_all()` + `emit("ai_action")` 已移到主线程的 `_on_response_with_instructions`）；
  类级缓存改为实例属性；`ruff --select RUF012` 已清零。

**Q-B3 禁止 `QThread.terminate()`**
- 现状：`✔` 2026-10-16：已移除，改为按 `sender()` 丢弃过期请求的结果。

**Q-B4 禁止在 worker 中改动进程级全局状态**（`sys.stdout`、`os.environ`、模块级缓存）
- 现状：`🔄` 2026-10-16：类属性缓存已改实例属性；`redirect_stdout` 仍用于捕获 CLI 输出，
  已加模块级锁串行化。**彻底消除**需把 handler 从 `print` 改为返回字符串（列入待办）。

**Q-B5 QObject/QThread 生命周期必须显式回收**（`deleteLater` / 单一归属），禁止反复 `new` 不释放
- 现状：`✔` 2026-10-16：`weather_service` 改为**按接口类型**管理 worker（顺带修掉"7 天预报永不刷新"的 bug）；
  `api_service` / `git_sync` 均 `deleteLater` 回收。

**Q-B6 禁止闭包捕获循环变量**（`lambda` / 生成器引用外层循环变量）
- 为什么：所有闭包共享同一变量 → 偶发跳错项，且难复现。
- 检查：`ruff --select B023`（在固定规则集内，已接 CI）。
- 现状：`✔` 2026-10-16：**3 处已修**（`a189421`），ruff `B023` 现为 **0**。

## C. 复杂度与资源

**Q-C1 圈复杂度 ≤ 10（B 级）**
- 阈值：**≤ 10（B 级，采用 radon 默认分档；2026-10-15 定）**。
- 检查：`radon cc -n C -s src scripts plugins`（已接 CI：`check_quality.py` 的 `RADON` 项，要求无输出）。
- 现状：`✔` 2026-10-16：**`radon cc -n C` 为空**（所有函数 ≤ B 级）；全局平均复杂度 A。
  拆分中抽出约 40 个语义化辅助函数；期间发现并修复 1 个真实崩溃（见 dev-log）。

**Q-C2 主线程禁止阻塞**（网络/IO/大循环）
- 现状：`✔` 2026-10-16：系统提示词构建改为**只读缓存**，余额/天气由一次性守护线程预热
  （`AIService._warm_context_cache`，预热不触碰主线程属主的 `WeatherService`）；
  `tests/test_ai_service_context.py` 断言构建期间任何 `requests` 调用都算失败。

**Q-C3 全表扫描类统计需评估规模上限或加缓存**
- 为什么：面板刷新 + 30s 状态栏会反复触发。
- 检查：`tests/test_habit_schedule.py`（daily/weekly/monthly/interval + 推迟/取消）。
- 现状：`🔄` 2026-10-16：**monthly 分支的层级错误已修**（`logs` 是 `logs[日期][habit_id]` 两层，
  旧代码把顶层键当 habit_id 比较 → 每月习惯永远判"未达标"），并补齐 9 条调度测试。
  记账/考试统计仍是每次 O(n)（当前数据量下无感，暂缓）。

**Q-C4 文件/线程/连接等资源必须显式释放**
- 检查：`ruff --select SIM115` + QThread 人工核查。
- 现状：`✔` 2026-10-16：`SIM115`（文件未用上下文管理器）**已清零**（ruff 0）；
  `weather_service` / `ai_service` 的 QThread 均已 `deleteLater` 回收。

## D. 日志与调试输出

**Q-D1 非脚本代码禁用裸 `print()`，统一 `logging`**
- 为什么：无法分级、无法关闭、污染 stdout（还会与 `redirect_stdout` 互相干扰）。
- 检查：`ruff` 规则 `T20`，或 `grep -rn "print(" src`。
- 现状：`✔` 2026-10-16：`src/` 内 `print()` 已清零（`task.py` 的调试输出移除）；`scripts/*` 的 CLI 输出按契约保留。

**Q-D2 日志按级别使用**：`debug` 默认关闭；异常路径 `logger.error(..., exc_info=True)`；不在热点循环里做字符串拼接。

**Q-D3 日志语句必须**"可静态剥离"**：独立表达式语句、无副作用实参、不处于"删除后块为空"的位置
- 为什么：为将来构建瘦身留路（否则 AST 剥离会改行为）。
- 检查：`scripts/check_quality.py` 的 `LOG-STRIP` 项（**必须 0**：日志嵌在表达式里）
  + `LOG-ONLY` 项（baseline：日志是所在块唯一语句）。
- 现状：`✔` 2026-10-16：`LOG-STRIP` **0 处**。`LOG-ONLY` 有 37 处存量（记入 baseline）。
  **口径说明**：`LOG-ONLY` 被**收窄为可容忍** —— 剥离器遇到"块内只有一条日志"只需补 `pass`
  即可保持语法与行为不变，不是剥离的阻断项；真正阻断的是 `x = logger.info(...)` 这类
  **嵌在表达式里**的写法（本项已强制为 0）。

**Q-D4 禁止把密钥、token、个人数据写入日志或异常信息**

## E. 安全与数据

**Q-E1 密钥不进代码 / 日志 / git**（本机 `data/settings.ini` 为明文，已在 `.gitignore`）
- 检查：`scripts/check_quality.py` 的两项 —— `SECRET`（断言 `data/settings.ini` 未被 git 跟踪）
  + `SECRETS`（**只读比对**：跑 `detect-secrets scan` 后与 `.secrets.baseline` 逐条对比，
  只报"基线里没有的新发现"；扫描排除 `data/`、`.venv/`、缓存目录，避免把真实密钥写进基线）
- ⚠ **不要用 `detect-secrets scan --baseline X` 当校验**：它的语义是"**更新**基线"（退出码恒 0，
  等于没检查），而且会把工作区写脏。基线只应通过 `check_quality.py --write-baseline` 刷新。
- 现状：`✔` 2026-10-16：首次扫描 4 处"Secret Keyword"均为**误报**（i18n 语言包里的
  `API Key:` / `密码:` 等标签文案）→ 已记入基线；`SECRETS` 现在能真正拦住新增（已实测：
  从基线删一条即报"新出现 1 处"）。全历史扫描（gitleaks 类）仍未引入——本项只覆盖**当前文件内容**。

**Q-E2 数据写入必须原子（`os.replace`）且经 Model 或 `actions.py`**（= R-002）
- 现状：`✔` `models/base.py` 已实现；`✗` 双写路径未统一。

**Q-E3 外部输入必须校验**（AI 生成命令、JSON 导入、插件）

**Q-E4 数据 schema 与迁移**：每个 `data/*.json` 的 `_version` 与 `migrate()` 必须有测试；
字段变更必须提供向后兼容或迁移路径（跨端共写：桌面 + TG + GitHub Actions）
- 现状：`🔄` 2026-10-16：`BaseJsonModel.load()` 对缺失 `_version` **自愈为 v1**；
  新增 `tests/test_data_schema.py`（7 个模型建文件 / 迁移 no-op / 仓库数据文件版本守卫），
  并据此补齐了 `data/inventory.json` 缺失的 `_version`。
  真正的 `_migrate_vN_to_vM` 仍是骨架（尚无历史版本迁移需求）。

**Q-E5 版本号单一来源**：以 `pyproject.toml` 的 `version` 为准，`i18n` / `README` / 发行包名由其派生
- 现状：`✗` 曾出现 `app.version` 0.3.0 与 README v0.9.0 不一致（已临时对齐，尚未做到派生）。

## F. 测试与可验证性

**Q-F1 新增/修改行为必须有测试**（见 `AGENTS.md` DoD）
- 现状：`✅` CI 每次跑 `pytest --cov`（下限 50%）。**具体数字不写进文档**（会漂）：以 CI 输出
  为准 —— 2026-10-17 审查发现文档里还留着"覆盖率 1%"与"225 passed"两个漂移样本。
  `--cov-fail-under=50` 下限（防"越改越少测"）。已有：actions 命令冒烟 + 日期解析、提示词↔实现**双向**
  一致性、令牌同步/合规、`send_digest`（含 exams.json）、考试提醒阈值、数据流（外部刷新 / save_all）、
  UI 接线（导航/主题/三态筛选）、AI 上下文非阻塞、数据 schema 守卫、习惯调度（4 种 schedule）、
  ID 生成、i18n（键存在/命名/去重/回退）、天气与余额"单一实现"守卫、工程门禁自身。
  UI 布局与部分服务仍无覆盖。

**Q-F2 契约必须可校验**：prompt ↔ `actions.py` ↔ TG skill 的命令集一致
- 现状：`✔` `tests/test_prompt_consistency.py`（3 处已知缺口以 xfail 固化）。

**Q-F3 改变更完成后必须自检**：import 完整、信号已连接、控件已初始化

**Q-F4 规范必须门禁化**：每条 Q 规则要么有**可运行的检查**（脚本/测试，且接进 CI），
要么在「检查」栏显式标注"人工"或"工具未装（待办）"——禁止留"写了检查方法但跑不起来"
- 为什么：2026-10-16 审计发现，64 条 Q 规则里只有约 16 条真正有门禁（25%），
  其余只有散文约束；`CODE_STANDARDS` 的「现状」栏因此大面积失真（✔/✗ 都错报）
- 落地：`scripts/check_quality.py`（可绝对化的必须为 0；有历史债的走
  `scripts/quality_baseline.json` 只防新增）；`tests/test_quality_gates.py` 守卫门禁本身
- 现状：`🔄` 2026-10-16：已补 9 类检查并接 CI；`Q-A2`/`Q-E1`(gitleaks)/`Q-D3` 三项因工具未装仍待办

## G. 文档

**Q-G1 文档只写代码表达不了的东西**（跨文件时序、不变量、为什么、外部契约）；签名/参数/字段不抄
- 现状：`✔` 2026-10-16：34 份 `.py.md` 与 `FORMAT_SPEC.md` **已全部删除**（`A-1`），
  现存 `.py.md` 文件数 = **0**。

**Q-G2 文档必须可校验，或明确标注 `*（待补）*`**；禁止"参见源码"式占位
- 现状：`✔` 2026-10-16：批量骨架文档已随 `A-1` 删除，现存文档均为手写内容。

**Q-G3 文档体系固定为**：`AGENTS.md`（流程/环境）· `PLAN.md`（计划与体检）· `CODE_STANDARDS.md`（规范）·
`ARCHITECTURE.md`（运作原理）· `ERRORS.md`（坑）· `dev-logs/`（变更史）· `README.md`（概览）。
**不再维护逐文件 `.py.md`**
- 现状：`✔` 2026-10-15 完成（34 份 `.py.md` 与 `FORMAT_SPEC.md` 已删，新增 `ARCHITECTURE.md`）。

**Q-G4 单一真值**：同一事实只允许一处权威来源；文档与代码冲突时以**代码**为准并立即修文档
- 现状：`✔` 2026-10-16：`design/tokens.json` 为唯一真值，`design/DESIGN_TOKENS.md` 由
  `scripts/gen_design_tokens.py` 生成、`tests/test_design_tokens_sync.py` 守卫漂移；`ERRORS.md` 重复问题已解决。
  同年 10-16 又收拢两处"多处各算一遍"：**周次计算**（5 处 → `models/semester.py`，见 `ERRORS #037`）
  与**天气/余额适配**（3 套 → `services/openmeteo.py` + `services/deepseek.py`，见 `PLAN P7`）。

## H. UI 与设计令牌

**Q-H1 颜色 / 字号 / 间距 / 圆角一律走 token，禁止字面量**（`#hex`、`rgb()/rgba()`、`Npx`、`QFont(..., int)`）
- 检查：`scripts/check_ui_tokens.py`（见 PLAN G-2）；或先 `grep -rn "#[0-9a-fA-F]\{3,8\}" src/ui`。
- 现状：`✔` 2026-10-16：`scripts/check_ui_tokens.py` 巡检 **0 违规**（由 `tests/test_ui_tokens_clean.py` 守卫）；
  清理过程中新增了令牌 `fg_on_fill` / `code_bg` / `bg_hover`（违规暴露出的缺失语义）。

**Q-H2 令牌单一真值**：规格文档由令牌文件**生成**，禁止规格与实现两份手写
- 现状：`✔` 2026-10-16：`tokens.json` 为唯一真值，`DESIGN_TOKENS.md` 的令牌表由 `scripts/gen_design_tokens.py` 生成，并由 `tests/test_design_tokens_sync.py` 守卫漂移。

**Q-H3 令牌命名：`<domain>_<variant>_<property>_<state>`，各槽取受控词表**

| 槽 | 取值（受控） |
|---|---|
| `domain` | `bg` `fg` `border` `divider` `accent` `state` `btn` `badge` `nav` `card` `input` `chip` `icon` `space` `radius` `size` `dur` `ease` `shadow` |
| `variant` | 组件变体：`primary` `secondary` `ghost` `danger` `success` `warning` `info` `subtle` |
| `property` | `bg` `fg` `border` `fill` `radius` `size` `duration` … |
| `state` | `hover` `active` `pressed` `disabled` `selected` `on`（如 `fg_on_accent`） |

- 示例：`bg_card`、`fg_primary`、`state_danger_subtle`、`btn_primary_bg_hover`、`nav_selected_fg`、`fg_on_accent`
- 禁止用原始色名当令牌名（`red`/`green`/`yellow`）；禁止把尺寸混进颜色集（如 `badge_radius`）
- 现状：`🔄` 2026-10-16：仍有 **10 处**存量（`colors.*.red/green/yellow/orange` + `colors.*.badge_radius`），
  **已记入 `quality_baseline.json` 防新增**；重命名会牵动调用点，与 `Q-H7` 分层一起排期。

**Q-H4 QSS 选择器仅 `#objectName`，禁止类名选择器**（= R-008）
- 检查：`scripts/check_ui_tokens.py` 的 `QSS-CLASS` 项（已接 CI）。
- 现状：`✔` 2026-10-16：`_HabitCard` / `_ExamCard` 已改为 `#objectName` 选择器（并补 `setObjectName`）——
  此前类名选择器在 Windows PySide6 **不生效**，卡片的背景/圆角/悬停实际从未应用，现按设计生效。
  实测已无自定义类名选择器（全局 QSS 里的 `QPushButton {}` 等原生类名不属此列）。

**Q-H5 颜色必须属于主题 token 集合**（禁止 `settings_panel.py:296/299` 那种非主题色）
- 现状：`✔` 2026-10-16：`check_ui_tokens.py` 巡检 0 违规；原先的 VS Code 风状态色已改主题 `green`/`red`。

**Q-H6 视觉克制**：accent 像素面积 < 5%；禁止第四种色相、纯黑/纯白（人工核对）

**Q-H7 令牌分三层**：`palette`（原始色板）→ `semantic`（角色：bg/fg/border/state）→ `component`（btn/badge/nav/card/input）
- 组件层只允许引用 `semantic` / `component`，**禁止直接引用 `palette`**

**Q-H8 令牌文件与生成链**：`design/tokens.json`（唯一真值）→ `theme.py` 加载并生成 QSS →
`design/DESIGN_TOKENS.md` 由脚本生成（**UI 规范总入口是 `design/INDEX.md`**）；组件经 `get_colors()` 取 `semantic` / `component` 名
- 现状：`✔` 2026-10-16：真值在 `design/tokens.json`（`theme.py` 加载）；`design/DESIGN_TOKENS.md` 由脚本生成并有同步测试；`palette` 分层（`Q-H7`）尚未引入。

**Q-H9 弹窗（Dialog）结构与尺寸**
- 三段式：**标题区**（`SIZE_BODY_L` 16px / 600，左对齐，与内容同缩进）→ **内容区** → **按钮区**（右对齐）
- 尺寸：默认宽 420–480px，最小 360px；内容超高用 `QScrollArea`
- 边距：外边距 20px，行间距 10–12px（与卡片一致）
- 为什么：5 个弹窗各写各的（宽 320/360/420、边距 16/20/32），并排看就不是一套东西

**Q-H10 弹窗不得重复画标题**
- 保留系统标题栏（原生拖拽 / 关闭 / 置顶行为正确），**内容区不再写一遍同名大标题**
- 现状：`✔` 2026-10-16：「场景管理」已随场景存档功能弃用而删除（`F-6`），弹窗不再重复标题。

**Q-H11 按钮区规范**
- 顺序：`取消` 在左，**主操作在最右**；主操作用 `btn_primary_qss()`，次操作用 `btn_secondary_qss()`
- 文案必须是中文动词（保存 / 取消 / 删除 / 确定），**禁止 `OK` / `Cancel`**
- 危险操作（删除 / 清空）二次确认，确认按钮用 `red_fill` 填充 + `fg_on_fill`
- 现状：`✔` 2026-10-16：全项目已无 `OK`/`Cancel` 文案（实测 `grep` 为 0）；「场景管理」已删除，
  库存标签对话框文案已统一。新增弹窗按本条执行（人工核对，尚无门禁）。

**Q-H12 输入控件高度统一**
- 同一弹窗内所有输入类控件（`QLineEdit` / `QComboBox` / `QSpinBox` / `QDateTimeEdit`）**同高**，字号走 `SIZE_BODY_S`
- 可编辑 `QComboBox` 的内嵌 `QLineEdit` 必须重置 padding，否则文字被裁（2026-10-16 实测）
- **日期/数字控件必须显示 ASCII 数字**：`theme.configure_locale()` 把默认区域固定为
  `en_US`（由 `init_theme()` 调用）。本机系统区域是 `zh_HK`，其 CLDR 用 **CJK 数字**，
  不设的话 `QDateEdit` 会把 `2026-10-19` 显示成 `〢〇〢〦-〡〇-〡〩`（`ERRORS #036`）。
  守卫：`tests/test_locale.py`
- 现状：`设置 → 模型` 曾因叠加 padding 被裁，已修

**Q-H13 弹窗配色只走 token**
- 底色 `bg_elevated`、卡片 `card_bg`、边框 `border_strong`、主按钮 `accent` + `fg_on_fill`
- 由 `scripts/check_ui_tokens.py` 强制（禁硬编码 `#hex`）

**Q-H14 弹窗必须跟着主题切换**
- 每次 `exec()` 新建的弹窗天然拿到当前主题；**长驻弹窗**（如 API 测试）需实现 `refresh_theme()`
- 兜底：`theme.remap_stylesheets()` 在切主题时统一重写所有内联样式表

**Q-H15 弹出层（菜单）定位与模板**
- **必须**走 `src/ui/widgets/menu.py` 的模板，禁止各自算坐标：
  - `new_menu(parent)`：`QMenu` + token 配色 + `NoDropShadowWindowHint`（Windows 上清 `CS_DROPSHADOW`）+ 圆角
  - 锚点三选一：`show_at_cursor`（右键 / 键盘）、`show_at(menu, widget, pos)`（右键回调的局部坐标）、`show_below(menu, widget)`（按钮下拉）
- **禁止**"`exec()` 之后比较 `last_action`"：菜单结果要用 `QMenu.exec()` 的**返回值**（`QAction`）或直接给 `add_action` 传回调
- 为什么：贴边翻转 / 多屏 / 缩放 / 键盘导航交给 Qt；自研实现只能在"单屏 + 100% 缩放"下碰巧正确，
  且旧实现的 `exec()` 依赖 `destroyed` 结束内嵌事件循环，实际**永不返回**（`close()` 不销毁控件），
  导致 5 个右键菜单失效并逐次遗留内嵌事件循环（见 `ERRORS #030`）
- 检查：`tests/test_menus.py`（flags / 可执行 / `exec` 必须返回）+ 代码里不得再出现 `context_menu` 导入

**Q-H16 动效（Animation）**
- **只允许** opacity / 位移；时长 ≤180ms；缓动 `OutCubic`；模板见 `src/ui/animations.py`
- **禁止**：动画化布局尺寸（宽高/间距）、侧边栏手风琴（保持 `show()`/`hide()` 即时）、
  对 QSS 画出来的图形做 transform（QSS 没有 transform，见 `ERRORS #031`）
- 动画对象必须保引用（`animations._RUNNING`），控件销毁时停止
- 有总开关 `animations.set_enabled(False)`（用户觉得闪/卡时一键关掉）
- 检查：`tests/test_animations.py`（结构守卫：模块里不得出现几何动画；结束后摘掉透明效果；
  像素与动画前一致）

**Q-H17 圆角绘制**
- 输入类控件（`QLineEdit` / `QComboBox` / `QAbstractSpinBox`）**必须关掉原生方框**
  （`setFrame(False)`）：Windows 上原生方框是直角，会从 QSS 圆角外露出"角点"
  → 已由 `theme.install_rounded_frame_fixer()` 全局钩子自动处理（带 `border-radius` 的才关）
- 需要"绝对可控"的圆角时：**自绘**（`QPainter` + `Antialiasing`，QSS 只留透明底）。
  已有两族自绘控件：`widgets/rounded_input.py`（输入）、`widgets/rounded_button.py`（按钮）
  → 判据与"为什么不能全局统一"见 `design/INDEX.md` §5（渲染路径）与 `ERRORS #032`
- 检查：`tests/test_ui_wiring.py::test_rounded_inputs_drop_native_frame`

**Q-H18 输入框样式唯一化**
- `QLineEdit` / `QComboBox` 的样式**只能**来自 `theme.input_qss()` / `theme.combo_qss()`；
  面板不得再写自己的 `_input_qss` / `_combo_qss`（只能委托）
- 统一参数：半径 `RADIUS["radius_md"]`、高度 `FIELD_H`、字号 `SIZE_BODY_S`、
  `border: 1px solid border`、`:focus` 用强调色
- 为什么：2026-10-16 实测同时存在 5 套副本（全局半径 4 / 面板半径 8、padding 与字号各不相同），
  同一个界面上输入框外观不一致，也让"圆角角点"这类问题难以定位
- 检查：`tests/test_ui_wiring.py` 断言各面板的 `_input_qss()` 与 `theme.input_qss()` 完全一致

**Q-H19 UI 规范入口唯一**
- 所有 UI 规范（令牌 / 样式工厂 / 菜单与动效模板 / 弹窗规范 / 原型）**登记在 `design/INDEX.md`**，
  动 UI 前先读它；表里没有对应规范时**先问用户**，确认后再创建并补进该文件
- 为什么：2026-10-16 实测同时存在 5 套输入框样式、菜单有 5 种坐标写法、令牌文档与实现漂移多年，
  根因都是"没有单一入口，各处各写一套"
- 检查：`design/INDEX.md` 存在且含权威位置表；`AGENTS.md` §3「UI 规范入口」为流程约束

## I. 异常与错误处理

**Q-I1 禁止无理由盲捕获**：`except Exception` / 裸 `except:` 必须二选一——
(a) **收窄**到具体异常类型；或
(b) 作为**显式边界**（线程入口 / 事件循环槽 / 第三方代码 / 外部服务）保留，
    并加一句理由注释 + `# noqa: BLE001`
- 为什么：盲捕获把 `AttributeError`、`KeyError` 这类真 bug 伪装成正常流程。
- 检查：`ruff --select BLE001`（`src/ui/**` 已在 ruff 配置中豁免，理由见 `pyproject.toml` 注释）。
- 现状：`✔` 2026-10-16：服务/脚本层 **6 处收窄 + 12 处标注边界**；UI 层经 per-file-ignore 豁免。

**Q-I2 禁止静默吞异常**：`except ...: pass` 必须改为 `logger.debug/warning(..., exc_info=True)`，或注释说明为何可忽略
- 为什么：静默吞异常是"AI 说做了、实际没做"这类故障的温床。
- 检查：`scripts/check_quality.py` 的 `SILENT` 项（AST，**含具名异常**）+ `ruff --select S110`。
- 现状：`✔` 2026-10-16：**40 处** `except: pass` 已改为 `logger.debug(..., exc_info=True)`，并为缺 logger 的
  20 个模块补齐。审计后又发现 **ruff S110 漏检具名异常**（`except (A, B): pass`），
  剩余 2 处已改用 `contextlib.suppress(...)`，现为 **0 处**，且由 AST 门禁兜住该类漏检。

## N. 命名约定

**Q-N1 标识符**：模块 `snake_case`、类 `PascalCase`、常量 `UPPER_SNAKE`、私有 `_` 前缀

**Q-N2 信号命名** `xxx_changed` / `xxx_requested` / `xxx_ready`，与语义一致

**Q-N3 槽命名** `_on_<信号源>_<事件>`

**Q-N4 文件与主类同名**（如 `habit_panel.py` ↔ `HabitPanel`）

**Q-N5 i18n**：UI 显示文本必须经 `tr()` 取得，禁止硬编码中文；键格式 `<area>.<subarea>.<name>`
（如 `panel.task.title`、`dialog.course.btn_save`、`tray.exit`）——**文字只存在于语言包**，代码里只有键
- 语言包分两层：`src/i18n/zh-CN.json`（主）+ `src/i18n/zh-CN.d/<模块>.json`（**分片**，按模块拆分，
  便于定位"某处文字在哪"与并行维护）
- 带变量用占位符：`tr("status.week", n=5)` ↔ `"第 {n} 周"`；缺语言包时**回退** zh-CN（不抛异常）
- 检查：`tests/test_i18n.py` 四道（用到的键必须存在 / 键必须命名空间化 / 键不得重复定义 / 回退与占位符）
  + `scripts/check_quality.py` 的 `I18N` 项（"未走 `tr()` 的中文字面量"计数，不得超过 baseline）
- 现状：`🔄` 2026-10-16：**692 → 106**（`src/ui` 未国际化中文字面量）。
  **不迁移**的对象（度量里已排除，不算遗漏）：日志实参、字典键、docstring、数据值/状态值、
  给 AI 的 prompt/快照文本、样式表内容、内部哨兵值。
  剩余 106 处的性质与后续见 `PLAN P7`。

**Q-N6 资源与图形命名**：图标 `ic_<name>_<size>`（如 `ic_add_16`）；图片 `img_<name>`；统一放 `resources/`
- 现状：`✔` 2026-10-15：已建 `resources/`，`image.png` 已归位（`app.py` 的 `_ICON_PATH` 同步更新）。

**Q-N7 信号事件后缀受控**：`_changed`（数据变更）· `_requested`（用户意图）· `_ready`（异步就绪）·
`_failed`（失败）· `_finished`（结束）
- 现状：`?` 现有 `ddl_alert`（名词）、`reminder_notify`（动词）等不符约定；**新信号按本约定命名**，旧的逐步迁移。

## P. 目录与文件结构

**Q-P1 顶层目录白名单**：`src/ scripts/ tests/ plugins/ data/ resources/ MD-files/ dev-logs/ .github/ design/`
+ 约定根文件（`main.py` `AGENTS.md` `README.md` `PLAN.md` `ERRORS.md` `pyproject.toml` `requirements*.txt`
  `.gitignore` `.importlinter` `.secrets.baseline`）；新增顶层目录必须同步 `AllTheFiles.md` / `README.md` / 本文件
- 检查：`scripts/check_quality.py` 的 `TOP-DIR` 项（只查 **git 跟踪**的顶层项，本地垃圾不影响 CI）。
- 现状：`✔` 2026-10-16：`design/`（UI 规范入口）已入白名单；根目录的第三方 skill
  `hermes-skill-life-assistant.md` 已归档到 `MD-files/archive/`（与 R-002 冲突，见该目录 README）。

**Q-P2 `data/` 是用户数据（含密钥），永不进发行版；`resources/` 是运行时资源**

**Q-P3 `src/` 分层目录固定**：`models/` `services/` `ui/{components,panels,widgets,styles}/` `i18n/`

**Q-P4 发行版目录**：`dist/LifeAssistant-<version>-win64/`；包含 入口/打包产物/`resources/`/`plugins/`/README；
排除 `data/` `.venv/` `.git/` `MD-files/` `dev-logs/` `tests/` `PLAN.md` `AGENTS.md`
