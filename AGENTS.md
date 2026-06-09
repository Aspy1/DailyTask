# AGENTS.md — 生活助手项目约束

> Hermes Agent 在此项目中必须遵守的规则。每次操作前自动加载。

## 必须读取的文件

开发任何功能前，必须按顺序查阅：

1. **`MD-files/AllTheFiles.md`** — 全局索引：文件树、初始化顺序、信号总览、禁止清单、术语映射
2. **`MD-files/FORMAT_SPEC.md`** — 文档格式规范
3. **`ERRORS.md`** — 已踩过的坑
4. **要修改的源文件** — 全文通读
5. **对应的 `.py.md` 文档**（如有）— 在 `MD-files/` 镜像目录下
   - 涉及函数合同、信号、数据流、架构决策时必须读
   - trivial 改动（颜色、文案、拼写）可跳过


## 开发/Bug修复流程

### 复杂度分档

| 档次 | 触发条件 | 必做步骤 |
|---|---|---|
| L1 轻 | 改颜色/文案/拼写 | 步骤 7 更新 .py.md |
| L2 中 | 单文件 bug / 小功能 | 步骤 1,3,5,7 |
| L3 重 | 跨文件架构/信号/数据流 | 全部 7 步 |

### 步骤清单

1. **读代码 + 模拟流程**：通读涉及的源文件，模拟数据/信号/线程全链路
2. **查文档**：查对应 .py.md + ERRORS.md 索引 + AllTheFiles.md
3. **描述**：写清 bug 成因/功能执行流程（逐环节，不概括多个 bug）
4. **列 todo**
5. **改代码 + 写日志**：改完后在 `dev-logs/YYYY-MM-DD-主题.md` 记录变更清单
6. **总结**：提炼犯错原因、决策原因
7. **补文档**：更新 .py.md + AllTheFiles.md + ERRORS.md（如有新坑）

### 新增文件规范

- `ERRORS.md`：单文件，索引+条目格式。先查索引再跳转条目。每条 ≤20 行。
- `dev-logs/`：按 `YYYY-MM-DD-主题.md` 平铺。含涉及文件、变更清单、关联条目。

### 代码审查要求

- 声明但未 emit 的 Qt 信号 = typo-like bug。新增信号后必须 `grep 'emit'` 确认有发射点。
- AI prompt 注入点（SYSTEM_PROMPT、_build_system_prompt、各 panel 的动态 prompt）必须格式一致。
- 跨线程信号链（Worker → Service → MainWindow）必须两端都能追踪到 emit → connect → slot。

## 架构红线

- **R-001**：`SettingsManager`、`DataManager`、`AIService` 仅 `App.__init__` 实例化
- **R-002**：数据写入必须经 `DataManager` 或 `actions.py`，禁止直接 `open()`/`json.dump()`
- **R-004**：禁止阻塞主线程，耗时操作放入 `QThread`
- **R-008**：QSS 仅 `#objectName` 选择器，颜色走 `get_colors()` token，禁止硬编码 hex
- 详见 `MD-files/AllTheFiles.md` → 项目级禁止清单

## 文件操作规则

- Windows 环境，bash 故障时用 Python `open()` 读写
- 修改代码前必须语法检查
- 每次功能修改后 commit + push，message ≤60 字英文

## 文档维护规则

- 修改代码后同步更新对应的 `.py.md` 文档
- 新增文件后同步更新 `AllTheFiles.md` 索引和 README.md
- 文档未覆盖的内容不编造，标注 `*（待补）*`
