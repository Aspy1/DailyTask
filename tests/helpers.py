"""测试辅助函数。"""

import json
from pathlib import Path

import scripts.actions as actions


def run(cmd: str) -> str:
    """在进程内执行一条 actions.py 命令，返回捕获的输出。"""
    return actions.run_in_process(cmd)


def read_json(data_dir: Path, name: str) -> dict:
    """读取沙箱数据目录下的 JSON；文件不存在时返回空 dict。"""
    p = data_dir / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
