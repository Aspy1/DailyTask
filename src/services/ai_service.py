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
- 日期: 统一 YYYY-MM-DD。"下周日""6月20日""明天"→计算为实际日期
- 时段: 1=08:30-10:05, 2=10:25-12:00, 3=13:30-15:05, 4=15:25-17:00, 5=18:30-20:05, 6=20:10-21:45

## 命令速查

```sh
python scripts/actions.py add_task --course "课程" --title "标题" --due "YYYY-MM-DD" [--priority high|medium|low]
python scripts/actions.py complete_task --id "t_001"
python scripts/actions.py add_exam --course "课程" --date "YYYY-MM-DD" [--scope "范围"] [--notes "备注"]
python scripts/actions.py add_habit --name "习惯" --schedule "daily/1" [--duration 30] [--reminder "20:00"]
python scripts/actions.py log_habit --id "h_001"
python scripts/actions.py add_plan --date "YYYY-MM-DD" --title "标题" --slot 3
python scripts/actions.py replace_plans --date "YYYY-MM-DD" --plans '[{"title":"标题","time_slot":3}]'
python scripts/actions.py add_course --name "课程" --day 1 --weeks "1-16" --slots "3-4"
```

schedule格式: daily/N, weekly/1,3,5, monthly/N。day: 1=周一...7=周日。

## 判断优先级
1. 考试/期中/期末 → add_exam
2. 作业/布置/pre/论文 → add_task
3. 习惯/打卡/每天 → add_habit/log_habit
4. 完成/做完了 → complete_task/log_habit
5. 提醒类 → add_plan
"""


class InstructionParser:
    """Extract and execute shell commands from AI responses."""

    @staticmethod
    def parse(text: str) -> list[str]:
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


