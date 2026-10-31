"""CLI 参数定义（`actions.py` 的 argparse 子命令）。

单独成文件的原因：命令层已接近「单文件 ≤800 行」上限；把纯声明式的
subparser 定义搬出来，命令层只留命令实现 + 执行器 + `main()`。

⚠ 这里的每个 `--选项` 都要与 `actions_core.ALLOWED_OPTIONS` 对齐，
由 `tests/test_actions_validation.py` 交叉校验（防漂移）。
"""



def _add_task_parsers(sub) -> None:
    """课程表 / 作业 / 考试。"""
    p = sub.add_parser("add_task", help="添加作业")
    p.add_argument("--course", help="课程名（支持模糊匹配）")
    p.add_argument("--title", required=True, help="作业标题")
    p.add_argument("--due", required=True, help="截止日期（YYYY-MM-DD / 下周日 / 6月20日）")
    p.add_argument("--priority", default="medium", choices=["high", "medium", "low"])
    p.add_argument("--tags")
    p.add_argument("--notes")

    p = sub.add_parser("complete_task", help="标记作业完成")
    p.add_argument("--id", required=True, help="作业ID (t_001)")

    p = sub.add_parser("add_exam", help="添加考试")
    p.add_argument("--course", required=True)
    p.add_argument("--date", required=True, help="考试日期")
    p.add_argument("--scope")
    p.add_argument("--location")
    p.add_argument("--notes")
    p.add_argument("--tags")

    p = sub.add_parser("add_course", help="添加课程")
    p.add_argument("--name", required=True)
    p.add_argument("--day", type=int, required=True, help="1=周一 … 7=周日")
    p.add_argument("--weeks", default="1-16")
    p.add_argument("--slots", default="3-4")
    p.add_argument("--location")
    p.add_argument("--teacher")
    p.add_argument("--parity", default="all", choices=["all", "odd", "even"])

    p = sub.add_parser("delete_course", help="删除课程")
    p.add_argument("--id", required=True)

    p = sub.add_parser("update_course", help="修改课程（只改传入的字段）")
    p.add_argument("--id", required=True)
    p.add_argument("--name")
    p.add_argument("--day", type=int, help="1=周一 … 7=周日")
    p.add_argument("--weeks", help="起-止（1-16）")
    p.add_argument("--slots", help="起-止（1-6，大节）")
    p.add_argument("--location")
    p.add_argument("--teacher")
    p.add_argument("--parity", choices=["all", "odd", "even"])


def _add_routine_parsers(sub) -> None:
    """习惯 / 日程计划。"""
    p = sub.add_parser("add_habit", help="添加习惯")
    p.add_argument("--name", required=True)
    p.add_argument("--schedule", default="daily/1", help="daily/1 weekly/1,3,5 monthly/4")
    p.add_argument("--duration", type=int, default=30)
    p.add_argument("--reminder")

    p = sub.add_parser("log_habit", help="打卡习惯")
    p.add_argument("--id", required=True)

    p = sub.add_parser("add_plan", help="添加日程计划")
    p.add_argument("--date", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--slot", type=int, default=1)
    p.add_argument("--type", default="custom")
    p.add_argument("--course")
    p.add_argument("--note")

    p = sub.add_parser("replace_plans", help="替换某天全部计划")
    p.add_argument("--date", required=True)
    p.add_argument("--plans", required=True, help="JSON数组")

    p = sub.add_parser("delete_plan", help="删除某天某条计划")
    p.add_argument("--date", required=True)
    p.add_argument("--index", type=int, required=True)

    p = sub.add_parser("complete_plan", help="把某条计划标记为完成")
    p.add_argument("--date", required=True)
    p.add_argument("--index", type=int, required=True)


def _add_finance_parsers(sub) -> None:
    """收入 / 固定支出 / 预计支出（A4）：只设初始值，预计支出由代码算。"""
    p = sub.add_parser("finance_set", help="设置总余额 / 月收入 / 固定支出")
    p.add_argument("--balance", help="现在总余额（元）")
    p.add_argument("--monthly-income", dest="monthly_income", help="每月收入（元）")
    p.add_argument("--fixed-expenses", dest="fixed_expenses", help="每月固定支出（元）")

    sub.add_parser("finance_summary", help="本月汇总：已花 / 预计 / 收入 / 结余 / 余额")


def _add_item_parsers(sub) -> None:
    """有什么（库存物品）。"""
    p = sub.add_parser("add_item", help="添加物品")
    p.add_argument("--name", required=True)
    p.add_argument("--category", default="其他")
    # default=None：要能区分「没传」与「--quantity 0（已用完）」，否则 `or 1` 会把 0 记成 1 件（ERRORS #027）
    p.add_argument("--quantity", type=int, default=None)
    p.add_argument("--min_qty", type=int, default=1)
    p.add_argument("--location")
    p.add_argument("--notes")
    p.add_argument("--group", default="")
    p.add_argument("--tags")
    p.add_argument("--status", default=None)  # accepted but ignored, auto-derived
    p.add_argument("--unit", help="单位（件/盒/提/片/瓶…）")
    p.add_argument("--doses-per-unit", type=int, default=None, help="每份含量（1 盒 24 片 → 24）")
    p.add_argument("--min-doses", type=int, default=None, help="片级下限（剩不到 N 片就标不足 → 触发补货）")
    p.add_argument("--instances", help='同类不同特征的各件，JSON 数组，如 [{"tags":["Type-C"]}]')
    p.add_argument("--runs-out", help="预估用完日 YYYY-MM-DD")
    p.add_argument("--runs-out-months", type=int, help="还能用 N 个月（代码算日期）")
    p.add_argument("--worn-days", type=int, help="这件穿了 N 天（代码算起始日）")
    p.add_argument("--needs-wash", choices=["yes", "no"], help="该洗了？yes/no")
    p.add_argument("--expires", help="保质期到期日 YYYY-MM-DD（药品临期换新）")
    p.add_argument("--remind-before", type=int, help="到期前 N 天提醒（默认 7）")
    p.add_argument("--stock-target", type=int, help="常备量（剩 1/4 时提醒补货）")
    p.add_argument("--membership",
                   help='会员信息 JSON（订阅）：{"username":"x","expires_on":"2027-03-15",'
                        '"auto_renew":true,"renew_months":12}；手机号**不放这里**')
    _add_billing_parsers(p)
    _update_item_parser(sub)


def _add_billing_parsers(p) -> None:
    """月付 / 分期（花呗，A1）：**只填每月几号**，不算手续费、不算利息。"""
    p.add_argument("--billing-type", choices=["monthly", "installment", "none"],
                   help="monthly=每月固定扣（会员）/ installment=分期（花呗）；none=取消账单")
    p.add_argument("--amount", type=float, help="每期金额（元）")
    p.add_argument("--due-day", type=int, help="每月几号扣（1-31；31 号在小月按月末）")
    p.add_argument("--installments", type=int, help="分几期；月付不填（不限期数）")


def _update_item_parser(sub) -> None:
    """`update_item`（只改显式传入的字段；`--membership` 是**整组替换**）。"""
    p = sub.add_parser("update_item", help="更新物品")
    p.add_argument("--id", required=True)
    p.add_argument("--name")
    p.add_argument("--group")
    p.add_argument("--category")
    p.add_argument("--quantity", type=int)
    p.add_argument("--status", choices=["充足", "不足", "需购"])
    p.add_argument("--min_qty", type=int)
    p.add_argument("--location")
    p.add_argument("--notes")
    p.add_argument("--runs-out", help="预估用完日 YYYY-MM-DD")
    p.add_argument("--runs-out-months", type=int, help="还能用 N 个月（代码算日期）")
    p.add_argument("--worn-days", type=int, help="这件穿了 N 天（代码算起始日）")
    p.add_argument("--needs-wash", choices=["yes", "no"], help="该洗了？yes/no")
    p.add_argument("--expires", help="保质期到期日 YYYY-MM-DD（药品临期换新）")
    p.add_argument("--remind-before", type=int, help="到期前 N 天提醒（默认 7）")
    p.add_argument("--stock-target", type=int, help="常备量（剩 1/4 时提醒补货）")
    p.add_argument("--tags")
    p.add_argument("--unit")
    p.add_argument("--doses-per-unit", type=int)
    p.add_argument("--min-doses", type=int)
    p.add_argument("--instances", help="JSON 数组（整组替换）")
    p.add_argument("--membership", help="会员信息 JSON（整组替换；空对象 = 清掉）")
    _add_billing_parsers(p)

    p = sub.add_parser("consume", help="消耗 N 份（按每份含量扣减 + 重算状态）")
    p.add_argument("--id", required=True)
    p.add_argument("--amount", type=int, default=1)

    p = sub.add_parser("set_locations", help="整份设置允许的位置清单（逗号分隔）")
    p.add_argument("--values", required=True)

    p = sub.add_parser("delete_item", help="删除物品")
    p.add_argument("--id", required=True)

    p = sub.add_parser("lookup_item", help="按条件查找物品（不带条件=列出全部）")
    p.add_argument("--name")
    p.add_argument("--category")
    p.add_argument("--tag")
    p.add_argument("--location")
    p.add_argument("--restock", choices=["yes", "no"], help="只看需补货的")

    p = sub.add_parser("add_location", help="给位置清单追加一个位置")
    p.add_argument("--name", required=True)

    sub.add_parser("need_restock", help="查看需购物品")


def _add_study_parsers(sub) -> None:
    """考研备考：学习记录 / 错题 / 模考 / 汇总。"""
    p = sub.add_parser("log_study", help="记一段学习时长")
    p.add_argument("--subject", required=True, help="math/english/politics/cs408 或中文名")
    p.add_argument("--minutes", type=int, required=True, help="分钟（1-1440）")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--note")

    p = sub.add_parser("add_mistake", help="记一道错题（自动安排间隔复习）")
    p.add_argument("--subject", required=True)
    p.add_argument("--topic", required=True, help="知识点，如 极限/页面置换")
    p.add_argument("--question")
    p.add_argument("--answer")
    p.add_argument("--note")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")

    p = sub.add_parser("review_mistake", help="复习一次错题（推进一档）")
    p.add_argument("--id", required=True)

    p = sub.add_parser("master_mistake", help="直接标记错题已掌握")
    p.add_argument("--id", required=True)

    p = sub.add_parser("add_mock", help="记一次模拟考试")
    p.add_argument("--subject", required=True)
    p.add_argument("--score", type=int, required=True)
    p.add_argument("--full-score", dest="full_score", type=int, default=150)
    p.add_argument("--duration", type=int, default=180, help="分钟")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")
    p.add_argument("--note")

    p = sub.add_parser("list_mistakes", help="列出未掌握错题")
    p.add_argument("--subject")
    p.add_argument("--due", choices=["yes", "no"], help="只看今天该复习的")

    p = sub.add_parser("study_summary", help="今日/本周学习、待复习、模考与倒计时")
    p.add_argument("--date", help="按某天算，默认今天")

    p = sub.add_parser("study_set_target", help="设置目标考试日期 / 每日目标")
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--daily-goal", dest="daily_goal", type=int, help="每日目标分钟")


def _add_expense_parsers(sub) -> None:
    """记账 / 存钱。"""
    p = sub.add_parser("add_expense", help="记一笔支出")
    p.add_argument("--amount", required=True, help="金额（>0）")
    p.add_argument("--category", required=True, help="分类 id 或中文名（food/餐饮）")
    p.add_argument("--note")
    p.add_argument("--date", help="YYYY-MM-DD，默认今天")

    p = sub.add_parser("add_saving", help="记一笔存钱")
    p.add_argument("--amount", required=True)
    p.add_argument("--note")
    p.add_argument("--date")

    p = sub.add_parser("delete_expense", help="删除一笔支出")
    p.add_argument("--id", required=True)

    p = sub.add_parser("expense_summary", help="支出汇总")
    p.add_argument("--month", help="YYYY-MM，默认当月")


def _add_backup_parsers(sub) -> None:
    """备份 / 恢复 / 概览。"""
    p = sub.add_parser("list_backups", help="列出备份")
    p.add_argument("--name", help="只看某个文件，如 courses.json")

    p = sub.add_parser("restore", help="从备份恢复（用户手动入口，需 --yes）")
    p.add_argument("--name", required=True)
    p.add_argument("--stamp", help="指定时间戳（默认最近一份）")
    p.add_argument("--yes", action="store_true", help="确认恢复")

    sub.add_parser("status", help="概览")
