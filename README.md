# 生活助手

AI 驱动的 PySide6 桌面日程管理应用。自然语言交互管理课程、作业、日常、记账、余额和自定义提醒，支持插件扩展。

## 技术栈

| 层 | 技术 |
|----|------|
| UI | PySide6（Qt for Python），手风琴侧边栏 + 内容区布局，QSS 主题 |
| 设计 | 暖纸书房系统（#F2EFE9 纸白底、#B0823A 琥珀金、4px 间距网格） |
| AI | DeepSeek / Claude API，30+ 结构化操作指令，上下文自动压缩 |
| 数据 | JSON 本地存储，原子写入（`.tmp` → `os.replace`，5 次重试），INI 配置 |
| 定时 | GitHub Actions 每日摘要 + 本机 SMTP 邮件 + 托盘弹窗 |
| 签名 | SSH (ed25519) 提交签名 |

## 项目结构

```
├── .github/workflows/
│   └── daily-digest.yml          # GitHub Actions 每日邮件摘要
├── data/                         # JSON 数据文件
│   ├── courses.json              # 课程
│   ├── tasks.json                # 作业
│   ├── habits.json               # 日常事项
│   ├── expenses.json             # 记账
│   ├── daily_logs.json           # 日程计划
│   └── settings.ini              # 配置
├── plugins/pomodoro/             # 番茄钟插件
├── scripts/
│   └── send_digest.py            # 邮件摘要脚本
├── src/
│   ├── i18n/                     # 国际化
│   ├── models/                   # 数据模型
│   │   ├── course.py             # 课程 · 学期 · 假期
│   │   ├── task.py               # 作业 · DDL · 归档
│   │   ├── habit.py              # 日常 · 周期 · 打卡
│   │   ├── expense.py            # 支出 · 预算 · 余额
│   │   └── daily_log.py          # 日程计划
│   ├── services/                 # 业务服务
│   │   ├── ai_service.py         # AI 对话 · 指令执行
│   │   ├── data_manager.py       # 数据聚合
│   │   ├── reminder_service.py   # 提醒 · 邮件 · 托盘
│   │   ├── settings_manager.py   # 配置读写
│   │   ├── git_sync.py           # Git 自动同步
│   │   └── plugin_manager.py     # 插件加载
│   ├── ui/
│   │   ├── main_window.py        # 主窗口 · 状态栏 · 主题切换
│   │   ├── components/
│   │   │   ├── sidebar.py        # 手风琴侧边栏（功能/生活分组）
│   │   │   ├── main_workspace.py # 内容区面板切换
│   │   │   └── ai_panel.py       # AI 助手面板
│   │   ├── panels/
│   │   │   ├── course_panel.py   # 课程表
│   │   │   ├── task_panel.py     # 作业管理
│   │   │   ├── habit_panel.py    # 日常（习惯打卡）
│   │   │   ├── expense_panel.py  # 记账
│   │   │   ├── settings_panel.py # 设置
│   │   │   └── plugins_panel.py  # 插件
│   │   ├── widgets/
│   │   │   ├── schedule_view.py  # 日程视图（首页）
│   │   │   ├── course_table.py   # 课程表表格
│   │   │   └── course_detail_dialog.py
│   │   └── styles/
│   │       └── theme.py          # 设计令牌 · QSS 生成
│   └── app.py                    # 应用入口 · 托盘 · 单实例
├── main.py                       # 启动入口
├── DESIGN_TOKENS.md              # 设计规范文档
├── design-showcase.html          # 设计展示页
├── sidebar-preview.html          # 侧边栏预览
└── requirements.txt
```

## 功能

### 侧边栏导航
- 手风琴分组：**功能**（日程总览 / 课程表 / 作业管理）+ **生活**（日常 / 记账 / 有什么 / 吃什么）
- 底部固定：设置 + 关于 + AI 助手开关
- 灰色侧边栏（#D0CCC4）+ 暖纸白内容区（#F2EFE9）

### 学习
- **日程视图**（首页）— 按时段展示课程、计划、日常，DDL 截止线标记，快速调整按钮（AI 自动排程）
- **课程表** — 周视图网格，暖纸配色（琥珀金/鼠尾草/陶土等淡色块），右键操作菜单
- **作业** — 表格视图，课程/时间筛选，DDL 红标倒计时，复选框完成，自动归档

### 生活
- **日常** — 卡片网格（HTML 预览风格），三种周期：每日（支持一日多次）/ 每周几 / 每月 N 次，连续天数 tag，完成打卡/推迟/跳过按钮
- **记账** — 分类支出、月度预算、今日/本月统计卡片
- **有什么**（规划中）— 物品统计与分类管理
- **吃什么**（规划中）— 菜品记录与智能推荐

### AI 助手
- 自然语言 → 结构化 JSON 指令 → 程序执行
- 发送后即时反馈"AI 正在准备回答…"
- 操作覆盖：课程增删改、作业增删改完成、日常增删改推迟取消、记账增删改预算、余额查询、日程计划、假期调休
- 聊天气泡（用户=琥珀金圆角框，AI=纯文+左边框），16 条消息自动压缩

### 提醒
- **本机**：DDL 6 小时内邮件、考试 14/7/3 天托盘、日常提前 5 分钟托盘、余额低阈值弹窗
- **GitHub Actions**：每日 04:55（北京时间）邮件摘要（课程/计划/日常/DDL/考试/支出/购物需求/余额）
- 启动漏检补发、DDL 3 天内红点

### 系统
- 系统托盘、开机自启动（Windows 注册表）、单实例锁
- 深色 / 浅色全局主题切换（暖纸暗色调色板）
- 凌晨 0-1 点按前一天计算
- Git 自动同步（30 秒防抖）

## 设计系统

详细规范见 `DESIGN_TOKENS.md`。核心令牌：

| Token | 浅色 | 深色 | 用途 |
|-------|------|------|------|
| `bg_root` | #F2EFE9 | #1E1D1A | 内容区背景 |
| `bg_surface` | #E0DDD6 | #252421 | 面板/工具栏 |
| `sidebar_bg` | #D0CCC4 | #1A1917 | 侧边栏 |
| `card_bg` | #F9F6F0 | #2C2B27 | 卡片 |
| `accent` | #B0823A | #D4A853 | 强调色 |

## 更新日志

### v0.5.0 (2025-06-06)
- 重构为手风琴侧边栏布局（废弃横排导航）
- 日常改名 + 卡片重设计（连续天数 tag、完成打卡/推迟/跳过）
- 习惯周期改为三种：每日（多次）/ 每周几 / 每月 N 次
- 课程表暖纸配色（去五颜六色）
- 深色模式完整色系
- 状态栏增加"N 项日常"和购物需求
- AI 发送即时反馈 + 日程快速调整
- 每日邮件摘要增加支出和购物需求

### v0.4.0
- 主题从深色改为暖纸白 + 琥珀金
- 全量去除硬编码颜色，统一 token 系统
- 卡片从 QFrame 迁移到 QWidget（解决圆角 artifact）
- 作业面板、AI 面板、设置面板 UI 优化
