#!/usr/bin/env python
"""工程规范门禁（CODE_STANDARDS 里"能自动检查"的那部分）。

**为什么需要它**：规范里写了不少"检查"方法，但此前只有 ruff 那几条真正进了 CI；
其余（尺寸上限、静默吞异常、ID 生成、令牌命名、i18n 计数、目录白名单、密钥入库）
只有散文约束，回归无人拦。本脚本把可自动化的部分变成门禁。

检查项：

    SIZE        文件 >800 行 / 类 >400 行 / 函数 >60 行        Q-A1（存量走 baseline）
    SILENT      `except ...: pass`（含具名异常，ruff S110 抓不到）Q-I2（必须为 0）
    ID-GEN      `len()+1` 生成 ID                              R-008（必须为 0）
    TOKEN-NAME  色名当令牌名 / 尺寸混进颜色集                   Q-H3（存量走 baseline）
    I18N        src/ui 中文字面量计数                           Q-N5（不得超过 baseline）
    TOP-DIR     顶层目录/根文件白名单（只查 git 跟踪项）        Q-P1
    SECRET      data/settings.ini 不得被 git 跟踪               Q-E1
    VULTURE     死代码（`vulture --min-confidence 80`）         Q-A4（必须为空）
    RADON       圈复杂度 C 级以上                                Q-C1（必须为空）

baseline（`scripts/quality_baseline.json`）是**存量债台账**，只防"新增"。
修好一项就 `--write-baseline` 把它划掉，债只会变少。

用法：
    .venv\\Scripts\\python.exe scripts/check_quality.py            # 只报告
    .venv\\Scripts\\python.exe scripts/check_quality.py --strict   # 有违规退出 1（CI）
    .venv\\Scripts\\python.exe scripts/check_quality.py --write-baseline
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = Path(__file__).resolve().parent / "quality_baseline.json"

LIMITS = {"file": 800, "class": 400, "func": 60}
UI_DIR = ROOT / "src" / "ui"
CHECK_ROOTS = ("src", "scripts", "plugins")
TOOLS = (("VULTURE", ["vulture", "src", "scripts", "plugins", "--min-confidence", "80"]),
         ("RADON", ["radon", "cc", "-n", "C", "-s", "src", "scripts", "plugins"]))

CN_RE = re.compile(r"[\u4e00-\u9fff]")
ID_LEN1_RE = re.compile(r"""f["'][^"']*\{len\([^)]*\)\s*\+\s*1""")
BAD_TOKEN_RE = re.compile(r"^(red|green|yellow|orange|blue|purple)$")

# Q-P1 顶层目录白名单（含 2026-10-16 新增的 design/）
TOP_DIRS = {"src", "scripts", "tests", "plugins", "data", "resources",
            "MD-files", "dev-logs", ".github", "design"}
TOP_FILES = {"main.py", "AGENTS.md", "README.md", "PLAN.md", "ERRORS.md",
             "pyproject.toml", "requirements.txt", "requirements.lock.txt",
             "requirements-dev.txt", ".gitignore"}


class Report:
    """收集报告行与违规项。"""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures: list[str] = []

    def add(self, text: str) -> None:
        self.lines.append(text)

    def fail(self, tag: str, detail: str) -> None:
        self.failures.append(f"{tag} {detail}")

    def must_zero(self, tag: str, title: str, items: list[str]) -> None:
        self.add(f"{tag:<10} {title} {len(items)} 处（必须 0）")
        for item in items:
            self.add(f"            {item}")
            self.fail(tag, item)


def iter_py(roots: tuple[str, ...] = CHECK_ROOTS) -> Iterator[Path]:
    for root in roots:
        base = ROOT / root
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.py")):
            if "__pycache__" not in f.parts:
                yield f


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def _decl_violations(tree: ast.AST, path: str) -> dict[str, int]:
    """类/函数超限（Q-A1）。"""
    out: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            kind = "class"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "func"
        else:
            continue
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        if length > LIMITS[kind]:
            out[f"{kind}:{node.name}@{path}"] = length
    return out


def check_sizes() -> dict[str, int]:
    over: dict[str, int] = {}
    for f in iter_py():
        src = f.read_text(encoding="utf-8")
        lines = len(src.splitlines())
        if lines > LIMITS["file"]:
            over[f"file:{rel(f)}"] = lines
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        over.update(_decl_violations(tree, rel(f)))
    return over


def _is_pass_only(body: list[ast.stmt]) -> bool:
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return True
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str))


def check_silent_swallow() -> list[str]:
    """Q-I2：`except ...: pass`。ruff S110 只拦 `except:`/`except Exception:`，
    具名异常（`except (A, B): pass`）会漏，所以这里用 AST 兜住。"""
    hits = []
    for f in iter_py():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        hits += [f"{rel(f)}:{n.lineno}" for n in ast.walk(tree)
                 if isinstance(n, ast.ExceptHandler) and _is_pass_only(n.body)]
    return hits


def check_id_generation() -> list[str]:
    hits = []
    for f in iter_py():
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if ID_LEN1_RE.search(line):
                hits.append(f"{rel(f)}:{i}")
    return hits


def check_token_names() -> list[str]:
    tokens = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
    bad = []
    for mode, group in tokens.get("colors", {}).items():
        if not isinstance(group, dict):
            continue
        bad += [f"colors.{mode}.{key}" for key in group
                if BAD_TOKEN_RE.match(key) or "radius" in key]
    return sorted(bad)


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            ids.add(id(body[0].value))
    return ids


def _count_cn_in_file(f: Path) -> int:
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0
    docs = _docstring_ids(tree)
    return sum(1 for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and id(n) not in docs and CN_RE.search(n.value))


def count_ui_chinese_literals() -> int:
    return sum(_count_cn_in_file(f) for f in UI_DIR.rglob("*.py")
               if "__pycache__" not in f.parts)


def _git_lines(*args: str) -> list[str]:
    """跑 git 并取行。`core.quotepath=false` + 按 UTF-8 解码，避免中文路径被加引号/乱码。"""
    # 参数全部是本模块写死的常量，无外部输入（S603/S607 不适用）
    proc = subprocess.run(["git", "-c", "core.quotepath=false", *args],  # noqa: S603, S607
                          cwd=ROOT, capture_output=True)
    return proc.stdout.decode("utf-8", errors="replace").splitlines()


def _tracked_entries() -> tuple[set[str], set[str]]:
    dirs, files = set(), set()
    for line in _git_lines("ls-files"):
        head, sep, _ = line.partition("/")
        (dirs if sep else files).add(head)
    return dirs, files


def check_top_level() -> list[str]:
    """Q-P1：只查 **git 跟踪**的顶层项（本地垃圾不该让 CI 变红）。"""
    dirs, files = _tracked_entries()
    bad = [f"目录 {d}/ 不在 Q-P1 白名单" for d in sorted(dirs) if d not in TOP_DIRS]
    bad += [f"文件 {f} 不在 Q-P1 约定根文件里" for f in sorted(files) if f not in TOP_FILES]
    return bad


def check_secret_not_tracked() -> list[str]:
    tracked = _git_lines("ls-files", "data/settings.ini")
    return [f"data/settings.ini 被 git 跟踪: {tracked[0]}"] if tracked else []


def run_tool(args: list[str]) -> tuple[str, str]:
    """返回 (状态, 输出)；状态 ∈ {ok, bad, skip}。"""
    try:
        # 解释器与工具名都是本模块写死的常量，无外部输入（S603/S607 不适用）
        proc = subprocess.run([sys.executable, "-m", *args],  # noqa: S603
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        return "skip", "未安装"
    err = (proc.stdout + proc.stderr).strip()
    if "No module named" in err:
        return "skip", "未安装"
    return ("ok", "") if not err else ("bad", err)


def report_baseline_sizes(rep: Report, sizes: dict[str, int], base: dict[str, int]) -> None:
    new = {k: v for k, v in sizes.items() if v > base.get(k, 0)}
    rep.add(f"SIZE       超限 {len(sizes)} 项（baseline {len(base)}）；新增/加重 {len(new)} 项")
    for key, val in sorted(new.items()):
        rep.add(f"            新增/加重: {key} = {val} 行")
        rep.fail("SIZE", f"{key}={val}")


def report_baseline_tokens(rep: Report, current: list[str], base: list[str]) -> None:
    new = [t for t in current if t not in set(base)]
    rep.add(f"TOKEN-NAME 违规 {len(current)} 项（baseline {len(base)}）；新增 {len(new)} 项")
    for item in new:
        rep.add(f"            新增: {item}")
        rep.fail("TOKEN-NAME", item)


def report_i18n(rep: Report, count: int, base: int | None) -> None:
    if base is None:
        rep.add(f"I18N       src/ui 中文字面量 {count} 处（无 baseline，仅报告）")
    elif count > base:
        rep.add(f"I18N       src/ui 中文字面量 {count} 处 > baseline {base} → 新增 {count - base} 处")
        rep.fail("I18N", f"{count}>{base}")
    else:
        rep.add(f"I18N       src/ui 中文字面量 {count} 处（baseline {base}，未增加）")


def report_tools(rep: Report) -> None:
    for name, args in TOOLS:
        status, output = run_tool(args)
        if status == "skip":
            rep.add(f"{name:<10} 跳过（{output}）")
        elif status == "ok":
            rep.add(f"{name:<10} 通过（无输出）")
        else:
            rep.add(f"{name:<10} 违规：")
            rep.lines += [f"            {ln}" for ln in output.splitlines()[:20]]
            rep.fail(name, output.splitlines()[0] if output else "")


def write_baseline() -> None:
    sizes = check_sizes()
    tokens_bad = check_token_names()
    ui_cn = count_ui_chinese_literals()
    payload = {
        "_note": "存量债台账（CODE_STANDARDS 门禁 baseline）：只防新增，修好后重写。",
        "sizes": sizes,
        "token_names": tokens_bad,
        "ui_chinese_literals": ui_cn,
    }
    BASELINE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="")
    print(f"已写入 {rel(BASELINE_FILE)}：尺寸 {len(sizes)} 项 / "
          f"令牌命名 {len(tokens_bad)} 项 / i18n 中文字面量 {ui_cn} 处")


def report_items(rep: Report, tag: str, ok_text: str, items: list[str]) -> None:
    rep.add(f"{tag:<10} {ok_text if not items else '违规'}")
    rep.lines += [f"            {item}" for item in items]
    rep.failures += [f"{tag} {item}" for item in items]


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def evaluate() -> Report:
    """跑全部检查，返回报告（供 CLI 与测试共用）。"""
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8")) if BASELINE_FILE.exists() else {}
    rep = Report()
    report_baseline_sizes(rep, check_sizes(), baseline.get("sizes", {}))
    rep.must_zero("SILENT", "`except: pass`", check_silent_swallow())
    rep.must_zero("ID-GEN", "`len()+1` 生成 ID", check_id_generation())
    report_baseline_tokens(rep, check_token_names(), baseline.get("token_names", []))
    report_i18n(rep, count_ui_chinese_literals(), baseline.get("ui_chinese_literals"))
    report_items(rep, "TOP-DIR", "通过", check_top_level())
    report_items(rep, "SECRET", "通过（settings.ini 未入库）", check_secret_not_tracked())
    report_tools(rep)
    return rep


def main() -> int:
    _configure_stdout()

    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="有违规时退出 1（CI）")
    ap.add_argument("--write-baseline", action="store_true", help="按当前状态重写存量台账")
    args = ap.parse_args()
    if args.write_baseline:
        write_baseline()
        return 0

    rep = evaluate()
    print("— 工程规范门禁 —")
    print("\n".join(rep.lines))
    if rep.failures:
        print(f"\n✗ {len(rep.failures)} 项违规")
        return 1 if args.strict else 0
    print("\n✓ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
