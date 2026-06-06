# 生活助手

AI 驱动的 PySide6 桌面日程管理应用。通过自然语言交互管理课程、作业、习惯、记账、余额和自定义提醒，支持插件扩展。

## 技术栈

| 层 | 技术 |
|----|------|
| UI | PySide6（Qt for Python），PCL 风格顶部导航，QSS 主题 |
| AI | DeepSeek / Claude API，30+ 结构化操作指令，上下文自动压缩 |
| 数据 | JSON 本地存储，原子写入（`.tmp` → `os.replace`，5 次重试），INI 配置 |
| 定时 | GitHub Actions 每日摘要 + 本机 SMTP 邮件 + 托盘弹窗 |
| 签名 | SSH (ed25519) 提交签名，GitHub 验证通过 |
| 插件 | 延迟加载，`IsOpen.able` 开关，面板注册 API |

## 功能

### 学习
- **日程视图**（默认首页） — 按时段展示课程、自定义计划、习惯，左侧 ▶ 指示当前时间，截止日标记线（任务名红字加粗居中）
- **课程表** — 周视图网格，多时段渲染（默认 5 节/天），周段解析，教师轮换，右键重命名/删除/查看关联作业
- **作业** — 表格视图，课程/时间筛选，复选框完成，DDL 状态栏红标 + 日期标红 + `(N天后)` 倒计时，自动归档已完成任务

### 生活
- **生活习惯** — 响应式卡片网格（210×135），每周固定日 / 每隔 N 天双模式，附加事项自动生成待办，右键推迟/取消今天，托盘提前 5 分钟提醒
- **记账** — 6 大分类支出、月度预算、今日/本月/预算剩余三卡片，校园卡/水卡支付自动扣减余额
- **存钱助手** — 记录每日省钱金额，月度汇总
- **余额追踪** — 校园卡 / 水卡 / 电费余额低于阈值托盘弹窗 + 邮件（每日一次）

### AI 助手
- 自然语言输入 → 结构化 JSON 指令 → 程序执行
- **关键词分流**：老师布置/作业/考试 → 作业 | 我习惯 → 习惯 | 提醒我/记得 → 自定义日程
- **操作覆盖**：课程增删改/批量导入、作业增删改完成、习惯增删改推迟取消（含附加事项）、记账增删改/预算、存钱记录/删除、余额查询更新、日程计划添加删除、假期/调休识别
- 聊天气泡 + Markdown 渲染，16 条消息自动压缩

### 提醒
- **本机**：DDL 6 小时内邮件、考试 14/7/3 天邮件 + 托盘、习惯提前 5 分钟托盘、余额每日检测
- **自定义邮件提醒**：日程任意项右键 → 时间选择器 → 本机 SMTP 发送，过去时间自动拒绝
- **GitHub Actions**：每日 04:55 北京时间摘要（课程/计划/习惯/DDL/考试/余额）
- 启动漏检补发、DDL 3 天内红点 + 托盘闪烁

### 系统
- 系统托盘（右键退出/同步/切换主题）、开机自启动（Windows 注册表）
- 单实例锁（QLocalServer）
- 深色 / 浅色全局主题切换（QApplication 级 `setStyleSheet`，所有面板 `refresh_theme()`）
- 统一设计系统：暖纸白浅色主题、琥珀金强调色、4px 间距网格、三级圆角、四态按钮
- 凌晨 0-1 点按前一天计算（`schedule_date()`）
- Git 自动同步（30 秒防抖 + 手动同步按钮）+ SSH 签名提交
- 假期/调休系统（AI 识别 → `excluded` 跳过课表 + `makeup` 映射）

### 插件
- 延迟加载 `PluginManager`，`IsOpen.able` 开关，设置页 + 小功能页两处管理
- `register_panel(name, factory)` API，示例：**番茄钟**（`plugins/pomodoro`）

## 运行

```bash
pip install -r requirements.txt
python main.py
```

## 项目结构

```
日程规划/
├── main.py                      # 入口
├── requirements.txt
├── README.md
├── DESIGN_TOKENS.md             # 设计标准规范（配色/字体/间距/圆角/按钮/阴影）
├── design-showcase.html         # 设计标准可视化展示页
├── PLUGINS.md                   # 插件开发文档
├── 规划书.md                     # 项目总结与路线图
├── 接口文档.md                   # 类依赖关系、信号流、初始化顺序
├── src/
│   ├── app.py                   # QApplication、托盘、单实例、自启动、初始化顺序
│   ├── models/                  # 数据模型（不依赖 Qt）
│   │   ├── base.py              #   BaseJsonModel：原子写入、版本迁移、reload
│   │   ├── course.py            #   课程、学期、假期/调休、schedule_date
│   │   ├── task.py              #   作业、DDL、自动归档
│   │   ├── habit.py             #   习惯、周期、附加事项、推迟/取消
│   │   ├── expense.py           #   支出、分类、预算
│   │   └── daily_log.py         #   日程计划、省钱、自定义提醒
│   ├── services/
│   │   ├── data_manager.py      #   数据中枢、信号、reload_all
│   │   ├── ai_service.py        #   DeepSeek/Claude、指令解析、上下文压缩
│   │   ├── reminder_service.py  #   定时检查、邮件/托盘、catch-up、自定义提醒
│   │   ├── git_sync.py          #   30s 防抖自动 commit + SSH 签名
│   │   ├── settings_manager.py  #   INI 读写、API Key 管理
│   │   └── plugin_manager.py    #   插件扫描、延迟加载、面板注册
│   ├── ui/
│   │   ├── main_window.py       #   顶部导航（学习/生活/设置/小功能/更多/AI）
│   │   ├── components/
│   │   │   ├── main_workspace.py  # 标签页切换、refresh_theme
│   │   │   └── ai_panel.py        # AI 聊天气泡、Markdown 渲染
│   │   ├── panels/              #   课程、作业、习惯、记账、设置、插件
│   │   ├── widgets/             #   日程视图、课程表、课程详情弹窗
│   │   └── styles/              #   主题 QSS + get_colors()
│   └── i18n/                    # 中文字符串（zh-CN.json）
├── plugins/
│   └── pomodoro/                # 番茄钟示例插件
│       ├── IsOpen.able               # 启用标记
│       └── plugin.py                 # register(api)
├── scripts/
│   └── send_digest.py           # GitHub Actions 每日摘要（北京时间）
├── .github/workflows/           # CI：每日摘要 (cron: 55 20 UTC)
└── data/                        # 用户数据（JSON + settings.ini）
```

## 相关文档

- [DESIGN_TOKENS.md](DESIGN_TOKENS.md) — 设计标准规范：配色/字体/间距/圆角/按钮/阴影/动效
- [design-showcase.html](design-showcase.html) — 设计标准可视化展示（浏览器打开）
- [规划书.md](规划书.md) — 32 项已实现功能、11 个开发问题、三段式路线图
- [接口文档.md](接口文档.md) — 初始化顺序约束、信号流向图、类依赖矩阵、常见崩溃场景
- [PLUGINS.md](PLUGINS.md) — 插件目录规范、API、示例
- [修改说明.md](修改说明.md) — 版本修改记录
