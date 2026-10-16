"""UI 样式耦合守卫：**禁止用按钮文案判断样式**（脆弱耦合）。

为什么：文案会随措辞改动与 i18n 迁移而变，用文案判断会让高亮**静默失效**
（改文案的人不会知道有段样式逻辑依赖它）。2026-10-16 实测到的两种表现：

- `task_panel` 用 `txt in ("添加", "记一笔", "开始", "保存", "打开")` 判断强调色 ——
  该面板一个按钮都不匹配，整段是**死代码**；
- `expense_panel` 把次级按钮"记一笔"也列进了强调色名单 → 换主题时它被翻成强调色，
  与创建时的样式不一致（设计上它是"存钱行"的次级按钮）。

正确做法：创建时用 `theme.mark_accent_button(btn)` 打属性，刷新时用
`theme.is_accent_button(btn)` 判断；菜单结果用 `add_action(..., callback)` 或
`action.data()`，不要比较 `chosen.text()`。
"""

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "src" / "ui"


def _iter_trees() -> Iterator[tuple[Path, ast.AST]]:
    for f in sorted(UI.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        yield f, ast.parse(f.read_text(encoding="utf-8"))


def _is_tr_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr"


def _is_text_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "text")


def _offenders() -> list[str]:
    """只扫**代码**（AST），不扫注释与 docstring —— 否则规则文档里的示例会误报。"""
    hits = []
    for f, tree in _iter_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            rel = f.relative_to(ROOT).as_posix()
            # 1) 按文案判断高亮：`txt in (...)`
            if isinstance(node.left, ast.Name) and node.left.id == "txt" \
                    and any(isinstance(op, ast.In) for op in node.ops):
                hits.append(f"{rel}:{node.lineno} txt in (...)")
            # 2) 菜单结果按文案比较：`chosen.text() == tr(...)`
            if _is_text_call(node.left) and any(_is_tr_call(c) for c in node.comparators):
                hits.append(f"{rel}:{node.lineno} .text() == tr(...)")
    return hits


def test_no_style_decided_by_button_text() -> None:
    assert _offenders() == []


def test_accent_helpers_exist_and_default_false(qapp) -> None:
    """属性机制本身可用：未标记的按钮不是主按钮。"""
    from PySide6.QtWidgets import QPushButton

    from src.ui.styles.theme import is_accent_button, mark_accent_button

    btn = QPushButton("随便")
    assert is_accent_button(btn) is False
    mark_accent_button(btn)
    assert is_accent_button(btn) is True


def test_expense_add_button_is_accent_and_save_is_not(qapp, tmp_path) -> None:
    """记账面板：只有「添加」是主按钮；「记一笔」保持次级（存钱行方案 1）。

    回归：此前按文案判断高亮，把「记一笔」也列进了强调色名单 →
    换主题时它被翻成强调色，与创建时的次级样式不一致。
    """
    from PySide6.QtWidgets import QPushButton

    from src.i18n.loader import tr
    from src.services.data_manager import DataManager
    from src.ui.panels.expense_panel import ExpensePanel
    from src.ui.styles.theme import get_colors, is_accent_button

    panel = ExpensePanel(DataManager(tmp_path))
    panel.refresh_theme()

    marked = [b for b in panel.findChildren(QPushButton) if is_accent_button(b)]
    assert len(marked) == 1, [b.text() for b in marked]
    assert marked[0].text() == tr("panel.expense.btn_add")

    save = next(b for b in panel.findChildren(QPushButton)
                if b.text() == tr("panel.expense.btn_record_saving"))
    assert is_accent_button(save) is False
    assert get_colors()["accent"] not in save.styleSheet()
