"""漂移守卫：DESIGN_TOKENS.md 的生成表必须与 tokens.json 一致。

失败时说明有人手改了生成区（或改了 tokens.json 但没跑生成器）：
    .venv\\Scripts\\python.exe scripts/gen_design_tokens.py
"""

import json
from pathlib import Path

from scripts.gen_design_tokens import _color_table, _size_table

ROOT = Path(__file__).resolve().parent.parent


def test_design_tokens_doc_in_sync() -> None:
    data = json.loads((ROOT / "src/ui/styles/tokens.json").read_text(encoding="utf-8"))
    doc = (ROOT / "design/DESIGN_TOKENS.md").read_text(encoding="utf-8")

    assert _color_table(data) in doc, "颜色表与 tokens.json 不同步 → 跑 gen_design_tokens.py"
    assert _size_table(data) in doc, "字号表与 tokens.json 不同步 → 跑 gen_design_tokens.py"
