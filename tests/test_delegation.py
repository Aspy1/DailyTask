"""CLI 委派给应用（`PLAN.md` P17 阶段 3 / 审查 #7）：通道决策 + 编解码 + **分帧**。

三个风险点：通道决策（连不上 / 连上没回应各走哪条路）、参数原样送达、
以及**字节流分帧** —— 本地 socket 不是消息流，一次读可能只有半帧。
"""

import subprocess
import sys
import time

import pytest
from PySide6.QtNetwork import QLocalServer

from src.services.single_instance import (
    CHANNEL_DELEGATE,
    CHANNEL_DIRECT,
    CHANNEL_REFUSE,
    SINGLE_INSTANCE_KEY,
    decide_channel,
    decode_reply,
    decode_request,
    encode_reply,
    encode_request,
    feed_buffer,
)


@pytest.mark.parametrize(("connected", "replied", "expected"), [
    (False, False, CHANNEL_DIRECT),      # 应用没跑 → CLI 自己写文件
    (True, True, CHANNEL_DELEGATE),      # 应用在跑且回应 → 交给它执行
    (True, False, CHANNEL_REFUSE),       # 连上但没回应（旧版本）→ 拒绝，不静默直写
])
def test_decide_channel(connected: bool, replied: bool, expected: str) -> None:
    assert decide_channel(connected, replied) == expected


def test_request_roundtrip_keeps_arguments_with_spaces() -> None:
    """参数里有空格 / 中文也必须原样送达 —— 这正是"传 argv 而不是命令串"的原因。"""
    argv = ["add_item", "--name", "抽纸 一提", "--quantity", "3"]
    assert decode_request(encode_request(argv).decode().strip()) == argv


@pytest.mark.parametrize("bad", ["not json", '{"nope": 1}', '{"argv": "x"}', "[]"])
def test_bad_request_is_rejected(bad: str) -> None:
    """非法请求返回 None（服务端回错误，不崩）。"""
    assert decode_request(bad) is None


def test_reply_roundtrip() -> None:
    assert decode_reply(encode_reply(True, "OK 已添加").decode().strip()) == (True, "OK 已添加")


@pytest.mark.parametrize("bad", [
    "garbage",                       # 不是 JSON
    "[]",                            # 不是对象
    '{"ok": 1, "out": "x"}',         # ok 不是 bool
    '{"ok": true}',                  # 缺 out
    '{"ok": true, "out": 5}',        # out 不是 str
])
def test_bad_reply_is_rejected(bad: str) -> None:
    """结构不对 → None，调用方必须**拒绝**，不能把原文当结果（审查 #7）。"""
    assert decode_reply(bad) is None


# ── 分帧（审查 #7）──────────────────────────────────────────

def test_feed_buffer_waits_for_full_line() -> None:
    """半帧不解析、凑齐换行才给出一行；多余的留在缓冲里等下一次。"""
    buf, line = feed_buffer(b"", b'{"argv": ["st')
    assert line is None
    assert buf == b'{"argv": ["st'

    buf, line = feed_buffer(buf, b'atus"]}\n')
    assert line == '{"argv": ["status"]}'
    assert buf == b""

    buf, line = feed_buffer(b"", b"a\nb\n")
    assert line == "a"
    assert buf == b"b\n", "第二行要留在缓冲里"


def test_delegate_end_to_end_assembles_fragmented_reply(qapp) -> None:
    """**真实 socket + 真 CLI 子进程**：服务端分两次写应答 → CLI 必须拼成完整帧。

    客户端放在独立进程里（就像真的 `scripts/actions.py`）—— 纯 Python 线程没有 Qt 事件
    分发器，`waitForReadyRead` 在那种线程里不工作（本轮踩过）。主线程扮演服务端，
    用事件循环驱动读取。

    用 `status`（只读）当命令：委派成功时它由"应用"执行，**不会**落到真实数据上。
    """
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    server = QLocalServer()
    assert server.listen(SINGLE_INSTANCE_KEY), "测试用监听起不来"
    payload = encode_reply(True, "OK 分片回复")

    proc = subprocess.Popen([sys.executable, "scripts/actions.py", "status"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    conn = None
    for _ in range(200):                     # 等服务端接到连接
        qapp.processEvents()
        if server.hasPendingConnections():
            conn = server.nextPendingConnection()
            break
        time.sleep(0.02)
    assert conn is not None, "CLI 没连上来"
    for _ in range(50):                      # 等请求到达
        qapp.processEvents()
        if bytes(conn.readAll()):
            break
        time.sleep(0.02)

    conn.write(payload[:4])                  # 先发半帧
    conn.flush()
    for _ in range(5):                       # 让客户端确实先收到这半帧
        qapp.processEvents()
        time.sleep(0.02)
    conn.write(payload[4:])                  # 再发剩下的
    conn.flush()

    out, _err = proc.communicate(timeout=20)
    server.close()
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)

    assert out.strip() == "OK 分片回复", f"分片必须被拼成完整帧，实际：{out!r}"
