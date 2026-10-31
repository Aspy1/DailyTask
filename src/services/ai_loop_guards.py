"""Agent 循环的**护栏**（判断"这一轮到底算不算完成"）。

从 `ai_service.py` 搬出来（那个文件正好 800 行上限）：这一族是**纯函数**，
不碰 Qt、不碰 Model，只按文本 + 命令名 + 数据变化做判断。

设计依据（`Agent Reliability Engineering Design Guide`）：
- §2.3 "the agent is also the reporter"：**模型的自我描述不是测量**；
- §4.3：进度谓词里**必须排除模型的自述**；
- §6.3：**提示词不是安全机制**，强制点在代码边界。

⚠ 名字保持下划线开头：调用方（`ai_service`）与测试都按原名导入。
"""

READ_ONLY = ("lookup_item", "need_restock", "status")
# 记账类：为写物品做准备，**不算**用户可见效果（否则"只加了位置"会被当成成功）
BOOKKEEPING = ("add_location", "set_locations")


def _looks_like_tool_call(text: str) -> bool:
    """模型是否改用了"工具调用"格式（本项目**不解析**它）。

    2026-10-18 探针实测：模型偶尔输出 `<｜｜DSML｜｜ invoke name="add_item">…<｜｜DSML｜｜ parameter …>`
    —— `InstructionParser` 只认 ```sh 代码块，于是那一轮**什么都不做**（用户看起来就是
    "AI 没反应"）。这里识别出来，好让上层明确纠正格式。
    """
    return "invoke name=" in text or "<｜" in text or "｜>" in text

def _claims_done(text: str) -> bool:
    """模型是不是在**声称已经写入**（"已记录 / 已录入 / 已更新 / 已将…改为"…）。

    2026-10-18 α 实测：模型有时只说"已记录：毛巾 2 条…"却**一条命令都没发** —— 数据其实没变 ✗。

    ⚠ 这只是**措辞表**，天生漏词 ✗（2026-10-19 评估集实测：模型说"已将羽绒服的位置改为家"，
    而"已将"当时不在表里 → 警示与统计都漏了）。所以**"有没有命令"这个更强的判据**
    在 `AIWorker._status_note` 里独立生效 —— 零命令时**不看措辞**也警告 ✓（§2.3 汇报权归代码）。
    """
    return any(m in text for m in ("已记录", "已录入", "已更新", "已加入", "已新增", "已保存",
                                   "已完成", "已将", "已改", "已移", "已设", "已标记", "已删除"))

def _has_write_cmd(commands: list) -> bool:
    """这批命令里有没有**用户可见的写操作**（记账类不算）。"""
    names = [str(c).split("actions.py", 1)[-1].strip().split()[:1] for c in commands]
    skip = ("lookup_item", "need_restock", "status", "add_location", "set_locations")
    return any(n and n[0] not in skip for n in names)

def cmds_key(commands: list) -> str:
    """一批命令的**指纹**（排序后拼接）—— 用于"同一批命令重复了几次"的循环检测（§4）。"""
    return "|".join(sorted(str(c).strip() for c in commands))


def repeat_nudge(seen: dict, key: str, produced_effect: bool) -> str | None:
    """同一批命令**重复出现**且毫无效果 → 给模型一条事实（§4 分级响应：告知 → 收束）。

    为什么需要：只靠 `max_turns` 计数器是"等浪费发生完才停"，而且不说明为什么（§14 反模式
    "A counter is treated as a loop detector"）。这里按 §4.4 的阶梯：第 1 次**告知**，
    第 2 次**收束**（禁止再发同一批）。
    """
    n = seen.get(key, 0)
    if n < 2 or produced_effect:
        return None
    if n == 2:
        return ("[事实] 这一批命令**刚才已经执行过一次**，结果不会变（数据没有任何改动）。"
                "请换个做法，或者直接说明做不到 / 还缺什么信息。")
    return ("[系统] 同一批命令已经重复 3 次且毫无效果。**不要再发它** —— "
            "要么换一条完全不同的命令，要么直接说明原因。")


def _continuation_nudge(text: str, truncated: bool, empty_retries: int = 0,
                        wrote_data: bool = False) -> str | None:
    """该不该要求模型"继续"？空回复 / 截断 / 声称写了却没命令 / 说"无需写入"却一条没执行 → 续跑；
    非空的普通提问**不**续跑（否则会把问题刷 5 遍）。
    """
    if not text.strip():
        if empty_retries >= 1:
            return None
        return ("[系统] 你上一轮没有输出任何内容。请**直接**输出 ```sh 命令块"
                "（每轮最多 8 条），不要长篇思考，也不要只解释。")
    if _looks_like_tool_call(text):
        # 模型改用了"工具调用"格式（`<｜｜DSML｜｜ invoke name=…>` 之类）→ 解析器认不出，
        # 等于什么都没做。明确纠正格式，只纠正一次（2026-10-18 探针实测遇到）
        if empty_retries >= 1:
            return None
        return ("[系统] 你用的是**工具调用格式**，本项目不解析它。请改用 ```sh 代码块，"
                "每行一条 `python scripts/actions.py …` 命令。")
    if truncated:
        return ("[系统] 你的回复被输出上限截断了。请**分批**继续："
                "每轮最多 8 条命令，先执行完这批再继续下一批。")
    return _claim_nudge(text, empty_retries, wrote_data)


def _claim_nudge(text: str, empty_retries: int, wrote_data: bool) -> str | None:
    """**声称写了却没命令** / **说"无需写入"却一条没执行** → 要求它真的输出命令。

    两种都只纠正两次（再刷就是模型/网关的问题，别让用户白等）。
    """
    if empty_retries >= 2 or wrote_data:
        return None
    if _claims_done(text):
        return ("[系统] 你说了\"已记录/已完成\"，但这一轮**没有任何命令** —— 数据不会变。请**立刻**"
                "输出 ```sh 命令块（先发命令再说话）；只有之前真的执行过命令，才可以回\"无需写入\"。")
    if "无需写入" in text:
        return ("[系统] 你说\"无需写入\"，但**本次请求到现在一条命令都没执行过**。如果用户"
                "这句话里有要记 / 要改的东西，请**立刻**输出 ```sh 命令块。")
    return None
