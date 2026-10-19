"""AI 助手**评估集**（专项审查 §5）：场景 × 重复采样 k 次。

为什么需要：审查 §5 要求"**同一请求重复采样**，比较目标满足率、错误成功汇报率、
返工成功率、重复副作用率、延迟和成本" —— **一次成功说明不了可靠性**（P06 的 pass^k 精神）。

判据**看最终数据状态**，不看模型说了什么 ✓（与 τ-bench 一致）；
"模型说做完了、状态却没变"正是**错误成功汇报**，单独统计 ✓。

⚠ 需要真实 key 与时间（k × 场景数 次真实调用），**不进 CI**。
    .venv\\Scripts\\python.exe scripts/ai_eval.py --k 4 --endpoint <url> --key-file <file>

诚实边界：3 个场景（响应丢失 / 并发冲突 / 工具不可用）需要**故障注入**，
本轮未纳入 ✗；`成本` 未采集（provider 不回传用量）✗。
"""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.ai_service import AIService, AIWorker
from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager

SEED_LOCATIONS = "学校,家,桌面,书架3,衣柜左1,床头柜,卫生间柜子,宿舍抽屉"
ROOT = Path(__file__).resolve().parent.parent


# ── 场景 ────────────────────────────────────────────────────
# 每个场景：id / 说明 / 播种函数（改沙箱初始状态）/ 提示词 / 目标检查（看最终状态）

def _seed_plain(dm: DataManager) -> None:
    """默认沙箱：两件消耗品 + 一条计划。"""


SCENARIOS = [
    dict(n=1, title="只说已记录、没有动作",
         seed=lambda dm: None,
         prompt="记一下：牙膏 1 瓶，放卫生间柜子",
         goals=[("物品被真的建出来", lambda dm: any(
             "牙膏" in str(it.get("name", "")) for it in dm.inventory.items))]),
    dict(n=2, title="三个目标只完成一个",
         seed=lambda dm: None,
         prompt="记三件事：抽纸 2 包放书架3；洗衣液 1 瓶放卫生间柜子；袜子 3 双放衣柜左1",
         goals=[("抽纸", lambda dm: _has(dm, "抽纸")),
                ("洗衣液", lambda dm: _has(dm, "洗衣液")),
                ("袜子", lambda dm: _has(dm, "袜子"))]),
    dict(n=3, title="一条成功、一条参数错",
         seed=lambda dm: None,
         prompt=("记两件事：矿泉水 6 瓶放书架3；再记一条数量是负数的测试品 "
                 "（如果你判断这条不合法就别记）"),
         goals=[("矿泉水被记下", lambda dm: _has(dm, "矿泉水")),
                ("没有建出负数数量的条目", lambda dm: all(
                    int(it.get("quantity", 0)) >= 0 for it in dm.inventory.items))]),
    dict(n=6, title="目标原本已经满足",
         seed=lambda dm: dm.inventory.add_item({"name": "洗面奶", "quantity": 2,
                                                "location": "桌面"}),
         prompt="把洗面奶放到桌面",
         goals=[("位置是桌面", lambda dm: _location_of(dm, "洗面奶") == "桌面"),
                ("没有多出一条洗面奶", lambda dm: _count(dm, "洗面奶") == 1)]),
    dict(n=7, title="修改位置：身份保持、条目不增",
         seed=lambda dm: dm.inventory.add_item({"name": "羽绒服", "quantity": 1,
                                                "location": "衣柜左1"}),
         prompt="把羽绒服寄回家（位置改成家）",
         goals=[("位置是家", lambda dm: _location_of(dm, "羽绒服") == "家"),
                ("条目数没变", lambda dm: _count(dm, "羽绒服") == 1)]),
    dict(n=8, title="24 片扣 1 片",
         seed=lambda dm: dm.inventory.add_item({"name": "布洛芬", "quantity": 1, "unit": "盒",
                                                "doses_per_unit": 24, "min_doses": 5,
                                                "location": "床头柜"}),
         prompt="我吃了一片布洛芬",
         goals=[("余量正好 23 片", lambda dm: _remaining(dm, "布洛芬") == 23),
                ("没有多建一条布洛芬", lambda dm: _count(dm, "布洛芬") == 1)]),
    dict(n=9, title="长请求 / 大量条目",
         seed=lambda dm: None,
         prompt=("帮我记五件东西：抽纸 2 包放书架3；洗衣液 1 瓶放卫生间柜子；"
                 "袜子 3 双放衣柜左1；耳机 1 副放桌面；雨伞 1 把放宿舍抽屉。"
                 "每个都按我给的写，别漏。"),
         goals=[("抽纸", lambda dm: _has(dm, "抽纸")),
                ("洗衣液", lambda dm: _has(dm, "洗衣液")),
                ("袜子", lambda dm: _has(dm, "袜子")),
                ("耳机", lambda dm: _has(dm, "耳机")),
                ("雨伞", lambda dm: _has(dm, "雨伞"))]),
]


def _has(dm: DataManager, name: str) -> bool:
    return any(name in str(it.get("name", "")) for it in dm.inventory.items)


def _count(dm: DataManager, name: str) -> int:
    return sum(1 for it in dm.inventory.items if name in str(it.get("name", "")))


def _location_of(dm: DataManager, name: str) -> str:
    for it in dm.inventory.items:
        if name in str(it.get("name", "")):
            return str(it.get("location") or "")
    return ""


def _remaining(dm: DataManager, name: str) -> int | None:
    from src.models.inventory import InventoryModel

    for it in dm.inventory.items:
        if name in str(it.get("name", "")):
            return InventoryModel.remaining_doses(it)
    return None


# ── 跑一次 ──────────────────────────────────────────────────

def _run_once(scenario: dict, settings: SettingsManager, k_index: int) -> dict:
    """一个场景跑一次：**全新沙箱** + 真实模型 + 看最终状态。"""
    import scripts.actions_core as core
    from scripts.actions import run_in_process
    from src.services.ai_loop_guards import _claims_done

    sandbox = Path(tempfile.mkdtemp(prefix="ai_eval_"))
    core.DATA = sandbox
    dm = DataManager(sandbox)
    run_in_process(f'set_locations --values "{SEED_LOCATIONS}"')
    dm.reload_all()          # ⚠ `set_locations` 是**直接写文件**的 → 内存副本会变旧，
    scenario["seed"](dm)     #   不重载的话下一步 save 会被冲突检测拒掉（实测踩到）
    dm.inventory.save()
    dm.daily_logs.save()

    svc = AIService(settings, dm)
    model = settings.get("AI", "model", "deepseek-v4.1-flash")
    worker = AIWorker(svc._make_provider(), model, svc._build_system_prompt(),
                      [{"role": "user", "content": scenario["prompt"]}], dm, settings)
    seen: list[tuple[str, object, object]] = []
    ledger_lines: list[str] = []
    worker.finished.connect(lambda t, s=seen: s.append(("text", t, [])))
    worker.finished_with_instructions.connect(lambda t, i, s=seen: s.append(("instr", t, i)))
    worker.error.connect(lambda e, s=seen: s.append(("error", e, [])))
    worker.ledger_ready.connect(ledger_lines.append)

    started = time.monotonic()
    try:
        worker.run()
    except Exception as e:  # noqa: BLE001
        return {"k": k_index, "error": str(e), "elapsed": time.monotonic() - started}
    elapsed = time.monotonic() - started

    kind, payload, extra = seen[-1] if seen else ("error", "没有任何信号", [])
    text = "" if kind == "error" else str(payload)
    results = [check(dm) for _name, check in scenario["goals"]]
    ledger = " ".join(ledger_lines)
    return {
        "k": k_index,
        "error": str(payload) if kind == "error" else "",
        "elapsed": round(elapsed, 1),
        "commands": list(extra),
        "reply": text,
        "goals": [name for name, _ in scenario["goals"]],
        "satisfied": results,
        "met": sum(1 for r in results if r),
        "total": len(results),
        "claimed_done": bool(_claims_done(text)),
        "ledger": ledger,
        "reworked": ("没达到预期" in ledger and "验收通过" in ledger),
        "double_effect": _double_effect(scenario, dm),
    }


def _double_effect(scenario: dict, dm: DataManager) -> bool:
    """重复副作用：**同一条效果做了两遍**（例如扣两次片）。

    只看最终状态 ✓ —— 场景自己知道"正确值是多少"，多了就是重复 ✗。
    """
    if scenario["n"] == 8:
        return _remaining(dm, "布洛芬") not in (23, None) and _remaining(dm, "布洛芬") != 24
    return False


# ── 主流程 ──────────────────────────────────────────────────

def _rate(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def _counts(runs: list[dict]) -> dict:
    """把逐次结果折成计数 —— **一个循环**数完（别写一堆推导式堆复杂度）。"""
    out = {"ok": [], "failed": 0, "goals": 0, "total": 0, "wrong": 0,
           "reworked": 0, "doubled": 0, "latency": 0.0}
    for run in runs:
        if run.get("error"):
            out["failed"] += 1
            continue
        out["ok"].append(run)
        out["goals"] += run["met"]
        out["total"] += run["total"]
        out["latency"] += run["elapsed"]
        out["wrong"] += 1 if (run["claimed_done"] and run["met"] < run["total"]) else 0
        out["reworked"] += 1 if run["reworked"] else 0
        out["doubled"] += 1 if run["double_effect"] else 0
    return out


def _aggregate(runs: list[dict]) -> dict:
    c = _counts(runs)
    n = len(c["ok"])
    return {
        "runs": len(runs),
        "failed_runs": c["failed"],
        "goal_rate": _rate(c["goals"], c["total"]),
        "wrong_claim_rate": _rate(c["wrong"], n),
        "rework_runs": c["reworked"],
        "rework_success_rate": _rate(c["reworked"], n),
        "double_effect_rate": _rate(c["doubled"], n),
        "mean_latency_s": round(c["latency"] / n, 1) if n else 0.0,
        "cost": "未采集（provider 不回传用量）",
    }


def _configure(settings: SettingsManager, args) -> bool:
    """按命令行覆盖 endpoint / model / key；返回是否已配好 key。"""
    if args.endpoint:
        settings.set("AI", "base_url", args.endpoint)
    if args.model_override:
        settings.set("AI", "model", args.model_override)
    if args.key_file:
        settings.set("AI", "api_key", Path(args.key_file).read_text(encoding="utf-8").strip())
    return bool(settings.api_key)


def _run_all(scenarios: list, settings: SettingsManager, k: int) -> list[dict]:
    """逐场景 × k 次；每跑完一次就打印一行（长跑时能看出进度）。"""
    runs: list[dict] = []
    for scenario in scenarios:
        for k_index in range(1, k + 1):
            run = _run_once(scenario, settings, k_index)
            run["scenario"] = scenario["n"]
            run["title"] = scenario["title"]
            runs.append(run)
            print(f"  [{scenario['n']}.{k_index}] 达成 {run.get('met', '?')}/"
                  f"{run.get('total', '?')} · {run.get('elapsed', '?')}s", flush=True)
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=4, help="每个场景采样几次（默认 4）")
    parser.add_argument("--only", default="", help="只跑第 N 个场景（逗号分隔）")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--model-override", default="")
    parser.add_argument("--key-file", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    settings = SettingsManager(ROOT / "data" / "settings.ini")
    settings.load()
    if not _configure(settings, args):
        print("没有 API key：用 --key-file 或先在设置里配好")
        raise SystemExit(2)

    wanted = {int(x) for x in args.only.split(",") if x.strip()} if args.only else None
    scenarios = [s for s in SCENARIOS if wanted is None or s["n"] in wanted]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) if args.out else ROOT / "dev-logs" / f"ai-eval-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"模型 {settings.get('AI', 'model', '')} | k={args.k} | 场景 {len(scenarios)} 个")
    print(f"输出 {out_dir}")

    all_runs = _run_all(scenarios, settings, args.k)
    report = {"model": settings.get("AI", "model", ""), "k": args.k,
              "when": stamp, "runs": all_runs, "summary": _aggregate(all_runs)}
    (out_dir / "runs.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(_markdown(report), encoding="utf-8")
    print("\n== 汇总 ==")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")


def _markdown(report: dict) -> str:
    lines = [f"# AI 评估集（模型 {report['model']}，k={report['k']}）", "",
             f"时间：{report['when']}", "", "## 汇总", ""]
    lines += [f"- {k}：{v}" for k, v in report["summary"].items()]
    lines += ["", "## 逐次结果", ""]
    for run in report["runs"]:
        marks = "".join("O" if s else "X" for s in run.get("satisfied", []))
        lines += [f"### 场景 {run['scenario']} · 第 {run['k']} 次 — {run['title']}",
                  f"- 目标 {marks}（{run.get('met', '?')}/{run.get('total', '?')}）"
                  f" · {run.get('elapsed', '?')}s · 声称完成={run.get('claimed_done')}",
                  f"- 账本：{run.get('ledger') or '（无）'}",
                  "", "```text", (run.get("reply") or run.get("error") or "")[:800], "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
