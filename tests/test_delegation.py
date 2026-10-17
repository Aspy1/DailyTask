"""CLI 委派给应用（`PLAN.md` P17 阶段 3）：通道决策 + 协议编解码。

风险点是**通道决策**（连不上/连上没回应各走哪条路）与**参数原样送达**（命令里带空格、
中文时不能拆错）—— 这两块做成纯函数，正好在这里钉住。
"""

import pytest

from src.services.single_instance import (
    CHANNEL_DELEGATE,
    CHANNEL_DIRECT,
    CHANNEL_REFUSE,
    decide_channel,
    decode_reply,
    decode_request,
    encode_reply,
    encode_request,
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
    assert decode_reply(encode_reply(True, "OK 已添加").decode().strip()) == "OK 已添加"


def test_bad_reply_is_none() -> None:
    assert decode_reply("garbage") is None
