#!/usr/bin/env python
"""检查 UI 代码是否符合设计令牌约束（CODE_STANDARDS §H）。

单一真值：src/ui/styles/tokens.json

检查项：
  COLOR      字面量颜色（#hex / rgb() / rgba()）→ 建议改用对应 token
  QSS-CLASS  自定义类名 QSS 选择器（R-008：Windows PySide6 不生效）
  QFONT      QFont(..., <int>) 硬编码字号 → 建议 SIZE_* 常量
  TOKEN-NAME 疑似令牌名拼写错误（不在 tokens.json 中）

用法：
    .venv\\Scripts\\python.exe scripts/check_ui_tokens.py [路径 ...] [--strict] [--check-px]

退出码：默认 0（只报告）；`--strict` 时若有违规返回 1（供 CI/pre-commit）。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS_FILE = ROOT / "src/ui/styles/tokens.json"

RE_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RE_RGB = re.compile(r"\brgba?\([^)]*\)")
# 误报豁免：`ERRORS #020` / `条目 #012` 这类**问题编号**不是颜色字面量
RE_ISSUE_REF = re.compile(r"(?:ERRORS|ERR|条目|问题|issue)\s*#\d+\b", re.IGNORECASE)
RE_QSS_CLASS = re.compile(r"(?<![\w.])(_?[A-Z][A-Za-z0-9_]*)\s*\{\{")
RE_PX = re.compile(r"font-size:\s*(\d+)px")
RE_SUBSCRIPT = re.compile(r"\[['\"]([a-z][a-z0-9_]{2,})['\"]\]")
RE_QFONT = re.compile(r"QFont\(")

# 行级豁免：行内出现该标记则跳过（用于图标绘制等非 QSS 场景）
IGNORE_MARK = "token-check: ignore"


def _split_args(s: str) -> list[str]:
    """按顶层逗号切分函数实参（忽略嵌套括号）。"""
    args, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            args.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        args.append(cur)
    return args


def find_qfont_sizes(line: str) -> list[str]:
    """返回 QFont(...) 中第 2 个位置参数为整数字面量的实参（= 硬编码 pointSize）。

    QFont 位置参数顺序为 (family, pointSize, weight, ...)，故只查第 2 个，
    避免把第 3 个参数（字重 600）误判为字号。
    """
    out = []
    for m in RE_QFONT.finditer(line):
        i, depth, j = m.end(), 1, m.end()
        while j < len(line) and depth:
            if line[j] == "(":
                depth += 1
            elif line[j] == ")":
                depth -= 1
            j += 1
        args = _split_args(line[i:j - 1])
        if len(args) >= 2 and re.fullmatch(r"\d+", args[1].strip()):
            out.append(args[1].strip())
    return out

# 令牌名合法前缀（用于识别"疑似拼错的令牌名"）
TOKEN_PREFIXES = (
    "bg_", "fg_", "border", "divider", "accent", "nav_", "sidebar_", "chat_",
    "status_bar_", "card_", "input_", "btn_", "badge_", "table_", "section_",
    "course_color_", "red", "green", "yellow", "orange",
)

SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist"}
# 令牌文件本身就是颜色字面量的定义处，不参与检查
SKIP_FILES = {"tokens.json"}


def load_tokens() -> tuple[set[str], dict[str, str]]:
    data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    names = set(data["colors"]["light"])
    value_to_name: dict[str, str] = {}
    for mode in ("light", "dark"):
        for name, value in data["colors"][mode].items():
            if isinstance(value, str):
                value_to_name.setdefault(value.strip().lower(), name)
    return names, value_to_name


def _color_finding(lit: str, value_to_name: dict[str, str]) -> tuple[str, str, str]:
    """颜色字面量 → (kind, 片段, 建议)。"""
    tok = value_to_name.get(lit.lower())
    hint = f"→ 用 token `{tok}`" if tok else "→ 无对应 token，需在 tokens.json 新增"
    return ("COLOR", lit, hint)


def _find_color_findings(line: str, value_to_name: dict[str, str]) -> list:
    """字面量颜色（#hex / rgb() / rgba()）。"""
    exempt = [m.span() for m in RE_ISSUE_REF.finditer(line)]
    findings = []
    for regex in (RE_HEX, RE_RGB):
        for m in regex.finditer(line):
            if any(lo <= m.start() < hi for lo, hi in exempt):
                continue
            findings.append(_color_finding(m.group(0), value_to_name))
    return findings


def _find_qss_class_findings(line: str) -> list:
    """自定义类名 QSS 选择器（Qt 内置 Q* 类合法）。"""
    findings = []
    for m in RE_QSS_CLASS.finditer(line):
        cls = m.group(1)
        if cls.startswith("Q"):        # Qt 内置类（QWidget/QPushButton…）合法
            continue
        findings.append(("QSS-CLASS", cls, "→ 自定义类选择器在 Windows PySide6 不生效，改用 #objectName"))
    return findings


def _find_token_name_findings(line: str, names: set[str]) -> list:
    """疑似令牌名拼写错误（不在 tokens.json 中，且带合法令牌前缀）。"""
    if line.strip().startswith("#") or "tokens.json" in line:
        return []
    findings = []
    for m in RE_SUBSCRIPT.finditer(line):
        name = m.group(1)
        if name in names:
            continue
        if name.startswith(TOKEN_PREFIXES) or name in {"fff", "fff0"}:
            findings.append(("TOKEN-NAME", name, "→ 不在 tokens.json，疑似拼写错误"))
    return findings


def check_line(line: str, names: set[str], value_to_name: dict[str, str], check_px: bool) -> list[tuple[str, str, str]]:
    """返回 [(kind, 片段, 建议), ...]"""
    if IGNORE_MARK in line:          # 行级豁免
        return []

    findings = _find_color_findings(line, value_to_name)
    findings += _find_qss_class_findings(line)

    for size in find_qfont_sizes(line):
        findings.append(("QFONT", f"pointSize={size}", "→ 用 SIZE_* 常量"))

    if check_px:
        for m in RE_PX.finditer(line):
            findings.append(("PX", m.group(0), "→ 用 SIZE_* 常量"))

    findings += _find_token_name_findings(line, names)
    return findings


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="UI 设计令牌约束检查")
    ap.add_argument("paths", nargs="*", default=["src"], help="要检查的路径（默认 src）")
    ap.add_argument("--strict", action="store_true", help="有违规时返回退出码 1")
    ap.add_argument("--check-px", action="store_true", help="同时检查 font-size 的 Npx")
    return ap.parse_args()


def _collect_files(paths: list[str]) -> list[Path]:
    """展开待检查文件列表（目录递归 *.py，跳过 SKIP_DIRS）。"""
    files: list[Path] = []
    for p in paths:
        path = (ROOT / p) if not Path(p).is_absolute() else Path(p)
        if path.is_dir():
            files.extend(f for f in sorted(path.rglob("*.py")) if not any(s in f.parts for s in SKIP_DIRS))
        elif path.exists():
            files.append(path)
    return files


def _scan_files(files: list[Path], names: set[str], value_to_name: dict[str, str],
                check_px: bool) -> tuple[int, dict[str, int], dict[str, int]]:
    """逐文件逐行检查并打印违规明细，返回 (总数, 按类型, 按文件)。"""
    total = 0
    by_kind: dict[str, int] = {}
    per_file: dict[str, int] = {}

    for f in files:
        if f.name in SKIP_FILES:
            continue
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for kind, frag, hint in check_line(line, names, value_to_name, check_px):
                total += 1
                by_kind[kind] = by_kind.get(kind, 0) + 1
                rel = f.relative_to(ROOT)
                per_file[str(rel)] = per_file.get(str(rel), 0) + 1
                print(f"{rel}:{lineno}: [{kind}] {frag} {hint}")
    return total, by_kind, per_file


def _print_summary(file_count: int, total: int, by_kind: dict[str, int],
                   per_file: dict[str, int]) -> None:
    """打印汇总区。"""
    print("\n—— 汇总 ——")
    print("检查文件:", file_count, "| 违规:", total)
    for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<11} {n}")
    if per_file:
        print("  Top 文件:")
        for name, n in sorted(per_file.items(), key=lambda kv: -kv[1])[:8]:
            print(f"    {n:>3}  {name}")


def main() -> None:
    args = _parse_args()

    names, value_to_name = load_tokens()

    files = _collect_files(args.paths)

    total, by_kind, per_file = _scan_files(files, names, value_to_name, args.check_px)
    _print_summary(len(files), total, by_kind, per_file)

    if args.strict and total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
