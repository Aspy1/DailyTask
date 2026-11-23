"""补货提醒（P18 第 2 步）：有"需购/不足"的物品 → **每天最多提醒一次**。

`InventoryModel.need_restock()` 早就有了，但**没有任何出口** —— 面板里看得到状态，
却不会推送。这里钉住三件事：有则提醒、每天一次、没缺货就不打扰。
"""

from datetime import date, timedelta

import pytest


@pytest.fixture
def env(tmp_path, qapp) -> tuple:
    """沙箱 DataManager + 记录型 ReminderService（不连 SMTP / 托盘）。"""
    from src.services.data_manager import DataManager
    from src.services.reminder_service import ReminderService
    from src.services.settings_manager import SettingsManager

    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    dm = DataManager(tmp_path)
    rem = ReminderService(settings, dm)
    mails: list[tuple[str, str]] = []
    trays: list[tuple[str, str]] = []
    rem._send_email = lambda subject, body: mails.append((subject, body))
    rem.reminder_notify.connect(lambda title, body: trays.append((title, body)))
    return dm, rem, mails, trays


def _add(dm, name: str, qty: int, min_qty: int = 1, unit: str = "件") -> None:
    dm.inventory.add_item({"name": name, "quantity": qty, "min_quantity": min_qty,
                           "unit": unit})
    dm.inventory.save()


def test_restock_notifies_once_a_day(env) -> None:
    dm, rem, mails, trays = env
    _add(dm, "纸巾", 0, unit="包")               # 用完 → 需购

    rem._check_restock()

    assert mails and mails[0][0] == "续费 / 补买提醒"
    assert "纸巾" in mails[0][1]
    assert "补买提醒" in mails[0][1]
    assert trays and trays[0][0] == "续费 / 补买提醒"

    rem._check_restock()                          # 同一天再调 → 幂等，不再打扰
    assert len(mails) == 1
    assert len(trays) == 1


def test_restock_silent_when_stock_is_enough(env) -> None:
    dm, rem, mails, trays = env
    _add(dm, "纸巾", 10)

    rem._check_restock()

    assert mails == []
    assert trays == []


def test_restock_lists_every_short_item(env) -> None:
    dm, rem, mails, _trays = env
    _add(dm, "洗手液", 0, unit="瓶")             # 需购
    _add(dm, "纸巾", 1, min_qty=5, unit="提")    # 不足
    _add(dm, "牙膏", 9)                          # 充足 → 不该出现

    rem._check_restock()

    body = mails[0][1]
    assert "洗手液" in body and "纸巾" in body
    assert "牙膏" not in body


def test_restock_separates_membership_renewal_from_purchases(env) -> None:
    dm, rem, mails, _trays = env
    expires = (date.today() + timedelta(days=2)).isoformat()
    dm.inventory.add_item({
        "name": "音乐会员", "category": "订阅", "quantity": 1,
        "membership": {"username": "music", "expires_on": expires,
                        "auto_renew": True, "renew_months": 12},
    })
    dm.inventory.add_item({"name": "纸巾", "quantity": 0, "unit": "包"})
    dm.inventory.save()

    rem._check_restock()

    body = mails[0][1]
    assert "续费提醒" in body and "音乐会员" in body
    assert expires in body and "自动续费已开启" in body
    assert "补买提醒" in body and "纸巾" in body


def test_restock_body_uses_current_membership_status_instead_of_saved_status() -> None:
    from src.services.reminder_rules import restock_body

    today = date.today()
    item = {
        "name": "过期会员", "quantity": 1, "unit": "个", "status": "充足",
        "membership": {"expires_on": (today - timedelta(days=2)).isoformat()},
    }

    body = restock_body([item], today=today)

    assert "续费提醒" in body
    assert "已过期 2 天" in body
