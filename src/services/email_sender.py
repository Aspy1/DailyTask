"""邮件发送：**永不阻塞 UI 线程**。

历史问题：`ReminderService._send_email()` 与设置面板的「发送测试邮件」都在主线程直接
`smtplib.SMTP(...)`，超时 10 秒 → 提醒 tick / 点按钮时界面整段卡死（Q-C2 / R-004）。

这里把「发」放到一条后台守护线程里串行执行：
- 提醒服务只负责把任务**入队**（O(1)，不会卡）；
- 同一时刻只有一个 SMTP 会话（QQ 邮箱对并发登录不友好）；
- 发送失败只记日志，不影响调用方。

`send_email_sync()` 保留给需要"等结果"的测试邮件弹窗（由它自己起 QThread）。
"""

import logging
import queue
import smtplib
import threading
from dataclasses import dataclass
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailConfig:
    """一次发送需要的全部配置（**在调用方线程快照**，worker 不再碰 SettingsManager）。"""

    host: str = "smtp.qq.com"
    port: int = 587
    user: str = ""
    password: str = ""
    recipient: str = ""
    timeout: int = 10


def send_email_sync(config: EmailConfig, subject: str, body: str) -> None:
    """同步发送一封纯文本邮件；失败抛异常（调用方决定怎么呈现）。"""
    recipient = config.recipient or config.user
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.user
    msg["To"] = recipient
    with smtplib.SMTP(config.host, config.port, timeout=config.timeout) as s:
        s.starttls()
        s.login(config.user, config.password)
        s.send_message(msg)


class EmailSender:
    """串行后台发件队列（单例由 `get_sender()` 提供）。"""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[EmailConfig, str, str] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="email-sender", daemon=True)
        self._thread.start()
        self._closed = False

    def send(self, config: EmailConfig, subject: str, body: str) -> None:
        """入队（立即返回）。未配置账号时直接跳过。"""
        if not config.user or not config.password:
            logger.info("Email not configured, skipping: %s", subject)
            return
        if self._closed:
            logger.warning("Email sender already closed, dropping: %s", subject)
            return
        self._queue.put((config, subject, body))

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                break
            config, subject, body = job
            try:
                send_email_sync(config, subject, body)
                logger.info("Email sent: %s", subject)
            # 边界捕获：外部 SMTP 的异常不能影响提醒服务（Q-I1）
            except Exception as e:  # noqa: BLE001
                logger.error("Failed to send email '%s': %s", subject, e)
                continue

    def shutdown(self, timeout: float = 2.0) -> None:
        """退出前尽量把已入队的邮件发完（最多等 `timeout` 秒）。"""
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=timeout)


_SENDER: EmailSender | None = None
_SENDER_LOCK = threading.Lock()


def get_sender() -> EmailSender:
    """进程级单例（懒创建；一条后台线程足够）。"""
    global _SENDER
    with _SENDER_LOCK:
        if _SENDER is None:
            _SENDER = EmailSender()
        return _SENDER
