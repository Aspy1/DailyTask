"""Exam panel — card-style list with countdown highlights."""

import logging
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.styles.cards import Card
from src.ui.styles.theme import RADIUS, font, get_colors
from src.ui.widgets.dialog_shell import cap_height, make_scrollable
from src.ui.widgets.menu import (
    add_action,
    new_menu,
    show_at,
)
from src.ui.widgets.rounded_button import RoundedButton

logger = logging.getLogger(__name__)


class _ExamCard(Card):
    """Card widget for one exam."""

    def __init__(self, exam: dict, days_left: int, parent=None) -> None:
        c = get_colors()
        # 底色按紧迫度取**令牌名**（不再拼派生色），hover 高亮交给 Card
        bg_key, accent_key = self._make_urgency_keys(days_left)
        accent_color = c[accent_key]
        super().__init__("item", pad="spacing_none", bg=bg_key,
                         hover_bg="accent_bg", parent=parent)
        self._exam = exam

        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 识别钩子（不再是 QSS 选择器）：测试/调试按它找考试卡
        self.setObjectName("examCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Left: countdown badge
        layout.addWidget(self._make_badge(days_left, c))

        # Center: info
        info = QVBoxLayout()
        info.setSpacing(4)

        name_lbl = QLabel(exam.get("course_name", ""))
        name_lbl.setStyleSheet(f"color: {c['fg_primary'] if days_left >= 0 else c['fg_secondary']}; font-size: 15px; font-weight: 600; border: none; background: transparent;")
        info.addWidget(name_lbl)

        date_lbl = QLabel(f"📅 {exam.get('exam_date', '')}")
        date_lbl.setStyleSheet(f"color: {accent_color}; font-size: 13px; border: none; background: transparent;")
        info.addWidget(date_lbl)

        detail = self._make_detail_label(exam, c)
        if detail is not None:
            info.addWidget(detail)

        layout.addLayout(info, stretch=1)
        layout.addStretch()

    @staticmethod
    def _make_urgency_keys(days_left: int) -> tuple[str, str]:
        """按紧迫度返回 (卡片底色**令牌名**, 强调色**令牌名**)。

        ⚠ 返回**令牌名**而不是色值：卡片自绘时现取令牌 → 切主题自动跟随。
        此前这里是 `c["red"] + "12"`（拼派生色），既绕过令牌体系，
        又踩了"QColor 与 QSS 对 8 位 hex 理解不同"的坑。
        """
        if days_left < 0:
            # 已过 ≠ 禁用：fg_disabled 在浅色下只有 1.5:1，正文必须仍可读
            return "bg_surface", "fg_secondary"
        if days_left == 0:
            return "red_tint", "red"
        if days_left <= 7:
            return "red_tint_weak", "red"
        if days_left <= 15:
            # 用 `_weak` 档：0.03 < red_tint_weak 之上不能更浓，否则紧迫度梯度倒挂
            return "orange_tint_weak", "orange"
        return "card_bg", "accent"

    @staticmethod
    def _make_badge(days_left: int, c: dict) -> QLabel:
        """左侧倒计时徽章。"""
        badge = QLabel()
        badge.setFixedSize(52, 52)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if days_left < 0:
            badge.setText(tr("panel.exam.badge_past"))
            badge.setStyleSheet(f"color: {c['fg_hint']}; font-size: 11px; font-weight: 600; background: {c['bg_input']}; border-radius: {RADIUS['radius_pill']}px;")
        elif days_left == 0:
            badge.setText(tr("panel.exam.badge_today"))
            badge.setStyleSheet(f"color: {c['fg_on_fill']}; font-size: 13px; font-weight: 700; background: {c['red_fill']}; border-radius: {RADIUS['radius_pill']}px;")
        elif days_left <= 7:
            badge.setText(tr("panel.exam.badge_days_left", days=days_left))
            badge.setStyleSheet(f"color: {c['fg_on_fill']}; font-size: 13px; font-weight: 700; background: {c['red_fill']}; border-radius: {RADIUS['radius_pill']}px;")
        elif days_left <= 15:
            badge.setText(tr("panel.exam.badge_days_left", days=days_left))
            badge.setStyleSheet(f"color: {c['fg_on_fill']}; font-size: 13px; font-weight: 700; background: {c['orange_fill']}; border-radius: {RADIUS['radius_pill']}px;")
        else:
            badge.setText(tr("panel.exam.badge_days_left", days=days_left))
            badge.setStyleSheet(f"color: {c['fg_secondary']}; font-size: 13px; font-weight: 600; background: {c['bg_input']}; border-radius: 26px;")
        return badge

    @staticmethod
    def _make_detail_label(exam: dict, c: dict) -> QLabel | None:
        """范围 / 地点 / 备注 合并行（均无时返回 None）。"""
        extras = []
        if exam.get("scope"):
            extras.append(tr("panel.exam.detail_scope", scope=exam["scope"]))
        if exam.get("location"):
            extras.append(exam["location"])
        if exam.get("notes"):
            extras.append(exam["notes"])
        if not extras:
            return None
        detail = QLabel(" · ".join(extras))
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color: {c['fg_hint']}; font-size: 12px; border: none; background: transparent;")
        return detail

    def contextMenuEvent(self, ev) -> None:
        # Handled by parent panel
        pass


class ExamPanel(QWidget):
    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        c = get_colors()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(8)

        title = QLabel(tr("panel.exam.title"))
        title.setFont(font("pageTitle"))
        title.setStyleSheet(f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        bl.addWidget(title)
        bl.addStretch()

        add_btn = RoundedButton(tr("panel.exam.btn_add"))
        add_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
                border-radius: 8px; padding: 4px 14px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        add_btn.clicked.connect(lambda: self._add_exam())
        bl.addWidget(add_btn)

        refresh_btn = RoundedButton(tr("panel.exam.btn_refresh"))
        refresh_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border-radius: 8px; padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        refresh_btn.clicked.connect(self._refresh)
        bl.addWidget(refresh_btn)

        layout.addWidget(bar)

        # Scrollable card area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(16, 8, 16, 16)
        self._card_layout.setSpacing(8)
        self._card_layout.addStretch()
        scroll.setWidget(self._card_container)
        layout.addWidget(scroll, stretch=1)

        self._refresh()

    def _refresh(self) -> None:
        # Clear old cards (keep stretch)
        while self._card_layout.count() > 1:
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        exams = sorted(self._dm.exams.exams, key=lambda e: e.get("exam_date", ""))
        today = date.today()

        for e in exams:
            exam_date = e.get("exam_date", "")
            days_left = 999
            try:
                days_left = (date.fromisoformat(exam_date) - today).days
            except (ValueError, TypeError):
                logger.debug("ExamPanel._refresh 中忽略异常", exc_info=True)

            card = _ExamCard(e, days_left)
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            # pos 是**卡片**局部坐标 → 必须拿卡片当锚点（拿面板会偏）
            card.customContextMenuRequested.connect(
                lambda pos, ex=e, c=card: self._context_menu(pos, ex, c))
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _add_exam(self, exam: dict | None = None) -> None:
        dlg = ExamDialog(exam, self)
        if dlg.exec():
            data = dlg.result_data
            if exam:
                self._dm.exams.update_exam(exam["id"], data)
            else:
                self._dm.exams.add_exam(data)
            self._dm.exams.save()
            self._dm.data_changed.emit("exam")
            self._refresh()

    def _context_menu(self, pos, exam: dict, anchor=None) -> None:
        menu = new_menu(self)
        add_action(menu, tr("panel.exam.menu_edit"), lambda checked=False: self._add_exam(exam))
        add_action(menu, tr("panel.exam.menu_delete"), lambda checked=False: self._delete_exam(exam["id"]))
        show_at(menu, anchor or self, pos)

    def _delete_exam(self, eid: str) -> None:
        name = eid
        for e in self._dm.exams.exams:
            if e["id"] == eid:
                name = e.get("course_name", eid)
                break
        if QMessageBox.question(
                self, tr("panel.exam.msg_confirm_delete_title"),
                tr("panel.exam.msg_confirm_delete", name=name)) == QMessageBox.StandardButton.Yes:
            self._dm.exams.delete_exam(eid)
            self._dm.exams.save()
            self._dm.data_changed.emit("exam")
            self._refresh()

    def refresh_theme(self) -> None:
        self._refresh()


class ExamDialog(QDialog):
    def __init__(self, exam: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        c = get_colors()
        editing = exam is not None
        self.setWindowTitle(tr("panel.exam.dialog_title_edit") if editing
                            else tr("panel.exam.dialog_title_add"))
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_card']}; color: {c['fg_primary']}; }}
            QLabel {{ color: {c['fg_primary']}; background: transparent; border: none; }}
            QLineEdit {{
                background-color: {c['bg_input']}; color: {c['fg_primary']};
                border: 1px solid {c['border']}; padding: 6px 10px; font-size: 13px;
                border-radius: 6px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setSpacing(12)
        outer.setContentsMargins(24, 20, 24, 16)
        # 内容可滚动 + 限高（审查 U9）；⚠ 按钮行挂在 `outer` 上，不跟着内容滚
        layout = make_scrollable(outer)
        form = QFormLayout()
        form.setSpacing(10)

        self._course = QLineEdit(exam.get("course_name", "") if exam else "")
        self._course.setPlaceholderText(tr("panel.exam.placeholder_course"))
        form.addRow(tr("panel.exam.label_course"), self._course)

        self._date = QLineEdit(exam.get("exam_date", "") if exam else "")
        self._date.setPlaceholderText("YYYY-MM-DD")
        form.addRow(tr("panel.exam.label_date"), self._date)

        self._scope = QLineEdit(exam.get("scope", "") if exam else "")
        self._scope.setPlaceholderText(tr("panel.exam.placeholder_scope"))
        form.addRow(tr("panel.exam.label_scope"), self._scope)

        self._location = QLineEdit(exam.get("location", "") if exam else "")
        self._location.setPlaceholderText(tr("panel.exam.placeholder_location"))
        form.addRow(tr("panel.exam.label_location"), self._location)

        self._notes = QLineEdit(exam.get("notes", "") if exam else "")
        self._notes.setPlaceholderText(tr("panel.exam.placeholder_notes"))
        form.addRow(tr("panel.exam.label_notes"), self._notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        cap_height(self)

    def _ok(self) -> None:
        if not self._course.text().strip():
            QMessageBox.warning(self, tr("panel.exam.msg_title_error"),
                                tr("panel.exam.msg_need_course"))
            return
        if not self._date.text().strip():
            QMessageBox.warning(self, tr("panel.exam.msg_title_error"),
                                tr("panel.exam.msg_need_date"))
            return
        self.result_data = {
            "course_name": self._course.text().strip(),
            "exam_date": self._date.text().strip(),
            "scope": self._scope.text().strip(),
            "location": self._location.text().strip(),
            "notes": self._notes.text().strip(),
        }
        self.accept()
