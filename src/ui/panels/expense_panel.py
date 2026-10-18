"""Expense tracking panel — add, filter, summarize."""

import logging
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.data_manager import DataManager
from src.ui.styles.theme import (
    RADIUS,
    SIZE_BODY_S,
    SIZE_SUBTITLE,
    combo_qss,
    font,
    get_colors,
    input_qss,
    is_accent_button,
    mark_accent_button,
    size_small_button,
)
from src.ui.widgets.menu import (
    add_action,
    add_separator,
    new_menu,
    show_below,
)
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedComboBox, RoundedLineEdit

logger = logging.getLogger(__name__)


class ExpensePanel(QWidget):
    def __init__(self, dm: DataManager, parent=None) -> None:
        super().__init__(parent)
        c = get_colors()
        self._dm = dm
        self._filter_category: str = ""
        self._filter_start: str = ""
        self._filter_end: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────
        bar = QWidget()
        bar.setObjectName("taskBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)
        bar_layout.setSpacing(8)

        title = QLabel(tr("panel.expense.title"))
        title.setFont(font(SIZE_SUBTITLE))
        title.setStyleSheet("font-weight: 600; border: none;")
        bar_layout.addWidget(title)
        bar_layout.addStretch()

        filter_buttons = [
            (tr("panel.expense.filter_category"), self._show_cat_filter),
            (tr("panel.expense.filter_time"), self._show_time_filter),
        ]
        for text, slot in filter_buttons:
            btn = RoundedButton(text)
            btn.setStyleSheet(self._btn_qss())
            btn.clicked.connect(slot)
            bar_layout.addWidget(btn)
            if "分类" in text:
                self._cat_btn = btn
            else:
                self._time_btn = btn

        refresh_btn = RoundedButton(tr("panel.expense.btn_refresh"))
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bar_layout.addWidget(refresh_btn)
        layout.addWidget(bar)

        # ── Summary cards ────────────────────────────────────
        cards = QWidget()
        cards.setStyleSheet("background: transparent;")
        cl = QHBoxLayout(cards)
        cl.setContentsMargins(16, 12, 16, 8)
        cl.setSpacing(12)
        self._sum_month = self._summary_card("month", tr("panel.expense.sum_month"))
        self._sum_today = self._summary_card("today", tr("panel.expense.sum_today"))
        self._sum_budget = self._summary_card("budget", tr("panel.expense.sum_budget"))
        self._sum_saved = self._summary_card("saved", tr("panel.expense.sum_saved"))
        cl.addWidget(self._sum_month)
        cl.addWidget(self._sum_today)
        cl.addWidget(self._sum_budget)
        cl.addWidget(self._sum_saved)
        cl.addStretch()
        layout.addWidget(cards)

        # ── Add row ──────────────────────────────────────────
        add_row = QWidget()
        self._add_row = add_row
        add_row.setStyleSheet(self._band_qss())
        al = QHBoxLayout(add_row)
        al.setContentsMargins(16, 4, 16, 4)
        al.setSpacing(8)

        self._amount_input = RoundedLineEdit()
        self._amount_input.setPlaceholderText(tr("expense.amount"))
        self._amount_input.setFixedWidth(80)
        self._amount_input.setStyleSheet(self._input_qss())
        al.addWidget(self._amount_input)

        self._cat_combo = RoundedComboBox()
        self._cat_combo.setFixedWidth(100)
        self._cat_combo.setStyleSheet(self._combo_qss())
        cats = self._dm.expenses.categories
        for cat in cats:
            self._cat_combo.addItem(cat.get("name", cat["id"]), cat["id"])
        al.addWidget(self._cat_combo)

        self._note_input = RoundedLineEdit()
        self._note_input.setPlaceholderText(tr("panel.expense.placeholder_note"))
        self._note_input.setStyleSheet(self._input_qss())
        al.addWidget(self._note_input)

        add_btn = RoundedButton(tr("panel.expense.btn_add"))
        size_small_button(add_btn, 56)
        c = get_colors()
        add_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
                border-radius: 8px; padding: 5px 12px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        add_btn.clicked.connect(self._add_expense)
        mark_accent_button(add_btn)          # 主按钮：强调色填充（刷新时按属性判断，不看文案）
        al.addWidget(add_btn)
        layout.addWidget(add_row)

        # ── Savings row ───────────────────────────────────────
        sav_row = QWidget()
        self._sav_row = sav_row
        sav_row.setStyleSheet(self._sub_band_qss())
        sl = QHBoxLayout(sav_row)
        sl.setContentsMargins(16, 4, 16, 4)
        sl.setSpacing(8)
        sav_label = QLabel(tr("panel.expense.label_saving"))
        sav_label.setFixedWidth(80)              # 让「省了多少」与上面「金额」左对齐
        sav_label.setStyleSheet(self._sub_label_qss())
        sl.addWidget(sav_label)
        self._sav_amount = RoundedLineEdit()
        self._sav_amount.setPlaceholderText(tr("panel.expense.placeholder_saving_amount"))
        self._sav_amount.setFixedWidth(80)       # 与上面「金额」输入框同宽
        self._sav_amount.setStyleSheet(self._input_qss())
        sl.addWidget(self._sav_amount)
        self._sav_note = RoundedLineEdit()
        self._sav_note.setPlaceholderText(tr("panel.expense.placeholder_saving_note"))
        self._sav_note.setStyleSheet(self._input_qss())
        sl.addWidget(self._sav_note)
        sav_btn = RoundedButton(tr("panel.expense.btn_record_saving"))
        size_small_button(sav_btn, 70)
        sav_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 5px 12px;
                font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """)
        sav_btn.clicked.connect(self._add_saving)
        sl.addWidget(sav_btn)
        sl.addStretch()
        layout.addWidget(sav_row)

        # ── Table ────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setObjectName("taskTable")
        self._table.setHorizontalHeaderLabels([
            tr("panel.expense.col_date"),
            tr("expense.category"),
            tr("expense.amount"),
            tr("expense.note"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 100)
        self._table.setColumnWidth(1, 80)
        self._table.setColumnWidth(2, 80)
        self._table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionsClickable(False)
        layout.addWidget(self._table, stretch=1)

        # ── Footer ───────────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("taskFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 4, 16, 4)
        self._total_label = QLabel()
        self._total_label.setObjectName("taskCount")
        fl.addWidget(self._total_label)
        layout.addWidget(footer)

        self._refresh()

    # ── helpers ────────────────────────────────────────────

    def _btn_qss(self) -> str:
        c = get_colors()
        return f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border-radius: 8px; padding: 4px 12px; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """

    def _input_qss(self) -> str:
        """委托 theme 的统一样式（Q-H18）。"""
        return input_qss()

    def _combo_qss(self) -> str:
        """委托 theme 的统一样式（Q-H18）。"""
        return combo_qss()

    @staticmethod
    def _sub_band_qss() -> str:
        """次级行（存钱）：透明底 + 顶部细线，视觉上从属于上面的支出行。"""
        c = get_colors()
        return (f"background: transparent;"
                f" border-top: 1px solid {c['divider']};")

    @staticmethod
    def _sub_label_qss() -> str:
        """次级行标签：13px/600 次要色，固定宽度与输入框对齐。"""
        c = get_colors()
        return (f"color: {c['fg_secondary']}; font-size: {SIZE_BODY_S}px;"
                f" font-weight: 600; background: transparent;")

    @staticmethod
    def _band_qss() -> str:
        """输入带（金额行/存钱行）底色。"""
        return (f"background-color: {get_colors()['card_bg']};"
                f" border-radius: {RADIUS['radius_md']}px;")

    @staticmethod
    def _card_qss() -> str:
        """汇总卡片底色。"""
        return (f"background-color: {get_colors()['card_bg']};"
                f" border-radius: {RADIUS['radius_md']}px;")

    def _summary_card(self, key: str, label: str) -> QWidget:
        c = get_colors()
        w = QWidget()
        w.setStyleSheet(self._card_qss())
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 8, 16, 8)
        title = QLabel(label)
        title.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        amount = QLabel("¥0")
        amount.setStyleSheet(f"color: {c['fg_primary']}; font-size: 16px; font-weight: 600; border: none;")
        amount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        amount.setObjectName(f"sum_{key}")
        lay.addWidget(amount)
        return w

    def _find_sum_label(self, key: str) -> QLabel:
        for child in self.findChildren(QLabel):
            if child.objectName() == f"sum_{key}":
                return child
        return QLabel()

    # ── data ───────────────────────────────────────────────

    def _get_filtered(self) -> list[dict]:
        records = self._dm.expenses.records
        if self._filter_category:
            records = [r for r in records if r.get("category") == self._filter_category]
        if self._filter_start:
            records = [r for r in records if r.get("date", "") >= self._filter_start]
        if self._filter_end:
            records = [r for r in records if r.get("date", "") <= self._filter_end]
        records.sort(key=lambda r: r.get("date", ""), reverse=True)
        return records

    def _refresh(self) -> None:
        self._table.setRowCount(0)
        records = self._get_filtered()
        total = 0.0
        for i, r in enumerate(records):
            self._table.insertRow(i)
            date_item = QTableWidgetItem(r.get("date", "")[:10])
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 0, date_item)

            cat_id = r.get("category", "other")
            cat_name = cat_id
            for cat in self._dm.expenses.categories:
                if cat["id"] == cat_id:
                    cat_name = cat["name"]
                    break
            cat_item = QTableWidgetItem(cat_name)
            cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 1, cat_item)

            amt = r.get("amount", 0)
            total += amt
            amt_item = QTableWidgetItem(f"¥{amt:.2f}")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 2, amt_item)

            note_item = QTableWidgetItem(r.get("note", ""))
            note_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setItem(i, 3, note_item)

        # Summary cards
        month_total = self._dm.expenses.month_total()
        today_total = self._dm.expenses.today_total()
        budget = self._dm.expenses.budget.get("monthly", 0)
        remaining = budget - month_total
        today_saved = self._dm.daily_logs.today_savings_total()

        self._find_sum_label("month").setText(f"¥{month_total:.0f}")
        self._find_sum_label("today").setText(f"¥{today_total:.0f}")
        self._find_sum_label("budget").setText(f"¥{remaining:.0f}")
        self._find_sum_label("saved").setText(f"¥{today_saved:.0f}")

        # Footer: filtered total
        cat_info = f" ({self._filter_category})" if self._filter_category else ""
        date_info = ""
        if self._filter_start or self._filter_end:
            date_info = f" {self._filter_start or '...'} ~ {self._filter_end or '...'}"
        self._total_label.setText(tr("panel.expense.footer_summary", n=len(records), cat=cat_info,
                                     date=date_info, total=f"{total:.2f}"))

    def _add_expense(self) -> None:
        text = self._amount_input.text().strip()
        if not text:
            return
        try:
            amount = float(text)
        except ValueError:
            QMessageBox.warning(self, tr("panel.expense.error_title"), tr("panel.expense.msg_invalid_amount"))
            return
        category = self._cat_combo.currentData()
        note = self._note_input.text().strip()
        self._dm.expenses.add({"amount": amount, "category": category, "note": note})
        self._dm.expenses.save()
        self._amount_input.clear()
        self._note_input.clear()
        self._refresh()
        self._dm.data_changed.emit("expense")

    def _add_saving(self) -> None:
        text = self._sav_amount.text().strip()
        if not text:
            return
        try:
            amount = float(text)
        except ValueError:
            QMessageBox.warning(self, tr("panel.expense.error_title"), tr("panel.expense.msg_invalid_amount"))
            return
        note = self._sav_note.text().strip()
        self._dm.daily_logs.add_saving(amount, note)
        self._dm.daily_logs.save()
        self._sav_amount.clear()
        self._sav_note.clear()
        self._refresh()
        self._dm.data_changed.emit("saving")

    def _show_cat_filter(self) -> None:
        menu = new_menu(self)
        add_action(menu, tr("panel.expense.filter_all_categories"),
                   lambda checked=False: self._apply_cat_filter(""))
        add_separator(menu)
        for cat in self._dm.expenses.categories:
            add_action(menu, cat["name"],
                       lambda checked=False, cid=cat["id"]: self._apply_cat_filter(cid))
        show_below(menu, self._cat_btn)

    def _apply_cat_filter(self, cat_id: str) -> None:
        self._filter_category = cat_id
        if cat_id:
            self._cat_btn.setText(tr("panel.expense.filter_category_active", cat=cat_id))
        else:
            self._cat_btn.setText(tr("panel.expense.filter_category"))
        self._refresh()

    def _show_time_filter(self) -> None:
        menu = new_menu(self)
        add_action(menu, tr("panel.expense.filter_all_time"), lambda checked=False: self._apply_time_filter("", ""))
        add_separator(menu)
        presets = [
            (tr("panel.expense.preset_today"), "today", "today"),
            (tr("panel.expense.preset_week"), "week", "week"),
            (tr("panel.expense.preset_month"), "month", "month"),
        ]
        for label, start, end in presets:
            add_action(menu, label,
                       lambda checked=False, s=start, e=end: self._apply_time_preset(s, e))
        show_below(menu, self._time_btn)

    def _apply_time_preset(self, start: str, end: str) -> None:
        today = date.today()
        if start == "today":
            self._filter_start = self._filter_end = today.isoformat()
        elif start == "week":
            weekday = today.weekday()
            self._filter_start = (today - date.resolution * weekday).isoformat()
            self._filter_end = today.isoformat()
        elif start == "month":
            self._filter_start = today.replace(day=1).isoformat()
            self._filter_end = today.isoformat()
        self._time_btn.setText(tr("panel.expense.filter_time_active"))
        self._refresh()

    def _apply_time_filter(self, start: str, end: str) -> None:
        self._filter_start = start
        self._filter_end = end
        if start or end:
            self._time_btn.setText(tr("panel.expense.filter_time_active"))
        else:
            self._time_btn.setText(tr("panel.expense.filter_time"))
        self._refresh()

    def _restyle_chrome(self) -> None:
        """重刷 __init__ 里写死颜色的静态骨架（汇总卡片 + 两条输入带）。"""
        for card in (self._sum_month, self._sum_today, self._sum_budget, self._sum_saved):
            card.setStyleSheet(self._card_qss())
        self._add_row.setStyleSheet(self._band_qss())
        self._sav_row.setStyleSheet(self._sub_band_qss())

    def refresh_theme(self) -> None:
        self._restyle_chrome()
        c = get_colors()
        # Update button styles
        btn_qss = self._btn_qss()
        for btn in self.findChildren(QPushButton):
            try:
                # 主按钮按**属性**判断（不看文案）：文案会随措辞/i18n 变，
                # 用文案判断会让高亮静默失效，或把次级按钮（如"记一笔"）误翻成强调色
                if is_accent_button(btn):
                    btn.setStyleSheet(f"QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none; border-radius: 8px; padding:5px 12px; font-weight:600; }}")
                else:
                    btn.setStyleSheet(btn_qss)
            except Exception:
                logger.debug("ExpensePanel.refresh_theme 中忽略异常", exc_info=True)

        # Update inputs
        try:
            for le in self.findChildren(QLineEdit):
                le.setStyleSheet(self._input_qss())
            for cb in self.findChildren(QComboBox):
                cb.setStyleSheet(self._combo_qss())
        except Exception:
            logger.debug("ExpensePanel.refresh_theme 中忽略异常", exc_info=True)

        # Refresh content to pick up any color changes
        try:
            self._refresh()
        except Exception:
            logger.debug("ExpensePanel.refresh_theme 中忽略异常", exc_info=True)
