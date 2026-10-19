"""批次三的遗留项回归（2026-10-19 审查"另外确认"那一节）。

四条都在这里钉住：

1. **提示跨天**：点掉的提示属于**哪一天** —— 常驻应用跨天后要自己失效
   （以前靠外部调 `clear_dismissed()`，而全仓没人调）。
2. **预算日期边界**：只筛 `date >= since` 会把**未来**记录算进"本月已花"；
   固定除 90 会把"还没记账的天"当成花了 0。
3. **门禁基线**：按**文件指纹**比存量（只比总数会放过"这里少一处、那里多一处"）。
4. **手动状态**：用户显式给过的 `status` 不许被自动推导覆盖（UI 与 CLI 同一规则）。
"""

from datetime import date, timedelta

from src.models.inventory import InventoryModel, status_is_manual
from src.services.budget import forecast, history_days, renewals_soon
from src.ui.widgets.hint_bar import HintBar

TODAY = date(2026, 10, 19)


# ── 1. 提示跨天 ─────────────────────────────────────────────

def test_dismissed_hints_expire_when_the_day_changes(qapp) -> None:
    """⭐ 昨天点掉的提示，今天要重新出现（提示是**今天**的）。"""
    from src.services.hints import Hint

    bar = HintBar()
    hints = [Hint("weather.rain", "今天有雨，记得带伞 ☔", "info")]
    bar.show_hints(hints)
    bar._dismiss("weather.rain")
    assert bar._dismissed == {"weather.rain"} and not bar.isVisible()

    # 模拟"到了第二天"（不改系统时钟，直接改它记的那一天）
    bar._dismissed_on = (date.today() - timedelta(days=1)).isoformat()
    bar.show_hints(hints)
    assert bar._dismissed == set(), "跨天没清 —— 昨天的提示今天还压着"
    assert bar.isVisible(), "跨天后提示该重新出现"


def test_dismissing_within_the_same_day_still_hides(qapp) -> None:
    """同一天内点掉仍然有效（别把功能清没了）。"""
    from src.services.hints import Hint

    bar = HintBar()
    bar.show_hints([Hint("k", "提示", "info")])
    bar._dismiss("k")
    bar.show_hints([Hint("k", "提示", "info")])
    assert bar._dismissed == {"k"} and not bar.isVisible()


# ── 2. 预算日期边界 ─────────────────────────────────────────

def test_future_records_do_not_count_as_spent() -> None:
    """⭐ 未来/下月的记录不算"本月已花"，也不算进历史日均。"""
    records = [{"date": "2030-01-01", "amount": 1000}]
    out = forecast(records, budget=1000, today=TODAY)
    assert out["spent"] == 0, "未来记录被算进本月支出了"
    assert out["projected"] == 0
    assert out["over"] is False


def test_history_days_uses_the_real_span_not_a_fixed_90() -> None:
    """⭐ 日均的分母是**实际有记账的天数**（封顶 90），不是固定 90。"""
    assert history_days([], TODAY) == 0
    assert history_days([{"date": TODAY.isoformat(), "amount": 10}], TODAY) == 1
    old = (TODAY - timedelta(days=400)).isoformat()
    assert history_days([{"date": old, "amount": 10}], TODAY) == 90, "封顶 90 天"


def test_daily_average_is_not_diluted_by_unrecorded_days() -> None:
    """只记了 10 天、共 100 元 → 日均 10（不是 100/90 ≈ 1.1）。"""
    records = [{"date": (TODAY - timedelta(days=9)).isoformat(), "amount": 100}]
    assert forecast(records, today=TODAY)["daily"] == 10.0
    assert forecast(records, today=TODAY)["history_days"] == 10


def test_expired_memberships_are_not_listed_as_upcoming() -> None:
    """⭐ 已经过期的会员不算"即将扣费"（那是"要续费"那条路的事）。"""
    items = [{"name": "已过期", "membership": {"auto_renew": True, "expires_on": "2026-10-01"}},
             {"name": "快到期", "membership": {"auto_renew": True, "expires_on": "2026-10-25"}}]
    assert renewals_soon(items, TODAY) == ["快到期（2026-10-25）"]


# ── 3. 门禁基线按文件指纹 ───────────────────────────────────

def test_ui_tokens_baseline_is_compared_per_file() -> None:
    """⭐ "这里少一处、那里多一处"必须被抓到（只比总数会放过）。"""
    from scripts.check_ui_tokens import _over_baseline

    baseline = {"px": {"a.py": 2, "b.py": 1}, "size_lit": {}}
    # 总数没变（3 → 3），但 a 多了一处 → 超标
    over = _over_baseline({"PX": {"a.py": 3, "b.py": 0}}, baseline)
    assert over and "a.py" in over[0]
    # 整体减少 → 通过
    assert _over_baseline({"PX": {"a.py": 1, "b.py": 1}}, baseline) == []


def test_i18n_baseline_is_compared_per_file() -> None:
    """同上：i18n 的存量也按文件比。"""
    from scripts.check_quality import Report, report_i18n

    rep = Report()
    report_i18n(rep, {"x.py": 2, "y.py": 0}, {"x.py": 1, "y.py": 1})
    assert rep.failures, "总数没变但 x.py 多了一处，应当失败"
    rep2 = Report()
    report_i18n(rep2, {"x.py": 1, "y.py": 1}, {"x.py": 1, "y.py": 1})
    assert not rep2.failures


# ── 4. 手动状态不被自动推导覆盖 ─────────────────────────────

def test_manual_status_survives_later_updates(tmp_path) -> None:
    """⭐ 界面右键"标成需购"之后，再改数量也不许把它推导回"充足"。"""
    path = tmp_path / "inventory.json"
    m = InventoryModel(path)
    iid = m.add_item({"name": "纸巾", "quantity": 5, "min_quantity": 1})
    assert m.update_item(iid, {"status": "需购"}) is True
    assert m.items[0]["status"] == "需购"
    assert status_is_manual(m.items[0])

    m.update_item(iid, {"quantity": 9})              # 数量变了，但状态是手动定的
    assert m.items[0]["status"] == "需购", "手动状态被自动推导覆盖了"
    m.save()
    assert InventoryModel(path).items[0]["status"] == "需购", "读盘后又丢了"


def test_manual_status_beats_the_date_rule(tmp_path) -> None:
    """日期驱动的物品也一样：手动 `status` 优先（与 CLI 的 `--status` 同一规则）。"""
    m = InventoryModel(tmp_path / "inventory.json")
    m.add_item({"name": "药", "quantity": 5, "expires_on": "2020-01-01", "status": "充足"})
    item = m.items[0]
    assert InventoryModel.derive_status(item) == "需购", "日期规则本身没变"
    assert InventoryModel.effective_status(item) == "充足", "手动覆盖没生效"


def test_status_without_a_manual_value_still_auto_derives(tmp_path) -> None:
    """没手动给过状态的，照旧自动推导（别把自动规则堵死）。"""
    m = InventoryModel(tmp_path / "inventory.json")
    iid = m.add_item({"name": "纸巾", "quantity": 0, "min_quantity": 1})
    assert m.items[0]["status"] == "需购"
    m.update_item(iid, {"quantity": 9})
    assert m.items[0]["status"] == "充足"
