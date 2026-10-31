"""天气详情弹窗（从 `main_window.py` 拆出：那里超过 800 行上限，Q-A1）。

只依赖 `WeatherService` 的公开 getter 与信号；关闭时断开连接。
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from src.i18n.loader import tr
from src.ui.styles.cards import card
from src.ui.styles.theme import (
    LAYOUT,
    SIZE_BODY,
    SIZE_BODY_M,
    SIZE_BODY_S,
    SIZE_CAPTION,
    SIZE_SUBTITLE,
    SIZE_TINY,
    SIZE_TITLE,
    get_colors,
)
from src.ui.widgets.rounded_button import RoundedButton

logger = logging.getLogger(__name__)


class WeatherDetailDialog(QDialog):
    """天气详情对话框（支持刷新后自动更新）。"""

    def __init__(self, weather_service, parent=None) -> None:
        super().__init__(parent)
        self._ws = weather_service
        c = get_colors()

        self.setWindowTitle(tr("window.weather.title"))
        self.setMinimumWidth(LAYOUT["weather_dialog_min_width"])
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg_card']}; }}
            QLabel {{ background: transparent; border: none; }}
        """)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(16)

        self._layout.addLayout(self._build_title_row(c))

        # 实时天气区域
        self._now_card = None
        self._temp_label = None
        self._info_label = None
        self._hum_label = None
        self._wind_label = None
        self._no_data_label = None

        # 预报区域
        self._forecast_rows = []  # 保存预报行的引用

        # 首次加载
        self._build_ui()
        self._update_content()

        # 连接信号
        self._ws.weather_updated.connect(self._update_content)
        self._ws.forecast_updated.connect(self._update_content)

    def _build_title_row(self, c: dict) -> QHBoxLayout:
        """标题 + 更新时间 + 刷新按钮（从 `__init__` 抽出，控制函数长度）。"""
        title_row = QHBoxLayout()
        self._title = QLabel(tr("window.weather.title"))
        self._title.setStyleSheet(
            f"font-size: {SIZE_SUBTITLE}px; font-weight: 700; color: {c['fg_primary']};")
        title_row.addWidget(self._title)

        self._update_time_label = QLabel()
        self._update_time_label.setStyleSheet(
            f"font-size: {SIZE_TINY}px; color: {c['fg_hint']}; margin-left: 8px;")
        title_row.addWidget(self._update_time_label)
        title_row.addStretch()

        self._refresh_btn = RoundedButton(tr("window.weather.refresh"))
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['accent']};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: {SIZE_BODY_S}px;
            }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:disabled {{
                background-color: {c['fg_hint']};
                color: {c['bg_card']};
            }}
        """)
        self._refresh_btn.clicked.connect(self._on_refresh)
        title_row.addWidget(self._refresh_btn)
        return title_row

    def _build_ui(self) -> None:
        """构建 UI 结构。"""
        c = get_colors()
        self._layout.removeWidget(self._no_data_label) if self._no_data_label else None

        # 实时天气卡片
        if self._now_card:
            self._layout.removeWidget(self._now_card)
        self._now_card = card("item")
        card_layout = QVBoxLayout(self._now_card)
        card_layout.setSpacing(8)

        self._temp_label = QLabel()
        self._temp_label.setStyleSheet(
            f"font-size: {SIZE_TITLE}px; font-weight: 700; color: {c['fg_primary']};")
        card_layout.addWidget(self._temp_label)

        self._info_label = QLabel()
        self._info_label.setStyleSheet(
            f"font-size: {SIZE_BODY}px; color: {c['fg_secondary']};")
        card_layout.addWidget(self._info_label)

        row = QHBoxLayout()
        row.setSpacing(16)
        self._hum_label = QLabel()
        self._hum_label.setStyleSheet(f"font-size: {SIZE_BODY_S}px; color: {c['fg_hint']};")
        row.addWidget(self._hum_label)

        self._wind_label = QLabel()
        self._wind_label.setStyleSheet(f"font-size: {SIZE_BODY_S}px; color: {c['fg_hint']};")
        row.addWidget(self._wind_label)
        row.addStretch()
        card_layout.addLayout(row)

        self._layout.insertWidget(1, self._now_card)

        # 预报标题
        self._forecast_title = QLabel(tr("window.weather.forecast_title"))
        self._forecast_title.setStyleSheet(
            f"font-size: {SIZE_BODY_M}px; font-weight: 600; color: {c['fg_primary']};")
        self._layout.insertWidget(2, self._forecast_title)

        self._build_forecast_rows(c)

    def _build_forecast_rows(self, c: dict) -> None:
        """未来 3 天预报行（从 `_build_ui` 抽出，控制函数长度）。"""
        for i in range(3):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(12)

            date_lbl = QLabel()
            date_lbl.setStyleSheet(
                f"font-size: {SIZE_BODY_S}px; color: {c['fg_secondary']};"
                f" min-width: {LAYOUT['input_width_md']}px;")
            row_layout.addWidget(date_lbl)

            text_lbl = QLabel()
            text_lbl.setStyleSheet(f"font-size: {SIZE_BODY_S}px; color: {c['fg_primary']};")
            row_layout.addWidget(text_lbl)

            rain_lbl = QLabel()
            rain_lbl.setStyleSheet(f"font-size: {SIZE_CAPTION}px; color: {c['accent_text']};")
            row_layout.addWidget(rain_lbl)

            temp_lbl = QLabel()
            temp_lbl.setStyleSheet(
                f"font-size: {SIZE_BODY_S}px; color: {c['fg_secondary']};")
            temp_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row_layout.addWidget(temp_lbl)

            self._layout.insertWidget(3 + i, row_layout.itemAt(0).widget())
            self._forecast_rows.append({
                "date": date_lbl,
                "text": text_lbl,
                "rain": rain_lbl,
                "temp": temp_lbl,
            })

    def _update_content(self) -> None:
        """更新内容。"""
        now_cache_time = self._ws._now_cache_time
        if now_cache_time:
            self._update_time_label.setText(
                tr("window.weather.updated_at",
                   time=now_cache_time.strftime('%H:%M')))
        else:
            self._update_time_label.setText("")

        # 恢复刷新按钮状态
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText(tr("window.weather.refresh"))

        self._update_now_section()
        self._update_forecast_section()

    def _update_now_section(self) -> None:
        """更新实时天气卡片（无数据时隐藏卡片）。"""
        now = self._ws.get_now()
        if not now:
            if self._now_card:
                self._now_card.hide()
            return
        if self._now_card:
            self._now_card.show()
        if self._temp_label:
            self._temp_label.setText(f"{now.get('temp', '?')}°C")
        if self._info_label:
            self._info_label.setText(
                tr("window.weather.feels_like", text=now.get('text', '?'),
                   feels=now.get('feelsLike', '?')))
        if self._hum_label:
            self._hum_label.setText(
                tr("window.weather.humidity", value=now.get('humidity', '?')))
        if self._wind_label:
            self._wind_label.setText(
                tr("window.weather.wind", direction=now.get('windDir', '?'),
                   scale=now.get('windScale', '?')))

    def _update_forecast_section(self) -> None:
        """更新未来三天预报行。"""
        forecast = self._ws.get_forecast()
        for i, row in enumerate(self._forecast_rows):
            if i < len(forecast):
                self._fill_forecast_row(row, forecast[i])
            else:
                self._clear_forecast_row(row)

    @staticmethod
    def _fill_forecast_row(row: dict, day: dict) -> None:
        """填充单行预报（降水字段可能是脏数据，解析失败按无雨）。"""
        row["date"].setText(day.get('fxDate', '?'))
        row["text"].setText(day.get('textDay', '?'))
        precip = day.get('precip', '0')
        try:
            has_rain = float(precip) > 0
        except (TypeError, ValueError):
            has_rain = False
        if has_rain:
            row["rain"].setText(tr("window.weather.precip", value=precip))
            row["rain"].show()
        else:
            row["rain"].hide()
        row["temp"].setText(
            f"{day.get('tempMin', '?')}°C ~ {day.get('tempMax', '?')}°C")

    @staticmethod
    def _clear_forecast_row(row: dict) -> None:
        """清空无数据时的预报行。"""
        row["date"].setText("")
        row["text"].setText("")
        row["rain"].hide()
        row["temp"].setText("")

    def _on_refresh(self) -> None:
        """刷新按钮点击。"""
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("...")
        self._ws.refresh()

    def closeEvent(self, event) -> None:
        """关闭时断开信号连接。"""
        try:
            self._ws.weather_updated.disconnect(self._update_content)
            self._ws.forecast_updated.disconnect(self._update_content)
        except RuntimeError:
            logger.debug("WeatherDetailDialog.closeEvent 中忽略异常", exc_info=True)
        super().closeEvent(event)
