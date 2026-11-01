"""「近期安排」面板 —— 可拖动排序的小卡片 + 三态框（用户 2026-10-30 口径）。

和「日常」（习惯）的区别：这里是**有生命周期**的事（"备考六级 → 每天背单词"），
考完就删，所以**不做连续天数** ✗；每张卡只记**当天**的三态：

    空 → ✔ → ✗ → 空     （点一次 / 两次 / 三次）

拖左边的「⋮⋮」手柄可以上下排序，顺序写进模型（`order` 字段）。
"""

import logging

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.models.routine import STATUS_DONE, STATUS_SKIPPED
from src.services.data_manager import DataManager
from src.ui.panels.routine_dialog import ask_routine
from src.ui.styles.cards import Card
from src.ui.styles.theme import (
    RADIUS,
    SIZE_BODY,
    SIZE_BODY_S,
    SIZE_CAPTION,
    font,
    get_colors,
)
from src.ui.widgets.menu import add_action, new_menu, show_at_cursor
from src.ui.widgets.rounded_button import RoundedButton

MIME_ROUTINE = "application/x-routine-id"
BOX_SIZE = 22          # 三态框边长（与卡片首列对齐）
HANDLE_WIDTH = 18      # 拖动手柄宽度
CARD_MIN_HEIGHT = 52
DRAG_START_PX = 6      # 移动超过这个距离才算拖动（否则只是点击）

logger = logging.getLogger(__name__)

_BOX_TEXT = {"": "", STATUS_DONE: "✔", STATUS_SKIPPED: "✗"}


class _DragHandle(QLabel):
    """卡片右侧的「⋮⋮」：按住上下拖 → 让卡片发起拖动。"""

    def __init__(self, card: "RoutineCard") -> None:
        super().__init__("⋮⋮", card)
        self._card = card
        self._press = None
        self.setFixedWidth(HANDLE_WIDTH)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(tr("panel.routine.drag_hint"))
        self.setStyleSheet(
            f"color: {get_colors()['fg_hint']}; font-size: {SIZE_BODY_S}px;"
            " background: transparent; border: none;")

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self._press = ev.position()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:
        if self._press is None:
            return
        moved = (ev.position() - self._press).manhattanLength()
        if moved >= DRAG_START_PX:
            self._press = None
            self._card.start_drag()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        self._press = None
        super().mouseReleaseEvent(ev)


class RoutineCard(Card):
    """一条近期安排：三态框 + 标题（+ 备注）+ 拖动柄。"""

    cycled = Signal(str)
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, item: dict, status: str, parent=None) -> None:
        super().__init__("item", pad="spacing_none",
                         bg="bg_card" if not status else "bg_surface",
                         hover_bg="accent_bg", parent=parent)
        self._rid = item.get("id", "")
        self._status = status
        self.setObjectName("routineCard")
        self.setMinimumHeight(CARD_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 10, 10)
        row.setSpacing(10)

        self._box = RoundedButton(_BOX_TEXT.get(status, ""), self)
        self._box.setFixedSize(BOX_SIZE, BOX_SIZE)
        self._box.setCursor(Qt.CursorShape.PointingHandCursor)
        self._box.setToolTip(tr("panel.routine.box_hint"))
        self._box.setStyleSheet(self._box_qss())
        self._box.clicked.connect(lambda: self.cycled.emit(self._rid))
        row.addWidget(self._box, 0, Qt.AlignmentFlag.AlignVCenter)

        row.addLayout(self._text_column(item), 1)
        row.addWidget(_DragHandle(self), 0, Qt.AlignmentFlag.AlignVCenter)

    def _text_column(self, item: dict) -> QVBoxLayout:
        c = get_colors()
        done = self._status == STATUS_DONE
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(item.get("title", ""))
        title.setWordWrap(True)
        title.setFont(font(SIZE_BODY))
        title.setStyleSheet(
            f"color: {c['fg_hint'] if done else c['fg_primary']}; font-weight: 600;"
            " border: none; background: transparent;")
        col.addWidget(title)

        note_text = item.get("note", "")
        if note_text:
            note = QLabel(note_text)
            note.setWordWrap(True)
            note.setStyleSheet(
                f"color: {c['fg_secondary']}; font-size: {SIZE_BODY_S}px;"
                " border: none; background: transparent;")
            col.addWidget(note)
        return col

    def _box_qss(self) -> str:
        """三态框配色：空 = 描边、✔ = 绿、✗ = 红。"""
        c = get_colors()
        if self._status == STATUS_DONE:
            bg, fg = c["green_tint"], c["green"]
        elif self._status == STATUS_SKIPPED:
            bg, fg = c["red_tint"], c["red"]
        else:
            bg, fg = "transparent", c["fg_hint"]
        border = c["border_strong"] if not self._status else fg
        return (f"QPushButton {{ background-color: {bg}; color: {fg};"
                f" border: 1px solid {border}; border-radius: {RADIUS['radius_sm']}px;"
                f" font-size: {SIZE_CAPTION}px; font-weight: 600; padding: 0; }}"
                f" QPushButton:hover {{ border-color: {c['accent']}; }}")

    def start_drag(self) -> None:
        """发起拖动：mime 里只放 id，落点由面板换算成目标序号。"""
        mime = QMimeData()
        mime.setData(MIME_ROUTINE, self._rid.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec(Qt.DropAction.MoveAction)

    def mouseDoubleClickEvent(self, ev) -> None:
        self.edit_requested.emit(self._rid)

    def contextMenuEvent(self, ev) -> None:
        menu = new_menu(self)
        add_action(menu, tr("panel.routine.menu_edit"),
                   lambda checked=False: self.edit_requested.emit(self._rid))
        add_action(menu, tr("panel.routine.menu_delete"),
                   lambda checked=False: self.delete_requested.emit(self._rid))
        show_at_cursor(menu)


class RoutineBoard(QWidget):
    """卡片竖排容器，同时是拖放的**接收方**。"""

    reordered = Signal(str, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._cards: list[RoutineCard] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 4, 16, 16)
        self._layout.setSpacing(8)
        self._layout.addStretch()

    def cards(self) -> list[RoutineCard]:
        return list(self._cards)

    def add_card(self, card: RoutineCard) -> None:
        self._layout.insertWidget(len(self._cards), card)
        self._cards.append(card)

    def add_empty(self, widget: QWidget) -> None:
        """空态卡片（没有卡片时才加）。"""
        self._layout.insertWidget(0, widget, alignment=Qt.AlignmentFlag.AlignHCenter)

    def add_note(self, text: str) -> None:
        """兼容旧调用的纯文本空态。"""
        note = QLabel(text)
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {get_colors()['fg_hint']}; font-size: {SIZE_BODY_S}px;"
            " padding: 16px 4px; background: transparent;")
        self._layout.insertWidget(0, note)

    def clear(self) -> None:
        self._cards.clear()
        while self._layout.count() > 1:        # 末尾的 stretch 保留
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasFormat(MIME_ROUTINE):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev) -> None:
        if ev.mimeData().hasFormat(MIME_ROUTINE):
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        rid = bytes(ev.mimeData().data(MIME_ROUTINE)).decode("utf-8")
        self.reordered.emit(rid, self.index_at(ev.position().y()))
        ev.acceptProposedAction()

    def index_at(self, y: float) -> int:
        """把落点的 y 换算成插入序号（越过某张卡的中线就算到它后面）。"""
        index = 0
        for card in self._cards:
            if y > card.geometry().center().y():
                index += 1
        return index


class RoutinePanel(QWidget):
    """近期安排页面。"""

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_bar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._board = RoutineBoard()
        self._board.reordered.connect(self._on_reorder)
        scroll.setWidget(self._board)
        layout.addWidget(scroll, 1)

    def _build_bar(self) -> QWidget:
        c = get_colors()
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(10)

        title = QLabel(tr("panel.routine.title"))
        title.setFont(font("pageTitle"))
        title.setStyleSheet("font-weight: 600; border: none;")
        row.addWidget(title)

        self._count = QLabel("")
        self._count.setStyleSheet(
            f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px; border: none;")
        row.addWidget(self._count)
        row.addStretch()

        add_btn = RoundedButton(tr("panel.routine.btn_add"))
        add_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']};"
            f" border: none; border-radius: {RADIUS['radius_md']}px;"
            f" padding: 6px 14px; font-size: {SIZE_BODY_S}px; font-weight: 600; }}"
            f" QPushButton:hover {{ background-color: {c['accent_hover']}; }}")
        add_btn.clicked.connect(self._on_add)
        row.addWidget(add_btn)
        return bar

    # ── 刷新 ────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._board.clear()
        items = self._dm.routines.items
        for item in items:
            card = RoutineCard(item, self._dm.routines.status_on(item.get("id", "")))
            card.cycled.connect(self._on_cycle)
            card.edit_requested.connect(self._on_edit)
            card.delete_requested.connect(self._on_delete)
            card.show()
            self._board.add_card(card)
        if not items:
            from src.ui.widgets.empty_state import empty_state

            self._board.add_empty(empty_state(
                tr("panel.routine.empty_title"), tr("panel.routine.empty"),
                tr("panel.routine.btn_add"), self._on_add, self._board))
        self._update_count()

    def _update_count(self) -> None:
        counts = self._dm.routines.day_counts()
        self._count.setText(tr("panel.routine.count", done=counts["done"],
                               total=counts["total"], skipped=counts["skipped"]))

    def refresh_theme(self) -> None:
        self._refresh()

    # ── 交互 ────────────────────────────────────────────────

    def _save_and_refresh(self) -> None:
        self._dm.routines.save()
        self._dm.data_changed.emit("routine")
        self._refresh()

    def _on_cycle(self, rid: str) -> None:
        self._dm.routines.cycle_status(rid)
        self._save_and_refresh()

    def _on_reorder(self, rid: str, index: int) -> None:
        if self._dm.routines.move(rid, index):
            self._save_and_refresh()

    def _on_add(self) -> None:
        result = ask_routine(self)
        if result is None:
            return
        self._dm.routines.add(*result)
        self._save_and_refresh()

    def _on_edit(self, rid: str) -> None:
        item = next((i for i in self._dm.routines.items
                     if i.get("id") == rid), None)
        if item is None:
            return
        result = ask_routine(self, item)
        if result is None:
            return
        self._dm.routines.update_routine(rid, {"title": result[0], "note": result[1]})
        self._save_and_refresh()

    def _on_delete(self, rid: str) -> None:
        answer = QMessageBox.question(
            self, tr("panel.routine.delete_title"), tr("panel.routine.delete_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._dm.routines.remove(rid):
            self._save_and_refresh()
