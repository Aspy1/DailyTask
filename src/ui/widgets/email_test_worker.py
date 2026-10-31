"""设置页「发送测试邮件」的后台线程。

SMTP 连接有 10 秒超时，不能放在 UI 线程（Q-C2 / R-004）。从 `settings_panel.py`
抽出：那个文件需要保持在 800 行以内（Q-A1）。
"""

from PySide6.QtCore import QThread, Signal

from src.i18n.loader import tr
from src.services.email_sender import EmailConfig, send_email_sync


class EmailTestWorker(QThread):
    """发一封测试邮件，结果通过信号回到 UI 线程。"""

    done = Signal(bool, str)

    def __init__(self, config: EmailConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config

    def run(self) -> None:
        try:
            send_email_sync(self._config, tr("panel.settings.email_test_subject"),
                            tr("panel.settings.email_test_body"))
            self.done.emit(True, "")
        # 边界捕获：外部 SMTP 的异常要回传给界面，不允许逃逸（Q-I1）
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, str(e))
