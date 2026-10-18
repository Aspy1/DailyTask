"""数据操作的**核心层**：读写、备份、参数校验、日期与课程名匹配。

被 `scripts/actions.py`（命令层）与测试共用。这里是「AI 不直接写 JSON」这条红线的落点：
`load()` 文件损坏**明说**（绝不当作空数据继续写）、`save()` 结构守卫 + 写前备份 +
`.tmp` + 回读自检 + 原子替换、`_validate_args()` 非法参数**抛错且不写任何文件**。
备份落在 `data/backup/actions/`（在 .gitignore 内），可用 `restore --name X --yes` 回滚。
"""

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.actions_backup import (  # noqa: F401 — 重新导出给 actions.py / 测试用
    DEFAULT_MAX_BACKUPS,
    _backup_dir,
    _backup_file,
    _max_backups,
)
from src.models.base import file_lock, fingerprint

DATA = Path(__file__).parent.parent / "data"

# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)


def _path(name: str) -> Path:
    """按学期分文件的解析：课程/作业/考试进 `semesters/<当前学期>/`，其余在根下。

    这样 `load("tasks.json")` 这类调用点（30+ 处）**不用改**，也不会误写错学期。
    """
    from src.models import semester_paths

    return semester_paths.resolve(DATA, name)


def load(name) -> dict:
    p = _path(name)
    if not p.exists():
        # ⚠ 缺失也要**记一笔**（指纹记 None）：否则"读缺失文件 → 切学期 / 别人先建了它 →
        # 保存"会绕过路径与状态检查，把别人的数据覆盖掉（审查 2026-10-17 第四轮 #1）
        _LOADED[_load_key(name)] = (str(p), None)
        return {}
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        # 文件坏了要**明说**，不能当成空数据继续写（否则等于把用户数据清空）
        raise ActionError(
            f"{p.name} 解析失败（{e}）。请先用 `list_backups` 查看备份，"
            f"再用 `restore --name {p.name} --yes` 恢复。") from e
    if not isinstance(data, dict):
        raise ActionError(f"{p.name} 顶层不是 JSON 对象，拒绝继续操作")
    # 记下"**哪个文件** + 那时的内容指纹"：`save()` 必须用同一组 ——
    # 只记指纹不够：`save()` 会**重新解析**当前学期，切学期后就会把旧学期的快照
    # 写进新学期（审查 2026-10-17 第三轮 #1）。
    _LOADED[_load_key(name)] = (str(p), fingerprint(data))
    return data


def _load_key(name: str) -> tuple[str, str]:
    """`(数据目录, 文件名)` —— **带上数据目录**，否则不同目录之间会串状态
    （测试沙箱一个接一个用不同 tmp 目录，第一条的指纹会污染后面的 ✓→✗）；
    同一个数据目录内换学期仍能检出（解析出的路径变了）。"""
    return str(DATA), name


# 载入时的 (目标路径, 内容指纹)，按 (数据目录, 文件名) 记 —— `save()` 用它判断
# "这份数据在我手上期间，目标文件变了没 / 内容被改过没"
_LOADED: dict[tuple[str, str], tuple[str, str]] = {}


def _disk_fingerprint(p: Path) -> str | None:
    """磁盘当前内容的指纹；文件缺失 / 读不出来 → None（调用方一律判为"变了"）。"""
    try:
        with open(p, encoding="utf-8") as f:
            return fingerprint(json.load(f))
    except (OSError, json.JSONDecodeError):
        return None


# ── 备份（写入前自动留存 + 轮转）：实现搬去 actions_backup.py，
# 顶部已**重新导出**，`actions.py` 与测试的调用点不用改 ──────


def _validate_payload(name: str, obj: dict) -> None:
    """写入前的**结构守卫**：AI 拼错结构时挡在写之前。

    只查廉价但致命的形状（顶层必须是对象；列表字段不能写成字符串/对象），
    目的是让"坏结构永远进不了数据文件"，而不是做完整 schema 校验。
    """
    if not isinstance(obj, dict):
        raise ActionError(f"{name}: 顶层必须是 JSON 对象")
    for key in ("courses", "tasks", "exams", "habits", "items", "records",
                "archived", "semesters"):
        if key in obj and not isinstance(obj[key], list):
            raise ActionError(f"{name}: {key} 必须是数组，收到 {type(obj[key]).__name__}")
    for key in ("plans", "savings", "logs", "holidays"):
        if key in obj and not isinstance(obj[key], dict):
            raise ActionError(f"{name}: {key} 必须是对象，收到 {type(obj[key]).__name__}")


def save(name, obj) -> None:
    """原子写入：结构守卫 → 备份旧文件 → 写 .tmp → 回读自检 → 原子替换。

    此前这里是裸 `json.dump`：写一半断电/并发就是坏文件（ERRORS #041 同类）。

    **整段持 `file_lock`**（与 `BaseJsonModel.save()` 同一套：进程内锁 + OS 级文件锁，
    审查 2026-10-17 #1 / 第三轮 #2），并比对"`load()` 时读到的**路径 + 内容**"：
    路径变了（切学期）或内容变了 → 拒绝，不用旧快照静默覆盖。
    """
    p = _path(name)                 # 现在的解析结果
    _validate_payload(name, obj)
    with file_lock(p):
        seen = _LOADED.get(_load_key(name))
        if seen is not None:
            recorded, recorded_fp = seen
            if str(p) != recorded:
                # 目标文件在"读"与"写"之间换了（切学期 / 改了注册表）→ 拒绝，
                # 否则会把旧学期的快照写进新学期（审查 2026-10-17 第三轮 #1）
                raise ActionError(
                    f"{name} 的目标文件在本次操作期间变了（切了学期？）："
                    f"读取时是 {Path(recorded).parent.name}/，现在是 {p.parent.name}/。"
                    f"已放弃写入，请重新查询后再改。")
            if recorded_fp is None:
                # 读取时这个文件**还不存在** → 现在存在 = 别人（另一个 CLI / 应用）先建了它
                if p.exists():
                    raise ActionError(
                        f"{p.name} 在本次操作期间被其它程序创建了，已放弃写入以免覆盖。"
                        f"请重新查询后再改。")
            elif _disk_fingerprint(p) != recorded_fp:
                raise ActionError(
                    f"{p.name} 在本次操作期间被其它程序改动，已放弃写入以免覆盖。"
                    f"请重新查询后再改（`list_backups` / `restore` 可回滚）。")
        p.parent.mkdir(parents=True, exist_ok=True)
        _backup_file(p)
        tmp = p.with_name(p.name + ".tmp")
        try:
            tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            json.loads(tmp.read_text(encoding="utf-8"))      # 回读自检：写出来必须是合法 JSON
            os.replace(tmp, p)                               # 原子替换
        finally:
            tmp.unlink(missing_ok=True)
        _LOADED[_load_key(name)] = (str(p), fingerprint(obj))

def forget_loaded(name: str) -> None:
    """丢掉 `name` 的载入基准 —— 内容被**整份替换**过（如 `restore`）之后要调它。"""
    _LOADED.pop(_load_key(name), None)


def gen_id(items, prefix) -> str:
    existing = set()
    for it in items:
        try:
            num = int(it["id"].split("_")[1])
            existing.add(num)
        except (KeyError, ValueError):
            logger.debug("gen_id 中忽略异常", exc_info=True)
    n = 1
    while n in existing:
        n += 1
    return f"{prefix}_{n:03d}"

def now_iso() -> str:
    return datetime.now().isoformat()

def _match_exact_course(courses: list, name_lower: str) -> str | None:
    """课程名精确匹配（大小写不敏感）；未命中返回 None。"""
    for c in courses:
        if c.get("name", "").lower() == name_lower:
            return c["name"]
    return None


def _find_contains_matches(courses: list, name_lower: str) -> list[str]:
    """双向包含匹配（输入包含课程名 / 课程名包含输入）。"""
    matches = []
    for c in courses:
        cn = c.get("name", "").lower()
        if name_lower in cn or cn in name_lower:
            matches.append(c["name"])
    return matches


def _find_abbr_matches(courses: list, name_lower: str) -> list[str]:
    """缩写匹配: "算法课" matches "算法设计与分析" (remove 课/程)。"""
    abbr = name_lower.replace("课", "").replace("程", "")
    if abbr == name_lower:
        return []
    matches = []
    for c in courses:
        cn = c.get("name", "").lower()
        if abbr in cn:
            matches.append(c["name"])
    return matches


def _find_word_matches(courses: list, name_lower: str) -> list[str]:
    """分词匹配：任一长度 ≥2 的词出现在课程名中即算命中。"""
    words = set(name_lower.replace("课", "").split())
    matches = []
    for c in courses:
        cn = c.get("name", "").lower()
        if any(w in cn for w in words if len(w) >= 2):
            matches.append(c["name"])
    return matches


def _find_course_matches(courses: list, name_lower: str) -> list[str]:
    """依次尝试「包含 → 缩写 → 分词」，返回首个非空的候选列表。"""
    for finder in (_find_contains_matches, _find_abbr_matches, _find_word_matches):
        matches = finder(courses, name_lower)
        if matches:
            return matches
    return []


def match_course(name: str) -> str | None:
    """Fuzzy match course name. Handles abbreviations like 算法课→算法设计与分析."""
    if not name:
        return None
    data = load("courses.json")
    courses = data.get("courses", [])
    name_lower = name.strip().lower()

    exact = _match_exact_course(courses, name_lower)
    if exact:
        return exact

    matches = _find_course_matches(courses, name_lower)
    if len(matches) == 1:
        return matches[0]
    # Return original if no match
    if not matches:
        return name.strip()
    # Multiple matches — try exact word match first
    return matches[0]

def _parse_relative_date(s: str, today: date, day_names: dict) -> str | None:
    """中文相对日期（下周X / 本周X / 明天 / N天后）→ ISO；不匹配返回 None。"""
    # "下周日"
    m = re.match(r'下周(.)', s)
    if m:
        wd = day_names.get(m.group(1))
        if wd is not None:
            # `7 - weekday + wd` 已经落在「下一个自然周」的同名星期：
            # wd < 今天 时是本周已过、需跨到下周；wd >= 今天 时天然就是下周。
            # ⚠ 不可再 `+= 7`（历史缺陷：会让周一到周五普遍晚一周，ERRORS #021）。
            days_ahead = 7 - today.weekday() + wd
            return (today + timedelta(days=days_ahead)).isoformat()
    # "这周五" / "本周五" / "周五"
    m = re.match(r'(?:这|本)?周(.)', s)
    if m:
        wd = day_names.get(m.group(1))
        if wd is not None:
            days_ahead = wd - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()
    # "明天" / "后天" / "今天"
    offsets = {"明天": 1, "后天": 2, "今天": 0}
    if s in offsets:
        return (today + timedelta(days=offsets[s])).isoformat()
    # "N天后"
    m = re.match(r'(\d+)天后', s)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat()
    return None


def _parse_month_day(s: str, today: date) -> str:
    """月日形式（6月20日 / 6.20 / 6/20）→ ISO；不匹配则原样返回。"""
    for pattern in (r'(\d{1,2})月(\d{1,2})[日号]?', r'(\d{1,2})[./-](\d{1,2})'):
        m = re.match(pattern, s)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            year = today.year
            if month < today.month:
                year += 1
            return f"{year}-{month:02d}-{day:02d}"
    return s


def parse_date(s: str) -> str:
    """Parse date string to YYYY-MM-DD. Supports Chinese relative dates."""
    s = s.strip()
    # Already ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:10]
    today = date.today()
    # Chinese relative
    day_names = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}
    relative = _parse_relative_date(s, today, day_names)
    if relative is not None:
        return relative
    return _parse_month_day(s, today)

def _shift_hour(period: str, hour: int) -> int:
    """中文时段 + 12 小时制小时 → 24 小时制。"""
    if period in ('下午', '晚上'):
        if hour != 12:
            hour += 12
    elif period in ('中午',) and hour < 12:  # 中午1点→13点
        hour += 12
    # 上午/早晨: keep as is (but 12→0 for midnight)
    if period == '上午' and hour == 12:
        hour = 0
    return hour


_ISO_TIME_TAIL = re.compile(r'[T ](\d{1,2}):(\d{2})')
_CN_TIME = re.compile(r'(中午|下午|上午|晚上|早晨|早上)(\d{1,2})点(半|(\d{1,2})分?)?')


def _cn_minute(tail: str, digits: str | None) -> str:
    """中文时间的分钟部分：`半` → 30，`N分` → N，未写 → 00。"""
    if tail == "半":
        return "30"
    if digits:
        minute = int(digits)
        if 0 <= minute < 60:
            return f"{minute:02d}"
    return "00"


def _split_date_time_text(raw: str) -> tuple[str, str]:
    """把 DDL 文本拆成 (日期文本, HH:MM:SS)；未给出时间时第二项为 ""。

    识别 `2026-10-20T14:30` / `2026-10-20 14:30` / `6月20日下午3点` / `明天晚上8点半`。
    """
    s = raw.strip()
    m = _ISO_TIME_TAIL.search(s)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh < 24 and 0 <= mm < 60:
            return (s[:m.start()].strip() or s), f"{hh:02d}:{mm:02d}:00"
        return parse_date(s), ""
    m = _CN_TIME.search(s)
    if m:
        hour = _shift_hour(m.group(1), int(m.group(2)))
        minute = _cn_minute(m.group(3) or "", m.group(4))
        return parse_date(_CN_TIME.sub("", s).strip()), f"{hour:02d}:{minute}:00"
    return parse_date(s), ""


def _normalize_due(raw: str) -> str | None:
    """DDL 文本 → `YYYY-MM-DDThh:mm:ss`；日期非法返回 None。

    ⚠ 必须**先取时间、后归一化日期**：`parse_date` 只保留年月日，
    先调它会把 `2026-10-20T14:30` 截成 `2026-10-20`，具体时间被静默丢弃
    （历史缺陷，见 ERRORS #020）。只给日期时补 23:00:00。
    """
    if not raw.strip():
        return None
    date_text, time_text = _split_date_time_text(raw)
    try:
        date.fromisoformat(date_text)
    except ValueError:
        return None
    return f"{date_text}T{time_text or '23:00:00'}"


# ═══════════════════════════════════════════════════════════
# 输入校验：AI 直接调用这些命令，非法输入必须**拒绝**而不是写进数据
# ═══════════════════════════════════════════════════════════
#
# 设计：校验与执行**分离**。`_validate_args()` 在 handler 之前跑，任何一条不过
# 就抛 ActionError → run_in_process 转成 "ERROR ..." 回给 AI，**文件一个字节都没动**。
# 这样"AI 拼错参数"永远不会变成"数据被改坏"。

MAX_TITLE = 120
MAX_TEXT = 80
MAX_JSON = 500          # JSON 载荷参数（`--instances` / `--membership`）—— 80 字装不下
MAX_NOTE = 500
MAX_QUANTITY = 100000
MAX_AMOUNT = 1_000_000

_ID_RE = re.compile(r"^[a-z]{1,4}_\d{3,4}$")


class ActionError(Exception):
    """参数/数据非法：不写任何文件，只把原因回给调用方。"""


def _fname(field: str) -> str:
    return "--" + field.replace("_", "-")


def _require(ns, *fields: str) -> None:
    for f in fields:
        v = getattr(ns, f, None)
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ActionError(f"缺少必填参数 {_fname(f)}")


def _text(value, field, *, required=False, max_len=MAX_TEXT) -> str:
    if value is None:
        if required:
            raise ActionError(f"缺少必填参数 {_fname(field)}")
        return ""
    s = str(value).strip()
    if required and not s:
        raise ActionError(f"{_fname(field)} 不能为空")
    if len(s) > max_len:
        raise ActionError(f"{_fname(field)} 过长（上限 {max_len} 字，收到 {len(s)} 字）")
    return s


def _integer(value, field, lo, hi, *, default=None) -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is None:
            raise ActionError(f"缺少必填参数 {_fname(field)}")
        return default
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise ActionError(f"{_fname(field)} 必须是整数，收到 {value!r}") from None
    if not lo <= n <= hi:
        raise ActionError(f"{_fname(field)} 必须在 {lo}~{hi} 之间，收到 {n}")
    return n


def _money(value, field) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ActionError(f"缺少必填参数 {_fname(field)}")
    try:
        v = round(float(str(value).strip()), 2)
    except (TypeError, ValueError):
        raise ActionError(f"{_fname(field)} 必须是数字，收到 {value!r}") from None
    if not 0 < v <= MAX_AMOUNT:
        raise ActionError(f"{_fname(field)} 必须大于 0 且不超过 {MAX_AMOUNT}，收到 {v}")
    return v


def _iso_date(value, field, *, default=None) -> str:
    """严格 YYYY-MM-DD（拒绝 2026-02-30 / 2026-13-01 这类"看着像日期"的值）。"""
    raw = str(value).strip() if value is not None else ""
    if not raw:
        if default is None:
            raise ActionError(f"缺少必填参数 {_fname(field)}")
        return default
    try:
        d = date.fromisoformat(raw[:10])
    except ValueError:
        raise ActionError(f"{_fname(field)} 必须是 YYYY-MM-DD 的有效日期，收到 {raw!r}") from None
    if not date(2000, 1, 1) <= d <= date(2100, 12, 31):
        raise ActionError(f"{_fname(field)} 超出合理范围：{d.isoformat()}")
    return d.isoformat()


def _month(value, field="month") -> str:
    """YYYY-MM（缺省为当月）。"""
    raw = str(value).strip() if value is not None else ""
    if not raw:
        return date.today().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-\d{2}", raw):
        raise ActionError(f"{_fname(field)} 必须是 YYYY-MM，收到 {raw!r}")
    m = int(raw[5:7])
    if not 1 <= m <= 12:
        raise ActionError(f"{_fname(field)} 月份非法：{raw!r}")
    return raw


def _due(value, field="due") -> str:
    """截止时间：先按自然语言解析，再校验结果（保留"下周日/6月20日"这类输入）。"""
    raw = _text(value, field, required=True)
    due = _normalize_due(raw)
    if due is None:
        raise ActionError(
            f"{_fname(field)} 无法识别：{raw!r}（用 YYYY-MM-DD 或 YYYY-MM-DDThh:mm）")
    return due


def _choice(value, field, allowed, *, default=None) -> str:
    raw = str(value).strip() if value is not None else ""
    if not raw:
        if default is None:
            raise ActionError(f"缺少必填参数 {_fname(field)}")
        return default
    if raw not in allowed:
        raise ActionError(f"{_fname(field)} 只能是 {'/'.join(allowed)}，收到 {raw!r}")
    return raw


def _record_id(value, field="id") -> str:
    raw = _text(value, field, required=True)
    if not _ID_RE.match(raw):
        raise ActionError(f"{_fname(field)} 格式应为 <前缀>_<三位数>（如 t_001），收到 {raw!r}")
    return raw


def _weeks_range(value, field="weeks") -> tuple[int, int]:
    raw = _text(value, field, required=True)
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", raw)
    if not m:
        raise ActionError(f"{_fname(field)} 格式应为 起-止（如 1-16），收到 {raw!r}")
    a, b = int(m.group(1)), int(m.group(2))
    if not (1 <= a <= b <= 30):
        raise ActionError(f"{_fname(field)} 必须满足 1 ≤ 起 ≤ 止 ≤ 30，收到 {raw!r}")
    return a, b


def _slots_range(value, field="slots") -> tuple[int, int]:
    raw = _text(value, field, required=True)
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", raw)
    if not m:
        raise ActionError(f"{_fname(field)} 格式应为 起-止（如 3-4），收到 {raw!r}")
    a, b = int(m.group(1)), int(m.group(2))
    if not (1 <= a <= b <= 6):        # 一天 6 个大节
        raise ActionError(f"{_fname(field)} 必须满足 1 ≤ 起 ≤ 止 ≤ 6，收到 {raw!r}")
    return a, b


def _schedule_spec(value, field="schedule") -> str:
    """daily/N | weekly/1,3,5 | monthly/N。"""
    raw = _text(value, field, required=True)
    typ, _, val = raw.partition("/")
    if typ == "daily" or typ == "monthly":
        _integer(val, field, 1, 30)
    elif typ == "weekly":
        days = [d.strip() for d in val.split(",") if d.strip()]
        if not days:
            raise ActionError(f"{_fname(field)} 的 weekly 需要列出星期几，如 weekly/1,3,5")
        for d in days:
            _integer(d, field, 1, 7)
    else:
        raise ActionError(f"{_fname(field)} 只支持 daily/N、weekly/1,3,5、monthly/N，收到 {raw!r}")
    return raw


def _resolve_category(value, categories: list[dict]) -> str:
    """分类：接受 id（food）或中文名（餐饮）；都不匹配则报错并列出可选项。"""
    raw = _text(value, "category", required=True)
    known = {str(c.get("id", "")): str(c.get("name", "")) for c in categories}
    if raw in known:
        return raw
    for cid, cname in known.items():
        if cname and cname == raw:
            return cid
    allowed = "、".join(f"{cid}({cname})" for cid, cname in known.items()) or "（数据里没有分类）"
    raise ActionError(f"--category 不认识 {raw!r}，可用：{allowed}")


# 每个命令允许出现的参数（防止 AI 拼错 --titel 之类被静默忽略）。
# ⚠ 与 CLI 的 subparser 由 tests/test_actions_validation.py 交叉校验，避免漂移。
ALLOWED_OPTIONS: dict[str, set[str]] = {
    "add_task": {"course", "title", "due", "priority", "tags", "notes"},
    "complete_task": {"id"},
    "add_exam": {"course", "date", "scope", "location", "notes", "tags"},
    "add_habit": {"name", "schedule", "duration", "reminder"},
    "log_habit": {"id"},
    "add_plan": {"date", "title", "slot", "type", "course", "note"},
    "replace_plans": {"date", "plans"},
    "delete_plan": {"date", "index"}, "complete_plan": {"date", "index"},
    "add_course": {"name", "day", "weeks", "slots", "location", "teacher", "parity"},
    "delete_course": {"id"},
    "update_course": {"id", "name", "day", "weeks", "slots", "location",
                      "teacher", "parity"},
    "add_item": {"name", "category", "quantity", "min_qty", "min_doses", "location", "notes", "group",
                 "tags", "status", "unit", "doses_per_unit", "instances", "membership", "runs_out",
                 "runs_out_months", "worn_days", "needs_wash", "expires", "remind_before"},
    "update_item": {"id", "name", "group", "category", "quantity", "status", "min_qty", "min_doses",
                    "location", "tags", "unit", "doses_per_unit", "instances", "membership", "notes",
                    "runs_out", "runs_out_months", "worn_days", "needs_wash", "expires", "remind_before"},
    "consume": {"id", "amount"},
    "set_locations": {"values"},
    "delete_item": {"id"},
    "need_restock": set(),
    "lookup_item": {"name", "category", "tag", "location", "restock"}, "add_location": {"name"},
    "status": set(),
    "add_expense": {"amount", "category", "note", "date"},
    "add_saving": {"amount", "note", "date"},
    "delete_expense": {"id"},
    "expense_summary": {"month"},
    "list_backups": {"name"},
    "restore": {"name", "stamp", "yes"},
}


# 参数规格（**数据驱动**）：{动作: {"required": (必填项…), 参数名: 规则}}
#
# 规则 = (kind, …)：
#   text(len)       文本，去空白 + 长度上限（非空由 required 负责）
#   due             截止时间（先按自然语言解析，再校验）
#   date / date_opt 严格 YYYY-MM-DD；date_opt 允许不传（命令内取默认）
#   month           YYYY-MM（不传取当月）
#   money           金额（>0，两位小数）
#   int(lo,hi)      必填整数范围
#   int_opt(lo,hi)  可缺省整数范围（None 允许：要能区分「没传」与「传 0」）
#   choice(…)       枚举（可缺省）
#   id              ID 形如 t_001
#   weeks / slots   起-止 区间（周次 1~30 / 节次 1~6）
#   schedule        习惯周期 daily/N、weekly/1,3,5、monthly/N
#   reminder        hh:mm（或空）
#   jsonplans       计划 JSON 数组
SPECS: dict[str, dict] = {
    "add_task": {
        "required": ("title", "due"),
        "title": ("text", MAX_TITLE), "due": ("due",),
        "priority": ("choice", ("high", "medium", "low")),
        "course": ("text", MAX_TEXT), "notes": ("text", MAX_NOTE),
        "tags": ("text", MAX_NOTE),
    },
    "complete_task": {"required": ("id",), "id": ("id",)},
    "add_exam": {
        "required": ("course", "date"),
        "course": ("text", MAX_TEXT), "date": ("date",),
        "scope": ("text", MAX_NOTE), "location": ("text", MAX_TEXT),
        "notes": ("text", MAX_NOTE), "tags": ("text", MAX_NOTE),
    },
    "add_habit": {
        "required": ("name",),
        "name": ("text", MAX_TITLE), "schedule": ("schedule",),
        "duration": ("int_opt", 1, 600), "reminder": ("reminder",),
    },
    "log_habit": {"required": ("id",), "id": ("id",)},
    "add_plan": {
        "required": ("date", "title"),
        "date": ("date",), "title": ("text", MAX_TITLE),
        "slot": ("int_opt", 1, 6), "type": ("text", MAX_TEXT),
        "course": ("text", MAX_TEXT), "note": ("text", MAX_NOTE),
    },
    "replace_plans": {
        "required": ("date", "plans"),
        "date": ("date",), "plans": ("jsonplans",),
    },
    "delete_plan": {
        "required": ("date", "index"),
        "date": ("date",), "index": ("int", 0, 100),
    },
    "complete_plan": {"required": ("date", "index"), "date": ("date",), "index": ("int", 0, 100)},
    "add_course": {
        "required": ("name", "day"),
        "name": ("text", MAX_TITLE), "day": ("int", 1, 7),
        "weeks": ("weeks",), "slots": ("slots",),
        "parity": ("choice", ("all", "odd", "even")),
        "location": ("text", MAX_TEXT), "teacher": ("text", MAX_TEXT),
    },
    "delete_course": {"required": ("id",), "id": ("id",)},
    "update_course": {
        "required": ("id",), "id": ("id",),
        "name": ("text", MAX_TITLE), "day": ("int_opt", 1, 7),
        "weeks": ("weeks_opt",), "slots": ("slots_opt",),
        "parity": ("choice", ("all", "odd", "even")),
        "location": ("text", MAX_TEXT), "teacher": ("text", MAX_TEXT),
    },
    "add_item": {
        "required": ("name",),
        "name": ("text", MAX_TITLE), "category": ("text", MAX_TEXT),
        "quantity": ("int_opt", 0, MAX_QUANTITY), "membership": ("text", MAX_JSON),
        "min_qty": ("int_opt", 0, MAX_QUANTITY),
        "location": ("text", MAX_TEXT), "notes": ("text", MAX_NOTE),
        "group": ("text", MAX_TEXT), "tags": ("text", MAX_NOTE),
        "status": ("text", MAX_TEXT),          # CLI 接受但忽略（状态自动推导）
        "unit": ("text", MAX_TEXT), "doses_per_unit": ("int_opt", 1, MAX_QUANTITY),
        "min_doses": ("int_opt", 0, MAX_QUANTITY),   # 片级下限（0 = 不用）
        "instances": ("text", MAX_JSON),       # JSON 数组，handler 里解析
    },
    "update_item": {
        "required": ("id",), "id": ("id",),
        "quantity": ("int_opt", 0, MAX_QUANTITY), "membership": ("text", MAX_JSON),
        "min_qty": ("int_opt", 0, MAX_QUANTITY),
        "status": ("choice", ("充足", "不足", "需购")),
        "name": ("text", MAX_TITLE), "group": ("text", MAX_TEXT),
        "category": ("text", MAX_TEXT), "location": ("text", MAX_TEXT),
        "notes": ("text", MAX_NOTE),
        "tags": ("text", MAX_NOTE),
        "unit": ("text", MAX_TEXT), "doses_per_unit": ("int_opt", 1, MAX_QUANTITY),
        "min_doses": ("int_opt", 0, MAX_QUANTITY),
        "instances": ("text", MAX_JSON), "runs_out": ("text", MAX_TEXT),
        "runs_out_months": ("int_opt", 1, 600),
        "worn_days": ("int_opt", 0, 3650), "needs_wash": ("choice", ("yes", "no")),
        "expires": ("text", MAX_TEXT), "remind_before": ("int_opt", 1, 3650),
    },
    "consume": {"required": ("id",), "id": ("id",),
                "amount": ("int_opt", 1, MAX_QUANTITY)},
    "set_locations": {"required": ("values",), "values": ("text", MAX_NOTE)},
    "delete_item": {"required": ("id",), "id": ("id",)},
    "lookup_item": {"name": ("text", MAX_TITLE), "category": ("text", MAX_TEXT),
                    "tag": ("text", MAX_TEXT), "location": ("text", MAX_TEXT),
                    "restock": ("choice", ("yes", "no"))},
    "add_location": {"required": ("name",), "name": ("text", MAX_TEXT)},
    "add_expense": {
        "required": ("amount", "category"),
        "amount": ("money",), "category": ("text", MAX_TEXT),
        "note": ("text", MAX_NOTE), "date": ("date_opt",),
    },
    "add_saving": {
        "required": ("amount",),
        "amount": ("money",), "note": ("text", MAX_NOTE), "date": ("date_opt",),
    },
    "delete_expense": {"required": ("id",), "id": ("id",)},
    "expense_summary": {"month": ("month",)},
    "list_backups": {"name": ("text", MAX_TEXT)},
    "restore": {"required": ("name",), "name": ("text", MAX_TEXT),
                "stamp": ("text", MAX_TEXT)},
}


def _known_categories() -> list[dict]:
    """可用支出分类：优先数据文件里的；文件不存在时退回模型默认值。

    （AI 在全新数据目录上第一次记账时文件还不存在，校验不能因此拒绝。）
    """
    cats = load("expenses.json").get("categories")
    if isinstance(cats, list) and cats:
        return cats
    try:
        from src.models.expense import DEFAULT_EXPENSES

        return list(DEFAULT_EXPENSES.get("categories", []))
    # 边界捕获：模型结构被改也只需退化成"没有可用分类"，不应让校验崩掉
    except Exception:
        logger.debug("读取默认支出分类失败", exc_info=True)
        return []


def _text_or_empty(value, field: str, max_len: int = MAX_TEXT) -> str:
    """可缺省文本：空/None 放过，非空则限长。"""
    if value is None or not str(value).strip():
        return ""
    return _text(value, field, max_len=max_len)


def _reminder(value, field: str = "reminder") -> None:
    raw = _text_or_empty(value, field)
    if raw and not re.fullmatch(r"\d{1,2}:\d{2}", raw):
        raise ActionError(f"{_fname(field)} 应为 hh:mm，收到 {raw!r}")


def _json_plans(value, field: str = "plans") -> None:
    try:
        plans = json.loads(_text(value, field, required=True, max_len=20_000))
    except json.JSONDecodeError as e:
        raise ActionError(f"{_fname(field)} 不是合法 JSON：{e}") from None
    if not isinstance(plans, list):
        raise ActionError(f"{_fname(field)} 必须是 JSON 数组")
    for i, p in enumerate(plans):
        if not isinstance(p, dict):
            raise ActionError(f"{_fname(field)}[{i}] 必须是对象")
        _text(p.get("title"), "plans.title", required=True, max_len=MAX_TITLE)
        if "time_slot" in p:
            _integer(p.get("time_slot"), "plans.time_slot", 1, 6)


def _apply_rule(value, field: str, rule: tuple) -> None:
    """按规格里的规则校验单个参数。

    规则名带 `_opt` 后缀 = **可缺省**（None/空直接放过，命令内自己取默认），
    其余规则要求有值。用"提前 return + 查表"，而不是一条 20 分支的 if/elif ——
    后者会被 radon 判为高复杂度（C 级以上），门禁会拦。
    """
    kind, *rest = rule
    if kind.endswith("_opt"):
        if value is None or not str(value).strip():
            return
        kind = kind[: -len("_opt")]
    if kind == "text":
        _text_or_empty(value, field, rest[0])
        return
    if kind == "int":
        _integer(value, field, rest[0], rest[1])
        return
    if kind == "choice":
        _choice(value, field, rest[0], default="")
        return

    simple = {
        "due": _due, "date": _iso_date, "month": _month,
        "money": _money, "id": _record_id, "weeks": _weeks_range,
        "slots": _slots_range, "schedule": _schedule_spec,
        "reminder": _reminder, "jsonplans": _json_plans,
    }
    fn = simple.get(kind)
    if fn is None:
        # 规格表写错时必须炸出来，而不是静默放过一条参数
        raise ActionError(f"内部错误：未知校验规则 {kind!r}（字段 {_fname(field)}）")
    fn(value, field)


def _validate_args(action: str, ns) -> None:
    """按 SPECS 逐项校验参数；不通过就抛 ActionError（调用方负责转成错误信息）。"""
    spec = SPECS.get(action)
    if not spec:
        return                                  # need_restock / status 无参数
    for field in spec.get("required", ()):
        _require(ns, field)
    for field, rule in spec.items():
        if field == "required":
            continue
        _apply_rule(getattr(ns, field, None), field, rule)
    if action == "add_expense":
        # 分类必须落在可用分类表里（id 或中文名），否则拒绝
        _resolve_category(ns.category, _known_categories())
