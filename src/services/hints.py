"""「今日提示」—— 由**代码规则**产生、今天有效、用户可 x 掉的一条条提示。

为什么要单独一层：天气联动（C 类第 3 项）与出门提醒（第 7 项）本质是同一件事 ——
**"从已有数据推出来的、今天该提醒你做的事"**。所以做**一张容器 + 一组规则函数**，
以后加规则就是加函数 ✓。

两条设计约束（都来自今天的教训）：
- **不让模型判断**该不该带伞 / 加衣 —— 它不可靠 ✗；这类建议由**规则**产生（代码说了算）✓
- 提示是**视图状态**：x 掉只影响今天这一次显示，**不写进数据文件** ✓

⚠ 天气代码用的是 **Open-Meteo 编码**（与 `ai_prompts` 里给模型的那套规则一致）。
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.services.weather_store import read_json_safe

logger = logging.getLogger(__name__)

# Open-Meteo 天气代码里的"下雨类"（与提示词里的 51-67 / 80-82 / 95-99 对齐）
RAIN_RANGES = ((51, 67), (80, 82), (95, 99))
HOT_C, COLD_C = 35, 0


@dataclass(frozen=True)
class Hint:
    """一条提示。`key` 是**幂等键**（同一条今天只提示一次）。

    `blink=True` → 这条会**低频闪烁**（吃饭提醒用：用户 2026-10-30 的口径是
    "和那三条可点掉的提示一样，只是低频闪烁"，不是托盘闪、也不是新控件）。
    """

    key: str
    text: str
    level: str = "info"          # info / warn
    blink: bool = False


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
    # ⚠ 不要在这里放 emoji：Windows 的 QSS 字体回退不稳定，☔/🧺 会显示成方框
    # （2026-11-01 截图实测）。提示文案本身已经说清楚了。
    if is_rain(code):
        out.append(Hint("weather.rain", "今天有雨，记得带伞", "warn"))
    if isinstance(temp, (int, float)):
        if temp >= HOT_C:
            out.append(Hint("weather.hot", f"今天 {temp:.0f}°C，注意防暑", "warn"))
        elif temp < COLD_C:
            out.append(Hint("weather.cold", f"今天 {temp:.0f}°C，注意保暖", "warn"))
    return out


def wash_hints(items: list) -> list[Hint]:
    """该洗的衣物 → 一条条提示（用户用例表第 13/22 条）。

    ⚠ 判断在 `inventory.needs_wash_now()` 里（显式标记 or 穿了够久）—— 这里只负责产出提示。
    """
    from src.models.inventory import needs_wash_now

    out = []
    for it in items or []:
        if it.get("id") and needs_wash_now(it):
            out.append(Hint(f"wash.{it['id']}", f"{it.get('name', '')} 该洗了", "info"))
    return out


def _outing_reason(plans: list, courses: list, today: date) -> str | None:
    """今天会不会出门？返回**原因**（"今天有课" / "今天有安排"）或 `None`（不出门）。

    ⚠ `courses` 必须是**今天该上的课**（调用方走 `get_courses_for_date`）——
    这里不再自己按星期几筛（那需要猜字段名，R7 就是这么错的 ✗）。
    """
    if courses:
        return "今天有课"
    if [p for p in plans or [] if str(p.get("title") or "").strip()]:
        return "今天有安排"
    return None


def outing_hints(plans: list, courses: list, today: date | None = None) -> list[Hint]:
    """**今天会出门吗**？会 → 出门前的三条提醒（`PLAN.md` P20）。

    三条都是**代码判断**，不让模型猜 ✓：
    1. 关键物品**归位**（用户口径：`右手架子上`）
    2. **倒垃圾**（每天第一次出门时）
    3. **给设备充电**（上课 / 出门前）
    """
    reason = _outing_reason(plans, courses, today or date.today())
    if not reason:
        return []
    return [
        Hint("outing.keys", f"{reason} —— 出门前把钥匙串 / 卡包放回右手架子上", "info"),
        Hint("outing.trash", "出门顺手带垃圾", "info"),
        Hint("outing.charge", "出门前检查设备电量、带上充电宝", "info"),
    ]


def load_weather(data_dir: Path) -> tuple[dict, list]:
    """读天气派生缓存（`weather_cache.json`）→ `(当天, 预报列表)`。

    读不到就返回空 —— 提示少一条，不影响别的功能 ✓。
    """
    cache = read_json_safe(Path(data_dir) / "weather_cache.json")
    return cache.get("now") or {}, cache.get("forecast") or []


def budget_hints(data_dir: Path, items: list, records: list | None = None,
                 budget: float | None = None) -> list[Hint]:
    """本月**预计超支** → 一条提示（C 类第 6 项，用例 16）。

    算不出来的东西（分期金额 / 续费金额 / 补货价格）**不硬编** —— 见 `services/budget.py`。
    `records` / `budget` 可由调用方从内存模型直接传入（省掉一次读盘）。
    """
    from src.services.budget import forecast

    if records is None:
        data = read_json_safe(Path(data_dir) / "expenses.json")
        records = data.get("records") or []
        if budget is None:
            budget = (data.get("budget") or {}).get("monthly") or 0
    result = forecast(records, budget or 0, items)
    if not result["over"]:
        return []
    return [Hint("budget.over",
                 f"本月预计超支 ¥{result['projected'] - result['budget']:.0f}"
                 f"（预计花 ¥{result['projected']:.0f} / 预算 ¥{result['budget']:.0f}）",
                 "warn")]


def today_hints(data_dir: Path, now: datetime | None = None, *,
                items: list | None = None,
                plans: list | None = None,
                courses: list | None = None,
                records: list | None = None,
                budget: float | None = None,
                weather: tuple[dict, list] | None = None) -> list[Hint]:
    """今天该提示的东西：天气 + 该洗的衣物 + 预算超支 + 出门提醒 + 吃饭（继续加规则）。

    ⚠ 参数 `items` / `plans` / `courses` / `records` / `budget` 允许调用方**直接传内存模型**
    （`HintBar` 已经从 `DataManager` 拿到了），避免每次刷新都重读 5 个 JSON、还构造一遍
    `CourseModel`（那会在 UI 刷新路径上做文件 IO，Q-C2）。不传时退回读盘（测试/独立脚本）。
    """
    now = now or datetime.now()
    now_weather, forecast_data = weather if weather is not None else load_weather(data_dir)
    if items is None:
        inventory = read_json_safe(Path(data_dir) / "inventory.json")
        items = inventory.get("items") or []
    if plans is None:
        logs = read_json_safe(Path(data_dir) / "daily_logs.json")
        today = date.today().isoformat()
        plans = (logs.get("plans") or {}).get(today) or []
    if courses is None:
        courses = _courses_today(data_dir, date.today())
    return (weather_hints(now_weather, forecast_data) + wash_hints(items)
            + budget_hints(data_dir, items, records=records, budget=budget)
            + outing_hints(plans, courses)
            + meal_hints(now))


def meal_hints(now: datetime) -> list[Hint]:
    """11:40 / 16:40 到点 → 一条**会闪**的提示（用户 2026-10-30 A2）。

    窗口与托盘通知**同一个口径**（`reminder_rules.meal_slot_due`）—— 通知弹出的同时
    首页那条开始低频闪烁，用户能对上号；点一下就消失（视图状态，不写数据）。
    """
    from src.services.reminder_rules import meal_slot_due

    return [Hint(key, f"{label}时间到了", "info", blink=True)
            for key, label in meal_slot_due(now, set())]


def _courses_today(data_dir: Path, today: date) -> list:
    """今天的课 —— 复用**生产同一套课程日历**（教学周 / 单双周 / 节假日 / 调课 / 未开学）。

    ⚠ 原来这里只把学期里所有课程倒出来，再让 `_has_class_on()` 按 `time_slots[].day` 筛 ——
    可**生产里没有这个字段** ✗（星期在 `course.day_of_week`，slot 只记节次和地点），
    于是"今天有课"永远为假，只有"今天有安排"才会提醒出门（2026-10-19 审查 R7）。
    现在交给 `CourseModel.get_courses_for_date()`，**不再自己写一套简化日历** ✓。

    读不到（学期缺失 / 未开学 / 文件损坏）→ 返回空列表：**少一条提示，不影响别的功能** ✓。
    """
    from src.models import semester_paths
    from src.models.course import CourseModel
    from src.models.semester_registry import SemesterRegistry

    try:
        registry = SemesterRegistry(semester_paths.registry_path(Path(data_dir)))
        model = CourseModel(semester_paths.resolve(Path(data_dir), "courses.json"), registry)
        return model.get_courses_for_date(today)
    except Exception:
        logger.debug("hints 读今日课程失败", exc_info=True)
        return []
