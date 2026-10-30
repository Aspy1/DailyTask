"""收入 / 固定支出 / 预计支出（A4，用户 2026-10-31 口径）。

口径：用户只给**初始值**；"预计本月支出"由**代码**算（过去 3 个整月中位数），
界面注明依据，**AI 只解释、不算数**。
"""

from datetime import date

from src.models.expense import ExpenseModel
from src.services.finance import basis_months, median, monthly_totals, summary


def _rec(day: str, amount: float) -> dict:
    return {"date": day, "amount": amount, "category": "food"}


TODAY = date(2026, 10, 15)


def test_median_odd_and_even() -> None:
    assert median([3, 1, 2]) == 2
    assert median([1, 2, 3, 4]) == 2.5
    assert median([]) == 0


def test_monthly_totals_groups_by_month() -> None:
    totals = monthly_totals([_rec("2026-09-01", 10), _rec("2026-09-20", 5.5),
                             _rec("2026-08-01", 7), _rec("bad", 99)])
    assert totals == {"2026-09": 15.5, "2026-08": 7.0}


def test_basis_months_rolls_over_the_year() -> None:
    assert basis_months(date(2026, 2, 10)) == ["2026-01", "2025-12", "2025-11"]


def test_projection_uses_median_of_past_three_months() -> None:
    records = [_rec("2026-07-10", 100), _rec("2026-08-10", 120),
               _rec("2026-09-10", 900)]          # 9 月是离群值（买了大件）
    result = summary(records, {"monthly_income": 2000}, today=TODAY)
    assert result["projected"] == 120, "中位数要抗离群值（均值会是 373）"
    assert result["basis_months"] == 3
    assert result["income"] == 2000
    assert result["left"] == 1880


def test_projection_never_below_what_is_already_spent() -> None:
    records = [_rec("2026-08-10", 100), _rec("2026-09-10", 100),
               _rec("2026-10-02", 500)]          # 本月已经花了 500
    result = summary(records, {"monthly_income": 0}, today=TODAY)
    assert result["projected"] == 500


def test_no_history_falls_back_to_spent() -> None:
    result = summary([_rec("2026-10-03", 30)], {}, today=TODAY)
    assert result["basis_months"] == 0
    assert result["projected"] == 30


def test_fixed_expenses_and_balance_pass_through() -> None:
    result = summary([], {"balance": 5000, "monthly_income": 3000,
                          "fixed_expenses": 1200}, today=TODAY)
    assert result["balance"] == 5000
    assert result["fixed"] == 1200
    assert result["projected"] == 0


def test_model_set_finance_only_takes_whitelisted_keys(tmp_path) -> None:
    m = ExpenseModel(tmp_path / "expenses.json")
    m.set_finance({"monthly_income": 3000, "utm_source": "x"})
    assert m.finance["monthly_income"] == 3000
    assert "utm_source" not in m.finance


# ── 命令路径（AI 与用户同一条）────────────────────────────────

def test_cli_set_and_summary(sandbox) -> None:
    from helpers import run

    out = run("python scripts/actions.py finance_set --balance 5000 "
              "--monthly-income 3000 --fixed-expenses 1200")
    assert "OK finance_set" in out

    out = run("python scripts/actions.py finance_summary")
    assert "月收入 ￥3000.00" in out or "月收入 ¥3000.00" in out
    assert "总余额 ¥5000.00" in out
    assert "中位数" in out or "本月已花" in out


def test_cli_set_requires_at_least_one_value(sandbox) -> None:
    from helpers import run

    out = run("python scripts/actions.py finance_set")
    assert "ERROR" in out


# ── 界面：数值来自 finance.summary()，界面不算数 ────────────────

def test_forecast_card_shows_numbers_and_basis(qapp) -> None:
    from src.ui.panels.expense_cards import ForecastCard

    card = ForecastCard()
    card.update_summary({"projected": 1234.5, "income": 3000.0, "left": 1765.5,
                         "basis_months": 3, "fixed": 0, "balance": 0, "spent": 0,
                         "basis_total": 3})
    assert card._projected.text() == "¥1234.50"
    assert "3000.00" in card._meta.text()
    assert "3 个月中位数" in card._basis.text()
