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
RE_QSS_CLASS = re.compile(r"(?<![\w.])(_?[A-Z][A-Za-z0-9_]*)\s*\{\{")
RE_QFONT_INT = re.compile(r"QFont\([^)]*,\s*(\d+)\s*\)")
RE_PX = re.compile(r"font-size:\s*(\d+)px")
RE_SUBSCRIPT = re.compile(r"\[['\"]([a-z][a-z0-9_]{2,})['\"]\]")

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


def check_line(line: str, names: set[str], value_to_name: dict[str, str], check_px: bool):
    """返回 [(kind, 片段, 建议), ...]"""
    findings = []
    stripped = line.strip()

    for m in RE_HEX.finditer(line):
        lit = m.group(0)
        tok = value_to_name.get(lit.lower())
        hint = f"→ 用 token `{tok}`" if tok else "→ 无对应 token，需在 tokens.json 新增"
        findings.append(("COLOR", lit, hint))

    for m in RE_RGB.finditer(line):
        lit = m.group(0)
        tok = value_to_name.get(lit.lower())
        hint = f"→ 用 token `{tok}`" if tok else "→ 无对应 token，需在 tokens.json 新增"
        findings.append(("COLOR", lit, hint))

    for m in RE_QSS_CLASS.finditer(line):
        cls = m.group(1)
        if cls.startswith("Q"):        # Qt 内置类（QWidget/QPushButton…）合法
            continue
        findings.append(("QSS-CLASS", cls, "→ 自定义类选择器在 Windows PySide6 不生效，改用 #objectName"))

    for m in RE_QFONT_INT.finditer(line):
        findings.append(("QFONT", m.group(0), "→ 用 SIZE_* 常量"))

    if check_px:
        for m in RE_PX.finditer(line):
            findings.append(("PX", m.group(0), "→ 用 SIZE_* 常量"))

    if not stripped.startswith("#") and "tokens.json" not in line:
        for m in RE_SUBSCRIPT.finditer(line):
            name = m.group(1)
            if name in names:
                continue
            if name.startswith(TOKEN_PREFIXES) or name in {"fff", "fff0"}:
                findings.append(("TOKEN-NAME", name, "→ 不在 tokens.json，疑似拼写错误"))

    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description="UI 设计令牌约束检查")
    ap.add_argument("paths", nargs="*", default=["src"], help="要检查的路径（默认 src）")
    ap.add_argument("--strict", action="store_true", help="有违规时返回退出码 1")
    ap.add_argument("--check-px", action="store_true", help="同时检查 font-size 的 Npx")
    args = ap.parse_args()

    names, value_to_name = load_tokens()

    files: list[Path] = []
    for p in args.paths:
        path = (ROOT / p) if not Path(p).is_absolute() else Path(p)
        if path.is_dir():
            files.extend(f for f in sorted(path.rglob("*.py")) if not any(s in f.parts for s in SKIP_DIRS))
        elif path.exists():
            files.append(path)

    total = 0
    by_kind: dict[str, int] = {}
    per_file: dict[str, int] = {}

    for f in files:
        if f.name in SKIP_FILES:
            continue
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for kind, frag, hint in check_line(line, names, value_to_name, args.check_px):
                total += 1
                by_kind[kind] = by_kind.get(kind, 0) + 1
                rel = f.relative_to(ROOT)
                per_file[str(rel)] = per_file.get(str(rel), 0) + 1
                print(f"{rel}:{lineno}: [{kind}] {frag} {hint}")

    print("\n—— 汇总 ——")
    print("检查文件:", len(files), "| 违规:", total)
    for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<11} {n}")
    if per_file:
        print("  Top 文件:")
        for name, n in sorted(per_file.items(), key=lambda kv: -kv[1])[:8]:
            print(f"    {n:>3}  {name}")

    if args.strict and total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
