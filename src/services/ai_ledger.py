"""AI 动作**账本**与**错误分类恢复**（专项审查 §3.1 / §3.4 / §2.3 的落地，2026-10-19）。

**账本（§3.1）**：完成率要按**目标**算，不能用"成功命令数 ÷ 总命令数"充数 ✗。
本项目能达到的最细粒度是**一条写命令** —— 自由文本的请求无法在代码里可靠分解
（那需要模型参与，属后续工作）。关键差别在**状态从哪来**：这里的状态来自**验收**
（`ai_verify` 回读数据），不是"handler 返回 OK" ✓。

**恢复（§2.3）**：把 ERROR **分类**，连同"该做什么 / 不能做什么"一起回喂模型。
原来只把 ERROR 原文丢回去，模型只能猜 —— 而 α 测试里真实出现过三种猜法 ✗：
"原样重发同一条"、"猜一个 id"、"为了让命令过自己加 `--yes`"。

分类只认执行层给的**原文**，按确定性关键词归类（关键词取自 `scripts/` 里真实的 ERROR 文案）；
归不到类的**明说"未分类"**，不硬套 ✓。
"""

from dataclasses import dataclass, field

# 账本状态（§3.1 的 pending/verified/failed/blocked + 本项目的 noop/mismatch/unverified）
PENDING = "pending"
VERIFIED = "verified"
NOOP = "verified_noop"
MISMATCH = "mismatch"
FAILED = "failed"
BLOCKED = "blocked"
UNVERIFIED = "unverified"

# 状态 → 给用户看的中文（汇报按**状态**分组，不按命令数 ✗）
STATE_LABEL = {
    VERIFIED: "验收通过",
    NOOP: "本来已满足",
    MISMATCH: "没达到预期",
    FAILED: "执行失败",
    BLOCKED: "被阻塞",
    UNVERIFIED: "未验收",
    PENDING: "未执行",
}

# §2.3 的恢复表：类别 → (该做什么, 不能做什么)
# 关键词按 `scripts/` 里**真实出现的 ERROR 文案**归类（不是凭想象写）。
_RULES: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (("未知参数", "必须在", "超出范围", "必须是", "不能为空", "无法识别", "invalid", "requires"),
     "参数不合法", "按字段级错误改参数后重试", "原样重复同一条命令"),
    (("已有同名同位置", "重复"),
     "对象已存在", "用 `update_item` 改那一条（回执里有 id）",
     "为了「记上」再建一条同样的"),
    (("not found", "找不到", "没有这条", "的备份"),
     "对象不存在", "先查询候选（`lookup_item` / `list_*`）或向用户澄清",
     "猜一个 id，或擅自新建替代对象"),
    (("冲突", "conflict", "保存被拒", "改过", "版本"),
     "保存冲突", "重读最新状态，保留原意重新算改动", "关掉冲突检测硬覆盖"),
    (("需要显式", "--yes", "确认"),
     "需要用户授权", "把这条**转达给用户**，等他们自己确认",
     "自己加 `--yes` 替用户拍板"),
    (("损坏", "备份", "解析失败"),
     "数据异常", "保留已完成的部分，如实说明卡在哪",
     "绕过合法入口去改文件"),
)


@dataclass
class Goal:
    """一条**写命令** = 一个可验收的目标。"""

    command: str
    state: str = PENDING
    detail: str = ""
    label: str = ""          # 对象名（"布洛芬" / "羽绒服" / 计划标题）—— 事实行里要写清楚


# 操作 → 中文动词（事实行的开头）。没登记的退化成操作名本身。
VERB = {
    "add_item": "记入", "update_item": "更新", "delete_item": "删除", "consume": "扣减",
    "add_task": "记作业", "complete_plan": "标记完成", "delete_plan": "删除日程",
    "add_plan": "记日程", "replace_plans": "重排日程",
    "add_expense": "记支出", "add_habit": "记习惯",
    "update_course": "改课表", "add_course": "加课程", "delete_course": "删课程",
    "add_exam": "记考试", "update_exam": "改考试",
}


def fact_line(goal: Goal) -> str:
    """一条写命令 → **给用户看的事实行**（乙方案：事实由代码写，模型只解释）。

    状态用**中文**表达，不用 ✓/✗ 之类的符号（用户明确不要）。
    """
    from src.services import ai_verify

    operation, _args = ai_verify.parse_command(goal.command)
    head = f"{VERB.get(operation, operation or '动作')}{(' ' + goal.label) if goal.label else ''}"
    if goal.state == VERIFIED:
        return f"{head}：{goal.detail}"
    if goal.state == NOOP:
        return f"{head}：无需改动"
    if goal.state == MISMATCH:
        return f"{head}：**没有达到预期** —— {goal.detail}"
    if goal.state == FAILED:
        return f"{head}：**没有生效** —— {goal.detail}"
    if goal.state == BLOCKED:
        return f"{head}：被阻塞 —— {goal.detail}"
    return f"{head}：未核对"


def fact_lines(goals: list[Goal]) -> list[str]:
    """整批账本 → 事实行列表（空账本 → 空列表，界面就不会多一块）。"""
    return [fact_line(goal) for goal in goals or []]


def render_facts(ledger: "Ledger", model_text: str) -> str:
    """**乙方案的渲染**：事实块在前、模型的话作为说明在后。

    - 有写命令 → 两块分开（【已执行】/【说明】）；模型那句**不重复**事实，只解释 ✓；
    - 没有写命令（纯查询 / 闲聊）→ 只有模型的话 ✓（丙：不显示"未核对"）。
    """
    facts = fact_lines(ledger.goals if ledger else [])
    if not facts:
        return model_text
    lines = ["【已执行】", *[f"  {f}" for f in facts]]
    if model_text:
        lines += ["", "【说明】", f"  {model_text}"]
    return "\n".join(lines)


@dataclass
class Ledger:
    """本次请求的账本：逐条记状态，汇报时**按状态分组**。"""

    goals: list[Goal] = field(default_factory=list)

    def record(self, command: str, state: str, detail: str = "", label: str = "") -> None:
        self.goals.append(Goal(command=command, state=state, detail=detail, label=label))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for goal in self.goals:
            out[goal.state] = out.get(goal.state, 0) + 1
        return out

    def summary(self) -> str:
        """一句话账本（按状态分组；没有写命令就返回空串）。"""
        counts = self.counts()
        if not counts:
            return ""
        parts = [f"{STATE_LABEL.get(s, s)} {n}" for s, n in counts.items()]
        return "本次账本：" + " · ".join(parts)

    def is_clean(self) -> bool:
        """全绿吗 —— 有"没达到预期 / 执行失败 / 被阻塞"就不算干净。"""
        counts = self.counts()
        return not any(counts.get(state) for state in (MISMATCH, FAILED, BLOCKED))


def classify_error(result: str) -> tuple[str, str, str]:
    """把一条 ERROR 归类 → `(类别, 该做什么, 不能做什么)`；归不到 → `("未分类", "", "")`。

    ⚠ 判据是**执行层给的原文**，不猜 ✓ —— 归不到类就让模型自己看原文（总比硬套一个错类别好）。
    """
    text = str(result or "")
    for keywords, name, should, must_not in _RULES:
        if any(kw in text for kw in keywords):
            return name, should, must_not
    return "未分类", "", ""


def recovery_note(results: list[str]) -> str:
    """给失败的那几条配上"下一步怎么办"（§2.3）—— 附在工具结果后面回喂模型。

    没失败 / 归不到类 → 空串（不啰嗦）。
    """
    lines = []
    for result in results or []:
        if str(result).startswith("OK"):
            continue
        name, should, must_not = classify_error(result)
        if not should:
            continue
        lines.append(f"  [{name}] 该做：{should}；**不要**：{must_not}")
    if not lines:
        return ""
    return "\n[恢复建议]\n" + "\n".join(dict.fromkeys(lines))
