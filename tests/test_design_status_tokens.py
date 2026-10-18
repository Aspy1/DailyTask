"""状态色必须**成套**（success / warning / danger 三档同构）。

起因（第四批遗留的"令牌体系 §3 · 状态成套"）：`green` 只有 `green_tint`，而
`orange` / `red` 还有 `_tint_weak` 和 `_fill`；三档都**没有描边色**。于是
`schedule_view` 的「撤销 / 保存」按钮只能**手工拼 alpha**（`{c['red']}30`）——
那正是 U4 明令禁止的写法：Qt 的 QSS 把 8 位十六进制当 **AARRGGBB**，而且一旦令牌
改成 `rgba(...)`，拼出来的字符串直接就是坏值。

这组测试把"成套"变成**可执行的不变量**：缺一个成员就红。
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))

# 档名 → 底色/徽章那一族的**色名**前缀（历史命名，不能改：改了就断掉既有引用）
STATUS_COLOR = {"success": "green", "warning": "orange", "danger": "red"}
# 卡片淡底 / 实心徽章：`<色名><后缀>`
CARD_MEMBERS = ("", "_tint", "_tint_weak", "_fill")
# 状态按钮：`btn_<档名><后缀>`
BTN_MEMBERS = ("_fg", "_bg", "_bg_hover", "_border")
MODES = ("dark", "light")

# 拼 alpha：`{c['red']}30` / `{c["green"]}60`
HAND_ROLLED_ALPHA = re.compile(r"""\{c\[['"](green|orange|red|yellow)['"]\]\}[0-9a-fA-F]{2}\b""")


def _keys(status: str, color: str) -> list[str]:
    return ([f"{color}{s}" for s in CARD_MEMBERS]
            + [f"btn_{status}{s}" for s in BTN_MEMBERS])


@pytest.mark.parametrize("status,color", sorted(STATUS_COLOR.items()))
def test_status_family_is_complete(status: str, color: str) -> None:
    """每档状态在**两种模式**下都要有完整成员，且每个键都有 `color_notes`。"""
    for mode in MODES:
        table = TOKENS["colors"][mode]
        missing = [k for k in _keys(status, color) if k not in table]
        assert not missing, f"{mode} 缺 {status} 档的令牌：{missing}"
    assert not [k for k in _keys(status, color) if k not in TOKENS["color_notes"]], \
        f"{status} 档有令牌没写说明（color_notes）"


def test_status_families_are_parallel() -> None:
    """三档的成员**形状**一致 —— 把色名/档名换成占位符后，三组应当完全相同。"""
    shapes = set()
    for status, color in STATUS_COLOR.items():
        shape = {k.replace(color, "<C>").replace(status, "<S>") for k in _keys(status, color)}
        shapes.add(frozenset(shape))
    assert len(shapes) == 1, f"三档成员形状不一致：{sorted(s for s in shapes)}"


def test_status_button_bg_and_border_are_real_color_values() -> None:
    """状态按钮的底色/描边必须是**完整可用的颜色值**（`rgba(...)` 或 `#RRGGBB`）。

    这条守住"别再回头去拼 alpha"：值本身自带透明度，调用点直接塞进 QSS。
    """
    for mode in MODES:
        for status in STATUS_COLOR:
            for suffix in ("_bg", "_bg_hover", "_border"):
                value = TOKENS["colors"][mode][f"btn_{status}{suffix}"]
                assert value.startswith("rgba(") or re.fullmatch(r"#[0-9A-Fa-f]{6}", value), \
                    f"{mode}.btn_{status}{suffix} 不是完整颜色值：{value!r}"


def test_no_hand_rolled_alpha_on_status_colors() -> None:
    """`src/` 里不许再出现 `{c['red']}30` 这种"色值 + 两位 hex"的拼法（U4 同类）。"""
    bad = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HAND_ROLLED_ALPHA.search(line):
                bad.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:90]}")
    assert not bad, "手工拼 alpha 的写法（应改用成套令牌）：\n" + "\n".join(bad)
