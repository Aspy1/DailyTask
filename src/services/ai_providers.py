"""AI 提供方适配层（Anthropic / OpenAI 兼容端点）。

从 `ai_service.py` 抽出（那个文件超过 800 行上限，Q-A1）。这一层只负责
"把一段对话发出去、把文本拿回来"，不碰 Qt、不碰数据、不做 Agent Loop。

`ai_service` 仍然重新导出这些名字（`DeepSeekProvider` / `REASONING_EFFORT` /
`provider_headers`），所以既有 import 与测试不用改。
"""

import logging
import uuid
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class AIProvider(Protocol):
    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str: ...


class AnthropicProvider:
    def __init__(self, api_key: str) -> None:
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key)

    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text


# 进程级稳定会话 ID：OpenCode Go 要求客户端带一个**稳定**的会话标识，
# 用于路由与 prompt 缓存优化（docs/go「Where can I use it?」）。
_SESSION_ID = uuid.uuid4().hex

# 单次模型请求的超时（秒）。SDK 默认是 10 分钟 —— 端点卡住时用户会干等十分钟
# 且没有任何提示（2026-10-16 实测：用户以为应用卡死）。120s 足够覆盖
# "导入 24 门课"这种长回复（实测 40–58s），超时则给出明确错误。
AI_REQUEST_TIMEOUT = 120

# 让模型**少想多做**：这类"翻译成命令"的任务不需要长篇推理，而推理会把输出预算
# 吃光（实测 8192 全给推理 → content 为空）。只在 OpenCode 端点发这个参数。
REASONING_EFFORT = "none"


def provider_headers(base_url: str) -> dict | None:
    """按端点补充请求头；不需要时返回 None。

    OpenCode Go（`opencode.ai/inference/go/...`）明确要求客户端：

    1. **自报身份**：用自定义 UA（`life-assistant/1.0`），而不是 SDK 默认的
       HTTP 库名（openai-python/httpx 之类）；
    2. 带 `x-opencode-session`：缺了它网关会返回
       `400 MissingSessionID`（实测）。

    DeepSeek 等其它端点不需要，返回 None 保持原样。
    """
    if "opencode.ai" not in base_url:
        return None
    return {"User-Agent": "life-assistant/1.0", "x-opencode-session": _SESSION_ID}


class DeepSeekProvider:
    """OpenAI 兼容端点客户端（DeepSeek / OpenCode Go / 其它兼容服务）。"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 extra_headers: dict | None = None) -> None:
        from openai import OpenAI
        self._base_url = base_url or ""
        self._client = OpenAI(api_key=api_key, base_url=base_url,
                              default_headers=extra_headers or None,
                              timeout=AI_REQUEST_TIMEOUT)

    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        response = self._create(full_messages, model, max_tokens, temperature)
        choice = response.choices[0]
        # 关键诊断：`finish_reason=length` + content 为空 = 推理把输出预算吃光了
        # （2026-10-16 用户报"连续返回空内容"，没有这行日志就只能靠猜）
        usage = getattr(response, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        logger.info("模型返回: finish_reason=%s | 补全 %s（推理 %s）| 提示 %s",
                    choice.finish_reason,
                    getattr(usage, "completion_tokens", "?"),
                    getattr(details, "reasoning_tokens", "?"),
                    getattr(usage, "prompt_tokens", "?"))
        content = choice.message.content or ""
        if not content.strip():
            # ⚠ 推理文本**绝不能**当回答交出去：`InstructionParser.parse()` 会从任意
            # 文本里抽含 `scripts/actions.py` 的行去执行，而推理里常有"比如可以这样
            # 删…"这类**被否决或仅作举例**的命令 —— `actions.py` 只校验格式合法，
            # 校验不了**意图**。空内容交给上层按"没有可执行内容"处理：
            # `_should_continue()` 会要求模型直接输出命令（只重试一次），
            # 仍为空则明确报错（`_EMPTY_REPLY_NOTE`）。
            reasoning = getattr(choice.message, "reasoning_content", "") or ""
            logger.warning("content 为空、推理 %d 字符 —— 推理不进执行通道，按空回复处理",
                           len(reasoning))
        return content

    def _create(self, full_messages: list[dict], model: str,
                max_tokens: int, temperature: float) -> Any:
        """发一次请求。

        OpenCode Go 上 `reasoning_effort="none"` 实测有效：推理 token 归零、
        输出更长（生成命令这种任务不需要长篇思考）。端点若不认这个参数（400），
        自动去掉重试一次，不影响可用性。
        """
        kwargs = {
            "model": model or "deepseek-chat",
            "messages": full_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if "opencode.ai" not in self._base_url:
            return self._client.chat.completions.create(**kwargs)
        try:
            return self._client.chat.completions.create(
                **kwargs, reasoning_effort=REASONING_EFFORT)
        except Exception:  # 端点可能不认这个参数，降级重试
            logger.warning("端点不接受 reasoning_effort=%s，去掉重试", REASONING_EFFORT,
                           exc_info=True)
            return self._client.chat.completions.create(**kwargs)
