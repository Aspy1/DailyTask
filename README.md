# 生活助手

AI 驱动的 PySide6 桌面日程管理应用。自然语言交互管理课程、作业、日常、记账。

## 技术栈

| 层 | 技术 |
|----|------|
| UI | PySide6 (Qt for Python)，手风琴侧边栏 + 内容区，QSS 主题 |
| 设计 | 暖纸书房系统 (#F2EFE9 纸白底、#B0823A 琥珀金、4px 间距网格) |
| AI | DeepSeek / OpenAI API，30+ 结构化操作指令 |
| 数据 | JSON 本地存储，原子写入 (.tmp → os.replace) |
| 提醒 | 托盘弹窗 + SMTP 邮件 + GitHub Actions 每日摘要 |
| 插件 | 延迟加载，IsOpen.able 开关，面板注册 API |

## 项目结构

```
├── src/
│   ├── app.py                      # 应用入口 · 托盘 · 单实例
│   ├── models/                     # 数据模型
│   │   ├── base.py                 #   BaseJsonModel (原子写入)
│   │   ├── course.py               #   课程 · 学期 · 假期 · 调休
│   │   ├── task.py                 #   作业 · DDL · 归档
│   │   ├── habit.py                #   日常 · 周期 · 打卡
│   │   ├── expense.py              #   支出 · 预算 · 余额
│   │   └── daily_log.py            #   日程计划 · 储蓄
│   ├── services/                   # 业务服务
│   │   ├── ai_service.py           #   AI 对话 · 指令执行
│   │   ├── data_manager.py         #   数据聚合
│   │   ├── reminder_service.py     #   提醒 · 邮件 · DDL
│   │   ├── settings_manager.py     #   配置读写
│   │   ├── git_sync.py             #   Git 自动同步
│   │   └── plugin_manager.py       #   插件加载
│   └── ui/                         # 用户界面
│       ├── main_window.py          #   主窗口 · 状态栏
│       ├── components/             #   布局组件
│       │   ├── sidebar.py          #     手风琴侧边栏
│       │   ├── main_workspace.py   #     内容区面板切换
│       │   ├── ai_panel.py         #     AI 助手面板
│       │   └── function_tabs.py    #     功能标签
│       ├── panels/                 #   功能面板
│       │   ├── course_panel.py     #     课程表
│       │   ├── task_panel.py       #     作业管理
│       │   ├── habit_panel.py      #     日常
│       │   ├── expense_panel.py    #     记账
│       │   ├── settings_panel.py   #     设置
│       │   └── plugins_panel.py    #     插件
│       ├── widgets/                #   自定义控件
│       │   ├── schedule_view.py    #     日程视图
│       │   ├── course_table.py     #     课程表表格
│       │   └── course_detail_dialog.py
│       └── styles/
│           └── theme.py            #     设计令牌 · QSS
├── scripts/
│   └── send_digest.py              # GitHub Actions 邮件摘要
├── plugins/pomodoro/               # 番茄钟插件
├── data/                           # JSON 数据文件
├── DESIGN_TOKENS.md                # 设计规范
├── 规划书.md                        # 开发规划
├── 接口文档.md                      # API 文档
└── 修改说明.md                      # 变更日志
```

## 功能

### 侧边栏
- 手风琴分组：功能 (日程/课程/作业) + 生活 (日常/记账)
- 三角箭头展开动画，灰色侧边栏 + 暖纸白内容区

### 日程视图 (首页)
- 时间轴卡片：课程 (琥珀金)、计划 (绿色)、日常 (含完成态)
- DDL 截止线标记，当前时段 ▶ 箭头
- 快速调整按钮 (AI 排程)

### 课程表
- 周网格 7×6，暖纸淡色块区分课程
- 自动过滤单双周
- 右键菜单：修改/删除/查看事项/布置作业

### 作业管理
- 表格视图，复选框完成，DDL 红标倒计时
- 课程/时间筛选，分页
- 自动归档，唯一 ID 防重复

### 日常
- 卡片网格，三种周期：每日 (多次) / 每周几 / 每月 N 次
- 连续天数 tag，完成打卡/推迟/跳过
- 附加事项自动生成待办

### 记账
- 6 大分类，月度预算
- 今日/本月统计卡片
- 校园卡/水卡/电费余额追踪

### AI 助手
- 自然语言 → JSON 指令 → 程序执行
- 关键词分流：作业/习惯/日程/记账
- 聊天气泡，16 条自动压缩

### 提醒
- DDL 6h 邮件，考试 14/7/3 天托盘
- 日常提前 5 分钟托盘
- 余额低阈值弹窗
- GitHub Actions 每日摘要 (课程/计划/日常/DDL/支出)

### 系统
- 系统托盘，开机自启
- 深色/浅色主题切换
- 单实例锁，Git 自动同步

## 设计令牌

| Token | 浅色 | 深色 | 用途 |
|-------|------|------|------|
| `bg_root` | #F2EFE9 | #1E1D1A | 内容区 |
| `sidebar_bg` | #D0CCC4 | #1A1917 | 侧边栏 |
| `card_bg` | #F9F6F0 | #2C2B27 | 卡片 |
| `accent` | #B0823A | #D4A853 | 强调色 |

## 更新日志

### v0.7.1
- 修复任务 ID 重复 bug (add() 唯一 ID 生成)
- 修复任务复选框标记回环 (toggled→clicked)
- 修复 DDL 计数不实时刷新
- 修复日常 describeSchedule 缺失

### v0.7.0
- 手风琴侧边栏布局
- 暖纸书房设计系统全面落地
- 日常三种周期 (每日多次/每周几/每月N次)
- 深色模式完整色系

### v0.4.0
- 暖纸白 + 琥珀金设计令牌
- 全量去硬编码颜色
- QFrame→QWidget 卡片迁移
