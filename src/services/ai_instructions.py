"""AI 回复里的**命令解析与执行**（从 `ai_service.py` 抽出，2026-10-19）。

为什么单独成模块：`ai_service.py` 顶到单文件 800 行上限 ✗，而这块职责独立
（"从回复文本里抽出命令" + "在内存里执行"），与 worker 的循环/预算/收尾无关 ✓。

⚠ `execute()` 运行在 **AI worker 线程**：**不得触碰 Model、不得 emit 信号** ——
数据重载与通知由主线程的 `AIService._on_response_with_instructions` 负责
（CODE_STANDARDS Q-B2 / Q-B4）。
"""

import re


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
        """在**内存中**执行 actions.py 命令，返回每条命令的输出。"""
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
