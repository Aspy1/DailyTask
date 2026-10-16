"""i18n 守卫（CODE_STANDARDS Q-N5）。

四道保证：
1. 代码里用到的每个 `tr("键")` 都**存在**于语言包（否则 UI 会显示裸键名）；
2. 键必须**命名空间化**（`<area>.<subarea>.<name>`，小写 + 下划线 + 点号）；
3. 同一个键**不重复定义**（含主文件与分片之间）；
4. 加载器能**回退**（缺语言包不崩）且支持占位符格式化。
"""

import ast
import json
import re
from pathlib import Path

import pytest

from src.i18n.loader import FALLBACK_LOCALE, I18nLoader, tr

ROOT = Path(__file__).resolve().parent.parent
I18N_DIR = ROOT / "src" / "i18n"
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def _pairs(path: Path) -> list[tuple[str, str]]:
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=lambda kv: kv)


def _locale_files(locale: str = FALLBACK_LOCALE) -> list[Path]:
    files = []
    main = I18N_DIR / f"{locale}.json"
    if main.exists():
        files.append(main)
    frag = I18N_DIR / f"{locale}.d"
    if frag.is_dir():
        files += sorted(frag.glob("*.json"))
    return files


def _all_strings() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in _locale_files():
        out.update(dict(_pairs(path)))
    return out


def _tr_keys_in_src() -> list[tuple[str, int, str]]:
    """扫描 src/ 下所有 `tr("键")` 的字面量键。"""
    found = []
    for f in sorted((ROOT / "src").rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", None) != "tr":
                continue
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                found.append((f.relative_to(ROOT).as_posix(), node.lineno, node.args[0].value))
    return found


def test_every_used_key_exists() -> None:
    keys = set(_all_strings())
    missing = [f"{path}:{line} {key}" for path, line, key in _tr_keys_in_src()
               if key not in keys]
    assert not missing, "以下 tr() 键在语言包里不存在：\n" + "\n".join(missing)


def test_keys_are_namespaced() -> None:
    bad = [k for k in _all_strings() if not KEY_RE.match(k)]
    assert not bad, f"键不符合 <area>.<subarea>.<name> 约定: {bad}"


def test_no_duplicate_keys() -> None:
    seen: dict[str, str] = {}
    dupes = []
    for path in _locale_files():
        for key, _value in _pairs(path):
            if key in seen:
                dupes.append(f"{key}（{seen[key]} 与 {path.name}）")
            seen[key] = path.name
    assert not dupes, f"重复定义的键: {dupes}"


def test_loader_falls_back_when_locale_missing() -> None:
    loader = I18nLoader()
    loader.load("xx-YY")                       # 不存在的语言包 → 回退 zh-CN
    assert loader.locale == FALLBACK_LOCALE
    assert loader.tr("app.name")


def test_tr_returns_key_when_missing() -> None:
    assert tr("no.such.key") == "no.such.key"


def test_tr_formats_placeholders() -> None:
    loader = I18nLoader()
    loader.load()
    loader._strings["test.placeholder"] = "第 {n} 周"
    assert tr("test.placeholder", n=5) == "第 5 周"


@pytest.mark.parametrize("locale", [FALLBACK_LOCALE])
def test_default_locale_loads(locale: str) -> None:
    loader = I18nLoader()
    loader.load(locale)
    assert loader.tr("app.name")
