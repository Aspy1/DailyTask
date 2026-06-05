"""Plugins listing panel shown inside main workspace.

Lists discovered plugins, allows enable/disable and opening plugin panels.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QScrollArea
)
from PySide6.QtCore import Qt
from src.ui.styles.theme import get_colors
from PySide6.QtWidgets import QMessageBox


class PluginsPanel(QWidget):
    def __init__(self, plugin_manager, settings, ai_service, data_manager, parent=None):
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
        self._list_layout.setContentsMargins(6, 6, 6, 6)
        self._list_layout.setSpacing(8)
        self._scroll.setWidget(container)

        layout.addWidget(self._scroll)

        self.refresh()

    def _c(self):
        return get_colors()

    def refresh(self):
        # clear
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        if not self._pm:
            return

        for pinfo in self._pm.list_plugins():
            c = self._c()
            row = QWidget()
            row.setStyleSheet(f"background-color: {c['card_bg']}; border: 1px solid {c['card_border']}; border-radius:8px; padding:8px;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 6, 8, 6)
            rl.setSpacing(10)
            name = QLabel(pinfo.name)
            name.setStyleSheet(f"font-weight:600; color: {c['fg_primary']}; font-size:14px;")
            name.setMinimumWidth(180)
            name.setWordWrap(True)
            rl.addWidget(name)

            desc = QLabel(pinfo.path.name)
            desc.setStyleSheet(f"color: {c['fg_secondary']};")
            desc.setWordWrap(True)
            rl.addWidget(desc, stretch=1)

            enabled_cb = QCheckBox("启用")
            enabled_cb.setChecked(bool(pinfo.enabled))
            enabled_cb.stateChanged.connect(lambda s, n=pinfo.name: self._toggle(n, s == 2))
            rl.addWidget(enabled_cb)

            panels = self._pm.get_panels(pinfo.name)
            open_btn = QPushButton("打开")
            open_btn.setEnabled(bool(panels) and pinfo.enabled)
            open_btn.setStyleSheet(f"background-color: {c['accent']}; color:#fff; border-radius:6px; padding:6px 10px;")
            open_btn.clicked.connect(lambda _=None, n=pinfo.name: self._open(n))
            rl.addWidget(open_btn)

            self._list_layout.addWidget(row)

        self._list_layout.addStretch()

    def _toggle(self, name: str, enable: bool):
        if not self._pm:
            return
        ok = self._pm.enable(name) if enable else self._pm.disable(name)
        if not ok:
            QMessageBox.warning(self, "插件", "设置失败，检查文件权限。")
        self.refresh()

    def _open(self, name: str):
        if not self._pm:
            return
        panels = self._pm.get_panels(name)
        if not panels:
            QMessageBox.information(self, "插件", "插件没有提供面板。")
            return
        display_name, _ = panels[0]
        widget = self._pm.create_panel(name, display_name, self._settings, self._ai_service, self._data_manager, None)
        if widget is None:
            QMessageBox.warning(self, "插件", "打开失败。")
            return
        widget.setWindowTitle(display_name)
        widget.setAttribute(Qt.WA_DeleteOnClose, True)
        # keep reference
        try:
            self._open_plugin_windows.append(widget)
            widget.destroyed.connect(lambda _, w=widget: self._open_plugin_windows.remove(w) if w in self._open_plugin_windows else None)
        except Exception:
            pass
        widget.show()
