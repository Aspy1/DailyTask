"""区域（locale）守卫：日期/数字控件必须显示 ASCII 数字。

**为什么需要**：本机系统区域是 `zh_HK`，而 zh_HK 在 CLDR 里用 **CJK 数字**
（〇〡〢〣 汉字/杭州码数字），Qt 的 `QDateEdit` / `QSpinBox` / `QDateTimeEdit`
会把 `2026-10-19` 显示成 `〢〇〢〦-〡〇-〡〩` —— 用户完全看不懂。

项目里曾有**两处各自打补丁**（`inventory_panel` / `schedule_view` 给单个控件
`setLocale(English, US)`），但只要新增日期/数字控件就会再中一次。
现在由 `src.app.configure_locale()` 统一设默认区域，这里守住它。
"""

from PySide6.QtCore import QDate, QLocale
from PySide6.QtWidgets import QDateEdit, QSpinBox

ASCII = set("0123456789-/. :,")


def test_configure_locale_gives_ascii_digits(qapp) -> None:
    from src.app import configure_locale

    configure_locale()
    # 只要求"数字是 ASCII"：具体格式（千分位、日期顺序）随区域变化，不该被钉死
    assert set(QLocale().toString(2026)) <= ASCII, QLocale().toString(2026)
    short = QLocale().toString(QDate(2026, 10, 19), QLocale.FormatType.ShortFormat)
    assert set(short) <= ASCII, f"日期里出现了非 ASCII 字符：{short!r}"


def test_date_edit_and_spinbox_render_ascii(qapp) -> None:
    """直接盯住用户可见的症状。"""
    from src.app import configure_locale

    configure_locale()

    date_edit = QDateEdit()
    date_edit.setDate(QDate(2026, 10, 19))
    assert set(date_edit.text()) <= ASCII, date_edit.text()

    spin = QSpinBox()
    spin.setValue(20)
    assert set(spin.text()) <= ASCII, spin.text()
