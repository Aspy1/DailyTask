"""天气统计/缓存读写守卫（`services/weather_store.py`）。

**回归背景**（2026-10-16 全量验收发现的真崩溃）：
`weather_stats.json` 由 now / 7d 两个 worker 并发写，写入用的是非原子 `write_text`
→ 文件出现"尾部多一个 `}`"的损坏形态；而设置面板在**启动时**读它且没有保护
→ `JSONDecodeError` 让**应用启动即崩**。
"""

import json
import threading
from datetime import datetime
from pathlib import Path

from src.services import weather_store


def _corrupt_like_concurrent_write(path: Path, extra: str = "}") -> None:
    """构造真实遇到的损坏形态：完整 JSON 后面多出残留内容。

    ⚠ 日期用**动态当天**：写死日期会在跨午夜（或跨月）时让断言失效 ——
    2026-10-17 凌晨实测踩到（fixture 里是 10-16、断言算的是 10-17）。
    """
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")
    good = json.dumps({"daily": {day: {"now": 1, "7d": 0, "warning": 0, "total": 1}},
                       "monthly": {month: {"now": 1, "7d": 0, "warning": 0, "total": 1}}},
                      indent=2)
    path.write_text(good + extra, encoding="utf-8")


# ── 读：坏文件永不抛 ────────────────────────────────────────

def test_read_missing_file_returns_empty(tmp_path) -> None:
    assert weather_store.read_json_safe(tmp_path / "nope.json") == {}


def test_read_valid_file(tmp_path) -> None:
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert weather_store.read_json_safe(path) == {"a": 1}


def test_read_salvages_file_with_trailing_garbage(tmp_path) -> None:
    """真实损坏形态：**能救回第一个完整对象**（用户数据里的调用统计不该白丢）。"""
    path = tmp_path / "weather_stats.json"
    _corrupt_like_concurrent_write(path)
    stats = weather_store.read_json_safe(path)
    month = datetime.now().strftime("%Y-%m")
    assert stats["monthly"][month]["total"] == 1


def test_read_totally_broken_returns_empty(tmp_path) -> None:
    path = tmp_path / "x.json"
    path.write_text("这不是 JSON", encoding="utf-8")
    assert weather_store.read_json_safe(path) == {}


def test_read_non_dict_returns_empty(tmp_path) -> None:
    path = tmp_path / "x.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert weather_store.read_json_safe(path) == {}


# ── 写：原子 + 并发安全 ─────────────────────────────────────

def test_write_json_atomic_produces_valid_json(tmp_path) -> None:
    path = tmp_path / "x.json"
    weather_store.write_json_atomic(path, {"k": "值"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": "值"}
    assert not list(tmp_path.glob("*.tmp")), "不应残留 .tmp 文件"


def test_record_request_increments_and_creates(tmp_path) -> None:
    path = tmp_path / "weather_stats.json"
    weather_store.record_request(path, "now")
    weather_store.record_request(path, "7d")
    stats = json.loads(path.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    assert stats["daily"][today]["now"] == 1
    assert stats["daily"][today]["7d"] == 1
    assert stats["daily"][today]["total"] == 2
    assert stats["last_request"]["type"] == "7d"


def test_record_request_recovers_from_corrupted_file(tmp_path) -> None:
    path = tmp_path / "weather_stats.json"
    _corrupt_like_concurrent_write(path)
    weather_store.record_request(path, "now")
    stats = json.loads(path.read_text(encoding="utf-8"))     # 修复后可正常解析
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    assert stats["daily"][today]["now"] == 2                 # 旧数据 1 次 + 新增 1 次
    assert stats["monthly"][month]["total"] == 2             # 旧数据被救回并累加


def test_concurrent_record_requests_keep_file_valid(tmp_path) -> None:
    """并发写（真实场景：now / 7d 两个 worker）不能让文件损坏。"""
    path = tmp_path / "weather_stats.json"
    threads = [threading.Thread(target=weather_store.record_request, args=(path, kind))
               for kind in ("now", "7d") * 15]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = json.loads(path.read_text(encoding="utf-8"))     # 不抛即为通过
    today = datetime.now().strftime("%Y-%m-%d")
    assert stats["daily"][today]["total"] == 30
    assert not list(tmp_path.glob("*.tmp"))


# ── 启动路径守卫：设置面板读到损坏文件不能崩 ────────────────

def test_settings_panel_survives_corrupted_stats(qapp, tmp_path, monkeypatch) -> None:
    """回归：损坏的 `weather_stats.json` 曾让应用**启动即崩**（设置面板构造时读它）。"""
    from src.services.ai_service import AIService
    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.panels.settings_panel import SettingsPanel

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _corrupt_like_concurrent_write(data_dir / "weather_stats.json")
    # 设置面板按 __file__ 上溯找 data/ —— 这里直接把它读的那个路径换掉
    monkeypatch.setattr("src.ui.panels.settings_panel.Path",
                        lambda *a: data_dir / "weather_stats.json" if a else Path())

    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    panel = SettingsPanel(settings, AIService(settings, dm), None, dm)
    assert panel._weather_stats_label.text()          # 有文案（哪怕是 0 次）
