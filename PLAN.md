# PLAN.md — 大框架整改计划

> 用途：记录本项目**工程/架构层面**的整改项与决策，避免散落在对话里丢失。
> 与 `dev-logs/` 的分工：dev-logs 记"已发生的变更"；本文件记"待做 / 在做 / 已定方向"。
> 最后更新：2026-10-15

## 状态图例

- `[已定]` 方向已确认，待执行
- `[执行中]`
- `[已完成]`
- `[待议]` 需要用户拍板

---

## A. 文档体系

### A-1 `[已定]` 废弃逐文件 `.py.md`，改用单一 `ARCHITECTURE.md`

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

### A-2 `[待议]` 合并两份 `ERRORS.md`（根 `ERRORS.md` 9.6KB vs `MD-files/ERRORS.md` 4KB，内容不同）

### A-3 `[待议]` `AllTheFiles.md` 索引补齐 + 初始化顺序校正 + 去掉写死的行号（`L28-L50`）

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
> 放在 `MD-files/CODE_STANDARDS.md`（已建骨架，条目 Q-A1…Q-G2，逐步补充）。

### D-1 `[已完成]` 规范文档骨架

- `MD-files/CODE_STANDARDS.md`：格式为 **规则 → 为什么 → 如何检查 → 现状**，
  `现状` 标注 `✔ / ✗（见 PLAN）/ ?`。当前已收录结构分层、线程并发、复杂度资源、
  日志调试、安全数据、测试、文档 7 类。

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

## E. 现状基线计划（先做，用数据决定重构优先级）

目的：在动手重构前，先拿到可复现的度量基线，避免凭感觉排优先级。

1. 接入 `ruff + radon + vulture`（此阶段**只报告、不阻断**，数据先于门禁）。
2. `.venv\Scripts\python.exe -m radon cc -n C -s src scripts` → 圈复杂度超阈值清单。
3. `.venv\Scripts\python.exe -m vulture src scripts --min-confidence 80` → 死代码清单。
4. `ruff check`，启用 `T20`（print 残留）、`B`（bugbear）、`S`（bandit 子集）。
5. `pytest --cov=src` → 覆盖率现状（当前仅 scripts/actions 有测试）。
6. 结果回填 `MD-files/CODE_STANDARDS.md` 的 `现状` 列，并生成 `dev-logs/` 报告。
7. 依据结果排序：**线程安全 → 复杂度过高 → 死代码 → 分层违规**。

---

## F. 已完成的框架工作

- `[已完成]` venv + 依赖锁定 + pytest 冒烟测试（commit `5788d61`）
- `[已完成]` `AGENTS.md` 重写（commit `b45a41c`）
- `[已完成]` 规范文档骨架 `MD-files/CODE_STANDARDS.md`
