#!/usr/bin/env python
"""模拟一个大三学生备考 11408 的一个月（纯模型，不碰真实数据）。

输出：`dev-logs/2026-10-31-考研一个月模拟.md`（可用 `--out` 指定）。

场景（2027 年 6 月，距 12/25 初试约 6 个月）：
- 工作日：数学 120 + 408 90 + 英语 40 + 政治 30 = 280 分钟
- 周末：模考（交替数学/408）+ 错题复盘 180 分钟
- 每天记 1–2 道错题；当天到期错题全部复习
- 每周一次模考，分数逐步上升
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.study import StudyModel  # noqa: E402

START = date(2027, 6, 1)
DAYS = 30
TARGET = "2027-12-25"
DAILY_PLAN = (("math", 120), ("cs408", 90), ("english", 40), ("politics", 30))
MOCK_PLAN = (("math", (95, 105, 112, 120)), ("cs408", (90, 98, 105, 110)))


def _weekday_plan(day: date) -> list[tuple[str, int]]:
    if day.weekday() < 5:
        return list(DAILY_PLAN)
    return [("math", 100), ("cs408", 80)]


def _run_month(model: StudyModel) -> dict:
    model.set_target(TARGET)
    model.set_daily_goal(220)
    mistakes_added = 0
    reviews_done = 0
    mock_index = 0

    for offset in range(DAYS):
        day = START + timedelta(days=offset)
        for subject, minutes in _weekday_plan(day):
            model.add_session(subject, minutes, note="模拟月", day=day)
            if minutes >= 80:
                model.add_mistake(subject, f"{subject}-第{offset + 1}天", day=day)
                mistakes_added += 1
        # 当天到期的错题全部复习
        for mistake in list(model.due_reviews(day)):
            model.review_mistake(mistake["id"], day)
            reviews_done += 1
        # 每周日一次模考
        if day.weekday() == 6:
            subject, scores = MOCK_PLAN[mock_index % len(MOCK_PLAN)]
            model.add_mock(subject, scores[(mock_index // 2) % len(scores)],
                           full_score=150, duration_minutes=180, day=day)
            mock_index += 1

    end = START + timedelta(days=DAYS - 1)
    summary = model.summary(end)
    totals: dict[str, int] = {}
    for session in model.sessions:
        sid = str(session.get("subject"))
        totals[sid] = totals.get(sid, 0) + int(session.get("minutes") or 0)
    return {
        "summary": summary,
        "totals": totals,
        "sessions": len(model.sessions),
        "mistakes_added": mistakes_added,
        "reviews_done": reviews_done,
        "mastered": sum(1 for m in model.mistakes if m.get("mastered")),
        "due_end": len(model.due_reviews(end)),
        "mocks": model.mock_history(),
        "daily": model.daily_minutes(DAYS, end),
    }


def _weekly_table(daily: dict[str, int]) -> list[str]:
    lines = ["| 周次 | 日期范围 | 学习分钟 | 达标天数 |", "|---|---|---|---|"]
    keys = sorted(daily)
    for week in range((len(keys) + 6) // 7):
        chunk = keys[week * 7:(week + 1) * 7]
        if not chunk:
            continue
        total = sum(daily[d] for d in chunk)
        passed = sum(1 for d in chunk if daily[d] >= 220)
        lines.append(f"| 第 {week + 1} 周 | {chunk[0]} ~ {chunk[-1]} | {total} | {passed}/{len(chunk)} |")
    return lines


def _helped_lines() -> list[str]:
    return [
        "## 这个月软件帮到了什么",
        "",
        "- **每天该复习哪几道错题**由代码按 1/2/4/7/15/30 天阶梯算，不用自己记；"
        "面板一打开就是到期清单，复习后自动推进下一档。",
        "- **各科投入是否均衡**用本周分钟数/目标进度条直接看；"
        "不需要自己拿表格加总，也不需要问 AI「我数学是不是学少了」。",
        "- **模考趋势**按科目存分数，最近几次一眼可比较；"
        "分数和倒计时都来自数据，不是模型复述。",
        "- 学习记录、错题、模考和原有的课表/作业/日程在同一个应用里，"
        "「今天有课 + 有作业 + 该复习哪道错题」可以在一个界面里看完。",
        "",
    ]


def _gap_lines() -> list[str]:
    return [
        "## 模拟中暴露的缺口（后续可做）",
        "",
        "- 学习记录目前只记「科目 + 分钟」，还没有**按章节/题型**的细分；"
        "真题二刷、错题归类仍要写在备注里。",
        "- 错题目前是「题干/正确思路」两行文本，没有**图片/公式**；"
        "数学一的公式题需要拍照或 LaTeX 时体验不够。",
        "- 模考只有分数，没有**逐题失分点**；"
        "要做「这次比上次多错在哪」还需要一张失分表。",
        "- 还没有**周计划生成**（例如「本周数学要完成哪几章」）；"
        "当前靠日程计划手工排，AI 可以按错题主题给出建议，但不会替用户做学习规划。",
        "- 没有**番茄钟/专注计时**；`log_study` 是事后记录，不能自动计时。",
        "- 没有**睡眠/精力**记录；考研后期「学多久」不如「什么时候学」重要，"
        "这需要和日程/习惯结合。",
    ]


def render(result: dict) -> str:
    summary = result["summary"]
    totals = result["totals"]
    names = {"math": "数学一", "english": "英语一", "politics": "政治", "cs408": "408"}
    lines = [
        "# 2026-10-31 第三步：考研 11408 一个月模拟",
        "",
        "> 这是 `scripts/study_month_simulation.py` 生成的模拟记录（沙箱数据，非用户真实数据）。",
        "",
        "## 场景",
        "",
        f"- 时间：{START} 起 {DAYS} 天（目标日 {TARGET}）",
        "- 工作日：数学 120 / 408 90 / 英语 40 / 政治 30 分钟；周末：模考 + 复盘",
        "- 每天记 1–2 道错题；到期错题当天复习；每周一次模考",
        "",
        "## 结果",
        "",
        f"- 学习记录：**{result['sessions']} 条**，合计 **{sum(totals.values())} 分钟**"
        f"（约 {sum(totals.values()) / 60:.1f} 小时）",
        "- 各科：" + " · ".join(f"{names.get(k, k)} {v} 分钟"
                                  for k, v in sorted(totals.items())),
        f"- 错题：新增 **{result['mistakes_added']}** 道，完成复习 **{result['reviews_done']}** 次，"
        f"已掌握 **{result['mastered']}** 道，月底待复习 **{result['due_end']}** 条",
        f"- 连续达标：**{summary['streak']}** 天（每日目标 {summary['daily_goal_minutes']} 分钟）",
        f"- 倒计时：距 {TARGET} 还有 **{summary['days_left']}** 天",
        "",
        "## 每周节奏",
        "",
        *_weekly_table(result["daily"]),
        "",
        "## 模考趋势",
        "",
        "| 日期 | 科目 | 得分 |",
        "|---|---|---|",
    ]
    for mock in result["mocks"]:
        lines.append(f"| {mock.get('date')} | {names.get(mock.get('subject'), mock.get('subject'))}"
                     f" | {int(mock.get('score', 0))}/{int(mock.get('full_score', 150))} |")
    lines += ["", *_helped_lines(), *_gap_lines()]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="考研 11408 一个月模拟")
    parser.add_argument("--out", default=str(ROOT / "dev-logs" / "2026-10-31-考研一个月模拟.md"))
    args = parser.parse_args()

    with TemporaryDirectory(prefix="study-month-") as tmp:
        model = StudyModel(Path(tmp) / "study.json")
        result = _run_month(model)
        report = render(result)
        Path(args.out).write_text(report, encoding="utf-8", newline="")
        print(f"wrote {args.out}")
        print(f"sessions={result['sessions']} minutes={sum(result['totals'].values())} "
              f"reviews={result['reviews_done']} due_end={result['due_end']}")


if __name__ == "__main__":
    main()
