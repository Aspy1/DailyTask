"""AI 服务回归：系统提示词构建**不得**同步发网络请求。

历史缺陷（CODE_STANDARDS Q-C2）：`_build_system_prompt()` 内联调用
`_fetch_deepseek_balance()` / `_fetch_weather_for_prompt()`，两者都是同步
`requests.get`（超时 5s）→ 每次缓存过期后发消息，UI 主线程可能卡 5 秒。
现在改为：构建只读缓存，网络预热放后台守护线程。
"""

import threading
import time
from typing import Any

import pytest

from src.services.ai_service import AIService
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager


@pytest.fixture
def svc(tmp_path, qapp) -> AIService:
    dm = DataManager(tmp_path)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    settings.set("AI", "api_key", "sk-test-not-real")
    return AIService(settings, dm)


def test_system_prompt_does_not_hit_network(svc, monkeypatch) -> None:
    """构建提示词时任何 requests 调用都视为失败。"""
    import requests

    def boom(*_a: Any, **_kw: Any) -> None:
        raise AssertionError("_build_system_prompt 不允许同步发网络请求")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(requests, "post", boom)

    started = time.time()
    prompt = svc._build_system_prompt()
    elapsed = time.time() - started

    assert "当前日期" in prompt
    assert elapsed < 1.0, f"构建提示词耗时 {elapsed:.2f}s，疑似仍在同步请求"


def test_prompt_cache_is_used_on_second_build(svc) -> None:
    first = svc._build_system_prompt()
    assert svc._build_system_prompt() is first


def test_warmup_fills_cache_in_background(svc, monkeypatch) -> None:
    """后台预热线程应把余额/天气写进缓存（替身须模拟真实函数的写缓存行为）。"""
    def fake_balance() -> str:
        svc._ds_balance_cache = {"value": "¥12.34", "fetched_at": time.time()}
        return "¥12.34"

    def fake_weather(allow_service: bool = True) -> str:
        svc._weather_cache = {"value": "  晴 20°C", "fetched_at": time.time()}
        return "  晴 20°C"

    monkeypatch.setattr(svc, "_fetch_deepseek_balance", fake_balance)
    monkeypatch.setattr(svc, "_fetch_weather_for_prompt", fake_weather)

    svc._warm_context_cache()
    for _ in range(50):                       # 最多等 ~1s
        if svc._ds_balance_cache.get("value") and svc._weather_cache.get("value"):
            break
        time.sleep(0.02)

    assert svc._ds_balance_cache.get("value") == "¥12.34"
    assert svc._weather_cache.get("value") == "  晴 20°C"


def test_warmup_is_not_reentrant(svc, monkeypatch) -> None:
    """并发调用只应起一个预热线程。"""
    started = []

    def slow(*_a: Any, **_kw: Any) -> str:
        started.append(1)
        time.sleep(0.2)
        return ""

    monkeypatch.setattr(svc, "_fetch_deepseek_balance", slow)
    monkeypatch.setattr(svc, "_fetch_weather_for_prompt", lambda allow_service=True: "")

    svc._warm_context_cache()
    svc._warm_context_cache()
    svc._warm_context_cache()

    time.sleep(0.4)
    assert len(started) == 1, started
    assert threading.active_count() < 20


def test_balance_info_reads_cache_only(svc, monkeypatch) -> None:
    monkeypatch.setattr(svc, "_fetch_deepseek_balance",
                        lambda: pytest.fail("不应同步查余额"))
    svc._ds_balance_cache = {"value": "¥9.99", "fetched_at": time.time()}
    from src.services.ai_service import _balance_info

    assert "¥9.99" in _balance_info(svc._settings, svc._ds_balance_cache)
