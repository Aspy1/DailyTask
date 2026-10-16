"""i18n 包。

便于 `from src.i18n import tr`；底层实现见 `loader.py`。
"""

from src.i18n.loader import I18nLoader, t, tr

__all__ = ["I18nLoader", "t", "tr"]
