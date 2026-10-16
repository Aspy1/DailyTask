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

logger = logging.getLogger(__name__)


# ── System prompt ──────────────────────────────────────────────

SYSTEM_PROMPT_BASE = """你是一个学生时间管理助手。理解用户意图、提取参数、调用脚本。

## 核心规则
1. 回复只使用纯文本，禁止使用 markdown 格式（包括标题、列表、代码块以外的用法）
2. 脚本命令放在 ```sh 代码块中，该代码块不会显示给用户
3. 禁止在自然语言回复中重复脚本命令或执行结果
4. 不编造数据，不删除数据（除非用户明确要求）
5. 每次最多一个 ```sh 代码块，每条命令一行
6. 改数据**只能**通过 `scripts/actions.py`；禁止自己拼 JSON、禁止直接写文件
7. 命令被脚本拒绝时会返回 `ERROR ...`：把原因**如实**告诉用户并请他补充信息，
   不要改写参数反复重试同一条命令（脚本拒绝就是没写任何数据）
8. **一次很多条**的任务（导入整学期课表、批量建作业等）：**分批**处理，
   每轮最多 8 条命令，执行完这批再继续下一批 —— 一次输出太长会被输出上限截断，
   截断后整段命令都作废

## 参数标准化
- 课程名: 提取核心词，脚本自动模糊匹配（"算法课"→匹配算法设计与分析）
- 日期: 统一 YYYY-MM-DD 或 YYYY-MM-DDThh:mm。用户提到具体时间(中午/下午/几点/几点半)时必须保留为Thh:mm格式。"下周日""6月20日""明天"等→计算为实际日期
- 时段: 1=08:30-10:05, 2=10:25-12:00, 3=13:30-15:05, 4=15:25-17:00, 5=18:30-20:05, 6=20:10-21:45
- 金额: 纯数字（不要带 ¥、元、"块"）；分类用 id 或中文名（food=餐饮, transport=交通, study=学习, entertainment=娱乐, shopping=购物, other=其他）
- 课程名/标题不超过 120 字；备注不超过 500 字

## 可用命令（按领域分组，共 7 类：课程表 / 作业 / 考试 / 习惯 / 日程 / 有什么 / 记账）

### 课程表
```sh
python scripts/actions.py add_course --name "课程" --day 1 --weeks "1-16" --slots "3-4" [--location "教学楼" --teacher "老师" --parity odd]
python scripts/actions.py delete_course --id "c_001"
```
day: 1=周一...7=周日。weeks: 起-止（1-16）。slots: 起-止（1-6）。parity: all/odd/even（单双周）。

### 作业
```sh
python scripts/actions.py add_task --course "课程" --title "标题" --due "YYYY-MM-DD"  # 或 YYYY-MM-DDThh:mm
python scripts/actions.py complete_task --id "t_001"
```

### 考试
```sh
python scripts/actions.py add_exam --course "课程" --date "YYYY-MM-DD" [--scope "范围" --location "考场" --notes "备注"]
```

### 习惯
```sh
python scripts/actions.py add_habit --name "习惯" --schedule "daily/1" [--duration 30 --reminder "20:00"]
python scripts/actions.py log_habit --id "h_001"
```
schedule格式: daily/N, weekly/1,3,5, monthly/N。

### 日程（计划）
```sh
python scripts/actions.py add_plan --date "YYYY-MM-DD" --title "标题" --slot 3
python scripts/actions.py replace_plans --date "YYYY-MM-DD" --plans '[{"title":"标题","time_slot":3}]'
python scripts/actions.py delete_plan --date "YYYY-MM-DD" --index 0
```

### 有什么（物品/库存）
添加物品分两步，第一步只查找不添加:
```sh
python scripts/actions.py lookup_item --name "A"
```
系统会自动把查找结果发回，让你判断重复。然后你再回复确认并添加。
```sh
python scripts/actions.py add_item --name "物品名" --category "分类" --quantity N --location "位置" [--tags "标签1,标签2"]
python scripts/actions.py update_item --id "i_001" --location "新位置"
python scripts/actions.py update_item --id "i_001" --quantity N --status "需购"
python scripts/actions.py delete_item --id "i_001"
python scripts/actions.py need_restock
```
分类: 日常消耗品/数码电子/衣物/虚拟品类/其他。数量单位统一用"件"。
移动物品: "把X从A拿到B" → update_item --id "i_xxx" --location "B"

### 记账 / 存钱
```sh
python scripts/actions.py add_expense --amount 12.5 --category food [--note "午饭" --date "YYYY-MM-DD"]
python scripts/actions.py add_saving --amount 30 [--note "自带午饭"]
python scripts/actions.py delete_expense --id "e_001"
python scripts/actions.py expense_summary [--month "2026-10"]
```
支出记 add_expense，存钱记 add_saving（两者是分开的两栏，不要混）。

### 概览与备份
```sh
python scripts/actions.py status  # 今日概览（课/任务/习惯/支出）
python scripts/actions.py list_backups --name "expenses.json"
python scripts/actions.py restore --name "expenses.json" --yes  # 仅用户明确要求恢复时
```

## 关键词 → 命令（判断优先级）
1. 课程表/上课/几点的课/在哪上/单双周/第几周/排课 → add_course（删除用 delete_course）
2. 作业/布置/pre/论文/报告/实验/大作业/提交/DDL/截止 → add_task
3. 做完了/写完了/交了/完成了 → complete_task
4. 考试/期中/期末/小测/考查/补考 → add_exam
5. 习惯/打卡/每天/每周/坚持/连续/签到 → add_habit、log_habit
6. 计划/安排/日程/几点做/提醒我 → add_plan（整段重排用 replace_plans）
7. 物品/存货/库存/还有多少/用完了/没货/该买/放在哪/在哪/挪到/拿到 → add_item、update_item、delete_item、lookup_item、need_restock
8. 花了/买了/支出/记账/消费/多少钱/吃饭花了/打车/话费 → add_expense
9. 存钱/省钱/攒钱/今天没花钱/自带饭/没消费 → add_saving
10. 这个月花了多少/分类统计/预算还剩/超支了吗 → expense_summary
11. 概览/统计/今天有什么/还有多少 → status
12. 天气/气温/多少度/下雨/晴天 → 直接用下文「天气」段回答，**不要调用脚本**
13. 余额/剩余/还剩/额度/多少钱（指卡余额）→ 直接用下文「余额」段回答，**不要调用脚本**

## 数据安全
- 脚本会**严格校验**每个参数：范围错（--day 9、--slots 3-99）、非法日期（2026-02-30）、
  负数金额、拼错的参数名（--titel）都会被拒绝并返回 ERROR，**此时数据没有被修改**。
- 收到 ERROR 时：把原因用自然语言告诉用户，请他补充/纠正信息；不要连续重试。
- `restore` / `list_backups` 是**给用户的手动入口**：除非用户明确说"恢复/回滚"，否则不要调用。
- `delete_*` 只在用户明确要求删除时使用；不确定就先问。

## 天气与日程规划
- 规划日程时参考天气预报。若当天有雨（weathercode 51-67, 80-82, 95-99），在相关日程备注中提醒"记得带伞"
- 若温度超过35°C，提醒"注意防暑"
- 若温度低于0°C，提醒"注意保暖"
- 天气信息已在上下文中提供，直接引用即可
"""



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


def _looks_truncated(text: str) -> bool:
    """回复是否疑似被输出上限截断：代码围栏数量是奇数 = 有开场没收尾。"""
    return text.count("```") % 2 == 1


def _continuation_nudge(text: str, truncated: bool) -> str | None:
    """该不该要求模型"继续"？需要时返回提示语，正常回复返回 None。

    - **空回复**（0 字符）：多半是推理把输出预算吃光（`finish_reason=length`）
      → 明确要求它直接输出命令、别长篇思考；
    - **被截断**（围栏没收尾）→ 要求分批继续。

    非空的普通文本回复**不**续跑：那可能是它在向用户提问（"请提供课表"），
    硬续跑只会把问题刷成 5 遍。
    """
    if not text.strip():
        return ("[系统] 你上一轮没有输出任何内容。请**直接**输出 ```sh 命令块"
                "（每轮最多 8 条），不要长篇思考，也不要只解释。")
    if truncated:
        return ("[系统] 你的回复被输出上限截断了。请**分批**继续："
                "每轮最多 8 条命令，先执行完这批再继续下一批。")
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
        self._client = OpenAI(api_key=api_key, base_url=base_url,
                              default_headers=extra_headers or None,
                              timeout=AI_REQUEST_TIMEOUT)

    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        response = self._client.chat.completions.create(
            model=model or "deepseek-chat",
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
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
        return choice.message.content or ""


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

    def _max_tokens(self) -> int:
        """输出预算：读设置 `AI.max_tokens`（默认 8192）。

        不能太小：这类模型会先花几百到上千 token **推理**，预算不够时
        `finish_reason=length` 而 content 为空（2026-10-16 用户报"连续返回空内容"）。
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
            for turn in range(5):  # max 5 turns
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
                    nudge = _continuation_nudge(text, truncated) if turn < 4 else None
                    if nudge:
                        logger.warning("AI 第 %d 轮没有可执行命令，要求继续", turn + 1)
                        msgs.append({"role": "assistant", "content": text})
                        msgs.append({"role": "user", "content": nudge})
                        final_text = text
                        continue
                    # No tool calls — done
                    if all_instructions:
                        # Instructions were executed in earlier turns
                        self.finished_with_instructions.emit(final_text, all_instructions)
                    else:
                        self.finished.emit(text)
                    return
                all_instructions.extend(instructions)
                # Execute tools silently
                results = InstructionParser.execute(instructions)
                # Feed results back for next turn
                msgs.append({"role": "assistant", "content": text})
                results_text = "\n".join(results)
                msgs.append({"role": "user", "content": f"[工具执行结果]\n{results_text}"})
                final_text = text
            # Max turns reached
            display = re.sub(r'```(?:sh|json)\s*.*?```', '', final_text, flags=re.DOTALL).strip()
            if all_instructions:
                self.finished_with_instructions.emit(display or "已完成", all_instructions)
            else:
                self.finished.emit(display or "已完成")
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


# ── Instruction parser ─────────────────────────────────────────


class InstructionParser:
    """Extract and execute shell commands from AI responses."""

    @staticmethod
    def parse(text: str) -> list[str]:
        """Extract shell commands from ```sh blocks.

        **容忍被 `max_tokens` 截断的块**（没有收尾 ```）：此时仍把已经完整写出的
        命令行交出去执行。理由：每行都要过 `actions.py` 的严格校验，非法行会被拒绝，
        所以"执行完整行"比"整段丢弃"更安全也更有用。
        （2026-10-16 实测：24 门课的导入回复被截断 → 旧实现一行都不执行，
        也不告诉用户，用户看到的就是"AI 没反应"。）
        """
        blocks = re.findall(r'```sh\s*\n?(.*?)(?:```|\Z)', text, re.DOTALL)
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
{self._build_expense_list()}

已有习惯（id 用于修改/推迟/取消）:
{self._build_habit_list()}

余额:
{balance_info}

天气:
{weather_info}

物品库存（id 用于修改/移动）:
{self._build_inventory_list()}

假期/调休:
{self._build_holiday_info()}
"""
        prompt = SYSTEM_PROMPT_BASE + "\n" + context + "\n【输出格式】\n- 纯文本，禁用 markdown。仅可用**加粗**。\n- 禁止输出脚本命令原文和执行结果。\n- 查找发现重复物品时，在该轮回复中告知用户，等待确认后再处理。\n- 完成后用一行简练中文总结操作结果。"
        self._prompt_cache_key = cache_key
        self._prompt_cache_value = prompt
        return prompt

    def _build_expense_list(self) -> str:
        records = sorted(self._dm.expenses.records, key=lambda r: r.get("date", ""), reverse=True)[:20]
        if not records:
            return "  （无支出记录）"
        cat_names = {c["id"]: c["name"] for c in self._dm.expenses.categories}
        lines = []
        for r in records:
            rid = r.get("id", "")
            d = (r.get("date", "") or "")[:10]
            cat = cat_names.get(r.get("category", ""), r.get("category", ""))
            amt = r.get("amount", 0)
            note = r.get("note", "")
            lines.append(f"  [{rid}] {d} {cat} ¥{amt:.1f} {note}")
        return "\n".join(lines)

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

    def _build_inventory_list(self) -> str:
        items = self._dm.inventory.items
        if not items:
            return "  （无物品记录）"
        lines = []
        for it in items:
            loc = it.get("location", "")
            loc_str = f" [{loc}]" if loc else ""
            tags = it.get("tags", [])
            tag_str = f" ({','.join(tags)})" if tags else ""
            lines.append(f"  [{it['id']}] {it['name']} {it['quantity']}{it['unit']}{loc_str} - {it['status']}{tag_str}")
        return chr(10).join(lines)

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
        # Strip code blocks
        display = re.sub(r'```(?:sh|json)\s*.*?```', '', text, flags=re.DOTALL).strip()
        if not display and not text.strip():
            # 空回复（常见于推理吃满 token 或输出被截断）必须**说出来**，
            # 否则界面是一片空白，用户只会以为"AI 没反应"（2026-10-16 实测）
            logger.warning("AI 返回空内容")
            display = "（模型这次没有返回内容，请重试；导入大量课程时请分批发给我）"
        self.response_received.emit(display or text)

    def _on_response_with_instructions(self, text: str, instructions: list) -> None:
        self._history.append({"role": "assistant", "content": text})
        n = len(instructions) if instructions else 0
        logger.info("AI completed with %d instructions executed by worker", n)

        # 数据重载与变更通知放在**主线程**（worker 线程不再触碰 Model，见 Q-B2）
        if instructions:
            self._dm.reload_all()
            self._dm.data_changed.emit("ai_action")

        # Strip code blocks from display text — keep only natural language
        display_text = re.sub(r'```(?:sh|json)\s*.*?```', '', text, flags=re.DOTALL).strip()
        if not display_text:
            display_text = re.sub(r'```(?:sh|json)?\s*.*?```', '', text, flags=re.DOTALL).strip()

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
