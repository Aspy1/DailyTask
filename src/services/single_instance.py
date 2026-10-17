"""单实例通道的**共享定义 + 客户端**：应用与 `scripts/actions.py` 都用它。

应用在 `src/app.py` 起 `QLocalServer(SINGLE_INSTANCE_KEY)`。CLI 在**写数据之前**先问它：
应用在跑 → 把命令**交给应用执行**（应用是唯一写者）；不在跑 → 自己写文件。

为什么单独一个模块：`src/app.py` 一被 import 就会拉起 PySide6 + 全部面板，CLI 不该付这个
代价（`PLAN.md` P17 阶段 3）。
"""

import json
import time

SINGLE_INSTANCE_KEY = "StudentSchedulerSingleInstance"

# 委派协议：一行 JSON（`\n` 收尾）
#   请求 {"argv": ["add_item", "--name", "纸巾"]}
#   应答 {"ok": true, "out": "OK ..."}
#
# 传 **argv 列表**而不是命令串：命令串要重新拼引号，参数里带空格（"--name 抽纸 一提"）
# 就会拆错（`ERRORS #045` 那类问题的近亲）。
CONNECT_TIMEOUT_MS = 300
REPLY_TIMEOUT_MS = 5000

CHANNEL_DELEGATE = "delegate"
CHANNEL_DIRECT = "direct"
CHANNEL_REFUSE = "refuse"

REFUSE_MESSAGE = ("应用正在运行但没有按协议回应（可能是旧版本）。"
                  "请重启应用后再改数据，或先关掉它。")
BAD_REQUEST_MESSAGE = "无法解析的委派请求（协议或版本不匹配？）"
BAD_REPLY_MESSAGE = "应用的回复不是合法帧（协议或版本不匹配？）"


def decide_channel(connected: bool, replied: bool) -> str:
    """(是否连上应用, 是否按协议回应) → 走哪条通道。**纯函数**，便于测试。

    - 没连上 → `direct`：应用没在跑，CLI 自己写文件（与以前一样）
    - 连上且回应 → `delegate`：交给应用执行（唯一写者，不会和 CLI 抢同一批文件）
    - 连上但没回应 → `refuse`：**可能**是旧版本应用、协议对不上 —— 这时直写会与它并发
      写同一批文件，所以宁可拒绝并说清楚，也不静默直写
    """
    if not connected:
        return CHANNEL_DIRECT
    return CHANNEL_DELEGATE if replied else CHANNEL_REFUSE


def encode_request(argv: list[str]) -> bytes:
    return (json.dumps({"argv": list(argv)}, ensure_ascii=False) + "\n").encode("utf-8")


def decode_request(line: str) -> list[str] | None:
    """解析请求行；不是合法请求返回 None（服务端据此回错误而不是崩）。"""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    argv = payload.get("argv") if isinstance(payload, dict) else None
    return [str(a) for a in argv] if isinstance(argv, list) else None


def encode_reply(ok: bool, out: str) -> bytes:
    return (json.dumps({"ok": ok, "out": out}, ensure_ascii=False) + "\n").encode("utf-8")


def decode_reply(line: str) -> tuple[bool, str] | None:
    """解析应答帧；结构不对返回 None。

    ⚠ 调用方拿到 None 时必须**拒绝**，不能把原文当结果交出去（审查 2026-10-17 #7）。
    """
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    ok, out = payload.get("ok"), payload.get("out")
    if not isinstance(ok, bool) or not isinstance(out, str):
        return None
    return ok, out


def feed_buffer(buf: bytes, chunk: bytes) -> tuple[bytes, str | None]:
    """把新到的字节并进缓冲：凑齐**一行**就返回 `(剩余缓冲, 那一行)`，否则 `(新缓冲, None)`。

    本地 socket 是**字节流**不是消息流 —— 一次读可能只拿到半帧（审查 #7）。
    """
    buf += chunk
    if b"\n" not in buf:
        return buf, None
    line, rest = buf.split(b"\n", 1)
    return rest, line.decode("utf-8", "replace")


def _read_frame(sock, timeout_ms: int) -> str | None:
    """从 socket 读**一整行**；超时 / 断开返回 None（审查 #7：不能只等一次就解析）。"""
    buf = bytearray()
    deadline = time.monotonic() + timeout_ms / 1000
    while b"\n" not in buf:
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0 or not sock.waitForReadyRead(remaining):
            return None
        buf += bytes(sock.readAll())
    return bytes(buf).split(b"\n", 1)[0].decode("utf-8", "replace")


def delegate(argv: list[str]) -> tuple[str, str]:
    """把一条命令交给正在运行的应用执行，返回 `(通道, 输出)`。

    通道见 `decide_channel`；`direct` 时输出为空串（调用方自己执行命令）。

    ⚠ 探测与委派用**同一个连接**：单独再连一次会被应用当成"第二次启动"，
    平白把窗口弹到前台。
    """
    from PySide6.QtNetwork import QLocalSocket

    sock = QLocalSocket()
    sock.connectToServer(SINGLE_INSTANCE_KEY)
    if not sock.waitForConnected(CONNECT_TIMEOUT_MS):
        sock.abort()
        return CHANNEL_DIRECT, ""

    sock.write(encode_request(argv))
    sock.flush()
    line = _read_frame(sock, REPLY_TIMEOUT_MS)      # 累积到换行帧（可能分片）
    sock.disconnectFromServer()
    sock.abort()

    channel = decide_channel(True, line is not None)
    if channel == CHANNEL_REFUSE:
        return channel, REFUSE_MESSAGE
    parsed = decode_reply(line or "")
    if parsed is None:
        # 回复不是合法帧 → 拒绝，**不把原文当结果**（审查 #7）
        return CHANNEL_REFUSE, BAD_REPLY_MESSAGE
    return channel, parsed[1]
