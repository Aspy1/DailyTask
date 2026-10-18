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
from datetime import date
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


def outing_hints(plans: list, courses: list, today: date | None = None) -> list[Hint]:
    """**今天会出门吗**？会 → 出门前的三条提醒（`PLAN.md` P20）。

    "出门"的口径（用户 P20 原话："上课也算出门"）：
    今天**有课** ✓ 或 **有计划**（日程里排了东西）✓。

    三条提示（都是**代码判断**，不让模型猜 ✓）：
    1. 关键物品**归位**（用户口径：`右手架子上`）
    2. **倒垃圾**（每天第一次出门时）
    3. **给设备充电**（上课 / 出门前）
    """
    today = today or date.today()
    weekday = today.isoweekday()          # 1=周一 … 7=周日
    has_class = any(any(int(s.get("day", 0)) == weekday for s in (c.get("time_slots") or []))
                    for c in courses or [])
    has_plan = bool([p for p in plans or [] if str(p.get("title") or "").strip()])
    if not (has_class or has_plan):
        return []
    why = "今天有课" if has_class else "今天有安排"
    return [
        Hint("outing.keys", f"{why} —— 出门前把钥匙串 / 卡包放回右手架子上 🔑", "info"),
        Hint("outing.trash", "出门顺手带垃圾 🗑", "info"),
        Hint("outing.charge", "出门前检查设备电量、带上充电宝 🔋", "info"),
    ]


def load_weather(data_dir: Path) -> tuple[dict, list]:
    """读天气派生缓存（`weather_cache.json`）→ `(当天, 预报列表)`。

    读不到就返回空 —— 提示少一条，不影响别的功能 ✓。
    """
    cache = read_json_safe(Path(data_dir) / "weather_cache.json")
    return cache.get("now") or {}, cache.get("forecast") or []


def budget_hints(data_dir: Path, items: list) -> list[Hint]:
    """本月**预计超支** → 一条提示（C 类第 6 项，用例 16）。

    算不出来的东西（分期金额 / 续费金额 / 补货价格）**不硬编** —— 见 `services/budget.py`。
    """
    from src.services.budget import forecast

    data = read_json_safe(Path(data_dir) / "expenses.json")
    result = forecast(data.get("records") or [],
                      (data.get("budget") or {}).get("monthly") or 0, items)
    if not result["over"]:
        return []
    return [Hint("budget.over",
                 f"本月预计超支 ¥{result['projected'] - result['budget']:.0f}"
                 f"（预计花 ¥{result['projected']:.0f} / 预算 ¥{result['budget']:.0f}）",
                 "warn")]


def today_hints(data_dir: Path) -> list[Hint]:
    """今天该提示的东西：天气 + 该洗的衣物 + 预算超支 + 出门提醒（继续加规则）。"""
    now, forecast_data = load_weather(data_dir)
    inventory = read_json_safe(Path(data_dir) / "inventory.json")
    items = inventory.get("items") or []
    logs = read_json_safe(Path(data_dir) / "daily_logs.json")
    today = date.today().isoformat()
    plans = (logs.get("plans") or {}).get(today) or []
    return (weather_hints(now, forecast_data) + wash_hints(items)
            + budget_hints(data_dir, items) + outing_hints(plans, _courses_today(data_dir)))


def _courses_today(data_dir: Path) -> list:
    """今天的课（课程按学期分文件存，用与生产同一套解析）。"""
    from src.models import semester_paths

    data = read_json_safe(semester_paths.resolve(Path(data_dir), "courses.json"))
    return data.get("courses") or []
