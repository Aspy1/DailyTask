"""精确余量（`remaining_doses`）必须**贯穿所有读取端** —— 2026-10-19 审查 R2 的回归。

病根：底层"1 盒 24 片扣 1 片"的算法已经修好（`remaining_doses=23` 存对了），
但**读取端各自重算**：界面拿 `quantity × doses_per_unit` 拼字符串、`lookup_item`
也一样、AI 摘要只给盒数 —— 于是三处都显示 `0盒`，用户和模型都以为没库存了。

所以这里测的是**链路**：扣减 → 界面 / 查询 / 提示词 → 重新载入，
四个出口都必须报出"还剩 23"。
"""

from src.models.inventory import InventoryModel
from src.services.ai_prompts import inventory_prompt
from src.ui.panels.inventory_text import quantity_text

# 1 盒 24 片（真实用例：布洛芬这类药）
PACK = {"name": "布洛芬", "category": "日常消耗品", "quantity": 1,
        "unit": "盒", "doses_per_unit": 24, "min_doses": 5}


# ── 纯口径 ──────────────────────────────────────────────────

def test_stock_parts_splits_boxes_and_loose() -> None:
    item = {**PACK, "remaining_doses": 23}
    assert InventoryModel.stock_parts(item) == (0, 23, 24)
    item = {**PACK, "remaining_doses": 48}
    assert InventoryModel.stock_parts(item) == (2, 0, 24)


def test_stock_text_says_the_loose_doses_out_loud() -> None:
    """"0 盒"必须带上散片 —— 否则读起来就是"没了"。"""
    assert "23" in InventoryModel.stock_text({**PACK, "remaining_doses": 23})
    assert InventoryModel.stock_text({**PACK, "remaining_doses": 48}) == "2盒"
    # 没分装的老数据：就是件数，不加括号
    plain = {"name": "抽纸", "quantity": 3, "unit": "包"}
    assert InventoryModel.stock_text(plain) == "3包"


def test_stock_parts_falls_back_for_old_data_without_remaining_doses() -> None:
    """老数据没有 `remaining_doses` → 用 `quantity × doses_per_unit` 现算（自愈）。"""
    assert InventoryModel.stock_parts(PACK) == (1, 0, 24)


# ── 链路：四个出口 + 重新载入 ────────────────────────────────

def test_remainder_reaches_ui_query_and_prompt(qapp, sandbox) -> None:
    """⭐ 扣减 1 片之后：界面 / `lookup_item` / AI 摘要都必须是"还剩 23"。"""
    from helpers import run

    assert run('add_item --name "布洛芬" --category "日常消耗品" --quantity 1 '
               '--unit "盒" --doses-per-unit 24 --min-doses 5').startswith("OK")
    out = run("consume --id i_001 --amount 1")
    assert out.startswith("OK") and "23" in out, out

    # ① CLI 查询（每个 `run` 都是新进程 → 这一条同时也是"重新载入" ✓）
    looked = run('lookup_item --name "布洛芬"')
    assert "23" in looked, looked
    assert "剩 23" in looked, f"散片没露出来：{looked}"

    # ② 界面
    model = InventoryModel(sandbox / "inventory.json")
    text = quantity_text(model.items[0])
    assert "23" in text, text

    # ③ AI 摘要
    prompt = inventory_prompt(model)
    assert "23" in prompt, prompt


def test_remainder_survives_a_save_and_reload(tmp_path) -> None:
    """存盘 → 重新读盘：余量不丢、不回到"盒数 × 每盒片数"。"""
    path = tmp_path / "inventory.json"
    model = InventoryModel(path)
    iid = model.add_item(dict(PACK))
    model.consume_doses(iid, 1)
    model.save()

    again = InventoryModel(path)
    assert again.items[0]["remaining_doses"] == 23
    assert "23" in InventoryModel.stock_text(again.items[0])
    assert "23" in quantity_text(again.items[0])
