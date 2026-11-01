# 现代化标准与审查结果（2026-11-01）

> 本文件回答三个问题：**现代桌面应用应该是什么样**（M-xxx 标准）、
> **本项目哪里不够现代**（审查表）、**改成了什么 / 怎么验证**（结果表）。
> 视觉数值的唯一真值仍是 `design/tokens.json`；UI 规范入口是 `design/INDEX.md`。
> 关联：`CODE_STANDARDS.md` Q-B7 / Q-H21 / Q-H22，`dev-logs/2026-11-01-*`。

## 1. 审查方法

1. **按钮级冒烟**：`scripts/ui_button_smoke.py` 枚举每个面板 / 侧边栏 / 状态栏 / 弹窗的
   `QAbstractButton` 并逐个 `click()`，捕获槽异常；菜单/模态框/网络全部换非阻塞替身。
2. **截图审查**：`scripts/ui_render.py` 渲染 49 张（宽/窄 × 浅/深 × 面板/弹窗），
   用 `QT_QPA_FONTDIR=C:\Windows\Fonts` 让中文可读；逐张看布局、裁切、层级、空态。
3. **现代实践对照**：Qt 官方 QThread 生命周期/对象树文档、Windows Fluent 的
   "reduced motion / focus / empty state" 指南、Material 3 的动效与状态规范；
   开源 agent harness 的共同教训：**"说做了"不等于"做了"**，写操作必须有后置校验
   （本项目已在 `ai_service` 的 verifier 中落地，见三步整改报告）。

## 2. 现代化标准（可检查）

| 编号 | 标准 | 检查方式 |
|---|---|---|
| M-001 | 动效只做透明度/短位移，≤ 200ms；提供总开关（减少动态效果） | `animations.py` + 设置页"界面动效" |
| M-002 | 每次面板切换/弹层出现有反馈，但不得改变布局几何 | `fade_in` / `fade_popup` |
| M-003 | 每个数据页面具备**有数据 / 空 / 失败**三态；空态给下一步 | Q-H21；`empty_state()` |
| M-004 | 加载中的控件必须能恢复（按钮不能永远停在 `...`） | 天气刷新回归测试 |
| M-005 | 窄窗口（990×638 + AI 展开）不裁切、不重叠；卡片自动换行 | Q-H22；`FlowGrid` 测试 |
| M-006 | 所有可点控件有文字或 tooltip/accessibleName；图标按钮必须有 | 代码审查 + 按钮冒烟 |
| M-007 | 破坏性操作二次确认；确认文案说明后果 | 现有 `QMessageBox.question` |
| M-008 | 键盘可达：Tab 焦点环、Esc 关闭、对话框默认按钮 | `RoundedButton` 焦点环 |
| M-009 | 颜色/字号/圆角/尺寸 100% 走令牌，禁止硬编码 | `check_ui_tokens.py --strict` |
| M-010 | 内容区不重复系统标题栏标题 | Q-H10；天气弹窗回归测试 |
| M-011 | 状态栏信息与缓存一致；离线首屏不显示 `--` | 天气缓存加载 + 截图 |
| M-012 | 侧边栏高亮始终等于当前面板（含程序化跳转） | 侧边栏同步测试 |
| M-013 | 列表排序指示与实际可排序状态一致 | 任务表 `isSortingEnabled()==False` |
| M-014 | 空页面不是"一大片空白"：标题 + 说明 + 主操作 | `empty_state()` |
| M-015 | 中文字体缺字形时显式 fallback；不把 emoji 放在 QSS 文本里 | 提示文案去 emoji + 字体 families |
| M-016 | QThread 结果信号不得遮蔽 `finished`；退出时等待线程 | Q-B7；结构测试 + `shutdown()` |
| M-017 | 未捕获异常（主线程/子线程）进 `app.log`，可追查 | `error_hook.py` + 测试 |
| M-018 | 外部数据/配置读取可注入目录，测试不碰真实 `data/` | `WeatherService(data_dir=...)` |
| M-019 | 每个新交互有回归测试；按钮集合变化由 CI 冒烟兜住 | `test_ui_smoke_buttons.py` |
| M-020 | 文档单一入口：规范进 `design/INDEX.md`，标准进本文件 | 本文件 + INDEX 行 |

## 3. 审查发现（按严重度）

| # | 现象 | 根因 | 处理 |
|---|---|---|---|
| 1 | 天气详情"未来 3 天"只显示日期 | `_build_forecast_rows` 只把日期标签插进布局，天气/温度/降水标签是**孤儿控件** | 整行容器入布局（`weather_dialog.py`） |
| 2 | 天气刷新崩溃：`QThread: Destroyed while thread is still running` | 三个 QThread 子类自定义 `finished` 遮蔽基类信号，`deleteLater` 在 `run()` 结束前触发 | 改名 `result/failed/done`，回收连 `QThread.finished`；`WeatherService.shutdown()` 等待 |
| 3 | 刷新按钮永远 `...`（未配置 Key） | `refresh()` 直接 return，无错误信号 | 返回 bool + `error_occurred`，弹窗恢复按钮并显示原因 |
| 4 | 离线时状态栏"天气: --" | 缓存文件从未加载 | `_load_cache()` + 启动后主动显示 |
| 5 | 窄窗口汇总卡被裁切 | 5 张卡固定 `QHBoxLayout` | `FlowGrid` 自动换行 |
| 6 | 程序化跳转后侧边栏高亮错误 | `switch_to()` 不通知侧边栏 | `panel_changed` 信号同步 |
| 7 | 提示条 emoji 显示方框 | 中文字体缺字形、QSS 字体回退不稳 | 提示文案去 emoji；`QFont.setFamilies` fallback |
| 8 | 任务表头出现排序箭头但不可排序 | `_refresh()` 末尾 `setSortingEnabled(True)` | 统一关闭 |
| 9 | 天气弹窗内容区重复"天气详情" | 系统标题 + 内容标题 | 内容标题改"实时天气" |
| 10 | 空页面只有一行说明/空白 | 无空态组件 | `empty_state()` 用于近期安排/考试 |
| 11 | 学习进度条轨道几乎不可见 | `item_bg` 4% 太淡 | 轨道改 `border` 令牌 |
| 12 | `qt_zh_CN.qm` 加载失败（用户日志） | `QLibraryInfo` 指向另一个 Qt 安装 | 候选目录（Qt 自报 → PySide6 包内 → prefix） |

## 4. 已落地改动（文件）

- `src/services/weather_service.py`：QThread 信号改名、`shutdown()`、缓存加载、
  `data_dir` 注入、刷新返回 bool。
- `src/services/api_service.py` / `src/services/git_sync.py`：同样修掉 `finished` 遮蔽。
- `src/ui/widgets/weather_dialog.py`：预报整行入布局、错误/空态、标题去重、
  `get_now_updated_at()`、信号断开。
- `src/ui/main_window.py`：启动显示缓存天气、`shutdown()`、侧边栏同步、注入数据目录。
- `src/ui/components/main_workspace.py`：`panel_changed` 信号。
- `src/ui/panels/expense_panel.py`：汇总卡 `FlowGrid`、显式"支出"标签、"今日存钱"。
- `src/ui/panels/task_panel.py`：移除刷新末尾的排序开启。
- `src/ui/panels/routine_panel.py` / `exam_panel.py`：统一空态卡片。
- `src/ui/panels/study_panel.py`：进度条轨道对比度。
- `src/ui/panels/settings_panel.py`：界面动效开关。
- `src/ui/panels/habit_panel.py` / `inventory_panel.py` / `schedule_view.py`：
  accessibleName + tooltip，FAB 圆角走令牌。
- `src/services/error_hook.py`：主线程/子线程未捕获异常落日志。
- `src/services/hints.py`：提示文案去掉 emoji（方框根因）。
- `src/ui/styles/theme.py`：Qt 翻译多目录回退、emoji 字体 fallback。
- `src/ui/widgets/empty_state.py`：统一空态。
- `scripts/ui_button_smoke.py`：按钮级全量冒烟（131 次点击）。
- `scripts/ui_render.py`：补 study/routines/weather 弹窗、沙箱天气缓存。
- `tests/test_weather_dialog.py` / `test_ui_modernization.py` / `test_ui_smoke_buttons.py`：
  对应回归。

## 5. 验证

```bash
.venv/Scripts/python.exe scripts/ui_button_smoke.py     # 131 buttons / 0 errors
QT_QPA_FONTDIR=C:\Windows\Fonts \
  .venv/Scripts/python.exe scripts/ui_render.py --out shots-modern   # 49 张
.venv/Scripts/python.exe -m pytest -q                    # 895 passed
.venv/Scripts/python.exe scripts/ui_walkthrough.py       # 39/39
.venv/Scripts/python.exe scripts/acceptance_check.py     # 79/79
.venv/Scripts/python.exe scripts/ui_visual_audit.py     # 18/18
```

原始输出与关键截图：`dev-logs/evidence/2026-11-01/`。

结果记录在 `dev-logs/2026-11-01-全量冒烟测试报告.md` 与
`dev-logs/2026-11-01-现代化整改报告.md`。

## 6. 仍未做（诚实边界）

- 没有引入真实系统级"减少动态效果"读取（Windows 动画设置 API）；当前是应用内总开关。
- 没有做全量屏幕阅读器（NVDA）实测；只补了 accessibleName/tooltip 与焦点环。
- 天气图标仍是文字/无图标；未做图标字体或 SVG 资源。
- 空态只覆盖近期安排/考试；任务/记账列表在窄窗口下仍以表格为主。
- 截图非像素级基线对比（没有 golden image），只断言尺寸/非空白 + 人工查看。

## 7. 参考

- Qt 6 `QThread` 文档：对象生命周期与 "do not delete a running QThread"。
  https://doc.qt.io/qt-6/qthread.html
- Microsoft Fluent 2 Motion：时长、缓动与 reduced motion。
  https://learn.microsoft.com/windows/apps/design/signature-experiences/motion
- Material 3 Motion：过渡时长/层级。
  https://m3.material.io/styles/motion/overview
- 开源 agent harness 的可靠性共识：写操作后置校验、工具结果回读、失败要显式暴露
  （本项目 `ai_service` verifier + `scripts/ai_eval.py`）。
