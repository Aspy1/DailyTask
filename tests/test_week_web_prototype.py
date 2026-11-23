"""方案 B 原型：周视图 Web 页（`MD-files/PERFORMANCE_WORKFLOW.md` §3.2）。

原型要证明的是**可行性与边界**，不是"Web 一定更快"：

1. 自包含、离线可用（无外链、无网络请求）；
2. 数据一次注入（不做每格跨桥请求）；
3. **受控消息契约**：只接受纯 JSON，标题按 `textContent` 渲染（不解析 HTML）；
4. 运行时缺失时**退回** Qt 周视图（`render_week` 返回 False，不抛异常）；
5. 同一份主题令牌（`design/tokens.json`）—— 原型里**零硬编码**色值与字号。
"""

import json
import re

from src.ui.widgets import week_web_prototype as proto

TOKENS = proto.design_tokens()


def _courses() -> list[dict]:
    return [
        {"name": "高等数学", "day_of_week": 1,
         "time_slots": [{"start": 1, "end": 2, "location": "A101"}]},
        {"name": "数据结构", "day_of_week": 3,
         "time_slots": [{"start": 3, "end": 4, "location": "B202"}]},
    ]


def _html(week: dict | None = None) -> str:
    return proto.build_html(week or proto.week_payload(_courses()), TOKENS)


def test_payload_is_pure_json_and_grouped_by_day() -> None:
    week = proto.week_payload(_courses(), {"title": "第 9 / 16 周"})

    assert len(week["days"]) == 7
    assert week["days"][0]["name"] == "周一"
    assert week["days"][0]["slots"][0]["title"] == "高等数学"
    assert week["days"][2]["slots"][0]["location"] == "B202"
    assert week["days"][1]["slots"] == [], "没课的那天是空列表，不是缺键"
    json.dumps(week, ensure_ascii=False)          # 必须可序列化（跨桥只传纯数据）


def test_conflicting_slots_are_flagged() -> None:
    """同一时段两门课 → 两条都标 conflict（页面画 ⚠ 边框）。"""
    courses = [
        {"name": "选修A", "day_of_week": 2,
         "time_slots": [{"start": 3, "end": 3, "location": "A"}]},
        {"name": "重修B", "day_of_week": 2,
         "time_slots": [{"start": 3, "end": 4, "location": "B"}]},
    ]

    week = proto.week_payload(courses)

    slots = week["days"][1]["slots"]
    assert len(slots) == 2
    assert all(slot["conflict"] for slot in slots)


def test_html_is_self_contained_offline() -> None:
    """⭐ 自包含：没有外链、没有 CDN、没有网络请求（离线也能开）。"""
    html = _html()

    assert "http://" not in html and "https://" not in html
    assert "<link" not in html and "fetch(" not in html
    assert "src=" not in html, "不允许外部脚本/资源"


def test_html_embeds_the_week_data_once() -> None:
    """数据一次注入，页面自己画（不是每格一次跨桥请求）。"""
    html = _html()

    assert html.count("高等数学") == 1
    assert "renderWeek(WEEK)" in html
    assert "fetch(" not in html


def test_page_renders_titles_as_text_not_html() -> None:
    """⭐ 受控契约：标题走 `textContent`（恶意课程名不能变成 HTML）。"""
    html = _html()

    assert "name.textContent = slot.title" in html
    assert "innerHTML = slot.title" not in html


def test_malicious_course_name_cannot_inject_markup() -> None:
    """课程名里的 `</script>` / `<img onerror>` 必须**无法闭合数据区**。"""
    evil = [{"name": '</script><img src=x onerror="alert(1)">', "day_of_week": 1,
             "time_slots": [{"start": 1, "end": 1, "location": "<b>x</b>"}]}]

    html = _html(proto.week_payload(evil))

    assert not re.search(r"</\s*script\s*>\s*<img", html, re.IGNORECASE), \
        "未转义的标签会逃出数据区"
    assert "\\u003c" in html.lower(), "`<` 应当被转成 \\u003c"
    assert html.lower().count("</script>") == 1, "真实闭合标签只能有模板自带的那一个"


def test_colors_and_sizes_come_from_the_token_file() -> None:
    """⭐ 颜色/字号来自 `design/tokens.json`（跨栈共用，不写死第二套）。"""
    html = _html()

    # 注入的调色板就是令牌文件里的那份
    assert TOKENS["colors"]["bg_surface"] in html
    # 字号也是令牌值
    assert f"font-size: {TOKENS['sizes']['SIZE_CAPTION']}px" in html
    # 样式只消费 CSS 变量（颜色值本身来自 PALETTE，不散落在规则里）
    style = html.split("<style>")[1].split("</style>")[0]
    assert not re.search(r"#[0-9a-fA-F]{6}", style), "样式中出现硬编码色值"
    assert not re.search(r"rgba?\((?![^)]*var)", style), "样式中出现硬编码颜色函数"


def test_no_hardcoded_px_outside_tokens() -> None:
    """`__FS_*__` 占位符必须已全部替换掉（否则页面会用不到字号）。"""
    html = _html()

    assert "__FS_" not in html, "有未替换的字号占位符"


def test_font_name_is_sanitized() -> None:
    """字体名是唯一拼进 CSS 的非数据值 —— 必须清洗。"""
    evil = dict(TOKENS)
    evil["font"] = 'Bad"; } body{display:none} .x{'

    html = proto.build_html(proto.week_payload(_courses()), evil)

    style = html.split("<style>")[1].split("</style>")[0]
    assert "display:none" not in style


def test_missing_runtime_falls_back_instead_of_raising(monkeypatch) -> None:
    """⭐ 运行时缺失 → `render_week` 返回 False（调用方退回 Qt 周视图）。"""
    monkeypatch.setattr(proto, "web_engine_available", lambda: False)

    assert proto.render_week(object(), {"days": []}, TOKENS) is False


def test_preview_file_is_written(tmp_path) -> None:
    """同一份 HTML 可落盘（离屏核对 / 截图用）。"""
    target = proto.write_preview(tmp_path / "week.html",
                                 proto.week_payload(_courses()), TOKENS)

    assert target.is_file()
    assert "高等数学" in target.read_text(encoding="utf-8")


def test_dark_and_light_modes_both_work() -> None:
    """深浅两套令牌都能注入（手册要求两种主题对照截图）。"""
    dark = proto.build_html(proto.week_payload(_courses()), proto.design_tokens("dark"))
    light = proto.build_html(proto.week_payload(_courses()), proto.design_tokens("light"))

    assert dark != light
    assert proto.design_tokens("light")["colors"]["bg_surface"] in light
