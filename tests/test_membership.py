"""会员（虚拟品类）：账号绑定 + 到期日驱动状态 + **手机号私有**。

用户口径（2026-10-18）：

- 会员要绑账号：用户名 / 到期日 / 是否自动续费 / 续费时长（存**月数**）；
- **到期日决定状态**：过期 → 需购（要续费）；7 天内 → 不足（要到期了）；否则充足（有效）；
- 自动续费**只是记着**（照常按到期日算）；
- **手机号选填、不进仓库、也不进 AI 提示词** —— 单独放私有文件
  （`data/private/memberships.json`，`.gitignore` + `git_sync.PRIVATE_FILES` 双重挡着）。
"""

import json
from datetime import date, timedelta

from src.models.inventory import RENEW_WARNING_DAYS, InventoryModel, days_until
from src.models.membership_contacts import MembershipContactsModel
from tests.helpers import run


def _items(sandbox) -> list[dict]:
    """沙箱里的物品；**文件不存在也算空**（被拒绝的命令什么都不写，R-002）。"""
    path = sandbox / "inventory.json"
    return json.loads(path.read_text(encoding="utf-8"))["items"] if path.exists() else []


def _model(tmp_path) -> InventoryModel:
    return InventoryModel(tmp_path / "inventory.json")


def _member(expires: date, **extra: object) -> dict:
    return {"id": "i_001", "name": "QQ音乐会员", "category": "虚拟品类",
            "quantity": 1, "unit": "个",
            "membership": {"username": "u", "expires_on": expires.isoformat(), **extra}}


def test_expiry_drives_status() -> None:
    """到期日决定状态：过期 → 需购；7 天内 → 不足；否则充足。"""
    today = date(2026, 10, 18)
    assert InventoryModel.effective_status(_member(today - timedelta(days=1)), today) == "需购"
    assert InventoryModel.effective_status(_member(today), today) == "不足"
    assert InventoryModel.effective_status(
        _member(today + timedelta(days=RENEW_WARNING_DAYS)), today) == "不足"
    assert InventoryModel.effective_status(
        _member(today + timedelta(days=RENEW_WARNING_DAYS + 1)), today) == "充足"


def test_auto_renew_does_not_change_the_rule() -> None:
    """自动续费**只是记着**：开着也照常按到期日算（用户口径）。"""
    today = date(2026, 10, 18)
    overdue = _member(today - timedelta(days=3), auto_renew=True, renew_months=12)
    assert InventoryModel.effective_status(overdue, today) == "需购"


def test_manual_status_is_not_overwritten_for_non_members(tmp_path) -> None:
    """⚠ 回归：非会员的 `status` 可能是用户手动改过的，不能被自动推导覆盖。

    2026-10-18 被 `test_actions_smoke` 抓到：`update_item --status 需购` 之后
    `need_restock` 又把它算回"充足"。
    """
    m = _model(tmp_path)
    m.data["items"] = [{"id": "i_001", "name": "洗衣液", "quantity": 2, "status": "需购"}]
    assert m.effective_status(m.items[0]) == "需购", "没有到期日就信存下来的状态"
    assert [it["name"] for it in m.need_restock] == ["洗衣液"]


def test_member_status_is_recomputed_on_load(tmp_path) -> None:
    """会员的状态在**读盘时重算** —— 存下来的快照会随日子过期。"""
    path = tmp_path / "inventory.json"
    stale = {"_version": 1, "items": [
        {"id": "i_001", "name": "会员", "category": "虚拟品类", "quantity": 1,
         "status": "充足",                                  # 写入那天是充足
         "membership": {"expires_on": "2020-01-01"}}]}      # 早就过期了
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")

    m = InventoryModel(path)
    assert m.items[0]["status"] == "需购", "读盘后应按当前日期重算"
    assert [it["name"] for it in m.need_restock] == ["会员"]


def test_days_until_handles_bad_input() -> None:
    """解析不了的到期日 → `None`（**不猜**，退回数量规则）。"""
    assert days_until("") is None
    assert days_until("不是日期") is None
    assert days_until("2026-10-18", date(2026, 10, 18)) == 0


def test_phone_is_rejected_from_inventory_json(sandbox) -> None:
    """⚠ 泄漏守卫：手机号**不许**写进 `inventory.json`（它会同步到 GitHub）。"""
    out = run('add_item --name "QQ音乐会员" --category "虚拟品类" '
              '--membership \'{"phone":"13800000000"}\'')
    assert out.startswith("ERROR") and "手机号" in out
    assert _items(sandbox) == []


def test_membership_round_trip_through_command(sandbox) -> None:
    """命令面：`--membership` 记下账号信息，并按到期日定状态。"""
    run('add_item --name "QQ音乐会员" --category "虚拟品类" --quantity 1 '
        '--membership \'{"username":"my_qq","expires_on":"2020-01-01",'
        '"auto_renew":true,"renew_months":12}\'')

    item = _items(sandbox)[0]
    assert item["membership"]["username"] == "my_qq"
    assert item["membership"]["renew_months"] == 12
    assert item["status"] == "需购", "到期日已过 → 需购（要续费）"
    assert "QQ音乐会员" in run("need_restock")


def test_membership_unknown_keys_are_rejected(sandbox) -> None:
    """拼错的键直接拒绝（不静默吞掉，R-002 的入口校验）。"""
    out = run('add_item --name "会员" --category "虚拟品类" '
              '--membership \'{"用户名":"x"}\'')
    assert out.startswith("ERROR")
    assert _items(sandbox) == []


def test_private_contacts_model_stores_and_clears(tmp_path) -> None:
    """手机号存在**私有文件**里；传空串 = 删掉那一条（不留空壳）。"""
    m = MembershipContactsModel(tmp_path / "private" / "memberships.json")
    m.set_phone("i_001", "13800000000")
    m.save()
    assert m.phone_of("i_001") == "13800000000"

    m.set_phone("i_001", "  ")
    m.save()
    assert m.phone_of("i_001") == ""
    assert m.data["contacts"] == {}


def test_prompt_never_contains_phone(tmp_path) -> None:
    """提示词只带用户名/到期日 —— 手机号绝不进（进了就等于发给模型服务商）。"""
    from src.services.ai_service import _inventory_prompt

    m = _model(tmp_path)
    m.data["items"] = [{"id": "i_001", "name": "QQ音乐会员", "category": "虚拟品类",
                        "quantity": 1, "unit": "个", "status": "充足",
                        "membership": {"username": "my_qq",
                                       "expires_on": "2027-03-15"}}]
    text = _inventory_prompt(m)
    assert "my_qq" in text and "2027-03-15" in text
    assert "phone" not in text and "138" not in text
