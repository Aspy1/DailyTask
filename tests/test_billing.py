"""月付 / 分期（A1，用户 2026-10-31 口径）。

三条硬口径：
1. **只填「每月几号」** —— 不做"每笔单独日期"；
2. **只填不算** —— 不算手续费/利息，期数 × 每期金额就是全部；
3. 到期由**代码**记一笔支出（分类「订阅/分期」）+ 邮件；**AI 只解释，不改数**。
"""

from datetime import date

from src.models.billing import (
    BILLING_CATEGORY_ID,
    apply_charge,
    charge_note,
    due_today,
    installments_of,
    is_active,
    remaining,
)
from src.models.course import schedule_date
from src.services import reminder_service as rs
from src.services.data_manager import DataManager


def _monthly(due_day: int = 5, **extra: object) -> dict:
    return {"id": "i_001", "name": "网盘会员", "billing_type": "monthly",
            "amount": 15.0, "due_day": due_day, "installments": 0,
            "paid_count": 0, "billing_active": True, **extra}


def _installment(total: int = 6, paid: int = 0, due_day: int = 10) -> dict:
    return {"id": "i_002", "name": "耳机", "billing_type": "installment",
            "amount": 100.0, "due_day": due_day, "installments": total,
            "paid_count": paid, "billing_active": True}


# ── 规则 ────────────────────────────────────────────────────

def test_due_exactly_on_the_day() -> None:
    item = _monthly(due_day=5)
    assert due_today(item, date(2026, 11, 5)) is True
    assert due_today(item, date(2026, 11, 4)) is False


def test_catch_up_if_missed_the_day() -> None:
    """那天没开机 → 之后打开补扣一次（同月只一次），不然就漏记一笔钱。"""
    item = _monthly(due_day=5)
    assert due_today(item, date(2026, 11, 20)) is True


def test_only_once_per_month() -> None:
    item = _monthly(due_day=5)
    apply_charge(item, date(2026, 11, 5))
    assert due_today(item, date(2026, 11, 6)) is False
    assert due_today(item, date(2026, 12, 5)) is True


def test_due_day_31_is_clamped_to_month_end() -> None:
    """31 号填的账单在 2 月要落到月末，否则那些月份永远不扣。"""
    item = _monthly(due_day=31, last_charged_on="2026-01-31")
    assert due_today(item, date(2026, 2, 28)) is True


def test_installment_stops_after_last_charge() -> None:
    item = _installment(total=6, paid=5, due_day=10)
    assert is_active(item) is True
    apply_charge(item, date(2026, 11, 10))
    assert item["billing_active"] is False, "扣完 6 期要自动停用"
    assert due_today(item, date(2026, 12, 10)) is False
    assert remaining(item) == 0
    assert item["id"] == "i_002", "停用但**保留**，还能回查"


def test_monthly_has_no_end() -> None:
    item = _monthly()
    assert installments_of(item) is None
    assert remaining(item) is None
    apply_charge(item, date(2026, 11, 5))
    assert is_active(item) is True


def test_inactive_item_never_charges() -> None:
    assert due_today(_monthly(billing_active=False), date(2026, 11, 5)) is False


def test_missing_due_day_never_charges() -> None:
    """没填几号 → **不猜**、不乱扣钱。"""
    assert due_today(_monthly(due_day=0), date(2026, 11, 5)) is False


def test_charge_note_mentions_installment_number() -> None:
    assert charge_note("耳机", 2, 6) == "耳机（第 2/6 期）"
    assert charge_note("网盘", 3, None) == "网盘（月付）"


# ── 服务层：真的记一笔支出 + 发邮件 ─────────────────────────

class _FakeNotify:
    """只替代 `_notify`，数据用**真实** DataManager（写在 tmp_path）。"""

    def __init__(self, dm: DataManager) -> None:
        self._dm = dm
        self.sent: list[dict] = []

    def _notify(self, title: str, body: str, **kw: object) -> None:
        self.sent.append({"title": title, "body": body, **kw})


def _due_today_item(iid: str, **extra: object) -> dict:
    today = schedule_date()
    return {"id": iid, "name": "网盘会员", "category": "订阅",
            "billing_type": "monthly", "amount": 15.0, "due_day": today.day,
            "installments": 0, "paid_count": 0, "billing_active": True, **extra}


def test_service_records_expense_and_emails(tmp_path, qapp) -> None:
    dm = DataManager(tmp_path)
    dm.inventory.add_item(_due_today_item("i_001"))
    fake = _FakeNotify(dm)

    rs._billing_charges_notify(fake)

    assert len(dm.expenses.records) == 1
    record = dm.expenses.records[0]
    assert record["amount"] == 15.0
    assert record["category"] == BILLING_CATEGORY_ID
    assert "月付" in record["note"]
    assert fake.sent and fake.sent[0]["email"] is True, "到期要发提醒邮件"
    assert dm.inventory.items[0]["paid_count"] == 1


def test_service_is_idempotent_within_the_month(tmp_path, qapp) -> None:
    dm = DataManager(tmp_path)
    dm.inventory.add_item(_due_today_item("i_001"))
    fake = _FakeNotify(dm)

    rs._billing_charges_notify(fake)
    rs._billing_charges_notify(fake)

    assert len(dm.expenses.records) == 1, "同一个月不能扣两次"
    assert len(fake.sent) == 1


def test_installment_finishes_and_stops_charging(tmp_path, qapp) -> None:
    dm = DataManager(tmp_path)
    dm.inventory.add_item(_due_today_item(
        "i_002", name="耳机", billing_type="installment", amount=100.0,
        installments=1, paid_count=0))
    fake = _FakeNotify(dm)

    rs._billing_charges_notify(fake)
    assert dm.inventory.items[0]["billing_active"] is False
    assert dm.expenses.records[0]["amount"] == 100.0

    rs._billing_charges_notify(fake)
    assert len(dm.expenses.records) == 1, "停用后不该再扣"


def test_old_category_name_is_renamed_on_load(tmp_path) -> None:
    """2026-10-31：虚拟品类正式叫「订阅」，老数据读进来就地改名。"""
    dm = DataManager(tmp_path)
    dm.inventory.add_item({"name": "网易云会员", "category": "虚拟品类"})
    dm.inventory.save()

    again = DataManager(tmp_path)
    assert "订阅" in again.inventory.categories
    assert "虚拟品类" not in again.inventory.categories
    assert again.inventory.items[0]["category"] == "订阅"


# ── AI 走同一条命令接口（用户口径：能自动就自动、和 AI 同一接口）──────

def test_cli_add_item_with_billing(sandbox) -> None:
    from helpers import read_json, run

    run('python scripts/actions.py add_item --name "网盘会员" '
        '--billing-type monthly --amount 15 --due-day 5')
    it = read_json(sandbox, "inventory.json")["items"][0]
    assert it["billing_type"] == "monthly"
    assert it["amount"] == 15.0
    assert it["due_day"] == 5
    assert it["billing_active"] is True
    assert it["category"] == "订阅", "账单自动归到「订阅」品类"


def test_cli_can_stop_billing(sandbox) -> None:
    from helpers import read_json, run

    run('python scripts/actions.py add_item --name "耳机" --billing-type installment '
        '--amount 100 --due-day 10 --installments 6')
    run('python scripts/actions.py update_item --id i_001 --billing-type none')
    it = read_json(sandbox, "inventory.json")["items"][0]
    assert "billing_type" not in it and "installments" not in it


def test_cli_rejects_bad_due_day(sandbox) -> None:
    """几号必须是 1-31 —— 非法值不写任何文件（A1 的钱不能乱扣）。"""
    from helpers import read_json, run

    out = run('python scripts/actions.py add_item --name "乱填" --due-day 99')
    assert "ERROR" in out
    assert "items" not in read_json(sandbox, "inventory.json")


def test_card_text_shows_installment_progress() -> None:
    from src.ui.panels.inventory_text import billing_text

    item = {"billing_type": "installment", "amount": 100.0, "due_day": 10,
            "installments": 6, "paid_count": 2, "billing_active": True}
    text = billing_text(item)
    assert "100" in text and "6 期" in text and "剩 4 期" in text


def test_card_text_for_monthly_and_finished() -> None:
    from src.ui.panels.inventory_text import billing_text

    monthly = {"billing_type": "monthly", "amount": 15.0, "due_day": 5,
               "installments": 0, "billing_active": True}
    assert "15" in billing_text(monthly) and "5 号" in billing_text(monthly)

    done = {"billing_type": "installment", "amount": 100.0, "due_day": 10,
            "installments": 6, "paid_count": 6, "billing_active": False}
    assert "扣完" in billing_text(done)
    assert billing_text({"name": "纸巾"}) == "", "不是账单的卡片不该多一行"
