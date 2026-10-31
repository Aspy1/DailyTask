"""Plugins listing panel shown inside main workspace.

Lists discovered plugins, allows enable/disable and opening plugin panels.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.ui.styles.cards import card
from src.ui.styles.theme import LAYOUT, SIZE_BODY, get_colors
from src.ui.widgets.rounded_button import RoundedButton

logger = logging.getLogger(__name__)


class PluginsPanel(QWidget):
    def __init__(self, plugin_manager, settings, ai_service, data_manager, parent=None) -> None:
        super().__init__(parent)
        self._pm = plugin_manager
        self._settings = settings
        self._ai_service = ai_service
        self._data_manager = data_manager
        self._open_plugin_windows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        container = QWidget()
        self._list_layout = QVBoxLayout(container)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(8)
        self._scroll.setWidget(container)

        layout.addWidget(self._scroll)

        self.refresh()

    def _c(self) -> dict:
        return get_colors()

    def refresh(self) -> None:
        c = get_colors()
        # clear
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        if not self._pm:
            return

        for pinfo in self._pm.list_plugins():
            c = self._c()
            row = card("panel", pad="spacing_sm")
            rl = QHBoxLayout(row)
            rl.setSpacing(10)
            name = QLabel(pinfo.name)
            name.setStyleSheet(f"font-weight:600; color: {c['fg_primary']}; font-size: {SIZE_BODY}px;")
            name.setMinimumWidth(LAYOUT["name_width"])
            name.setWordWrap(True)
            rl.addWidget(name)

            desc = QLabel(pinfo.path.name)
            desc.setStyleSheet(f"color: {c['fg_secondary']};")
            desc.setWordWrap(True)
            rl.addWidget(desc, stretch=1)

            enabled_cb = QCheckBox(tr("panel.plugins.label_enabled"))
            enabled_cb.setChecked(bool(pinfo.enabled))
            # R-008：用 clicked(bool)，`stateChanged` 也会被程序化 setChecked 触发
            enabled_cb.clicked.connect(lambda checked, n=pinfo.name: self._toggle(n, checked))
            rl.addWidget(enabled_cb)

            panels = self._pm.get_panels(pinfo.name)
            open_btn = RoundedButton(tr("panel.plugins.btn_open"))
            open_btn.setEnabled(bool(panels) and pinfo.enabled)
            open_btn.setStyleSheet(f"background-color: {c['accent']}; color:{c['fg_on_fill']}; border-radius: 8px; padding:6px 10px;")
            open_btn.clicked.connect(lambda _=None, n=pinfo.name: self._open(n))
            rl.addWidget(open_btn)

            self._list_layout.addWidget(row)

        self._list_layout.addStretch()

    def _toggle(self, name: str, enable: bool) -> None:
        if not self._pm:
            return
        ok = self._pm.enable(name) if enable else self._pm.disable(name)
        if not ok:
            QMessageBox.warning(self, tr("panel.plugins.title"), tr("panel.plugins.msg_toggle_failed"))
        self.refresh()

    def _open(self, name: str) -> None:
        if not self._pm:
            return
        panels = self._pm.get_panels(name)
        if not panels:
            QMessageBox.information(self, tr("panel.plugins.title"), tr("panel.plugins.msg_no_panel"))
            return
        display_name, _ = panels[0]
        widget = self._pm.create_panel(name, display_name, self._settings, self._ai_service, self._data_manager, None)
        if widget is None:
            QMessageBox.warning(self, tr("panel.plugins.title"), tr("panel.plugins.msg_open_failed"))
            return
        widget.setWindowTitle(display_name)
        widget.setAttribute(Qt.WA_DeleteOnClose, True)
        # keep reference
        try:
            self._open_plugin_windows.append(widget)
            widget.destroyed.connect(lambda _, w=widget: self._open_plugin_windows.remove(w) if w in self._open_plugin_windows else None)
        except Exception:
            logger.debug("PluginsPanel._open 中忽略异常", exc_info=True)
        widget.show()
