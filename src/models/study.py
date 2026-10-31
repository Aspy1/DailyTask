"""考研备考（11408）数据模型：学习记录 / 错题间隔复习 / 模拟考试。

**为什么单开一个模型**：现有「习惯 / 近期安排 / 日程」能表达"每天做什么"，
但表达不了"这一科投入了多少分钟、这道错题下次哪天复习、模考趋势如何"。
这些问题都需要**确定性计算**（和 A4 财务同一条原则：代码算，AI 只解释）。

数据文件：`data/study.json`（跨学期共享 —— 考研跨学期，和习惯/记账同一口径）。

错题复习采用**固定阶梯** `1, 2, 4, 7, 15, 30` 天：
每次复习推进一档，走完即视为掌握。不引入 SM-2 的自评难度 ——
那会让模型/用户每天多填一个参数，收益却不如"按时出现"本身。

本模块**无 Qt、无 IO**（除 BaseJsonModel 的读写），便于单测与月模拟。
"""

import copy
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from src.models.base import BaseJsonModel, next_id

logger = logging.getLogger(__name__)

DEFAULT_SUBJECTS = [
    {"id": "math", "name": "数学一", "target_minutes": 120},
    {"id": "english", "name": "英语一", "target_minutes": 60},
    {"id": "politics", "name": "政治", "target_minutes": 40},
    {"id": "cs408", "name": "408", "target_minutes": 140},
]

DEFAULT_STUDY = {
    "_version": 1,
    # 大三备考：默认下一次 12 月 25 日（可在面板/命令里改）
    "target_date": "",
    "daily_goal_minutes": 360,
    "subjects": DEFAULT_SUBJECTS,
    "sessions": [],
    "mistakes": [],
    "mocks": [],
}

# 错题复习阶梯（天）：第 0 次 → 1 天后；第 1 次 → 2 天后；… 走完即掌握
REVIEW_INTERVALS = (1, 2, 4, 7, 15, 30)
MAX_MINUTES = 24 * 60
DEFAULT_FULL_SCORE = 150


def _today(day: date | str | None) -> date:
    """把 `None` / ISO 字符串 / date 统一成 date。"""
    if day is None:
        return date.today()
    if isinstance(day, date):
        return day
    return date.fromisoformat(str(day)[:10])


def default_target(today: date | None = None) -> str:
    """默认目标日：下一次 12 月 25 日（当年还没过就当年，否则明年）。"""
    today = today or date.today()
    year = today.year if (today.month, today.day) <= (12, 25) else today.year + 1
    return date(year, 12, 25).isoformat()


class StudyModel(BaseJsonModel):
    """学习记录 / 错题 / 模考。所有统计都是**现算**，不落派生值。"""

    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_STUDY)
        if not self._data.get("subjects"):
            self._data["subjects"] = [dict(s) for s in DEFAULT_SUBJECTS]
        if not self._data.get("target_date"):
            self._data["target_date"] = default_target()

    # ── 科目 ────────────────────────────────────────────────

    @property
    def subjects(self) -> list[dict]:
        return self._data.get("subjects") or list(DEFAULT_SUBJECTS)

    def subject_name(self, subject_id: str) -> str:
        for subject in self.subjects:
            if subject.get("id") == subject_id:
                return str(subject.get("name") or subject_id)
        return str(subject_id or "")

    def resolve_subject(self, raw: str) -> str:
        """接受 id（math）或中文名（数学一），返回 id；不认识原样返回。"""
        value = str(raw or "").strip()
        for subject in self.subjects:
            if value == subject.get("id") or value == subject.get("name"):
                return str(subject["id"])
        return value

    # ── 学习记录 ─────────────────────────────────────────────

    @property
    def sessions(self) -> list[dict]:
        return self._data.get("sessions") or []

    def add_session(self, subject: str, minutes: int, note: str = "",
                    day: date | str | None = None) -> str:
        records = self._data.setdefault("sessions", [])
        sid = next_id("s", (r.get("id", "") for r in records), width=4)
        records.append({
            "id": sid,
            "date": _today(day).isoformat(),
            "subject": self.resolve_subject(subject),
            "minutes": int(minutes),
            "note": note or "",
            "created_at": datetime.now().isoformat(),
        })
        return sid

    def minutes_on(self, day: date | str | None = None, subject: str | None = None) -> int:
        target = _today(day).isoformat()
        subject_id = self.resolve_subject(subject) if subject else None
        return sum(int(r.get("minutes") or 0) for r in self.sessions
                   if r.get("date") == target
                   and (subject_id is None or r.get("subject") == subject_id))

    @staticmethod
    def week_start(day: date | str | None = None) -> date:
        target = _today(day)
        return target - timedelta(days=target.weekday())

    def week_minutes(self, day: date | str | None = None,
                     subject: str | None = None) -> int:
        start = self.week_start(day)
        end = start + timedelta(days=6)
        subject_id = self.resolve_subject(subject) if subject else None
        return sum(int(r.get("minutes") or 0) for r in self.sessions
                   if start.isoformat() <= str(r.get("date") or "") <= end.isoformat()
                   and (subject_id is None or r.get("subject") == subject_id))

    def week_by_subject(self, day: date | str | None = None) -> dict[str, int]:
        return {str(s["id"]): self.week_minutes(day, str(s["id"]))
                for s in self.subjects}

    def daily_minutes(self, days: int = 30, day: date | str | None = None) -> dict[str, int]:
        """最近 `days` 天每天的总分钟数（含没学习的天 = 0），用于趋势/复盘。"""
        end = _today(day)
        out: dict[str, int] = {}
        for offset in range(days - 1, -1, -1):
            current = end - timedelta(days=offset)
            out[current.isoformat()] = self.minutes_on(current)
        return out

    def study_streak(self, day: date | str | None = None) -> int:
        """连续达标天数（今天还没达标时，从昨天往前数）。"""
        target = _today(day)
        goal = int(self._data.get("daily_goal_minutes") or 0)
        if goal <= 0:
            return 0
        if self.minutes_on(target) < goal:
            target -= timedelta(days=1)
        streak = 0
        while self.minutes_on(target) >= goal:
            streak += 1
            target -= timedelta(days=1)
        return streak

    def set_daily_goal(self, minutes: int) -> int:
        self._data["daily_goal_minutes"] = max(1, min(int(minutes), MAX_MINUTES))
        return self._data["daily_goal_minutes"]

    # ── 错题本（间隔复习）────────────────────────────────────

    @property
    def mistakes(self) -> list[dict]:
        return self._data.get("mistakes") or []

    def add_mistake(self, subject: str, topic: str, question: str = "",
                    answer: str = "", note: str = "",
                    day: date | str | None = None) -> str:
        records = self._data.setdefault("mistakes", [])
        mid = next_id("m", (r.get("id", "") for r in records), width=4)
        today = _today(day)
        records.append({
            "id": mid,
            "subject": self.resolve_subject(subject),
            "topic": topic or "",
            "question": question or "",
            "answer": answer or "",
            "note": note or "",
            "created_at": datetime.now().isoformat(),
            "stage": 0,
            "interval_days": REVIEW_INTERVALS[0],
            "reviewed_count": 0,
            "next_review": (today + timedelta(days=REVIEW_INTERVALS[0])).isoformat(),
            "mastered": False,
        })
        return mid

    def _find_mistake(self, mid: str) -> dict | None:
        return next((m for m in self.mistakes if m.get("id") == mid), None)

    def review_mistake(self, mid: str, day: date | str | None = None) -> dict | None:
        """复习一次：推进一档；走完阶梯 → 掌握。返回更新后的条目。"""
        mistake = self._find_mistake(mid)
        if mistake is None:
            return None
        if mistake.get("mastered"):
            return mistake
        today = _today(day)
        stage = int(mistake.get("stage") or 0) + 1
        mistake["stage"] = stage
        mistake["reviewed_count"] = int(mistake.get("reviewed_count") or 0) + 1
        if stage >= len(REVIEW_INTERVALS):
            mistake["mastered"] = True
            mistake["next_review"] = None
            mistake["interval_days"] = REVIEW_INTERVALS[-1]
        else:
            interval = REVIEW_INTERVALS[stage]
            mistake["interval_days"] = interval
            mistake["next_review"] = (today + timedelta(days=interval)).isoformat()
        return mistake

    def master_mistake(self, mid: str) -> bool:
        mistake = self._find_mistake(mid)
        if mistake is None:
            return False
        mistake["mastered"] = True
        mistake["next_review"] = None
        return True

    def due_reviews(self, day: date | str | None = None) -> list[dict]:
        """今天该复习的错题（含逾期未复习的），按到期日/科目排序。"""
        today = _today(day).isoformat()
        due = [m for m in self.mistakes
               if not m.get("mastered")
               and str(m.get("next_review") or "") <= today]
        return sorted(due, key=lambda m: (str(m.get("next_review") or ""),
                                          str(m.get("subject") or ""),
                                          str(m.get("id") or "")))

    def open_mistakes(self) -> list[dict]:
        return [m for m in self.mistakes if not m.get("mastered")]

    # ── 模考 ────────────────────────────────────────────────

    @property
    def mocks(self) -> list[dict]:
        return self._data.get("mocks") or []

    def add_mock(self, subject: str, score: float, full_score: float = DEFAULT_FULL_SCORE,
                 duration_minutes: int = 180, note: str = "",
                 day: date | str | None = None) -> str:
        records = self._data.setdefault("mocks", [])
        kid = next_id("k", (r.get("id", "") for r in records), width=3)
        records.append({
            "id": kid,
            "date": _today(day).isoformat(),
            "subject": self.resolve_subject(subject),
            "score": float(score),
            "full_score": float(full_score or DEFAULT_FULL_SCORE),
            "duration_minutes": int(duration_minutes),
            "note": note or "",
            "created_at": datetime.now().isoformat(),
        })
        return kid

    def latest_mock(self, subject: str | None = None) -> dict | None:
        subject_id = self.resolve_subject(subject) if subject else None
        records = [m for m in self.mocks
                   if subject_id is None or m.get("subject") == subject_id]
        if not records:
            return None
        # 同一天同一秒写入时用**插入顺序**兜底（否则 max 会返回第一条）
        indexed = list(enumerate(records))
        _, latest = max(indexed, key=lambda pair: (
            str(pair[1].get("date") or ""),
            str(pair[1].get("created_at") or ""),
            pair[0]))
        return latest

    def mock_history(self, subject: str | None = None, limit: int = 8) -> list[dict]:
        subject_id = self.resolve_subject(subject) if subject else None
        records = [m for m in self.mocks
                   if subject_id is None or m.get("subject") == subject_id]
        records.sort(key=lambda m: (str(m.get("date") or ""),
                                    str(m.get("created_at") or "")))
        return records[-limit:]

    # ── 目标 / 汇总 ─────────────────────────────────────────

    @property
    def target_date(self) -> str:
        raw = str(self._data.get("target_date") or "")
        if raw:
            return raw[:10]
        return default_target()

    def set_target(self, day: date | str) -> str:
        self._data["target_date"] = _today(day).isoformat()
        return self._data["target_date"]

    def countdown(self, day: date | str | None = None) -> int | None:
        try:
            return (date.fromisoformat(self.target_date) - _today(day)).days
        except ValueError:
            return None

    def summary(self, day: date | str | None = None) -> dict:
        """给界面 / CLI / AI 的一张汇总（**全部现算**，不存派生值）。"""
        today = _today(day)
        due = self.due_reviews(today)
        latest = self.latest_mock()
        return {
            "date": today.isoformat(),
            "target_date": self.target_date,
            "days_left": self.countdown(today),
            "daily_goal_minutes": int(self._data.get("daily_goal_minutes") or 0),
            "today_minutes": self.minutes_on(today),
            "week_minutes": self.week_minutes(today),
            "week_by_subject": self.week_by_subject(today),
            "due_reviews": due,
            "due_count": len(due),
            "open_mistakes": len(self.open_mistakes()),
            "studied_days_30": sum(1 for v in self.daily_minutes(30, today).values() if v > 0),
            "streak": self.study_streak(today),
            "latest_mock": latest,
        }


def adopt(data: dict) -> StudyModel:
    """把**已经读出来的 dict** 包成 StudyModel（不触碰磁盘）。

    CLI（`scripts/actions.py`）必须走 `actions_core.load/save` 才能享受
    "写前备份 + 指纹校验 + 原子写"（R-002）。但学习记录/错题的 ID 与复习阶梯
    只应有一份实现 —— 所以这里让命令层复用模型方法，而不是另写一套。
    """
    model = StudyModel.__new__(StudyModel)
    model._data = data if data else copy.deepcopy(DEFAULT_STUDY)
    if not model._data.get("subjects"):
        model._data["subjects"] = [dict(s) for s in DEFAULT_SUBJECTS]
    if not model._data.get("target_date"):
        model._data["target_date"] = default_target()
    return model
