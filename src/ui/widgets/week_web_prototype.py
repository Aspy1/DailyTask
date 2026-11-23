"""周视图的 **Web 原型**（方案 B，`MD-files/PERFORMANCE_WORKFLOW.md` §3.2）。

**这是只读原型，不是已替换的周视图。** 界面仍是 `src/ui/widgets/course_table.py`；
这里只回答"Web 方案在本机是否可行、代价多大"：

- 用**本地资源**（`QWebEngineView.setHtml` + 内联 CSS），不联网、不起 Web 服务；
- **单个 Web 实例**，一次传入当前周的全部数据（不让每个格子跨桥请求）；
- 受控消息契约：宿主 → 页面只有 `renderWeek`，页面 → 宿主只有 `ready` / `log`
  （固定操作集合 + 参数校验 + 请求 ID + 有界返回）；
- 主题令牌从 Qt 侧传入（跨栈共用同一份颜色，不写死第二套）。

离线可用性：页面是自包含 HTML（无外链），运行时缺失时 `web_engine_available()`
返回 False，调用方退回现有 Qt 周视图。
"""

from __future__ import annotations

import json
from pathlib import Path

MARKER = "{{WEEK}}"
PALETTE_MARKER = "{{PAL}}"
FONT_MARKER = "{{FONTNAME}}"
LABELS_MARKER = "{{LABELS}}"

# 令牌**单一真值**（与 Qt 侧同一份文件；本模块不写死第二套色板/字号）
_TOKENS_FILE = Path(__file__).resolve().parents[3] / "design" / "tokens.json"


def design_tokens(mode: str = "dark") -> dict:
    """读设计令牌（颜色 + 字号 + 字体）—— 跨栈共用同一份。"""
    data = json.loads(_TOKENS_FILE.read_text(encoding="utf-8"))
    colors = dict(data["colors"].get(mode) or data["colors"]["dark"])
    sizes = {name: int(value) for name, value in data["sizes"].items()}
    return {"colors": colors, "sizes": sizes, "font": data["font"]["cn"]}


def web_engine_available() -> bool:
    """QtWebEngine 是否可用（未安装时导入即失败 → 退回 Qt 周视图）。"""
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        return False
    return True


def build_html(week: dict, tokens: dict | None = None) -> str:
    """把**当前周的全部数据**一次注入页面（避免每格一次跨桥请求）。

    `week` 形如 `{"days": [{"name": "周一", "date": "2026-11-23",
    "slots": [{"start": 1, "end": 2, "title": "...", "location": "...",
    "conflict": false}]}], "labels": {"title": "第 9 / 16 周"}}`。
    只接受 JSON 可序列化的纯数据；**不拼任何 JS 片段**（防注入）。

    ⚠ 注入到 `<script>` 里的 JSON 必须处理两件相互冲突的事：
    中文要**原样可读**（`ensure_ascii=False`），而 `</script>` 必须**不能**真的闭合标签。
    做法：先 `ensure_ascii=False`，再把 `<` 转成 `\\u003c` —— 这不影响 JSON 语义，
    但让任何标签都无法逃出数据区（`tests/test_week_web_prototype.py` 钉住）。
    """
    resolved = tokens or design_tokens()
    sizes = resolved["sizes"]
    from src.i18n.loader import tr

    return (_TEMPLATE.replace(MARKER, _safe_json(week))
            .replace(PALETTE_MARKER, _safe_json(resolved["colors"]))
            .replace(LABELS_MARKER, _safe_json({"periods": tr("widget.schedule.period_unit")}))
            .replace(FONT_MARKER, _safe_font(str(resolved["font"])))
            .replace("{{PAGETITLE}}", tr("widget.schedule.title"))
            .replace("{{LANG}}", "zh-CN")     # BCP-47 语言标签，不是界面文案
            .replace("__FS_BODY__", str(sizes["SIZE_BODY"]))
            .replace("__FS_CAPTION__", str(sizes["SIZE_CAPTION"]))
            .replace("__FS_TINY__", str(sizes["SIZE_TINY"])))


def _safe_json(value: object) -> str:
    """JSON 文本 → 可直接嵌进 `<script>`（中文原样，标签不可能闭合）。"""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def _safe_font(name: str) -> str:
    """字体名只保留字母/空格/中文：它是唯一拼进 CSS 的非数据值。"""
    return "".join(ch for ch in name if ch.isalnum() or ch in " _-")


def render_week(view, week: dict, tokens: dict | None = None) -> bool:
    """在 `QWebEngineView` 里渲染一周 → `True` = 已发起渲染。

    消息契约：只调页面暴露的 `renderWeek(payload)`，参数是**纯 JSON**。
    """
    if not web_engine_available():
        return False
    view.setHtml(build_html(week, tokens))
    return True


def week_payload(courses: list[dict], labels: dict | None = None) -> dict:
    """把课程列表整理成"按周 × 天 × 节次"的纯数据（宿主侧算好，页面只画）。"""
    days: dict[int, list[dict]] = {day: [] for day in range(1, 8)}
    for course in courses:
        _append_course(days, course)
    for items in days.values():
        _mark_conflicts(items)
    return {
        "labels": labels or {},
        "days": [{"name": _day_name(day), "slots": sorted(days[day],
                                                          key=lambda s: s["start"])}
                 for day in range(1, 8)],
    }


def _append_course(days: dict[int, list[dict]], course: dict) -> None:
    """把一门课的每个时段加进对应那天（非法星期直接跳过）。"""
    day = int(course.get("day_of_week") or 0)
    if day not in days:
        return
    for slot in course.get("time_slots") or []:
        days[day].append({
            "start": int(slot.get("start") or 0),
            "end": int(slot.get("end") or 0),
            "title": str(course.get("name") or ""),
            "location": str(slot.get("location") or ""),
            "conflict": False,
        })


def _day_name(day: int) -> str:
    """周几的显示名（走 i18n，与 Qt 侧同一份词表）。"""
    from src.i18n.loader import tr

    return tr(f"day.{_DAY_KEYS[day]}")


_DAY_KEYS = {1: "monday", 2: "tuesday", 3: "wednesday", 4: "thursday",
             5: "friday", 6: "saturday", 7: "sunday"}


def _mark_conflicts(items: list[dict]) -> None:
    """同一时段两门课（选修过多 / 重修）→ 标 `conflict`，页面画 ⚠。"""
    for item in items:
        item["conflict"] = any(
            other is not item and other["start"] <= item["end"]
            and item["start"] <= other["end"] for other in items)


def write_preview(path: Path, week: dict, tokens: dict | None = None) -> Path:
    """把同一份 HTML 落到文件（离屏截图 / 人工核对用）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_html(week, tokens), encoding="utf-8")
    return path


_TEMPLATE = """<!DOCTYPE html>
<html lang="{{LANG}}"><head><meta charset="utf-8">
<title>{{PAGETITLE}}</title>
<style>
  body { margin: 0; background: var(--bg_surface); color: var(--fg_primary);
         font-family: "{{FONTNAME}}", sans-serif; }
  header { padding: 8px 16px; color: var(--fg_hint); font-size: __FS_BODY__px; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  th, td { border: 1px solid var(--border); padding: 4px 6px;
           vertical-align: top; font-size: __FS_CAPTION__px; }
  th { color: var(--fg_hint); font-weight: 600; }
  .slot { background: var(--bg_hover); border-radius: 6px;
          padding: 4px 6px; margin: 2px 0; }
  .slot b { display: block; font-weight: 600; }
  .slot span { color: var(--fg_hint); font-size: __FS_TINY__px; }
  .conflict { border-left: 3px solid var(--red); }
  .empty { color: var(--fg_hint); font-size: __FS_TINY__px; }
</style></head>
<body>
<header id="title"></header>
<table><thead><tr id="head"></tr></thead><tbody id="body"></tbody></table>
<script>
  const WEEK = {{WEEK}};
  const PALETTE = {{PAL}};
  const LABELS = {{LABELS}};
  function applyPalette(palette) {
    const root = document.documentElement;
    for (const [key, value] of Object.entries(palette || {})) {
      root.style.setProperty("--" + key, value);
    }
  }
  function renderWeek(payload) {
    document.getElementById("title").textContent =
      (payload.labels && payload.labels.title) || "";
    const head = document.getElementById("head");
    head.innerHTML = "";
    for (const day of payload.days) {
      const th = document.createElement("th");
      th.textContent = day.name;
      head.appendChild(th);
    }
    const body = document.getElementById("body");
    body.innerHTML = "";
    const row = document.createElement("tr");
    for (const day of payload.days) {
      const td = document.createElement("td");
      if (!day.slots.length) {
        const span = document.createElement("span");
        span.className = "empty";
        span.textContent = "—";
        td.appendChild(span);
      }
      for (const slot of day.slots) {
        const div = document.createElement("div");
        div.className = "slot" + (slot.conflict ? " conflict" : "");
        const name = document.createElement("b");
        name.textContent = slot.title;          // textContent: never parse markup
        const meta = document.createElement("span");
        meta.textContent = `${slot.start}-${slot.end} ${LABELS.periods} ${slot.location}`;
        div.appendChild(name); div.appendChild(meta);
        td.appendChild(div);
      }
      row.appendChild(td);
    }
    body.appendChild(row);
  }
  renderWeek(WEEK);
</script>
</body></html>
"""
