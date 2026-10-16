"""天气统计/缓存的读写（**唯一实现**：原子写 + 坏文件自愈 + 并发锁）。

**为什么单独成模块**：`weather_stats.json` / `weather_cache.json` 是**派生缓存**，
由 worker 线程并发写。原来的写法有两个坑，2026-10-16 全量验收时炸出真崩溃：

1. `path.write_text(json.dumps(...))` **非原子、无锁** —— now / 7d 两个 worker
   同时写同一文件 → 内容互相截断，出现"尾部多一个 `}`"这种**损坏文件**
   （实测用户真实数据里就是这个形态）；
2. 读方（设置面板在**启动时**读它显示调用次数）**没有保护** → `JSONDecodeError`
   直接把应用**启动即崩**。

现在：读一律走 `read_json_safe()`（损坏时尽量救回第一个 JSON 对象），
写一律走 `write_json_atomic()`（tmp + `os.replace`），
读-改-写（记一次调用）走 `record_request()`（全程加锁）。
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


def _try_parse(text: str) -> dict | None:
    """严格解析；不是合法 JSON 返回 None，是合法 JSON 但不是对象返回 {}。"""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else {}


def read_json_safe(path: Path) -> dict:
    """读 JSON；文件损坏时**尽量救回第一个完整对象**，完全不可用则返回 `{}`（永不抛）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    parsed = _try_parse(text)
    if parsed is not None:
        return parsed

    # 并发写坏的典型形态：完整对象后面多出残留内容 → 取第一个对象
    try:
        value, _end = json.JSONDecoder().raw_decode(text.lstrip())
    except json.JSONDecodeError:
        logger.warning("天气文件无法解析，按空处理：%s", path)
        return {}
    if not isinstance(value, dict):
        return {}
    logger.warning("天气文件尾部有多余内容，已按第一个 JSON 对象读取：%s", path)
    return value


def write_json_atomic(path: Path, data: dict) -> None:
    """原子写（先写 `.tmp` 再 `os.replace`），避免并发/中断写坏文件。"""
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        logger.debug("写入天气文件失败：%s", path, exc_info=True)
        return


def _bump(bucket: dict, key: str, api_type: str) -> None:
    entry = bucket.setdefault(key, {"now": 0, "7d": 0, "warning": 0, "total": 0})
    entry[api_type] = entry.get(api_type, 0) + 1
    entry["total"] += 1


def record_request(path: Path, api_type: str) -> None:
    """把一次 API 调用计入统计（读-改-写**全程加锁** + 原子落盘）。"""
    now = datetime.now()
    with _LOCK:
        stats = read_json_safe(path)
        _bump(stats.setdefault("daily", {}), now.strftime("%Y-%m-%d"), api_type)
        _bump(stats.setdefault("monthly", {}), now.strftime("%Y-%m"), api_type)
        stats["last_request"] = {"time": now.isoformat(), "type": api_type}
        write_json_atomic(path, stats)
