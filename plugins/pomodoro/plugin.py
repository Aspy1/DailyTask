"""简单的番茄钟插件示例。

提供一个面板：显示倒计时、开始/暂停/重置按钮，单次工作时长 25 分钟，短休息 5 分钟。
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import QTimer


def register(api):
    api.register_panel("番茄钟", factory)


class PomodoroWidget(QWidget):
    def __init__(self, settings, ai_service, data_manager, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._remaining = 25 * 60
        self._running = False

        layout = QVBoxLayout(self)
        self._label = QLabel(self._format(self._remaining))
        self._label.setStyleSheet("font-size:28px; font-weight:600;")
        layout.addWidget(self._label)

        btns = QHBoxLayout()
        self._start_btn = QPushButton("开始")
        self._start_btn.clicked.connect(self._start_pause)
        btns.addWidget(self._start_btn)
        self._reset_btn = QPushButton("重置")
        self._reset_btn.clicked.connect(self._reset)
        btns.addWidget(self._reset_btn)
        layout.addLayout(btns)

    def _format(self, s: int) -> str:
        m = s // 60
        sec = s % 60
        return f"{m:02d}:{sec:02d}"

    def _tick(self):
        if self._remaining > 0:
            self._remaining -= 1
            self._label.setText(self._format(self._remaining))
        else:
            self._timer.stop()
            self._running = False
            self._start_btn.setText("开始")

    def _start_pause(self):
        if self._running:
            self._timer.stop()
            self._running = False
            self._start_btn.setText("开始")
        else:
            self._timer.start()
            self._running = True
            self._start_btn.setText("暂停")

    def _reset(self):
        self._timer.stop()
        self._remaining = 25 * 60
        self._label.setText(self._format(self._remaining))
        self._running = False
        self._start_btn.setText("开始")


def factory(settings, ai_service, data_manager, parent=None):
    return PomodoroWidget(settings, ai_service, data_manager, parent)
