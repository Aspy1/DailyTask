"""「近期安排」面板接线：卡片数量、三态点击、拖动排序落到模型。

界面本身（拖动）难以在测试里真的"用手拖"，所以拖动的两个端点分开测：
`RoutineBoard.index_at()`（落点 → 序号）+ `reordered` → `RoutineModel.move()`。
"""

from PySide6.QtWidgets import QLabel

from src.models.routine import STATUS_DONE
from src.services.data_manager import DataManager
from src.ui.panels.routine_panel import MIME_ROUTINE, RoutinePanel


def _panel(tmp_path, qapp) -> tuple[DataManager, RoutinePanel]:
    dm = DataManager(tmp_path)
    return dm, RoutinePanel(dm)


def _title_of(card) -> str:
    for label in card.findChildren(QLabel):
        if label.text():
            return label.text()
    return ""


def test_one_card_per_item(tmp_path, qapp) -> None:
    dm, panel = _panel(tmp_path, qapp)
    dm.routines.add("背单词")
    dm.routines.add("跑步")
    panel._refresh()
    assert len(panel._board.cards()) == 2


def test_empty_state_shows_hint(tmp_path, qapp) -> None:
    _dm, panel = _panel(tmp_path, qapp)
    assert panel._board.cards() == []
    assert panel._board.layout().count() == 2      # 提示 + 末尾 stretch


def test_click_cycles_status_and_rebuilds_card(tmp_path, qapp) -> None:
    dm, panel = _panel(tmp_path, qapp)
    rid = dm.routines.add("背单词")
    panel._refresh()
    panel._board.cards()[0]._box.click()

    assert dm.routines.status_on(rid) == STATUS_DONE
    assert _title_of(panel._board.cards()[0]) == "背单词"
    assert panel._board.cards()[0]._box.text() == "✔"


def test_reorder_signal_moves_item_in_model(tmp_path, qapp) -> None:
    dm, panel = _panel(tmp_path, qapp)
    a = dm.routines.add("A")
    b = dm.routines.add("B")
    panel._refresh()
    panel._board.reordered.emit(b, 0)
    assert [i["id"] for i in dm.routines.items] == [b, a]


def test_index_at_maps_drop_position_to_slot(tmp_path, qapp) -> None:
    """落点在第二张卡中线上方 → 插到它前面；下方 → 后面。"""
    dm, panel = _panel(tmp_path, qapp)
    dm.routines.add("A")
    dm.routines.add("B")
    panel._refresh()
    panel.resize(400, 400)
    panel.show()
    cards = panel._board.cards()
    top_center = cards[0].geometry().center().y()
    bottom_center = cards[-1].geometry().center().y()
    assert panel._board.index_at(top_center - 1) == 0
    assert panel._board.index_at(bottom_center + 1) == len(cards)


def test_board_accepts_routine_drag(tmp_path, qapp) -> None:
    _dm, panel = _panel(tmp_path, qapp)
    assert panel._board.acceptDrops() is True
    assert MIME_ROUTINE.startswith("application/")


def test_sidebar_entry_switches_to_routine_panel(tmp_path, qapp) -> None:
    """侧边栏「近期安排」必须切到这一页（不是点了没反应的死入口）。"""
    from src.services.ai_service import AIService
    from src.services.settings_manager import SettingsManager
    from src.ui.main_window import MainWindow

    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    mw = MainWindow(settings, AIService(settings, dm), dm, None)

    mw._workspace.switch_to("routines")

    assert mw._workspace._stack.currentWidget() is mw._workspace._routine_panel
