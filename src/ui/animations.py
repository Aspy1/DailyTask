"""动效模板集合（CODE_STANDARDS Q-H16）。

规则（`AllTheFiles.md` R-008 动画条，2026-10-16 修订）：

- **只做 opacity / 位移**；**禁止**动画化布局尺寸（宽高/间距）与侧边栏手风琴
- 时长 ≤180ms，缓动 `OutCubic`
- 动画对象必须**保引用**（被 GC 会中断），控件销毁时停止

历史坑（`ERRORS #031`）：当年把动画做在 QSS 画出来的箭头上（QSS 无 transform），
并且动画化了菜单几何（每帧 layout + 重绘）→ 方向错乱 + 持续闪烁，于是整条禁掉了动画。

出问题时的总开关：`set_enabled(False)` 可一次性关掉所有动效。
"""

import re

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from src.ui.styles.theme import MOTION

# 时长 / 缓动**只从令牌读**（design/tokens.json 的 `motion`）：
# 早先这里是 100 / 150 / 200 三个裸数字，切页那边也没法单独指定"更短的时长"。
DURATION_FAST = MOTION["duration_fast"]
DURATION_BASE = MOTION["duration_base"]
DURATION_COUNT = MOTION["duration_count"]
# `easing` 存的是 `QEasingCurve.Type` 的**成员名**（不写枚举序号，也不写数字）
EASING: QEasingCurve.Type = QEasingCurve.Type[MOTION["easing"]]

ENABLED = True

# 保引用：QPropertyAnimation 没有 Python 引用会被 GC，动画中途停住
_RUNNING: dict[int, list] = {}


def set_enabled(enabled: bool) -> None:
    """总开关（用户觉得闪/卡时一键关掉）。"""
    global ENABLED
    ENABLED = enabled


def _keep(widget: QWidget, *objs: object) -> None:
    _RUNNING[id(widget)] = list(objs)


def _opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    """复用已有的透明效果（反复创建会让控件发虚）。"""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    return effect


def fade_in(widget: QWidget, duration: int = DURATION_BASE,
            start: float = 0.0) -> QPropertyAnimation | None:
    """淡入（只动 opacity，不动几何）。

    `start` 是**起点不透明度**（默认 0 → 从全透明淡入，与旧行为一致）。
    切页这类"内容已经在那儿了"的场景要传一个接近 1 的起点（`motion.switch_fade_from`）：
    起点 0 会让第一帧整块空白，用户看到的是"闪一下"而不是"淡入"。

    ⚠ 起点**同步**写进 effect（不等动画第一次 tick）：否则"控件已显示、动画还没跑"
    的那一帧仍然是上一帧的透明度 —— 正是"第一帧空白"的成因。
    """
    if not ENABLED:
        return None
    effect = _opacity_effect(widget)
    effect.setOpacity(start)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setEasingCurve(EASING)
    _keep(widget, effect, anim)
    # 结束后摘掉透明效果：QGraphicsOpacityEffect 会走离屏渲染，留着会让面板发虚
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped)
    return anim


def fade_popup(widget: QWidget, duration: int = DURATION_FAST) -> QPropertyAnimation | None:
    """弹层淡入（QMenu 等 popup 窗口）：动 `windowOpacity`，不碰几何。"""
    if not ENABLED:
        return None
    widget.setWindowOpacity(0.0)
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(EASING)
    _keep(widget, anim)
    # exec() 会阻塞在嵌套事件循环里：用 0ms 定时器把动画推进去
    QTimer.singleShot(0, lambda: anim.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped))
    return anim


def count_to(label, value: float, fmt: str = "{:.0f}",
             duration: int = DURATION_COUNT) -> QVariantAnimation | None:
    """数字滚动到目标值（汇总卡/状态栏这类数值变化）。

    起点从控件当前文本里解析；解析不到或已经是目标值就直接设值、不动画。
    """
    if not ENABLED:
        label.setText(fmt.format(value))
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", label.text() or "")
    start = float(match.group()) if match else value
    if start == value:
        label.setText(fmt.format(value))
        return None

    var = QVariantAnimation(label)
    var.setStartValue(start)
    var.setEndValue(value)
    var.setDuration(duration)
    var.setEasingCurve(EASING)
    var.valueChanged.connect(lambda v: label.setText(fmt.format(float(v))))
    _keep(label, var)
    var.start(QVariantAnimation.DeletionPolicy.KeepWhenStopped)
    return var
