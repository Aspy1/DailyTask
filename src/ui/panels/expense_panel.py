"""Expense tracking panel — add, filter, summarize."""

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QLineEdit, QComboBox, QMessageBox,
)
from PySide6.QtGui import QFont

from src.services.data_manager import DataManager
from src.ui.styles.theme import get_colors


class ExpensePanel(QWidget):
    def __init__(self, dm: DataManager, parent=None):
        super().__init__(parent)
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
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(14, 8, 14, 8)
        bar_layout.setSpacing(8)

        title = QLabel("记账")
        title.setFont(QFont(self.font().family(), 13))
        title.setStyleSheet("font-weight: 600; border: none;")
        bar_layout.addWidget(title)
        bar_layout.addStretch()

        for text, slot in [("按分类筛选 ▼", self._show_cat_filter), ("时间筛选 ▼", self._show_time_filter)]:
            btn = QPushButton(text)
            btn.setStyleSheet(self._btn_qss())
            btn.clicked.connect(slot)
            bar_layout.addWidget(btn)
            if "分类" in text:
                self._cat_btn = btn
            else:
                self._time_btn = btn

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet(self._btn_qss())
        refresh_btn.clicked.connect(self._refresh)
        bar_layout.addWidget(refresh_btn)
        layout.addWidget(bar)

        # ── Summary cards ────────────────────────────────────
        cards = QWidget()
        cards.setStyleSheet("background: transparent;")
        cl = QHBoxLayout(cards)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(12)
        self._sum_month = self._summary_card("本月支出")
        self._sum_today = self._summary_card("今日支出")
        self._sum_budget = self._summary_card("预算剩余")
        self._sum_saved = self._summary_card("今省")
        cl.addWidget(self._sum_month)
        cl.addWidget(self._sum_today)
        cl.addWidget(self._sum_budget)
        cl.addWidget(self._sum_saved)
        cl.addStretch()
        layout.addWidget(cards)

        # ── Add row ──────────────────────────────────────────
        add_row = QWidget()
        add_row.setStyleSheet("background: transparent;")
        al = QHBoxLayout(add_row)
        al.setContentsMargins(14, 4, 14, 4)
        al.setSpacing(8)

        self._amount_input = QLineEdit()
        self._amount_input.setPlaceholderText("金额")
        self._amount_input.setFixedWidth(80)
        self._amount_input.setStyleSheet(self._input_qss())
        al.addWidget(self._amount_input)

        self._cat_combo = QComboBox()
        self._cat_combo.setFixedWidth(100)
        self._cat_combo.setStyleSheet(self._combo_qss())
        cats = self._dm.expenses.categories
        for cat in cats:
            self._cat_combo.addItem(cat.get("name", cat["id"]), cat["id"])
        al.addWidget(self._cat_combo)

        self._note_input = QLineEdit()
        self._note_input.setPlaceholderText("备注（可选）")
        self._note_input.setStyleSheet(self._input_qss())
        al.addWidget(self._note_input)

        add_btn = QPushButton("添加")
        add_btn.setFixedWidth(56)
        c = get_colors()
        add_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 6px; padding: 5px 12px; font-weight: 600; font-size: 11px; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        add_btn.clicked.connect(self._add_expense)
        al.addWidget(add_btn)
        layout.addWidget(add_row)

        # ── Savings row ───────────────────────────────────────
        sav_row = QWidget()
        sav_row.setStyleSheet("background: transparent;")
        sl = QHBoxLayout(sav_row)
        sl.setContentsMargins(14, 4, 14, 4)
        sl.setSpacing(8)
        sl.addWidget(QLabel("存钱"))
        self._sav_amount = QLineEdit()
        self._sav_amount.setPlaceholderText("省了多少")
        self._sav_amount.setFixedWidth(100)
        self._sav_amount.setStyleSheet(self._input_qss())
        sl.addWidget(self._sav_amount)
        self._sav_note = QLineEdit()
        self._sav_note.setPlaceholderText("怎么省的（可选）")
        self._sav_note.setStyleSheet(self._input_qss())
        sl.addWidget(self._sav_note)
        sav_btn = QPushButton("记一笔")
        sav_btn.setFixedWidth(56)
        sav_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 6px; padding: 5px 12px; font-weight: 600; font-size: 11px; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        sav_btn.clicked.connect(self._add_saving)
        sl.addWidget(sav_btn)
        sl.addStretch()
        layout.addWidget(sav_row)

        # ── Table ────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setObjectName("taskTable")
        self._table.setHorizontalHeaderLabels(["日期", "分类", "金额", "备注"])
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
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(14, 4, 14, 4)
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
                border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 12px; font-size: 11px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; color: {c['btn_secondary_hover_fg']}; }}
        """

    def _input_qss(self) -> str:
        c = get_colors()
        return f"""
            QLineEdit {{ background-color: {c['input_bg']}; color: {c['fg_primary']};
                border: 1px solid {c['input_border']}; border-radius: 6px; padding: 5px 8px; font-size: 12px; }}
        """

    def _combo_qss(self) -> str:
        c = get_colors()
        return f"""
            QComboBox {{ background-color: {c['input_bg']}; color: {c['fg_primary']};
                border: 1px solid {c['input_border']}; border-radius: 6px; padding: 5px 8px; font-size: 12px; }}
            QComboBox QAbstractItemView {{
                background-color: {c['bg_surface_hi']}; color: {c['fg_primary']};
                selection-background-color: {c['accent_bg']}; outline: none;
            }}
        """

    def _summary_card(self, label: str) -> QWidget:
        c = get_colors()
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        l = QVBoxLayout(w)
        l.setContentsMargins(14, 8, 14, 8)
        title = QLabel(label)
        title.setStyleSheet(f"color: {c['fg_hint']}; font-size: 10px; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(title)
        amount = QLabel("¥0")
        amount.setStyleSheet(f"color: {c['fg_primary']}; font-size: 16px; font-weight: 600; border: none;")
        amount.setAlignment(Qt.AlignmentFlag.AlignCenter)
        amount.setObjectName(f"sum_{label}")
        l.addWidget(amount)
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

        self._find_sum_label("本月支出").setText(f"¥{month_total:.0f}")
        self._find_sum_label("今日支出").setText(f"¥{today_total:.0f}")
        self._find_sum_label("预算剩余").setText(f"¥{remaining:.0f}")
        self._find_sum_label("今省").setText(f"¥{today_saved:.0f}")

        # Footer: filtered total
        cat_info = f" ({self._filter_category})" if self._filter_category else ""
        date_info = ""
        if self._filter_start or self._filter_end:
            date_info = f" {self._filter_start or '...'} ~ {self._filter_end or '...'}"
        self._total_label.setText(f"{len(records)} 条记录{cat_info}{date_info}  合计 ¥{total:.2f}")

    def _add_expense(self) -> None:
        text = self._amount_input.text().strip()
        if not text:
            return
        try:
            amount = float(text)
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效金额。")
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
            QMessageBox.warning(self, "错误", "请输入有效金额。")
            return
        note = self._sav_note.text().strip()
        self._dm.daily_logs.add_saving(amount, note)
        self._dm.daily_logs.save()
        self._sav_amount.clear()
        self._sav_note.clear()
        self._refresh()
        self._dm.data_changed.emit("saving")

    def _show_cat_filter(self) -> None:
        from PySide6.QtWidgets import QMenu
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_surface_hi']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)
        all_action = menu.addAction("全部分类")
        all_action.triggered.connect(lambda: self._apply_cat_filter(""))
        menu.addSeparator()
        for cat in self._dm.expenses.categories:
            action = menu.addAction(cat["name"])
            action.triggered.connect(lambda checked, cid=cat["id"]: self._apply_cat_filter(cid))
        menu.exec(self._cat_btn.mapToGlobal(self._cat_btn.rect().bottomLeft()))

    def _apply_cat_filter(self, cat_id: str) -> None:
        self._filter_category = cat_id
        if cat_id:
            self._cat_btn.setText(f"分类: {cat_id} ▼")
        else:
            self._cat_btn.setText("按分类筛选 ▼")
        self._refresh()

    def _show_time_filter(self) -> None:
        from PySide6.QtWidgets import QMenu, QWidgetAction, QDateEdit
        c = get_colors()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {c['bg_surface_hi']}; color: {c['fg_primary']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {c['accent_bg']}; }}
        """)
        all_action = menu.addAction("全部时间")
        all_action.triggered.connect(lambda: self._apply_time_filter("", ""))
        menu.addSeparator()
        # Basic presets
        for label, start, end in [("今天", "today", "today"), ("本周", "week", "week"), ("本月", "month", "month")]:
            action = menu.addAction(label)
            action.triggered.connect(lambda checked, s=start, e=end: self._apply_time_preset(s, e))
        menu.exec(self._time_btn.mapToGlobal(self._time_btn.rect().bottomLeft()))

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
        self._time_btn.setText("时间: 已筛选 ▼")
        self._refresh()

    def _apply_time_filter(self, start: str, end: str) -> None:
        self._filter_start = start
        self._filter_end = end
        if start or end:
            self._time_btn.setText("时间: 已筛选 ▼")
        else:
            self._time_btn.setText("时间筛选 ▼")
        self._refresh()

    def refresh_theme(self) -> None:
        c = get_colors()
        # Update button styles
        btn_qss = self._btn_qss()
        for btn in self.findChildren(QPushButton):
            try:
                txt = (btn.text() or "").strip()
                if txt in ("添加", "记一笔", "保存") or txt == "+":
                    btn.setStyleSheet(f"QPushButton {{ background-color: {c['accent']}; color: #fff; border: none; border-radius:6px; padding:5px 12px; font-weight:600; }}")
                else:
                    btn.setStyleSheet(btn_qss)
            except Exception:
                pass

        # Update inputs
        try:
            for le in self.findChildren(QLineEdit):
                le.setStyleSheet(self._input_qss())
            for cb in self.findChildren(QComboBox):
                cb.setStyleSheet(self._combo_qss())
        except Exception:
            pass

        # Refresh content to pick up any color changes
        try:
            self._refresh()
        except Exception:
            pass
