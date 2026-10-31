"""考研备考面板（11408）：倒计时 / 今日待复习 / 本周各科 / 最近模考。

所有数字来自 `models/study.py` 的确定性计算（和财务 A4 同一条原则：
**代码算，AI 只解释**）。面板上的按钮只负责写数据与刷新，不做统计。
"""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.panels.study_dialogs import (
    MistakeDialog,
    MockDialog,
    StudySessionDialog,
    StudyTargetDialog,
)
from src.ui.styles.cards import Card, card
from src.ui.styles.theme import (
    LAYOUT,
    RADIUS,
    SIZE_BODY,
    SIZE_BODY_S,
    SIZE_CAPTION,
    SIZE_SUBTITLE,
    btn_primary_qss,
    btn_secondary_qss,
    font,
    get_colors,
    mark_accent_button,
    size_small_button,
)
from src.ui.widgets.rounded_button import RoundedButton


def _clear(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class StudyPanel(QWidget):
    """备考页面：一屏内先看"还剩多久 / 今天做什么 / 各科够不够"。"""

    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        self._dm = dm
        self._stat_labels: dict[str, QLabel] = {}
        self._buttons: list[tuple[RoundedButton, bool]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_toolbar())
        outer.addWidget(self._build_stats())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 8, 16, 16)
        self._content_layout.setSpacing(12)
        self._due_layout = self._section(tr("study.section_due"))
        self._week_layout = self._section(tr("study.section_week"))
        self._mock_layout = self._section(tr("study.section_mock"))
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        outer.addWidget(scroll, stretch=1)

        self._style()
        self._refresh()

    # ── 构建 ────────────────────────────────────────────────

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(8)

        self._title = QLabel(tr("study.title"))
        self._title.setFont(font("pageTitle"))
        row.addWidget(self._title)
        self._countdown = QLabel()
        self._countdown.setStyleSheet(f"font-size: {SIZE_BODY_S}px; border: none;")
        row.addWidget(self._countdown)
        row.addStretch()

        for text, key, slot, primary in (
            (tr("study.btn_log"), "log", self._log_study, True),
            (tr("study.btn_mistake"), "mistake", self._add_mistake, False),
            (tr("study.btn_mock"), "mock", self._add_mock, False),
            (tr("study.btn_target"), "target", self._set_target, False),
        ):
            btn = RoundedButton(text)
            btn.setObjectName(f"studyBtn_{key}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            size_small_button(btn)
            if primary:
                mark_accent_button(btn)
            btn.setStyleSheet(btn_primary_qss() if primary else btn_secondary_qss())
            self._buttons.append((btn, primary))
            btn.clicked.connect(slot)
            row.addWidget(btn)
        return bar

    def _build_stats(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(16, 12, 16, 8)
        row.setSpacing(12)
        for key, label in (("today", tr("study.sum_today")),
                           ("week", tr("study.sum_week")),
                           ("due", tr("study.sum_due")),
                           ("mock", tr("study.sum_mock"))):
            row.addWidget(self._stat_card(key, label))
        row.addStretch()
        return wrapper

    def _stat_card(self, key: str, label: str) -> QWidget:
        box = card("item", pad="spacing_sm", bg="bg_card")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(2)
        title = QLabel(label)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName(f"study_stat_title_{key}")
        layout.addWidget(title)
        value = QLabel("—")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value.setObjectName(f"study_stat_{key}")
        layout.addWidget(value)
        self._stat_labels[key] = value
        return box

    def _section(self, title: str) -> QVBoxLayout:
        heading = QLabel(title)
        heading.setFont(font(SIZE_BODY))
        heading.setStyleSheet("font-weight: 600; border: none;")
        self._content_layout.addWidget(heading)
        body = QVBoxLayout()
        body.setSpacing(6)
        self._content_layout.addLayout(body)
        return body

    # ── 刷新 ────────────────────────────────────────────────

    def _refresh(self) -> None:
        summary = self._dm.study.summary()
        self._render_countdown(summary)
        self._stat_labels["today"].setText(
            tr("study.unit_minutes", n=summary["today_minutes"]))
        self._stat_labels["week"].setText(
            tr("study.unit_minutes", n=summary["week_minutes"]))
        self._stat_labels["due"].setText(
            tr("study.unit_count", n=summary["due_count"]))
        mock = summary["latest_mock"]
        self._stat_labels["mock"].setText(
            tr("study.score_pair", score=int(mock.get("score") or 0),
               full=int(mock.get("full_score") or 150))
            if mock else tr("study.unit_none"))
        self._render_due(summary["due_reviews"])
        self._render_week(summary["week_by_subject"])
        self._render_mocks()

    def _render_countdown(self, summary: dict) -> None:
        days = summary.get("days_left")
        if days is None:
            self._countdown.setText(tr("study.countdown_none"))
            return
        self._countdown.setText(
            tr("study.countdown", date=summary["target_date"], days=days))
        self._style_countdown(days)

    def _style_countdown(self, days: int) -> None:
        c = get_colors()
        color = c["red"] if days <= 30 else c["orange"] if days <= 90 else c["fg_secondary"]
        self._countdown.setStyleSheet(
            f"color: {color}; font-size: {SIZE_BODY_S}px; font-weight: 600; border: none;")

    def _render_due(self, due: list[dict]) -> None:
        _clear(self._due_layout)
        if not due:
            empty = QLabel(tr("study.due_empty"))
            empty.setStyleSheet(f"color: {get_colors()['fg_hint']}; font-size: {SIZE_BODY_S}px;")
            self._due_layout.addWidget(empty)
            return
        for mistake in due[:10]:
            self._due_layout.addWidget(self._due_card(mistake))

    def _due_card(self, mistake: dict) -> QWidget:
        c = get_colors()
        box = Card("item", pad="spacing_sm", bg="orange_tint_weak")
        row = QHBoxLayout(box)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)
        subject = self._dm.study.subject_name(str(mistake.get("subject") or ""))
        text = QLabel(tr("study.due_line", subject=subject,
                         topic=str(mistake.get("topic") or ""),
                         date=str(mistake.get("next_review") or "")))
        text.setWordWrap(True)
        text.setStyleSheet(f"color: {c['fg_primary']}; font-size: {SIZE_BODY_S}px;")
        row.addWidget(text, stretch=1)
        review = RoundedButton(tr("study.btn_review"))
        size_small_button(review)
        review.clicked.connect(lambda _=False, mid=mistake["id"]: self._review(mid))
        row.addWidget(review)
        master = RoundedButton(tr("study.btn_master"))
        size_small_button(master)
        master.clicked.connect(lambda _=False, mid=mistake["id"]: self._master(mid))
        row.addWidget(master)
        return box

    def _render_week(self, week_by_subject: dict[str, int]) -> None:
        _clear(self._week_layout)
        for subject in self._dm.study.subjects:
            sid = str(subject["id"])
            minutes = int(week_by_subject.get(sid, 0))
            target = int(subject.get("target_minutes") or 0) * 7
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(8)
            name = QLabel(str(subject.get("name") or sid))
            name.setFixedWidth(LAYOUT["name_width"])
            name.setStyleSheet(f"color: {get_colors()['fg_primary']}; font-size: {SIZE_BODY_S}px;")
            layout.addWidget(name)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            bar.setValue(min(100, int(minutes * 100 / target)) if target else 0)
            bar.setFixedHeight(LAYOUT["progress_height"])
            bar.setStyleSheet(self._progress_qss())
            layout.addWidget(bar, stretch=1)
            value = QLabel(tr("study.week_line", minutes=minutes, target=target))
            value.setStyleSheet(f"color: {get_colors()['fg_secondary']};"
                                f" font-size: {SIZE_CAPTION}px;")
            layout.addWidget(value)
            self._week_layout.addWidget(row)

    def _render_mocks(self) -> None:
        _clear(self._mock_layout)
        mocks = self._dm.study.mock_history(limit=5)
        if not mocks:
            empty = QLabel(tr("study.mock_empty"))
            empty.setStyleSheet(f"color: {get_colors()['fg_hint']}; font-size: {SIZE_BODY_S}px;")
            self._mock_layout.addWidget(empty)
            return
        for mock in mocks:
            subject = self._dm.study.subject_name(str(mock.get("subject") or ""))
            label = QLabel(tr(
                "study.mock_line", date=mock.get("date", ""), subject=subject,
                score=int(mock.get("score") or 0), full=int(mock.get("full_score") or 150),
                duration=int(mock.get("duration_minutes") or 0)))
            label.setStyleSheet(
                f"color: {get_colors()['fg_secondary']}; font-size: {SIZE_BODY_S}px;")
            self._mock_layout.addWidget(label)

    @staticmethod
    def _progress_qss() -> str:
        c = get_colors()
        return (f"QProgressBar {{ background-color: {c['item_bg']}; border: none;"
                f" border-radius: {RADIUS['radius_sm']}px; }}"
                f" QProgressBar::chunk {{ background-color: {c['accent']};"
                f" border-radius: {RADIUS['radius_sm']}px; }}")

    def _style(self) -> None:
        c = get_colors()
        self._title.setStyleSheet(
            f"color: {c['fg_primary']}; font-weight: 600; border: none;")
        self._countdown.setStyleSheet(
            f"color: {c['fg_secondary']}; font-size: {SIZE_BODY_S}px; border: none;")
        for label in self._stat_labels.values():
            label.setStyleSheet(
                f"color: {c['fg_primary']}; font-size: {SIZE_SUBTITLE}px;"
                f" font-weight: 600; border: none;")
        self._style_stat_titles(c)
        for btn, primary in self._buttons:
            btn.setStyleSheet(btn_primary_qss() if primary else btn_secondary_qss())

    def _style_stat_titles(self, c: dict) -> None:
        for child in self.findChildren(QLabel):
            if str(child.objectName()).startswith("study_stat_title_"):
                child.setStyleSheet(
                    f"color: {c['fg_hint']}; font-size: {SIZE_BODY_S}px; border: none;")

    # ── 动作 ────────────────────────────────────────────────

    def _save(self) -> None:
        if not self._dm.study.save():
            QMessageBox.warning(self, tr("study.dialog.error_title"),
                                tr("study.msg_save_conflict"))
        self._dm.data_changed.emit("study")
        self._refresh()

    def _log_study(self) -> None:
        dialog = StudySessionDialog(self._dm, self)
        if dialog.exec() and dialog.result_data:
            data = dialog.result_data
            self._dm.study.add_session(data["subject"], data["minutes"],
                                       data["note"], data["date"])
            self._save()

    def _add_mistake(self) -> None:
        dialog = MistakeDialog(self._dm, self)
        if dialog.exec() and dialog.result_data:
            data = dialog.result_data
            self._dm.study.add_mistake(data["subject"], data["topic"],
                                       data["question"], data["answer"],
                                       data["note"], data["date"])
            self._save()

    def _add_mock(self) -> None:
        dialog = MockDialog(self._dm, self)
        if dialog.exec() and dialog.result_data:
            data = dialog.result_data
            self._dm.study.add_mock(data["subject"], data["score"], data["full_score"],
                                    data["duration_minutes"], data["note"], data["date"])
            self._save()

    def _set_target(self) -> None:
        dialog = StudyTargetDialog(self._dm, self)
        if dialog.exec() and dialog.result_data:
            data = dialog.result_data
            self._dm.study.set_target(data["date"])
            self._dm.study.set_daily_goal(data["daily_goal"])
            self._save()

    def _review(self, mid: str) -> None:
        if self._dm.study.review_mistake(mid, date.today()) is not None:
            self._save()

    def _master(self, mid: str) -> None:
        if self._dm.study.master_mistake(mid):
            self._save()

    def refresh_theme(self) -> None:
        self._style()
        self._refresh()
