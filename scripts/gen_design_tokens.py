#!/usr/bin/env python
"""从令牌单一真值生成 DESIGN_TOKENS.md 的令牌表。

单一真值：src/ui/styles/tokens.json
产出：design/DESIGN_TOKENS.md 中 `<!-- TOKENS:xxx:BEGIN/END -->` 之间内容

用法：
    .venv\\Scripts\\python.exe scripts/gen_design_tokens.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS_FILE = ROOT / "src/ui/styles/tokens.json"
DOC_FILE = ROOT / "design/DESIGN_TOKENS.md"

# 颜色令牌的输出顺序（按用途域，见 CODE_STANDARDS Q-H3）
DOMAIN_ORDER = [
    "bg_", "fg_", "border", "divider", "accent",
    "nav_", "sidebar_", "chat_", "status_bar_",
    "card_", "input_", "btn_", "badge_", "table_", "section_",
    "course_color_", "red", "green", "yellow", "orange",
]

SIZE_ORDER = [
    "SIZE_TINY", "SIZE_CAPTION", "SIZE_BODY_S", "SIZE_BODY", "SIZE_BODY_M",
    "SIZE_BODY_L", "SIZE_ICON", "SIZE_SUBTITLE", "SIZE_TITLE", "SIZE_HEADING", "SIZE_FAB",
]


def _domain_rank(name: str) -> int:
    for i, prefix in enumerate(DOMAIN_ORDER):
        if name.startswith(prefix):
            return i
    return len(DOMAIN_ORDER)


def _color_table(data: dict) -> str:
    light = data["colors"]["light"]
    dark = data["colors"]["dark"]
    notes = data.get("color_notes", {})
    names = sorted(light, key=lambda n: (_domain_rank(n), n))
    lines = ["| Token | 浅色 | 暗色 | 用途 |", "|---|---|---|---|"]
    for name in names:
        lines.append(f"| `{name}` | `{light[name]}` | `{dark.get(name, '—')}` | {notes.get(name, '')} |")
    return "\n".join(lines)


def _size_table(data: dict) -> str:
    sizes = data["sizes"]
    notes = data.get("size_notes", {})
    lines = ["| Token | px | 用途 | 字重 | 行高 |", "|---|---|---|---|---|"]
    for name in SIZE_ORDER:
        meta = notes.get(name, {})
        lines.append(
            f"| `{name}` | {sizes[name]} | {meta.get('use', '')} "
            f"| {meta.get('weight', '')} | {meta.get('line_height', '')} |"
        )
    return "\n".join(lines)


def _replace_between(text: str, tag: str, body: str) -> str:
    begin = f"<!-- TOKENS:{tag}:BEGIN -->"
    end = f"<!-- TOKENS:{tag}:END -->"
    if begin not in text or end not in text:
        raise SystemExit(f"标记缺失: {tag}（请先在 design/DESIGN_TOKENS.md 插入 BEGIN/END 标记）")
    i = text.index(begin) + len(begin)
    j = text.index(end)
    return text[:i] + "\n" + body + "\n" + text[j:]


def main() -> None:
    data = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    doc = DOC_FILE.read_text(encoding="utf-8")

    doc = _replace_between(doc, "colors", _color_table(data))
    doc = _replace_between(doc, "sizes", _size_table(data))

    DOC_FILE.write_text(doc, encoding="utf-8", newline="")
    print(f"updated {DOC_FILE.relative_to(ROOT)}")
    print(f"  colors: {len(data['colors']['light'])} tokens (light) / {len(data['colors']['dark'])} (dark)")
    print(f"  sizes : {len(data['sizes'])} tokens")


if __name__ == "__main__":
    main()
