"""考研备考命令（11408）：学习记录 / 错题间隔复习 / 模考 / 汇总。

这些命令和界面共用 `models/study.py` 的同一套算法；写入仍走
`actions_core.load/save`（备份 + 指纹校验 + 原子写，R-002）。
"""

from datetime import date

from scripts.actions_core import (
    MAX_NOTE,
    ActionError,
    _integer,
    _iso_date,
    _record_id,
    _text,
    emit,
    load,
    save,
)
from src.models.study import MAX_MINUTES, StudyModel, adopt

MAX_SCORE = 1000


def _model() -> StudyModel:
    return adopt(load("study.json"))


def _subject(model, raw: str) -> str:
    sid = model.resolve_subject(raw)
    if sid not in {str(s["id"]) for s in model.subjects}:
        names = "、".join(f"{s['id']}({s['name']})" for s in model.subjects)
        raise ActionError(f"--subject 不认识 {raw!r}，可用：{names}")
    return sid


def cmd_log_study(args) -> None:
    model = _model()
    subject = _subject(model, args.subject)
    minutes = _integer(args.minutes, "minutes", 1, MAX_MINUTES)
    day = _iso_date(getattr(args, "date", None), "date",
                    default=date.today().isoformat())
    note = _text(getattr(args, "note", None), "note", max_len=MAX_NOTE)
    sid = model.add_session(subject, minutes, note, day)
    save("study.json", model.data)
    emit(f"OK log_study {sid} | {model.subject_name(subject)} {minutes} 分钟 | {day}")


def cmd_add_mistake(args) -> None:
    model = _model()
    subject = _subject(model, args.subject)
    topic = _text(args.topic, "topic", required=True, max_len=MAX_NOTE)
    question = _text(getattr(args, "question", None), "question", max_len=MAX_NOTE)
    answer = _text(getattr(args, "answer", None), "answer", max_len=MAX_NOTE)
    note = _text(getattr(args, "note", None), "note", max_len=MAX_NOTE)
    mid = model.add_mistake(subject, topic, question, answer, note,
                            getattr(args, "date", None) or None)
    save("study.json", model.data)
    emit(f"OK add_mistake {mid} | {model.subject_name(subject)} | {topic}")


def cmd_review_mistake(args) -> None:
    mid = _record_id(args.id)
    model = _model()
    before = next((m for m in model.mistakes if m.get("id") == mid), None)
    if before is None:
        raise ActionError(f"没有 id 为 {mid} 的错题（用 list_mistakes 查一下）")
    if before.get("mastered"):
        emit(f"OK review_mistake {mid} | 已经掌握，无需再复习")
        return
    model.review_mistake(mid, date.today())
    save("study.json", model.data)
    after = next(m for m in model.mistakes if m.get("id") == mid)
    if after.get("mastered"):
        emit(f"OK review_mistake {mid} | 已完成最后一轮，标记为掌握")
    else:
        emit(f"OK review_mistake {mid} | 下次复习 {after.get('next_review')}"
             f"（第 {after.get('stage')} 档）")


def cmd_master_mistake(args) -> None:
    mid = _record_id(args.id)
    model = _model()
    if not model.master_mistake(mid):
        raise ActionError(f"没有 id 为 {mid} 的错题")
    save("study.json", model.data)
    emit(f"OK master_mistake {mid}")


def cmd_add_mock(args) -> None:
    model = _model()
    subject = _subject(model, args.subject)
    score = _integer(args.score, "score", 0, MAX_SCORE)
    full = _integer(getattr(args, "full_score", None), "full_score", 1, MAX_SCORE,
                    default=150)
    duration = _integer(getattr(args, "duration", None), "duration", 1, MAX_MINUTES,
                        default=180)
    note = _text(getattr(args, "note", None), "note", max_len=MAX_NOTE)
    day = _iso_date(getattr(args, "date", None), "date",
                    default=date.today().isoformat())
    kid = model.add_mock(subject, score, full, duration, note, day)
    save("study.json", model.data)
    emit(f"OK add_mock {kid} | {model.subject_name(subject)} | {score}/{full} | {day}")


def cmd_list_mistakes(args) -> None:
    model = _model()
    subject = getattr(args, "subject", None)
    subject_id = model.resolve_subject(subject) if subject else None
    due_only = str(getattr(args, "due", "") or "").lower() == "yes"
    records = model.due_reviews() if due_only else model.open_mistakes()
    if subject_id:
        records = [m for m in records if m.get("subject") == subject_id]
    if not records:
        emit("NO_MISTAKE")
        return
    for mistake in records[:20]:
        emit(f"  [{mistake['id']}] {model.subject_name(mistake.get('subject', ''))}"
             f" | {mistake.get('topic', '')} | 下次 {mistake.get('next_review') or '已掌握'}")
    emit(f"FOUND {len(records)}")


def cmd_study_summary(args) -> None:
    """今日/本周学习、待复习、模考与倒计时 —— 数字全部由代码算。"""
    model = _model()
    result = model.summary(getattr(args, "date", None) or None)
    emit(f"目标日期 {result['target_date']} | 倒计时 "
         f"{result['days_left'] if result['days_left'] is not None else '未设置'} 天")
    emit(f"今日学习 {result['today_minutes']} 分钟（目标 "
         f"{result['daily_goal_minutes']}）| 本周 {result['week_minutes']} 分钟")
    parts = [f"{model.subject_name(sid)} {minutes}"
             for sid, minutes in result["week_by_subject"].items()]
    emit("本周各科: " + " | ".join(parts))
    emit(f"待复习 {result['due_count']} 条 | 未掌握错题 {result['open_mistakes']} 条"
         f" | 连续达标 {result['streak']} 天")
    for mistake in result["due_reviews"][:10]:
        emit(f"  待复习 [{mistake['id']}] {model.subject_name(mistake.get('subject', ''))}"
             f" | {mistake.get('topic', '')}")
    latest = result["latest_mock"]
    if latest:
        emit(f"最近模考: {model.subject_name(latest.get('subject', ''))} "
             f"{int(latest.get('score') or 0)}/{int(latest.get('full_score') or 150)}"
             f"（{latest.get('date')}）")
    else:
        emit("最近模考: （无）")


def cmd_study_set_target(args) -> None:
    model = _model()
    target = _iso_date(args.date, "date")
    model.set_target(target)
    goal = getattr(args, "daily_goal", None)
    if goal is not None:
        model.set_daily_goal(_integer(goal, "daily_goal", 1, MAX_MINUTES))
    save("study.json", model.data)
    emit(f"OK study_set_target {model.target_date} | 每日目标 "
         f"{model.data.get('daily_goal_minutes')} 分钟")
