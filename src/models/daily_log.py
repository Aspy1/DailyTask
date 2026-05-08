"""Daily log + plans model."""

from datetime import date, datetime
from pathlib import Path

from src.models.base import BaseJsonModel
from src.models.course import schedule_date


DEFAULT_DAILY_LOGS = {
    "_version": 4,
    "logs": {},
    "plans": {},
    "savings": {},
    "reminders": [],
}


class DailyLogModel(BaseJsonModel):
    def __init__(self, file_path: Path):
        super().__init__(file_path, DEFAULT_DAILY_LOGS)

    def get_log(self, day: str | None = None) -> dict:
        if day is None:
            day = date.today().isoformat()
        return self._data.get("logs", {}).get(day, {})

    def set_log(self, day: str, log: dict) -> None:
        self._data.setdefault("logs", {})[day] = log

    def is_logged_today(self) -> bool:
        today = schedule_date().isoformat()
        return today in self._data.get("logs", {})

    @property
    def today(self) -> dict:
        return self.get_log()

    # ── Plans ──────────────────────────────────────────────

    def get_plans(self, day: str | None = None) -> list[dict]:
        if day is None:
            day = date.today().isoformat()
        return self._data.get("plans", {}).get(day, [])

    def add_plan(self, plan: dict, day: str | None = None) -> None:
        if day is None:
            day = date.today().isoformat()
        plans = self._data.setdefault("plans", {})
        day_plans = plans.setdefault(day, [])
        plan.setdefault("type", "custom")
        day_plans.append(plan)

    def get_today_plans(self) -> list[dict]:
        return self.get_plans()

    def delete_plan(self, day: str, index: int) -> bool:
        day_plans = self._data.get("plans", {}).get(day, [])
        if 0 <= index < len(day_plans):
            day_plans.pop(index)
            if not day_plans:
                del self._data["plans"][day]
            return True
        return False

    # ── Savings ─────────────────────────────────────────────

    def get_savings(self, day: str | None = None) -> list[dict]:
        if day is None:
            day = date.today().isoformat()
        return self._data.get("savings", {}).get(day, [])

    def add_saving(self, amount: float, note: str = "", day: str | None = None) -> str:
        if day is None:
            day = date.today().isoformat()
        sav = self._data.setdefault("savings", {})
        day_sav = sav.setdefault(day, [])
        sid = f"s_{len(day_sav) + 1:03d}"
        entry = {"id": sid, "amount": amount, "note": note, "created_at": datetime.now().isoformat()}
        day_sav.append(entry)
        return sid

    def delete_saving(self, day: str, index: int) -> bool:
        day_sav = self._data.get("savings", {}).get(day, [])
        if 0 <= index < len(day_sav):
            day_sav.pop(index)
            if not day_sav:
                del self._data["savings"][day]
            return True
        return False

    def today_savings_total(self) -> float:
        today = date.today().isoformat()
        return sum(s.get("amount", 0) for s in self.get_savings(today))

    # ── Custom Email Reminders ──────────────────────────────

    def add_reminder(self, item_type: str, item_name: str, item_date: str, notify_time: str) -> str:
        reminders = self._data.setdefault("reminders", [])
        rid = f"rem_{len(reminders) + 1:04d}"
        entry = {
            "id": rid,
            "item_type": item_type,
            "item_name": item_name,
            "item_date": item_date,
            "notify_time": notify_time,
            "created_at": datetime.now().isoformat(),
        }
        reminders.append(entry)
        return rid

    def get_reminders(self) -> list[dict]:
        return self._data.get("reminders", [])

    def delete_reminder(self, reminder_id: str) -> bool:
        reminders = self._data.get("reminders", [])
        for i, r in enumerate(reminders):
            if r["id"] == reminder_id:
                reminders.pop(i)
                return True
        return False

    def find_reminder(self, item_type: str, item_name: str, item_date: str) -> dict | None:
        for r in self._data.get("reminders", []):
            if r["item_type"] == item_type and r["item_name"] == item_name and r["item_date"] == item_date:
                return r
        return None

    def delete_reminders_by_item(self, item_type: str, item_name: str, item_date: str) -> int:
        """Delete all reminders matching an item. Returns count deleted."""
        reminders = self._data.get("reminders", [])
        kept = []
        removed = 0
        for r in reminders:
            if r["item_type"] == item_type and r["item_name"] == item_name and r["item_date"] == item_date:
                removed += 1
            else:
                kept.append(r)
        if removed:
            self._data["reminders"] = kept
        return removed

    def month_savings_total(self, year: int | None = None, month: int | None = None) -> float:
        if year is None:
            year = date.today().year
        if month is None:
            month = date.today().month
        prefix = f"{year}-{month:02d}"
        total = 0.0
        for day_str, entries in self._data.get("savings", {}).items():
            if day_str.startswith(prefix):
                total += sum(s.get("amount", 0) for s in entries)
        return total
