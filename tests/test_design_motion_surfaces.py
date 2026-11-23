"""动效 / 表面角色令牌（`design/tokens.json` 的 `motion` / `surfaces`）。

为什么要有这两组令牌（2026-11-02 切页修复）：

- **motion**：时长/缓动原本是 `animations.py` 里的裸数字（100/150/200），切页那边
  想用"更短的时长 + 更接近 1 的起点"就没有地方可调，于是默认 `fade_in` 从 0 淡入整块
  面板 —— 第一帧是空白，静态外框也跟着淡。
- **surfaces**：各面板自己挑颜色令牌（`bg_root` / `bg_surface`），于是"页脚没有底色、
  工具栏有"这种不一致没人拦。角色只存**令牌名**，不复制色值。

这里守住：键齐全、两套模式都解析得出、时长达标、`surface_color()` 跟着当前模式走。
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOKENS = json.loads((ROOT / "design/tokens.json").read_text(encoding="utf-8"))

MODES = ("light", "dark")
# 转场类时长（面板切换 / 淡入 / 弹层）：R-008 动画条要求 ≤180ms
TRANSITION_DURATIONS = ("duration_fast", "duration_base", "duration_switch")
# `surfaces` 的角色是**约定**：少一个角色意味着某类区域又回去自己挑颜色了
ROLES = ("page", "chrome", "content", "transition", "row_alt", "elevated")


@pytest.fixture(autouse=True)
def _restore_theme_mode(qapp) -> Iterator[None]:
    """本文件会临时改 `theme._current_mode`；测完必须还原，否则后面的 UI 测试换色。"""
    from src.ui.styles import theme

    before = (theme._current_mode, theme._color_cache)
    yield
    theme._current_mode, theme._color_cache = before


# ── motion ──────────────────────────────────────────────────

def test_motion_keys_are_complete() -> None:
    motion = TOKENS.get("motion", {})
    expected = {
        "duration_fast": 100,
        "duration_base": 150,
        "duration_switch": 120,
        "duration_count": 200,
        "switch_fade_from": 0.9,
        "easing": "OutCubic",
        "loading_min_ms": 150,
    }
    missing = [key for key in expected if key not in motion]
    assert not missing, f"tokens.json 的 motion 缺键：{missing}"
    wrong = {key: motion[key] for key, want in expected.items() if motion[key] != want}
    assert not wrong, f"motion 的值被改了（同时要改 DESIGN_TOKENS.md 与测试）：{wrong}"


def test_motion_has_notes_for_every_key() -> None:
    notes = TOKENS.get("motion_notes", {})
    missing = [key for key in TOKENS["motion"] if not notes.get(key)]
    assert not missing, f"motion 令牌没写用途：{missing}"


def test_transition_durations_are_short_enough() -> None:
    """R-008 动画条：转场类时长 ≤180ms（工具不是表演）。"""
    too_long = {key: TOKENS["motion"][key] for key in TRANSITION_DURATIONS
                if TOKENS["motion"][key] > 180}
    assert not too_long, f"转场时长超过 180ms：{too_long}"


def test_count_duration_is_not_a_transition() -> None:
    """数字滚动不是转场（用户在等数字停下），单独一档但要 < 250ms。"""
    assert 180 < TOKENS["motion"]["duration_count"] <= 250


def test_switch_fade_from_is_a_partial_opacity() -> None:
    """切页淡入的起点必须 0 < x < 1。

    = 0 → 第一帧空白（就是这次要修的 bug）；= 1 → 没有淡入，切换是硬跳。
    """
    start = TOKENS["motion"]["switch_fade_from"]
    assert 0.0 < start < 1.0, f"switch_fade_from 越界：{start}"


def test_animations_module_reads_the_motion_tokens() -> None:
    """`animations.py` 不许再自带时长数字：模块常量必须等于令牌值。"""
    from src.ui import animations
    from src.ui.styles.theme import MOTION

    assert MOTION["duration_fast"] == animations.DURATION_FAST
    assert MOTION["duration_base"] == animations.DURATION_BASE
    assert MOTION["duration_count"] == animations.DURATION_COUNT


def test_easing_token_maps_to_a_real_curve(qapp) -> None:
    from PySide6.QtCore import QEasingCurve

    from src.ui import animations
    from src.ui.styles.theme import MOTION

    curve = QEasingCurve.Type[MOTION["easing"]]
    assert curve == QEasingCurve.Type.OutCubic
    assert curve == animations.EASING


def test_fade_in_start_defaults_to_zero(qapp) -> None:
    """`fade_in` 的 `start` 默认 0 —— 其它调用点（卡片/弹层）行为不变。"""
    from PySide6.QtWidgets import QWidget

    from src.ui import animations

    widget = QWidget()
    anim = animations.fade_in(widget)
    assert anim is not None
    assert anim.startValue() == 0.0
    widget.setGraphicsEffect(None)


def test_fade_in_start_is_applied_synchronously(qapp) -> None:
    """起点必须**立刻**写进 effect：否则"已显示但动画还没跑"的那一帧仍是旧透明度。"""
    from PySide6.QtWidgets import QWidget

    from src.ui import animations

    widget = QWidget()
    animations.fade_in(widget, duration=120, start=0.9)
    effect = widget.graphicsEffect()
    assert effect is not None and effect.opacity() == pytest.approx(0.9)
    widget.setGraphicsEffect(None)


# ── surfaces ────────────────────────────────────────────────

def test_surface_roles_are_complete() -> None:
    surfaces = TOKENS.get("surfaces", {})
    missing = [role for role in ROLES if role not in surfaces]
    assert not missing, f"tokens.json 的 surfaces 缺角色：{missing}"


def test_surface_roles_reference_color_tokens_only() -> None:
    """角色只能指向**颜色令牌名**，不许把色值抄进来（否则切主题要改两处）。"""
    colors = TOKENS["colors"]["light"]
    for role, token in TOKENS["surfaces"].items():
        assert isinstance(token, str) and token in colors, \
            f"surfaces.{role} 不是颜色令牌名：{token!r}"


@pytest.mark.parametrize("mode", MODES)
def test_surface_roles_resolve_in_both_modes(mode: str) -> None:
    for role, token in TOKENS["surfaces"].items():
        value = TOKENS["colors"][mode].get(token)
        assert value, f"{mode} 缺颜色令牌 {token}（surfaces.{role} 指向它）"
        assert value.startswith(("#", "rgb")), f"{mode}.{token} 不是色值：{value!r}"


def test_surface_roles_have_notes() -> None:
    notes = TOKENS.get("surface_notes", {})
    missing = [role for role in TOKENS["surfaces"] if not notes.get(role)]
    assert not missing, f"表面角色没写用途：{missing}"


def test_surface_color_follows_the_current_mode() -> None:
    from src.ui.styles import theme

    for mode in MODES:
        theme._current_mode = mode
        theme._color_cache = None
        for role, token in TOKENS["surfaces"].items():
            assert theme.surface_color(role) == TOKENS["colors"][mode][token]


def test_chrome_surface_is_a_distinct_layer_from_content() -> None:
    """外框与内容必须是**两层**（同色的话"只淡内容区"就看不出边界，也分不了层）。"""
    surfaces = TOKENS["surfaces"]
    for mode in MODES:
        colors = TOKENS["colors"][mode]
        assert colors[surfaces["chrome"]] != colors[surfaces["content"]]


def test_surface_roles_are_exported_by_theme() -> None:
    from src.ui.styles.theme import LAYOUT, MOTION, SURFACES

    assert TOKENS["surfaces"] == SURFACES
    assert TOKENS["motion"] == MOTION
    assert LAYOUT["table_header_height"] == TOKENS["layout"]["table_header_height"]
