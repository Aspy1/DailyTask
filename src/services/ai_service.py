"""AI service with pluggable backends (Anthropic, DeepSeek)."""

import logging
import re
import threading
from datetime import date
from typing import Any, Protocol

from PySide6.QtCore import QObject, QThread, Signal

from src.services import deepseek, openmeteo

logger = logging.getLogger("ai_service")


# ── System prompt ──────────────────────────────────────────────

SYSTEM_PROMPT_BASE = """你是一个学生时间管理助手。理解用户意图、提取参数、调用脚本。

## 核心规则
1. 回复只使用纯文本，禁止使用 markdown 格式（包括标题、列表、代码块以外的用法）
2. 脚本命令放在 ```sh 代码块中，该代码块不会显示给用户
3. 禁止在自然语言回复中重复脚本命令或执行结果
4. 不编造数据，不删除数据（除非用户明确要求）
5. 每次最多一个 ```sh 代码块，每条命令一行

## 参数标准化
- 课程名: 提取核心词，脚本自动模糊匹配（"算法课"→匹配算法设计与分析）
- 日期: 统一 YYYY-MM-DD 或 YYYY-MM-DDThh:mm。用户提到具体时间(中午/下午/几点/几点半)时必须保留为Thh:mm格式。"下周日""6月20日""明天"等→计算为实际日期
- 时段: 1=08:30-10:05, 2=10:25-12:00, 3=13:30-15:05, 4=15:25-17:00, 5=18:30-20:05, 6=20:10-21:45

## 可用命令
```sh
python scripts/actions.py add_task --course "课程" --title "标题" --due "YYYY-MM-DD"  # 或 YYYY-MM-DDThh:mm
python scripts/actions.py complete_task --id "t_001"
python scripts/actions.py add_exam --course "课程" --date "YYYY-MM-DD" [--scope "范围"] [--notes "备注"]
python scripts/actions.py add_habit --name "习惯" --schedule "daily/1" [--duration 30] [--reminder "20:00"]
python scripts/actions.py log_habit --id "h_001"
python scripts/actions.py add_plan --date "YYYY-MM-DD" --title "标题" --slot 3
python scripts/actions.py replace_plans --date "YYYY-MM-DD" --plans '[{"title":"标题","time_slot":3}]'
python scripts/actions.py delete_plan --date "YYYY-MM-DD" --index 0
python scripts/actions.py add_course --name "课程" --day 1 --weeks "1-16" --slots "3-4"
python scripts/actions.py delete_course --id "c_001"
python scripts/actions.py status  # 今日概览（课/任务/习惯/支出）
```

schedule格式: daily/N, weekly/1,3,5, monthly/N。day: 1=周一...7=周日。

### 物品（有什么）
添加物品分两步，第一步只查找不添加:
```sh
python scripts/actions.py lookup_item --name "A"
python scripts/actions.py lookup_item --name "B"
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

## 判断优先级
1. 物品/存货/库存/还有/用完了/放在 → add_item 或 update_item
2. 考试/期中/期末 → add_exam
3. 作业/布置/pre/论文 → add_task
4. 习惯/打卡/每天 → add_habit/log_habit
5. 完成/做完了 → complete_task/log_habit
6. 提醒类 → add_plan
7. 移动/拿到/放到/挪到 → update_item --location
8. 删除/丢掉/扔掉/不要了 → delete_item
9. 天气/气温/多少度/下雨/晴天 → 直接用下文「天气」段回答，**不要调用脚本**
10. 余额/剩余/还剩/额度/多少钱 → 直接用下文「余额」段回答，**不要调用脚本**
11. 概览/统计/今天有什么/还有多少 → status

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


class DeepSeekProvider:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com") -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        response = self._client.chat.completions.create(
            model=model or "deepseek-chat",
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


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

    def run(self) -> None:
        try:
            msgs = list(self._messages)
            final_text = ""
            all_instructions = []  # collect across multi-turn agent loop
            for _turn in range(5):  # max 5 turns
                text = self._provider.chat(
                    system_prompt=self._system_prompt,
                    messages=msgs,
                    model=self._model,
                    max_tokens=4096,
                    temperature=0.3,
                )
                instructions = InstructionParser.parse(text)
                if not instructions:
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
        """Extract shell commands from ```sh blocks."""
        blocks = re.findall(r'```sh\s*\n?(.*?)```', text, re.DOTALL)
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
        else:
            base_url = self._settings.get("AI", "api_endpoint", "https://api.deepseek.com")
            return DeepSeekProvider(api_key, base_url)

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
        """Fetch DeepSeek API balance. Returns cached value if < 5 min old.

        实际请求经共享适配器 `services/deepseek.fetch_balance()`（Q-A3）。
        """
        import time

        now = time.time()
        cached = self._ds_balance_cache
        if cached and (now - cached.get("fetched_at", 0)) < 300:
            return cached.get("value", "")

        api_key = self._settings.api_key
        if not api_key:
            return ""

        result = deepseek.fetch_balance(api_key)
        kind = result.get("error_kind")
        if kind == "network":
            val = ""                    # 与旧行为一致：网络异常给空串
        elif "error" in result:
            val = "查询失败"
        elif result.get("balance_infos"):
            val = f"¥{float(result['balance_infos'][0].get('total_balance', 0)):.2f}"
        else:
            val = "未知"
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
