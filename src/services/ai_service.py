"""AI service with pluggable backends (Anthropic, DeepSeek)."""

import logging
import re
import threading
import time
import uuid
from datetime import date
from typing import Any, Protocol

from PySide6.QtCore import QObject, QThread, Signal

from src.services import deepseek, openmeteo
from src.services.ai_prompts import (
    SYSTEM_PROMPT_BASE,
    expense_prompt,
)

logger = logging.getLogger(__name__)





# ── Provider interface ─────────────────────────────────────────

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


def _looks_truncated(text: str) -> bool:
    """回复是否疑似被输出上限截断：代码围栏数量是奇数 = 有开场没收尾。"""
    return text.count("```") % 2 == 1


def _strip_code_blocks(text: str) -> str:
    """去掉代码块，只留自然语言（显示给用户用）。

    围栏语言标记要放宽：模型常写 ```bash / ```shell，只认 ```sh 会把命令漏给用户看
    （2026-10-17 实测：用户看到的"奇怪代码"就是这么漏出来的）。
    """
    return re.sub(r'```(?:sh|bash|shell|console|zsh|json)\s*.*?```', '',
                  text, flags=re.DOTALL).strip()


# 空回复的**明确失败**文案：模型只输出推理（或什么都没给）时用。
# 服务层沿用既有做法直接 emit 文案（与 `self.error.emit(str(e))` 一致）。
_EMPTY_REPLY_NOTE = ("模型没有返回可执行内容（推理可能占满了输出预算）。"
                     "请重试，或提高设置里的 AI.max_tokens。")


def _looks_like_tool_call(text: str) -> bool:
    """模型是否改用了"工具调用"格式（本项目**不解析**它）。

    2026-10-18 探针实测：模型偶尔输出 `<｜｜DSML｜｜ invoke name="add_item">…<｜｜DSML｜｜ parameter …>`
    —— `InstructionParser` 只认 ```sh 代码块，于是那一轮**什么都不做**（用户看起来就是
    "AI 没反应"）。这里识别出来，好让上层明确纠正格式。
    """
    return "invoke name=" in text or "<｜" in text or "｜>" in text


def _has_write_cmd(commands: list) -> bool:
    """这批命令里有没有**写操作**（纯查询不算）。"""
    names = [str(c).split("actions.py", 1)[-1].strip().split()[:1] for c in commands]
    return any(n and n[0] not in ("lookup_item", "need_restock", "status") for n in names)


def _state_fingerprint() -> str:
    """**从磁盘**算「库存 + 日程」的指纹 —— 这一轮到底有没有**真的改动**（不看模型怎么说）。"""
    import hashlib
    import json as _json

    import scripts.actions_core as core

    blob = _json.dumps([core.load(n) for n in ("inventory.json", "daily_logs.json")],
                       sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _claims_done(text: str) -> bool:
    """模型是不是在**声称已经写入**（"已记录 / 已录入 / 已更新"…）。

    2026-10-18 α 实测：模型有时只说"已记录：毛巾 2 条…"却**一条命令都没发** —— 数据其实没变 ✗。
    """
    return any(m in text for m in ("已记录", "已录入", "已更新", "已加入", "已新增", "已保存"))


def _continuation_nudge(text: str, truncated: bool, empty_retries: int = 0,
                        wrote_data: bool = False) -> str | None:
    """该不该要求模型"继续"？需要时返回提示语，正常回复返回 None。

    空回复 / 被截断 / **声称写了却没命令** / **说"无需写入"却一条都没执行** 都要续跑；
    非空的普通提问**不**续跑（否则会把问题刷 5 遍）。
    """
    if not text.strip():
        if empty_retries >= 1:
            return None
        return ("[系统] 你上一轮没有输出任何内容。请**直接**输出 ```sh 命令块"
                "（每轮最多 8 条），不要长篇思考，也不要只解释。")
    if _looks_like_tool_call(text):
        # 模型改用了"工具调用"格式（`<｜｜DSML｜｜ invoke name=…>` 之类）→ 解析器认不出，
        # 等于什么都没做。明确纠正格式，只纠正一次（2026-10-18 探针实测遇到）
        if empty_retries >= 1:
            return None
        return ("[系统] 你用的是**工具调用格式**，本项目不解析它。请改用 ```sh 代码块，"
                "每行一条 `python scripts/actions.py …` 命令。")
    if truncated:
        return ("[系统] 你的回复被输出上限截断了。请**分批**继续："
                "每轮最多 8 条命令，先执行完这批再继续下一批。")
    if _claims_done(text) and not wrote_data:
        # 声称"已记录"却没有命令 → 数据其实**没变**（2026-10-18 α 实测 ✗）
        if empty_retries >= 2:
            return None
        return ("[系统] 你说了\"已记录/已完成\"，但这一轮**没有任何命令** —— 数据不会变。请**立刻**"
                "输出 ```sh 命令块（先发命令再说话）；只有之前真的执行过命令，才可以回\"无需写入\"。")
    if "无需写入" in text and not wrote_data:
        # ⚠ 真实数据实测：模型先说"已记录"、被追问后改口"无需写入"，该记的**根本没落库**
        if empty_retries >= 2:
            return None
        return ("[系统] 你说\"无需写入\"，但**本次请求到现在一条命令都没执行过**。如果用户"
                "这句话里有要记 / 要改的东西，请**立刻**输出 ```sh 命令块。")
    return None


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
            # `_handle_no_instructions()` 会要求模型直接输出命令（只重试一次），
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


# ── Worker ─────────────────────────────────────────────────────

class AIWorker(QObject):
    finished = Signal(str)
    error = Signal(str)
    finished_with_instructions = Signal(str, list)

    def __init__(self, provider: AIProvider, model: str, system_prompt: str,
                 messages: list, dm=None, settings=None, parent=None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._model = model
        self._system_prompt = system_prompt
        self._messages = messages
        self._dm = dm
        self._settings = settings

    def _max_seconds(self) -> float:
        """整次请求的**墙钟上限**（读 `AI.max_seconds`，默认 90s）。到点优雅收尾。"""
        raw = self._settings.get("AI", "max_seconds", "90") if self._settings else "90"
        try:
            return max(10.0, float(raw))
        except (TypeError, ValueError):
            return 90.0

    def _max_tokens(self) -> int:
        """输出预算：读设置 `AI.max_tokens`（默认 8192）。太小会因推理占满而返回空内容。
        """
        raw = self._settings.get("AI", "max_tokens", "8192") if self._settings else "8192"
        try:
            return max(512, min(int(raw), 32768))
        except (TypeError, ValueError):
            return 8192

    def run(self) -> None:
        try:
            msgs = list(self._messages)
            final_text = ""
            all_instructions = []  # collect across multi-turn agent loop
            max_tokens = self._max_tokens()
            wrote_data = False     # **数据真的变了**才算（不是"发过命令"）
            deadline = time.monotonic() + self._max_seconds()
            for turn in range(5):  # max 5 turns
                if time.monotonic() > deadline:
                    logger.warning("AI 总时限到，优雅收尾（已执行 %d 条命令）", len(all_instructions))
                    break
                started = time.monotonic()
                text = self._provider.chat(
                    system_prompt=self._system_prompt,
                    messages=msgs,
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=0.3,
                )
                # 生命周期日志：用户会盯着日志等结果（"怎么没有 200 OK"），
                # 这里把"第几轮 / 耗时 / 是否疑似截断 / 解析出几条命令"都写清楚。
                truncated = _looks_truncated(text)
                logger.info("AI turn %d: %.1fs | %d 字符 | 疑似截断=%s | 命令=%d",
                            turn + 1, time.monotonic() - started, len(text), truncated,
                            len(InstructionParser.parse(text)))
                instructions = InstructionParser.parse(text)
                if not instructions:
                    if self._handle_no_instructions(text, truncated, msgs, turn,
                                                    all_instructions, wrote_data):
                        final_text = text
                        continue
                    return
                all_instructions.extend(instructions)
                # Execute tools silently
                before = _state_fingerprint()
                results = InstructionParser.execute(instructions)
                changed = _state_fingerprint() != before
                wrote_data = wrote_data or changed
                # Feed results back for next turn
                msgs.append({"role": "assistant", "content": text})
                results_text = "\n".join(results)
                if not changed:
                    # 给模型一条**事实**（不是指令）：命令跑了但世界没变
                    results_text += ("\n[事实] 命令已执行，但**库存/日程没有任何变化**"
                                     "（被拒或报错了）。")
                msgs.append({"role": "user", "content": f"[工具执行结果]\n{results_text}"})
                final_text = text
            # Max turns reached
            display = re.sub(r'```(?:sh|json)\s*.*?```', '', final_text, flags=re.DOTALL).strip()
            self._finish(all_instructions, wrote_data, display)
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))

    def _finish(self, all_instructions: list, wrote_data: bool, display: str) -> None:
        if all_instructions:
            if not wrote_data and _has_write_cmd(all_instructions):
                # ⭐ 汇报权**永远**归代码：写了命令却一点没变 → 必须告诉用户，
                # 不管模型嘴上说什么（Agent Reliability §2.3；bonsai 实测正是这种）
                display += ("\n\n⚠ **数据没有任何改动** —— 命令执行了但没生效"
                            "（可能被拒或报错），请重试或换个说法。")
            self.finished_with_instructions.emit(display or "已完成", all_instructions)
        elif display:
            self.finished.emit(display)
        else:
            self.error.emit(_EMPTY_REPLY_NOTE)

    def _handle_no_instructions(self, text: str, truncated: bool, msgs: list,
                                turn: int, all_instructions: list,
                                wrote_data: bool = False) -> bool:
        """这一轮没有可执行命令：要么要求模型继续（返回 True），要么收尾（返回 False）。

        `wrote_data` = **数据是否真的变过**（不是"发过命令"），由调用方从磁盘指纹算出。
        """
        empty_retries = sum(1 for m in msgs
                            if m["role"] == "user" and "[系统]" in str(m["content"]))
        nudge = _continuation_nudge(text, truncated, empty_retries, wrote_data) if turn < 4 else None
        if nudge:
            logger.warning("AI 第 %d 轮没有可执行命令，要求继续", turn + 1)
            msgs.append({"role": "assistant", "content": text})
            msgs.append({"role": "user", "content": nudge})
            return True
        if all_instructions:
            # 前几轮执行过命令 → 走"执行完成"路径（带上汇总文本）
            self.finished_with_instructions.emit(text or _EMPTY_REPLY_NOTE, all_instructions)
        elif text.strip():
            self.finished.emit(text)
        else:
            # 空回复 = **失败**，不是"完成"（此前会把推理文本当回答显示并执行）
            self.error.emit(_EMPTY_REPLY_NOTE)
        return False


# ── Instruction parser ─────────────────────────────────────────


class InstructionParser:
    """Extract and execute shell commands from AI responses."""

    @staticmethod
    def parse(text: str) -> list[str]:
        """从 ```sh 块里抽命令。**容忍被截断的块**（围栏没收尾）—— 完整行仍交出去执行：
        每行都过 `actions.py` 的严格校验，所以"执行完整行"比"整段丢弃"更安全
        （2026-10-16：截断导致一行都不执行，用户看到"AI 没反应"）。
        """
        blocks = re.findall(r'```(?:sh|bash|shell|console|zsh)\s*\n?(.*?)(?:```|\Z)',
                            text, re.DOTALL)
        commands = []
        for block in blocks:
            for line in block.strip().split('\n'):
                line = line.strip()
                if line and 'scripts/actions.py' in line:
                    commands.append(line)
        return commands

    @staticmethod
    def execute(commands: list[str]) -> list[str]:
        """在**内存中**执行 actions.py 命令，返回每条命令的输出。

        ⚠ 本方法运行在 AI worker 线程：**不得触碰 Model、不得 emit 信号**。
        数据重载与通知由主线程的 `AIService._on_response_with_instructions` 负责
        （CODE_STANDARDS Q-B2 / Q-B4）。
        """
        try:
            from scripts.actions import run_in_process
        except ImportError as e:  # 仅项目结构异常时可能发生
            return [f"ERROR 无法加载 scripts/actions.py: {e}"] * len(commands)
        results = []
        for cmd in commands:
            try:
                results.append(run_in_process(cmd))
            # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
            except Exception as e:  # noqa: BLE001
                results.append(f"ERROR {e}")
        return results


def _inventory_prompt(inventory) -> str:
    """（已并入 `ai_prompts.inventory_prompt`。）"""
    from src.services.ai_prompts import inventory_prompt

    return inventory_prompt(inventory)


class AIService(QObject):
    response_received = Signal(str)
    error_occurred = Signal(str)
    instructions_executed = Signal(str, list)

    def __init__(self, settings, data_manager, weather_service=None, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._dm = data_manager
        self._weather_service = weather_service  # 天气服务
        self._history: list[dict] = []
        self._thread: QThread | None = None
        self._worker: AIWorker | None = None
        # 实例级缓存（原为类属性 → 跨实例共享可变状态，见 CODE_STANDARDS Q-B2 / RUF012）
        self._ds_balance_cache: dict[str, Any] = {}
        self._weather_cache: dict[str, Any] = {}
        self._context_warming = False

    def set_weather_service(self, weather_service) -> None:
        """设置天气服务"""
        self._weather_service = weather_service

    def _make_provider(self) -> AIProvider:
        provider = self._settings.get("AI", "provider", "deepseek")
        api_key = self._settings.api_key
        if provider == "claude":
            return AnthropicProvider(api_key)
        base_url = self._settings.get("AI", "api_endpoint", "https://api.deepseek.com")
        return DeepSeekProvider(api_key, base_url, provider_headers(base_url))

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.api_key)

    def send_message(self, text: str) -> None:
        if not self.is_configured:
            self.error_occurred.emit("未配置 API 密钥，请在设置中填写。")
            return
        self._auto_continue_count = 0
        self._history.append({"role": "user", "content": text})
        self._auto_compress()
        self._send_to_ai()

    def _send_to_ai(self) -> None:
        system_prompt = self._build_system_prompt()
        try:
            provider = self._make_provider()
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            self.error_occurred.emit(f"创建 AI 连接失败: {e}")
            return
        model = self._settings.get("AI", "model", "deepseek-chat")
        self._thread = QThread()
        self._worker = AIWorker(
            provider=provider, model=model,
            system_prompt=system_prompt,
            messages=list(self._history),
            dm=self._dm, settings=self._settings,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_response)
        self._worker.error.connect(self._on_error)
        self._worker.finished_with_instructions.connect(self._on_response_with_instructions)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._worker.finished_with_instructions.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._worker.finished_with_instructions.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _fetch_deepseek_balance(self) -> str:
        """DeepSeek 余额文本（5 分钟缓存）。非 DeepSeek 端点直接返回空串。

        格式化与请求都交给共享适配器 `services/deepseek.py`（Q-A3）。
        """
        import time

        now = time.time()
        cached = self._ds_balance_cache
        if cached and (now - cached.get("fetched_at", 0)) < 300:
            return cached.get("value", "")
        # 余额是 DeepSeek 专属接口：换到其它 OpenAI 兼容端点（如 OpenCode Go）时
        # 不要拿别的 key 去查 DeepSeek 余额（提示词里也就不会出现「余额」段）。
        val = (deepseek.balance_text(self._settings.api_key)
               if self._settings.get("AI", "provider", "deepseek") == "deepseek" else "")
        self._ds_balance_cache = {"value": val, "fetched_at": now}
        return val

    def _fetch_weather_for_prompt(self, allow_service: bool = True) -> str:
        """获取天气信息用于系统提示词。

        `allow_service=False` 时只走 Open-Meteo（后台预热线程用：不触碰
        主线程属主的 WeatherService）。
        """
        import time
        now = time.time()
        cached = self._weather_cache
        if cached and (now - cached.get("fetched_at", 0)) < 300:
            return cached.get("value", "  天气信息暂不可用")

        # 优先使用WeatherService
        val = self._weather_from_service() if allow_service else None
        if val is None:
            # 回退到Open-Meteo（保留旧逻辑作为备用）
            val = self._weather_from_open_meteo()
        self._weather_cache = {"value": val, "fetched_at": now}
        return val

    def _weather_from_service(self) -> str | None:
        """经 WeatherService 获取天气文本；未配置或失败返回 None。"""
        if not self._weather_service:
            return None
        try:
            return self._weather_service.get_weather_text_for_ai()
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            logger.warning(f"WeatherService获取天气失败: {e}")
            return None

    def _weather_from_open_meteo(self) -> str:
        """回退方案：经**共享**的 Open-Meteo 适配器取天气文本。

        Q-A3：此前这里是内联的 `requests.get` + 自带一份天气码映射（第三套实现），
        现已收拢到 `src/services/openmeteo.py`（唯一实现）。
        """
        try:
            lat = float(self._settings.get("Weather", "lat", "31.23"))
            lon = float(self._settings.get("Weather", "lon", "121.47"))
        except (ValueError, TypeError):
            lat, lon = openmeteo.DEFAULT_LAT, openmeteo.DEFAULT_LON
        return openmeteo.fetch_text_for_ai(lat, lon)

    def _compute_prompt_cache_key(self, today: date) -> tuple:
        """提示词轻量缓存键：数据形状 + 天气缓存时间戳。"""
        weather_ts = self._weather_cache.get("fetched_at", 0) if hasattr(self, '_weather_cache') else 0
        return (
            today.isoformat(),
            len(self._dm.courses.courses),
            len(self._dm.daily_logs._data.get("plans", {})),
            len(self._dm.tasks.active),
            len(self._dm.habits.habits),
            len(self._dm.expenses.records),
            len(self._dm.inventory.items),
            self._dm.expenses.budget.get("monthly", 0),
            int(weather_ts),  # 包含天气缓存时间戳
        )

    def _build_course_list(self, weekday_names: list[str]) -> str:
        """课程清单（用于系统提示词）。"""
        course_lines = []
        for c in self._dm.courses.courses:
            day = c.get("day_of_week", 0)
            day_str = weekday_names[day - 1] if 1 <= day <= 7 else "?"
            weeks = c.get("weeks", {})
            w_str = f"第{weeks.get('start','?')}-{weeks.get('end','?')}周" if weeks else ""
            course_lines.append(f"  - {c.get('name','')} ({day_str} {w_str})")
        return "\n".join(course_lines) if course_lines else "  （无课程）"

    def _build_plan_list(self) -> str:
        """日程计划清单（最近10天，方括号内为 delete_plan 的 index）。"""
        plan_lines = []
        all_plans = self._dm.daily_logs._data.get("plans", {})
        for day_str in sorted(all_plans.keys())[:10]:
            plans = all_plans[day_str]
            for i, p in enumerate(plans):
                plan_lines.append(f"  [{i}] {day_str} 时段{p.get('time_slot','?')} — {p.get('title','')} ({p.get('course_name','')})")
        return "\n".join(plan_lines) if plan_lines else "  （无日程计划）"

    def _build_balance_info(self) -> str:
        """余额清单：校园卡/水卡/电费 + DeepSeek API（API 余额只读缓存）。"""
        balance_lines = []
        for key, label in [("campus_card", "校园卡"), ("water_card", "水卡"), ("electricity", "电费")]:
            bal = self._settings.get("Balance", f"{key}_balance")
            thr = self._settings.get("Balance", f"{key}_threshold")
            if bal:
                b = f"¥{bal}"
                b += f" (低于{thr}元提醒)" if thr else ""
            else:
                b = "未设置"
            balance_lines.append(f"  {label}: {b}")
        # DeepSeek API 余额：只读缓存，网络预热在后台线程（Q-C2）
        ds_balance = self._ds_balance_cache.get("value", "")
        if ds_balance:
            balance_lines.append(f"  DeepSeek API: {ds_balance}")
        return "\n".join(balance_lines)

    def _warm_context_cache(self) -> None:
        """后台线程预热余额 / 天气上下文，避免主线程同步网络请求（CODE_STANDARDS Q-C2）。

        构建系统提示词的路径**不允许**发网络请求：有 API key 时至少 5s 超时，
        会卡住 UI（原来是主线程 `requests.get`）。这里用一次性守护线程预热，
        构建时只读缓存；首次预热完成前的 prompt 就用空值，下一条消息即为实时值。
        """
        if self._context_warming:
            return
        self._context_warming = True

        def work() -> None:
            try:
                if self.is_configured:
                    self._fetch_deepseek_balance()
                # 不碰 WeatherService（QObject 属主在主线程），只用 Open-Meteo 兜底
                self._fetch_weather_for_prompt(allow_service=False)
            except Exception:
                logger.debug("上下文预热失败", exc_info=True)
            finally:
                self._context_warming = False

        threading.Thread(target=work, name="ai-context-warmup", daemon=True).start()

    def _weather_context_for_prompt(self) -> str:
        """天气文本：优先 WeatherService（本地缓存），否则用预热结果。"""
        text = self._weather_from_service()
        if text:
            return text
        self._warm_context_cache()
        return self._weather_cache.get("value", "  天气信息暂不可用")

    def _build_system_prompt(self) -> str:
        today = date.today()
        # Lightweight cache: skip rebuild if data shape hasn't changed today
        cache_key = self._compute_prompt_cache_key(today)
        if getattr(self, '_prompt_cache_key', None) == cache_key:
            return self._prompt_cache_value

        summary = self._dm.get_today_summary()
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[today.weekday()]

        course_list = self._build_course_list(weekday_names)
        plan_list = self._build_plan_list()
        balance_info = self._build_balance_info()

        # 获取天气信息（本地缓存；网络预热在后台线程）
        weather_info = self._weather_context_for_prompt()

        context = f"""当前日期: {today.isoformat()} {weekday}
当前学期: {self._dm.courses.current_semester or '未设置'}
当前第{self._get_current_week()}周 ({self._get_week_parity()})
单双周课程: {self._build_parity_hint()}

已导入的课程:
{course_list}

日程计划（最近10天，方括号内为delete_plan所需的index）:
{plan_list}

今日课程: {len(summary['today_courses'])} 节
待完成任务: {summary['pending_tasks']} 个
待核销习惯: {summary['pending_habits']} 个
今日支出: ¥{summary['today_expense']:.2f}（{len([r for r in self._dm.expenses.records if r.get('date','') == today.isoformat()])} 条）
本月支出: ¥{self._dm.expenses.month_total():.2f} / 预算 ¥{self._dm.expenses.budget.get('monthly', 0):.0f}

最近支出（按支出日期 date 字段排列，非记录时间）:
{expense_prompt(self._dm.expenses)}

已有习惯（id 用于修改/推迟/取消）:
{self._build_habit_list()}

余额:
{balance_info}

天气:
{weather_info}

物品库存（id 用于修改/移动）:
{_inventory_prompt(self._dm.inventory)}

假期/调休:
{self._build_holiday_info()}
"""
        prompt = SYSTEM_PROMPT_BASE + "\n" + context + "\n【输出格式】\n- 纯文本，禁用 markdown。仅可用**加粗**。\n- 禁止输出脚本命令原文和执行结果。\n- ⚠ 要执行操作时**只能**输出 ```sh 代码块（每行一条 `python scripts/actions.py …`）。\n  禁止输出任何**工具调用 / 函数调用**格式（例如 `<｜｜DSML｜｜ invoke name=…>`、`<｜｜DSML｜｜ parameter …>`、\n  XML/JSON 包裹的 invoke/parameter）—— 那些不会被解析，等于什么都没做。\n- 查找发现重复物品时，在该轮回复中告知用户，等待确认后再处理。\n- 完成后用一行简练中文总结操作结果。"
        self._prompt_cache_key = cache_key
        self._prompt_cache_value = prompt
        return prompt

    def _build_habit_list(self) -> str:
        habits = self._dm.habits.habits
        if not habits:
            return "  （无习惯）"
        day_names = ["一", "二", "三", "四", "五", "六", "日"]
        lines = []
        for h in habits:
            sched = h.get("schedule", {})
            if sched.get("type") == "weekly":
                days = sched.get("days", [])
                s = "每周" + "".join(day_names[d - 1] for d in sorted(days))
            else:
                s = f"每{sched.get('value', 1)}天"
            rt = h.get("reminder_time", "")
            rt_str = f" {rt}" if rt else ""
            pu = h.get("postpone_until", "")
            pu_str = f" [推迟至{pu[:10]}]" if pu else ""
            lines.append(f"  [{h['id']}] {h.get('name','')} ({s}{rt_str}){pu_str}")
        return "\n".join(lines)

    def _get_current_week(self) -> int:
        """当前教学周（**唯一口径**见 `models/semester.py`）；未知时按第 1 周。

        此前这里遍历 `semesters` 取**第一个**、且忽略 `current_semester` ——
        多个学期时 AI 提示词里的"第 N 周 / 单双周"会算错。
        """
        return self._dm.courses.current_week() or 1

    def _get_week_parity(self) -> str:
        return "单周" if self._get_current_week() % 2 == 1 else "双周"

    def _build_parity_hint(self) -> str:
        lines = []
        day_names = ["周一","周二","周三","周四","周五","周六","周日"]
        for c in self._dm.courses.courses:
            parity = c.get("week_parity", "all")
            if parity != "all":
                day = c.get("day_of_week", 0)
                day_str = day_names[day-1] if 1 <= day <= 7 else "?"
                lines.append(f"  {c.get('name','')}: {day_str} {parity}周")
        return chr(10).join(lines) if lines else "  (无)"

    def _build_holiday_info(self) -> str:
        h = self._dm.courses.holidays
        excluded = h.get("excluded", [])
        makeup = h.get("makeup", {})
        if not excluded and not makeup:
            return "  （无）"
        lines = []
        if excluded:
            lines.append(f"  假期: {', '.join(sorted(excluded))}")
        if makeup:
            dn = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            for d in sorted(makeup.keys()):
                dow = makeup[d]
                lines.append(f"  调休: {d} 按{dn[dow] if 1 <= dow <= 7 else '?'}课表")
        return "\n".join(lines)

    def _on_response(self, text: str) -> None:
        self._history.append({"role": "assistant", "content": text})
        display = _strip_code_blocks(text)
        if not display and not text.strip():
            # 空回复（常见于推理吃满 token 或输出被截断）必须**说出来**，
            # 否则界面是一片空白，用户只会以为"AI 没反应"（2026-10-16 实测）
            logger.warning("AI 返回空内容")
            display = ("（模型这次没有输出内容 —— 通常是它把输出预算全用在思考上了。"
                       "可以直接重试；若反复出现，请在 设置 → AI 里换一个模型）")
        self.response_received.emit(display or text)

    def _on_response_with_instructions(self, text: str, instructions: list) -> None:
        self._history.append({"role": "assistant", "content": text})
        n = len(instructions) if instructions else 0
        logger.info("AI completed with %d instructions executed by worker", n)

        # 数据重载与变更通知放在**主线程**（worker 线程不再触碰 Model，见 Q-B2）
        if instructions:
            self._dm.reload_all()
            self._dm.data_changed.emit("ai_action")

        # 只把自然语言显示给用户（代码块里的命令不进聊天记录）
        display_text = _strip_code_blocks(text)

        summary = f"已执行 {n} 条指令" if n else text
        self.instructions_executed.emit(display_text or summary, instructions)

    def _on_error(self, error_msg: str) -> None:
        logger.error("AI error: %s", error_msg)
        self.error_occurred.emit(error_msg)

    def clear_history(self) -> None:
        self._history = []

    def _auto_compress(self) -> None:
        """Keep history at a reasonable size — last 16 messages (~8 exchanges)."""
        if len(self._history) <= 16:
            return
        kept = self._history[-16:]
        summary = "（之前的对话已被压缩。用户进行了日程管理、数据操作等。）"
        self._history = [{"role": "user", "content": summary}, *kept]
        logger.info("Context compressed to %d messages", len(self._history))

    def compress_context(self) -> None:
        """Manual compress — keep only the last 10 exchanges."""
        self._auto_compress()
