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

SYSTEM_PROMPT_BASE = """你是一个学生时间管理助手，运行在桌面应用中。
你的职责是：理解用户的自然语言输入，将其转化为结构化的数据操作。

## 重要规则
1. 当用户表达了需要修改数据的意图时，先用自然语言回复确认，然后用 ```json 代码块包裹要执行的操作。
2. 如果用户只是闲聊或询问，直接自然语言回复，不需要输出 JSON。
3. 如果用户询问今天有什么要做，根据"今日概况"数据回答。
4. 如果用户提到某个日期但未给出年份，以当前日期为参考推断。
5. 不要编造不存在的数据。如果用户询问未设置的内容，如实告知。
6. 永远不要删除数据，除非用户明确要求删除。
7. 每次回复最多包含一个 ```json 代码块，但代码块内可以包含一个 JSON 数组包含多个操作。
8. 每门课程每天只应添加一次，用 time_slots 数组包含该天所有时间段。
9. 当用户说"我习惯...""我有个习惯...""添加习惯..."时，应识别为添加习惯。如果用户说"我今天不想..."或"今天不想做..."，应识别为推迟或取消今日习惯。
10. 当用户告知调休/放假安排（如"这周五放假，下周六补课"）时，计算具体日期后调用 add_holiday。调休只影响课程表，不影响 DDL、习惯和自定义日程。

## 关键词分流规则（重要）

根据用户消息中的关键词，判断意图并选择正确的操作类型：

### → 添加作业/任务（add_task）
触发词：**老师布置**、**作业**、**老师安排**、**这门课要求**、**考试**
示例：
- "老师布置了高数作业" → add_task
- "这门课要求做一个pre" → add_task
- "下周有考试" → add_task

### → 添加习惯（add_habit）
触发词：**我习惯**、**添加习惯**、**我有个习惯**
示例：
- "我习惯每天跑步" → add_habit
- "添加习惯：每周三练琴" → add_habit

### → 自定义日程（add_plan）
触发词：**提醒我**、**记得**、**帮我记下来**、**别忘了**，以及任何不含上述作业/习惯关键词的提醒类发言
示例：
- "提醒我今天下午5点半出去练习排球" → add_plan（不是作业，不是习惯）
- "记得明天去图书馆还书" → add_plan
- "帮我记下来周五开会" → add_plan

如果用户同时表达了提醒时间（如"提前5分钟提醒"），在 add_plan 完成后，还需要通过自定义邮件提醒功能让用户设置提醒时间。告知用户可在日程视图右键该计划选择"添加邮件提醒"来自由设定提醒时间。

**判断优先级**: 先检查是否有作业关键词 → 再检查是否有习惯关键词 → 都没有则视为自定义日程。

## 课程表时间模型（重要）

一天分为若干大时段。默认 5 个（上午 2 + 下午 2 + 晚上 1），但如果用户告知本学期晚上排了 2 节课，则为 6 个。以用户实际告知为准，通过 set_semester 的 period_count 字段记录。

默认 5 时段：

| 编号 | 名称 | 时间范围 | 45分钟小节数 |
|------|------|----------|-------------|
| 1 | 上午第1节 | 08:30-10:05 | 2 |
| 2 | 上午第2节 | 10:25-12:00 | 2 |
| 3 | 下午第1节 | 13:30-15:05 | 2 |
| 4 | 下午第2节 | 15:25-17:00 | 2 |
| 5 | 晚上第1节 | 18:30-20:05（或 18:30-20:55） | 2 或 3 |

如果晚上有 2 节课（period_count=6），晚上两节通常为：
| 5 | 晚上第1节 | 18:30-20:05 | 2 |
| 6 | 晚上第2节 | 20:10-21:45 | 2 |

注意：每段由 `&` 连接的多个 45 分钟小节组成。例如 "08:30-09:15 & 09:20-10:05" 对应编号 1，不是两节课。把 & 连接的小节合并为一个 time_slot。晚上如果出现三个小节（18:30-19:15 & 19:20-20:05 & 20:10-20:55），同样合并为一个 time_slot。

## 周段表述解析

用户课程表使用以下几种周段表述，你需要正确解析：

| 示例 | 含义 | weeks 字段 |
|------|------|------------|
| (1-16周) | 第1到16周，每周上课 | {"start":1, "end":16}, week_parity:"all" |
| (单1-15周) | 第1到15周中的奇数周 | {"start":1, "end":15}, week_parity:"odd" |
| (双2-16周) | 第2到16周中的偶数周 | {"start":2, "end":16}, week_parity:"even" |
| (1-8周) | 第1到8周，每周上课 | {"start":1, "end":8}, week_parity:"all" |

如果出现"点+段"的复合周段，例如 (4 9-16周) 表示第4周加上第9-16周，则拆分为两条课程记录：一条 weeks:{"start":4,"end":4}，另一条 weeks:{"start":9,"end":16}。类似 (单3 5-8周) 拆为 weeks:{"start":3,"end":3}, week_parity:"odd" 和 weeks:{"start":5,"end":8}, week_parity:"odd"。

## 老师按周段切换

用户数据中，同一课程、同一时段、不同周段可能由不同老师授课。例如：

13:30-14:15：人工智能数学基础，杨雅君老师，(1-8周, 45楼B308)
14:20-15:05：人工智能数学基础，刘志磊老师，(9-16周, 45楼B308)

这是**一门课**（人工智能数学基础），在第3时段（13:30-15:05），前8周杨雅君、后8周刘志磊。**不要**拆成两条课程记录。正确做法：使用 teacher_schedule 字段，合并为一条课程：

{"name":"人工智能数学基础","day_of_week":3,"weeks":{"start":1,"end":16},"time_slots":[{"start":3,"end":4,"location":"45楼B308"}],"teacher_schedule":[{"name":"杨雅君","weeks":{"start":1,"end":8}},{"name":"刘志磊","weeks":{"start":9,"end":16}}]}

规则：同一门课、同一天、同一时段但不同老师按周段轮换 → 一定是同一门课，使用 teacher_schedule。

## 支持的 JSON 操作

### 添加课程
单条：{"action":"add_course","data":{"name":"课程名","teacher":"教师","day_of_week":1,"weeks":{"start":1,"end":15},"week_parity":"all","time_slots":[{"start":1,"end":2,"location":"教学楼A201"}],"notes":""}}
批量：{"action":"add_courses_batch","data":[课程1, 课程2, ...]}

day_of_week: 1=周一,2=周二,3=周三,4=周四,5=周五,6=周六,7=周日。
time_slots: 以上述 5 时段编号为准。start/end 为时段编号（1-5），不是 45 分钟小节号。
week_parity: "all" | "odd" | "even"。分别表示每周、单周、双周。
如果同一门课不同周段由不同老师授课，使用 teacher_schedule 代替 teacher 字段：
{"teacher_schedule":[{"name":"教师A","weeks":{"start":1,"end":8}},{"name":"教师B","weeks":{"start":9,"end":16}}]}

### 修改课程
{"action":"rename_course","data":{"id":"课程ID","name":"新名称"}}
### 删除课程
{"action":"delete_course","data":{"id":"课程ID"}}
### 清空全部课程
{"action":"delete_all_courses","data":{}}

### 添加任务
{"action":"add_task","data":{"title":"任务标题","description":"","course_name":"对应课程名","due_date":"YYYY-MM-DDTHH:MM:SS","priority":"medium","tags":[]}}
course_name 必填：从用户消息中提取课程名称填入，如"毛概""高数"等。不可省略。priority: "high"|"medium"|"low"

### 完成任务
{"action":"complete_task","data":{"id":"任务ID"}}

### 日程计划操作（用于快速安排）
添加计划: {"action":"add_plan","data":{"date":"YYYY-MM-DD","title":"计划标题","time_slot":时段编号,"type":"custom","note":"备注"}}
删除计划: {"action":"delete_plan","data":{"date":"YYYY-MM-DD","index":索引}}
替换全天计划: {"action":"replace_plans","data":{"date":"YYYY-MM-DD","plans":[计划1, 计划2, ...]}}
time_slot编号从1开始，对应课程表时段。type可选: "custom"(自定义), "course_note"(课程备注)

### 核销习惯
{"action":"log_habit","data":{"habit_id":"习惯ID","completed":true,"note":""}}

### 添加习惯
{"action":"add_habit","data":{"name":"习惯名","schedule":{"type":"weekly","days":[1,3,5]},"reminder_time":"20:00","duration_minutes":30,"attached_tasks":[{"name":"收衣服","delay_hours":2,"duration_minutes":10}]}}
schedule: {"type":"weekly","days":[1,3,5]}（每周一三五）或 {"type":"interval","value":2,"unit":"day"}（每2天）
reminder_time 选填: "HH:MM"。duration_minutes 选填，默认 30。
attached_tasks 选填: 附加事项数组，可在创建习惯时直接传入，无需分步操作。
**触发词**: 当用户说"我习惯...""帮我记下来..."时，应识别为要添加习惯。如果用户没有提供周期（每周几/每N天）、执行时间（几点）、持续时间（多少分钟）和附加事项，**必须先追问**用户这些信息，不要自行假设或填写默认值。

### 修改习惯
{"action":"update_habit","data":{"id":"习惯ID","name":"新名称","schedule":{...},"reminder_time":"22:00"}}
只需传要修改的字段。如需修改附加事项，传完整的 attached_tasks 数组。
### 为习惯新增附加事项
{"action":"add_attached_to_habit","data":{"id":"习惯ID","attached":{"name":"收衣服","delay_hours":2,"duration_minutes":10}}}
向已有习惯追加一条附加事项。
### 删除习惯的附加事项
{"action":"remove_attached_from_habit","data":{"id":"习惯ID","index":0}}
index 为附加事项列表中的序号（从0开始）。

### 删除习惯
{"action":"delete_habit","data":{"id":"习惯ID"}}

### 推迟习惯
{"action":"postpone_habit","data":{"id":"习惯ID","until":"YYYY-MM-DD"}}
将今天的习惯推迟到指定日期。until 可选，默认推迟到明天。

### 取消今日习惯
{"action":"cancel_habit_today","data":{"id":"习惯ID"}}
取消今天的习惯（今天不做，不推迟）。

### 记录支出
{"action":"add_expense","data":{"amount":15.5,"category":"food","note":"午餐","payment_card":""}}
category: "food"|"transport"|"study"|"entertainment"|"shopping"|"other"
payment_card 选填: "campus_card"（校园卡支付）| "water_card"（水卡支付）| ""（其他方式）。
**重要**: 当用户提到用校园卡、水卡、刷卡、饭卡支付时，必须填写 payment_card。系统会自动从对应卡余额中扣除支出金额。例如"食堂用校园卡花了15" → payment_card:"campus_card"，"水卡刷了5块" → payment_card:"water_card"。

### 设置学期
{"action":"set_semester","data":{"name":"学期名","start_date":"YYYY-MM-DD","total_weeks":16,"period_count":5}}
period_count 默认为 5。若用户告知"这个学期晚上有两节课"，则设为 6。用户告知几节就是几节。

### 添加提醒（自定义日程）
{"action":"add_reminder","data":{"title":"事项名","time":"HH:MM","date":"YYYY-MM-DD","frequency":"once"}}
等价于 add_plan，将提醒内容作为自定义日程添加到指定日期的对应时段。date 默认为今天，time 用于自动匹配时段。

### 添加日程计划
{"action":"add_plan","data":{"date":"YYYY-MM-DD","time_slot":3,"title":"背ppt","course_name":"英语","type":"course_note","note":""}}
date 默认为今天。time_slot: 1-5时段编号。type: "course_note"(课程备注) | "custom"(自定义) | "habit"(习惯)。course_name 选填，关联课程时使用。
示例: 用户说"明天英语课要背ppt" → {"action":"add_plan","data":{"date":"2026-06-02","time_slot":3,"title":"背ppt","course_name":"英语","type":"course_note"}}

### 删除日程计划
{"action":"delete_plan","data":{"date":"YYYY-MM-DD","index":0}}
date 为计划所在日期，index 为当天的第几条（从0开始）。若不知 index，先列出当天的 plans 供用户选择。

### 修改支出
{"action":"edit_expense","data":{"id":"支出ID","amount":20.0,"category":"food","note":"新备注"}}
只需填写要修改的字段，未填字段保持不变。
### 删除支出
{"action":"delete_expense","data":{"id":"支出ID"}}
### 清空全部支出
{"action":"delete_all_expenses","data":{}}
### 修改预算
{"action":"set_budget","data":{"monthly":2000}}
### 记录省钱
{"action":"add_saving","data":{"amount":15.0,"note":"自己做饭省了外卖钱","date":"YYYY-MM-DD"}}
date 默认为今天。note 选填。
### 删除省钱记录
{"action":"delete_saving","data":{"date":"YYYY-MM-DD","index":0}}
date 为记录所在日期，index 为当天第几条（从0开始）。

### 更新余额
{"action":"set_balance","data":{"card":"campus_card","balance":85.5,"threshold":20}}
card: "campus_card"|"water_card"|"electricity"。balance 为当前余额，threshold 为低余额提醒阈值（选填）。
### 查询余额
{"action":"query_balance","data":{}}
当用户询问校园卡/水卡/电费余额时调用此操作，系统会返回最新数据。

### 记录调休/假期
{"action":"add_holiday","data":{"excluded":["2026-06-05","2026-06-06","2026-06-07"],"makeup":{"2026-06-13":5}}}
excluded: 放假的日期列表（这些日期不按课表上课）。makeup: {日期: 星期几} 调休日按星期几的课表上课（1=周一...7=周日）。
当用户告知调休安排时（如"这周五到周日放假，下周六调休"），计算出具体日期后调用此操作。**只影响课程表**，不影响 DDL、习惯、自定义日程。
### 清除所有假期
{"action":"clear_holidays","data":{}}

### 添加校园卡充值提醒
{"action":"add_card_reminder","data":{"payment_method":"campus_card","low_balance_threshold":20}}
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
    @staticmethod
    def parse(text: str) -> list[dict]:
        blocks = re.findall(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        instructions = []
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            try:
                obj = json.loads(block)
                instructions.extend(InstructionParser._normalize(obj))
            except json.JSONDecodeError:
                instructions.extend(InstructionParser._try_multi_object(block))
        return instructions

    @staticmethod
    def _normalize(obj) -> list[dict]:
        if isinstance(obj, list):
            result = []
            for item in obj:
                if isinstance(item, dict):
                    if "action" in item:
                        result.append(item)
                    elif "name" in item:
                        result.append({"action": "add_course", "data": item})
            if result:
                return result
            return [{"action": "add_courses_batch", "data": obj}]
        if isinstance(obj, dict):
            if "action" in obj:
                return [obj]
            if "name" in obj:
                return [{"action": "add_course", "data": obj}]
        return []

    @staticmethod
    def _try_multi_object(text: str) -> list[dict]:
        results = []
        for candidate in re.split(r'\n(?=\{)|(?<=\})\n', text):
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                obj = json.loads(candidate)
                results.extend(InstructionParser._normalize(obj))
            except json.JSONDecodeError:
                continue
        return results

    @staticmethod
    def execute(instructions: list[dict], dm, settings=None) -> list[str]:
        results = []
        for instr in instructions:
            action = instr.get("action", "")
            data = instr.get("data", {})
            try:
                msg = InstructionParser._exec_one(action, data, dm, settings)
                results.append(msg)
            except Exception as e:
                results.append(f"执行 {action} 失败: {e}")
        dm.save_all()
        dm.data_changed.emit(action)
        return results

    @staticmethod
    def _exec_one(action: str, data: dict, dm, settings=None) -> str:
        if action == "add_course":
            cid = dm.courses.add_course(data)
            return f"已添加课程: {data.get('name', cid)}"

        elif action == "add_courses_batch":
            courses = data if isinstance(data, list) else [data]
            names = []
            for c in courses:
                cid = dm.courses.add_course(c)
                names.append(c.get('name', cid))
            return f"已批量添加 {len(names)} 门课程: {', '.join(names)}"

        elif action == "update_course":
            dm.courses.update_course(data["id"], data.get("changes", {}))
            return f"已更新课程: {data['id']}"

        elif action == "rename_course":
            dm.courses.update_course(data["id"], {"name": data["name"]})
            return f"已重命名课程: {data['id']} → {data['name']}"

        elif action == "delete_course":
            dm.courses.delete_course(data["id"])
            return f"已删除课程: {data['id']}"

        elif action == "delete_all_courses":
            count = len(dm.courses.courses)
            dm.courses._data["courses"] = []
            dm.courses.save()
            return f"已清空全部 {count} 门课程"

        elif action == "add_task":
            tid = dm.tasks.add(data)
            return f"已添加任务: {data.get('title', tid)}"

        elif action == "complete_task":
            dm.tasks.complete(data["id"])
            return f"已完成任务: {data['id']}"

        elif action == "add_habit":
            hid = dm.habits.add_habit(data)
            return f"已添加习惯: {data.get('name', hid)}"

        elif action == "update_habit":
            ok = dm.habits.update_habit(data["id"], {k: v for k, v in data.items() if k != "id"})
            dm.habits.save()
            return f"已更新习惯: {data['id']}" if ok else f"未找到习惯: {data['id']}"

        elif action == "delete_habit":
            ok = dm.habits.delete_habit(data["id"])
            dm.habits.save()
            return f"已删除习惯: {data['id']}" if ok else f"未找到习惯: {data['id']}"

        elif action == "add_attached_to_habit":
            at = data.get("attached", {})
            for h in dm.habits.habits:
                if h["id"] == data["id"]:
                    ats = h.setdefault("attached_tasks", [])
                    ats.append(at)
                    existing = {t["name"] for t in dm.habits.attached_task_templates}
                    if at.get("name", "") not in existing:
                        dm.habits.add_template(dict(at))
                    dm.habits.save()
                    return f"已为习惯 {data['id']} 添加附加事项: {at.get('name', '')}"
            return f"未找到习惯: {data['id']}"

        elif action == "remove_attached_from_habit":
            idx = data.get("index", 0)
            ok = False
            for h in dm.habits.habits:
                if h["id"] == data["id"]:
                    ats = h.get("attached_tasks", [])
                    if 0 <= idx < len(ats):
                        removed = ats.pop(idx)
                        dm.habits.save()
                        return f"已从习惯 {data['id']} 移除附加事项: {removed.get('name', '')}"
            return f"未找到习惯 {data['id']} 的第 {idx} 项附加事项"

        elif action == "postpone_habit":
            until = data.get("until") or (date.today() + timedelta(days=1)).isoformat()
            ok = dm.habits.postpone(data["id"], until)
            dm.habits.save()
            return f"已将习惯 {data['id']} 推迟至 {until}" if ok else f"未找到习惯: {data['id']}"

        elif action == "cancel_habit_today":
            ok = dm.habits.cancel_today(data["id"])
            dm.habits.save()
            return f"已取消今天的习惯: {data['id']}" if ok else f"未找到习惯: {data['id']}"

        elif action == "log_habit":
            dm.habits.log(data["habit_id"], data.get("completed", True), data.get("note", ""))
            return f"已核销习惯: {data['habit_id']}"

        elif action == "add_expense":
            eid = dm.expenses.add(data)
            msg = f"已记录支出: ¥{data.get('amount', 0)} ({data.get('category', 'other')})"
            # Auto-deduct from card balance
            card = data.get("payment_card", "")
            if card in ("campus_card", "water_card") and settings:
                cur = settings.get("Balance", f"{card}_balance")
                if cur:
                    try:
                        new_bal = float(cur) - data.get("amount", 0)
                        settings.set("Balance", f"{card}_balance", f"{new_bal:.1f}")
                        settings.save()
                        labels = {"campus_card": "校园卡", "water_card": "水卡"}
                        msg += f"，{labels[card]}余额自动更新为 ¥{new_bal:.1f}"
                    except ValueError:
                        pass
            return msg

        elif action == "set_semester":
            if "id" not in data:
                data["id"] = data.get("name", f"sem_{len(dm.courses.semesters) + 1}")
            dm.courses._data.setdefault("semesters", []).append(data)
            dm.courses.current_semester = data["id"]
            weeks = data.get("total_weeks", "?")
            periods = data.get("period_count", 5)
            return f"已设置学期: {data.get('name', '')} (共{weeks}周, 每天{periods}节)"

        elif action == "add_plan":
            dm.daily_logs.add_plan(data, data.get("date"))
            return f"已添加日程计划: {data.get('title', '')}"

        elif action == "delete_plan":
            day = data.get("date", date.today().isoformat())
            idx = data.get("index", 0)
            ok = dm.daily_logs.delete_plan(day, idx)
            return f"已删除 {day} 的第{idx+1}条日程计划" if ok else f"删除失败: {day} 不存在第{idx+1}条计划"

        elif action == "edit_expense":
            eid = data["id"]
            records = dm.expenses._data.get("records", [])
            for r in records:
                if r["id"] == eid:
                    if "amount" in data:
                        r["amount"] = data["amount"]
                    if "category" in data:
                        r["category"] = data["category"]
                    if "note" in data:
                        r["note"] = data["note"]
                    dm.expenses.save()
                    return f"已修改支出: {eid}"
            return f"未找到支出: {eid}"

        elif action == "delete_expense":
            ok = dm.expenses.delete(data["id"])
            dm.expenses.save()
            return f"已删除支出: {data['id']}" if ok else f"未找到支出: {data['id']}"

        elif action == "delete_all_expenses":
            count = len(dm.expenses.records)
            dm.expenses._data["records"] = []
            dm.expenses.save()
            return f"已清空全部 {count} 条支出记录"

        elif action == "set_budget":
            budget = dm.expenses._data.setdefault("budget", {})
            if "monthly" in data:
                budget["monthly"] = data["monthly"]
            dm.expenses.save()
            return f"已更新预算: 每月 ¥{data.get('monthly', budget.get('monthly', 0))}"

        elif action == "add_saving":
            sid = dm.daily_logs.add_saving(
                data.get("amount", 0), data.get("note", ""), data.get("date"),
            )
            dm.daily_logs.save()
            return f"已记录省钱: ¥{data.get('amount', 0)}"

        elif action == "delete_saving":
            day = data.get("date", date.today().isoformat())
            idx = data.get("index", 0)
            ok = dm.daily_logs.delete_saving(day, idx)
            return f"已删除 {day} 的第{idx+1}条省钱记录" if ok else f"删除失败: {day} 不存在第{idx+1}条省钱记录"

        elif action == "set_balance":
            card = data.get("card", "campus_card")
            if card not in ("campus_card", "water_card", "electricity"):
                return f"未知卡类型: {card}"
            if settings:
                if "balance" in data:
                    settings.set("Balance", f"{card}_balance", str(data["balance"]))
                if "threshold" in data:
                    settings.set("Balance", f"{card}_threshold", str(data["threshold"]))
                settings.save()
            labels = {"campus_card": "校园卡", "water_card": "水卡", "electricity": "电费"}
            return f"已更新{labels[card]}余额: ¥{data.get('balance', '?')}"

        elif action == "query_balance":
            if not settings:
                return "无法查询余额"
            lines = []
            labels = {"campus_card": "校园卡", "water_card": "水卡", "electricity": "电费"}
            for key, label in labels.items():
                bal = settings.get("Balance", f"{key}_balance")
                thr = settings.get("Balance", f"{key}_threshold")
                if bal:
                    s = f"{label}: ¥{bal}"
                    if thr:
                        try:
                            if float(bal) <= float(thr):
                                s += f"（⚠低于阈值 {thr} 元）"
                        except ValueError:
                            pass
                else:
                    s = f"{label}: 未设置"
                lines.append(s)
            return "当前余额: " + " | ".join(lines)

        elif action == "add_holiday":
            excluded = data.get("excluded", [])
            makeup = data.get("makeup", {})
            dm.courses.add_holiday(excluded, makeup)
            dm.courses.save()
            parts = []
            if excluded:
                parts.append(f"假期: {', '.join(excluded)}")
            if makeup:
                day_names = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                m_parts = [f"{d}({day_names.get(dow, '')})" for d, dow in makeup.items()]
                parts.append(f"调休: {', '.join(m_parts)}")
            return "已记录" + "；".join(parts)

        elif action == "clear_holidays":
            dm.courses.clear_holidays()
            dm.courses.save()
            return "已清除所有假期和调休记录"

        elif action == "add_reminder":
            # General reminder → custom plan (not a task)
            from src.models.course import PERIOD_TIMES
            time_str = data.get("time", "")
            time_slot = 1
            if time_str:
                try:
                    hh, mm = time_str.split(":")
                    h_min = int(hh) * 60 + int(mm)
                    for i, (start_s, end_s) in enumerate(PERIOD_TIMES):
                        s = int(start_s[:2]) * 60 + int(start_s[3:])
                        e = int(end_s[:2]) * 60 + int(end_s[3:])
                        if s <= h_min <= e:
                            time_slot = i + 1
                            break
                except (ValueError, IndexError):
                    pass
            dm.daily_logs.add_plan({
                "title": data.get("title", ""),
                "time_slot": time_slot,
                "type": "custom",
                "note": f"{data.get('time', '')} {data.get('frequency', '')}".strip(),
            }, data.get("date"))
            return f"已添加提醒: {data.get('title', '')}"

        elif action == "add_card_reminder":
            dm.tasks.add({
                "title": data.get("payment_method", "余额提醒"),
                "description": json.dumps(data, ensure_ascii=False),
                "due_date": "",
                "priority": "medium",
                "tags": [action],
            })
            return f"已添加余额提醒: {data.get('payment_method', '')}"

        return f"未知操作: {action}"


# ── AI Service ─────────────────────────────────────────────────

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
