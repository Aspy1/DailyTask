"""守卫：UI 代码不得违反令牌约束（CODE_STANDARDS Q-H1/Q-H4）。

等于把 `scripts/check_ui_tokens.py` 的结论固化为测试：
出现违规即失败。若确需豁免，在该行加 `# token-check: ignore`。
"""

from pathlib import Path

from scripts.check_ui_tokens import (
    SKIP_DIRS,
    SKIP_FILES,
    check_line,
    load_tokens,
    mask_doc_lines,
)

ROOT = Path(__file__).resolve().parent.parent


def test_no_ui_token_violations() -> None:
    names, value_to_name = load_tokens()
    problems: list[str] = []
    for f in (ROOT / "src").rglob("*.py"):
        if f.name in SKIP_FILES or any(s in f.parts for s in SKIP_DIRS):
            continue
        lines = f.read_text(encoding="utf-8").splitlines()
        masked = mask_doc_lines(lines)
        for i, line in enumerate(lines, 1):
            if masked[i - 1]:
                continue
            for kind, frag, _hint in check_line(line, names, value_to_name, False):
                problems.append(f"{f.relative_to(ROOT)}:{i} [{kind}] {frag}")
    assert not problems, "UI 令牌违规:\n" + "\n".join(problems[:20])


def test_issue_reference_is_not_a_color() -> None:
    """`ERRORS #020` 这类问题编号不能被当成颜色字面量（否则代码注释没法写引用）。"""
    names, value_to_name = load_tokens()
    assert not check_line("    # 见 ERRORS #020", names, value_to_name, False)
    assert not check_line("    # 见 条目 #012 说明", names, value_to_name, False)
    # 真颜色仍要报出来
    assert check_line('    color = "#ff0000"', names, value_to_name, False)

def test_docstring_colors_are_not_violations() -> None:
    """文档字符串/注释里的 rgba(...) 与 #hex 是说明文字，不该被判成颜色。"""
    q3 = chr(34) * 3
    lines = [
        q3 + "把 token 的 rgba(r,g,b,a) 解析成 QColor。" + q3,
        "    # 例如 #ff0000 表示红色",
        '    self.setStyleSheet("color: #ff0000;")',
    ]
    assert mask_doc_lines(lines) == [True, True, False]

    names, value_to_name = load_tokens()
    assert not check_line(lines[0], names, value_to_name, False)   # 说明文字，不报
    assert check_line(lines[2], names, value_to_name, False)       # 真颜色，要报
