"""Expense tracking data model."""

from datetime import date, datetime
from pathlib import Path

from src.models.base import BaseJsonModel, next_id
from src.models.billing import BILLING_CATEGORY_ID, BILLING_CATEGORY_NAME
from src.models.course import schedule_date

DEFAULT_EXPENSES = {
    "_version": 1,
    "categories": [
        {"id": "food", "name": "餐饮"},
        {"id": "transport", "name": "交通"},
        {"id": "study", "name": "学习"},
        {"id": "entertainment", "name": "娱乐"},
        {"id": "shopping", "name": "购物"},
        {"id": BILLING_CATEGORY_ID, "name": BILLING_CATEGORY_NAME},
        {"id": "other", "name": "其他"},
    ],
    "budget": {"monthly": 1500, "by_category": {}},
    "records": [],
}


class ExpenseModel(BaseJsonModel):
    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_EXPENSES)
        self._ensure_billing_category()

    def _ensure_billing_category(self) -> None:
        """老数据里没有「订阅/分期」分类 → 补上（自愈，幂等）。

        为什么必须补：自动记账用的是分类 **id**，界面按 id 找名字；没有这条，
        到期扣款的那几笔会在界面上显示成 `subscription` 这种键名 ✗。
        """
        cats = self._data.setdefault("categories", [])
        if not any(str(c.get("id")) == BILLING_CATEGORY_ID for c in cats):
            cats.append({"id": BILLING_CATEGORY_ID, "name": BILLING_CATEGORY_NAME})

    @property
    def records(self) -> list[dict]:
        return self._data.get("records", [])

    @property
    def categories(self) -> list[dict]:
        return self._data.get("categories", [])

    @property
    def budget(self) -> dict:
        return self._data.get("budget", {"monthly": 0, "by_category": {}})

    def add(self, expense: dict) -> str:
        records = self._data.setdefault("records", [])
        record_id = expense.get("id") or next_id("e", (r.get("id", "") for r in records))
        expense["id"] = record_id
        expense.setdefault("date", date.today().isoformat())
        expense.setdefault("created_at", datetime.now().isoformat())
        records.append(expense)
        return record_id

    def delete(self, record_id: str) -> bool:
        records = self._data.get("records", [])
        for i, r in enumerate(records):
            if r["id"] == record_id:
                records.pop(i)
                return True
        return False

    def month_total(self, year: int | None = None, month: int | None = None) -> float:
        if year is None:
            year = date.today().year
        if month is None:
            month = date.today().month
        prefix = f"{year}-{month:02d}"
        return sum(
            r["amount"] for r in self.records
            if r.get("date", "").startswith(prefix)
        )

    def today_total(self) -> float:
        today = schedule_date().isoformat()
        return sum(
            r["amount"] for r in self.records
            if r.get("date") == today
        )

    def is_today_logged(self) -> bool:
        today = schedule_date().isoformat()
        return any(r.get("date") == today for r in self.records)

    def month_by_category(self, year: int | None = None, month: int | None = None) -> dict[str, float]:
        if year is None:
            year = date.today().year
        if month is None:
            month = date.today().month
        prefix = f"{year}-{month:02d}"
        result: dict[str, float] = {}
        for r in self.records:
            if r.get("date", "").startswith(prefix):
                cat = r.get("category", "other")
                result[cat] = result.get(cat, 0) + r["amount"]
        return result
