"""Settings panel — theme-aware card grouping."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QPushButton, QLabel, QCheckBox,
    QScrollArea, QMessageBox, QFrame,
)
from PySide6.QtGui import QFont

from src.i18n.loader import tr
from src.services.settings_manager import SettingsManager
from src.services.ai_service import AIService
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_SUBTITLE, SIZE_TITLE

PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek", "endpoint": "https://api.deepseek.com",
        "model": "deepseek-chat", "key_placeholder": "sk-...",
        "key_url": "https://platform.deepseek.com",
    },
    "claude": {
        "name": "Claude (Anthropic)", "endpoint": "https://api.anthropic.com",
        "model": "claude-sonnet-4-20250514", "key_placeholder": "sk-ant-...",
        "key_url": "https://console.anthropic.com",
    },
}


class SettingsPanel(QWidget):
    def __init__(self, settings: SettingsManager, ai_service: AIService, plugin_manager=None, data_manager=None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._ai_service = ai_service
        self._plugin_manager = plugin_manager
        self._data_manager = data_manager
        # Keep references to opened plugin windows to avoid GC closing them
        self._open_plugin_windows = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(28)
        layout.addWidget(self._section_heading("AI 设置"))
        layout.addWidget(self._build_ai_card())
        layout.addWidget(self._section_heading("通用设置"))
        layout.addWidget(self._build_general_card())
        layout.addWidget(self._section_heading("邮件提醒"))
        layout.addWidget(self._build_email_card())
        layout.addWidget(self._section_heading("余额提醒"))
        layout.addWidget(self._build_balance_card())
        # 插件管理
        if self._plugin_manager is not None:
            layout.addWidget(self._section_heading("插件"))
            layout.addWidget(self._build_plugins_card())
        layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── helpers ────────────────────────────────────────────

    def _c(self) -> dict:
        return get_colors()

    def _section_heading(self, title: str) -> QLabel:
        c = get_colors()
        c = self._c()
        lbl = QLabel(title)
        lbl.setFont(QFont(FONT_CN, SIZE_SUBTITLE))
        lbl.setStyleSheet(f"color: {c['section_heading']}; font-weight: 600; padding: 0 2px;")
        return lbl

    def _card(self) -> QFrame:
        c = get_colors()
        c = self._c()
        card = QWidget()
        card.setStyleSheet(
            f"QWidget {{ background-color: {c['card_bg']}; border-radius: 12px; }}"
        )
        return card

    def _row(self, label: str, widget: QWidget, hint: QWidget | None = None) -> QWidget:
        c = get_colors()
        c = self._c()
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(16, 12, 16, 12)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {c['fg_primary']}; font-size: 13px; font-weight: 600; background: transparent;")
        lbl.setFixedWidth(100)
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(lbl)
        wc = QWidget()
        wc.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wc)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(widget)
        if hint:
            wl.addWidget(hint)
        rl.addWidget(wc, stretch=1)
        return row

    def _divider(self) -> QFrame:
        c = get_colors()
        c = self._c()
        d = QFrame()
        d.setFrameShape(QFrame.Shape.HLine)
        d.setStyleSheet(f"border: none; background-color: {c['divider']}; max-height: 1px; margin: 0 18px;")
        return d

    def _input_qss(self) -> str:
        c = get_colors()
        c = self._c()
        return f"""
            QLineEdit {{ background-color: {c['input_bg']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 7px 10px; font-size: 13px; }}
            QLineEdit:focus {{ border-color: {c['accent']}; }}
        """

    def _combo_qss(self) -> str:
        c = get_colors()
        c = self._c()
        return f"""
            QComboBox {{ background-color: {c['input_bg']}; color: {c['fg_primary']};
                border-radius: 8px; padding: 7px 10px; font-size: 13px; }}
            QComboBox:hover {{ border-color: {c['border_strong']}; }}
            QComboBox:focus {{ border-color: {c['accent']}; }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                background-color: {c['bg_elevated']}; color: {c['fg_primary']};
                border-radius: 8px;
                selection-background-color: {c['accent_bg']}; outline: none;
            }}
        """

    # ── AI card ────────────────────────────────────────────

    def _build_ai_card(self) -> QFrame:
        c = get_colors()
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        current = self._settings.get("AI", "provider", "deepseek")
        self._provider_combo = QComboBox()
        self._provider_combo.setStyleSheet(self._combo_qss())
        for key, info in PROVIDERS.items():
            self._provider_combo.addItem(info["name"], key)
        idx = list(PROVIDERS.keys()).index(current) if current in PROVIDERS else 0
        self._provider_combo.setCurrentIndex(idx)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        layout.addWidget(self._row("提供商", self._provider_combo))
        layout.addWidget(self._divider())

        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setStyleSheet(self._input_qss())
        self._api_key_input.setText(self._settings.api_key)
        layout.addWidget(self._row("API Key", self._api_key_input))
        layout.addWidget(self._divider())

        self._model_combo = QComboBox()
        self._model_combo.setStyleSheet(self._combo_qss())
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumWidth(200)
        layout.addWidget(self._row("模型", self._model_combo))
        layout.addWidget(self._divider())

        self._endpoint_input = QLineEdit()
        self._endpoint_input.setStyleSheet(self._input_qss())
        layout.addWidget(self._row("端点", self._endpoint_input))
        layout.addWidget(self._divider())

        status_row = QWidget()
        status_row.setStyleSheet("background: transparent;")
        sr = QHBoxLayout(status_row)
        sr.setContentsMargins(16, 12, 16, 12)
        self._status_label = QLabel()
        sr.addWidget(self._status_label)
        sr.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setFixedSize(72, 30)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 8px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:pressed {{ background-color: {c['accent_dim']}; }}
        """)
        save_btn.clicked.connect(self._save_ai_settings)
        sr.addWidget(save_btn)
        layout.addWidget(status_row)

        self._on_provider_changed()
        self._update_status()
        return card

    # ── General card ───────────────────────────────────────

    def _build_general_card(self) -> QFrame:
        c = get_colors()
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        self._auto_start = QCheckBox()
        self._auto_start.setChecked(self._settings.get_bool("General", "auto_start"))
        layout.addWidget(self._row(tr("settings.auto_start"), self._auto_start))
        layout.addWidget(self._divider())

        self._minimize_tray = QCheckBox()
        self._minimize_tray.setChecked(self._settings.get_bool("General", "minimize_to_tray"))
        layout.addWidget(self._row(tr("settings.minimize_to_tray"), self._minimize_tray))
        layout.addWidget(self._divider())

        self._reminder = QCheckBox()
        self._reminder.setChecked(self._settings.get_bool("General", "reminder_enabled"))
        layout.addWidget(self._row(tr("settings.reminder_enabled"), self._reminder))
        layout.addWidget(self._divider())

        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(16, 12, 16, 12)
        br.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setFixedSize(72, 30)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_primary']}; border: none;
                border-radius: 8px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        save_btn.clicked.connect(self._save_general_settings)
        br.addWidget(save_btn)
        layout.addWidget(btn_row)
        return card

    # ── Provider logic ─────────────────────────────────────

    def _on_provider_changed(self) -> None:
        key = self._provider_combo.currentData()
        info = PROVIDERS.get(key, PROVIDERS["deepseek"])
        self._endpoint_input.setText(info["endpoint"])
        self._api_key_input.setPlaceholderText(info["key_placeholder"])
        self._model_combo.clear()
        if key == "deepseek":
            self._model_combo.addItems(["deepseek-chat", "deepseek-reasoner"])
        else:
            self._model_combo.addItems([
                "claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001",
            ])
        cur = self._settings.get("AI", "model", info["model"])
        i = self._model_combo.findText(cur)
        if i >= 0:
            self._model_combo.setCurrentIndex(i)

    def _update_status(self) -> None:
        if self._ai_service.is_configured:
            self._status_label.setText("● " + tr("settings.status.configured"))
            self._status_label.setStyleSheet("color: #4ec9b0; font-size: 13px; background: transparent;")
        else:
            self._status_label.setText("● " + tr("settings.status.not_configured"))
            self._status_label.setStyleSheet("color: #f48771; font-size: 13px; background: transparent;")

    def _save_ai_settings(self) -> None:
        self._settings.api_key = self._api_key_input.text().strip()
        self._settings.set("AI", "provider", self._provider_combo.currentData())
        self._settings.set("AI", "model", self._model_combo.currentText())
        self._settings.set("AI", "api_endpoint", self._endpoint_input.text().strip())
        self._settings.save()
        self._update_status()
        QMessageBox.information(self, "设置", "AI 设置已保存。")

    def _build_email_card(self) -> QFrame:
        c = get_colors()
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        self._smtp_host = QLineEdit(self._settings.get("Email", "smtp_host", fallback="smtp.qq.com"))
        self._smtp_host.setStyleSheet(self._input_qss())
        layout.addWidget(self._row("SMTP 服务器", self._smtp_host))
        layout.addWidget(self._divider())

        self._smtp_port = QLineEdit(self._settings.get("Email", "smtp_port", fallback="587"))
        self._smtp_port.setStyleSheet(self._input_qss())
        layout.addWidget(self._row("端口", self._smtp_port))
        layout.addWidget(self._divider())

        self._smtp_user = QLineEdit(self._settings.get("Email", "smtp_user", fallback=""))
        self._smtp_user.setStyleSheet(self._input_qss())
        self._smtp_user.setPlaceholderText("如 123456789@qq.com")
        layout.addWidget(self._row("邮箱地址", self._smtp_user))
        layout.addWidget(self._divider())

        self._smtp_pass = QLineEdit(self._settings.get("Email", "smtp_pass", fallback=""))
        self._smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._smtp_pass.setStyleSheet(self._input_qss())
        self._smtp_pass.setPlaceholderText("QQ邮箱请填授权码，非QQ密码")
        layout.addWidget(self._row("授权码", self._smtp_pass))

        help_lbl = QLabel("QQ邮箱: 设置 → 账户 → POP3/SMTP服务 → 开启 → 生成授权码")
        help_lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; padding: 0 18px;")
        layout.addWidget(help_lbl)

        layout.addWidget(self._divider())
        test_row = QWidget()
        test_row.setStyleSheet("background: transparent;")
        trl = QHBoxLayout(test_row)
        trl.setContentsMargins(16, 8, 16, 8)
        test_btn = QPushButton("发送测试邮件")
        test_btn.setFixedWidth(120)
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: #fff; border: none;
                border-radius: 8px; padding: 6px 12px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
        """)
        test_btn.clicked.connect(self._send_test_email)
        trl.addWidget(test_btn)
        trl.addStretch()
        layout.addWidget(test_row)

        layout.addWidget(self._divider())
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(16, 12, 16, 12)
        br.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setFixedSize(72, 30)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_primary']}; border: none;
                border-radius: 8px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        save_btn.clicked.connect(self._save_email_settings)
        br.addWidget(save_btn)
        layout.addWidget(btn_row)
        return card

    def _send_test_email(self) -> None:
        import smtplib
        from email.mime.text import MIMEText

        host = self._smtp_host.text().strip() or "smtp.qq.com"
        try:
            port = int(self._smtp_port.text().strip())
        except ValueError:
            port = 587
        user = self._smtp_user.text().strip()
        pwd = self._smtp_pass.text().strip()

        if not user or not pwd:
            QMessageBox.warning(self, "错误", "请先填写邮箱地址和授权码。")
            return

        try:
            msg = MIMEText("日程规划邮件配置测试成功！", "plain", "utf-8")
            msg["Subject"] = "日程规划 - 测试邮件"
            msg["From"] = user
            msg["To"] = user
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
            QMessageBox.information(self, "成功", f"测试邮件已发送至 {user}\n请检查收件箱。")
        except Exception as e:
            QMessageBox.warning(self, "失败", f"发送失败: {e}")

    def _save_email_settings(self) -> None:
        self._settings.set("Email", "smtp_host", self._smtp_host.text().strip())
        self._settings.set("Email", "smtp_port", self._smtp_port.text().strip())
        self._settings.set("Email", "smtp_user", self._smtp_user.text().strip())
        self._settings.set("Email", "smtp_pass", self._smtp_pass.text().strip())
        self._settings.save()
        QMessageBox.information(self, "设置", "邮件设置已保存。")

    # ── 插件卡片 ────────────────────────────────────────────
    def _build_plugins_card(self) -> QFrame:
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._plugins_container = QWidget()
        pcl = QVBoxLayout(self._plugins_container)
        pcl.setContentsMargins(8, 8, 8, 8)
        pcl.setSpacing(6)

        layout.addWidget(self._plugins_container)
        self._refresh_plugins()
        return card

    def _refresh_plugins(self) -> None:
        # rebuild plugins list
        for i in reversed(range(self._plugins_container.layout().count())):
            w = self._plugins_container.layout().itemAt(i).widget()
            if w:
                w.setParent(None)

        if self._plugin_manager is None:
            return

        for pinfo in self._plugin_manager.list_plugins():
            row = QWidget()
            row.setStyleSheet(f"background-color: {self._c()['card_bg']}; border-radius: 8px; padding: 6px;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 8, 8, 8)
            rl.setSpacing(8)
            name_lbl = QLabel(pinfo.name)
            name_lbl.setFixedWidth(180)
            name_lbl.setStyleSheet("font-weight:600; font-size:14px; color: " + self._c()['fg_primary'] + "; background: transparent;")
            rl.addWidget(name_lbl)
            enabled_cb = QCheckBox("启用")
            enabled_cb.setStyleSheet(f"""
                QCheckBox {{ spacing: 8px; font-size: 13px; }}
                QCheckBox::indicator {{
                    width: 40px; height: 22px; border-radius: 11px;
                    background-color: {self._c()['fg_disabled']};
                }}
                QCheckBox::indicator:checked {{
                    background-color: {self._c()['accent']};
                }}
            """)
            enabled_cb.setChecked(bool(pinfo.enabled))
            enabled_cb.stateChanged.connect(lambda state, n=pinfo.name: self._toggle_plugin(n, state == 2))
            rl.addWidget(enabled_cb)
            panels = self._plugin_manager.get_panels(pinfo.name)
            open_btn = QPushButton("打开面板")
            open_btn.setEnabled(bool(panels) and pinfo.enabled)
            open_btn.clicked.connect(lambda _=None, n=pinfo.name: self._open_plugin(n))
            open_btn.setStyleSheet(f"background-color: {self._c()['accent']}; color: #fff; border-radius: 8px; padding:6px 10px; font-weight:600;")
            rl.addWidget(open_btn)
            rl.addStretch()
            self._plugins_container.layout().addWidget(row)

    def _open_plugin(self, plugin_name: str) -> None:
        if not self._plugin_manager:
            return
        panels = self._plugin_manager.get_panels(plugin_name)
        if not panels:
            QMessageBox.information(self, "插件", "插件未提供面板。")
            return
        # open the first registered panel
        display_name, _ = panels[0]
        widget = self._plugin_manager.create_panel(plugin_name, display_name, self._settings, self._ai_service, self._data_manager, None)
        if widget is None:
            QMessageBox.warning(self, "插件", "打开插件面板失败。")
            return
        widget.setWindowTitle(display_name)
        widget.setAttribute(Qt.WA_DeleteOnClose, True)
        # keep reference to avoid GC closing the window immediately
        try:
            self._open_plugin_windows.append(widget)
            widget.destroyed.connect(lambda _, w=widget: self._open_plugin_windows.remove(w) if w in self._open_plugin_windows else None)
        except Exception:
            pass
        widget.show()

    def _toggle_plugin(self, plugin_name: str, enable: bool) -> None:
        if not self._plugin_manager:
            return
        ok = self._plugin_manager.enable(plugin_name) if enable else self._plugin_manager.disable(plugin_name)
        if not ok:
            QMessageBox.warning(self, "插件", "设置失败，请检查文件权限。")
        self._refresh_plugins()

    def refresh_theme(self) -> None:
        # Re-apply dynamic styles for settings panel widgets
        c = get_colors()
        try:
            # inputs
            for le in self.findChildren(QLineEdit):
                le.setStyleSheet(self._input_qss())
        except Exception:
            pass
        try:
            for cb in self.findChildren(QComboBox):
                cb.setStyleSheet(self._combo_qss())
        except Exception:
            pass
        try:
            # refresh plugin list styling
            if self._plugin_manager is not None:
                self._refresh_plugins()
        except Exception:
            pass

    # ── Balance card ───────────────────────────────────────

    def _build_balance_card(self) -> QFrame:
        c = get_colors()
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        self._balance_widgets: dict[str, dict] = {}

        for idx, (key, label) in enumerate([
            ("campus_card", "校园卡"), ("water_card", "水卡"), ("electricity", "电费"),
        ]):
            enabled_cb = QCheckBox()
            enabled_cb.setChecked(self._settings.get_bool("Balance", f"{key}_enabled"))
            balance_input = QLineEdit(self._settings.get("Balance", f"{key}_balance"))
            balance_input.setStyleSheet(self._input_qss())
            balance_input.setFixedWidth(100)
            balance_input.setPlaceholderText("当前余额")
            threshold_input = QLineEdit(self._settings.get("Balance", f"{key}_threshold"))
            threshold_input.setStyleSheet(self._input_qss())
            threshold_input.setFixedWidth(80)
            threshold_input.setPlaceholderText("阈值")

            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(16, 8, 16, 8)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {c['fg_primary']}; font-size: 13px; background: transparent;")
            lbl.setFixedWidth(60)
            rl.addWidget(lbl)
            rl.addWidget(enabled_cb)
            rl.addWidget(QLabel("余额"))
            rl.addWidget(balance_input)
            rl.addWidget(QLabel("低于"))
            rl.addWidget(threshold_input)
            rl.addWidget(QLabel("元提醒"))
            rl.addStretch()
            layout.addWidget(row_w)
            if idx < 2:
                layout.addWidget(self._divider())

            self._balance_widgets[key] = {
                "enabled": enabled_cb, "balance": balance_input, "threshold": threshold_input,
            }

        layout.addWidget(self._divider())
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(16, 12, 16, 12)

        hint = QLabel("电费数据可从学校缴费平台查询，或按每周充值 20-30 估算。")
        hint.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; background: transparent;")
        br.addWidget(hint)

        br.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setFixedSize(72, 30)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_primary']}; border: none;
                border-radius: 8px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        save_btn.clicked.connect(self._save_balance_settings)
        br.addWidget(save_btn)
        layout.addWidget(btn_row)
        return card

    def _save_balance_settings(self) -> None:
        for key, w in self._balance_widgets.items():
            self._settings.set("Balance", f"{key}_enabled", str(w["enabled"].isChecked()).lower())
            self._settings.set("Balance", f"{key}_balance", w["balance"].text().strip())
            self._settings.set("Balance", f"{key}_threshold", w["threshold"].text().strip())
        self._settings.save()
        QMessageBox.information(self, "设置", "余额提醒设置已保存。")

    # ── General card ───────────────────────────────────────

    def _save_general_settings(self) -> None:
        self._settings.set("General", "auto_start", str(self._auto_start.isChecked()).lower())
        self._settings.set("General", "minimize_to_tray", str(self._minimize_tray.isChecked()).lower())
        self._settings.set("General", "reminder_enabled", str(self._reminder.isChecked()).lower())
        self._settings.save()
        from src.app import set_autostart
        set_autostart(self._auto_start.isChecked())
        QMessageBox.information(self, "设置", "通用设置已保存。")
