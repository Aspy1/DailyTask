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
> `现状`：`✔ 达标` / `✗ 违规（见 PLAN）` / `? 未核查`。
> 章节：**A** 结构分层 · **B** 线程并发 · **C** 复杂度资源 · **D** 日志调试 · **E** 安全数据 ·
> **F** 测试 · **G** 文档 · **H** UI 与令牌 · **I** 异常处理 · **N** 命名约定 · **P** 目录结构。

---

## A. 结构与分层

**Q-A1 单一职责：函数 ≤ 60 行、类 ≤ 400 行、单文件 ≤ 800 行**
- 阈值：**采用默认（2026-10-15 定）**。
- 为什么：超过认知上限后，改动成本与 bug 率非线性上升。
- 检查：行数脚本（`dev-logs/2026-10-15-现状基线.md` §1b）、`radon`、`vulture`。
- 现状：`✗` 文件超限 2 个（`habit_panel.py` 863、`schedule_view.py` 848）；类超限 5 个（`ScheduleView` 828、`SettingsPanel` 716、`InventoryPanel` 663、`MainWindow` 543、`AIService` 406）。

**Q-A2 依赖单向：UI → Service → Model，禁止反向 import**
- 为什么：反向依赖使分层失效、难以测试。
- 检查：`import-linter`（contract: layers）。
- 现状：`✗` `src/services/api_service.py:10` import `src.ui.styles.theme`。

**Q-A3 同一外部能力只保留一套适配**
- 为什么：多套实现必然漂移，改一处漏一处。
- 检查：人工/关键字扫描。
- 现状：`✗` 天气有 3 套（`weather_service` / `api_service` / `ai_service` 内联），天气码映射两份。

**Q-A4 禁止死代码**
- 为什么：误导读者、掩盖真实路径。
- 检查：`vulture src scripts --min-confidence 80`。
- 现状：`✗` `main_window._shopping_label`（从未创建）、`_placeholder("吃什么")`。

**Q-A5 不用继承表达"部分复用"**
- 为什么：继承是 is-a，不是"借用几个方法"。
- 现状：`✗` `models/scene_archive.py` 继承 `BaseJsonModel` 又整套重写 `load/save`。

## B. 线程与并发

**Q-B1 Qt 对象只在创建它的线程访问；跨线程只经 signal/slot（队列连接）**
- 检查：人工 + `pytest-qt`。
- 现状：`?` 需核查 UI 与服务边界。

**Q-B2 共享可变状态必须加锁或明确单线程归属**
- 为什么：无锁的 dict 并发读写会产生撕裂读/丢失更新。
- 检查：人工审查 + 并发压测。
- 现状：`✗` Model 的 `_data` 被 worker 线程改（`ai_service.py:246-248`），同时主线程 `data_manager.py:66-85` 在读；`RUF012`（类级可变默认值）**5 处**，如 `ai_service.py:322/357` 的缓存字典。

**Q-B3 禁止 `QThread.terminate()`**
- 现状：`✗` `api_service.py:169`。

**Q-B4 禁止在 worker 中改动进程级全局状态**（`sys.stdout`、`os.environ`、模块级缓存）
- 现状：`✗` `actions.py:557-563` 用 `contextlib.redirect_stdout`；`ai_service.py:322,357` 类属性缓存。

**Q-B5 QObject/QThread 生命周期必须显式回收**（`deleteLater` / 单一归属），禁止反复 `new` 不释放
- 现状：`✗` `weather_service.py:118`（单一 `_worker` 槽）、`api_service.py:147`。

**Q-B6 禁止闭包捕获循环变量**（`lambda` / 生成器引用外层循环变量）
- 为什么：所有闭包共享同一变量 → 偶发跳错项，且难复现。
- 检查：`ruff --select B023`。
- 现状：`✗` `B023` **3 处**。

## C. 复杂度与资源

**Q-C1 圈复杂度 ≤ 10（B 级）**
- 阈值：**≤ 10（B 级，采用 radon 默认分档；2026-10-15 定）**。
- 检查：`radon cc -n C -s src scripts`。
- 现状：`✗` **34 个函数 ≥ C**（平均仅 A/3.52）。最差：`send_digest.build_digest`(75,F)、`schedule_view._refresh`(60,F)、`_build_snapshot`(37,E)；C(15–17) 11 个。见 `dev-logs/2026-10-15-现状基线.md`。

**Q-C2 主线程禁止阻塞**（网络/IO/大循环）
- 现状：`✗` `ai_service._fetch_deepseek_balance()` / `_fetch_weather_for_prompt()` 在发送路径同步请求。

**Q-C3 全表扫描类统计需评估规模上限或加缓存**
- 为什么：面板刷新 + 30s 状态栏会反复触发。
- 现状：`✗` 记账/考试统计每次 O(n)；且 `habit.py:122-129` monthly 分支遍历层级写错（每月习惯永远判"未完成"）。

**Q-C4 文件/线程/连接等资源必须显式释放**
- 检查：`ruff --select SIM115` + QThread 人工核查。
- 现状：`✗` `SIM115`（文件未用上下文管理器）**3 处**；QThread 反复 `new` 不 `deleteLater`（`weather_service.py:118`、`api_service.py:147`）。

## D. 日志与调试输出

**Q-D1 非脚本代码禁用裸 `print()`，统一 `logging`**
- 为什么：无法分级、无法关闭、污染 stdout（还会与 `redirect_stdout` 互相干扰）。
- 检查：`ruff` 规则 `T20`，或 `grep -rn "print(" src`。
- 现状：`✗` `src/` 内 **5 处**，全部在 `models/task.py:85-97`（`TaskModel.complete()` 的调试输出）。`scripts/*` 的 print 属 CLI 契约，已在 ruff 配置中排除。

**Q-D2 日志按级别使用**：`debug` 默认关闭；异常路径 `logger.error(..., exc_info=True)`；不在热点循环里做字符串拼接。

**Q-D3 日志语句必须**"可静态剥离"**：独立表达式语句、无副作用实参、不处于"删除后块为空"的位置
- 为什么：为将来构建瘦身留路（否则 AST 剥离会改行为）。
- 检查：自定义 AST 检查（见 PLAN E-2）。
- 现状：`✗` 当前无此约束。

**Q-D4 禁止把密钥、token、个人数据写入日志或异常信息**

## E. 安全与数据

**Q-E1 密钥不进代码 / 日志 / git**（本机 `data/settings.ini` 为明文，已在 `.gitignore`）
- 检查：`gitleaks` / `detect-secrets`。

**Q-E2 数据写入必须原子（`os.replace`）且经 Model 或 `actions.py`**（= R-002）
- 现状：`✔` `models/base.py` 已实现；`✗` 双写路径未统一。

**Q-E3 外部输入必须校验**（AI 生成命令、JSON 导入、插件）

**Q-E4 数据 schema 与迁移**：每个 `data/*.json` 的 `_version` 与 `migrate()` 必须有测试；
字段变更必须提供向后兼容或迁移路径（跨端共写：桌面 + TG + GitHub Actions）
- 现状：`?` `models/base.py` 有迁移框架骨架，但无迁移测试。

**Q-E5 版本号单一来源**：以 `pyproject.toml` 的 `version` 为准，`i18n` / `README` / 发行包名由其派生
- 现状：`✗` 曾出现 `app.version` 0.3.0 与 README v0.9.0 不一致（已临时对齐，尚未做到派生）。

## F. 测试与可验证性

**Q-F1 新增/修改行为必须有测试**（见 `AGENTS.md` DoD）
- 现状：`✗` 覆盖率 **1%**（7442 语句 / 7384 未覆盖）；仅 `scripts/actions.py` 有冒烟测试，`src/` 全 0%。

**Q-F2 契约必须可校验**：prompt ↔ `actions.py` ↔ TG skill 的命令集一致
- 现状：`✔` `tests/test_prompt_consistency.py`（3 处已知缺口以 xfail 固化）。

**Q-F3 改变更完成后必须自检**：import 完整、信号已连接、控件已初始化

## G. 文档

**Q-G1 文档只写代码表达不了的东西**（跨文件时序、不变量、为什么、外部契约）；签名/参数/字段不抄
- 现状：`✗` 34 份 `.py.md` 逐文件抄签名（见 PLAN A-1）。

**Q-G2 文档必须可校验，或明确标注 `*（待补）*`**；禁止"参见源码"式占位
- 现状：`✗` `task.py.md` 等为批量骨架。

**Q-G3 文档体系固定为**：`AGENTS.md`（流程/环境）· `PLAN.md`（计划与体检）· `CODE_STANDARDS.md`（规范）·
`ARCHITECTURE.md`（运作原理）· `ERRORS.md`（坑）· `dev-logs/`（变更史）· `README.md`（概览）。
**不再维护逐文件 `.py.md`**
- 现状：`✔` 2026-10-15 完成（34 份 `.py.md` 与 `FORMAT_SPEC.md` 已删，新增 `ARCHITECTURE.md`）。

**Q-G4 单一真值**：同一事实只允许一处权威来源；文档与代码冲突时以**代码**为准并立即修文档
- 现状：`✗` `DESIGN_TOKENS.md`(规格) 与 `theme.py`(实现) 漂移；根 `ERRORS.md` 与 `MD-files/ERRORS.md` 重复。

## H. UI 与设计令牌

**Q-H1 颜色 / 字号 / 间距 / 圆角一律走 token，禁止字面量**（`#hex`、`rgb()/rgba()`、`Npx`、`QFont(..., int)`）
- 检查：`scripts/check_ui_tokens.py`（见 PLAN G-2）；或先 `grep -rn "#[0-9a-fA-F]\{3,8\}" src/ui`。
- 现状：`✗` `#fff` 约 15 处、`settings_panel.py:296/299`、`app.py:65/82/115`、`toggle_switch.py:46`、`ai_panel.py:20/173` 等。

**Q-H2 令牌单一真值**：规格文档由令牌文件**生成**，禁止规格与实现两份手写
- 现状：`✗` `DESIGN_TOKENS.md` 与 `theme.py:TOKENS` 已漂移。

**Q-H3 令牌命名：`<domain>_<variant>_<property>_<state>`，各槽取受控词表**

| 槽 | 取值（受控） |
|---|---|
| `domain` | `bg` `fg` `border` `divider` `accent` `state` `btn` `badge` `nav` `card` `input` `chip` `icon` `space` `radius` `size` `dur` `ease` `shadow` |
| `variant` | 组件变体：`primary` `secondary` `ghost` `danger` `success` `warning` `info` `subtle` |
| `property` | `bg` `fg` `border` `fill` `radius` `size` `duration` … |
| `state` | `hover` `active` `pressed` `disabled` `selected` `on`（如 `fg_on_accent`） |

- 示例：`bg_card`、`fg_primary`、`state_danger_subtle`、`btn_primary_bg_hover`、`nav_selected_fg`、`fg_on_accent`
- 禁止用原始色名当令牌名（`red`/`green`/`yellow`）；禁止把尺寸混进颜色集（如 `badge_radius`）
- 现状：`✗` 现存 `red/green/yellow/orange`、`badge_radius` 等违反。

**Q-H4 QSS 选择器仅 `#objectName`，禁止类名选择器**（= R-008）
- 现状：`✗` `habit_panel.py:54/58` 的 `_HabitCard { … }`。

**Q-H5 颜色必须属于主题 token 集合**（禁止 `settings_panel.py:296/299` 那种非主题色）

**Q-H6 视觉克制**：accent 像素面积 < 5%；禁止第四种色相、纯黑/纯白（人工核对）

**Q-H7 令牌分三层**：`palette`（原始色板）→ `semantic`（角色：bg/fg/border/state）→ `component`（btn/badge/nav/card/input）
- 组件层只允许引用 `semantic` / `component`，**禁止直接引用 `palette`**

**Q-H8 令牌文件与生成链**：`src/ui/styles/tokens.json`（唯一真值）→ `theme.py` 加载并生成 QSS →
`MD-files/DESIGN_TOKENS.md` 由脚本生成；组件经 `get_colors()` 取 `semantic` / `component` 名
- 现状：`✗` 真值目前是 `theme.py` 里的 Python 字面量，且规格文档手写。

## I. 异常与错误处理

**Q-I1 禁止盲捕获**：`except Exception` / 裸 `except:` 必须收窄到具体异常，或在捕获后重新抛出/记录
- 为什么：盲捕获把 `AttributeError`、`KeyError` 这类真 bug 伪装成正常流程。
- 检查：`ruff --select BLE001`。
- 现状：`✗` `BLE001` **50 处**。

**Q-I2 禁止静默吞异常**：`except ...: pass` 必须改为 `logger.debug/warning(..., exc_info=True)`，或注释说明为何可忽略
- 为什么：静默吞异常是"AI 说做了、实际没做"这类故障的温床。
- 检查：`ruff --select S110`。
- 现状：`✗` `S110` **24 处**。

## N. 命名约定

**Q-N1 标识符**：模块 `snake_case`、类 `PascalCase`、常量 `UPPER_SNAKE`、私有 `_` 前缀

**Q-N2 信号命名** `xxx_changed` / `xxx_requested` / `xxx_ready`，与语义一致

**Q-N3 槽命名** `_on_<信号源>_<事件>`

**Q-N4 文件与主类同名**（如 `habit_panel.py` ↔ `HabitPanel`）

**Q-N5 i18n key 命名空间**：`<area>.<subarea>.<name>`（如 `panel.task.title`、`dialog.course.edit`、`tray.exit`）；
UI 显示文本必须经 `tr()` 取得，禁止硬编码中文
- 现状：`✗` `zh-CN.json` 为扁平键；全项目仅约 47 处 `tr()` 调用。

**Q-N6 资源与图形命名**：图标 `ic_<name>_<size>`（如 `ic_add_16`）；图片 `img_<name>`；统一放 `resources/`
- 现状：`✗` 根目录 `image.png` 未归位。

**Q-N7 信号事件后缀受控**：`_changed`（数据变更）· `_requested`（用户意图）· `_ready`（异步就绪）·
`_failed`（失败）· `_finished`（结束）
- 现状：`?` 现有 `ddl_alert`（名词）、`reminder_notify`（动词）等不符约定；**新信号按本约定命名**，旧的逐步迁移。

## P. 目录与文件结构

**Q-P1 顶层目录白名单**：`src/ scripts/ tests/ plugins/ data/ resources/ MD-files/ dev-logs/ .github/`
+ 约定根文件（`main.py` `AGENTS.md` `README.md` `PLAN.md` `ERRORS.md` `pyproject.toml` `requirements*.txt` `.gitignore`）；
新增顶层目录必须同步 `AllTheFiles.md` / `README.md` / 本文件
- 现状：`✗` `resources/` 尚不存在，`image.png` 落在根目录。

**Q-P2 `data/` 是用户数据（含密钥），永不进发行版；`resources/` 是运行时资源**

**Q-P3 `src/` 分层目录固定**：`models/` `services/` `ui/{components,panels,widgets,styles}/` `i18n/`

**Q-P4 发行版目录**：`dist/LifeAssistant-<version>-win64/`；包含 入口/打包产物/`resources/`/`plugins/`/README；
排除 `data/` `.venv/` `.git/` `MD-files/` `dev-logs/` `tests/` `PLAN.md` `AGENTS.md`
