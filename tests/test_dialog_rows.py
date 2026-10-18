"""弹窗**行工厂**的守卫（`Q-H9` 结构 / `Q-H11` 按钮区）。

起因（第四批遗留「U9 其余 · 统一 Dialog/FormRow/Field/ActionRow 工厂」）：原来
**4 套各写各的**「标签 + 控件」行 —— `semester_dialog._field_row`（标签左）、
`inventory_dialogs._labeled_field`（标签**在上**）、`settings_panel._row`（固定 100 居中）、
裸 `QFormLayout`；按钮行也有 2 套（`schedule_actions._dialog_buttons` + 各处自写）。

现在统一到 `dialog_shell.form_row` / `action_row`，并把规范钉成测试。
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton

from src.ui.widgets.dialog_shell import action_row, form_row

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _drop_widgets_created_here(qapp) -> Iterator[None]:
    from PySide6.QtWidgets import QApplication

    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.processEvents()


def test_form_row_puts_label_left_and_stretches_the_field(qapp) -> None:
    field = QLineEdit()
    row = form_row("名称", field)
    row.resize(400, 40)
    row.show()
    qapp.processEvents()

    label = next(w for w in row.findChildren(QLabel) if w.text() == "名称")
    assert label.x() < field.x(), "标签在左"
    assert field.width() > label.width(), "控件占满余下宽度"
    assert label.styleSheet() == "", "标签样式由 dialog_qss 统一决定，不写内联"


def test_action_row_puts_cancel_left_of_primary(qapp) -> None:
    """`Q-H11`：**取消在左、主操作在最右**。"""
    calls: list[str] = []
    row = action_row("保存", lambda: calls.append("primary"),
                     on_cancel=lambda: calls.append("cancel"))
    row.resize(400, 50)
    row.show()
    qapp.processEvents()

    buttons = row.findChildren(QPushButton)
    assert [b.text() for b in buttons] == ["取消", "保存"]
    assert buttons[0].x() < buttons[1].x(), "取消必须在主操作左边"

    buttons[0].click()
    buttons[1].click()
    assert calls == ["cancel", "primary"]


def test_action_row_danger_uses_red_fill(qapp) -> None:
    """`Q-H11`：危险操作（删除 / 清空）用 `red_fill` 填充 + `fg_on_fill` 文字。"""
    from src.ui.styles.theme import get_colors

    c = get_colors()
    row = action_row("删除", lambda: None, danger=True)
    primary = next(b for b in row.findChildren(QPushButton) if b.text() == "删除")
    assert c["red_fill"] in primary.styleSheet()
    assert c["fg_on_fill"] in primary.styleSheet()


def test_no_ad_hoc_row_or_button_row_implementations_left() -> None:
    """`src/` 里不许再出现**自己造行**的 helper —— 统一走 `dialog_shell`。

    判据分两类（都只防**新增**）：

    - **已删除**的 `_field_row` / `_dialog_buttons` 不许回来；
    - 允许保留**薄委托**（`_labeled_field`），但它的函数体里必须真的调用工厂
      —— 防止"名字还在、实现又长回自己那套"。
    """
    removed = ("_field_row", "_dialog_buttons")
    delegators = {"_labeled_field": "form_row"}
    hits: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines):
            stripped = line.strip()
            for name in removed:
                if stripped.startswith(f"def {name}("):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno + 1} 又造了 {name}")
            for name, factory in delegators.items():
                if stripped.startswith(f"def {name}("):
                    body = "\n".join(lines[lineno:lineno + 12])
                    if f"{factory}(" not in body:
                        hits.append(f"{path.relative_to(ROOT)}:{lineno + 1} {name} 没委托给 {factory}")
    assert not hits, "自造的行 helper（应改用 dialog_shell.form_row / action_row）：\n" + "\n".join(hits)
