"""i18n 加载器。

**字符串来源**：`zh-CN.json`（主文件）+ `zh-CN.d/*.json`（**分片**，按文件名排序合并）。

为什么要分片：键按模块拆分（`panel_task.json` / `dialog_course.json` …），
既方便定位"某处文字在哪"，也避免多人/多任务同时改同一个大 JSON。
**文字只存在于 JSON**，代码里只出现键（CODE_STANDARDS Q-N5）。

用法：
    from src.i18n.loader import tr
    label.setText(tr("panel.task.title"))
    label.setText(tr("status.week", n=5))       # 占位符：JSON 里写 "第 {n} 周"
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FALLBACK_LOCALE = "zh-CN"


class I18nLoader:
    _instance: "I18nLoader | None" = None
    _strings: dict          # 实例属性，见 CODE_STANDARDS Q-B2 / RUF012
    _loaded: bool = False
    locale: str = FALLBACK_LOCALE

    def __new__(cls) -> "I18nLoader":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._strings = {}
            cls._instance = inst
        return cls._instance

    @staticmethod
    def _locale_files(locale: str) -> list[Path]:
        base = Path(__file__).parent
        files: list[Path] = []
        main = base / f"{locale}.json"
        if main.exists():
            files.append(main)
        frag_dir = base / f"{locale}.d"
        if frag_dir.is_dir():
            files += sorted(frag_dir.glob("*.json"))
        return files

    def load(self, locale: str = FALLBACK_LOCALE) -> None:
        """加载语言包；该语言不存在时**回退**到 zh-CN（不抛异常，避免启动即崩）。"""
        files = self._locale_files(locale)
        if not files and locale != FALLBACK_LOCALE:
            logger.warning("语言包 %s 不存在，回退到 %s", locale, FALLBACK_LOCALE)
            locale, files = FALLBACK_LOCALE, self._locale_files(FALLBACK_LOCALE)
        if not files:
            raise FileNotFoundError(f"Language file not found for locale: {locale}")

        strings: dict[str, str] = {}
        for path in files:
            strings.update(json.loads(path.read_text(encoding="utf-8")))
        self._strings = strings
        self.locale = locale
        self._loaded = True

    def tr(self, key: str, default: str = "", **fmt: object) -> str:
        if not self._loaded:
            self.load()
        text = self._strings.get(key)
        if text is None:
            logger.debug("i18n 缺少键: %s", key)
            text = default or key
        if fmt:
            try:
                text = text.format(**fmt)
            except (KeyError, IndexError):
                logger.warning("i18n 占位符不匹配: %s（%s）", key, fmt)
        return text


t = I18nLoader()


def tr(key: str, default: str = "", **fmt: object) -> str:
    return t.tr(key, default, **fmt)
