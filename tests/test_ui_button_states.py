"""UI 审查 U1 / U4 的回归守卫（`dev-logs/2026-10-18-UI审查整改第一批.md`）。

- **U1**：自绘按钮的伪状态必须从**选择器**里读。原来正则把选择器丢掉，于是每个块都落进
  `normal`、后写的覆盖先写的 —— 主按钮最后显示的是 disabled 灰、次级按钮长期用 pressed 色。
- **U4**：不能拿"拼 8 位十六进制"当加透明度用。Qt 的 QSS 把 8 位十六进制当
  **AARRGGBB**，`#B93B3B18` 会被解释成透明橄榄色，而不是浅红。
"""

from collections.abc import Iterator

import pytest

from src.ui.styles.theme import qcolor, rgba
from src.ui.widgets.rounded_button import _extract, _state_of


@pytest.fixture(autouse=True)
def _drop_widgets_created_here(qapp) -> Iterator[None]:
    """本文件会造不少顶层控件；测完按**安全顺序**清掉。

    ⚠ conftest 明确警告过：**不能**对所有顶层控件统一 `deleteLater()` / `close()`
    （会双重释放）。这里只处理**本测试新造**的：先让测试函数返回（它的局部引用随之释放），
    再 `deleteLater()` + 跑一次事件循环 —— 这正是 conftest 说的安全姿势。

    为什么必须做：不清理的话解释器退出时 Qt 会**乱序**销毁它们 —— 2026-10-18 本地实测
    连跑三次就有一次 SIGSEGV（CI 的 3.12 job 因此偶发"530 passed 但退出码 1"）。
    """
    from PySide6.QtWidgets import QApplication

    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.processEvents()

QSS = ("QPushButton { background: #111111; border: 1px solid #222222; border-radius: 8px; }"
       "QPushButton:hover { background: #333333; }"
       "QPushButton:pressed { background: #444444; }"
       "QPushButton:disabled { background: #555555; }")


def test_pseudo_states_are_parsed_from_the_selector() -> None:
    """⚠ U1 回归：四个状态各归各位，不再互相覆盖。"""
    colors, border, radius = _extract(QSS)

    assert colors["normal"] == qcolor("#111111")
    assert colors["hover"] == qcolor("#333333")
    assert colors["pressed"] == qcolor("#444444")
    assert colors["disabled"] == qcolor("#555555")
    assert border == qcolor("#222222")
    assert radius == 8


def test_state_priority_prefers_disabled_over_hover() -> None:
    """同时带多个伪状态时按优先级取（`:hover:disabled` 是禁用态）。"""
    assert _state_of("QPushButton:hover:disabled") == "disabled"
    assert _state_of("QPushButton:pressed:hover") == "pressed"
    assert _state_of("QPushButton:checked") == "checked"
    assert _state_of("QPushButton") == "normal"


def test_rgba_helper_is_not_hex_alpha_concatenation() -> None:
    """⚠ U4 回归：用 `rgba()`，不要拼 `{color}18`。"""
    out = rgba("#B93B3B", 0.1)
    assert out == "rgba(185, 59, 59, 0.100)"
    assert "#B93B3B18" not in out


def test_rgba_clamps_alpha() -> None:
    assert rgba("#000000", 5) == "rgba(0, 0, 0, 1.000)"
    assert rgba("#000000", -1) == "rgba(0, 0, 0, 0.000)"


def _luminance(color: str) -> float:
    """相对亮度（WCAG）—— 只看 `#RRGGBB`。"""
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    lo, hi = min(a, b), max(a, b)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_code_block_pair_has_enough_contrast(mode) -> None:
    """⚠ U8 回归：`code_bg` 是深色，文字必须配 `code_fg`。

    原来浅色主题的代码块继承正文色（深字 + 深底）→ 实测只有 1.32:1。
    """
    from src.ui.styles.theme import TOKENS

    pair = TOKENS[mode]
    ratio = _contrast(pair["code_fg"], pair["code_bg"])
    assert ratio >= 4.5, f"{mode}: code_fg/code_bg 只有 {ratio:.2f}:1"


def test_markdown_escapes_user_html() -> None:
    """⚠ U3 的一半：用户正文里的 `<b>` 不能被当成标签渲染。"""
    from src.ui.components.ai_panel import _md_to_html

    assert "&lt;b&gt;" in _md_to_html("<b>不是标签</b>")
    assert "<b>粗</b>" in _md_to_html("**粗**")


def test_instance_thresholds_use_or_semantics() -> None:
    """⚠ 用户用例表第 4 条：分件阈值是 **or** —— 任意一件到下限，整条就告急。

    "0.5 的笔芯还有 12 根、0.4 的还有 4 根，任意一种剩 2 根时提醒我补货"。
    """
    from src.models.inventory import InventoryModel

    item = {"id": "i_001", "name": "笔芯", "quantity": 16, "min_quantity": 1,
            "instances": [{"tags": ["0.5"], "quantity": 12, "min_doses": 2},
                          {"tags": ["0.4"], "quantity": 4, "min_doses": 2}]}
    assert InventoryModel.derive_status(item) == "充足", "12 / 4 都在下限之上"

    item["instances"][1]["quantity"] = 2
    assert InventoryModel.derive_status(item) == "不足", "任意一件告急 → 整条告急"

    item["instances"][1]["quantity"] = 0
    assert InventoryModel.derive_status(item) == "需购"


def test_instance_without_quantity_follows_the_item() -> None:
    """没写数量的件跟整条一致（老数据/普通 instances 不受影响）。"""
    from src.models.inventory import InventoryModel

    item = {"id": "i_001", "name": "充电线", "quantity": 2, "min_quantity": 1,
            "instances": [{"tags": ["Type-C"]}, {"tags": ["Lightning"]}]}
    assert InventoryModel.derive_status(item) == "充足"

    item["quantity"] = 0
    assert InventoryModel.derive_status(item) == "需购"


def test_instance_remainder_does_not_leak_from_the_item() -> None:
    """⚠ 单件算状态时不能被整条的 `remaining_doses` 串味。"""
    from src.models.inventory import InventoryModel

    item = {"id": "i_001", "name": "笔芯", "quantity": 1, "remaining_doses": 99,
            "instances": [{"tags": ["0.5"], "quantity": 1, "min_doses": 2}]}
    assert InventoryModel.derive_status(item) == "不足", "按单件自己的 1 算，不是整条的 99"


def test_control_specs_live_in_tokens() -> None:
    """⚠ 审查 §3：控件规格（高度 / 尺寸）要在 **tokens** 里，不是散在代码里。

    原来 `FIELD_H = 34` / `BTN_H_SM = 30` 是硬编码在 `theme.py` 的。
    """
    from src.ui.styles.theme import CONTROLS, FIELD_H

    assert CONTROLS, "tokens 里要有 controls 段"
    assert FIELD_H == CONTROLS["field_height"] == 34
    for key in ("button_height_sm", "button_width_sm", "toggle_width", "toggle_height", "fab"):
        assert key in CONTROLS, f"controls 缺 {key}"


def test_text_roles_group_size_and_weight() -> None:
    """⚠ 审查 §3：文字角色把 size + weight **成组**，调用点不再各挑一套。

    原来每个页面自己写 `font(SIZE_X, 600)`，字号和字重是两处独立的决定 —— 迟早漂。
    现在 `font()` 既收像素也收角色名（这样调用点只改一行、不用改导入）。
    """
    from src.ui.styles.theme import SIZE_BODY, SIZE_SUBTITLE, TEXT_ROLES, font

    assert TEXT_ROLES, "tokens 里要有 text_roles"
    assert font("pageTitle").pixelSize() == SIZE_SUBTITLE
    assert font("body").pixelSize() == SIZE_BODY
    assert font("pageTitle").weight() > font("body").weight(), "标题该更粗"
    assert font("不存在的角色").pixelSize() == SIZE_BODY, "未知角色退回 body"
    assert font(18, 700).pixelSize() == 18, "照样收像素字号"


def test_ui_token_baseline_guards_against_new_debt() -> None:
    """⚠ 审查 §6.2：存量（QSS 的 PX + 代码里的固定尺寸字面量）登记在基线里，**只允许减少**。

    改少了要重写基线（`--write-px-baseline`）；改多了 CI 会拦
    （`SIZE-LIT` 是**始终检查**的，不受 `--check-px` 开关影响）。
    """
    from scripts.check_ui_tokens import (
        _collect_files,
        _load_px_baseline,
        _scan_files,
        load_tokens,
    )

    names, value_to_name = load_tokens()
    _, by_kind, _ = _scan_files(_collect_files(["src"]), names, value_to_name, True)
    baseline = _load_px_baseline()

    assert baseline, "基线文件丢了（scripts/ui_tokens_baseline.json）"
    for key, kind in (("px", "PX"), ("size_lit", "SIZE-LIT")):
        assert by_kind.get(kind, 0) <= baseline.get(key, 0), (
            f"{kind} 涨到 {by_kind.get(kind)}（基线 {baseline.get(key)}）"
            f" —— 新增了硬编码尺寸")


def test_dialog_shell_caps_height_and_scrolls(qapp) -> None:
    """⚠ U9 回归：长弹窗要**限高 + 中间滚动**，否则屏幕不够高时底部按钮够不着。"""
    from PySide6.QtWidgets import QScrollArea

    from src.ui.widgets.dialog_shell import MAX_HEIGHT_RATIO, DialogShell

    dlg = DialogShell(title="测试", min_width=320)
    assert dlg.findChild(QScrollArea) is not None, "内容区必须可滚动"
    assert dlg.buttons is not None, "按钮行固定在外壳上"

    screen = qapp.primaryScreen()
    assert screen is not None
    cap = int(screen.availableGeometry().height() * MAX_HEIGHT_RATIO)
    assert dlg.maximumHeight() <= cap + 1, "必须限高"


def test_flow_grid_reports_height_for_width(qapp) -> None:
    """⚠ U6 回归：流式排布要能**按宽度报高度**，否则塞进 layout 会占固定高度。"""
    from PySide6.QtWidgets import QWidget

    from src.ui.widgets.flow_grid import FlowGrid

    grid = FlowGrid(min_item_width=200)
    assert grid.hasHeightForWidth() is True
    for _ in range(3):
        child = QWidget(grid)
        child.setMinimumHeight(100)
        child.show()

    one_row = grid.heightForWidth(900)        # 3 项排得下
    three_rows = grid.heightForWidth(200)     # 一行只放得下一个
    assert three_rows > one_row, f"{three_rows} 应大于 {one_row}"


def test_flow_grid_natural_width_mode_does_not_stretch(qapp) -> None:
    """标签用**自然宽度**流式：宽窄不一，不该被拉伸成等宽。"""
    from PySide6.QtWidgets import QLabel, QWidget

    from src.ui.widgets.flow_grid import FlowGrid

    grid = FlowGrid(uniform=False)
    grid.resize(200, 100)
    for text in ("短", "很长很长的标签文字"):
        QLabel(text, grid).show()
    grid._layout_children()

    widths = [c.width() for c in grid.children() if isinstance(c, QWidget)]
    assert len(set(widths)) > 1, f"自然宽度模式下不该等宽：{widths}"


def test_course_table_columns_have_a_readable_minimum(qapp) -> None:
    """⚠ U6 回归：周课表的列/行要有**下限**，窄窗口不能把名称/教室挤没。

    原来横纵表头都是 `Stretch`、没有最小节宽 → 7 列可以被无限压缩。
    """
    from src.ui.widgets.course_table import DAY_COL_MIN_WIDTH, ROW_MIN_HEIGHT, CourseTable

    table = CourseTable(period_count=5)
    table.resize(300, 400)          # 故意很窄
    qapp.processEvents()

    widths = [table.columnWidth(c) for c in range(7)]
    assert min(widths) >= DAY_COL_MIN_WIDTH, f"列被挤到 {widths}"
    heights = [table.rowHeight(r) for r in range(5)]
    assert min(heights) >= ROW_MIN_HEIGHT, f"行被挤到 {heights}"


def test_habit_card_grows_instead_of_clipping(qapp) -> None:
    """⚠ U6 回归：习惯卡是**最小**高度（原来固定 135 → 长标题/多标签被硬裁）。"""
    from src.ui.panels.habit_panel import CARD_MIN_HEIGHT, _HabitCard

    card = _HabitCard({"id": "h1", "name": "很长很长很长的习惯名字" * 4,
                       "schedule": {"type": "daily"}}, active=True, done=False)
    assert card.minimumHeight() == CARD_MIN_HEIGHT
    assert card.maximumHeight() > CARD_MIN_HEIGHT, "不能再是固定高度"


def test_flow_grid_divides_available_width(qapp) -> None:
    """⚠ U6 回归：流式网格按可用宽度**均分**（原来每项固定宽 → 右侧留一大片空白）。"""
    from PySide6.QtWidgets import QWidget

    from src.ui.widgets.flow_grid import FlowGrid

    grid = FlowGrid(min_item_width=200)
    grid.resize(900, 400)
    for _ in range(3):
        child = QWidget(grid)
        child.setMinimumHeight(100)
        child.show()
    grid._layout_children()

    kids = [c for c in grid.children() if isinstance(c, QWidget)]
    widths = {c.width() for c in kids}
    assert len(widths) == 1, "同一行应等宽"
    assert widths.pop() > 200, "余宽要摊开，不是每项固定 200"


def test_toggle_switch_is_keyboard_operable(qapp) -> None:
    """⚠ U7 回归：开关不能只有鼠标路径（原来是 `QWidget` + 默认 `NoFocus`）。

    顺带钉住另一条：`setChecked()` 是程序性赋值，**不发** `toggled`
    —— 否则"从数据刷新界面"会反过来触发写回（`R-008` 那类回环）。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    from src.ui.widgets.toggle_switch import ToggleSwitch

    sw = ToggleSwitch()
    assert sw.focusPolicy() == Qt.FocusPolicy.StrongFocus, "Tab 必须能到"
    assert sw.accessibleName(), "至少有个无障碍名字"

    seen: list[bool] = []
    sw.toggled.connect(seen.append)
    sw.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space,
                               Qt.KeyboardModifier.NoModifier))
    assert sw.isChecked() is True
    assert seen == [True], "用户操作要发信号"

    sw.setChecked(False)
    assert seen == [True], "程序性 setChecked 不该发信号"


def test_qt_standard_buttons_are_localized(qapp) -> None:
    """⚠ U9 回归：`QDialogButtonBox` 的 OK/Cancel 必须是中文。

    原来没装 Qt 自带翻译 → 习惯/考试/标签/邮件弹窗底部是英文 OK / Cancel。
    """
    from PySide6.QtWidgets import QApplication, QDialogButtonBox

    from src.ui.styles.theme import _install_qt_translations

    # ⚠ 只装翻译，**不要**再调 `init_theme()`：它会重装 QProxyStyle，
    # 旧 style 在退出时被二次释放 → 进程崩在收尾（3.12 上实测到）
    _install_qt_translations(QApplication.instance())
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                           | QDialogButtonBox.StandardButton.Cancel)
    for btn in (QDialogButtonBox.StandardButton.Ok, QDialogButtonBox.StandardButton.Cancel):
        text = box.button(btn).text()
        assert text not in ("OK", "Cancel"), f"还是英文：{text!r}"
        assert any("\u4e00" <= ch <= "\u9fff" for ch in text), f"不是中文：{text!r}"


def test_font_factory_uses_pixels_not_points() -> None:
    """⚠ U5 回归：令牌是**像素**，字体必须 `setPixelSize`。

    `QFont(family, size)` 的第二个参数是 **point**（本机 20pt ≈ 27 逻辑像素），
    而 QSS 用 px —— 混用会让标题/标签/输入内容比例不一致。
    """
    from src.ui.styles.theme import SIZE_SUBTITLE, font

    f = font(SIZE_SUBTITLE)
    assert f.pixelSize() == SIZE_SUBTITLE
    assert f.pointSize() == -1, "不该同时设 point（两套单位会打架）"


def test_ai_history_is_rebuilt_on_theme_change(qapp) -> None:
    """⚠ U3 回归：历史消息的配色写在 HTML 里，换主题必须重画。

    原实现把颜色烤进 HTML 就丢了原文，`refresh_theme` 只改外壳 QSS →
    浅色下建的消息切到深色后仍是深色字。
    """
    from src.ui.components.ai_panel import AIPanel
    from src.ui.styles import theme

    panel = AIPanel()
    panel.append_message("user", "你好")
    assert "你好" in panel._chat_label.text()

    theme.switch_theme("dark")
    panel.refresh_theme()
    # 断言用的是**当前**主题的色 —— 修之前这里还是浅色那份（原文被丢了）
    assert theme.get_colors()["accent"] in panel._chat_label.text()
    theme.switch_theme("light")
    panel.refresh_theme()
    assert theme.get_colors()["accent"] in panel._chat_label.text()


def test_ai_placeholder_is_replaced_by_the_real_reply(qapp) -> None:
    """占位消息在真回复到达时被替换（原来是拿 `<!--ph-->` 做字符串手术）。"""
    from src.ui.components.ai_panel import AIPanel

    panel = AIPanel()
    panel.append_message("ai", "正在思考", is_placeholder=True)
    assert "正在思考" in panel._chat_label.text()

    panel.append_message("ai", "答案")
    text = panel._chat_label.text()
    assert "答案" in text and "正在思考" not in text
