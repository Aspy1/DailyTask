"""AI service with pluggable backends (Anthropic, DeepSeek)."""

import hashlib
import json
import logging
import re
import threading
import time
from datetime import date
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from src.services import ai_ledger, ai_verify, deepseek, openmeteo
from src.services.ai_instructions import InstructionParser
from src.services.ai_loop_guards import (
    _claims_done,
    _continuation_nudge,
    _has_write_cmd,
    cmds_key,
    repeat_nudge,
)
from src.services.ai_prompts import (
    SYSTEM_PROMPT_BASE,
    expense_prompt,
)

# 提供方适配层已拆到 `ai_providers.py`（单文件 ≤800 行）；这里**重新导出**，
# 既有 import（包括测试里的 `DeepSeekProvider` / `REASONING_EFFORT`）不用改。
from src.services.ai_providers import (  # noqa: F401 — 兼容旧 import 路径
    AI_REQUEST_TIMEOUT,
    REASONING_EFFORT,
    AIProvider,
    AnthropicProvider,
    DeepSeekProvider,
    provider_headers,
)

logger = logging.getLogger(__name__)

# 账本保留条数：它是"**最近实际做过什么**"（§2.4 的执行日志），不是流水账
EXEC_LOG_KEEP = 5


def _exec_log_section(lines: list[str]) -> str:
    """把"实际执行过的动作"拼成提示词里的一段（§2.4：执行日志 ≠ 聊天记录，且标明是**事实**）。"""
    body = "\n".join(f"  {line}" for line in lines)
    return ("\n最近实际执行过的动作（**事实**，不是你的回忆；"
            "\"继续 / 撤销刚才那条\"要以此为准）:\n" + body + "\n")


def _looks_truncated(text: str) -> bool:
    """回复是否疑似被输出上限截断：代码围栏数量是奇数 = 有开场没收尾。"""
    return text.count("```") % 2 == 1


def _strip_code_blocks(text: str) -> str:
    """去掉代码块与 **`<ds_safety>` 安全分类残留**，只留自然语言（显示给用户用）。

    围栏语言要放宽（模型常写 ```bash）；`<ds_safety>` 是端点把分类器输出拼进 content 的
    产物（2026-10-19 评估集实测），在**末尾** → 从它开始截断。
    """
    text = re.sub(r'<ds_safety>.*\Z', '', text, flags=re.DOTALL)
    return re.sub(r'```(?:sh|bash|shell|console|zsh|json)\s*.*?```', '',
                  text, flags=re.DOTALL).strip()


# 空回复的**明确失败**文案：模型只输出推理（或什么都没给）时用。
# 服务层沿用既有做法直接 emit 文案（与 `self.error.emit(str(e))` 一致）。
_EMPTY_REPLY_NOTE = ("模型没有返回可执行内容（推理可能占满了输出预算）。"
                     "请重试，或提高设置里的 AI.max_tokens。")


# ── Worker ─────────────────────────────────────────────────────

def _status_note(all_instructions: list, wrote_data: bool, ok_count: int,
                 write_failures: list, finished_normally: bool, display: str) -> str:
    """给用户看的告警文案（没有问题时返回空串）。

    ⚠ **判据以证据为主**：命令结果 / 验收结论 / 是否被切断 / **有没有发过命令**；措辞表只是补充触发。
    """
    total = ok_count + len(write_failures)
    if write_failures:
        shown = "\n".join(f"  {c}" for c in write_failures[:5])
        return f"\n\n⚠ **{len(write_failures)}/{total} 条写命令没有生效或没达到预期**：\n{shown}"
    if all_instructions and not finished_normally:
        return (f"\n\n⚠ **可能没记全** —— 到了轮次/时限上限才停。本次执行 "
                f"{len(all_instructions)} 条命令、其中写命令成功 {ok_count} 条；"
                f"这条话里东西多的话请核对，或回一句\"继续\"让我接着记。")
    if not wrote_data and display and (not all_instructions
                                       or _has_write_cmd(all_instructions)
                                       or _claims_done(display)):
        return ("\n\n⚠ **数据没有任何改动** —— 命令没生效，或本轮压根没执行任何命令"
                "（上面那句是模型的自我描述）。请重试或换个说法。")
    return ""


def _record_goals(ledger, instructions: list, verdicts: list, labels: list) -> None:
    """把每条**写命令**的状态记进账本（查询不算目标；没有账本就跳过）。"""
    if ledger is None:
        return
    for cmd, (state, detail), label in zip(instructions, verdicts, labels, strict=False):
        if _has_write_cmd([cmd]):
            ledger.record(cmd, state, detail, label)


class AIWorker(QObject):
    finished = Signal(str)
    error = Signal(str)
    finished_with_instructions = Signal(str, list)
    ledger_ready = Signal(str)          # §3.1 账本：独立于聊天历史，供下一次请求参考

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
        """整次请求的**墙钟上限**（读 `AI.max_seconds`，默认 90s）。到点优雅收尾。

        ⚠ **这是"软"上限**（2026-10-19 审查）：检查发生在**每轮请求之前**，而**单次** SDK
        调用本身可能超过它（provider 侧 120s，且可能重试）→ 真实耗时可能是 `max_seconds + 一次请求`。
        口径：**到点后不再发起新请求，已执行的命令结果照常保留并如实汇报**（不承诺回滚）。
        """
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
        # 累计状态**在 try 之外初始化** —— 异常路径也要能带上"已经做了什么"（见下面 except）。
        final_text = ""
        all_instructions: list = []  # collect across multi-turn agent loop
        wrote_data, finished_normally, ok_count = False, False, 0   # 见 _finish 的注释
        write_failures: list[str] = []                 # 写命令里返回 ERROR 的
        ledger = ai_ledger.Ledger()                    # §3.1 动作账本（按状态汇报）
        try:
            msgs = list(self._messages)
            max_tokens = self._max_tokens()
            seen_cmds: dict[str, int] = {}                 # 同一批命令重复了几次（§4 循环检测）
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
                instructions = InstructionParser.parse(text)
                logger.info("AI turn %d: %.1fs | %d 字符 | 疑似截断=%s | 命令=%d | 本批重复=%d",
                            turn + 1, time.monotonic() - started, len(text), truncated,
                            len(instructions), seen_cmds.get(cmds_key(instructions), 0))
                if not instructions:
                    if self._should_continue(text, truncated, msgs, turn, wrote_data):
                        final_text = text
                        continue
                    # 模型自己收尾了（不是被轮次/时限切断）。
                    # ⚠ **不在这里 emit**：所有出口统一走 `run()` 末尾那一处 `_finish()` ——
                    #   原来这里直接 emit + return，把累计的 `write_failures` / `ok_count`
                    #   整个绕过去了（R1/A1：模型说"已记录"，用户就只看到"已记录" ✗）。
                    finished_normally = True
                    final_text = text
                    break
                all_instructions.extend(instructions)
                results_text, n_ok, bad, off_target = self._run_commands(instructions, seen_cmds,
                                                                        ledger)
                ok_count += n_ok
                # 验收没达到预期的，与"命令报错"一起进"没生效"清单（汇报权归代码）
                write_failures += bad + off_target
                wrote_data = wrote_data or n_ok > 0
                msgs.append({"role": "assistant", "content": text})
                msgs.append({"role": "user", "content": f"[工具执行结果]\n{results_text}"})
                final_text = text
            self._report(all_instructions, wrote_data, final_text, write_failures,
                         finished_normally, ok_count, ledger)
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:
            # 异常也可能发生在**部分写入之后** → 把已有结果摘要一起带上（只报异常会丢掉"写了什么" ✗）
            logger.exception("AI worker 异常（已转成用户可见的错误）")
            self.error.emit(str(e) + _status_note(
                all_instructions, wrote_data, ok_count, write_failures, finished_normally, ""))

    def _run_commands(self, instructions: list, seen_cmds: dict,
                      ledger=None) -> tuple[str, int, list, list]:
        """执行一批命令 → `(喂回文本, 写命令成功数, 写失败, 没达到预期)`。

        执行前记状态、执行后**回读数据**验收（§3.2/§3.3），并逐条写进账本（§3.1）。
        """
        data_dir = getattr(self._dm, "data_dir", None)
        before = [ai_verify.observe(cmd, data_dir) for cmd in instructions]
        labels = [ai_verify.label_of(cmd, data_dir) for cmd in instructions]
        results = InstructionParser.execute(instructions)
        ok, bad = self._split_results(instructions, results)
        verdicts = [ai_verify.check(cmd, was, res, data_dir)
                    for cmd, was, res in zip(instructions, before, results, strict=False)]
        _record_goals(ledger, instructions, verdicts, labels)
        ckey = cmds_key(instructions)
        seen_cmds[ckey] = seen_cmds.get(ckey, 0) + 1
        text = "\n".join(results) + ai_verify.summarize(verdicts) + ai_ledger.recovery_note(results)
        if results and not ok and not bad:
            # 给模型一条**事实**（不是指令）：命令跑了但一条都没成功
            text += ("\n[事实] 命令已执行，但**一条都没成功**（被拒或报错了），"
                     "库存/日程没有任何变化。")
        note = repeat_nudge(seen_cmds, ckey, bool(ok))
        return ((text + "\n" + note) if note else text, len(ok), bad,
                ai_verify.mismatches(verdicts))

    @staticmethod
    def _split_results(instructions: list, results: list) -> tuple[list, list]:
        """按**命令自己的结果**（OK / ERROR）分写命令的成功与失败（记账/查询不算）。"""
        pairs = list(zip(instructions, results, strict=False))
        ok = [c for c, r in pairs if _has_write_cmd([c]) and str(r).startswith("OK")]
        bad = [c for c, r in pairs if _has_write_cmd([c]) and not str(r).startswith("OK")]
        return ok, bad

    def _report(self, all_instructions: list, wrote_data: bool, final_text: str,
                write_failures: list, finished_normally: bool, ok_count: int,
                ledger) -> None:
        """收尾：**事实块（代码生成）在前、模型的话作为说明在后**（乙方案）。

        以前模型那句"已将 X 改为 Y"是主报告，代码只能事后补告警（还挂在措辞表上，会漏）。
        现在反过来：做过什么由账本 + 验收回执写，模型只解释；没有写命令就没有事实块。
        """
        display = ai_ledger.render_facts(ledger, _strip_code_blocks(final_text))
        logger.info("AI 账本：%s", ledger.summary() or "（无写命令）")
        # ⚠ 账本走自己的信号（§2.4：执行日志 ≠ 聊天记录），压缩历史也带不走它
        if ledger.summary():
            self.ledger_ready.emit(ledger.summary())
        self._finish(all_instructions, wrote_data, display, write_failures,
                     finished_normally, ok_count)

    def _finish(self, all_instructions: list, wrote_data: bool, display: str,
                write_failures: list | None = None, finished_normally: bool = True,
                ok_count: int = 0) -> None:
        """收尾：**汇报权归代码**（§2.3）+ **量化覆盖**（§9.3），见 `_status_note`。"""
        display += _status_note(all_instructions, wrote_data, ok_count,
                                     write_failures or [], finished_normally, display)
        if all_instructions:
            self.finished_with_instructions.emit(display or "已完成", all_instructions)
        elif display:
            self.finished.emit(display)
        else:
            self.error.emit(_EMPTY_REPLY_NOTE)

    def _should_continue(self, text: str, truncated: bool, msgs: list,
                         turn: int, wrote_data: bool = False) -> bool:
        """这一轮没有可执行命令：**只决定**继续（`True`）还是停止（`False`）。

        ⚠ **绝不在这里发最终信号** —— 出口只有 `run()` 末尾那一处 `_finish()`（R1/A1）。
        以前它自己 emit，于是"累计的写失败"在"模型自己收尾"这条路上全丢了 ✗。

        `wrote_data` = **数据是否真的变过**（不是"发过命令"），由调用方从磁盘指纹算出。
        """
        empty_retries = sum(1 for m in msgs
                            if m["role"] == "user" and "[系统]" in str(m["content"]))
        nudge = _continuation_nudge(text, truncated, empty_retries, wrote_data) if turn < 4 else None
        if not nudge:
            return False
        # §12.1：把**哪个护栏触发了**也记下来（"为什么这轮停了"排查时缺的就是这个字段）
        logger.warning("AI 第 %d 轮没有可执行命令，要求继续：%s",
                       turn + 1, nudge.split("：", 1)[0][:40])
        msgs.append({"role": "assistant", "content": text})
        msgs.append({"role": "user", "content": nudge})
        return True


def _inventory_prompt(inventory) -> str:
    """（已并入 `ai_prompts.inventory_prompt`。）"""
    from src.services.ai_prompts import inventory_prompt

    return inventory_prompt(inventory)


# ── 提示词片段（模块级：AIService 类需要保持在 400 行以内，Q-A1）──

def _prompt_cache_key(dm, settings, exec_log: list[str],
                      weather_cache: dict, today: date) -> str:
    """提示词缓存键：**内容指纹**（不是列表长度）。

    旧实现用 `len(...)` 当键：改一条任务标题 / 把 5 元改成 50 元 / 同名替换，
    长度都没变 → AI 继续拿到**旧上下文**（它会把旧值当成事实）。
    """
    payload = {
        "today": today.isoformat(),
        "semester": dm.courses.current_semester,
        "courses": dm.courses.courses,
        "tasks": dm.tasks.active,
        "habits": dm.habits.habits,
        "plans": dm.daily_logs._data.get("plans", {}),
        "expenses": {"records": dm.expenses.records, "budget": dm.expenses.budget},
        "inventory": dm.inventory.items,
        "balances": {
            key: [settings.get("Balance", f"{key}_balance"),
                  settings.get("Balance", f"{key}_threshold")]
            for key in ("campus_card", "water_card", "electricity")
        },
        "exec_log": exec_log,
        "weather_ts": int(weather_cache.get("fetched_at", 0)),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _course_list(dm, weekday_names: list[str]) -> str:
    """课程清单（用于系统提示词）。"""
    course_lines = []
    for c in dm.courses.courses:
        day = c.get("day_of_week", 0)
        day_str = weekday_names[day - 1] if 1 <= day <= 7 else "?"
        weeks = c.get("weeks", {})
        w_str = f"第{weeks.get('start','?')}-{weeks.get('end','?')}周" if weeks else ""
        course_lines.append(f"  - {c.get('name','')} ({day_str} {w_str})")
    return "\n".join(course_lines) if course_lines else "  （无课程）"


def _plan_list(dm) -> str:
    """日程计划清单（**今天起**最近 10 天，方括号内为 delete_plan 的 index）。"""
    plan_lines = []
    all_plans = dm.daily_logs._data.get("plans", {})
    today = date.today().isoformat()
    upcoming = sorted(day for day in all_plans if day >= today)[:10]
    for day_str in upcoming:
        for i, plan in enumerate(all_plans[day_str]):
            plan_lines.append(
                f"  [{i}] {day_str} 时段{plan.get('time_slot','?')} — "
                f"{plan.get('title','')} ({plan.get('course_name','')})")
    return "\n".join(plan_lines) if plan_lines else "  （无日程计划）"


def _balance_info(settings, ds_balance_cache: dict) -> str:
    """余额清单：校园卡/水卡/电费 + DeepSeek API（API 余额只读缓存）。"""
    balance_lines = []
    for key, label in [("campus_card", "校园卡"), ("water_card", "水卡"),
                       ("electricity", "电费")]:
        bal = settings.get("Balance", f"{key}_balance")
        thr = settings.get("Balance", f"{key}_threshold")
        if bal:
            b = f"¥{bal}"
            b += f" (低于{thr}元提醒)" if thr else ""
        else:
            b = "未设置"
        balance_lines.append(f"  {label}: {b}")
    ds_balance = ds_balance_cache.get("value", "")
    if ds_balance:
        balance_lines.append(f"  DeepSeek API: {ds_balance}")
    return "\n".join(balance_lines)


def _habit_list(dm) -> str:
    """习惯清单（id 用于修改 / 推迟 / 取消）。"""
    habits = dm.habits.habits
    if not habits:
        return "  （无习惯）"
    day_names = ["一", "二", "三", "四", "五", "六", "日"]
    lines = []
    for habit in habits:
        sched = habit.get("schedule", {})
        if sched.get("type") == "weekly":
            days = sched.get("days", [])
            spec = "每周" + "".join(day_names[d - 1] for d in sorted(days))
        else:
            spec = f"每{sched.get('value', 1)}天"
        rt = habit.get("reminder_time", "")
        rt_str = f" {rt}" if rt else ""
        pu = habit.get("postpone_until", "")
        pu_str = f" [推迟至{pu[:10]}]" if pu else ""
        lines.append(f"  [{habit['id']}] {habit.get('name','')} ({spec}{rt_str}){pu_str}")
    return "\n".join(lines)


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
        # 实际执行过的动作（§2.4：**执行日志 ≠ 聊天记录**）—— 压缩历史时**不丢** ✓
        self._exec_log: list[str] = []
        self._thread: QThread | None = None
        self._worker: AIWorker | None = None
        # 同一时刻只允许一个请求：旧实现无守卫，第二次 send_message 会**覆盖** `_thread`
        # 引用，正在跑的 QThread 可能在 Python GC 时被销毁（崩溃/未定义行为）。
        self._busy = False
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
        if self._busy:
            # 不覆盖正在运行的 QThread：让用户等这一条结束（界面本来也禁用了输入）
            self.error_occurred.emit("正在处理上一条消息，请稍候再发。")
            return
        if not self.is_configured:
            self.error_occurred.emit("未配置 API 密钥，请在设置中填写。")
            return
        self._history.append({"role": "user", "content": text})
        self._auto_compress()
        self._busy = True
        self._send_to_ai()

    def _send_to_ai(self) -> None:
        system_prompt = self._build_system_prompt()
        try:
            provider = self._make_provider()
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception as e:  # noqa: BLE001
            self._busy = False
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
        self._worker.ledger_ready.connect(self._on_ledger)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._worker.finished_with_instructions.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._worker.finished_with_instructions.connect(self._worker.deleteLater)
        # ⚠ 忙标记要等**线程真正结束**才放开（响应信号在 run() 结束前就发出了，
        # 那时立刻再发一条仍会覆盖正在收尾的 QThread）
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        try:
            self._thread.start()
        # 边界捕获：线程起不来（系统资源耗尽）必须回到可重试状态，不能永久 busy
        except Exception as e:  # noqa: BLE001
            self._busy = False
            self.error_occurred.emit(f"无法启动 AI 线程: {e}")

    def _on_thread_finished(self) -> None:
        """线程真正退出后才允许下一次请求。"""
        self._busy = False
        self._thread = None
        self._worker = None

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
        cache_key = _prompt_cache_key(self._dm, self._settings, self._exec_log,
                                      self._weather_cache, today)
        if getattr(self, '_prompt_cache_key', None) == cache_key:
            return self._prompt_cache_value

        summary = self._dm.get_today_summary()
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[today.weekday()]

        course_list = _course_list(self._dm, weekday_names)
        plan_list = _plan_list(self._dm)
        balance_info = _balance_info(self._settings, self._ds_balance_cache)

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
{_habit_list(self._dm)}

余额:
{balance_info}

天气:
{weather_info}

物品库存（id 用于修改/移动）:
{_inventory_prompt(self._dm.inventory)}

假期/调休:
{self._build_holiday_info()}
"""
        if self._exec_log:
            context += _exec_log_section(self._exec_log)
        prompt = SYSTEM_PROMPT_BASE + "\n" + context + "\n【输出格式】\n- 纯文本，禁用 markdown。仅可用**加粗**。\n- 禁止输出脚本命令原文和执行结果。\n- ⚠ 要执行操作时**只能**输出 ```sh 代码块（每行一条 `python scripts/actions.py …`）。\n  禁止输出任何**工具调用 / 函数调用**格式（例如 `<｜｜DSML｜｜ invoke name=…>`、`<｜｜DSML｜｜ parameter …>`、\n  XML/JSON 包裹的 invoke/parameter）—— 那些不会被解析，等于什么都没做。\n- 查找发现重复物品时，在该轮回复中告知用户，等待确认后再处理。\n- 完成后用一句简练中文**补充说明**（背景、注意事项）；**不要**复述「已记录 / 已完成 / 已改为」这类完成叙述 —— 实际执行结果由程序单独显示给用户。"
        self._prompt_cache_key = cache_key
        self._prompt_cache_value = prompt
        return prompt

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

    def _on_ledger(self, summary: str) -> None:
        """收下本次账本，作为**事实**留给下一次请求（§2.4）。只留最近 `EXEC_LOG_KEEP` 条；
        与 `_history` **分开存** —— 压缩聊天历史不会动它 ✓。"""
        self._exec_log.append(summary)
        del self._exec_log[:-EXEC_LOG_KEEP]

    def clear_history(self) -> None:
        self._history = []
        self._exec_log = []

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
