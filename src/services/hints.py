"""「今日提示」—— 由**代码规则**产生、今天有效、用户可 x 掉的一条条提示。

为什么要单独一层：天气联动（C 类第 3 项）与出门提醒（第 7 项）本质是同一件事 ——
**"从已有数据推出来的、今天该提醒你做的事"**。所以做**一张容器 + 一组规则函数**，
以后加规则就是加函数 ✓。

两条设计约束（都来自今天的教训）：
- **不让模型判断**该不该带伞 / 加衣 —— 它不可靠 ✗；这类建议由**规则**产生（代码说了算）✓
- 提示是**视图状态**：x 掉只影响今天这一次显示，**不写进数据文件** ✓

⚠ 天气代码用的是 **Open-Meteo 编码**（与 `ai_prompts` 里给模型的那套规则一致）。
"""

from dataclasses import dataclass
from pathlib import Path

from src.services.weather_store import read_json_safe

# Open-Meteo 天气代码里的"下雨类"（与提示词里的 51-67 / 80-82 / 95-99 对齐）
RAIN_RANGES = ((51, 67), (80, 82), (95, 99))
HOT_C, COLD_C = 35, 0


@dataclass(frozen=True)
class Hint:
    """一条提示。`key` 是**幂等键**（同一条今天只提示一次）。"""

    key: str
    text: str
    level: str = "info"          # info / warn


def is_rain(code: int) -> bool:
    return any(lo <= code <= hi for lo, hi in RAIN_RANGES)


def weather_hints(now: dict | None, forecast: list | None = None) -> list[Hint]:
    """从天气推"带伞 / 加衣 / 防暑"这类提示。**纯函数**（好测、不碰界面）。

    `now` 是当天天气（`{"weathercode": 61, "temp": 12}` 这种），`forecast` 可省。
    """
    if not now:
        return []
    out: list[Hint] = []
    code = int(now.get("weathercode") or 0)
    temp = now.get("temp")
    if is_rain(code):
        out.append(Hint("weather.rain", "今天有雨，记得带伞 ☔", "warn"))
    if isinstance(temp, (int, float)):
        if temp >= HOT_C:
            out.append(Hint("weather.hot", f"今天 {temp:.0f}°C，注意防暑 🥵", "warn"))
        elif temp < COLD_C:
            out.append(Hint("weather.cold", f"今天 {temp:.0f}°C，注意保暖 🧣", "warn"))
    return out


def wash_hints(items: list) -> list[Hint]:
    """该洗的衣物 → 一条条提示（用户用例表第 13/22 条）。

    ⚠ 判断在 `inventory.needs_wash_now()` 里（显式标记 or 穿了够久）—— 这里只负责产出提示。
    """
    from src.models.inventory import needs_wash_now

    out = []
    for it in items or []:
        if it.get("id") and needs_wash_now(it):
            out.append(Hint(f"wash.{it['id']}", f"{it.get('name', '')} 该洗了 🧺", "info"))
    return out


def load_weather(data_dir: Path) -> tuple[dict, list]:
    """读天气派生缓存（`weather_cache.json`）→ `(当天, 预报列表)`。

    读不到就返回空 —— 提示少一条，不影响别的功能 ✓。
    """
    cache = read_json_safe(Path(data_dir) / "weather_cache.json")
    return cache.get("now") or {}, cache.get("forecast") or []


def today_hints(data_dir: Path) -> list[Hint]:
    """今天该提示的东西：天气 + 该洗的衣物（后面继续往这里加规则）。"""
    now, forecast = load_weather(data_dir)
    inventory = read_json_safe(Path(data_dir) / "inventory.json")
    return weather_hints(now, forecast) + wash_hints(inventory.get("items") or [])
