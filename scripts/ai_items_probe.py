"""「有什么」AI 提示词端到端探针（P18 第 3 步）。

跑**真实模型**：系统提示词 → 日常口语 → 模型输出的 `actions.py` 命令 → 在**沙箱**里执行
→ 打印「模型发出的命令」+「库存现状」+「关键事实是否达标」。

用途：在**清空重建真实库存之前**，确认提示词能表达你要的四个维度
（份数 / 同类物品不同特征 / 位置 / 提醒补货）以及两个边界（不存在的东西 / 模糊表述）。

⚠ 密钥**不由本脚本读取或打印**：走应用自己的 `SettingsManager`，key 只活在运行时内存里。
⚠ 数据全部落在临时目录（沙箱），**不碰 `data/`**。
⚠ 单次通过 ≠ 稳定（模型有随机性）→ 关键样例可 `--repeat 2` 再跑一遍。

用法：
    .venv/Scripts/python.exe scripts/ai_items_probe.py [--repeat N] [--only N]
"""

import argparse
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.ai_service import AIService, AIWorker
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _one(items: list[dict], name: str) -> dict | None:
    return next((it for it in items if name in str(it.get("name", ""))), None)


def _has(items: list[dict], name: str, **want: object) -> tuple[bool, str]:
    """关键事实检查：`quantity` / `unit` / `status` / `instances`（条数）/ `location_has`。"""
    it = _one(items, name)
    if it is None:
        return False, f"没找到「{name}」"
    bad = []
    for key, expect in want.items():
        if key == "instances":
            got = len(it.get("instances") or [])
        elif key == "location_has":
            got = str(it.get("location", ""))
            if expect not in got:
                bad.append(f"位置={got!r} 不含 {expect!r}")
            continue
        else:
            got = it.get(key)
        if got != expect:
            bad.append(f"{key}={got!r}（期望 {expect!r}）")
    return (not bad), "；".join(bad)


def _unchanged(seed: list[dict]) -> Callable[[list[dict]], tuple[bool, str]]:
    """边界样例的检查：**不许新增任何物品**（该反问 / 该拒绝，不该瞎写）。"""
    def check(items: list[dict]) -> tuple[bool, str]:
        if len(items) != len(seed):
            names = [it.get("name") for it in items]
            return False, f"不该写却写了：{names}"
        return True, ""
    return check


SAMPLES: list[tuple[str, str, list[dict], object]] = [
    ("份数+位置", "家里抽纸还有 3 提，放在阳台储物柜", [],
     lambda it: _has(it, "抽纸", quantity=3, unit="提", location_has="阳台")),
    ("份数+补货", "布洛芬 1 盒 24 片，放药箱；剩不到 5 片就提醒我买", [],
     lambda it: _has(it, "布洛芬", quantity=1, unit="盒", location_has="药箱",
                     min_doses=5)),          # 片级下限（不是 `--min_qty 5` = 5 盒）
    ("同类不同特征+位置", "两条充电线，一条 Type-C 一条 Lightning，都在书房抽屉", [],
     lambda it: _has(it, "充电线", quantity=2, instances=2)),
    ("补货（新物品）", "猫粮快吃完了，这周内要买", [],
     lambda it: _has(it, "猫粮")),
    ("补货查询", "还有什么要买的？",
     [{"name": "洗衣液", "quantity": 0, "min_quantity": 1, "unit": "瓶"}],
     _unchanged([{"name": "洗衣液"}])),
    ("位置（移动已有物品）", "创可贴挪到车上急救包",
     [{"name": "创可贴", "quantity": 2, "min_quantity": 1, "unit": "盒",
       "location": "药箱"}],
     lambda it: _has(it, "创可贴", location_has="车")),
    ("份数（消耗）", "洗手液用掉一瓶",
     [{"name": "洗手液", "quantity": 2, "min_quantity": 1, "unit": "瓶"}],
     lambda it: _has(it, "洗手液", quantity=1)),
    ("同类不同位置", "纸巾：客厅 2 包、储物间 6 包", [],
     lambda it: _has(it, "纸巾")),
    ("查找·按位置", "书架3 上都放了什么？",
     [{"name": "纸巾", "quantity": 2, "min_quantity": 1, "unit": "包",
       "location": "书架3"}],
     _unchanged([{"name": "纸巾"}])),
    ("查找·按分类", "我有哪些虚拟会员？",
     [{"name": "QQ音乐会员", "quantity": 1, "min_quantity": 1, "unit": "个",
       "category": "虚拟品类"}],
     _unchanged([{"name": "QQ音乐会员"}])),
    ("查找·需补货", "哪些东西该补货了？",
     [{"name": "牙膏", "quantity": 0, "min_quantity": 1, "unit": "支"}],
     _unchanged([{"name": "牙膏"}])),
    ("位置·清单外新增", "把抹布放在厨房水槽下面", [],
     lambda it: _has(it, "抹布", location_has="厨房")),
    ("边界·不存在的东西", "把不存在的东西挪到车库", [], _unchanged([])),
    ("边界·模糊表述", "衣柜里那几件夏天 T 恤挪到收纳箱", [], _unchanged([])),
]


def _print_inventory(items: list[dict]) -> None:
    for it in items:
        extra = f" instances={len(it['instances'])}" if it.get("instances") else ""
        print(f"  {it.get('name')} × {it.get('quantity')}{it.get('unit', '')}"
              f" @{it.get('location') or '—'} [{it.get('status')}]{extra}")


CONFIRM = "对，继续。"                    # 两步流程第二步（**中性**：不暗示"新建"）
CONFIRM_CREATE = "对，库存里没有，就新建一条。"   # 只给"确实要新建"的样例用

# 这些样例**确实要新建**物品 → 确认时可以说"没有就新建"；
# 其余（移动 / 查询 / 边界）用中性确认，否则会把"该反问"的样例诱导成乱写 ✗
CREATE_LABELS = {
    "份数+位置", "份数+补货", "同类不同特征+位置", "补货（新物品）",
    "同类不同位置", "位置·清单外新增",
}


def _ask_turns(svc, dm, settings, text: str, confirm: str = CONFIRM) -> tuple[str, object]:
    """跑最多三轮：模型可能先查、再确认、才写（提示词规定的两步流程）。

    返回最后一轮的 `(类型, 载荷)`：`instr`（有命令）/ `text`（只说话）/ `error`。
    """
    model = settings.get("AI", "model", "deepseek-v4.1-flash")
    history: list[dict] = []
    kind, payload = "", ""
    for turn in (1, 2, 3):
        worker = AIWorker(svc._make_provider(), model, svc._build_system_prompt(),
                          [*history, {"role": "user", "content": text}], dm, settings)
        seen: list[tuple[str, object]] = []
        worker.finished_with_instructions.connect(
            lambda t, i, s=seen: s.append(("instr", i)))
        worker.finished.connect(lambda t, s=seen: s.append(("text", t)))
        worker.error.connect(lambda e, s=seen: s.append(("error", e)))
        worker.run()
        kind, payload = seen[-1] if seen else ("?", "")
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": str(payload)[:2000]})
        if kind != "text":
            break                              # 有命令（或出错）→ 不用再确认
        if turn == 1:
            text = confirm                     # 模型在等确认 → 替用户确认一次
        elif turn == 2:
            text = CONFIRM_CREATE              # 它还在问（多半是"要不要新建"）→ 明确一下
    return kind, payload


def _run_one(svc, dm, settings, index: int, label: str, text: str,
             seed: list[dict], check) -> bool:
    # 每个样例**清空**再放种子：否则后面的"不该写"断言会拿空种子比，产生假失败
    dm.reload_all()
    dm.inventory.data["items"] = []
    for item in seed:
        dm.inventory.add_item(dict(item))
    dm.inventory.save()

    kind, payload = _ask_turns(
        svc, dm, settings, text,
        CONFIRM_CREATE if label in CREATE_LABELS else CONFIRM)

    print(f"\n── [{index}/{len(SAMPLES)}] {label} ──────────────────────────")
    print(f"你说：{text}")
    if kind == "error":
        print(f"❌ 模型/执行出错：{payload}")
        return False
    if kind == "text":
        print(f"（两轮都没有可执行命令）模型回复：{str(payload)[:200]}")
    else:
        print("模型命令：")
        for cmd in payload:
            print(f"  {cmd}")

    dm.reload_all()
    print("库存：")
    _print_inventory(dm.inventory.items)

    ok, why = check(dm.inventory.items)
    print(f"{'✅ 达标' if ok else '⚠️ 未达标'}：{why or '关键事实一致'}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=1, help="每个样例跑几次（看稳定性）")
    parser.add_argument("--only", type=int, default=0, help="只跑第 N 个样例（1 起）")
    args = parser.parse_args()

    settings = SettingsManager(DATA_DIR / "settings.ini")
    settings.load()
    sandbox = Path(tempfile.mkdtemp(prefix="ai_items_probe_"))
    import scripts.actions_core as core

    core.DATA = sandbox                       # AI 的命令写进沙箱（不碰真实数据）
    dm = DataManager(sandbox)
    svc = AIService(settings, dm)

    # 沙箱也装上那 12 个固定位置 —— 让探针跑在**和真实环境一样的配置**下
    from scripts.actions import run_in_process

    print("位置清单:", run_in_process(
        'set_locations --values "衣柜左1,衣柜左2,衣柜左3,衣柜左4,衣柜右1,衣柜右2,'
        '左侧抽屉,右侧抽屉,书架1,书架2,书架3,书架4"'))

    print(f"沙箱：{sandbox}")
    print(f"模型：{settings.get('AI', 'model', '?')}"
          f"（provider={settings.get('AI', 'provider', '?')}）")

    passed = 0
    total = 0
    for _round in range(args.repeat):
        for i, (label, text, seed, check) in enumerate(SAMPLES, start=1):
            if args.only and i != args.only:
                continue
            total += 1
            passed += bool(_run_one(svc, dm, settings, i, label, text, seed, check))

    print(f"\n══ 达标 {passed}/{total} ══")


if __name__ == "__main__":
    main()
