"""本地跑一遍 CI 的全部检查（替代 GitHub Actions，节省分钟额度）。

**为什么要它**：仓库是**私有**的 → Actions 按分钟计费（Free 计划 2,000 分钟/月），
而且 **Windows runner ×2**。原来的 `ci.yml` 每次 push 会跑 4 个 job
（2 个 Windows 全量检查 + 1 个 Windows 锁文件复现 + 1 个 Ubuntu 审计）≈ **17 分钟/次** ✗。
这些检查**全都能在本机跑**，所以默认只保留"每日日程摘要"那个定时任务 ✓。

用法：
    .venv\\Scripts\\python.exe scripts/ci_local.py            # 全跑，遇错停
    .venv\\Scripts\\python.exe scripts/ci_local.py --keep-going  # 全跑，跑完再汇总
    .venv\\Scripts\\python.exe scripts/ci_local.py --audit      # 额外做依赖漏洞审计

退出码：全绿 0；任何一项失败 1。
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def _steps(with_audit: bool) -> list[tuple[str, list[str]]]:
    steps = [
        ("编译检查", [PY, "-m", "compileall", "-q", "src", "scripts", "tests"]),
        ("ruff", [PY, "-m", "ruff", "check", "src", "scripts", "tests"]),
        ("UI 令牌门禁", [PY, "scripts/check_ui_tokens.py", "--strict", "--check-px"]),
        ("工程规范门禁", [PY, "scripts/check_quality.py", "--strict"]),
        ("依赖一致性", [PY, "-m", "pip", "check"]),
        ("pytest", [PY, "-m", "pytest", "-q"]),
    ]
    if with_audit:
        steps.append(("依赖漏洞审计",
                      [PY, "-m", "pip_audit", "-r", "requirements.lock.txt"]))
    return steps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-going", action="store_true", help="一个失败也继续跑后面的")
    parser.add_argument("--audit", action="store_true", help="额外跑 pip-audit（对着锁文件）")
    args = parser.parse_args()

    failed: list[str] = []
    for name, cmd in _steps(args.audit):
        started = time.monotonic()
        print(f"\n── {name} ──", flush=True)
        code = subprocess.run(cmd, cwd=ROOT).returncode  # noqa: S603 —— 参数全是本文件写死的
        took = time.monotonic() - started
        status = "通过" if code == 0 else f"失败（exit {code}）"
        print(f"   {name}: {status} · {took:.1f}s", flush=True)
        if code != 0:
            failed.append(name)
            if not args.keep_going:
                break

    print("\n== 汇总 ==")
    if failed:
        print("失败：" + "、".join(failed))
        sys.exit(1)
    print("全部通过 ✓")


if __name__ == "__main__":
    main()
