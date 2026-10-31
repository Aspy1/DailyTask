"""考研备考命令的验收器（从 `ai_verify.py` 分出：单文件 ≤800 行，Q-A1）。"""

from datetime import date
from pathlib import Path

from src.models.study import StudyModel
from src.models.study import adopt as adopt_study
from src.services.ai_verify import MISMATCH, NOOP, UNVERIFIED, VERIFIED, _read


def _study(data_dir: Path) -> StudyModel:
    return adopt_study(_read(data_dir, "study.json"))


def _label_study_subject(args: dict, data_dir: Path) -> str:
    model = _study(data_dir)
    return model.subject_name(model.resolve_subject(str(args.get("subject") or "")))


def _label_study_topic(args: dict, data_dir: Path) -> str:
    return str(args.get("topic") or "")


def _label_study_target(args: dict, data_dir: Path) -> str:
    return str(args.get("date") or "")


def _observe_log_study(args: dict, data_dir: Path) -> dict:
    return {"count": len(_study(data_dir).sessions)}


def _check_log_study(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    model = _study(data_dir)
    subject = model.resolve_subject(str(args.get("subject") or ""))
    day = args.get("date") or date.today().isoformat()
    try:
        minutes = int(args.get("minutes", "0"))
    except ValueError:
        return UNVERIFIED, "未验收（minutes 不是整数）"
    hit = any(r.get("date") == day and r.get("subject") == subject
              and int(r.get("minutes") or 0) == minutes for r in model.sessions)
    if len(model.sessions) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"{model.subject_name(subject)} {minutes} 分钟已记录"
    return MISMATCH, f"学习记录里找不到 {model.subject_name(subject)} {minutes} 分钟"


def _observe_add_mistake(args: dict, data_dir: Path) -> dict:
    return {"count": len(_study(data_dir).mistakes)}


def _check_add_mistake(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    model = _study(data_dir)
    subject = model.resolve_subject(str(args.get("subject") or ""))
    topic = str(args.get("topic") or "")
    hit = any(m.get("subject") == subject and m.get("topic") == topic
              for m in model.mistakes)
    if len(model.mistakes) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"错题「{topic}」已记入复习队列"
    return MISMATCH, f"错题本里找不到「{topic}」"


def _observe_review_mistake(args: dict, data_dir: Path) -> dict:
    mistake = next((m for m in _study(data_dir).mistakes
                    if m.get("id") == args.get("id")), {})
    return {"stage": int(mistake.get("stage") or 0),
            "mastered": bool(mistake.get("mastered"))}


def _check_review_mistake(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    mistake = next((m for m in _study(data_dir).mistakes
                    if m.get("id") == args.get("id")), None)
    if mistake is None:
        return MISMATCH, f"错题 {args.get('id', '')} 不在了"
    stage = int(mistake.get("stage") or 0)
    if mistake.get("mastered") and not before.get("mastered"):
        return VERIFIED, "走完复习阶梯，已标记掌握"
    if stage > int(before.get("stage", -1)):
        return VERIFIED, f"复习档位推进到第 {stage} 档"
    return MISMATCH, "复习档位没有推进"


def _observe_master_mistake(args: dict, data_dir: Path) -> dict:
    mistake = next((m for m in _study(data_dir).mistakes
                    if m.get("id") == args.get("id")), {})
    return {"mastered": bool(mistake.get("mastered"))}


def _check_master_mistake(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    mistake = next((m for m in _study(data_dir).mistakes
                    if m.get("id") == args.get("id")), None)
    if mistake is None:
        return MISMATCH, f"错题 {args.get('id', '')} 不在了"
    if mistake.get("mastered"):
        if before.get("mastered"):
            return NOOP, "本来就是掌握状态"
        return VERIFIED, "已标记掌握"
    return MISMATCH, "没有标记掌握"


def _observe_add_mock(args: dict, data_dir: Path) -> dict:
    return {"count": len(_study(data_dir).mocks)}


def _check_add_mock(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    model = _study(data_dir)
    subject = model.resolve_subject(str(args.get("subject") or ""))
    day = args.get("date") or date.today().isoformat()
    try:
        score = int(args.get("score", "0"))
    except ValueError:
        return UNVERIFIED, "未验收（score 不是整数）"
    hit = any(m.get("subject") == subject and m.get("date") == day
              and int(m.get("score") or 0) == score for m in model.mocks)
    if len(model.mocks) > int(before.get("count", -1)) and hit:
        return VERIFIED, f"模考 {model.subject_name(subject)} {score} 分已记录"
    return MISMATCH, "模考记录里找不到这一条"


def _observe_study_set_target(args: dict, data_dir: Path) -> dict:
    model = _study(data_dir)
    return {"target": model.target_date,
            "goal": int(model.data.get("daily_goal_minutes") or 0)}


def _check_study_set_target(before: dict, args: dict, data_dir: Path) -> tuple[str, str]:
    model = _study(data_dir)
    if model.target_date != str(args.get("date") or "")[:10]:
        return MISMATCH, f"目标日期还是 {model.target_date}"
    if (args.get("daily_goal") not in (None, "")
            and int(model.data.get("daily_goal_minutes") or 0) != int(args["daily_goal"])):
        return MISMATCH, "每日目标没改成功"
    return VERIFIED, f"目标日期已设为 {model.target_date}"


STUDY_LABELERS = {
    "log_study": _label_study_subject,
    "add_mock": _label_study_subject,
    "add_mistake": _label_study_topic,
    "study_set_target": _label_study_target,
}

STUDY_OBSERVERS = {
    "log_study": _observe_log_study,
    "add_mistake": _observe_add_mistake,
    "review_mistake": _observe_review_mistake,
    "master_mistake": _observe_master_mistake,
    "add_mock": _observe_add_mock,
    "study_set_target": _observe_study_set_target,
}

STUDY_CHECKS = {
    "log_study": _check_log_study,
    "add_mistake": _check_add_mistake,
    "review_mistake": _check_review_mistake,
    "master_mistake": _check_master_mistake,
    "add_mock": _check_add_mock,
    "study_set_target": _check_study_set_target,
}
