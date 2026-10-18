"""2026-10-18 用户看渲染截图提的 5 条 UI 反馈的回归守卫。

| 反馈 | 守卫 |
|---|---|
| 习惯卡「今日未打卡」徽章三个大小不一致 | 徽章不再跟着卡片高度被拉伸（对齐方式固定） |
| 考试倒计时应是**圆** | 圆角 = 直径的一半（`radius_pill`=999 会被 Qt 画成圆角方块） |
| AI 回复行间距过大 | markdown 不用 `<ul>/<li>`、空行折叠 |
| 标签弹窗行距大、没有区分底色 | 有 `item_bg` 淡底 + 收紧内边距 |
| 侧边栏「AI 助手」要居中 | 按钮文字居中（原来 `text-align: left`） |
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "src" / "ui"


def _src(rel: str) -> str:
    return (UI / rel).read_text(encoding="utf-8")


def test_ai_markdown_avoids_list_blocks() -> None:
    """⚠ 行距回归：Qt 给 `<ul>/<li>` 加的块间距很大，回复看着像被拉开。"""
    from src.ui.components.ai_panel import _md_to_html

    out = _md_to_html("- 甲\n- 乙\n\n\n丙")
    assert "<ul" not in out and "<li>" not in out, "项目符号不该用列表块"
    assert "•" in out, "要用 • 直接拼"
    assert "<br><br>" not in out, "空行要折叠掉（否则行距过大）"


def test_exam_countdown_badge_is_a_circle(qapp) -> None:
    """⚠ 圆角必须是**直径的一半**：用 `radius_pill`（999）Qt 会画成圆角方块。"""
    from src.ui.panels.exam_panel import _ExamCard
    from src.ui.styles.theme import CIRCLE_BADGE, get_colors

    badge = _ExamCard._make_badge(3, get_colors())
    assert badge.width() == badge.height() == CIRCLE_BADGE
    assert f"border-radius: {CIRCLE_BADGE // 2}px" in badge.styleSheet()
    assert "radius_pill" not in badge.styleSheet()


def test_habit_tag_does_not_stretch_with_the_card() -> None:
    """⚠ 三个卡片的徽章要一样大：徽章不能被卡片高度拉伸（对齐方式钉住）。"""
    src = _src("panels/habit_panel.py")
    assert "row1.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)" in src


def test_tags_list_items_have_a_visible_chip_background() -> None:
    """标签项要有**两模式都可见**的淡底，并把内边距收紧。

    ⚠ `bg_elevated` 在浅色下与 `bg_input` 同色 → 用它等于没底色（实测过）。
    """
    src = _src("panels/inventory_dialogs.py")
    assert "c['item_bg']" in src, "标签项底色要走 item_bg"
    assert "padding: 2px 10px" in src, "行距要收紧（全局是 8px 12px）"


def test_sidebar_ai_button_text_is_centered() -> None:
    src = _src("components/sidebar.py")
    assert "text-align: center" in src, "AI 助手按钮文字要居中"
