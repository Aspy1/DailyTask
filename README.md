# 生活助手

AI 驱动的 PySide6 桌面日程管理应用。自然语言交互管理课程、作业、考试、日常、记账。

## 技术栈

| 层 | 技术 |
|----|------|
| UI | PySide6，手风琴侧边栏 + 内容区，QSS 暖纸书房主题 |
| 设计 | #F2EFE9 纸白、#B0823A 琥珀金、4px 间距网格 |
| AI | DeepSeek API，sh 命令调用 scripts/actions.py 统一操作脚本 |
| 数据 | JSON 本地存储，原子写入 (.tmp → os.replace)，3s 自动 reload |
| 提醒 | 托盘弹窗 + SMTP 邮件 + GitHub Actions 每日摘要 |
| 插件 | 延迟加载，面板注册 API |
| 移动端 | TG bot 通过 Hermes Gateway 直连 data/ 目录，零同步 |

## 项目结构

```
├── src/
│   ├── app.py                      # 应用入口 · 托盘 · 单实例
│   ├── models/                     # 数据模型
│   │   ├── base.py                 #   BaseJsonModel (原子写入)
│   │   ├── course.py               #   课程 · 学期 · 假期
│   │   ├── task.py                 #   作业 · DDL
│   │   ├── habit.py                #   日常 · 周期 · 打卡
│   │   ├── expense.py              #   支出 · 预算 · 余额
│   │   ├── exam.py                 #   考试 · 日期 · 范围
│   │   └── daily_log.py            #   日程计划 · 储蓄
│   ├── services/                   # 业务服务
│   │   ├── ai_service.py           #   AI 对话 · sh 命令解析
│   │   ├── data_manager.py         #   数据聚合 · 3s 自动 reload
│   │   ├── reminder_service.py     #   提醒 · 邮件 · DDL
│   │   ├── settings_manager.py     #   配置读写
│   │   ├── git_sync.py             #   Git 自动同步
│   │   └── plugin_manager.py       #   插件加载
│   └── ui/                         # 用户界面
│       ├── main_window.py          #   主窗口 · 状态栏 (DDL/课程/习惯)
│       ├── components/             #   布局组件
│       │   ├── sidebar.py          #     手风琴侧边栏 (功能/生活分组)
│       │   ├── main_workspace.py   #     面板切换 (8 面板)
│       │   ├── ai_panel.py         #     AI 助手聊天面板
│       │   └── function_tabs.py    #     功能标签
│       ├── panels/                 #   功能面板
│       │   ├── course_panel.py     #     课程表 (周网格 7×6)
│       │   ├── task_panel.py       #     作业 (三态筛选: 未完成/已完成/全部)
│       │   ├── exam_panel.py       #     考试 (日期/范围/地点)
│       │   ├── habit_panel.py      #     日常 (卡片网格, 仅显示当日)
│       │   ├── expense_panel.py    #     记账 (6 分类)
│       │   ├── settings_panel.py   #     设置 (API/邮箱/余额)
│       │   └── plugins_panel.py    #     插件管理
│       ├── widgets/                #   自定义控件
│       │   ├── schedule_view.py    #     日程视图 (3天 AI 调整)
│       │   ├── course_table.py     #     课程表表格
│       │   └── course_detail_dialog.py
│       └── styles/
│           └── theme.py            #     设计令牌 · QSS
├── scripts/
│   ├── actions.py                  # 统一数据操作脚本 (AI + TG bot 共用)
│   ├── build_index.py              # 模糊搜索索引生成
│   ├── send_digest.py              # GitHub Actions 邮件摘要
│   └── hermes_life.py              # Hermes bot 数据脚本
├── plugins/pomodoro/               # 番茄钟插件
├── data/                           # JSON 数据文件
│   ├── tasks.json / habits.json / courses.json
│   ├── expenses.json / exams.json / daily_logs.json
│   └── search_index.json           # 模糊搜索索引
├── DESIGN_TOKENS.md                # 设计规范
├── 规划书.md                        # 开发规划
├── 接口文档.md                      # API 文档
└── 修改说明.md                      # 变更日志
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
- 按日期排序，3天内红色高亮，7天内橙色
- AI 识别："老师说下周五考试，范围发到微信群"

### 日常
- 卡片网格，三种周期：每日(多次) / 每周几 / 每月N次
- **仅显示当日活跃**，非指定日期隐藏
- 完成打卡/推迟/跳过，连续天数 tag

### 记账
- 6 大分类，月度预算，今日/本月统计
- 校园卡/水卡/电费余额追踪

### AI 助手
- 自然语言 → **sh 命令** → scripts/actions.py 执行
- 统一脚本处理：模糊匹配课程名、中文日期解析、ID 生成、JSON 写入
- 聊天气泡，16 条自动压缩

### 提醒
- DDL 6h 邮件，考试 14/7/3 天托盘+邮件
- 日常提前 5 分钟托盘
- 余额低阈值弹窗
- GitHub Actions 每日摘要

### 系统
- 系统托盘，深色/浅色主题切换
- 单实例锁，Git 自动同步
- 3s 自动检测外部 JSON 修改 (TG bot 写入即时可见)

## 设计令牌

| Token | 浅色 | 用途 |
|-------|------|------|
| `bg_root` | #F2EFE9 | 内容区 |
| `sidebar_bg` | #D0CCC4 | 侧边栏 |
| `card_bg` | #F9F6F0 | 卡片 |
| `accent` | #B0823A | 强调色 |

## 更新日志

### v0.8.1
- 考试卡片 UI 重构 (圆角卡片+倒计时徽章)
- 状态栏精简 (今日消费N | DDL N | 日常x/y | 备考N科)，全部可点击跳转
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
