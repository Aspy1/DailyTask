# PLAN.md — 大框架整改计划

> 用途：记录本项目**工程/架构层面**的整改项与决策，避免散落在对话里丢失。
> 与 `dev-logs/` 的分工：dev-logs 记"已发生的变更"；本文件记"待做 / 在做 / 已定方向"。
> 最后更新：2026-10-16

## 状态图例

- `[已定]` 方向已确认，待执行
- `[执行中]`
- `[已完成]`
- `[待议]` 需要用户拍板

---

## 执行顺序（Roadmap）

> 原则：**先用数据定级 → 再定规范 → 再让规范变成门禁 → 最后才动架构与发布。**
> 每项详细内容见下方同名章节；ID 不变，仅重排先后。

**P0 度量（用数据说话）**
- `E` 现状基线 ✅ **已完成**（2026-10-15，报告见 `dev-logs/2026-10-15-现状基线.md`）
- `D-1` 规范骨架 ✅ 已完成
- ✅ 阈值已定：函数 ≤60 行 / 类 ≤400 行 / 文件 ≤800 行、圈复杂度 ≤10（采用默认，2026-10-15）

**P1 规范定稿 ✅ 已完成（2026-10-15）**
- 见 `MD-files/CODE_STANDARDS.md` 定稿 v1.0：命名（Q-N）· 令牌（Q-H）· 目录（Q-P）·
  文档体系（Q-G3/Q-G4）· 异常处理（Q-I）· schema/版本号（Q-E4/E5）
**P1b 规范落地（把决策应用到代码与文档）**
- `A-1` ✅ 写 `ARCHITECTURE.md` + `git rm` 34 份 `.py.md` + `FORMAT_SPEC.md`
- `A-2` ✅ 合并两份 `ERRORS.md`；`A-3` ✅ `AllTheFiles.md` 瘦身（430→311 行）
- `G-1` ✅ `tokens.json` 单一真值 + `theme.py` 改加载（G-1a）+ `gen_design_tokens.py` 生成 `DESIGN_TOKENS.md`（G-1b）；
  ⏳ G-1c `palette → semantic → component` 分层未做
- `H-1` / `Q-P1` ✅ 建 `resources/`、`image.png` 归位（`app.py` `_ICON_PATH` 同步；`rewrite_history.py` 路径同步）
- `Q-N5` i18n key 命名空间落地

**P2 自动检查（把规范变成门禁）**
- `B-1` ✅ `[tool.ruff]` 已在 `pyproject.toml` 固定（基线可复现）；`mypy` 待接
- `D-2` 规范检查器（`scripts/check_standards.py` + 审查 skill）
- `G-2` UI 令牌检查器（`scripts/check_ui_tokens.py`，先只检查、不 `--fix`）
- ✅ `B-6` CI 跑 pytest + lint（`.github/workflows/ci.yml`：ruff → 令牌检查器 → 令牌文档同步 → pytest）
- `[待议]` `I-8` pre-commit 钩子（本地钩子；CI 已覆盖同一组检查）
- `[待议]` `I-16` 依赖审计（`pip-audit`）

**P3 架构与正确性整改（顺序据基线数据重排）**
- ✅ ① `B-5` 线程安全 + `RUF012`（2026-10-16 完成）→ 详见 `dev-logs/2026-10-16-线程安全整改.md`
- ✅ ② `I-2` 异常处理（2026-10-16 完成）→ 详见 `dev-logs/2026-10-16-异常处理整改.md`
- ✅ ③ `B-2` 复杂度长尾（2026-10-16 完成：**radon ≥C 清零**）→ `dev-logs/2026-10-16-复杂度重构.md`
- ✅ ④ `Q-B6` 闭包捕获循环变量（`B023` ×3 已于 2026-10-16 修复：`a189421`，ruff 现为 0）
- ✅ ⑤ 死代码 / 未用导入清理（2026-10-16 完成，ruff 315 → **0**）→ `dev-logs/2026-10-16-静态检查清零.md`
- ✅ ⑥a `I-4` 类型注解（2026-10-16）：返回类型全量补齐并纳入 ruff 规则集 → `dev-logs/2026-10-16-类型注解与schema.md`
- ✅ ⑥b `I-10` 数据 schema 守卫（2026-10-16）：`_version` 自愈 + 守卫测试（并据此补齐 `data/inventory.json`）
- `[待议]` ⑥c `I-3` / `Q-N5` i18n：现状是"单语言却挂着 i18n 层"（仅 `zh-CN.json`，约 47 处 `tr()` 调用，大量硬编码中文）。
  **建议**：不做全量迁移，改为"新 UI 文本必须走 `tr()`，存量改到即补"（与类型注解同策略）；若确定不需要多语言，则整层移除。**需你裁决。**
- ✅ ⑦ 资源归位（`resources/` 建好、`image.png` 就位、`schedule_snapshot.txt` 停止跟踪）

**P4 发布**
- `C-1` 注释/日志处理、`C-2` 日志写法规范
- `H-2` 发行版目录与命名
- `I-15` 性能基线门禁

**P5 功能可用性排查与修复 ✅ 已完成（2026-10-16）**
- ✅ `F-1` 对 README「功能」/ 本文件 ✅ 项做**可执行**排查（离屏 Qt + 临时目录，32 项断言）
- ✅ `F-2` 15 项缺陷全部修复（数据解析 2 · 考试提醒 2 · 数据流 2 · AI 命令契约 4 · 主题入口 1 ·
  主线程网络 1 · 日期语义 1 · 模型默认值 1 · 文档漂移 1）
- ✅ `F-3` 测试 92 → **149 passed，5 xfail 全部转正为真实断言**
- ✅ `F-6` **场景存档功能弃用**（2026-10-16）：删 `scene_archive.py` + `scene_manager_dialog.py`（约 300 行），
  位置并入「天气设置」的纬度/经度，学期交给学期切换；旧 `scenes_meta.json` 的位置由 `migrate_legacy_scene_location()` 一次性迁移
- ⏳ `F-4` README「吃什么」仍是占位面板（"即将上线"），未实现
- ⏳ `F-5` 真实托盘 / 单实例 / 自启 / SMTP / GitHub Actions 运行未验证（需真实环境与凭据）
- 详见 `dev-logs/2026-10-16-功能可用性排查.md`

---

## A. 文档体系

### A-1 `[已完成]` 废弃逐文件 `.py.md`，改用单一 `ARCHITECTURE.md`

**决策**：Pivot。文档只写"代码表达不了的东西"（跨文件时序、不变量、为什么、外部契约）；
签名/参数/返回值/字段一律不抄。

**依据（实测）**：

- 34 份 / 122.6 KB ≈ 源码体积的 24%；若要 agent "按序通读"即大量烧上下文。
- 内容是**批量生成骨架**：`task.py.md` 全部函数合同为"核心逻辑：参见源码 / 返回值：*（待补）*"，
  文件末行自述"本文档为批量生成骨架"。
- **系统性失实**：把只读查询 `pending/completed/active/get_overdue` 标为"副作用：修改 `self._data`"，
  并给只读属性编造 setter；同时**漏掉真正有值的逻辑**（`_auto_archive`、`_repair_course_names`、`GENERIC_TAGS`）。
- 覆盖不全：11 个源文件无文档，恰含最复杂的 `inventory_panel.py`(565 行)、`weather_service.py`、`api_service.py`。

**落地步骤**：

1. 新建 `ARCHITECTURE.md`（≤300 行）：分层、初始化顺序、数据流与信号链、并发模型、
   关键不变量（ID 生成 / 原子写入 / `schedule_date()` 的 0–1 点语义 / 双写路径）、各 `data/*.json` schema 总表。
2. `actions.py` 命令契约表（命令 + 参数 + 示例 + handler + CLI/prompt/TG 一致性），**用测试把关**，不手工抄。
3. 函数级信息就近写：代码内 docstring + 类型注解。
4. 改 `AGENTS.md` §1 / §8 指向 `ARCHITECTURE.md`。
5. 废弃或改写 `MD-files/FORMAT_SPEC.md`。
6. `git rm` 那 34 份 `.py.md`（留痕，可回滚）。

**已知硬规则冲突**：`AGENTS.md` §1（必须读 .py.md）、§8（改代码同步 .py.md）、
`MD-files/FORMAT_SPEC.md` §二（.py.md 模板）、`AllTheFiles.md` 文件详情表 —— 执行时一并改。

**✅ 2026-10-15 完成**：`ARCHITECTURE.md` 已写（10 节：分层/启动顺序/三条数据路径/信号链/并发/不变量/schema/扩展/债务）；
34 份 `.py.md` 与 `FORMAT_SPEC.md` 已 `git rm`；`AGENTS.md` §1/§8 已改指；`AllTheFiles.md` 加变更横幅并移除失效链接。

### A-2 `[已完成]` 合并两份 `ERRORS.md`

- ✅ 2026-10-15：两份内容完全不同（根 6 条 vs `MD-files` 13 条），已合并为根 `ERRORS.md` 共 **19 条**；
  索引改为**按条目号**（去掉写死的 `L28-L50` 行号）；`MD-files/ERRORS.md` 已删除。

### A-3 `[已完成]` `AllTheFiles.md` 瘦身

- ✅ 2026-10-16：三章（初始化顺序 / 数据路径 / 信号总览）**正文已删除**，只留指向 ARCHITECTURE 的指针（−75 行）；
  「文件详情」链接表改为指针；DR 条目的 `详见 xxx.py.md` 死链已清除；`MD-files/全量审核.md`
  （针对已删 `.py.md` 的审查笔记）已删除。**文件 430 → 311 行**。
- 保留并作为权威：索引 · 全局常量（R-005 登记）· 术语映射 · 操作步骤清单 · 决策记录（DR-xxx）· 项目级禁止清单（R-001~R-008）。

---

## B. 代码质量与工具链

### B-1 `[待议]` 静态检查接入：ruff（含 bugbear/bandit 规则）+ mypy/pyright

### B-2 `[待议]` 复杂度与死代码基线：radon（CC/MI）+ vulture

### B-3 `[待议]` 内存泄漏检查：tracemalloc + objgraph（必要时 memray）

### B-4 `[待议]` 计时日志：是否要为每个函数加耗时日志（倾向：不加，改用采样/行级 profiler）

### B-5 `[待议]` 线程安全整改（详见对话中的具体问题清单）

### B-6 `[待议]` CI 增加 `pytest` + lint（当前 CI 只跑邮件摘要）

---

## C. 发布瘦身

### C-1 `[待议]` 是否剥离注释/日志

**倾向结论**：不建议"剥离源码"，而是

- 发行版走**打包**（PyInstaller/Nuitka）→ 只有字节码，注释本就不存在；
- 调试输出改 `logger.debug()`（默认不输出）→ 发布零成本；
- 若确需源码瘦身：注释/docstring 用现成工具（`python-minifier`、或 stdlib `compileall -OO` 发 `.pyc`）；
- **日志调用没有可靠现成工具**，静态删除是语义改写，风险高；需自建 AST 脚本且必须先定"日志写法规范"。

### C-2 `[待议]` 日志写法规范（若坚持做 AST 剥离）

---

## D. 规范与自动检查

> 结论：把"如何构建优雅/行之有效/安全的软件"落成**可检查的规范性语句**，
> 放在 `MD-files/CODE_STANDARDS.md`（**定稿 v1.0**，条目 Q-A…Q-P）。

### D-1 `[已完成]` 规范文档定稿 v1.0

- `MD-files/CODE_STANDARDS.md`：格式为 **规则 → 为什么 → 如何检查 → 现状**，`现状` 标注 `✔ / ✗（见 PLAN）/ ?`。
- 章节：**A** 结构分层 · **B** 线程并发 · **C** 复杂度资源 · **D** 日志调试 · **E** 安全数据 ·
  **F** 测试 · **G** 文档 · **H** UI 与令牌 · **I** 异常处理 · **N** 命名约定 · **P** 目录结构。
- 命名/令牌/目录/文档体系/异常处理的**决策已定**；对应落地见 P1b。

### D-2 `[待议]` 文件级规范检查器（脚本 + skill 两步）

- 目标：输入一个文件，输出"违反了哪几条 Q-xxx + 证据（行号）"。
- **脚本**（优先，可进 CI）：`scripts/check_standards.py`，只做**可确定判断**的规则——
  `print()` 残留、行数/类大小、圈复杂度阈值、`QThread.terminate()`、类属性可变缓存、
  `redirect_stdout`、写死行号等（AST + 正则即可）。
- **skill / 审查清单**：处理"需要判断"的规则（分层方向、命名、是否优雅），
  作为人工或 AI 审查的 checklist 输出。
- 检查器输出即 `CODE_STANDARDS.md` 的 `现状` 基线，两者保持同步。

### D-3 `[待议]` 注释与日志的构建期处理

- **注释/docstring**：用 stdlib `compileall -OO`（发布 `.pyc`）或 `python-minifier`；
  **不自研剥离器**。
- **日志**：优先"运行时级别控制"（`logger.debug` + 默认关闭），**不做静态删除**；
  若确需静态剥离，先满足 Q-D3 的"可剥离写法"，再用 `ast.NodeTransformer`，
  并配"剥离后行为不变"的测试。

### D-4 `[待议]` 时空占用与内存泄漏的考察手段

- 时间：`py-spy record` / `scalene` / `line_profiler`；基准对比用 `pytest-benchmark`。
- 内存：`tracemalloc` 两次快照对比 → `objgraph` 查引用链 → 必要时 `memray`。
- Qt 专项：`pytest-qt` + 对象计数，专门盯 QThread/QObject 泄漏。
- 触发时机：怀疑泄漏/卡顿时跑；不常驻。

### D-5 `[待议]` 规范来源（后续逐步补充）

- 参考来源：PEP 8/20/257、Google Python Style Guide、SOLID/SRP、Qt 线程亲和性规则、
  OWASP（密钥/输入）、"make illegal states unrepresentable" 等。
- 原则：**只落成"本项目的可检查规则"，不照抄**；每条都要能回答"怎么查、现状如何"。

---

## E. `[已完成]` 现状基线（2026-10-15）

**报告**：`dev-logs/2026-10-15-现状基线.md`；已回填 `CODE_STANDARDS.md` 的「现状」列。
**工具**：ruff 0.17.0 / radon 6.0.1 / vulture 2.16 / pytest-cov 7.1.0。

| 维度 | 结果 |
|---|---|
| 圈复杂度 | 686 块，平均 **A(3.52)**；**34 个函数 ≥ C**。最差 `send_digest.build_digest`(75,F)、`schedule_view._refresh`(60,F)、`_build_snapshot`(37,E) |
| 体量 | 文件超限 **2**（`habit_panel.py` 863、`schedule_view.py` 848）；类超限 **5**（`ScheduleView` 828 / `SettingsPanel` 716 / `InventoryPanel` 663 / `MainWindow` 543 / `AIService` 406） |
| 死代码 | vulture ≥80% 仅 **3 处**（2 未用导入 + 1 未用变量） |
| Lint | **315 项**（固定规则集）：F401 54 / **BLE001 50** / I001 47 / E702 39 / **S110 24** / F841 17 / E701 11 / UP006 8 / **RUF012 5** / **T201 5** / **B023 3** / SIM115 3 …；可自动修复 131 |
| 覆盖率 | **1%**（7442 语句，`src/` 全 0） |

**已解决**：`pyproject.toml` 已固定 `[tool.ruff]`（select + ignore）→ 基线可复现；
`print` 残留已收敛为 `src/` 内 5 处（`models/task.py:85-97`），`scripts/*` 的 CLI 输出已排除。

---

## G. UI 规范与设计令牌

### G-0 现状（实测）

- 令牌分散在 **3 处且已经漂移**：`MD-files/DESIGN_TOKENS.md`（规格）、`src/ui/styles/theme.py:TOKENS`（实现）、`design-showcase.html` / `sidebar-preview.html`（原型）。
- 具体漂移：`bg_surface` 规格 `#E8E5DE` / 代码 `#E0DDD6`；`border` `rgba(0,0,0,0.06)` / `0.08`；暗色 `bg_root` `#1C1B18` / `#1E1D1A`；暗色 `red` `#E05555` / `#E06060`；字号 `SIZE_TINY/BODY_M/ICON/FAB` 代码有、规格无。
- 规格文件头仍写"版本 1.0 | 分支 ui-redesign | 暗色后续修复"，已过期。
- 组件内硬编码：`#fff` 约 15 处（accent 按钮文字，无对应 token）；`settings_panel.py:296/299` 的 `#4ec9b0`/`#f48771`（非主题色）；`app.py:65/82/115`、`toggle_switch.py:46`、`ai_panel.py:20/173`、`exam_panel.py:64-70`、`scene_manager_dialog.py:53`、`api_test_dialog.py:53`。
- 类名 QSS 选择器（R-008 明禁）：`habit_panel.py:54/58` 的 `_HabitCard { … }`。
- 字号/圆角/间距的 `Npx` 字面量散落各处；`QFont(..., 14)` 硬编码字号。

### G-1 `[进行中]` 令牌格式改造：单一真值 + 分层 + 命名约定

- ✅ **G-1a（2026-10-16）**：建 `src/ui/styles/tokens.json`（48 色键 × 2 模式 + 11 字号 + 字体，值由脚本从 `theme.py` 导出，零转录风险）；`theme.py` 改为加载；**逐键比对确认色值/字号完全未变**。
- ✅ **G-1b（2026-10-16）**：`scripts/gen_design_tokens.py` 从 `tokens.json` 生成 `DESIGN_TOKENS.md` 令牌表（颜色 48×2 + 字号 11；用途注释存于 `tokens.json` 的 `color_notes`/`size_notes`）；`tests/test_design_tokens_sync.py` 守卫漂移。**顺带修正规格中的漂移旧值**（如 `bg_surface` `#E8E5DE`→`#E0DDD6`）。
- ⏳ **G-1c**：引入 `palette → semantic → component` 分层（`Q-H7`）；令牌"类型标签"尚未加。

**原始设计要点（对账）**：
- 单一真值 ✅（`tokens.json`）；规格由脚本生成 ✅
- 分层 ⏳（当前是扁平 48 键 + 长度混入，如 `badge_radius`）
- 命名约定：受控词表见 `CODE_STANDARDS Q-H3`；尺寸域 `space_/radius_/size_/icon_/dur_` 尚未落地
- 类型标签 ⏳；图形资源命名 `ic_<name>_<size>` 见 `Q-N6`

### G-2 `[已完成]` 令牌检查器 + 违规清理

- ✅ **G-2a（2026-10-16）**：`scripts/check_ui_tokens.py` —— 四类检查
  （`COLOR` / `QSS-CLASS` / `QFONT` / `TOKEN-NAME`），支持行级豁免 `# token-check: ignore`；
  默认只报告，`--strict` 供 CI。修掉了把 `tokens.json` 真值当违规、以及把 `QFont` 第 3 参（字重）误判为字号的 bug。
- ✅ **清理（2026-10-16）**：首轮 **50 处 → 0 处**。新增令牌 `fg_on_fill` / `code_bg` / `bg_hover`；
  `course_table` 8 个 `rgba` 改走 `course_color_*`；`_HabitCard`/`_ExamCard` 改 `#objectName`；
  硬编码字号改 `SIZE_*`。由 `tests/test_ui_tokens_clean.py` 守卫。
- ⏳ **G-2b**：`--fix`（libcst codemod）；接 `I-8` pre-commit / `B-6` CI。

**⚠ 本次的可见视觉变化（有意为之）**：
1. `_HabitCard`/`_ExamCard` 的卡片背景/圆角/悬停**现在才真正生效**（此前类名选择器无效）。
2. `settings_panel` 状态色 `#4ec9b0`/`#f48771`（VS Code 风）→ 主题 `green`/`red`。
3. `ai_panel` 输入框字号 11 → `SIZE_CAPTION`(12)。
4. 暗色模式下 `bg_hover` 由黑色 overlay 改为亮 overlay（原先几乎不可见）。
5. `app.py` 图标字母字体 `SimHei` → `FONT_CN`。

---

## H. 目录结构规范（项目内 + 发行版）

### H-1 `[待议]` 项目目录约定

- **顶层白名单**：`src/ scripts/ tests/ plugins/ data/ resources/ MD-files/ dev-logs/ .github/`
  + 约定根文件（`main.py` `AGENTS.md` `README.md` `ERRORS.md` `PLAN.md` `pyproject.toml` `requirements*.txt` `.gitignore`）。
- **新增顶层目录必须同时更新** `AllTheFiles.md` / `README.md` / 本节。
- `data/` = 用户数据（含密钥），**永不进发行版**。
- 资源归位：运行时资源放 `resources/`；根目录的 `image.png` 应移入 `resources/`。
- `src/` 分层目录固定：`models/` `services/` `ui/{components,panels,widgets,styles}/` `i18n/`。

### H-2 `[待议]` 发行版目录与命名

- 产物目录 `dist/`；命名 `LifeAssistant-<version>-win64/`（版本与 `pyproject.toml` 单一来源）。
- **包含**：入口、打包产物（`.pyc`/二进制）、`resources/`、`plugins/`、`README`。
- **排除**：`data/`（密钥）、`.venv/`、`.git/`、`MD-files/`、`dev-logs/`、`tests/`、`PLAN.md`、`AGENTS.md`。
- 打包工具与 `C-1` 一致（PyInstaller/Nuitka）。

---

## I. 其他待补规范（我补充，待你裁决）

- **I-1 命名总约定**：模块 `snake_case`；类 `PascalCase`；常量 `UPPER_SNAKE`；私有 `_` 前缀；
  信号 `xxx_changed` / `xxx_requested`；槽 `_on_xxx`；文件与主类同名。
- **I-2 异常处理**：禁止裸 `except: pass`（现状约 80 处）；至少 `logger.debug` 记录或注释说明理由。
- **I-3 i18n**：UI 显示文本必须经 `tr()`（现状全项目仅约 47 处调用，大量硬编码中文，违反 R-008）。
- **I-4 类型注解**：公共函数/方法必须有参数与返回注解。
- **I-5 导入规范**：分组排序、禁 `import *`（交给 ruff/isort）。
- **I-6 时间日期**：统一 ISO 8601；`schedule_date()` 的 0–1 点算前一日语义必须全局一致。
- **I-7 依赖规范**：新增依赖必须同时更新 `requirements.txt` 与 `requirements.lock.txt`。
- **I-8 提交前钩子**：把 ruff + `check_standards.py` + `check_ui_tokens.py` 挂成 pre-commit。
- **I-9 脚本契约**：`scripts/*` 的 CLI 参数、退出码、输出格式统一（供 AI/TG/CI 三方共用）。
- **I-10 数据 schema 与迁移**：`_version` / `migrate()` 必须有测试与兼容策略
  （跨端：桌面 + TG + GitHub Actions 共写同一份 JSON，schema 变更需护栏）。
- **I-11 i18n key 命名空间**：分层 key，如 `panel.task.add_title`
  （现状 `zh-CN.json` 为扁平键，且全项目仅约 47 处 `tr()` 调用）。
- **I-12 测试命名与结构**：`test_<模块>_<行为>`；数据写入类测试固定用 `sandbox` fixture。
- **I-13 插件目录约定**：`plugins/<name>/plugin.py` + `IsOpen.able` + `manifest.json`。
- **I-14 版本号单一来源**：以 `pyproject.toml` 为准，`i18n` / `README` / 发行包名全部由它派生。
- **I-15 性能基线门禁**：把启动时间、`schedule_view._refresh` 耗时记成基线，超阈值告警。
- **I-16 依赖审计**：`pip-audit` + 定期升级（锁文件里 `openai 3.x` / `anthropic 1.x` 均未做真实调用验证）。

> 以上 G/H/I 均为 `[待议]`，需你裁决采纳范围与优先级。

---

## F. 已完成的框架工作

- `[已完成]` venv + 依赖锁定 + pytest 冒烟测试（commit `5788d61`）
- `[已完成]` `AGENTS.md` 重写（commit `b45a41c`）
- `[已完成]` 规范文档骨架 `MD-files/CODE_STANDARDS.md`
- `[已完成]` **可迁移准则** `MD-files/DEV_PRINCIPLES.md`（本轮整改的通用化提炼）
