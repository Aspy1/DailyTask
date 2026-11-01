# design/ — UI 规范总入口

> **动 UI 之前先读这个文件。** 这里列出所有"令牌 / 模板 / 规范"的**权威位置**。
> 如果这里**没有**你要的规范：**先问用户**，确认后再创建，并把新条目补进本文件（见 `AGENTS.md` §9）。
>
> 最后更新：2026-11-01

## 1. 按"我要改什么"查

| 我要改… | 权威位置 | 说明 |
|---|---|---|
| **颜色 / 字号 / 圆角** 的具体值 | `design/tokens.json` | **唯一真值**（51 键 × 深浅两模式 + 字号 + 圆角刻度）。改完跑 `scripts/gen_design_tokens.py` 同步文档 |
| **控件 / 布局尺寸**（窗口、弹窗、列表、窄输入） | `design/tokens.json` 的 `controls` / `layout` → `theme.CONTROLS` / `theme.LAYOUT` | 代码只写 `LAYOUT["dialog_width_lg"]`，不写 `setMinimumWidth(420)`（`Q-H20`） |
| 令牌的**用途说明** | `design/tokens.json` 的 `color_notes` / `size_notes` | 与值同文件，避免两处漂移 |
| 令牌的**人类可读表** | `design/DESIGN_TOKENS.md` | **由脚本生成，不要手改**；`tests/test_design_tokens_sync.py` 守卫漂移 |
| **全局 QSS**（控件长相） | `src/ui/styles/theme.py` 的 `build_theme()` | 只有 `#objectName` 选择器（R-008） |
| **输入框样式** | `theme.input_qss()` / `theme.combo_qss()` | 唯一工厂（`Q-H18`）；面板只能委托，不得自写 |
| **按钮样式** | `theme.btn_primary_qss()` / `btn_secondary_qss()` / `btn_ghost_qss()` / `fab_qss()` | |
| **菜单/弹层样式** | `theme.menu_qss()` + `src/ui/widgets/menu.py` | 菜单模板集合（`Q-H15`） |
| **动效** | `src/ui/animations.py` | 动效模板（`Q-H16`）：`fade_in` / `fade_popup` / `count_to` + 总开关 |
| **弹窗规范** | `MD-files/CODE_STANDARDS.md` → `Q-H9 ~ Q-H14` | 结构/尺寸/按钮区/输入高度/配色/跟主题 |
| **圆角绘制** | `CODE_STANDARDS` `Q-H17` + `theme.install_rounded_frame_fixer()` | 原生方框会露出方角（`ERRORS #032`） |
| **卡片 / 圆角框**（内容展示类） | `src/ui/styles/cards.py` 的 `card()` | **唯一实现**（自绘抗锯齿）。变体 `panel`/`item`/`sub`/`chip`/`bubble`/`pill`；**不传像素尺寸**（长宽交给 layout）；`pad=`/`bg=`/`hover_bg=` 只接受令牌名 |
| **空态卡片**（无数据页面） | `src/ui/widgets/empty_state.py` → `empty_state()` | 标题 + 说明 + 可选主操作；尺寸/颜色走令牌（`Q-H21`） |
| **现代化审查标准 / 结果** | `MD-files/MODERNIZATION.md` | 动效、空/错/载三态、响应式、可访问性、维护性（M-xxx） |
| **设计原型**（意图参考） | `design/showcase.html`、`design/sidebar-preview.html` | 2026-06 的原型，**只作意图与结构参考**，数值以 `tokens.json` 为准（见 §3） |
| 视觉审查记录 / 决策 | `dev-logs/2026-10-16-UI视觉审查与设置改造.md` | 每个"为什么这么改"都在里面 |

## 2. 使用规则

1. **先查本文件**（`design/INDEX.md`）。表里有 → 按权威位置改，不要另建一套。
2. 表里没有 → **先问用户**：是新增规范，还是已有规范够用？确认后创建，并在本文件补一行。
3. 颜色/字号/圆角**只能**改 `tokens.json`；改完必须跑生成器 + 测试（`Q-H8`）。
4. 硬编码颜色会被 `scripts/check_ui_tokens.py` 拦下（`--strict` 供 CI）；文档字符串/注释里的颜色不算违规。

## 3. 与原型（`showcase.html`）的关系：结构一致，数值有意偏离

原型写于 2026-06，**token 名、圆角刻度、字号刻度都一致**（`radius-sm/md/lg = 4/8/12`、
`s-caption 12 / body-s 13 / body 14 / body-l 16 / subtitle 20 / title 28 / heading 36`），
但**数值不能照抄**，原因两类：

| 类型 | 例子（原型 → 现在） | 为什么 |
|---|---|---|
| 原型过期（代码改了没回写原型） | `bg_surface` `#E8E5DE` → `#EAE7E0`；`border` `0.06` → `0.10` | 原型是单次快照，不是活文档 |
| **对比度不达标**（有意偏离） | `fg_hint` `#9E9B96`（2.41:1）→ `#6A675F`（4.9:1）；`accent` `#B0823A`（白字 3.44:1）→ `#8C5F24`（5.6:1）；`red`/`green`/`orange` 同步压深 | WCAG 2.2 正文 4.5:1（见 `dev-logs/2026-10-16-UI视觉审查与设置改造.md`） |

**结论**：把原型当"意图与结构"的参考，把 `tokens.json` 当"可执行的数值真值"。
想回到原型的某个数值时，先确认它是否满足对比度（`Q-H5`/`Q-H6`）。

## 4. 发行版注意（重要）

`design/tokens.json` 是**运行时**要读的（`theme.py` 启动即加载）。本文件夹其余内容
（`INDEX.md` / `DESIGN_TOKENS.md` / 原型 HTML）是文档。

所以按 `PLAN H-2`：**发行版必须带上 `design/tokens.json`**，其余文档可以不带
（打包时保留 `design/` 目录但只放 tokens.json，或整目录带上都行）。

## 5. 渲染路径：为什么"统一样式"还不够，必须按控件族自绘

Qt 画一个"圆角矩形"有**三条互不相同的路径**，走哪条由 Qt 决定，不由样式表决定：

| 路径 | 谁在画 | 后果 |
|---|---|---|
| **A. QSS `border-radius`** | `QStyleSheetStyle`：先按**整块矩形**填 `background-color`，再沿圆角路径描边 | **不裁剪控件**；圆角**不开抗锯齿** → 非整数缩放（125%/150%）下圆弧被量化成台阶，就是"圆角框周围的角点" |
| **B. 原生控件原语** | 平台样式（`QPushButton` 的 bevel 等） | 一旦控件有 QSS，就被 A 取代 |
| **C. 自绘 `QPainter` + `Antialiasing`** | 我们自己 | 抗锯齿与裁剪完全可控 ✓ |

**为什么不能"全局统一"**：A 的绘制发生在 `QStyleSheetStyle` 内部，**不会委托给 `QProxyStyle`**，
所以"加个全局钩子让 QSS 圆角抗锯齿"这条路不存在；要让一个控件走 C，**必须给它换类**
（`paintEvent` 是"每类一份"）。

**所以结论是**：**样式可以统一（工厂），渲染路径必须逐控件族统一**。当前已自绘的两族：

- 输入类：`src/ui/widgets/rounded_input.py`（`RoundedLineEdit` / `RoundedComboBox`）
- 按钮类：`src/ui/widgets/rounded_button.py`（`RoundedButton`，**自动接管 QSS 里的背景/描边/圆角**，
  所以调用点只改类名，内联样式照旧）

**判据（新控件用哪条路）**：

| 条件 | 选择 |
|---|---|
| 圆角**贴对比背景**（白输入框贴浅灰带、深色按钮贴浅底）且缩放可能非 100% | **自绘**（否则一定有瑕疵） |
| 圆角半径 ≤4px，或底色与父背景接近 | QSS 够用（瑕疵看不出来） |
| 第三方控件 / 不便子类化 | QSS + 接受轻微瑕疵，或用自绘容器包裹 |

**实现细节（踩过的坑）**：自绘按钮若直接 `super().paintEvent()`，会把**原生按钮底面**画在
自绘底色之下透出来（次级按钮看起来像原生按钮）→ 只画标签层 `CE_PushButtonLabel`。
另外"吸收 QSS"不能只做一次：首次 `paint` 可能早于调用方的 `setStyleSheet`，
锁死会导致 QSS 底色与自绘**叠加**。
