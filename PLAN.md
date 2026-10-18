# PLAN.md — 大框架整改计划

> 用途：记录本项目**工程/架构层面**的整改项与决策，避免散落在对话里丢失。
> 与 `dev-logs/` 的分工：dev-logs 记"已发生的变更"；本文件记"待做 / 在做 / 已定方向"。
> 最后更新：2026-10-17

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
- `D-2` ✅ `[已完成]`（2026-10-16）→ 落地为 **`scripts/check_quality.py`**（尺寸/静默吞异常/ID 生成/
  令牌命名/i18n 计数/顶层目录/密钥入库 + vulture + radon；存量债走 `scripts/quality_baseline.json`）
- `G-2` ✅ UI 令牌检查器（`scripts/check_ui_tokens.py`，先只检查、不 `--fix`）
- ✅ `B-2`（2026-10-16）radon/vulture **接进 CI**（此前只是"一次性测量"）
- ✅ `B-6` CI 扩充为：`compileall` → ruff → `check_ui_tokens --strict` → **`check_quality --strict`** →
  `pytest --cov --cov-fail-under=50`
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
- ✅ `G-3` **UI 规范入口唯一**（2026-10-16）：建 `design/`（`INDEX.md` 规范总入口 + 原型 + 令牌文档），
  `AGENTS.md` §1/§3 写入"动 UI 先查、缺规范先问再建"，`CODE_STANDARDS Q-H19`

**P4 发布**
- `C-1` 注释/日志处理、`C-2` 日志写法规范
- `H-2` 发行版目录与命名
- `I-15` 性能基线门禁

**P5 功能可用性排查与修复 ✅ 已完成（2026-10-16）**- ✅ `F-1` 对 README「功能」/ 本文件 ✅ 项做**可执行**排查（离屏 Qt + 临时目录，32 项断言）
- ✅ `F-2` 15 项缺陷全部修复（数据解析 2 · 考试提醒 2 · 数据流 2 · AI 命令契约 4 · 主题入口 1 ·
  主线程网络 1 · 日期语义 1 · 模型默认值 1 · 文档漂移 1）
- ✅ `F-3` 测试 92 → **149 passed，5 xfail 全部转正为真实断言**
- ✅ `F-6` **场景存档功能弃用**（2026-10-16）：删 `scene_archive.py` + `scene_manager_dialog.py`（约 300 行），
  位置并入「天气设置」的纬度/经度，学期交给学期切换；旧 `scenes_meta.json` 的位置由 `migrate_legacy_scene_location()` 一次性迁移
- ⏳ `F-4` README「吃什么」仍是占位面板（"即将上线"），未实现
- ⏳ `F-5` 真实托盘 / 单实例 / 自启 / SMTP / GitHub Actions 运行未验证（需真实环境与凭据）
- 详见 `dev-logs/2026-10-16-功能可用性排查.md`

---

## P6 规范门禁补强（审计驱动）✅ 已完成（2026-10-16）

**起因**：一次"规范 vs 门禁"交叉审计发现 —— CI 实际只跑 ruff / 令牌 / pytest 三项，
64 条 Q 规则里**只有约 16 条真正有门禁（25%）**；且 `CODE_STANDARDS` 的「现状」栏大面积过时
（✔/✗ 都有错报）。结论：**光有 AGENTS.md 不足以可靠**，规范必须变成可运行的门禁。

**A. 修掉 5 个"没被检查出"的真缺陷**

| # | 缺陷 | 处理 |
|---|---|---|
| 1 | `habit.py` monthly 分支把 `logs` 顶层键（日期）当 habit_id 比较 → 每月习惯**永远判未达标** | 改为按"本月已完成次数 vs 配额"；新增 `tests/test_habit_schedule.py`（9 条，覆盖 daily/weekly/monthly/interval/推迟/取消） |
| 2 | 2 处静默吞异常（`theme.py` / `check_ui_tokens.py`），且 **ruff S110 漏检具名 `except (A,B): pass`** | 改用 `contextlib.suppress(...)`；门禁用 AST 兜住 ruff 的漏检 |
| 3 | 6 处 `len()+1` 生成 ID（R-008 明禁） | 新增 `models/base.next_id()`（最大后缀 +1）；`tests/test_ids.py`（8 条，含"删后再加不撞车"） |
| 4 | `Q-A1` 尺寸超限实为 **36 项**（文档写 2 文件/5 类） | 记入 baseline 防新增；全量拆分留 P3 长尾 |
| 5 | i18n（`Q-N5`）仅 19 处 `tr()`、**692 处**中文字面量 | 记入 baseline 防新增；全量迁移待裁决（见下） |

**B. 门禁补强**

- 新增 **`scripts/check_quality.py`**（含 `--strict` / `--write-baseline`）+ `scripts/quality_baseline.json`（存量债台账）：
  `SIZE` · `SILENT` · `ID-GEN` · `TOKEN-NAME` · `I18N` · `TOP-DIR` · `SECRET` · `VULTURE` · `RADON`。
  设计原则：**能绝对化的必须为 0；有历史债的走 baseline 只防新增**，债只减不增。
- 新增 `tests/test_quality_gates.py`（8 条）：既验证"探测器真能探测"（合成违规），也验证"当前仓库真干净"。
- CI 扩充：`compileall` → ruff → `check_ui_tokens --strict` → **`check_quality --strict`** →
  `pytest --cov=src --cov=scripts --cov-fail-under=50`。
- 归档：`hermes-skill-life-assistant.md`（第三方 skill，指令"直接读写 `data/` JSON"，与 R-002 冲突）
  → `MD-files/archive/`，附说明；`Q-P1` 白名单补 `design/`。

**C. 文档修正**

- `CODE_STANDARDS.md` 全量对账「现状」栏（把 6 条已修的 ✗ 改 ✔、3 条"一次性测量"标为已接 CI、
  更新尺寸/覆盖率/`tr()` 计数），并新增 **`Q-F4 规范必须门禁化`**。
- `AGENTS.md` §3 步骤 6 的验证命令与 CI 对齐。

**结果**：202 passed（177 → 202）· ruff 0 · 令牌违规 0 · 门禁 9 项全绿 · 覆盖率 54%（下限 50）。

**仍待裁决（原样保留）**：

- `Q-N5` i18n：**全量迁移**（692 处，~1 天）还是"新文本必须走 `tr()`、存量改到即补"？
  现状是后者 + baseline 防新增。
- `Q-A1` 尺寸：36 项超限（4 文件 / 6 类 / ~26 函数）何时拆分？
- `Q-H3` 令牌命名：10 处存量（`red/green/yellow/orange` + `colors.badge_radius`）何时重命名？
- `Q-A3` ✅ 天气 3 套实现**已收拢**（2026-10-16）：删死模块 `api_service.py`，
  新增 `services/openmeteo.py`（唯一 Open-Meteo 适配 + 唯一天气码映射），
  `ai_service` 改为委托；`tests/test_openmeteo.py` 守卫。`Q-E2` 双写路径 / `Q-H7` 令牌分层：仍是已知债。
- 工具缺口：`Q-A2`（`import-linter` 未装）、`Q-E1`（`gitleaks`/`detect-secrets` 未装）、`Q-D3`（AST 剥离检查未实现）。

---

## P7 i18n 全量迁移 · 工具补齐 · 天气整理 ✅ 已完成（2026-10-16）

**A. i18n（`Q-N5`）从"仅 19 处 `tr()`"做到"UI 文本全部走 `tr()`"**

- **机制升级**：语言包改为 **主文件 + 分片**（`src/i18n/zh-CN.json` + `src/i18n/zh-CN.d/<模块>.json`），
  加载器合并；`tr()` 支持占位符（`tr("k", n=5)`）与**缺语言包回退**（此前会直接抛
  `FileNotFoundError`，设置里填个 `en-US` 就崩）。
- **四道守卫**（`tests/test_i18n.py`）：用到的键必须存在 / 键必须命名空间化 / 键不得重复定义 /
  回退与占位符可用。
- **度量口径**（`check_quality.py` 的 `I18N`）：只数"**未走 `tr()`** 的中文字面量"，
  并排除四类非界面文字：docstring、日志实参、字典键、`tr()` 实参。
- **结果**：`src/ui` 未国际化中文字面量 **692 → 106**（16 个文件、约 30 个分片）。
- **剩余 106 处的性质**（不是遗漏）：
  | 类别 | 例子 | 为什么不迁移 |
  |---|---|---|
  | 数据值直接渲染 | `充足/需购/不足`、`衣物/虚拟品类` | 是 `inventory.json` 里存的**数据值**；要迁移需先引入"状态→键"映射表（逻辑变更） |
  | AI 提示词/快照 | `_build_snapshot`、`_build_context_prompt`、`replace_plans` 指令 | 机器可读契约，不是给人看的界面文字 |
  | 内部哨兵 | `"全部"`（筛选状态）、`sum_*` 查找键 | 参与比较，不显示 |
  | 数据默认值 | `"未知课程"`（prompt 侧） | 兜底值 |
- **顺带修掉的两处脆弱设计**：
  1. 记账汇总卡此前用**显示文字**当 `objectName`（`sum_本月支出`）再按文字查找 →
     改为按**稳定键**（`sum_month`），`test_ui_wiring` 同步；
  2. 三处"按按钮文案判断高亮"的启发式（`txt in ("添加", ...)`）中，记账面板已改为 `tr()` 比较；
     任务/考试面板的同类启发式**仍是待办**（见下方"仍待裁决"）。
- **顺手清掉**：`main_window` 两处传给 `on_arrange_done(success=True, msg)` 的中文字符串
  在成功分支**根本不会被使用**（死字符串）→ 改为 `""`。

**B. 工具补齐（`Q-A2` / `Q-E1` / `Q-D3`）**

| 工具 | 状态 | 接入方式 |
|---|---|---|
| `import-linter`（Q-A2 分层方向） | ✅ 装 + 配 `.importlinter` | 门禁 `IMPORT-LINTER`（1 kept / 0 broken） |
| `detect-secrets`（Q-E1 密钥） | ✅ 装 + `.secrets.baseline`（0 处可疑） | 门禁 `SECRETS`（扫描排除 `data/`，避免把真密钥写进基线） |
| `Q-D3` 可剥离日志检查 | ✅ 自建 AST 检查 | 门禁 `LOG-STRIP`（必须 0）+ `LOG-ONLY`（baseline 37） |

- `Q-D3` **口径收窄**（有依据，非迁就实现）："日志是块内唯一语句"只影响剥离时需补 `pass`，
  不是阻断项 → 改为 baseline；真正阻断的"日志嵌在表达式里"（`x = logger.info(...)`）**强制 0**。
- 门禁总数：9 类 → **13 类**（新增 LOG-STRIP / LOG-ONLY / IMPORT-LINTER / SECRETS）。

**C. 天气整理（`Q-A3`）**

- 收拢为**每个能力一套适配**：和风 → `weather_service.py`；Open-Meteo → 新 `services/openmeteo.py`
  （唯一 URL + 唯一天气码映射）；余额 → 新 `services/deepseek.py`。
- `api_service.py` 退化为**只起线程的 Qt 外壳**（`_ApiWorker` 委托共享适配器），删掉自带的
  天气码映射、天气请求、余额解析。
- `ai_service.py` 删掉内联的 Open-Meteo 请求与重复的天气码映射、内联余额解析 → 全部委托。
- 守卫：`tests/test_openmeteo.py`（映射/URL 只能出现在一处、`ai_service`/`api_service` 不得自带实现、
  弹窗字段契约、失败路径永不抛异常）。

**D. 本轮踩的坑（已记 `ERRORS #035`）**

用 PowerShell `Select-String -Path src/**/*.py` 搜引用时**静默漏文件**，据此误判 `api_service.py`
为死模块并删除，实际它被"API 测试"弹窗使用 → 由子代理发现后回滚重做。
**教训**：搜引用一律用 `grep` 工具，不要用 shell 通配符；删模块前必须用**可靠**方式确认零引用。

**结果**：**225 passed**（202 → 225）· ruff 0 · 令牌 0 · 门禁 13 项全绿 · 覆盖率 56%。

**仍待裁决 / 待办**：

- 记账之外的"按按钮文案判断高亮"（`task_panel` / `exam_panel` / `inventory_panel`）→ 建议统一改为
  按 `objectName` 或动态属性判断（现在是改文案就会静默失效的脆弱耦合）。
- `inventory` 的"状态值直接渲染"（`充足/需购/不足`）→ 若要入语言包，需先加"状态→键"映射。
- i18n 剩余 106 处中若还有你认为是界面文字的，告诉我具体位置，我补键。

---

## P8 合并 B：课程表并入日程（日/周 切换）✅ 已完成（2026-10-16）

**决策（用户拍板"方案 B"）**：删掉独立的「课程表」导航项，并入「日程」+ 顶部 日/周 切换；
周视图补上 DDL/考试/计划标记，解决"没课的日子一片空白、看着像这周什么都没有"。

- 侧边栏：移除 `courses` 导航项；`sidebar.nav.schedule` 文案 `日程总览` → **`日程`**
- `ScheduleView`：顶部加 **日 / 周** 切换（激活态用强调色，`_set_mode` 切换 `QStackedWidget`）；
  周页内嵌 `CoursePanel`（保留其"上一周/本周/下一周 + 课程数"工具栏）；
  切到周视图时隐藏日视图专属控件（日期导航 / 调整 / 外层刷新）
- `CourseTable`：新增**末行"事项"**（`_marker_row`，按内容自适应高度；无事项时整行隐藏），
  列出当天：`截止 · {作业}` / `考试 · {课程}` / `计划 · {标题}`
- `CoursePanel._collect_markers()`：按"该周第 1 天"（学期开始日 + (周-1)×7，无学期则退回本周一）
  收集当周 7 天的事项
- `MainWorkspace`：`courses` 从 `_panel_map` 移除（面板 9 → 8）；`course_panel` 属性改为
  **委托** `ScheduleView.course_panel`（菜单/测试入口不变）
- **令牌清理**：删除早已不再使用的 `course_color_1..8`（课程块已改中性色）——
  颜色令牌 48 → **47**（每模式），同步 `gen_design_tokens.py` / `check_ui_tokens.py` 的前缀表
- 测试：新增 `tests/test_schedule_modes.py`（6 条：默认日视图 / 切换 / 事项行内容 /
  空周隐藏 / 主题刷新后仍在 / 工作区委托入口）；`test_ui_wiring` 的 nav 键集合同步
- 离屏截图核对：浅色 / 深色两套主题下，周视图的课程块、日/周 切换、事项行均正确

---

## P9 学期合法性检测 + 学期过期处理 ✅ 已完成（2026-10-16）

**起因**：用户真实数据的学期 `start_date` 过旧，状态栏显示 **"第 32 / 16 周"**（第 32 周不存在）。
排查发现根因不是"某个算式写错"，而是**同一件事（第几周）在 5 处各算一遍、口径不同**。

**A. 单一真值：`src/models/semester.py`（纯函数，无 Qt / 无 IO）**

| 函数 | 用途 |
|---|---|
| `semester_status(sem, today)` | **显示口径**：`state` ∈ `none` / `invalid` / `not_started` / `active` / `expired`；已结束时 `week` 钳到总周数 |
| `week_number_for(sem, target)` | **取课表口径**：超范围返回 `None`（不钳制） |
| `validate_semester` / `validate_courses` / `validate_all` | **合法性检测**：14 个问题码（机器可读，UI 翻译） |

改为调用它的 5 处：`CourseModel`（含 `get_courses_for_date` / 新增 `semester_status()` / `validate()` /
`current_week()`）、`MainWindow` 状态栏、`CoursePanel` 周标签、`AIService._get_current_week`
（**修掉"忽略 `current_semester`"的真 bug**）、`scripts/send_digest.py`（第三套算法 → 同一份实现）。

**B. 合法性检测**（问题码 → 文案在 `ui/components/semester_text.py`）

- 学期级：缺 id / 缺或无法解析的开始日期 / 开始日期超出 2000–2100 / 缺总周数 / 总周数不在 1–30 /
  节次不在 1–12
- 模型级：`current_semester` 指向不存在 / 有课程却没学期 / id 重复 / 学期区间重叠
- 课程级：周次超出学期 / 星期不在 1–7 / 节次无效（空、起止颠倒、超上限）

**C. 安全自愈**（`_repair_semesters`，幂等，只补能安全推断的）

补 `id` / `total_weeks=20` / `period_count=5`；`current_semester` 失效时挑一个最合理的
（今天落在其区间内的 > 开始日最新的）。**不猜 `start_date`** —— 猜不出就报出来让用户改。

**D. 学期过期处理（UI）**

- **状态栏**：`学期已结束` / `学期未开始` / `学期数据异常` / `未设置学期`，过期等异常状态用强调色；
  该片段可点击 → 学期管理。**不再显示"第 32 / 16 周"**。
- **课程表周标签**：`学期已结束 · 第 20 / 20 周`（状态 + 正在看的周次，两件事都说清）；
  工具栏新增「学期」按钮。
- **新增 `SemesterDialog`**（学期管理，`Q-H9~Q-H14`）：显示状态与检测结果、切换当前学期、
  **新建学期**（默认开始日 = 下一个周一，可设总周数/每天节次，创建后即设为当前）。

**E. 顺带修掉的坑**

- `ERRORS #036`：本机区域 `zh_HK` 用 **CJK 数字**，`QDateEdit`/`QSpinBox` 显示 `〢〇〢〦-〡〇-〡〩`。
  项目里原本有两处给单个控件打补丁，新控件又中招 → 改为 `theme.configure_locale()`
  由 `init_theme()` 统一调用（任何 UI 入口都覆盖），守卫 `tests/test_locale.py`。
- 删掉 `CourseModel.active_courses`（**无人调用的死代码**，`Q-A4`）。

**结果**：**270 passed**（235 → 270）· ruff 0 · 令牌 0 · 门禁 14 项全绿 · 覆盖率 59%；
离屏截图核对：状态栏 / 周标签 / 对话框（含日期控件数字）三处均正确。

---

## P10 学期参数（16 周 + 期末周）· 同一时段两门课 ✅ 已完成（2026-10-16）

**A. 学期参数按用户口径调整**

| 项 | 旧 | 新 |
|---|---|---|
| 教学周默认 | 20 | **16**（用户：每个学期 16 周） |
| 期末周 | 无 | **默认 1 周**（教学周之后）→ 学期总跨度 17 周 |
| 新建学期默认开始日 | 下一个周一 | **按季节预设：7–12 月 → 当年 9/21；1–6 月 → 当年 3/2** |

- 新增状态 **`exam`（期末周）**：教学周上完但学期未结束 → 状态栏/周标签显示"期末周"，
  且**仍显示最后一周课表**（不是空白页）；期末周内 `week_number_for()` 返回 `None`（确实不上课）。
- `end_date` 语义改为"**含期末周**的学期最后一天"，新增 `teaching_end_date`（教学周最后一天）；
  "已结束"只在期末周也过完之后。
- 校验新增 `exam_weeks` 范围（0–6）；自愈补默认 1。
- 用户给的例子在测试里钉住：`2026-09-21`（周一）+ 16 教学周 → 第 16 周周五 = **2027-01-08** ✓ 与描述一致。

**B. 同一时段两门课（选修过多 / 重修）**

- **数据本身不用改**：两门课本来就是两条记录（各自 `day_of_week` + `time_slots`）。
  真正缺的是**检测 + 同时显示 + 提示**——原来 `setCellWidget` 会让第二门**静默覆盖**第一门（`ERRORS #038`）。
- 新增纯规则 `models/course_rules.py`：`is_active_week()` / `slots_of()` /
  `conflicts_by_cell()` / `find_conflicts()`（`CourseModel` 与渲染都调它）。
- **周视图**：冲突格渲染成一个列出**两门课**的块（`⚠ 两门课冲突` + 两门课名，按合并跨度 `setSpan`）；
  右键菜单逐门课提供"查看事项"。
- **日视图**：该时段卡片加一行 `⚠ 本时段有两门课，记得请假`。
- 按用户选择：**只做应用内**（不动邮件摘要；本轮也不做"标记已请假"——
  `excluded_weeks` 字段已具备该能力，将来想加只需在冲突块右键加一项）。

**结果**：**290 passed**（271 → 290）· ruff 0 · 令牌 0 · 门禁 14 项全绿 · 覆盖率 60%。
离屏截图核对：周视图三个冲突格（含跨节合并）、日视图两处请假提示。

**顺带**：截图核实时发现"方块字"分两种 ——
① **真问题**（`#036` 区域 CJK 数字，`text()` 里就是怪字符）；
② **离屏假象**（emoji/符号缺字体回退，真实平台全部正常）。
两者要分清，否则会把好代码"修坏"。

---

## P11 按学期分数据文件（切换学期 = 换一份数据）✅ 已完成（2026-10-16）

**起因**：用户发现"切换学期不会修改应当显示的课程表"，并要求明确"哪些跨学期继承、哪些换新"。

**根因（`ERRORS #040`）**：`courses[]` 是**全局一个列表**，每条课程没有学期字段；
`tasks.json` / `exams.json` 同理 —— 切学期只改"周次→日期"的映射，24 门课永远都在。
**不是刷新问题，是数据模型缺"学期"这个维度。**

**用户口径**：

| 按学期（换新） | 跨学期（继承） |
|---|---|
| 课程表 / 作业 / 考试 | 有什么 / 记账 / 习惯 / 日程计划 |

**落地**：

- **布局**：`data/semesters.json`（注册表：`semesters[]` + `current_semester`）
  + `data/semesters/<学期id>/{courses,tasks,exams}.json`。
- **路径解析只有一处**：`models/semester_paths.resolve()` —— 应用、`actions.py`、`send_digest.py`、
  `build_index.py`、`tests/helpers.read_json` 全调它（**30+ 处 `load("tasks.json")` 调用点没改**）。
- **切换收口**：`DataManager.switch_semester()` / `create_semester()` —— 改指针 + **重定向三个模型**
  + 重载 + 通知界面；`semester_dialog` 改调它。
- **模型拆分**：`SemesterRegistry`（新，`data/semesters.json`）承接原 `CourseModel` 的全部学期职责；
  `CourseModel` 保留**同名转发**接口（`semester_status` / `current_week` / `get_period_count` /
  `semesters` / `get_courses_for_date`…）→ 界面/AI 的 40 处调用点**零改动**。
- **迁移**：`semester_paths.migrate_legacy()` 幂等，先写新文件 → 校验 → 再删旧文件。
  真实数据实测 **24 课 / 2 作业 / 6 考试零丢失**（旧学期数据本就无法区分归属，统一归到当前学期）。
- `GitSync` 同步范围加 `data/semesters`；`_auto_reload` 监视 8 个文件（含注册表）。

**结果**：**293 passed**（290 → 293）· ruff 0 · 令牌 0 · 门禁 14 项全绿。

**说明（重要）**：老学期 `2025-2026学年第二学期` 的课表**看起来是空的** ——
旧数据没有学期归属，迁移时全部归到**当前学期**；那学期的数据无法反推，需要的话得手动补。
（→ 已在 `P12` 里按日期归位修正。）

---

## P12 全量功能验收 + 6 项修补 ✅ 已完成（2026-10-16）

**起因**：用户要求"从启动到每个功能（除 AI 助手）做全量测试，站在用户角度验证可用性，并检查日志"。

**验收结果**：`scripts/acceptance_check.py` —— **80/80 通过**（18 个环节：启动 / 导航 /
日程日周视图 / 作业三态筛选 / 考试 / 日常 / 记账 / 库存 / 占位面板 / 设置 / 学期管理 /
主题 / 状态栏托盘 / 数据落盘 / 日志 / 单实例 / 学期对话框 / 真实数据未被改动）。

**验收抓到并修复的真问题**：

| # | 问题 | 修复 |
|---|---|---|
| 1 | **天气缓存被并发写坏 → 应用启动即崩**（`ERRORS #041`） | 新增 `services/weather_store.py`（安全读 + 原子写 + 锁）；读写点收口；用户坏文件已救回重写 |
| 2 | `GitSync` 子进程 `text=True` 未指定编码 → 中文文件名输出触发 `UnicodeDecodeError` | 显式 `encoding="utf-8", errors="replace"` |
| 3 | 状态栏不接 `data_changed` → 切学期后最多 30s 显示旧数字 | `MainWindow` 接上并立即 `_refresh_status()` |
| 4 | i18n 门禁**范围缺口**：只查 `src/ui/**`，漏掉 `src/app.py`（托盘菜单/气泡 6 处硬编码） | 度量范围加应用入口 + 那 6 处走 `tr()` |
| 5 | 日志三问题：git 失败**原因是空的**（只看 stderr）/ logger 命名不一致 / httpx INFO 噪声 102 行 | 失败带上 stdout 与退出码；3 个短名 logger 改 `__name__`；第三方库降 WARNING |
| 6 | 习惯面板**无空态**（今天没有要做的日常时整页空白） | 加"今天没有要做的日常"提示 |

**迁移归位**（用户确认后执行）：验收发现旧学期的课程/考试/作业都落在当前学期，
但它们的**日期属于春季**（考试 6/19–7/9）→ 按"距离最近的学期"归位到
`2025-2026学年第二学期`（24 课 / 2 作业 / 6 考试），`sem_001` 清空为空白新学期；
并按实际考试跨度把该学期期末周 1 → **3 周**（保证 6 场考试都在学期窗口内、都能显示为"事项行"）。
备份在 `%TEMP%\data_backup_before_reassign`。

**固化**：`scripts/acceptance_check.py` 进仓库（沙箱隔离 / 不碰注册表 / 看门狗 / 断言 + 截图），
`AGENTS.md` §3 步骤 6 把它列为**分界点可选**的验收步骤。

**结果**：**311 passed**（303 → 311）· ruff 0 · 令牌 0 · 门禁 14 项全绿 · 验收 80/80。

---

## P13 AI 助手接入 OpenCode Go + 脚本硬化 ✅ 已完成（2026-10-16）

**AI 助手**：用户给的 `https://opencode.ai/zen/go` + 空 key + `longcat-2.5-preview-free`
实测不可行（`zen/go` 是客户端内部路由 → 400 `MissingSessionID`；按量付费端点上免费模型
→ 403 `FreeTierError` "free tier can only be used from within OpenCode"）。已按用户确认
改走 **OpenCode Go 订阅**：端点 `https://opencode.ai/inference/go/openai/v1`，代码侧自动补
`x-opencode-session` 与自定义 UA（官方文档要求）；设置面板新增 `opencode` provider 预设。
**待用户提供 Go 的 API key 后切换**（当前 DeepSeek 配置实测可用，没有动）。

**脚本硬化**（`scripts/actions.py` —— AI 唯一的写数据入口，`ERRORS #042`）：
- **入口统一校验**（规格表覆盖 22 条命令）：非法输入只回 `ERROR`、**不写任何文件**；
  未知参数（拼错的 `--titel`）直接拒绝，不再静默忽略
- **写入**：结构守卫 → 写前备份 → `.tmp` → 回读自检 → `os.replace`；`load()` 遇坏文件**明说**
- **手动恢复**：`list_backups` / `restore --name X --yes`（备份在 `data/backup/actions/`，按份数轮转）
- **新增记账 4 条命令**（`add_expense`/`add_saving`/`delete_expense`/`expense_summary`），
  命令总数 16 → 22
- 拆分为 `actions_core.py`（757 行）/ `actions_cli.py`（139）/ `actions.py`（711），
  顺带修掉 `main()` 135 行、`_validate_args` 109 行的函数长度超限

**提示词**：按 7 个领域重排（课程表/作业/考试/习惯/日程/有什么/记账；
**「吃什么」跳过** —— 仍是占位面板、没有数据模型），新增 13 条关键词映射 + 数据安全段。

**检查项**：天气（Open-Meteo + 和风天气均正常 ✓）、邮件（实发测试邮件成功 ✓）、
GitHub Action（无失败 run；8/22 起因仓库约 8 周无活动被 GitHub 自动停用定时 workflow，
用户已重新启用，下次触发为次日 04:55）。

**结果**：**355 passed**（326 → 355）· ruff 0 · 门禁 14 项全绿 · 验收 80/80。

---

## P14 提醒功能（点名 / 作业 3 天）✅ 已完成（2026-10-16）

**两条新规则**（都走「托盘 + 邮件」，并受设置总开关控制）：

| 规则 | 触发 | 数据 |
|---|---|---|
| **点名提醒** | 开课前 **30 分钟**（`lead_minutes` 可覆盖；课已开始则不提醒） | `course["reminders"] = {"attendance": true, "lead_minutes": 30}`，由**课程右键菜单**开关 |
| **作业截止** | 截止前 **3 天内**（与既有「6 小时内」邮件叠加，各发一次） | 现有 `tasks.json` 的 `due_date` |

**总开关**：设置 → 通用 →「提醒」（`General/reminder_enabled`，**默认开**）——所有提醒统一走
`ReminderService._notify()` 出口。关掉后托盘与普通提醒（点名 / 3 天 / 习惯 / 余额 / 自定义）都停，
**考试与 DDL 6 小时的紧急邮件例外**（`mandatory=True`，永远发 —— 用户明确要求）。

**结构**：规则抽成**纯函数** `services/reminder_rules.py`（无 Qt、可单测），
服务只留接线；`ReminderService` 类从 526 行降到 **378** 行（原来已超「单类 ≤400」的存量债，
现在回到限内）。UI 侧新增 `ui/widgets/schedule_actions.py`（从 `schedule_view.py` 搬出 63 行的
弹窗函数，顺带让「单函数 >60 行」消失）。

**结果**：**369 passed**（355 → 369）· ruff 0 · 门禁 14 项全绿（SIZE 存量 34 → 32）· 验收 80/80。

---

## P15 AI"没反应"排查与加固 ✅ 已完成（2026-10-16）

**用户报**：让 AI 导入本学期课程表，迟迟未回复，命令行也没见 200 OK。

**排查结论**（证据链）：日志里请求其实 **200 成功**（23:11:31），py-spy 显示主线程 idle、
无工作线程 → 应用没卡死；但数据一条没变 → **模型回复没被解析出命令**。
实测复现：只发一句"帮我导入课程表"→ 6s、0 条命令（模型反问要课表）；
带 24 门课表 → 40–58s、24 条命令。**最可能是回复撞输出上限被截断**，
而旧 `parse` 要求必须有收尾 ``` → 整段丢弃、且**没有任何提示**。

**加固**（`ERRORS #043`）：
- `parse` 容忍未收尾的块（完整行照执行，非法行由 `actions.py` 拦下）
- `AIWorker` 检测截断 → 让模型**分批续跑**（提示词新增"每轮 ≤8 条"规则）
- 补**生命周期日志**（`AI turn N: 耗时 | 字符数 | 疑似截断 | 命令数`）
- 模型客户端 **120s 超时**（原为 SDK 默认 10 分钟）；空回复给明确提示

**验证**：端到端跑 `AIWorker` 导入 24 门课 → 44s、**24 条命令全部执行**（沙箱课表 24 门）。
**结果**：**377 passed**（369 → 377）· 门禁 14 项全绿 · 验收 80/80。

### 追加（同一晚第二次报障：连续返回空内容、没有自动分批）

**证据**（新日志立功）：`AI turn 1: 95.6s | 0 字符 | 疑似截断=False | 命令=0` ×2 →
**空回复**；前三次是 344–526 字符的**纯文本**（模型在要信息，命令=0）。

**根因**：推理型模型把 `max_tokens=4096` 全花在推理上 → `finish_reason=length`、
content 为空；而"空回复"围栏数为 0 → 不算截断 → **上一轮的分批逻辑从不触发**。

**追加修复**：
- 空回复也走"要求继续"分支（提示语：直接输出命令、每轮 ≤8 条、别长篇思考）；
- `max_tokens` 改读设置、默认 **4096 → 8192**；
- provider 每轮打印 `finish_reason` + 推理 token 数（一眼看出是预算问题）；
- 换模型：`longcat-2.5-preview-free`（预览版、推理冗长、会空回复、15–25s）
  → **`deepseek-v4.1-flash`**（实测 4.8s、稳定分批；已含在 Go 订阅额度内）。

**又抓到一个坑**（`ERRORS #044`）：运行中的应用每 60s 把**内存里的配置整份写回**
`settings.ini`，我脚本改的模型/预算被静默回滚 —— 改配置只能在界面里或关应用后做。

### 第三轮（用户贴出日志：`补全 8192（推理 8192）` × 5 轮）

**现象**：模型把**整份输出预算都给推理**（content 恒为空），5 轮共空转 ≈ 3.5 分钟 ——
我上一轮加的"空回复就重试"反而**放大了**问题。

**对照实验**（同一提示词，证明模型没坏）：

| 配置 | 耗时 | finish | 推理 token | content |
|---|---|---|---|---|
| `deepseek-v4.1-flash`（应用配置） | 5.7s | stop | 75 | 877 字符 ✓ |
| `deepseek-v4.1-flash` + `reasoning_effort=none` | **3.7s** | stop | **0** | **1359 字符** ✓ |
| `glm-5.3-flash` / `mimo-v2.6-flash` | 7.7 / 8.6s | stop | 406 / 11 | 857 / 844 ✓ |

**修复**：空回复只重试一次 ✓；content 空但推理有内容时**用推理文本** ✓；
OpenCode 端点加 `reasoning_effort="none"`（不认则自动降级）✓；空回复提示改成可操作 ✓。

**实测**：24 门课导入 **11.1s、24 条命令全部执行**（原来 44–58s）。

**顺手**：提示词抽成 `services/ai_prompts.py`（`ai_service.py` 830 → 713 行，回到 800 内）；
修掉一个**跨午夜必然失败**的既有测试（fixture 写死 2026-10-16、断言算"今天"）。

**结果**：**387 passed** · 门禁 14 项全绿（SIZE 存量 34 → 32）· 验收 80/80 · CI success。

---

## P16 课表导入时段修正 + `update_course` ✅ 已完成（2026-10-17）

**用户报**：导入后时段整体下移一节；让 AI 修正时它回了奇怪的代码。

**根因**（`ERRORS #045`/`#046`）：
1. **小节 vs 大节**：用户课表一天 8 小节，应用一天 6 个大节（每个含两小节），
   AI 按 1:1 映射 → 第三节显示成 13:30、第五节显示成 18:30（15 门课受影响）；
2. **没有"改课程"命令**：只有 add/delete → AI 想修正无从下手，去跑了 `status`；
3. **围栏只认 ```sh**：模型写 ```bash 时命令不执行、代码还漏到聊天里；
4. `update_*` 被注入默认值 → 改一个字段会静默重置别的字段（既有隐患）。

**修复**：提示词加"小节→大节"对照表（`大节 = ceil(小节/2)`）+ 禁 shell 语法 +
"修正用 update_course"；新增 `update_course` 命令；`parse` 接受多种围栏 +
`_strip_code_blocks()` 统一剥代码块；`update_*` 不再注入默认值（handler 全改 `getattr`）。
已用 `update_course` 修正 15 门课（分布 `{1:8, 3:10, 4:6, 5:5}` → `{1:8, 2:10, 3:5, 4:6}`）。

**结果**：**395 passed** · 门禁 14 项全绿 · 物品命令拆出 `actions_cmds_items.py`（actions.py 807 → 694 行）。

**第二轮（用户给出课表截图）**：逐格比对确认**时段已全对**，但**星期几错了 21 门** ——
根因是用户最初粘贴的**纯文本课表空单元格塌陷**（周二没课 → 周三内容贴到周一后面）。
已按图用 `update_course --day` 修正 21 门，29 门课与图片完全一致；提示词补上
"列比节次更容易错 / 拿不准先列出各天课程请用户确认 / 截图读不到请改文字"。

**结果**：**383 passed**（377 → 383）· 门禁 14 项全绿 · 验收 80/80。

---

## P17 数据一致性收敛（路线 B：冲突检测 + 单写者）`[已完成]`

**进度**：阶段 1 ✓（退出不覆盖 + 撤销范围）· 阶段 2 ✓（保存冲突检测）·
阶段 3 ✓（CLI 单写者：委派给运行中的应用）—— 均 2026-10-17，见
`dev-logs/2026-10-17-数据一致性收敛.md`。

**起因**：2026-10-17 一次外部审查（含隔离目录复现）指出 6 项缺口，其中 #1 是
"原子写入 ≠ 并发安全，仍会静默丢更新"。逐条核实结论：**诊断属实**（证据见下表），
但**药方**（SQLite 事务 + 跨进程锁）对这个项目代价过大 —— 会丢掉 `data/*.json`
的可读、可被 skill/CLI 编辑、可 git 版本化、可 backup/restore（这些都是设计优势）。

**已核实的具体缺口**：

| # | 缺口 | 证据 |
|---|---|---|
| 1 | 退出时 `save_all()` 整份覆盖外部改动 | `app.py:272/281` + `data_manager.py:139` |
| 2 | 整份文档写回、无版本检测 → 后写者赢 | `models/base.py:61 atomic_write` |
| 3 | 撤销 `copy2` 整份 `daily_logs.json`（连带回滚打卡/自定义提醒） | `ui/widgets/schedule_view.py:381/433` |
| 4 | 手动同步 `git add -A`；"nothing to commit" 会跳过 push | `services/git_sync.py:78/95` |
| 5 | `migrate()` 找不到迁移函数也照样抬版本号 | `models/base.py:101-108` |
| 6 | `"semester"` 不在全刷集合 → 作业/考试面板不刷新 | `main_workspace.py:149` |

**用户决策（2026-10-17）**：走**路线 B**（不换存储），顺序按审查（#1 优先）。

**方案（三个阶段，各自可独立合并）**：

1. **退出不覆盖 + 撤销范围**（对应 #1 的退出路径 + #3）
   - `DataManager.flush_on_exit()`：比对**磁盘内容**而不是 mtime（应用自己保存也会动 mtime，
     只比 mtime 会把"刚保存完就退出"误判成冲突）；磁盘已是内存态 → 跳过不碰文件；
     内容不同 → **不覆盖**，我方版本落到 `data/backup/exit_conflict/`（`data/backup/` 已在
     `.gitignore`）+ 日志 + `save_conflict` 信号
   - 撤销改**内存快照 + 只回滚本次涉及的 plan 条目 + 校验期间无他人改动**（不一致则拒绝并告知）
2. **保存冲突检测**（对应 #1 的核心）
   - 实现用**磁盘内容指纹**（sha256 + `sort_keys`），**不用 `_rev` 号**：`_rev` 要求每个
     写入方都配合维护，而 `scripts/actions_core.py`、skill、手工编辑都会漏 → 冲突照样
     静默通过，而这三条正是真实的并发来源（2026-10-17 实现时改的方案，理由见 dev-log）
   - `save()` 写前比对指纹：不一致 → **不写** + `on_conflict` 回调（`DataManager` 留副本到
     `data/backup/save_conflict/` + 发 `save_conflict` 信号）→ `MainWindow` 弹窗；
     **不抛异常**（`save()` 有二十来个调用点，抛出去会把 UI 打崩）
   - 指纹与键序无关 → "只是被重新格式化过"不算改动
3. **CLI 单写者**（对应 #1 的根因）
   - `scripts/actions.py` 写前用现有 `QLocalSocket` 单实例通道探测；应用在跑 → 把命令交给
     应用执行（沿用 AI 那条已验证的路径 + `reload_all()`）；不在跑 → 直写；连不上 → **明确拒绝**

**不做**：关系型 / 文档型 SQLite；行级并发；`actions.run_in_process` 的 stdout 重定向改造。

**最脆弱的假设**：冲突会被检测到。极端同毫秒并发时退化为"拒绝后写者 + 留副本" —— 退化是安全的。

**回滚**：三个阶段都只是代码 revert（**零数据迁移**）—— 这是相对 SQLite 的最大好处。

**规则/文档影响**：`R-002` 加一句"CLI 在应用运行时委派给应用执行"（命令面不变）；
`ARCHITECTURE` §6 并发模型 / §7 不变量 / §8 schema 总表；`ERRORS` 新增"整份文档写回 = 静默覆盖"。
**无 DR 被推翻**（DR-001~004 均不涉及存储）。

**已完成的相邻项**：#2（AI 推理进执行通道）已修 —— `fix(ai): keep reasoning out of command
execution`（`cc6a9e4`，2026-10-17）：`chat()` 不再把 `reasoning_content` 当回答返回，空回复
改走 `error` + 可操作文案。

---

## P18 「有什么」AI 重建（命令面补齐 → 提示词测试 → 清空重建）`[已定]`

**用户决策（2026-10-17）**：补货要**推送提醒**；命令面**全补 + 提示词补例**；
**等 P17 全部做完再清空重建真实数据**。

**为什么必须先补命令面**（核实结果，2026-10-17）：

| 维度 | 数据模型 | AI 能用的命令 | 现有真实数据 | 结论 |
|---|---|---|---|---|
| 位置 | `location` | `--location` ✓ | 11/11 有 | **够用** |
| 份数 | `quantity` + `unit` + `doses_per_unit` | 只有 `--quantity` ✗ | 11/11 有 `unit` | **缺 2 个参数** |
| 同类不同特征 | `group` + `tags` + `instances` | `instances` ✗ | 6/11 有 `instances` | **缺 1 个参数** |
| 提醒补货 | `min_quantity` + 状态自动推导 + `need_restock()` | `--min_qty` ✓、`need_restock` ✓（提示词无例 ✗）| 11/11 有 `min_quantity` | 阈值够用、**缺推送** |

现有 11 条（衣物 3 / 日常消耗品 3 / 数码电子 2 / 虚拟 2 / 其他 1）用到了
`unit` / `min_quantity` / `instances`，而 AI 只能写 `min_quantity` →
**现在清空重建会得到比现有更差的数据**（丢单位、丢同类分件）。这正是"先测提示词"的价值。

**待做（顺序固定）**：

1. **命令面补齐**（`actions_core` SPECS + `actions_cli` + `ai_prompts` 三处一起改）
   - `add_item` / `update_item`：`--unit`、`--doses-per-unit`
   - `add_item` / `update_item`：`--instances`（JSON 列表，写法同 `replace_plans --plans`）
   - 新命令 `consume --id --amount`（带状态推导 + 每份数扣减；`InventoryModel.consume()` 已存在）
   - 提示词补例：`--min_qty`（补货阈值）、`need_restock`（"还有什么要买的"）
2. **补货推送提醒**：`InventoryModel.need_restock()` 已有 → 在 `services/reminder_rules.py`
   加一条规则（状态为需购/不足 → 托盘 + 邮件，**每天最多一次**，受
   `General/reminder_enabled` 总开关控制）
3. **沙箱端到端测试**：真实 AI 全链路（提示词 → 日常口语 → 模型输出命令 → 执行 → 断言沙箱 JSON），
   **原样打印模型发出的命令**；**密钥不读**（走 `SettingsManager` 加载）；
   10 个样例覆盖 4 维度 + 2 个边界（拒绝不存在的物品 / 模糊表述应反问）；
   关键样例跑 2–3 次（模型有随机性，单次通过 ≠ 稳定）
4. **清空重建**（用户看过测试结果并确认后再做）：整份备份到
   `%TEMP%\inventory_backup_before_reset\` → **先关应用** →
   用 `scripts/actions.py delete_item --id ...` 逐条删（R-002 的合法写入路径）
5. **位置就是归属（学校 / 家）**（2026-10-18 追加，第二版）：换季把部分衣物**寄回家**、
   来年再寄回，所以要能表达"在哪一边"。
   - **不存 `dataset` 字段**，由 `location` 推导（`InventoryModel.side_of()`）：位置是「家」→ 家侧，
     其余（宿舍格位 /「学校」/ 空）→ 学校侧
   - 词表 = 宿舍格位 + 「学校」「家」两个粗格位；**没说位置 → 默认「学校」**（虚拟品类留空）
   - 界面的"看哪边"切换是**纯视图状态**，不写数据文件
   - **补货只看学校侧**；家那侧卡片不显示位置（那边的位置一律是"家"）
   - ⚠ 第一版是"数据集字段 + 让模型判断'家里'指哪边"，**被用户否掉**（flash 中文不稳，必错）
   - 详见 `dev-logs/2026-10-18-库存归属学校与家.md`
6. **会员账号 + 私有手机号**（2026-10-18 追加）：虚拟品类通常是会员，要绑账号。
   - item 里加 `membership`：`username` / `expires_on` / `auto_renew` / `renew_months`
   - **到期日决定状态**（过期 → 需购、7 天内 → 不足）；自动续费只是记着
   - **手机号选填、不进仓库、也不进 AI 提示词** → 单独放 `data/private/memberships.json`
     （`.gitignore` + `git_sync.PRIVATE_FILES`），只在面板弹窗里录
   - 详见 `dev-logs/2026-10-18-会员账号与私有手机号.md`

---

## P19 审查整改（其余条目）`[执行中]`

审查（2026-10-17）6 项里 #1 由 P17 完成、#2 已单独修（`cc6a9e4`：推理不进执行通道）。
本节点其余条目：

| # | 条目 | 状态 |
|---|---|---|
| #3 撤销范围 | ✅ 并入 P17 阶段 1 |
| **#4 Git 同步** | ✅ **完成**（2026-10-17）：唯一清单 + 手动同步不再 `-A` + 三态回报；派生文件取消跟踪（跟踪数 15 → 11）；`.gitignore` 补 `*.tmp` 等。见 `dev-logs/2026-10-17-Git同步范围收敛.md` |
| #5 迁移闭环 | ✅ **完成**（2026-10-17）：`migrate()` 逐步执行 + 缺一步就拒绝（不再"假装迁过了"）；缺失/损坏/版本过新三种情况分开；坏文件**留档**（`*.corrupt-*.json`）后用默认值继续 + ERROR 日志。见 `dev-logs/2026-10-17-迁移与损坏数据闭环.md` |
| #6 学期事件 | ✅ **完成**（2026-10-17）：事件→面板**显式映射**（`main_workspace.EVENT_PANELS`）+ 未登记事件保守全刷 + 守卫测试扫全仓 emit；`_auto_reload` 发现外部改注册表 → **重绑学期模型** + 发 `"semester"`。顺带修掉 `"saving"` 刷不到记账、`"semester"` 刷不到作业/考试。见 `dev-logs/2026-10-17-数据事件映射.md` |
| 星期几敏感的既有测试 | ⏳ 5 个：`test_reminder_exams` ×3 · `test_ui_fixes::test_statusbar_refreshes_on_data_changed` · `test_course_conflicts::test_day_view_warns_about_conflict`（本地/UTC 跨到 10-18 周日就红；代码路径与本轮改动不相交）|
| **第二轮审查（85a2287..97c52f8）** | ✅ **1~6 已修**（2026-10-18）：写入锁 + `actions_core` 同锁与指纹校验 · `commit --only` · 损坏三态与留档失败禁写 · 撤销只回滚本次覆盖日期 · 迁移内存回滚 · 目录级暂存覆盖删除。见 `dev-logs/2026-10-18-并发与损坏路径加固.md` |
| 第二轮 #7（CLI 委派分帧） | ✅ **已修**（2026-10-18）：服务端按 socket 累积到**换行帧**再解析（并处理连接前已到达的数据）；客户端循环读到换行帧、校验 `ok`/`out` 类型，**不再把非法回复原文当结果**。测试用**真 CLI 子进程 + 分两次写应答**验证 ✓ |
| `fill_prompt:` 借 `data_changed` 传提示词 | ⏳ 不是数据变更、且全仓无消费者（疑似死 emit）→ 应改成专用信号（`schedule_view.py:844`）|
| 文档规范 | ⏳ BLE001 收窄到 Qt 事件边界 · 删文档里会漂移的硬编码数字 · L1 与 DoD 统一 · CI 加 3.14 + 锁文件复现 |

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
  默认只报告，`--strict` 供 CI。修掉了把令牌真值当违规、以及把 `QFont` 第 3 参（字重）误判为字号的 bug。
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
- ⚠ **例外**：`design/tokens.json` 是**运行时**要读的，必须随发行版带上（`design/` 里其余是文档，可带可不带）。
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

---

## P20 后续功能（用户 2026-10-18 追加，待一起评估）

### 新增 · 衣物状态
- 衣服加两个属性：**穿了几天**（`worn_days`）、**是否要洗**（`needs_wash`）
- 与「有什么」的衣物分类联动：穿够天数 / 该洗 → 参与状态或提醒

### 优化 · 天气
- 天气**类型要明确**（不只"阴 / 晴"），温度保留即可
- 用这些数据驱动提醒：**换衣服 / 带伞 / 其他事项**（现在天气只用于展示）

### 新增 · 出门与设备提醒
- **电子设备**：提醒充电 / 检查电量（睡前、上课前两个时点）
- **关键物品归位**：钥匙串、卡包等关键物品，出门前提醒归位到**默认位置**
  （用户口径：`右手架子上`）—— 与电子设备提醒同样做成**小提示框**
- **倒垃圾**：每天**第一次出门**时提醒 —— 要结合日程 / 习惯判断"今天是否会出门"（上课也算出门）
- 在**日程界面**给一条**可以直接 x 掉**的提示信息

### 新增 · 喝水与起身
- **每半小时**提醒喝水 + 起身活动
- 走 **Windows 原生通知**
- 先记两条现成情况，评估时用得上：
  1. 托盘 `showMessage` 在 Win10+ 本来就以**原生 toast** 呈现 —— 所以"原生通知"大概不用另接 API，主要是换**节拍**；
  2. 现有提醒是**每天一次**的日检（`ReminderService` 的定时器），半小时一次需要**另一套节拍**，
     且要考虑免打扰时段 / 只在开机时段跑 / 总提醒开关。

### 新增 · 常备药（按周期补货）
- 「药物」品类加**保质期**属性；常备药按**周期**补货：
  - 到**保质期的 3/4** 时提醒（临期换新）
  - 或剩**常备量的 1/4** 时提醒
- 暂定储备药：盐酸西替利嗪 · 复方金银花颗粒 · 蒲地蓝消炎片 · 罗红霉素 · 氨酚烷胺 · 蒙脱石散
  （量暂时不定）
- 评估时注意两点现成基础：
  1. **"到期日驱动状态"这套已经有了**（会员的 `membership.expires_on` → 需购 / 不足 / 充足，
     还带"读盘时按当前日期重算"）。药品保质期是**同一个形状** —— 把它从"会员专用"推广成
     "任何带到期日的物品"就行，不用另起一套；缺的只是"3/4 时提醒"这个**阈值可配**。
  2. "剩常备量的 1/4"需要一个新的**常备量**字段：现在只有下限 `min_quantity`（"低于就提醒"），
     它不等于"应该常备多少"。两条路：新增 `stock_target`，或者约定
     `min_quantity = 常备量 / 4` 复用现有阈值 —— 评估时二选一。

### 来自 α 测试表备注的缺口（2026-10-18 逐条跑完，状态已更新）
- **分件阈值**：`instances` 各件各自的补货下限，而且是 **or 不是 and**（"任意一种剩 2 根就提醒我补货"）
  —— **已完成**（B1）。α 用例 4 实测通过。
- **嵌套位置**：`柜子4 → 中间`（现在位置词表是扁平的）
  —— **已定口径：不做嵌套模型**，"位置的位置"写进 `--notes`（用户自己的建议）。用例 5/6/20/21/24/31/33/34 实测通过。
- **库存 ↔ 日程跨域**：从库存口语生成日程 / 提醒；日程完成时反过来扣物品
  —— **已完成**（提示词 + `complete_plan`，用例 9/10/16/20 实测通过）。
- **位置别名 / 模糊搜索**：外侧=外面=外边、桌面=桌子，但**衣柜 ≠ 柜子**
  —— **已完成**（B3）。用例 12/24/25 实测通过。
- **按时间估算补货**："还能用半年 / 一个月"（现在只按数量 / 片数阈值）
  —— **待评估**（用例 7/8；现在落在 notes）
- **预算预估**（用例 16 点名）：分期付款 + 自动续费 + 要补货的东西 + 按前几个月预估日常支出
- **日程界面区分学习 / 生活**（用例 13 点名："日程表界面有些拥挤了"）
- **物品间相对关系**（用例 35："手机盒里装着数据线"）
  —— 实测**按 notes 处理已够用**；只有要"按容器检索"时才需要新模型

## P21 AI 可靠性（2026-10-18 新增，依据 `Agent Reliability Engineering Design Guide`）

> 起因：α 测试发现模型"**说了没做**"。挖到根后把"什么算完成"的判定权**从提示词/模型搬进代码**。
> 详见 `dev-logs/2026-10-18-AI可靠性-代码说了算.md`。

**已完成**：
- **汇报权归代码**（§2.3）：模型的自述不算数，按**命令自己的结果**（`OK`/`ERROR`）判定
- **记账类命令不算效果**（`add_location`/`set_locations`）—— 修掉后 bonsai 落库 **6 → 47 件**
- **量化覆盖**（§9.3）：失败报"**N/M 条写命令没有生效**"并逐条列出
- **部分完成上报**（§2.2）：被轮次/时限切断 → "执行 N 条、成功 K 条；可能没记全"
- **重复命令阶梯**（§4.4）：第 2 次告知、第 3 次收束
- **双预算**（§3.3）：轮次 5 + 墙钟 `AI.max_seconds`（默认 90s）
- **护栏桩测试**（§13.4）：不经过模型的确定性测试

**待做**：
- **每轮"守护状态"记录**（§12.1）：现在只记一行 `logger.info`（轮次/耗时/命令数），
  没记"哪些护栏评估过、哪个触发了" —— 排查"为什么这轮停了"时缺的就是这个字段
- **§14 反模式自查表进 CI**：现在靠人工对照
- **`_auto_compress` 只留 16 条**（§10.6 的隐患）：目前被两道挡住（提示词每次从数据重建 +
  `add_item` 同名同位置硬护栏），但**长会话**下仍值得盯

**明确不做**：
- **持久化"副作用台账"**（§12.2）—— 我们天然满足：副作用落在 JSON、提示词每次从数据重建
- **靠换模型解决** —— 设计成立后，模型强弱只影响"一次能办成多少"，不影响"会不会被骗"

