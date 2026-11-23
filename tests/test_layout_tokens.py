"""布局令牌的**键**必须真实存在。

`check_ui_tokens.py` 只检查"名字像不像令牌"，不检查 `LAYOUT["..."]` 的键是否真的
定义在 `design/tokens.json` —— 2026-10-31 就因此漏了一个
`exam_card_min_height`，直到打开考试面板才 KeyError。

2026-11-02 追加：任务表的行高/表头/列宽/分页也进了 `layout`（原来 120/175/50/64/10
散在 `task_panel.py` 里），这里把新键**逐个点名**，缺一个就红。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = json.loads((ROOT / "design/tokens.json").read_text(encoding="utf-8"))
RE_LAYOUT = re.compile(r'LAYOUT\[\s*"([a-z0-9_]+)"\s*\]')

# 任务表（与课程表共用表头/行高档）的规格键 → 期望值
TABLE_LAYOUT = {
    "table_row_height": 40,
    "table_header_height": 34,
    "table_cell_pad_v": 8,
    "table_cell_pad_h": 12,
    "task_col_course_width": 120,
    "task_col_due_width": 175,
    "task_col_done_width": 50,
    "task_detail_col_width": 64,
    "task_page_size": 10,
}


def test_every_layout_key_exists() -> None:
    known = set(TOKENS.get("layout", {}))
    assert known, "tokens.json 缺少 layout 段"

    used: dict[str, set[str]] = {}
    for path in (ROOT / "src").rglob("*.py"):
        for match in RE_LAYOUT.finditer(path.read_text(encoding="utf-8")):
            used.setdefault(match.group(1), set()).add(
                str(path.relative_to(ROOT)))

    missing = {key: files for key, files in used.items() if key not in known}
    assert not missing, f"代码用了未定义的布局令牌：{missing}"


def test_table_layout_tokens_exist_with_expected_values() -> None:
    """表格族的布局令牌：**存在 + 值对**（表头/行高/列宽/每页行数）。"""
    layout = TOKENS["layout"]
    missing = [key for key in TABLE_LAYOUT if key not in layout]
    assert not missing, f"tokens.json 缺表格布局令牌：{missing}"
    wrong = {key: layout[key] for key, want in TABLE_LAYOUT.items() if layout[key] != want}
    assert not wrong, f"表格布局令牌的值被改了（同时要改 DESIGN_TOKENS.md 与测试）：{wrong}"


def test_table_layout_tokens_have_notes() -> None:
    """每个表格布局令牌都要写用途（否则下一个人不知道 `table_cell_pad_v` 跟谁对齐）。"""
    notes = TOKENS.get("layout_notes", {})
    missing = [key for key in TABLE_LAYOUT if not notes.get(key)]
    assert not missing, f"表格布局令牌没写 layout_notes：{missing}"
