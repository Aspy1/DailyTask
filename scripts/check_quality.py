#!/usr/bin/env python
"""工程规范门禁（CODE_STANDARDS 里"能自动检查"的那部分）。

**为什么需要它**：规范里写了不少"检查"方法，但此前只有 ruff 那几条真正进了 CI；
其余（尺寸上限、静默吞异常、ID 生成、令牌命名、i18n 计数、目录白名单、密钥入库）
只有散文约束，回归无人拦。本脚本把可自动化的部分变成门禁。

检查项：

    SIZE        文件 >800 行 / 类 >400 行 / 函数 >60 行        Q-A1（存量走 baseline）
    SILENT      `except ...: pass`（含具名异常，ruff S110 抓不到）Q-I2（必须为 0）
    ID-GEN      `len()+1` 生成 ID                              R-008（必须为 0）
    LOG-STRIP   日志必须可静态剥离（独立语句 / 非块内唯一语句）  Q-D3（必须为 0）
    TOKEN-NAME  色名当令牌名 / 尺寸混进颜色集                   Q-H3（存量走 baseline）
    I18N        src/ui 中**未走 tr()** 的中文字面量计数          Q-N5（不得超过 baseline）
    TOP-DIR     顶层目录/根文件白名单（只查 git 跟踪项）        Q-P1
    SECRET      data/settings.ini 不得被 git 跟踪               Q-E1
    VULTURE     死代码（`vulture --min-confidence 80`）         Q-A4（必须为空）
    RADON       圈复杂度 C 级以上                                Q-C1（必须为空）
    IMPORT-LINTER 分层依赖方向 UI → Services → Models            Q-A2（必须 0 broken）
    SECRETS     detect-secrets 扫描（排除 data/，基线 .secrets.baseline）Q-E1

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
import logging
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = Path(__file__).resolve().parent / "quality_baseline.json"
SECRETS_BASELINE = ROOT / ".secrets.baseline"

logger = logging.getLogger(__name__)

LIMITS = {"file": 800, "class": 400, "func": 60}
UI_DIR = ROOT / "src" / "ui"
# 尺寸检查排除项：验收脚本是线性清单（与 tests/ 同性质，不是产品代码）
SIZE_EXCLUDE = {"scripts/acceptance_check.py"}
# 度量范围除 `src/ui/**` 外，还包含**应用入口**：`app.py` 也有用户可见文本
# （托盘菜单「同步到 GitHub」、托盘气泡「同步完成」…）—— 2026-10-16 全量验收发现漏检。
UI_EXTRA_FILES = (ROOT / "src" / "app.py",)
CHECK_ROOTS = ("src", "scripts", "plugins")
TOOLS = (("VULTURE", ["vulture", "src", "scripts", "plugins", "--min-confidence", "80"]),
         ("RADON", ["radon", "cc", "-n", "C", "-s",
                    # 验收脚本是**线性清单**（80 个断言按顺序走一遍），复杂度天然很高，
                    # 与 tests/ 同性质（不是产品代码）→ 显式排除，不隐藏
                    "--exclude", "scripts/acceptance_check.py",
                    "src", "scripts", "plugins"]))
# 控制台脚本类工具（不能 `-m` 运行）：(名称, 可执行名, 参数)
CONSOLE_TOOLS = (
    ("IMPORT-LINTER", "lint-imports", []),
)
# detect-secrets 的扫描排除项：`data/` 含真实密钥，绝不能进基线
SECRETS_EXCLUDES = ("data/.*", r"\.venv/.*", r"\.git/.*", r".*__pycache__.*",
                    r"\.pytest_cache/.*", r"\.ruff_cache/.*", r"\.secrets\.baseline")
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
LOG_OWNERS = {"logger", "logging", "log"}

# 子进程统一用 UTF-8：Windows 控制台默认 cp936，lint-imports 的横幅会直接崩
_SUBPROC_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

CN_RE = re.compile(r"[\u4e00-\u9fff]")
ID_LEN1_RE = re.compile(r"""f["'][^"']*\{len\([^)]*\)\s*\+\s*1""")
BAD_TOKEN_RE = re.compile(r"^(red|green|yellow|orange|blue|purple)$")

# Q-P1 顶层目录白名单（含 2026-10-16 新增的 design/）
TOP_DIRS = {"src", "scripts", "tests", "plugins", "data", "resources",
            "MD-files", "dev-logs", ".github", "design"}
TOP_FILES = {"main.py", "AGENTS.md", "README.md", "PLAN.md", "ERRORS.md",
             "pyproject.toml", "requirements.txt", "requirements.lock.txt",
             "requirements-dev.txt", ".gitignore", ".importlinter", ".secrets.baseline"}


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
        if rel(f) in SIZE_EXCLUDE:
            continue
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


def _is_logging_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOG_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in LOG_OWNERS)


def _child_blocks(node: ast.AST) -> list[list[ast.stmt]]:
    blocks = []
    for field in ("body", "orelse", "finalbody"):
        value = getattr(node, field, None)
        if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
            blocks.append(value)
    return blocks


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


def check_log_embedded() -> list[str]:
    """Q-D3（真阻断）：日志调用嵌在表达式里（`x = logger.info(...)`、`return logger...`）。

    这类语句无法被 AST 剥离器整体删除（删了会改变返回值/赋值语义）。
    """
    hits = []
    for f in iter_py():
        tree = _parse(f)
        if tree is None:
            continue
        standalone = {id(n.value) for n in ast.walk(tree)
                      if isinstance(n, ast.Expr) and _is_logging_call(n.value)}
        hits += [f"{rel(f)}:{n.lineno} 日志调用嵌在表达式里"
                 for n in ast.walk(tree)
                 if _is_logging_call(n) and id(n) not in standalone]
    return hits


def check_log_sole_statement() -> list[str]:
    """Q-D3（可容忍，走 baseline）：日志是所在块的**唯一语句**。

    剥离器遇到这种块只需补一个 `pass` 即可保持语法合法、行为不变，
    所以它不是剥离的阻断项（2026-10-16 收窄口径，见 CODE_STANDARDS Q-D3）。
    """
    hits = []
    for f in iter_py():
        tree = _parse(f)
        if tree is None:
            continue
        for node in ast.walk(tree):
            hits += [f"{rel(f)}:{block[0].lineno}"
                     for block in _child_blocks(node)
                     if len(block) == 1 and isinstance(block[0], ast.Expr)
                     and _is_logging_call(block[0].value)]
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


def _tr_arg_ids(tree: ast.AST) -> set[int]:
    """被 `tr(...)` 包住的字面量（这些已走 i18n，不算"未国际化"）。"""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr":
            ids.update(id(a) for a in node.args if isinstance(a, ast.Constant))
    return ids


def _const_ids(nodes: list[ast.expr]) -> set[int]:
    return {id(n) for n in nodes if isinstance(n, ast.Constant)}


def _log_arg_ids(tree: ast.AST) -> set[int]:
    """日志调用的实参（日志永远不是界面文字）。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if _is_logging_call(node) and isinstance(node, ast.Call):
            ids |= _const_ids([*node.args, *(kw.value for kw in node.keywords)])
    return ids


def _dict_key_ids(tree: ast.AST) -> set[int]:
    """字典的**键**（数据标识符，不是界面文字；值可能是）。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            ids |= _const_ids(list(node.keys))
    return ids


def _count_cn_in_file(f: Path) -> int:
    """未国际化的中文字面量：排除 docstring、`tr(...)` 实参、日志实参、字典键。"""
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0
    skip = (_docstring_ids(tree) | _tr_arg_ids(tree)
            | _log_arg_ids(tree) | _dict_key_ids(tree))
    return sum(1 for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)
               and id(n) not in skip and CN_RE.search(n.value))


def _ui_py_files() -> Iterator[Path]:
    """度量范围内的界面文件：`src/ui/**` + 应用入口。"""
    yield from (f for f in UI_DIR.rglob("*.py") if "__pycache__" not in f.parts)
    yield from (f for f in UI_EXTRA_FILES if f.exists())


def count_ui_chinese_literals() -> int:
    """界面层**未走 tr()** 的中文字面量总数（Q-N5 的度量口径）。"""
    return sum(count_ui_chinese_literals_by_file().values())


def count_ui_chinese_literals_by_file() -> dict[str, int]:
    """**按文件**统计（存量基线要按文件记账 —— 只记总数会放过"这里少一处、那里多一处"）。"""
    out: dict[str, int] = {}
    for f in _ui_py_files():
        n = _count_cn_in_file(f)
        if n:
            out[str(f.relative_to(ROOT))] = n
    return out


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
                              cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=_SUBPROC_ENV)
    except FileNotFoundError:
        return "skip", "未安装"
    err = (proc.stdout + proc.stderr).strip()
    if "No module named" in err:
        return "skip", "未安装"
    return ("ok", "") if not err else ("bad", err)


def _console_script(name: str) -> Path | None:
    """找控制台脚本。**venv 与非 venv 布局不同**：venv 里 `python.exe` 就在 `Scripts/` 下，
    而 CI（hostedtoolcache）里脚本在 `<python根>/Scripts/`，与 `python.exe` 同级目录**不同**。
    """
    base = Path(sys.executable).parent
    dirs = [base, base / "Scripts", Path(sys.prefix) / "Scripts", Path(sys.prefix) / "bin"]
    for d in dirs:
        for candidate in (d / f"{name}.exe", d / name, d / f"{name}.cmd"):
            if candidate.exists():
                return candidate
    found = shutil.which(name)
    return Path(found) if found else None


def run_console_tool(name: str, args: list[str]) -> tuple[str, str]:
    """控制台脚本类工具（lint-imports）：成功 = 退出码 0。"""
    exe = _console_script(name)
    if exe is None:
        return "skip", "未安装"
    # 可执行文件与参数都是本模块写死的常量，无外部输入（S603/S607 不适用）
    proc = subprocess.run([str(exe), *args], cwd=ROOT, capture_output=True,  # noqa: S603
                          text=True, encoding="utf-8", errors="replace", env=_SUBPROC_ENV)
    out = (proc.stdout + proc.stderr).strip()
    return ("ok", "") if proc.returncode == 0 else ("bad", out)


def run_secrets_scan() -> dict | None:
    """跑 detect-secrets 扫描（**只读**：输出到 stdout，不碰基线文件）。

    注意 `detect-secrets scan --baseline X` 的语义是"**更新**基线"（退出码恒 0），
    不能当校验用；所以这里自己拿扫描结果与基线比对。
    """
    exe = _console_script("detect-secrets")
    if exe is None:
        return None
    args = [str(exe), "scan"]
    for pattern in SECRETS_EXCLUDES:
        args += ["--exclude-files", pattern]
    # 可执行文件与参数都是本模块写死的常量，无外部输入（S603/S607 不适用）
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, env=_SUBPROC_ENV)  # noqa: S603
    try:
        return json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        logger.debug("detect-secrets 输出无法解析", exc_info=True)
        return {}


def check_new_secrets() -> list[str] | None:
    """只报"基线里没有的新发现"；工具未安装时返回 None（调用方标注跳过）。"""
    found = run_secrets_scan()
    if found is None:
        return None
    known: set[tuple[str, str]] = set()
    if SECRETS_BASELINE.exists():
        base = json.loads(SECRETS_BASELINE.read_text(encoding="utf-8")).get("results", {})
        known = {(f, h.get("hashed_secret", "")) for f, hits in base.items() for h in hits}
    return [f"{f}:{h.get('line_number')} ({h.get('type')})"
            for f, hits in found.get("results", {}).items()
            for h in hits if (f, h.get("hashed_secret", "")) not in known]


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


def report_i18n(rep: Report, per_file: dict[str, int], base) -> None:
    """按**文件指纹**比存量 —— 只比总数会放过"这里少一处、那里多一处"（审查的门禁边界）。

    老格式（纯数字）→ 只做总数比较（兼容一次），但会提示"建议重写基线"。
    """
    total = sum(per_file.values())
    if isinstance(base, dict):
        new = {p: n for p, n in per_file.items() if n > int(base.get(p, 0))}
        rep.add(f"I18N       src/ui 中文字面量 {total} 处（按文件比 baseline）；"
                f"新增/加重 {len(new)} 个文件")
        for path, n in sorted(new.items()):
            rep.add(f"            新增: {path} = {n}（baseline {int(base.get(path, 0))}）")
            rep.fail("I18N", f"{path}={n}")
        return
    if base is None:
        rep.add(f"I18N       src/ui 中文字面量 {total} 处（无 baseline，仅报告）")
    elif total > base:
        rep.add(f"I18N       src/ui 中文字面量 {total} 处 > baseline {base} → 新增 {total - base} 处")
        rep.fail("I18N", f"{total}>{base}")
    else:
        rep.add(f"I18N       src/ui 中文字面量 {total} 处（baseline {base}，未增加）")


def report_baseline_count(rep: Report, tag: str, title: str, count: int, base: int | None) -> None:
    """按"计数不得超过 baseline"上报（适合行号会漂移的检查）。"""
    if base is None:
        rep.add(f"{tag:<10} {title} {count} 处（无 baseline，仅报告）")
    elif count > base:
        rep.add(f"{tag:<10} {title} {count} 处 > baseline {base} → 新增 {count - base} 处")
        rep.fail(tag, f"{count}>{base}")
    else:
        rep.add(f"{tag:<10} {title} {count} 处（baseline {base}，未增加）")


def report_tools(rep: Report) -> None:
    for name, args in TOOLS:
        status, output = run_tool(args)
        _report_tool_result(rep, name, status, output)
    for name, exe, args in CONSOLE_TOOLS:
        status, output = run_console_tool(exe, args)
        _report_tool_result(rep, name, status, output)


def _report_tool_result(rep: Report, name: str, status: str, output: str) -> None:
    if status == "skip":
        rep.add(f"{name:<10} 跳过（{output}）")
    elif status == "ok":
        rep.add(f"{name:<10} 通过")
    else:
        rep.add(f"{name:<10} 违规：")
        rep.lines += [f"            {ln}" for ln in output.splitlines()[:20]]
        rep.fail(name, output.splitlines()[0] if output else "")


def write_baseline() -> None:
    sizes = check_sizes()
    tokens_bad = check_token_names()
    ui_cn = count_ui_chinese_literals_by_file()
    payload = {
        "_note": "存量债台账（CODE_STANDARDS 门禁 baseline）：只防新增，修好后重写。",
        "sizes": sizes,
        "token_names": tokens_bad,
        "ui_chinese_literals": ui_cn,
        "log_sole_statement": len(check_log_sole_statement()),
    }
    BASELINE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="")

    scan = run_secrets_scan()
    if scan is not None:
        # 丢掉 `generated_at`：否则每次刷新都会产生一行"假改动"，把 diff 弄脏
        scan.pop("generated_at", None)
        SECRETS_BASELINE.write_text(
            json.dumps(scan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="")
        known = sum(len(v) for v in scan.get("results", {}).values())
        baseline_note = f"密钥基线已刷新（{known} 处已知/误报）"
    else:
        baseline_note = "detect-secrets 未安装，密钥基线未刷新"

    print(f"已写入 {rel(BASELINE_FILE)}：尺寸 {len(sizes)} 项 / "
          f"令牌命名 {len(tokens_bad)} 项 / i18n 中文字面量 {ui_cn} 处 / "
          f"块内唯一日志 {payload['log_sole_statement']} 处；{baseline_note}")


def report_items(rep: Report, tag: str, ok_text: str, items: list[str]) -> None:
    rep.add(f"{tag:<10} {ok_text if not items else '违规'}")
    rep.lines += [f"            {item}" for item in items]
    rep.failures += [f"{tag} {item}" for item in items]


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def evaluate(with_tools: bool = True) -> Report:
    """跑全部检查，返回报告（供 CLI 与测试共用）。

    `with_tools=False` 跳过外部工具（vulture / radon / lint-imports / detect-secrets）——
    测试里没必要重复跑 CI 的"工程规范门禁"步骤（又慢又占内存），只验证轻量检查即可。
    """
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8")) if BASELINE_FILE.exists() else {}
    rep = Report()
    # ⚠ 基线缺失**必须失败**（2026-10-19 审查）：否则存量项全部"无基线可比"，
    # 门禁悄悄变成不拦（`sizes` / `token_names` / `i18n` 都会退化成"仅报告"）。
    if not BASELINE_FILE.exists():
        rep.must_zero("BASELINE", "存量基线文件存在（`scripts/quality_baseline.json`）", ["缺失"])
    else:
        rep.add("BASELINE  存量基线文件存在")
    report_baseline_sizes(rep, check_sizes(), baseline.get("sizes", {}))
    rep.must_zero("SILENT", "`except: pass`", check_silent_swallow())
    rep.must_zero("ID-GEN", "`len()+1` 生成 ID", check_id_generation())
    rep.must_zero("LOG-STRIP", "日志嵌在表达式里", check_log_embedded())
    report_baseline_count(rep, "LOG-ONLY", "日志是块内唯一语句",
                          len(check_log_sole_statement()), baseline.get("log_sole_statement"))
    report_baseline_tokens(rep, check_token_names(), baseline.get("token_names", []))
    report_i18n(rep, count_ui_chinese_literals_by_file(), baseline.get("ui_chinese_literals"))
    report_items(rep, "TOP-DIR", "通过", check_top_level())
    report_items(rep, "SECRET", "通过（settings.ini 未入库）", check_secret_not_tracked())
    if not with_tools:
        rep.add("（外部工具已跳过：由 CI 的 check_quality 步骤负责）")
        return rep
    new_secrets = check_new_secrets()
    if new_secrets is None:
        rep.add("SECRETS    跳过（detect-secrets 未安装）")
    else:
        rep.must_zero("SECRETS", "新出现的疑似密钥", new_secrets)
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
