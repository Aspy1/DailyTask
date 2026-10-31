"""布局令牌的**键**必须真实存在。

`check_ui_tokens.py` 只检查"名字像不像令牌"，不检查 `LAYOUT["..."]` 的键是否真的
定义在 `design/tokens.json` —— 2026-10-31 就因此漏了一个
`exam_card_min_height`，直到打开考试面板才 KeyError。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = json.loads((ROOT / "design/tokens.json").read_text(encoding="utf-8"))
RE_LAYOUT = re.compile(r'LAYOUT\[\s*"([a-z0-9_]+)"\s*\]')


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
