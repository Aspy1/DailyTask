"""API 测试窗口 - 用于验证外部 API 调用"""

from datetime import datetime

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QTextEdit,
    QVBoxLayout,
)

from src.i18n.loader import tr
from src.services.api_service import ApiService
from src.ui.styles.theme import SIZE_BODY, SIZE_SUBTITLE, font, get_colors
from src.ui.widgets.rounded_button import RoundedButton
from src.ui.widgets.rounded_input import RoundedLineEdit


class ApiTestDialog(QDialog):
    """API 测试对话框"""

    def __init__(self, api_service: ApiService, parent=None) -> None:
        super().__init__(parent)
        self._api = api_service
        c = get_colors()

        self.setWindowTitle(tr("dialog.api_test.title"))
        self.setMinimumSize(600, 500)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c['bg_card']};
                color: {c['fg_primary']};
            }}
            QLabel {{
                color: {c['fg_primary']};
                background: transparent;
            }}
            QLineEdit, QSpinBox {{
                background-color: {c['bg_input']};
                color: {c['fg_primary']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QTextEdit {{
                background-color: {c['bg_input']};
                color: {c['fg_primary']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                padding: 8px;
                font-family: Consolas;
                font-size: 12px;
            }}
            QPushButton {{
                background-color: {c['accent']};
                color: {c['fg_on_fill']};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {c['accent_hover']};
            }}
            QPushButton:pressed {{
                background-color: {c['accent_dim']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # 标题
        title = QLabel(tr("dialog.api_test.heading"))
        title.setFont(font(SIZE_SUBTITLE, 600))
        layout.addWidget(title)

        # 天气预报测试
        weather_group = QGroupBox(tr("dialog.api_test.group_weather"))
        weather_layout = QFormLayout()
        weather_group.setLayout(weather_layout)

        self._lat_input = RoundedLineEdit()
        self._lat_input.setPlaceholderText(tr("dialog.api_test.placeholder_lat"))
        self._lat_input.setText("31")
        weather_layout.addRow(tr("dialog.api_test.label_lat"), self._lat_input)

        self._lon_input = RoundedLineEdit()
        self._lon_input.setPlaceholderText(tr("dialog.api_test.placeholder_lon"))
        self._lon_input.setText("121")
        weather_layout.addRow(tr("dialog.api_test.label_lon"), self._lon_input)

        self._weather_btn = RoundedButton(tr("dialog.api_test.btn_weather"))
        self._weather_btn.clicked.connect(self._test_weather)
        weather_layout.addRow("", self._weather_btn)

        layout.addWidget(weather_group)

        # DeepSeek 额度测试
        balance_group = QGroupBox(tr("dialog.api_test.group_balance"))
        balance_layout = QFormLayout()
        balance_group.setLayout(balance_layout)

        self._api_key_input = RoundedLineEdit()
        self._api_key_input.setPlaceholderText("sk-...")
        balance_layout.addRow(tr("dialog.api_test.label_api_key"), self._api_key_input)

        self._balance_btn = RoundedButton(tr("dialog.api_test.btn_balance"))
        self._balance_btn.clicked.connect(self._test_balance)
        balance_layout.addRow("", self._balance_btn)

        layout.addWidget(balance_group)

        # 结果显示
        result_label = QLabel(tr("dialog.api_test.label_result"))
        result_label.setFont(font(SIZE_BODY, 600))
        layout.addWidget(result_label)

        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setMaximumHeight(150)
        layout.addWidget(self._result_text)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        # 连接信号
        self._api.weather_ready.connect(self._on_weather_result)
        self._api.balance_ready.connect(self._on_balance_result)
        self._api.error_occurred.connect(self._on_error)

    def _test_weather(self) -> None:
        try:
            lat = float(self._lat_input.text().strip())
            lon = float(self._lon_input.text().strip())
        except ValueError:
            self._result_text.append(tr("dialog.api_test.msg_invalid_coords"))
            return
        self._result_text.append(tr(
            "dialog.api_test.status_weather_request",
            time=datetime.now().strftime('%H:%M:%S'), lat=lat, lon=lon))
        self._api.fetch_weather(lat, lon)

    def _test_balance(self) -> None:
        api_key = self._api_key_input.text().strip()
        if not api_key:
            self._result_text.append(tr("dialog.api_test.msg_api_key_required"))
            return
        self._result_text.append(tr(
            "dialog.api_test.status_balance_request",
            time=datetime.now().strftime('%H:%M:%S')))
        self._api.fetch_deepseek_balance(api_key)

    def _on_weather_result(self, result: dict) -> None:
        if "error" in result:
            self._result_text.append(
                tr("dialog.api_test.result_weather_error", error=result['error']))
        else:
            self._result_text.append(tr(
                "dialog.api_test.result_weather_success",
                weather=result.get('weather_text', tr("dialog.api_test.value_unknown")),
                temperature=result.get('temperature', '?'),
                humidity=result.get('humidity', '?'),
                wind=result.get('wind_speed', '?'),
                time=result.get('timestamp', '?')))

    def _on_balance_result(self, result: dict) -> None:
        if "error" in result:
            self._result_text.append(
                tr("dialog.api_test.result_balance_error", error=result['error']))
        else:
            self._result_text.append(tr(
                "dialog.api_test.result_balance_success",
                total=f"{result.get('total_balance', 0):.4f}",
                currency=result.get('currency', 'CNY'),
                available=(tr("dialog.api_test.value_yes") if result.get('is_available')
                           else tr("dialog.api_test.value_no")),
                time=result.get('timestamp', '?')))

    def _on_error(self, error: str) -> None:
        self._result_text.append(tr("dialog.api_test.result_network_error", error=error))
