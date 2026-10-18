"""α 用例逐条测试（用户 35 条表，2026-10-18）。

把表里「原始提示词」**原样**喂给真实模型（不美化、不补充），记录三样东西：

1. 模型发出的命令（agent 回路里所有轮次，命令在**沙箱**执行）
2. 助手回复文本（用户实际看到的）
3. `inventory.json` / `daily_logs.json` 等文件的**前后 diff**

逐条**追加**写报告，中途失败可 `--from N` 续跑。用例之间**累积**（同一条对话流），
因为表里第 15/23/28 条明确引用前面的用例。

⚠ 密钥走应用自己的 `SettingsManager`，脚本不读取、不打印。
⚠ 数据全落在临时沙箱，**不碰 `data/`**。
⚠ 会发真实 API 请求（每条最多 5 轮）。

用法：
    .venv/Scripts/python.exe scripts/ai_alpha_probe.py [--from N] [--only N] [--out 路径]
"""

import argparse
import difflib
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.ai_service import AIService, AIWorker
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_OUT = ROOT / "dev-logs" / "2026-10-18-α测试记录.md"

# (编号, 原始提示词, 表里备注) —— 提示词**逐字**照抄，不修标点、不补主语
CASES: list[tuple[int, str, str]] = [
    (1, "现有牙膏1瓶，位于柜子1", "不说特征的物品在代码上怎么处理？"),
    (2, "牙刷放在柜子1", ""),
    (3, "黑色洗面奶位于柜子1 绿色洗面奶位于柜子2", ""),
    (4, "0.5的笔芯还有12根 0.4的还有4根 都在柜子2 任意一种剩2根时提醒我补货",
     "能否正确识别 or 而非 and"),
    (5, "湿巾还有1包多点 位于柜子4中间", "1 模糊数据能否处理 2 应该实现「位置的位置」"),
    (6, "褪黑素还有1瓶+大约15粒 不满的在床上 满的在桌面", "新位置能否正确处理"),
    (7, "垃圾袋还有约130只 估算大约还能用半年 位于柜子4中间", "能否识别出补货信息"),
    (8, "抽纸还剩五包 预估还能用一个月 记得提醒我补货", "同上"),
    (9, "扑克牌上次玩完忘整理了 记得提醒我整理并收纳至柜子4", "能否正确安排日程"),
    (10, "（assumption）我收拾完扑克牌了",
     "假设性情境，ai能否识别「有这个日程」，标记日程完成，同时操作物品到位置"),
    (11, "过敏药还剩2盒（2*12）+4粒 预计一天一粒 剩10粒提醒我买", ""),
    (12, "茶包还剩个大概20多包 在桌面上", "能否识别桌面=桌子=…等表述 而不是新建位置"),
    (13, "毛巾两条 一条蓝色一条黄色 在晾衣架上",
     "1 新位置的识别与建立 2 是否正确初始化提醒清洗的日程 3 日程界面拥挤，加功能区分学习/生活"),
    (14, "活页纸还有3包左右的A，4包B", "未说明是否补货默认按不补处理"),
    (15, "还有两瓶牙膏在衣柜1侧面",
     "1 名字一样且未说特征的已有物品、不同位置的处理 2「位置的位置」建议写为备注类"),
    (16, "鱼油就剩半瓶多了 下个月月初提醒我补买",
     "新功能：预算预估（分期付款/自动续费/要补货的东西/按前几个月预估日常支出）"),
    (17, "除螨仪在衣柜2", ""),
    (18, "抽纸输错了 还有8包 挪到了衣柜1", "冲突处理"),
    (19, "白色床单2条 在衣柜3 枕套1个 在衣柜3", ""),
    (20, "秋衣秋裤在衣柜2外面 天气冷了就提醒我换",
     "天气提醒换衣联动；这套衣服接下来不应当在柜子2，ai能否理解这个逻辑关系？"),
    (21, "蓝色床单1 位于衣柜3最里面", ""),
    (22, "我把衣柜3最里面的蓝色床单换来用了 记得提醒我洗之前的蓝色床单",
     "正确日程安排与位置处理；日程的连锁关系（洗衣服后1日收衣服并归位）"),
    (23, "（接上一条）换洗床单我收进衣柜3最里面了", "ai读取日程，应当知道「换洗床单」指的是蓝色的床单"),
    (24, "被罩在衣柜3外侧", "搜索应加模糊功能 比如外侧=外面=外边 但是衣柜=！柜子"),
    (25, "便签纸1叠 在桌子上", ""),
    (26, "再加1条蓝色床单，还是衣柜3最里面", "增加还是别的情况？有歧义 AI 应当询问"),
    (27, "6级书在柜子3", "简单案例"),
    (28, "另一件被罩在衣柜3 外侧 加上这个总共2件", "简单的逻辑计算判别"),
    (29, "花露水在柜子2", ""),
    (30, "（综合）我的柜子2现在有什么？柜子3有什么？", "简单常规问答"),
    (31, "我的智能手环在柜子4中间", ""),
    (32, "衣柜右2现有：灰白色 灰蓝色 灰黑色裤子各一条 白色长袖衬衫一件 黑色长袖衬衫一件 "
         "黑色毛衣一件 黑色加绒外套一件 灰色加绒外套一件 白色羽绒服一件", "大量数据的处理"),
    (33, "洗衣粉两袋 在衣柜左3外侧", ""),
    (34, "蓝色秋裤在衣柜4最里面", ""),
    (35, "我的右侧抽屉东西情况如下：iPhone手机盒里面装着原装数据线 保修卡；抽屉里有4根typec短线 "
         "一个翻译笔 一个绿色充电宝 一个黄色充电宝 一个hdmi-dp线 一个键盘防尘盖 2个u盘 "
         "鼠标充电线 3.5mm耳机孔的入耳式耳机（白色）、各种产品的说明书与保修卡 一个卷尺 "
         "一个小型洗衣机的电源线", "1 极大量数据的正确处理 2 物品间相对关系"),
]

SEED_LOCATIONS = ("衣柜左1,衣柜左2,衣柜左3,衣柜左4,衣柜右1,衣柜右2,"
                  "左侧抽屉,右侧抽屉,书架1,书架2,书架3,书架4,学校,家")

# 模型反问时补的**中性**一句：不给新信息（不暗示"新建"也不暗示"改已有"），只让它把活干完
NUDGE = "嗯，你先按我说的处理吧。"

# 只读命令：只发了这些就说明**这一轮什么都没写**（多半是在反问）→ 也补一句让它继续
READ_ONLY = {"lookup_item", "need_restock", "status"}


def _wrote_something(commands: list[str]) -> bool:
    """命令里有没有**写操作**（纯查询不算）。"""
    for cmd in commands:
        tail = cmd.split("actions.py", 1)[-1].strip().split()
        if tail and tail[0] not in READ_ONLY:
            return True
    return False


def _snapshot(root: Path) -> dict[str, str]:
    """把沙箱里所有 JSON 读成 `相对路径 -> 格式化文本`，用于前后 diff。

    ⚠ 跳过 `backup/` —— 那是 `reload_all` 顺手建的，会把 diff 淹掉。
    """
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*.json")):
        if "backup" in path.parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            out[str(path.relative_to(root))] = f"<读不了：{e}>"
            continue
        out[str(path.relative_to(root))] = json.dumps(data, ensure_ascii=False, indent=1)
    return out


def _diff(before: dict[str, str], after: dict[str, str]) -> str:
    """只列**变动**的文件（新增 / 修改），返回 Markdown 代码块；无变动返回空串。"""
    chunks: list[str] = []
    for name in sorted(set(before) | set(after)):
        old = before.get(name, "")
        new = after.get(name, "")
        if old == new:
            continue
        lines = difflib.unified_diff(old.splitlines(), new.splitlines(),
                                     fromfile=f"before/{name}", tofile=f"after/{name}",
                                     lineterm="", n=1)
        chunks.append("```diff\n" + "\n".join(lines) + "\n```")
    return "\n\n".join(chunks)


def _ask(svc, dm, settings, messages: list[dict]) -> tuple[str, list[str], str]:
    """跑一次应用真实的 agent 回路，返回 `(显示文本, 命令列表, 错误)`。"""
    model = settings.get("AI", "model", "deepseek-v4.1-flash")
    worker = AIWorker(svc._make_provider(), model, svc._build_system_prompt(),
                      messages, dm, settings)
    seen: list[tuple[str, object, object]] = []
    worker.finished.connect(lambda t, s=seen: s.append(("text", t, [])))
    worker.finished_with_instructions.connect(
        lambda t, i, s=seen: s.append(("instr", t, i)))
    worker.error.connect(lambda e, s=seen: s.append(("error", e, [])))
    worker.run()
    kind, payload, extra = seen[-1] if seen else ("error", "没有任何信号", [])
    if kind == "error":
        return "", [], str(payload)
    return str(payload), list(extra), ""


def _markdown(n: int, prompt: str, note: str, elapsed: float, error: str,
              commands: list[str], reply: str, change: str, follow: str) -> str:
    lines = [f"## 用例 {n}", "", f"**提示词**（原样）：{prompt}", ""]
    if note:
        lines += [f"**表里备注**：{note}", ""]
    lines += [f"**耗时**：{elapsed:.1f}s", ""]
    if error:
        lines += [f"**错误**：{error}", ""]
    if commands:
        lines += ["**模型命令**：", "```sh", *commands, "```", ""]
    else:
        lines += ["**模型命令**：无", ""]
    lines += ["**助手回复**：", "", reply.strip() or "（空）", ""]
    if follow:
        lines += ["**追问后**（我以用户身份补一句中性话，让流程继续、状态能累积）：", "",
                  follow, ""]
    lines += ["**文件变动**：", "", change or "（无变动）", ""]
    lines += ["**我的判定**：", "", "- [ ] 通过　- [ ] 有问题（处置：）", ""]
    return "\n".join(lines)


def _run_case(svc, dm, settings, n: int, prompt: str, note: str,
              history: list[dict]) -> tuple[str, str]:
    """跑一条用例，返回 `(Markdown 小节, 写进对话历史的助手回复)`。"""
    dm.reload_all()
    before = _snapshot(dm.data_dir)
    started = time.monotonic()
    reply, commands, error = _ask(svc, dm, settings,
                                  [*history, {"role": "user", "content": prompt}])
    elapsed = time.monotonic() - started
    follow = ""
    if not _wrote_something(commands) and not error and reply.strip():
        # 模型在**反问**（应用的 `_continuation_nudge` 故意不硬续跑 —— 那是给用户的提问）。
        # 用例判定看**第一轮**；这里补一句中性话让流程走完，好让后面用例有累积上下文。
        r2, c2, e2 = _ask(svc, dm, settings, [
            *history, {"role": "user", "content": prompt},
            {"role": "assistant", "content": reply},
            {"role": "user", "content": NUDGE}])
        follow = r2.strip() or (f"错误：{e2}" if e2 else "（空）")
        commands = c2
    dm.reload_all()
    section = _markdown(n, prompt, note, elapsed, error, commands, reply,
                        _diff(before, _snapshot(dm.data_dir)), follow)
    return section, reply + (f"\n\n（追问后）{follow}" if follow else "")



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", type=int, default=1, help="从第 N 条开始")
    parser.add_argument("--only", default="",
                        help="只跑第 N 条（可逗号分隔多个，如 2,3,5）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="报告路径")
    parser.add_argument("--tag", default="",
                        help="报告文件名后缀（**别在命令行写中文**，会被编码吃掉）")
    parser.add_argument("--real", action="store_true",
                        help="⚠ 直接写**真实 data/**（先自动备份；AI 命令真的落库）")
    parser.add_argument("--clear", action="store_true",
                        help="跑之前清空 inventory 的 items（配合 --real 用；位置清单保留）")
    args = parser.parse_args()

    settings = SettingsManager(DATA_DIR / "settings.ini")
    settings.load()
    sandbox = Path(tempfile.mkdtemp(prefix="ai_alpha_"))
    import scripts.actions_core as core

    if args.real:
        # ⚠ 真实模式：AI 命令**真的写进 data/** —— 先备份（`data/backup/` 不进仓库）
        import shutil

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = DATA_DIR / "backup" / f"alpha-real-{stamp}"
        backup.mkdir(parents=True, exist_ok=True)
        for name in ("inventory.json", "daily_logs.json"):
            if (DATA_DIR / name).exists():
                shutil.copy2(DATA_DIR / name, backup / name)
        core.DATA = DATA_DIR
        dm = DataManager(DATA_DIR)
        print(f"⚠ 真实模式：已备份 {backup}")
        if args.clear:
            inv = dm.inventory
            inv.data["items"] = []
            inv.save()
            print(f"⚠ 已清空 inventory items（位置清单保留 {len(inv.locations)} 个）")
    else:
        core.DATA = sandbox
        dm = DataManager(sandbox)
    svc = AIService(settings, dm)

    from scripts.actions import run_in_process

    if not args.real:
        run_in_process(f'set_locations --values "{SEED_LOCATIONS}"')

    only = {int(x) for x in str(args.only).split(",") if x.strip()}
    out = Path(args.out)
    if args.tag:
        out = out.with_name(f"{out.stem}-{args.tag}{out.suffix}")
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.start == 1 and not only:
        out.write_text(
            f"# α 用例逐条测试记录（{datetime.now():%Y-%m-%d %H:%M}）\n\n"
            f"- 表：`D:\\360MoveData\\Users\\ASUS\\OneDrive\\Desktop\\新建 XLSX 工作表.xlsx`\n"
            f"- 模型：`{settings.get('AI', 'model', '?')}`"
            f"（provider=`{settings.get('AI', 'provider', '?')}`）\n"
            f"- 方式：提示词**原样**喂入；用例之间**累积**同一条对话；命令在沙箱执行\n"
            f"- 沙箱：`{sandbox}`（**未碰真实 `data/`**）\n\n"
            "> 判定列留空，由我看过回复与 diff 后逐条填。\n\n---\n\n",
            encoding="utf-8")

    history: list[dict] = []
    todo = [c for c in CASES if (c[0] in only if only else c[0] >= args.start)]
    print(f"沙箱：{sandbox}\n模型：{settings.get('AI', 'model', '?')}\n待跑 {len(todo)} 条")

    for n, prompt, note in todo:
        print(f"\n── [{n}] {prompt[:60]}", flush=True)
        section, reply = _run_case(svc, dm, settings, n, prompt, note, history)
        history += [{"role": "user", "content": prompt},
                    {"role": "assistant", "content": reply}]
        with out.open("a", encoding="utf-8") as f:
            f.write(section + "\n---\n\n")
        print(f"   已写入报告（回复 {len(reply)} 字）", flush=True)

    print(f"\n报告：{out}")


if __name__ == "__main__":
    main()
