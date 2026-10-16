"""宽松取值（纯函数）：把外部 JSON 里的脏值安全转成 `int` / `date`。

数据可能被桌面端、TG bot、GitHub Actions 三方写入，字段缺失/类型错/格式旧都很常见。
这里统一"不抛异常"的口径，避免各处各写一遍 `try/except`。
"""

from datetime import date


def as_int(value: object) -> int | None:
    """宽松取整：`"5"` / `5.0` → 5；`None` / `"x"` → None。"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_date(value: object) -> date | None:
    """宽松解析日期：接受 `date`、`"YYYY-MM-DD"`、`"YYYY-MM-DDThh:mm"`；否则 None。"""
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
