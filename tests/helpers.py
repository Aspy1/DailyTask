"""测试辅助函数。"""

import json
from pathlib import Path

import scripts.actions as actions

# 真实数据目录（用于防止测试误写用户数据）
REAL_DATA_DIR = (Path(__file__).resolve().parent.parent / "data").resolve()


def run(cmd: str) -> str:
    """在进程内执行一条 actions.py 命令，返回捕获的输出。

    ⚠ **必须**在 `sandbox` fixture 下使用：否则 `actions.DATA` 指向真实 `data/`，
    命令会直接写进用户数据（2026-10-16 真实事故：一个漏了 sandbox 的菜单冒烟测试
    往 courses/tasks/exams/habits/inventory/daily_logs 各写了一条种子数据，
    并被应用的 GitSync 自动提交推送）。这里做成硬失败，让同类错误不可能再发生。
    """
    if Path(actions.DATA).resolve() == REAL_DATA_DIR:
        raise RuntimeError(
            "run() 只能在 sandbox fixture 下调用：当前 actions.DATA 指向真实 data/，"
            "会污染用户数据。请给测试加上 sandbox 参数。")
    return actions.run_in_process(cmd)


def read_json(data_dir: Path, name: str) -> dict:
    """读取沙箱数据目录下的 JSON；文件不存在时返回空 dict。

    按学期分文件后，`courses/tasks/exams.json` 实际在 `semesters/<当前学期>/` 下 ——
    这里用**与生产代码同一套解析**（`semester_paths.resolve`），
    这样测试断言 `read_json(sandbox, "tasks.json")` 依然成立。
    """
    from src.models import semester_paths

    p = semester_paths.resolve(data_dir, name) if semester_paths.is_per_semester(name) \
        else data_dir / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
