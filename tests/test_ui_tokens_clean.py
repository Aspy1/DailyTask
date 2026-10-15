"""守卫：UI 代码不得违反令牌约束（CODE_STANDARDS Q-H1/Q-H4）。

等于把 `scripts/check_ui_tokens.py` 的结论固化为测试：
出现违规即失败。若确需豁免，在该行加 `# token-check: ignore`。
"""

from pathlib import Path

from scripts.check_ui_tokens import SKIP_DIRS, SKIP_FILES, check_line, load_tokens

ROOT = Path(__file__).resolve().parent.parent


def test_no_ui_token_violations() -> None:
    names, value_to_name = load_tokens()
    problems: list[str] = []
    for f in (ROOT / "src").rglob("*.py"):
        if f.name in SKIP_FILES or any(s in f.parts for s in SKIP_DIRS):
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for kind, frag, _hint in check_line(line, names, value_to_name, False):
                problems.append(f"{f.relative_to(ROOT)}:{i} [{kind}] {frag}")
    assert not problems, "UI 令牌违规:\n" + "\n".join(problems[:20])
