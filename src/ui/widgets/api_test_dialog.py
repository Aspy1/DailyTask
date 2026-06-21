"""API 测试窗口 - 用于验证外部 API 调用"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QGroupBox, QFormLayout, QSpinBox,
    QDialogButtonBox, QDialog,
)
from PySide6.QtGui import QFont

from src.services.api_service import ApiService
from src.ui.styles.theme import get_colors, FONT_CN, SIZE_BODY_S, SIZE_BODY, SIZE_SUBTITLE


class ApiTestDialog(QDialog):
    """API 测试对话框"""

    def __init__(self, api_service: ApiService, parent=None):
        super().__init__(parent)
        self._api = api_service
        c = get_colors()

        self.setWindowTitle("API 测试窗口")
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
                color: #fff;
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
        title = QLabel("外部 API 测试")
        title.setFont(QFont(FONT_CN, SIZE_SUBTITLE, 600))
        layout.addWidget(title)

        # 天气预报测试
        weather_group = QGroupBox("天气预报 API (Open-Meteo)")
        weather_layout = QFormLayout()
        weather_group.setLayout(weather_layout)

        self._lat_input = QLineEdit()
        self._lat_input.setPlaceholderText("如: 31.23")
        self._lat_input.setText("31")
        weather_layout.addRow("纬度:", self._lat_input)

        self._lon_input = QLineEdit()
        self._lon_input.setPlaceholderText("如: 121.47")
        self._lon_input.setText("121")
        weather_layout.addRow("经度:", self._lon_input)

        self._weather_btn = QPushButton("测试天气预报")
        self._weather_btn.clicked.connect(self._test_weather)
        weather_layout.addRow("", self._weather_btn)

        layout.addWidget(weather_group)

        # DeepSeek 额度测试
        balance_group = QGroupBox("DeepSeek 余额 API")
        balance_layout = QFormLayout()
        balance_group.setLayout(balance_layout)

        self._api_key_input = QLineEdit()
        self._api_key_input.setPlaceholderText("sk-...")
        balance_layout.addRow("API Key:", self._api_key_input)

        self._balance_btn = QPushButton("查询余额")
        self._balance_btn.clicked.connect(self._test_balance)
        balance_layout.addRow("", self._balance_btn)

        layout.addWidget(balance_group)

        # 结果显示
        result_label = QLabel("测试结果:")
        result_label.setFont(QFont(FONT_CN, SIZE_BODY, 600))
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
            self._result_text.append("[错误] 请输入有效的经纬度数字")
            return
        self._result_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] 请求天气数据 ({lat}°N, {lon}°E)...")
        self._api.fetch_weather(lat, lon)

    def _test_balance(self) -> None:
        api_key = self._api_key_input.text().strip()
        if not api_key:
            self._result_text.append("[错误] 请输入 API Key")
            return
        self._result_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] 请求 DeepSeek 余额...")
        self._api.fetch_deepseek_balance(api_key)

    def _on_weather_result(self, result: dict) -> None:
        from datetime import datetime
        if "error" in result:
            self._result_text.append(f"[天气 API 错误] {result['error']}")
        else:
            self._result_text.append(
                f"[天气 API 成功]\n"
                f"  天气: {result.get('weather_text', '未知')}\n"
                f"  温度: {result.get('temperature', '?')}°C\n"
                f"  湿度: {result.get('humidity', '?')}%\n"
                f"  风速: {result.get('wind_speed', '?')} km/h\n"
                f"  更新时间: {result.get('timestamp', '?')}"
            )

    def _on_balance_result(self, result: dict) -> None:
        from datetime import datetime
        if "error" in result:
            self._result_text.append(f"[余额 API 错误] {result['error']}")
        else:
            self._result_text.append(
                f"[余额 API 成功]\n"
                f"  总额: {result.get('total_balance', 0):.4f} {result.get('currency', 'CNY')}\n"
                f"  可用: {'是' if result.get('is_available') else '否'}\n"
                f"  更新时间: {result.get('timestamp', '?')}"
            )

    def _on_error(self, error: str) -> None:
        self._result_text.append(f"[网络错误] {error}")


from datetime import datetime
