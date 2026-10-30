"""「收入 / 固定支出 / 预计支出」命令（A4，2026-10-31）。

从 `scripts/actions.py` 分出（那里 759 行，加不动）。两条命令：

- `finance_set`：写**用户给的**初始值（总余额 / 月收入 / 固定支出）；
- `finance_summary`：读 `services/finance.summary()` 的结果打印出来 ——
  **AI 只能读这个，不许自己算数** ✗（用户 2026-10-31 口径）。
"""

from scripts.actions_core import (
    ActionError,
    _money,
    load,
    now_iso,
    save,
)
from src.models.expense import FINANCE_FIELDS


def cmd_finance_set(args) -> None:
    """设置初始值。只写显式传入的那几项（其余保持原样）。"""
    data = load("expenses.json")
    finance = data.setdefault("finance", {})
    changed: list[str] = []
    for field in FINANCE_FIELDS:
        raw = getattr(args, field, None)
        if raw is None:
            continue
        finance[field] = _money(raw, field)
        changed.append(field)
    if not changed:
        raise ActionError("finance_set 至少要给一个：--balance / --income / --fixed")
    finance["updated_at"] = now_iso()
    save("expenses.json", data)
    print("OK finance_set | " + "、".join(
        f"{name}={finance[name]:.2f}" for name in changed))


def cmd_finance_summary(args) -> None:
    """本月汇总：已花 / 预计 / 收入 / 固定支出 / 结余 / 余额 + 依据。**

    ⚠ 数字**全部来自** `services/finance.summary()`（代码算好）；模型只负责转述。
    """
    from src.services.finance import summary

    data = load("expenses.json")
    result = summary(data.get("records") or [], data.get("finance") or {})
    basis = (f"过去 {result['basis_months']} 个月中位数"
             if result["basis_months"] else "本月已花（历史不足一个月）")
    print(f"本月已花 ¥{result['spent']:.2f}")
    print(f"预计本月支出 ¥{result['projected']:.2f}（依据：{basis}）")
    print(f"月收入 ¥{result['income']:.2f} · 固定支出 ¥{result['fixed']:.2f}")
    print(f"本月结余 ¥{result['left']:.2f} · 总余额 ¥{result['balance']:.2f}")
