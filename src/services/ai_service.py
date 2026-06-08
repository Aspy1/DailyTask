"""AI service with pluggable backends (Anthropic, DeepSeek)."""

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, Signal, QThread

logger = logging.getLogger("ai_service")


# ── System prompt ──────────────────────────────────────────────

SYSTEM_PROMPT_BASE = """你是一个学生时间管理助手。理解用户意图、提取参数、调用脚本。

## 核心规则
1. 先用自然语言确认，然后在 ```sh 代码块中输出命令
2. 闲聊则只回复自然语言
3. 不编造数据，不删除数据（除非用户明确要求）
4. 每次最多一个 ```sh 代码块，可包含多条命令（每行一条）

## 参数标准化
- 课程名: 提取核心词，脚本自动模糊匹配（"算法课"→匹配算法设计与分析）
- 日期: 统一 YYYY-MM-DD。"下周日""6月20日""明天"等→计算为实际日期
- 时段: 1=08:30-10:05, 2=10:25-12:00, 3=13:30-15:05, 4=15:25-17:00, 5=18:30-20:05, 6=20:10-21:45

## 可用命令
```sh
python scripts/actions.py add_task --course "课程" --title "标题" --due "YYYY-MM-DD"
python scripts/actions.py complete_task --id "t_001"
python scripts/actions.py add_exam --course "课程" --date "YYYY-MM-DD" [--scope "范围"] [--notes "备注"]
python scripts/actions.py add_habit --name "习惯" --schedule "daily/1" [--duration 30] [--reminder "20:00"]
python scripts/actions.py log_habit --id "h_001"
python scripts/actions.py add_plan --date "YYYY-MM-DD" --title "标题" --slot 3
python scripts/actions.py replace_plans --date "YYYY-MM-DD" --plans '[{"title":"标题","time_slot":3}]'
python scripts/actions.py add_course --name "课程" --day 1 --weeks "1-16" --slots "3-4"
```

schedule格式: daily/N, weekly/1,3,5, monthly/N。day: 1=周一...7=周日。

### 物品（有什么）
添加前先查找避免重复:
```sh
python scripts/actions.py lookup_item --name "关键词"
```
如果返回FOUND，告知用户已有类似物品并确认。如返回NOT_FOUND则添加:
```sh
python scripts/actions.py add_item --name "物品名" --category "分类" --quantity N --location "位置" [--tags "标签1,标签2"]
python scripts/actions.py update_item --id "i_001" --location "新位置"
python scripts/actions.py update_item --id "i_001" --quantity N --status "需购"
python scripts/actions.py need_restock
```
分类: 日用品/食品饮料/学习用品/数码电子/衣物/药品/其他。数量单位统一用"件"。
移动物品: "把X从A拿到B" → update_item --id "i_xxx" --location "B"

## 判断优先级
1. 物品/存货/库存/还有/用完了/放在 → add_item 或 update_item
2. 考试/期中/期末 → add_exam
3. 作业/布置/pre/论文 → add_task
4. 习惯/打卡/每天 → add_habit/log_habit
5. 完成/做完了 → complete_task/log_habit
6. 提醒类 → add_plan
7. 移动/拿到/放到/挪到 → update_item --location
"""



# ── Provider interface ─────────────────────────────────────────

class AIProvider(Protocol):
    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str: ...


class AnthropicProvider:
    def __init__(self, api_key: str):
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
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(self, system_prompt: str, messages: list[dict], model: str,
             max_tokens: int, temperature: float) -> str:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
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
                 messages: list, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._model = model
        self._system_prompt = system_prompt
        self._messages = messages

    def run(self) -> None:
        try:
            text = self._provider.chat(
                system_prompt=self._system_prompt,
                messages=self._messages,
                model=self._model,
                max_tokens=4096,
                temperature=0.3,
            )
            instructions = InstructionParser.parse(text)
            if instructions:
                self.finished_with_instructions.emit(text, instructions)
            else:
                self.finished.emit(text)
        except Exception as e:
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
    def execute(commands: list[str], dm=None, settings=None) -> list[str]:
        """Execute shell commands via subprocess."""
        import subprocess
        results = []
        for cmd in commands:
            try:
                r = subprocess.run(
                    cmd, shell=True,
                    cwd=str(Path(__file__).parent.parent.parent),
                    capture_output=True, text=True, timeout=30
                )
                output = r.stdout.strip() or r.stderr.strip()
                results.append(output)
            except Exception as e:
                results.append(f"ERROR {e}")
        if dm:
            dm.reload_all()
            dm.data_changed.emit("ai_action")
        return results


class AIService(QObject):
    response_received = Signal(str)
    error_occurred = Signal(str)
    instructions_executed = Signal(str, list)

    def __init__(self, settings, data_manager, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._dm = data_manager
        self._history: list[dict] = []
        self._thread: QThread | None = None
        self._worker: AIWorker | None = None

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

        self._history.append({"role": "user", "content": text})
        self._auto_compress()
        system_prompt = self._build_system_prompt()

        try:
            provider = self._make_provider()
        except Exception as e:
            self.error_occurred.emit(f"创建 AI 连接失败: {e}")
            return

        model = self._settings.get("AI", "model", "deepseek-chat")

        self._thread = QThread()
        self._worker = AIWorker(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            messages=list(self._history),
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

    def _build_system_prompt(self) -> str:
        summary = self._dm.get_today_summary()
        today = date.today()
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[today.weekday()]

        course_lines = []
        for c in self._dm.courses.courses:
            day = c.get("day_of_week", 0)
            day_str = weekday_names[day - 1] if 1 <= day <= 7 else "?"
            weeks = c.get("weeks", {})
            w_str = f"第{weeks.get('start','?')}-{weeks.get('end','?')}周" if weeks else ""
            course_lines.append(f"  - {c.get('name','')} ({day_str} {w_str})")
        course_list = "\n".join(course_lines) if course_lines else "  （无课程）"

        plan_lines = []
        all_plans = self._dm.daily_logs._data.get("plans", {})
        for day_str in sorted(all_plans.keys())[:10]:
            plans = all_plans[day_str]
            for i, p in enumerate(plans):
                plan_lines.append(f"  [{i}] {day_str} 时段{p.get('time_slot','?')} — {p.get('title','')} ({p.get('course_name','')})")
        plan_list = "\n".join(plan_lines) if plan_lines else "  （无日程计划）"

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
        balance_info = "\n".join(balance_lines)

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

物品库存（id 用于修改/移动）:
{self._build_inventory_list()}

假期/调休:
{self._build_holiday_info()}
"""
        return SYSTEM_PROMPT_BASE + "\n" + context + "\n【格式规则】\n- 禁止多余换行，直接下一句。\n- 禁用Markdown格式，最多用**加粗**。\n- 回复简洁。\n- 执行操作后一行说明即可。"

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
        semesters = self._dm.courses._data.get("semesters", [])
        for s in semesters:
            try:
                start = date.fromisoformat(s["start_date"])
                delta = (date.today() - start).days
                return max(1, delta // 7 + 1)
            except (KeyError, ValueError):
                pass
        return 1

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
        self.response_received.emit(text)

    def _on_response_with_instructions(self, text: str, instructions: list) -> None:
        self._history.append({"role": "assistant", "content": text})
        logger.info("AI response with %d instructions:\n%s", len(instructions), text[:500])
        results = InstructionParser.execute(instructions, self._dm, self._settings)
        logger.info("Executed %d instructions: %s", len(results), results)

        # Strip JSON blocks from display text — keep only the natural language part
        display_text = re.sub(r'```json\s*.*?```', '', text, flags=re.DOTALL).strip()
        if not display_text:
            display_text = text.replace('```json', '').replace('```', '').strip()

        all_results = "\n".join(f"• {r}" for r in results)
        self.instructions_executed.emit(f"{display_text}\n\n{all_results}", instructions)

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
        self._history = [{"role": "user", "content": summary}] + kept
        logger.info("Context compressed to %d messages", len(self._history))

    def compress_context(self) -> None:
        """Manual compress — keep only the last 10 exchanges."""
        self._auto_compress()
