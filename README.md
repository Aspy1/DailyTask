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

## 项目结构

```
├── main.py                         # 入口
├── AGENTS.md                       # AI Agent 开发约束
├── ERRORS.md                       # 已踩坑索引
├── README.md
├── src/
│   ├── app.py                      # 应用入口 · 托盘 · 单实例
│   ├── models/                     # 数据模型 (7 models)
│   │   ├── base.py                 #   BaseJsonModel (原子写入)
│   │   ├── course.py               #   课程 · 学期 · 假期
│   │   ├── task.py                 #   作业 · DDL
│   │   ├── habit.py                #   日常 · 周期 · 打卡
│   │   ├── expense.py              #   支出 · 预算 · 余额
│   │   ├── exam.py                 #   考试 · 日期 · 范围
│   │   ├── daily_log.py            #   日程计划 · 储蓄
│   │   └── inventory.py            #   物品库存 · 5 分类
│   ├── services/                   # 业务服务 (6 services)
│   │   ├── ai_service.py           #   AI 对话 · Agent Loop · DeepSeek 余额
│   │   ├── data_manager.py         #   数据聚合 · 3s 自动 reload
│   │   ├── reminder_service.py     #   提醒 · 邮件 · DDL
│   │   ├── settings_manager.py     #   配置读写
│   │   ├── git_sync.py             #   Git 自动同步
│   │   └── plugin_manager.py       #   插件加载
│   └── ui/                         # 用户界面
│       ├── main_window.py          #   主窗口 · 状态栏 · AI 调整链路
│       ├── components/             #   布局组件
│       │   ├── sidebar.py          #     手风琴侧边栏
│       │   ├── main_workspace.py   #     面板切换 (9 面板)
│       │   ├── ai_panel.py         #     AI 助手聊天面板
│       │   └── click_label.py      #     可点击 Label 公共组件
│       ├── panels/                 #   功能面板
│       │   ├── course_panel.py     #     课程表 (周网格 7×6)
│       │   ├── task_panel.py       #     作业 (多选筛选 + 分页)
│       │   ├── exam_panel.py       #     考试
│       │   ├── habit_panel.py      #     日常 (卡片网格)
│       │   ├── expense_panel.py    #     记账 (5 分类)
│       │   ├── inventory_panel.py  #     有什么 (分类筛选 + 标签编辑)
│       │   ├── settings_panel.py   #     设置
│       │   └── plugins_panel.py    #     插件管理
│       ├── widgets/                #   自定义控件
│       │   ├── schedule_view.py    #     日程视图 (增量更新 + AI 调整)
│       │   ├── course_table.py     #     课程表表格
│       │   └── course_detail_dialog.py
│       └── styles/
│           └── theme.py            #     设计令牌 · QSS
├── scripts/
│   ├── actions.py                  # 统一数据操作 (15 命令 + 内存调用)
│   ├── build_index.py              # 模糊搜索索引
│   └── send_digest.py              # GitHub Actions 邮件摘要
├── MD-files/                       # ATF 文档体系
│   ├── AllTheFiles.md              #   全局索引
│   ├── FORMAT_SPEC.md              #   格式规范
│   └── src/                        #   逐文件 .py.md (35 文件)
├── dev-logs/                       # 开发日志
├── plugins/pomodoro/               # 番茄钟插件
├── data/                           # JSON 数据 (8 files)
│   └── backup/                     #   自动备份
├── DESIGN_TOKENS.md
├── 规划书.md
├── 接口文档.md
└── 修改说明.md
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

### 有什么 (新增)
- 物品库存管理：5 大分类（日常消耗品/数码电子/衣物/虚拟品类/其他）
- **仅 AI 操作**：手动添加已移除，全部通过 AI 对话管理
- 分类筛选 + 标签筛选 + 分页
- 右键菜单：修改标签（多标签并存，双击编辑）、标记需购/充足、邮件提醒、删除
- DeepSeek API 额度自动查询（5 分钟缓存）
- 存放地点自由文本：衣柜-左侧上层、抽屉-右侧

### AI 助手
- 自然语言 → **sh 命令** → 内存调用 actions.py (无 subprocess 开销)
- 15 种数据操作：add/complete/delete task, add/delete exam, add/log habit, add/replace/delete plan, add/delete course, add/update/delete/lookup item, need_restock, status
- 统一脚本处理：模糊匹配课程名、中文日期解析、ID 生成、JSON 写入
- Agent Loop 最多 5 轮自动调用
- 聊天气泡，16 条自动压缩
- 快速调整：一键生成日程快照 → AI 排程 → 备份 → 撤销/保存

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
