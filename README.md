# 生活助手

AI 驱动的 PySide6 桌面日程管理应用。自然语言交互管理课程、作业、考试、日常、记账。

## 技术栈

| 层 | 技术 |
|----|------|
| UI | PySide6，手风琴侧边栏 + 内容区，QSS 暖纸书房主题 |
| 设计 | #F2EFE9 纸白、#B0823A 琥珀金、4px 间距网格 |
| AI | DeepSeek API，sh 命令 → 内存调用 actions.py (无 subprocess 开销) |
| 数据 | JSON 本地存储，原子写入，3s 增量 reload，hash 跳过未变 widget |
| 提醒 | 托盘弹窗 + SMTP 邮件 + GitHub Actions 每日摘要 |
| 插件 | 延迟加载，面板注册 API |
| 移动端 | TG bot 通过 Hermes Gateway 直连 data/ 目录，零同步 |

## 开发环境

```powershell
# 1. 创建虚拟环境（需 Python >= 3.12，见 pyproject.toml）
python -m venv .venv

# 2. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 3. 运行测试
.venv\Scripts\python.exe -m pytest
```

- 依赖声明：`requirements.txt`（直接依赖，兼容区间）→ `requirements.lock.txt`（精确锁定，用于复现）
- 复现环境：`.venv\Scripts\python.exe -m pip install -r requirements.lock.txt`
- 启动：`.venv\Scripts\python.exe main.py`

## 项目结构

```
├── main.py                         # 入口
├── AGENTS.md                       # AI Agent 开发约束
├── ERRORS.md                       # 已踩坑索引
├── README.md
├── PLAN.md                         # 大框架整改计划
├── pyproject.toml                  # requires-python + pytest 配置
├── requirements.txt                # 运行时依赖（区间）
├── requirements-dev.txt            # 开发/测试依赖
├── requirements.lock.txt           # 精确锁定版本
├── src/
│   ├── app.py                      # 应用入口 · 托盘 · 单实例
│   ├── models/                     # 数据模型 (7 models + base)
│   │   ├── base.py                 #   BaseJsonModel (原子写入)
│   │   ├── course.py               #   课程 · 学期 · 假期
│   │   ├── task.py                 #   作业 · DDL
│   │   ├── habit.py                #   日常 · 周期 · 打卡
│   │   ├── expense.py              #   支出 · 预算 · 余额
│   │   ├── exam.py                 #   考试 · 日期 · 范围
│   │   ├── daily_log.py            #   日程计划 · 储蓄 · 自定义提醒
│   │   └── inventory.py            #   物品库存 · 5 分类
│   ├── services/                   # 业务服务 (8)
│   │   ├── ai_service.py           #   AI 对话 · Agent Loop · DeepSeek 余额
│   │   ├── data_manager.py         #   数据聚合 · 3s 自动 reload
│   │   ├── reminder_service.py     #   提醒 · 邮件 · DDL
│   │   ├── settings_manager.py     #   配置读写
│   │   ├── weather_service.py      #   和风天气 · 实时/7 天预报
│   │   ├── api_service.py          #   Open-Meteo / 余额查询 worker
│   │   ├── git_sync.py             #   Git 自动同步
│   │   └── plugin_manager.py       #   插件加载
│   └── ui/                         # 用户界面
│       ├── main_window.py          #   主窗口 · 状态栏 · AI 调整链路
│       ├── components/             #   布局组件
│       │   ├── sidebar.py          #     手风琴侧边栏（含「更多」菜单）
│       │   ├── main_workspace.py   #     面板切换 (9 面板)
│       │   ├── ai_panel.py         #     AI 助手聊天面板
│       │   └── click_label.py      #     可点击 Label 公共组件
│       ├── panels/                 #   功能面板
│       │   ├── course_panel.py     #     课程表 (周网格 7×6)
│       │   ├── task_panel.py       #     作业 (多选筛选 + 分页)
│       │   ├── exam_panel.py       #     考试
│       │   ├── habit_panel.py      #     日常 (卡片网格)
│       │   ├── expense_panel.py    #     记账 (6 分类)
│       │   ├── inventory_panel.py  #     有什么 (分类筛选 + 标签编辑)
│       │   ├── settings_panel.py   #     设置
│       │   └── plugins_panel.py    #     插件管理
│       ├── widgets/                #   自定义控件
│       │   ├── schedule_view.py    #     日程视图 (增量更新 + AI 调整)
│       │   ├── course_table.py     #     课程表表格
│       │   ├── course_detail_dialog.py
│       │   ├── context_menu.py     #     通用右键菜单
│       │   ├── toggle_switch.py    #     开关控件
│       │   └── api_test_dialog.py  #     API 连通性测试
│       └── styles/
│           ├── theme.py            #     设计令牌加载 · QSS
│           └── tokens.json         #     设计令牌单一真值
├── scripts/
│   ├── actions.py                  # 统一数据操作 (16 命令 + 内存调用)
│   ├── build_index.py              # 模糊搜索索引
│   ├── send_digest.py              # GitHub Actions 邮件摘要
│   ├── gen_design_tokens.py        # 从 tokens.json 生成 DESIGN_TOKENS.md
│   ├── check_ui_tokens.py          # UI 令牌约束检查（--strict 供 CI）
│   └── rewrite_history.py          # 历史重写脚本（一次性工具）
├── tests/                          # pytest 测试（9 个测试文件 + conftest/helpers）
├── MD-files/                       # 文档体系
│   ├── ARCHITECTURE.md             #   项目运作原理（分层/数据流/信号/不变量/schema）
│   ├── CODE_STANDARDS.md           #   代码与工程规范（Q-xxx，可检查）
│   ├── DEV_PRINCIPLES.md           #   可迁移的通用开发准则
│   ├── DESIGN_TOKENS.md            #   设计令牌（由脚本生成）
│   ├── PLUGINS.md                  #   插件开发约定
│   ├── AllTheFiles.md              #   索引 · 术语映射 · 决策记录
│   ├── 规划书.md · 接口文档.md · 修改说明.md
├── dev-logs/                       # 开发日志
├── plugins/pomodoro/               # 番茄钟插件（当前禁用：IsOpen.able.disable）
├── resources/                      # 运行时资源（image.png）
└── data/                           # 用户数据（JSON + settings.ini，永不进发行版）
    └── backup/                     #   自动备份
```

## 功能

### 日程视图 (首页)
- 时间轴卡片：课程/计划/日常，DDL 截止线，当前时段箭头
- **AI 调整**：一键生成 3 天日程快照 → AI 排程 → 备份 → 撤销/保存
- 课程表/前一天/后一天/今天导航

### 课程表
- 周网格 7×6，自动过滤单双周
- 右键菜单：修改/删除/查看作业
- AI 批量导入

### 作业管理
- 表格视图，复选框完成，DDL 红标倒计时
- **三态筛选**：未完成 → 已完成 → 全部（替换旧归档功能）
- 截止时间列宽 175px，课程/时间筛选，分页

### 考试 (新增)
- 日期/课程/范围/地点/备注
- 按日期排序，**7天内红色、15天内橙色**高亮
- AI 识别："老师说下周五考试，范围发到微信群"

### 日常
- 卡片网格，三种周期：每日(多次) / 每周几 / 每月N次
- **仅显示当日活跃**，非指定日期隐藏
- 完成打卡/推迟/跳过，连续天数 tag

### 记账
- 6 大分类，月度预算，今日/本月统计
- 校园卡/水卡/电费余额追踪

### 有什么 (新增)
- 物品库存管理：5 大分类（日常消耗品/数码电子/衣物/虚拟品类/其他）
- **仅 AI 操作**：手动添加已移除，全部通过 AI 对话管理
- 分类筛选 + 标签筛选 + 分页
- 右键菜单：修改标签（多标签并存，双击编辑）、标记需购/充足、邮件提醒、删除
- DeepSeek API 额度自动查询（5 分钟缓存）
- 存放地点自由文本：衣柜-左侧上层、抽屉-右侧

### AI 助手
- 自然语言 → **sh 命令** → 内存调用 actions.py (无 subprocess 开销)
- 16 种数据操作：add/complete task, add exam, add/log habit, add/replace/delete plan, add/delete course, add/update/delete/lookup item, need_restock, status
- 统一脚本处理：模糊匹配课程名、中文日期解析（含"下周X"/"下午3点"，保留具体时间）、ID 生成、JSON 写入
- Agent Loop 最多 5 轮自动调用
- 聊天气泡，16 条自动压缩
- 快速调整：一键生成日程快照 → AI 排程 → 备份 → 撤销/保存

### 提醒
- DDL 6h 邮件，考试 14/7/3 天**托盘 + 邮件**（每个阈值各提醒一次，不重复轰炸）
- 日常提前 5 分钟托盘
- 余额低阈值托盘 + 邮件
- GitHub Actions 每日摘要（含 exams.json 的考试提醒）

### 系统
- 系统托盘，深色/浅色主题切换（侧边栏「更多…」）
- 单实例锁，Git 自动同步
- 3s 自动检测外部 JSON 修改 (TG bot 写入即时刷新界面)

## 设计令牌

| Token | 浅色 | 用途 |
|-------|------|------|
| `bg_root` | #F2EFE9 | 内容区 |
| `sidebar_bg` | #D0CCC4 | 侧边栏 |
| `card_bg` | #F9F6F0 | 卡片 |
| `accent` | #B0823A | 强调色 |

## 更新日志

### v0.9.1
- 功能可用性排查（15 项缺陷）与修复，详见 `dev-logs/2026-10-16-功能可用性排查.md`
- 修复作业 DDL **具体时间被丢弃**（`14:30`/`下午3点` 一律变 `23:00`），并拒绝无法解析的日期
- 修复"下周X"比正确日期晚一周；支持 `10-25` 月日格式
- 考试提醒/每日摘要改为读 `exams.json`（此前考试模块的提醒从未触发），且每个阈值只提醒一次
- 外部（TG）写入后界面就地刷新；`save_all()` 补全 7 个模型
- 侧边栏新增「更多…」入口，深浅色主题切换从此可达
- AI 提示词与 `actions.py` 命令集双向对齐（删 3 条不存在的命令、补 3 条漏宣传的、补 `delete_item` CLI）
- `add_item --quantity 0` 正确记为"需购"
- AI 系统提示词不再在主线程同步查余额/天气（改后台预热）
- 模型默认值改深拷贝，避免实例之间数据串味

### v0.9.0
- 性能优化三刀：show 提前 / 增量 refresh (hash skip) / actions 内存调用
- 物品库存 (有什么)：5 分类、标签编辑器、AI 驱动
- 虚拟品类 + DeepSeek API 余额自动查询
- 分类筛选从 model 读 (修只显示"其他"的 bug)
- 手动添加物品移除，全部依靠 AI
- delete_item 命令补齐
- 窗口默认大小 +10%
- AGENTS.md 开发约束 (分档流程 + 改后模拟)
- dev-logs/ ERRORS.md 文档体系

### v0.8.2
- 清理死代码 (context_sidebar/function_tabs/hermes_life, -665行)
- ClickLabel 提取为公共组件
- 调整信号链修复 (finished_with_instructions emit)

### v0.8.1
- 考试卡片 UI 重构 (圆角卡片+倒计时徽章)
- 状态栏精简 (今日消费N | DDL N | 日常x/y | 备考N科)
- AI 整理日程信号链三重修复，全部可点击跳转
- 状态栏考试阈值 7天红/15天橙
- DDL 线自适应单行，居中，可点击跳转
- AI 上下文注入当前周次+单双周
- DDL 计数改为按天比较
- ClickLabel 统一：仅左键触发，默认手型光标
- 移除购物标签，日常空态显示"今日无事"

### v0.8.0
- 考试模块 (模型+面板+AI识别)
- AI 重构: JSON→sh命令, scripts/actions.py 统一脚本
- 作业三态筛选 (替换归档)
- 日程 3 天 AI 调整 + 撤销/保存
- 日常仅显示当日, 卡片背景色
- TG bot 直连 data/ (Hermes Gateway)
- DDL 列宽扩展, 状态栏空 DDL 提示

### v0.7.1
- 修复任务 ID 重复、复选框回环、DDL 计数刷新

### v0.7.0
- 手风琴侧边栏, 暖纸书房设计系统
- 日常三种周期
