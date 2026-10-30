"""命令参数规格表（**纯数据**）：每命令允许的参数 + 每个参数的校验规则。

从 `scripts/actions_core.py` 搬出来（那个文件超过 800 行上限）。
`actions_core` 仍从这里再导出 `ALLOWED_OPTIONS` / `SPECS` / `MAX_*` —— 老的 import 不用改。
"""

MAX_TITLE = 120
MAX_TEXT = 80
MAX_JSON = 500          # JSON 载荷参数（`--instances` / `--membership`）—— 80 字装不下
MAX_NOTE = 500
MAX_QUANTITY = 100000
MAX_AMOUNT = 1_000_000


# 每个命令允许出现的参数（防止 AI 拼错 --titel 之类被静默忽略）。
# ⚠ 与 CLI 的 subparser 由 tests/test_actions_validation.py 交叉校验，避免漂移。
ALLOWED_OPTIONS: dict[str, set[str]] = {
    "add_task": {"course", "title", "due", "priority", "tags", "notes"},
    "complete_task": {"id"},
    "add_exam": {"course", "date", "scope", "location", "notes", "tags"},
    "add_habit": {"name", "schedule", "duration", "reminder"},
    "log_habit": {"id"},
    "add_plan": {"date", "title", "slot", "type", "course", "note"},
    "replace_plans": {"date", "plans"},
    "delete_plan": {"date", "index"}, "complete_plan": {"date", "index"},
    "add_course": {"name", "day", "weeks", "slots", "location", "teacher", "parity"},
    "delete_course": {"id"},
    "update_course": {"id", "name", "day", "weeks", "slots", "location",
                      "teacher", "parity"},
    "add_item": {"name", "category", "quantity", "min_qty", "min_doses", "location", "notes", "group",
                 "tags", "status", "unit", "doses_per_unit", "instances", "membership", "runs_out", "runs_out_months", "worn_days", "needs_wash", "expires", "remind_before", "stock_target",
                 "billing_type", "amount", "due_day", "installments"},
    "update_item": {"id", "name", "group", "category", "quantity", "status", "min_qty", "min_doses",
                    "location", "tags", "unit", "doses_per_unit", "instances", "membership", "notes",
                    "runs_out", "runs_out_months", "worn_days", "needs_wash", "expires",
                    "remind_before", "stock_target",
                    "billing_type", "amount", "due_day", "installments"},
    "consume": {"id", "amount"},
    "set_locations": {"values"},
    "delete_item": {"id"},
    "need_restock": set(),
    "lookup_item": {"name", "category", "tag", "location", "restock"}, "add_location": {"name"},
    "status": set(),
    "add_expense": {"amount", "category", "note", "date"},
    "add_saving": {"amount", "note", "date"},
    "delete_expense": {"id"},
    "expense_summary": {"month"},
    "list_backups": {"name"},
    "restore": {"name", "stamp", "yes"},
}


# 参数规格（**数据驱动**）：{动作: {"required": (必填项…), 参数名: 规则}}
#
# 规则 = (kind, …)：
#   text(len)       文本，去空白 + 长度上限（非空由 required 负责）
#   due             截止时间（先按自然语言解析，再校验）
#   date / date_opt 严格 YYYY-MM-DD；date_opt 允许不传（命令内取默认）
#   month           YYYY-MM（不传取当月）
#   money           金额（>0，两位小数）
#   int(lo,hi)      必填整数范围
#   int_opt(lo,hi)  可缺省整数范围（None 允许：要能区分「没传」与「传 0」）
#   choice(…)       枚举（可缺省）
#   id              ID 形如 t_001
#   weeks / slots   起-止 区间（周次 1~30 / 节次 1~6）
#   schedule        习惯周期 daily/N、weekly/1,3,5、monthly/N
#   reminder        hh:mm（或空）
#   jsonplans       计划 JSON 数组
SPECS: dict[str, dict] = {
    "add_task": {
        "required": ("title", "due"),
        "title": ("text", MAX_TITLE), "due": ("due",),
        "priority": ("choice", ("high", "medium", "low")),
        "course": ("text", MAX_TEXT), "notes": ("text", MAX_NOTE),
        "tags": ("text", MAX_NOTE),
    },
    "complete_task": {"required": ("id",), "id": ("id",)},
    "add_exam": {
        "required": ("course", "date"),
        "course": ("text", MAX_TEXT), "date": ("date",),
        "scope": ("text", MAX_NOTE), "location": ("text", MAX_TEXT),
        "notes": ("text", MAX_NOTE), "tags": ("text", MAX_NOTE),
    },
    "add_habit": {
        "required": ("name",),
        "name": ("text", MAX_TITLE), "schedule": ("schedule",),
        "duration": ("int_opt", 1, 600), "reminder": ("reminder",),
    },
    "log_habit": {"required": ("id",), "id": ("id",)},
    "add_plan": {
        "required": ("date", "title"),
        "date": ("date",), "title": ("text", MAX_TITLE),
        "slot": ("int_opt", 1, 6), "type": ("text", MAX_TEXT),
        "course": ("text", MAX_TEXT), "note": ("text", MAX_NOTE),
    },
    "replace_plans": {
        "required": ("date", "plans"),
        "date": ("date",), "plans": ("jsonplans",),
    },
    "delete_plan": {
        "required": ("date", "index"),
        "date": ("date",), "index": ("int", 0, 100),
    },
    "complete_plan": {"required": ("date", "index"), "date": ("date",), "index": ("int", 0, 100)},
    "add_course": {
        "required": ("name", "day"),
        "name": ("text", MAX_TITLE), "day": ("int", 1, 7),
        "weeks": ("weeks",), "slots": ("slots",),
        "parity": ("choice", ("all", "odd", "even")),
        "location": ("text", MAX_TEXT), "teacher": ("text", MAX_TEXT),
    },
    "delete_course": {"required": ("id",), "id": ("id",)},
    "update_course": {
        "required": ("id",), "id": ("id",),
        "name": ("text", MAX_TITLE), "day": ("int_opt", 1, 7),
        "weeks": ("weeks_opt",), "slots": ("slots_opt",),
        "parity": ("choice", ("all", "odd", "even")),
        "location": ("text", MAX_TEXT), "teacher": ("text", MAX_TEXT),
    },
    "add_item": {
        "required": ("name",),
        "name": ("text", MAX_TITLE), "category": ("text", MAX_TEXT),
        "quantity": ("int_opt", 0, MAX_QUANTITY), "membership": ("text", MAX_JSON),
        "min_qty": ("int_opt", 0, MAX_QUANTITY),
        "location": ("text", MAX_TEXT), "notes": ("text", MAX_NOTE),
        "group": ("text", MAX_TEXT), "tags": ("text", MAX_NOTE),
        "status": ("text", MAX_TEXT),          # CLI 接受但忽略（状态自动推导）
        "unit": ("text", MAX_TEXT), "doses_per_unit": ("int_opt", 1, MAX_QUANTITY),
        "min_doses": ("int_opt", 0, MAX_QUANTITY),   # 片级下限（0 = 不用）
        "instances": ("text", MAX_JSON),       # JSON 数组，handler 里解析
        "billing_type": ("choice", ("monthly", "installment", "none")),
        "amount": ("money_opt",), "due_day": ("int_opt", 1, 31),
        "installments": ("int_opt", 0, 120),
    },
    "update_item": {
        "required": ("id",), "id": ("id",),
        "quantity": ("int_opt", 0, MAX_QUANTITY), "membership": ("text", MAX_JSON),
        "min_qty": ("int_opt", 0, MAX_QUANTITY),
        "status": ("choice", ("充足", "不足", "需购")),
        "name": ("text", MAX_TITLE), "group": ("text", MAX_TEXT),
        "category": ("text", MAX_TEXT), "location": ("text", MAX_TEXT),
        "notes": ("text", MAX_NOTE),
        "tags": ("text", MAX_NOTE),
        "unit": ("text", MAX_TEXT), "doses_per_unit": ("int_opt", 1, MAX_QUANTITY),
        "min_doses": ("int_opt", 0, MAX_QUANTITY),
        "instances": ("text", MAX_JSON), "runs_out": ("text", MAX_TEXT),
        "runs_out_months": ("int_opt", 1, 600),
        "worn_days": ("int_opt", 0, 3650), "needs_wash": ("choice", ("yes", "no")),
        "expires": ("text", MAX_TEXT), "remind_before": ("int_opt", 1, 3650), "stock_target": ("int_opt", 1, MAX_QUANTITY),
        "billing_type": ("choice", ("monthly", "installment", "none")),
        "amount": ("money_opt",), "due_day": ("int_opt", 1, 31),
        "installments": ("int_opt", 0, 120),
    },
    "consume": {"required": ("id",), "id": ("id",),
                "amount": ("int_opt", 1, MAX_QUANTITY)},
    "set_locations": {"required": ("values",), "values": ("text", MAX_NOTE)},
    "delete_item": {"required": ("id",), "id": ("id",)},
    "lookup_item": {"name": ("text", MAX_TITLE), "category": ("text", MAX_TEXT),
                    "tag": ("text", MAX_TEXT), "location": ("text", MAX_TEXT),
                    "restock": ("choice", ("yes", "no"))},
    "add_location": {"required": ("name",), "name": ("text", MAX_TEXT)},
    "add_expense": {
        "required": ("amount", "category"),
        "amount": ("money",), "category": ("text", MAX_TEXT),
        "note": ("text", MAX_NOTE), "date": ("date_opt",),
    },
    "add_saving": {
        "required": ("amount",),
        "amount": ("money",), "note": ("text", MAX_NOTE), "date": ("date_opt",),
    },
    "delete_expense": {"required": ("id",), "id": ("id",)},
    "expense_summary": {"month": ("month",)},
    "list_backups": {"name": ("text", MAX_TEXT)},
    "restore": {"required": ("name",), "name": ("text", MAX_TEXT),
                "stamp": ("text", MAX_TEXT)},
}
