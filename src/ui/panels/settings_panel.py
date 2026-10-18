"""Settings panel — theme-aware card grouping."""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.i18n.loader import tr
from src.services.ai_service import AIService
from src.services.api_service import ApiService
from src.services.settings_manager import SettingsManager
from src.ui.styles.cards import card
from src.ui.styles.theme import (
    FIELD_H,
    SIZE_BODY_L,
    SIZE_BODY_S,
    btn_secondary_qss,
    combo_qss,
    font,
    get_colors,
    input_qss,
    size_small_button,
)
from src.ui.widgets.api_test_dialog import ApiTestDialog
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedComboBox, RoundedLineEdit
from src.ui.widgets.toggle_switch import ToggleSwitch

# 数据目录（本文件在 src/ui/panels/ 下，往上 3 层是仓库根）
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"

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
    # OpenCode Go（订阅制）：OpenAI 兼容端点 + 订阅 key。
    # ⚠ 必须用 /inference/go/... 这个地址；免费模型在**按量付费**端点会被
    # 403 FreeTierError 拦下（"free tier can only be used from within OpenCode"）。
    # 代码侧会自动补 x-opencode-session 与自定义 UA（见 ai_service.provider_headers）。
    "opencode": {
        "name": "OpenCode Go", "endpoint": "https://opencode.ai/inference/go/openai/v1",
        "model": "longcat-2.5-preview-free", "key_placeholder": "sk-...",
        "key_url": "https://opencode.ai/console",
    },
}


logger = logging.getLogger(__name__)



class SettingsPanel(QWidget):
    def __init__(self, settings: SettingsManager, ai_service: AIService, plugin_manager=None, data_manager=None, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._ai_service = ai_service
        self._plugin_manager = plugin_manager
        self._data_manager = data_manager
        self._api_service = ApiService()  # API 服务
        # Keep references to opened plugin windows to avoid GC closing them
        self._open_plugin_windows = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        layout.addWidget(self._section_heading(tr("settings.general")))
        layout.addWidget(self._build_general_card())
        layout.addWidget(self._section_heading(tr("settings.ai")))
        layout.addWidget(self._build_ai_card())
        layout.addWidget(self._section_heading(tr("panel.settings.section_email")))
        layout.addWidget(self._build_email_card())
        layout.addWidget(self._section_heading(tr("panel.settings.section_balance")))
        layout.addWidget(self._build_balance_card())
        layout.addWidget(self._section_heading(tr("panel.settings.section_weather")))
        layout.addWidget(self._build_weather_card())
        # 插件管理
        if self._plugin_manager is not None:
            layout.addWidget(self._section_heading(tr("panel.settings.section_plugins")))
            layout.addWidget(self._build_plugins_card())
        layout.addWidget(self._section_heading(tr("panel.settings.section_about")))
        layout.addWidget(self._build_about_card())
        layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── helpers ────────────────────────────────────────────

    def _c(self) -> dict:
        return get_colors()

    def _section_heading(self, title: str) -> QLabel:
        c = self._c()
        lbl = QLabel(title)
        lbl.setFont(font(SIZE_BODY_L))
        lbl.setStyleSheet(f"color: {c['section_heading']}; font-weight: 600; padding: 0 2px;")
        return lbl

    def _card(self) -> QFrame:
        """设置卡：圆角与底色走卡片组件；**内边距由各行自己管**（故用 spacing_none）。

        这样"设置卡长什么样"由 `cards.CARD_VARIANTS["panel"]` 一处决定，
        不再是每个面板各写一段 QSS。
        """
        return card("panel", pad="spacing_none")

    def _row(self, label: str, widget: QWidget, hint: QWidget | None = None) -> QWidget:
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
        c = self._c()
        d = QFrame()
        d.setFrameShape(QFrame.Shape.HLine)
        d.setStyleSheet(f"border: none; background-color: {c['divider']}; max-height: 1px; margin: 0 18px;")
        return d

    def _input_qss(self) -> str:
        """委托 theme 的统一样式（Q-H18）。"""
        return input_qss()

    def _combo_qss(self) -> str:
        """委托 theme 的统一样式（Q-H18）。"""
        return combo_qss()

    def _build_ai_card(self) -> QFrame:
        c = get_colors()
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        current = self._settings.get("AI", "provider", "deepseek")
        self._provider_combo = RoundedComboBox()
        self._provider_combo.setStyleSheet(self._combo_qss())
        for key, info in PROVIDERS.items():
            self._provider_combo.addItem(info["name"], key)
        idx = list(PROVIDERS.keys()).index(current) if current in PROVIDERS else 0
        self._provider_combo.setCurrentIndex(idx)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        layout.addWidget(self._row(tr("panel.settings.label_provider"), self._provider_combo))
        layout.addWidget(self._divider())

        self._api_key_input = RoundedLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setStyleSheet(self._input_qss())
        self._api_key_input.setText(self._settings.api_key)
        layout.addWidget(self._row(tr("panel.settings.label_api_key"), self._api_key_input))
        layout.addWidget(self._divider())

        self._model_combo = RoundedComboBox()
        self._model_combo.setStyleSheet(self._combo_qss())
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumWidth(200)
        self._model_combo.setFixedHeight(FIELD_H)
        layout.addWidget(self._row(tr("settings.model"), self._model_combo))
        layout.addWidget(self._divider())

        self._endpoint_input = RoundedLineEdit()
        self._endpoint_input.setStyleSheet(self._input_qss())
        layout.addWidget(self._row(tr("panel.settings.label_endpoint"), self._endpoint_input))
        layout.addWidget(self._divider())

        status_row = QWidget()
        status_row.setStyleSheet("background: transparent;")
        sr = QHBoxLayout(status_row)
        sr.setContentsMargins(16, 12, 16, 12)
        self._status_label = QLabel()
        sr.addWidget(self._status_label)
        sr.addStretch()
        save_btn = RoundedButton(tr("panel.settings.btn_save"))
        size_small_button(save_btn)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
                border-radius: 8px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:pressed {{ background-color: {c['accent_dim']}; }}
        """)
        save_btn.clicked.connect(self._save_ai_settings)
        sr.addWidget(save_btn)

        test_btn = RoundedButton(tr("panel.settings.btn_api_test"))
        size_small_button(test_btn)
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['btn_secondary_fg']};
                border: none; border-radius: 8px; font-weight: 500; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        test_btn.clicked.connect(self._open_api_test)
        sr.addWidget(test_btn)
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

        self._auto_start = ToggleSwitch()
        self._auto_start.setChecked(self._settings.get_bool("General", "auto_start"))
        layout.addWidget(self._row(tr("settings.auto_start"), self._auto_start))
        layout.addWidget(self._divider())

        self._minimize_tray = ToggleSwitch()
        self._minimize_tray.setChecked(self._settings.get_bool("General", "minimize_to_tray"))
        layout.addWidget(self._row(tr("settings.minimize_to_tray"), self._minimize_tray))
        layout.addWidget(self._divider())

        self._reminder = ToggleSwitch()
        self._reminder.setChecked(self._settings.get_bool("General", "reminder_enabled"))
        layout.addWidget(self._row(tr("settings.reminder_enabled"), self._reminder))
        layout.addWidget(self._divider())

        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(16, 12, 16, 12)
        br.addStretch()
        save_btn = RoundedButton(tr("panel.settings.btn_save"))
        size_small_button(save_btn)
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
        elif key == "opencode":
            self._model_combo.addItems([
                "longcat-2.5-preview-free",   # Go 订阅内不限量
                "deepseek-v4.1-flash", "glm-5.3-flash", "mimo-v2.6-flash", "qwen3.8-flash",
            ])
        else:
            self._model_combo.addItems([
                "claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001",
            ])
        cur = self._settings.get("AI", "model", info["model"])
        i = self._model_combo.findText(cur)
        if i >= 0:
            self._model_combo.setCurrentIndex(i)

    def _update_status(self) -> None:
        c = get_colors()
        if self._ai_service.is_configured:
            self._status_label.setText("● " + tr("settings.status.configured"))
            self._status_label.setStyleSheet(f"color: {c['green']}; font-size: 13px; background: transparent;")
        else:
            self._status_label.setText("● " + tr("settings.status.not_configured"))
            self._status_label.setStyleSheet(f"color: {c['red']}; font-size: 13px; background: transparent;")

    def _open_api_test(self) -> None:
        """打开 API 测试窗口"""
        dialog = ApiTestDialog(self._api_service, self)
        dialog.exec()

    def _save_ai_settings(self) -> None:
        self._settings.api_key = self._api_key_input.text().strip()
        self._settings.set("AI", "provider", self._provider_combo.currentData())
        self._settings.set("AI", "model", self._model_combo.currentText())
        self._settings.set("AI", "api_endpoint", self._endpoint_input.text().strip())
        self._settings.save()
        self._update_status()
        QMessageBox.information(self, tr("panel.settings.dialog_title"), tr("panel.settings.msg_ai_saved"))

    def _build_email_card(self) -> QFrame:
        c = get_colors()
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        self._smtp_host = QLineEdit(self._settings.get("Email", "smtp_host", fallback="smtp.qq.com"))
        self._smtp_host.setStyleSheet(self._input_qss())
        layout.addWidget(self._row(tr("panel.settings.label_smtp_host"), self._smtp_host))
        layout.addWidget(self._divider())

        self._smtp_port = QLineEdit(self._settings.get("Email", "smtp_port", fallback="587"))
        self._smtp_port.setStyleSheet(self._input_qss())
        layout.addWidget(self._row(tr("panel.settings.label_smtp_port"), self._smtp_port))
        layout.addWidget(self._divider())

        self._smtp_user = QLineEdit(self._settings.get("Email", "smtp_user", fallback=""))
        self._smtp_user.setStyleSheet(self._input_qss())
        self._smtp_user.setPlaceholderText(tr("panel.settings.placeholder_smtp_user"))
        layout.addWidget(self._row(tr("panel.settings.label_smtp_user"), self._smtp_user))
        layout.addWidget(self._divider())

        self._smtp_pass = QLineEdit(self._settings.get("Email", "smtp_pass", fallback=""))
        self._smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._smtp_pass.setStyleSheet(self._input_qss())
        self._smtp_pass.setPlaceholderText(tr("panel.settings.placeholder_smtp_pass"))
        layout.addWidget(self._row(tr("panel.settings.label_smtp_pass"), self._smtp_pass))

        help_lbl = QLabel(tr("panel.settings.hint_email_help"))
        help_lbl.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; padding: 0 18px;")
        layout.addWidget(help_lbl)

        layout.addWidget(self._divider())
        test_row = QWidget()
        test_row.setStyleSheet("background: transparent;")
        trl = QHBoxLayout(test_row)
        trl.setContentsMargins(16, 8, 16, 8)
        test_btn = RoundedButton(tr("panel.settings.btn_send_test_email"))
        test_btn.setMinimumWidth(120)
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['accent']}; color: {c['fg_on_fill']}; border: none;
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
        save_btn = RoundedButton(tr("panel.settings.btn_save"))
        size_small_button(save_btn)
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
            QMessageBox.warning(self, tr("panel.settings.dialog_title_error"), tr("panel.settings.msg_email_required"))
            return

        try:
            msg = MIMEText(tr("panel.settings.email_test_body"), "plain", "utf-8")
            msg["Subject"] = tr("panel.settings.email_test_subject")
            msg["From"] = user
            msg["To"] = user
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
            QMessageBox.information(self, tr("panel.settings.dialog_title_success"), tr("panel.settings.msg_test_email_sent", user=user))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("panel.settings.dialog_title_failed"), tr("panel.settings.msg_send_failed", error=e))

    def _save_email_settings(self) -> None:
        self._settings.set("Email", "smtp_host", self._smtp_host.text().strip())
        self._settings.set("Email", "smtp_port", self._smtp_port.text().strip())
        self._settings.set("Email", "smtp_user", self._smtp_user.text().strip())
        self._settings.set("Email", "smtp_pass", self._smtp_pass.text().strip())
        self._settings.save()
        QMessageBox.information(self, tr("panel.settings.dialog_title"), tr("panel.settings.msg_email_saved"))

    # ── 天气设置卡片 ────────────────────────────────────────
    def _build_weather_card(self) -> QFrame:
        """天气设置卡片"""
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(0)

        # API Key
        self._weather_api_key = RoundedLineEdit()
        self._weather_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._weather_api_key.setStyleSheet(self._input_qss())
        self._weather_api_key.setText(self._settings.weather_api_key)
        self._weather_api_key.setPlaceholderText(tr("panel.settings.placeholder_weather_api_key"))
        layout.addWidget(self._row(tr("panel.settings.label_api_key"), self._weather_api_key))
        layout.addWidget(self._divider())

        # API Host
        self._weather_api_host = RoundedLineEdit()
        self._weather_api_host.setStyleSheet(self._input_qss())
        self._weather_api_host.setText(self._settings.weather_api_host)
        self._weather_api_host.setPlaceholderText(tr("panel.settings.placeholder_weather_api_host"))
        layout.addWidget(self._row(tr("panel.settings.label_weather_api_host"), self._weather_api_host))
        layout.addWidget(self._divider())

        # 位置（经度/纬度）：原「场景存档」的位置并入此处
        self._weather_lat = RoundedLineEdit()
        self._weather_lat.setStyleSheet(self._input_qss())
        self._weather_lat.setText(self._settings.weather_lat)
        self._weather_lat.setPlaceholderText(tr("panel.settings.placeholder_weather_lat"))
        layout.addWidget(self._row(tr("panel.settings.label_weather_lat"), self._weather_lat))
        layout.addWidget(self._divider())

        self._weather_lon = RoundedLineEdit()
        self._weather_lon.setStyleSheet(self._input_qss())
        self._weather_lon.setText(self._settings.weather_lon)
        self._weather_lon.setPlaceholderText(tr("panel.settings.placeholder_weather_lon"))
        layout.addWidget(self._row(tr("panel.settings.label_weather_lon"), self._weather_lon))
        layout.addWidget(self._divider())

        # 定时更新
        self._weather_auto_update = ToggleSwitch()
        self._weather_auto_update.setChecked(self._settings.weather_auto_update)
        layout.addWidget(self._row(tr("panel.settings.label_weather_auto_update"), self._weather_auto_update))
        layout.addWidget(self._divider())

        # 调用统计
        stats_row = QWidget()
        stats_row.setStyleSheet("background: transparent;")
        sr = QHBoxLayout(stats_row)
        sr.setContentsMargins(16, 12, 16, 12)
        self._weather_stats_label = QLabel(tr("panel.settings.label_weather_stats", count=0))
        self._weather_stats_label.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px;")
        sr.addWidget(self._weather_stats_label)
        sr.addStretch()
        layout.addWidget(stats_row)
        layout.addWidget(self._divider())

        # 保存按钮
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(16, 12, 16, 12)
        br.addStretch()
        save_btn = RoundedButton(tr("panel.settings.btn_save"))
        size_small_button(save_btn)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {c['btn_secondary_bg']}; color: {c['fg_primary']}; border: none;
                border-radius: 8px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ background-color: {c['btn_secondary_hover']}; }}
        """)
        save_btn.clicked.connect(self._save_weather_settings)
        br.addWidget(save_btn)
        layout.addWidget(btn_row)

        # 初始化后更新统计
        self._update_weather_stats()
        return card

    def _update_weather_stats(self) -> None:
        """更新天气 API 调用统计显示（**坏文件不能让应用崩** —— 这是启动路径）。"""
        from datetime import datetime
        from pathlib import Path

        from src.services.weather_store import read_json_safe

        stats_file = Path(__file__).resolve().parents[3] / "data" / "weather_stats.json"
        stats = read_json_safe(stats_file)          # 缺文件/损坏 → {}，不抛
        month = datetime.now().strftime("%Y-%m")
        monthly = stats.get("monthly", {}).get(month, {}).get("total", 0)
        self._weather_stats_label.setText(tr("panel.settings.label_weather_stats", count=monthly))

    def _save_weather_settings(self) -> None:
        """保存天气设置"""
        self._settings.weather_api_key = self._weather_api_key.text().strip()
        self._settings.weather_api_host = self._weather_api_host.text().strip()
        self._settings.weather_auto_update = self._weather_auto_update.isChecked()
        for field, attr, default in ((self._weather_lat, "weather_lat", "31.23"),
                                     (self._weather_lon, "weather_lon", "121.47")):
            raw = field.text().strip()
            try:
                float(raw)
            except ValueError:
                raw = default
            setattr(self._settings, attr, raw)
        self._settings.save()
        self._update_weather_stats()
        QMessageBox.information(self, tr("panel.settings.dialog_title"), tr("panel.settings.msg_weather_saved"))

    # ── 关于卡片 ────────────────────────────────────────────
    def _build_about_card(self) -> QFrame:
        """关于：版本 / 说明 / 仓库链接 / 数据目录（原侧边栏弹窗并入设置）。"""
        c = self._c()
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        title = QLabel(f"{tr('app.name')}  v{tr('app.version')}")
        title.setStyleSheet(
            f"color: {c['fg_primary']}; font-size: {SIZE_BODY_L}px; font-weight: 600;"
            f" background: transparent;")
        layout.addWidget(title)

        desc = QLabel(tr("panel.settings.about_desc"))
        desc.setStyleSheet(
            f"color: {c['fg_secondary']}; font-size: {SIZE_BODY_S}px; background: transparent;")
        layout.addWidget(desc)

        link = QLabel(f'<a href="https://github.com/Aspy1/DailyTask">{tr("panel.settings.about_link")}</a>')
        link.setOpenExternalLinks(True)
        link.setStyleSheet(f"background: transparent; font-size: {SIZE_BODY_S}px;")
        layout.addWidget(link)

        data_btn = RoundedButton(tr("panel.settings.btn_open_data_dir"))
        data_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        data_btn.setStyleSheet(btn_secondary_qss())
        data_btn.clicked.connect(self._open_data_dir)
        layout.addWidget(data_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        return card

    def _open_data_dir(self) -> None:
        """在文件管理器里打开 data/（数据是本地 JSON，用户可能想直接看）。"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(_DATA_DIR)))

    # ── 插件卡片 ────────────────────────────────────────────
    def _build_plugins_card(self) -> QFrame:
        self._c()
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
            enabled_cb = ToggleSwitch()
            enabled_cb.setChecked(bool(pinfo.enabled))
            enabled_cb.toggled.connect(lambda checked, n=pinfo.name: self._toggle_plugin(n, checked))
            rl.addWidget(enabled_cb)
            panels = self._plugin_manager.get_panels(pinfo.name)
            open_btn = RoundedButton(tr("panel.settings.btn_open_plugin_panel"))
            open_btn.setEnabled(bool(panels) and pinfo.enabled)
            open_btn.clicked.connect(lambda _=None, n=pinfo.name: self._open_plugin(n))
            open_btn.setStyleSheet(f"background-color: {self._c()['accent']}; color: {self._c()['fg_on_fill']}; border-radius: 8px; padding:6px 10px; font-weight:600;")
            rl.addWidget(open_btn)
            rl.addStretch()
            self._plugins_container.layout().addWidget(row)

    def _open_plugin(self, plugin_name: str) -> None:
        if not self._plugin_manager:
            return
        panels = self._plugin_manager.get_panels(plugin_name)
        if not panels:
            QMessageBox.information(self, tr("panel.settings.dialog_title_plugin"), tr("panel.settings.msg_plugin_no_panel"))
            return
        # open the first registered panel
        display_name, _ = panels[0]
        widget = self._plugin_manager.create_panel(plugin_name, display_name, self._settings, self._ai_service, self._data_manager, None)
        if widget is None:
            QMessageBox.warning(self, tr("panel.settings.dialog_title_plugin"), tr("panel.settings.msg_plugin_open_failed"))
            return
        widget.setWindowTitle(display_name)
        widget.setAttribute(Qt.WA_DeleteOnClose, True)
        # keep reference to avoid GC closing the window immediately
        try:
            self._open_plugin_windows.append(widget)
            widget.destroyed.connect(lambda _, w=widget: self._open_plugin_windows.remove(w) if w in self._open_plugin_windows else None)
        except Exception:
            logger.debug("SettingsPanel._open_plugin 中忽略异常", exc_info=True)
        widget.show()

    def _toggle_plugin(self, plugin_name: str, enable: bool) -> None:
        if not self._plugin_manager:
            return
        ok = self._plugin_manager.enable(plugin_name) if enable else self._plugin_manager.disable(plugin_name)
        if not ok:
            QMessageBox.warning(self, tr("panel.settings.dialog_title_plugin"), tr("panel.settings.msg_plugin_toggle_failed"))
        self._refresh_plugins()

    def refresh_theme(self) -> None:
        # Re-apply dynamic styles for settings panel widgets
        try:
            # inputs
            for le in self.findChildren(QLineEdit):
                le.setStyleSheet(self._input_qss())
        except Exception:
            logger.debug("SettingsPanel.refresh_theme 中忽略异常", exc_info=True)
        try:
            for cb in self.findChildren(QComboBox):
                cb.setStyleSheet(self._combo_qss())
        except Exception:
            logger.debug("SettingsPanel.refresh_theme 中忽略异常", exc_info=True)
        try:
            # refresh plugin list styling
            if self._plugin_manager is not None:
                self._refresh_plugins()
        except Exception:
            logger.debug("SettingsPanel.refresh_theme 中忽略异常", exc_info=True)

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
            ("campus_card", tr("panel.settings.balance_campus_card")), ("water_card", tr("panel.settings.balance_water_card")), ("electricity", tr("panel.settings.balance_electricity")),
        ]):
            enabled_cb = QCheckBox()
            enabled_cb.setChecked(self._settings.get_bool("Balance", f"{key}_enabled"))
            balance_input = QLineEdit(self._settings.get("Balance", f"{key}_balance"))
            balance_input.setStyleSheet(self._input_qss())
            balance_input.setFixedWidth(100)
            balance_input.setPlaceholderText(tr("panel.settings.placeholder_balance"))
            threshold_input = QLineEdit(self._settings.get("Balance", f"{key}_threshold"))
            threshold_input.setStyleSheet(self._input_qss())
            threshold_input.setFixedWidth(80)
            threshold_input.setPlaceholderText(tr("panel.settings.placeholder_threshold"))

            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(16, 8, 16, 8)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {c['fg_primary']}; font-size: 13px; background: transparent;")
            lbl.setFixedWidth(60)
            rl.addWidget(lbl)
            rl.addWidget(enabled_cb)
            rl.addWidget(QLabel(tr("panel.settings.label_balance")))
            rl.addWidget(balance_input)
            rl.addWidget(QLabel(tr("panel.settings.label_below")))
            rl.addWidget(threshold_input)
            rl.addWidget(QLabel(tr("panel.settings.label_yuan_remind")))
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

        hint = QLabel(tr("panel.settings.hint_balance_electricity"))
        hint.setStyleSheet(f"color: {c['fg_hint']}; font-size: 13px; background: transparent;")
        br.addWidget(hint)

        br.addStretch()
        save_btn = RoundedButton(tr("panel.settings.btn_save"))
        size_small_button(save_btn)
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
        QMessageBox.information(self, tr("panel.settings.dialog_title"), tr("panel.settings.msg_balance_saved"))

    # ── General card ───────────────────────────────────────

    def _save_general_settings(self) -> None:
        self._settings.set("General", "auto_start", str(self._auto_start.isChecked()).lower())
        self._settings.set("General", "minimize_to_tray", str(self._minimize_tray.isChecked()).lower())
        self._settings.set("General", "reminder_enabled", str(self._reminder.isChecked()).lower())
        self._settings.save()
        from src.app import set_autostart
        set_autostart(self._auto_start.isChecked())
        QMessageBox.information(self, tr("panel.settings.dialog_title"), tr("panel.settings.msg_general_saved"))
