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
    p.add_argument("--membership",
                   help='会员信息 JSON（虚拟品类）：{"username":"x","expires_on":"2027-03-15",'
                        '"auto_renew":true,"renew_months":12}；手机号**不放这里**')
    _update_item_parser(sub)


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
    p.add_argument("--tags")
    p.add_argument("--unit")
    p.add_argument("--doses-per-unit", type=int)
    p.add_argument("--min-doses", type=int)
    p.add_argument("--instances", help="JSON 数组（整组替换）")
    p.add_argument("--membership", help="会员信息 JSON（整组替换；空对象 = 清掉）")

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
