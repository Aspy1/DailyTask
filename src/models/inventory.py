"""Inventory model — personal item library."""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from src.models.base import BaseJsonModel

# 位置是**唯一的归属信号**（用户口径 2026-10-18）：换季把衣物寄回家、来年寄回，所以
# "在哪一边"要能表达出来 —— 但**不单独存字段**，而是**由位置推导**：
#   说了位置 → 就用那个位置；没说 → 默认「学校」。
# 这样模型只需要会**抄位置**，不用去猜"家里"指哪边（flash 模型中文不稳，靠猜必错 ——
# 2026-10-18 探针实测：它把"家里抽纸"记成了"寄回家的那批"）。
DEFAULT_LOCATION = "学校"
# 「家」那一侧的位置（`HOME_LOCATION` 是主格位，"老家"是同义写法）。**其余位置（宿舍格位、
# "学校"、后来新增的）都算学校侧。** 判断"哪一边"只有这一处规则 —— 一律走 `side_of()`。
HOME_LOCATION = "家"
HOME_LOCATIONS = (HOME_LOCATION, "老家")
SIDE_SCHOOL = "school"
SIDE_HOME = "home"

# 会员（虚拟品类）：绑定账号 → 记用户名 / 到期日 / 自动续费 / 续费月数。
# ⚠ **手机号不进这个文件** —— 它会被同步到 GitHub（`git_sync.DATA_FILES`），
#   手机号单独放 `data/private/memberships.json`（.gitignore + `git_sync.PRIVATE_FILES`），
#   也不进 AI 提示词（见 `models/membership_contacts.py` 的说明）。
MEMBERSHIP_CATEGORY = "虚拟品类"
# 到期前多少天算"不足（要到期了）"。R-005：阈值只有这一处，改这里即可。
RENEW_WARNING_DAYS = 7

# 物品的**可写字段**（唯一清单）—— `add_item` / `update_item` 都读它，**不许各写一份** ✗。
# ⚠ 2026-10-19 实测到的静默丢数据：两个方法原来各写一份白名单，后加的字段（`membership` /
#   `expires_on` / `runs_out_on` / `stock_target` / `worn_*`）只加进了**命令路径**
#   （`scripts/actions_cmds_items.py` 直接改 dict，不经这里），于是
#   **会员弹窗填完到期日一保存就没了**（`update_item` 还返回 `True` 谎报成功 ✗✗）。
#   → 加字段只改这一处；`update_item` 对清单外的键会**告警**（不再默默吞掉）。
ITEM_FIELDS = (
    "name", "category", "group", "quantity", "unit", "status",
    "min_quantity", "min_doses", "location", "notes", "tags",
    "instances", "ignore_low_stock", "doses_per_unit",
    # 到期 / 常备量（C 类）
    "membership", "expires_on", "runs_out_on", "remind_before_days", "stock_target",
    # 衣物（C 类第 4 项）
    "worn_since", "wash_after_days", "needs_wash",
)


def days_until(expires_on: str, today: date | None = None) -> int | None:
    """`expires_on`（`YYYY-MM-DD`）距今还有几天；空 / 解析不了 → `None`（**不猜**）。"""
    if not expires_on:
        return None
    try:
        target = date.fromisoformat(str(expires_on)[:10])
    except ValueError:
        logger.debug("membership.expires_on 解析失败：%r", expires_on)
        return None
    return (target - (today or date.today())).days

DEFAULT_INVENTORY = {
    "_version": 1,
    "items": [],
    "categories": ["日常消耗品", "数码电子", "衣物", "虚拟品类", "其他"],
    # 允许的位置清单（用户定的固定格位 + 「学校」「家」两个粗格位）。位置本身仍是自由文本，
    # 但**AI 只应从这份清单里选** —— 提示词会把它带给模型（`AIService._inventory_prompt`）。
    "locations": [DEFAULT_LOCATION, *HOME_LOCATIONS],
}


logger = logging.getLogger(__name__)


def worn_since_date(days: int, today: date | None = None) -> str:
    """`N` 天前 → `YYYY-MM-DD`（"这件我穿了 3 天了" → 起始日）。"""
    return ((today or date.today()) - timedelta(days=int(days))).isoformat()


def worn_days(item: dict, today: date | None = None) -> int | None:
    """这件衣物**穿了几天**（从 `worn_since` 算）—— 没记返回 `None`。

    ⚠ 刻意**不存计数器**：计数器要有人记得每天 +1（漏一天就错），而且跨天/跨设备必错 ✗。
    存一个"从哪天开始穿"的日期，天数**每次算** ✓ —— 和 `runs_out_on` 同一个思路。
    """
    days = days_until(str(item.get("worn_since") or ""), today)
    return None if days is None else -days


def needs_wash_now(item: dict, today: date | None = None) -> bool:
    """这件衣物现在**该不该洗**（用户用例表第 13/22 条）。

    - 显式标了 `needs_wash` → 该洗 ✓（"我把那条床单换来用了"）
    - 或穿了 ≥ `wash_after_days` 天 → 该洗 ✓（阈值可配，跟着"穿够几天就洗"走）
    """
    if item.get("needs_wash"):
        return True
    limit = item.get("wash_after_days")
    if not limit:
        return False
    days = worn_days(item, today)
    return days is not None and days >= int(limit)


def runs_out_date(months: int, today: date | None = None) -> str:
    """今天 + `months` 个月 → `YYYY-MM-DD`（**按 30 天/月近似**，够用且不引第三方库）。

    给"还能用半年 / 预估还能用一个月"用：**代码算日期**，不让模型做算术
    （用户用例表第 7/8 条）。
    """
    base = today or date.today()
    return (base + timedelta(days=int(months) * 30)).isoformat()


def apply_consume(item: dict, amount: int = 1) -> int:
    """扣 `amount` 个小单位（片 / 次），写回 `remaining_doses` + `quantity`，返回剩余片数。

    **唯一**的扣减算法：`InventoryModel.consume_doses()` 与 CLI 的 `consume` 命令都调它
    （审查 §6 第 6 条：CLI 与 Model 不要各写一份消耗）。老算法用整除换算盒数，
    1 盒 24 片用掉 1 片会变成 0 盒、**23 片凭空消失**（F1 / P1）。
    """
    left = max(0, InventoryModel.remaining_doses(item) - amount)
    item["remaining_doses"] = left
    InventoryModel.sync_units(item)
    return left


# 位置**同义说法**归一（用户用例表）：不同说法指同一个位置。
# ⚠ **只归一真正的同义词** —— 用户明确要求"衣柜 ≠ 柜子"，所以**不做**模糊/子串匹配。
# ⚠ 「外侧 / 外面 / 外边」按用户口径是**位置的位置**，写进 `notes`；这里归一它，
#    是为了让"搜外面"也能找到 notes 里写着"外侧"的东西（见 `lookup_item`）。
LOCATION_ALIASES = {
    "桌子": "桌面",
    "外面": "外侧", "外边": "外侧",
    # 用户口径：衣柜没说哪一侧一律算**左**
    "衣柜1": "衣柜左1", "衣柜2": "衣柜左2", "衣柜3": "衣柜左3", "衣柜4": "衣柜左4",
}


def canonical_location(name: str) -> str:
    """把位置的同义说法归一到规范名（未知说法原样返回）。"""
    value = (name or "").strip()
    return LOCATION_ALIASES.get(value, value)


class InventoryModel(BaseJsonModel):
    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_INVENTORY)

    def load(self) -> dict:
        """读盘后把**日期驱动的**状态按当前日期重算一遍（其余物品保持存下来的值）。

        状态随时间变的（**三种日期任一**：会员到期 / 保质期 / 预计用完），存下来的 `status`
        只是写入那一刻的快照 → 读盘时重算。
        ⚠ **只重算日期驱动的那些**：其余物品的 `status` 可能是用户用 `--status` 手动改过的，
        一刷新就被覆盖了（2026-10-18 被 `test_actions_smoke` 抓到的回归）。
        ⚠ 判据是"有没有日期"，不是"是不是会员" —— 否则顶层 `expires_on` / `runs_out_on`
        跨天不生效（2026-10-19 审查 R3）。
        """
        data = super().load()
        for it in self.items:
            if InventoryModel.has_time_status(it) and not it.get("ignore_low_stock"):
                it["status"] = InventoryModel.derive_status(it)
        return data

    @property
    def items(self) -> list[dict]:
        """全部物品（两边都在内）—— 界面按 `side_of()` 分边显示。"""
        return self._data.get("items", [])

    # ── 归属（学校 / 家）：由**位置**推导，不存字段 ──────────────
    @staticmethod
    def side_of(item: dict) -> str:
        """这条物品在**哪一边**：位置属于「家」那一侧 → `home`，否则 `school`。

        判断规则**只有这一处**（`HOME_LOCATIONS`）—— 界面切换、补货范围、命令回执都用它，
        免得"哪边算家"在多处各写一遍。
        """
        return SIDE_HOME if item.get("location") in HOME_LOCATIONS else SIDE_SCHOOL

    @staticmethod
    def remaining_doses(item: dict) -> int:
        """总余量（**小单位**：片 / 次）—— 库存的**精确真值**。

        ⚠ 老数据没有这个字段 → 用 `quantity × doses_per_unit` 现算（自愈，不写盘）。

        为什么必须有它：原来 `consume` 用整除把余量换回"盒"，1 盒 24 片用掉 1 片 →
        `23 // 24 = 0` 盒，**23 片凭空消失**（审查 F1 / P1）。
        """
        stored = item.get("remaining_doses")
        if isinstance(stored, int) and stored >= 0:
            return stored
        return int(item.get("quantity", 0)) * (item.get("doses_per_unit", 1) or 1)

    @staticmethod
    def sync_units(item: dict) -> None:
        """把精确余量换算回展示用的 `quantity`（盒数）；不足一盒时为 0。

        余量**不丢** —— 散片仍记在 `remaining_doses` 里（盒数只是展示换算）。
        """
        dpu = item.get("doses_per_unit", 1) or 1
        item["remaining_doses"] = InventoryModel.remaining_doses(item)
        item["quantity"] = item["remaining_doses"] // dpu

    @staticmethod
    def stock_parts(item: dict) -> tuple[int, int, int]:
        """库存的展示三元组 `(整包装数, 散装小单位, 每包装小单位)`。

        真值**只有 `remaining_doses` 一处** —— 展示一律从它推，**不许**再写
        `quantity × doses_per_unit`（2026-10-19 审查 R2：底层"扣 1 片丢 23 片"修好了，
        但界面 / `lookup_item` / AI 摘要各自重算 ✗ —— 1 盒 24 片扣 1 片仍显示成"0 盒"，
        用户和模型都以为没库存了 ✗）。
        """
        dpu = int(item.get("doses_per_unit", 1) or 1)
        total = InventoryModel.remaining_doses(item)
        return (total // dpu, total % dpu, dpu)

    @staticmethod
    def stock_text(item: dict) -> str:
        """**纯文本口径**（CLI / AI 摘要用；界面走 i18n + `stock_parts()`）。

        - 没分装：`3盒` / `2件`
        - 有分装：`0盒（剩 23 片）` —— 整包装为 0 时**必须**把散的说出来，
          否则读起来就是"没了" ✗（这正是 R2 的病灶）。
        """
        boxes, loose, dpu = InventoryModel.stock_parts(item)
        unit = str(item.get("unit") or "个")
        if dpu > 1 and loose:
            return f"{boxes}{unit}（剩 {loose} 片）"
        return f"{boxes}{unit}"

    def consume_doses(self, iid: str, amount: int = 1) -> int | None:
        """扣 `amount` 个**小单位**（片 / 次），返回剩余片数；找不到返回 `None`。

        **唯一**的扣减实现：CLI（`consume`）、界面、习惯扣减都走这里
        —— 审查 §6 第 6 条："CLI 与 Model 不要复制库存消耗"。
        """
        for it in self.items:
            if it["id"] == iid:
                left = apply_consume(it, amount)
                it["status"] = self.derive_status(it)
                it["updated_at"] = datetime.now().isoformat()
                return left
        return None

    @property
    def need_restock(self) -> list[dict]:
        """需要补货 / 续费的物品 —— **只看学校那一侧**，且**按当前日期重新推导状态**。

        家里的东西在这儿买不了，提醒了也没用（用户口径 2026-10-18）。

        ⚠ 必须用 `effective_status`（**重新推导**）：会员的"需购"来自**到期日**，而存下来的
        `status` 是写入那一刻的快照 —— 应用开着几天不动，快照就过期了。
        """
        return [it for it in self.items
                if self.side_of(it) == SIDE_SCHOOL
                and not it.get("ignore_low_stock")
                and self.effective_status(it) in ("需购", "不足")]

    @property
    def categories(self) -> list[str]:
        cats = self._data.get("categories")
        if not cats:
            # Repair: file created before categories key existed
            cats = list(DEFAULT_INVENTORY["categories"])
            self._data["categories"] = cats
        return cats

    def add_item(self, data: dict) -> str:
        items = self._data.setdefault("items", [])
        existing = set()
        for it in items:
            try:
                num = int(it["id"].split("_")[1])
                existing.add(num)
            except (KeyError, ValueError):
                logger.debug("InventoryModel.add_item 中忽略异常", exc_info=True)
        n = 1
        while n in existing:
            n += 1
        iid = f"i_{n:03d}"
        item = {
            "id": iid,
            "name": data.get("name", ""),
            "category": data.get("category", "其他"),
            "group": data.get("group", ""),
            "quantity": data.get("quantity", 1),
            "unit": "件",
            "status": data.get("status") or self.derive_status(data),
            "min_quantity": data.get("min_quantity", 1),
            "remaining_doses": int(data.get("quantity", 1)) * (data.get("doses_per_unit", 1) or 1),
            "location": data.get("location", ""),
            "notes": data.get("notes", ""),
            "tags": data.get("tags", []),
            "instances": data.get("instances", []),
            "ignore_low_stock": data.get("ignore_low_stock", False),
            "doses_per_unit": data.get("doses_per_unit", 1),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        # 上面只列了**有默认值**的字段；`ITEM_FIELDS` 里其余可写字段（`membership` /
        # `expires_on` / `runs_out_on` / `stock_target` / `worn_since` …）原样带上
        # —— 否则"带会员信息建一条"会**静默丢字段**（2026-10-19，见 `ITEM_FIELDS` 说明）。
        for key, value in data.items():
            if key in ITEM_FIELDS and key not in item:
                item[key] = value
        items.append(item)
        return iid

    @staticmethod
    def derive_status(item: dict, today: date | None = None) -> str:
        """推导状态：**会员按到期日**（有 `membership.expires_on` 时），其余按数量/片数。

        会员（用户口径 2026-10-18）：过期 → 需购（要续费）；`RENEW_WARNING_DAYS` 天内 →
        不足（要到期了）；否则充足（有效）。**自动续费开着也照常按到期日算** ——
        那个开关只是记着（你要知道它什么时候扣钱）。

        其余物品（`CODE_STANDARDS` 单一真值）：`quantity <= 0` → 需购；低于下限 → 不足；
        否则充足。两个下限同时给了**以片级为准**（`quantity × doses_per_unit < min_doses`）
        —— 它才对应"剩不到 5 片就提醒我买"（2026-10-18 探针发现的单位错位：
        `--min_qty 5` 是"5 盒"，与用户说的"5 片"差 24 倍）。

        **分件阈值（or 语义）**：`instances` 里某一"件"自己带了 `quantity` 就按它自己的下限
        算，**任意一件**告急 → 整条告急（用户用例表第 4 条："0.5 的笔芯 12 根、0.4 的 4 根，
        任意一种剩 2 根就提醒我补货"）。
        """
        status = (InventoryModel._membership_status(item, today)
                  or InventoryModel._expiry_status(item, today)
                  or InventoryModel._runs_out_status(item, today)
                  or InventoryModel._quantity_status(item))
        for inst in item.get("instances") or []:
            if isinstance(inst, dict):
                status = InventoryModel._worse(status,
                                               InventoryModel.instance_status(inst, item))
        return status

    @staticmethod
    def instance_status(instance: dict, item: dict) -> str:
        """**单件**的状态：它自己带了 `quantity` 就按它算（可覆盖整条的下限），否则跟整条一致。"""
        if instance.get("quantity") is None:
            return InventoryModel._quantity_status(item)
        merged = {**item, **instance}
        merged.pop("remaining_doses", None)   # ⚠ 整条的余量别串到单件上
        return InventoryModel._quantity_status(merged)

    @staticmethod
    def _worse(a: str, b: str) -> str:
        """取更严重的状态（需购 > 不足 > 充足）—— 分件阈值是 **or** 语义。"""
        order = {"充足": 0, "不足": 1, "需购": 2}
        return a if order.get(a, 0) >= order.get(b, 0) else b

    @staticmethod
    def _membership_status(item: dict, today: date | None = None) -> str | None:
        """会员按到期日给状态；没有到期日（或日期解析不了）→ `None`，交给数量规则。"""
        expires_on = str(InventoryModel.membership_of(item).get("expires_on") or "")
        days = days_until(expires_on, today)
        if days is None:
            return None
        if days < 0:
            return "需购"
        return "不足" if days <= RENEW_WARNING_DAYS else "充足"

    @staticmethod
    def _runs_out_status(item: dict, today: date | None = None) -> str | None:
        """**预估用完日**（`runs_out_on`）驱动状态 —— 形状与会员到期日**完全一致**。

        用户用例表第 7/8 条："估算大约还能用半年 / 预估还能用一个月"。
        日期由**命令面**用 `--runs-out-months N` 算好存进来（**不让模型做日期算术**）。
        没有这个字段（或解析不了）→ `None`，交给数量规则。
        """
        days = days_until(str(item.get("runs_out_on") or ""), today)
        if days is None:
            return None
        if days < 0:
            return "需购"
        return "不足" if days <= RENEW_WARNING_DAYS else "充足"

    @staticmethod
    def _expiry_status(item: dict, today: date | None = None) -> str | None:
        """**保质期**（`expires_on`）驱动状态 —— 药品临期换新用（C 类第 5 项）。

        ⚠ `PLAN.md` P20 原来写的是"到保质期的 **3/4** 时提醒"，但**我们只有到期日、
        没有生产日期**，这个比例**算不出来** ✗。所以老实做成"**到期前 N 天**"
        （`remind_before_days`，默认 7），比假装精确更诚实。

        与 `runs_out_on` 的区别：那是"用完要补货"，这是"临期要换新" —— 机制相同，语义不同。
        """
        days = days_until(str(item.get("expires_on") or ""), today)
        if days is None:
            return None
        if days < 0:
            return "需购"
        lead = item.get("remind_before_days") or RENEW_WARNING_DAYS
        return "不足" if days <= int(lead) else "充足"

    @staticmethod
    def _quantity_status(item: dict) -> str:
        """按余量 / 片级下限 / 单位级下限给状态。

        ⚠ 顺序要紧：**先看余量是否为 0**，而且要用**精确余量**比 ——
        一盒用剩 23 片时 `quantity`（盒数）是 0，先判盒数就会误报"需购"（F1 的连带）。

        ⚠ 两个下限的**边界不同**（跟着用户说法走，用户用例表）：
        - `min_doses`（片级）："剩 **2 根时**提醒我补货" → **到 2 就算不足**（`<=`）
        - `min_quantity`（单位级）："剩**不到** 2 盒" → **低于**才算不足（`<`）
        - `stock_target`（**常备量**，P20 的另一条路）："剩常备量的 **1/4** 时提醒"
          → `left * 4 <= stock_target` 就算不足 ✓（它比 `min_quantity` 更好懂：
          "低于多少提醒"和"应该常备多少"本来就是两件事 ✗）
        """
        left = InventoryModel.remaining_doses(item)
        if left <= 0:
            return "需购"
        target = item.get("stock_target") or 0
        if target > 0:
            return "不足" if left * 4 <= int(target) else "充足"
        min_doses = item.get("min_doses", 0) or 0
        if min_doses > 0:
            return "不足" if left <= min_doses else "充足"
        return "不足" if item.get("quantity", 1) < item.get("min_quantity", 1) else "充足"

    @staticmethod
    def membership_of(item: dict) -> dict:
        """会员信息（用户名 / 到期日 / 自动续费 / 续费月数）；没有就空 dict。

        ⚠ 这里**不含手机号** —— 手机号在 `MembershipContactsModel`（私有文件）。
        """
        value = item.get("membership")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def has_time_status(item: dict) -> bool:
        """这条物品的状态**由日期驱动**吗（三种日期任一）。

        - 会员到期：`membership.expires_on`
        - 保质期：顶层 `expires_on`（药品临期换新）
        - 预计用完：顶层 `runs_out_on`（按时间估算补货）

        为什么三种都要算：`derive_status()` 早就支持这三种，但**入口**只认会员那一种
        （`load()` / `effective_status()`）—— 于是顶层日期**跨天不生效**：
        存盘状态"充足"、到期日已过时 `derive_status=需购` 而 `effective_status=充足`，
        界面 / AI / 每日提醒全部漏报（2026-10-19 审查 R3）。
        """
        if InventoryModel.membership_of(item).get("expires_on"):
            return True
        return bool(item.get("expires_on") or item.get("runs_out_on"))

    @staticmethod
    def effective_status(item: dict, today: date | None = None) -> str:
        """物品**当前**的状态（界面 / 提示词 / 补货都该用它，而不是裸读 `status`）。

        - **日期驱动的（三种日期任一）**：按日期重算 —— 存下来的 `status` 只是写入那一刻的
          快照，应用开着几天不动就过期了（"该续费了""该换新了"会漏掉）。
        - **其余**：用存下来的 `status` —— 用户可能用 `--status` 手动改过，
          不能被自动推导覆盖（2026-10-18 `test_actions_smoke` 抓到的回归）。

        ⚠ 判据必须是"**有没有日期**"而不是"是不是会员" —— 否则为了保住手动状态，
        会把**所有非会员**的自动状态一起冻住（R3 就是这么来的）。

        `ignore_low_stock` 是**显式豁免**（用户说"这条别自动改"）→ 日期驱动也不重算，
        原样返回存下来的 `status`（与 `load()` 同一口径）。
        """
        if InventoryModel.has_time_status(item) and not item.get("ignore_low_stock"):
            return InventoryModel.derive_status(item, today)
        return str(item.get("status") or InventoryModel.derive_status(item, today))

    @staticmethod
    def _apply_fields(it: dict, iid: str, data: dict) -> None:
        """把 `ITEM_FIELDS` 里传入的字段写进物品；清单外的键**告警**（不默默吞 ✗）。

        ⚠ 告警块里同时做**真正的过滤**（不只是打日志）—— 门禁 `LOG-ONLY` 拦"块内唯一语句是日志"。
        """
        unknown = [k for k in data
                   if k not in ITEM_FIELDS
                   and k not in ("id", "created_at", "updated_at")]
        if unknown:
            logger.warning("update_item 忽略未知字段 %s（物品 %s）", unknown, iid)
            data = {k: v for k, v in data.items() if k in ITEM_FIELDS}
        for k in ITEM_FIELDS:
            if k in data:
                it[k] = data[k]

    def update_item(self, iid: str, data: dict) -> bool:
        for it in self.items:
            if it["id"] == iid:
                self._apply_fields(it, iid, data)
                it["updated_at"] = datetime.now().isoformat()
                # 数量 / 每份含量变了 → 由它们重算**精确余量**（用户填的 `quantity` 是盒数）
                if "quantity" in data or "doses_per_unit" in data:
                    dpu = it.get("doses_per_unit", 1) or 1
                    it["remaining_doses"] = int(it.get("quantity", 0)) * dpu
                self.sync_units(it)
                # 状态自动推导（`ignore_low_stock` 的物品跳过 —— 那是显式豁免）。
                # ⚠ 现在**也会回到"充足"**：补货之后不该还挂着"需购"（原来不清）
                if not it.get("ignore_low_stock"):
                    it["status"] = self.derive_status(it)
                return True
        return False

    def delete_item(self, iid: str) -> bool:
        items = self._data.get("items", [])
        for i, it in enumerate(items):
            if it["id"] == iid:
                items.pop(i)
                return True
        return False

    def consume(self, iid: str, amount: int = 1) -> bool:
        """Consume N doses. Returns True if item still has stock.

        ⚠ 保留这个方法只是为了兼容老调用点；真正的扣减逻辑在 `consume_doses()`
        （审查 §6：不要在 Model 与 CLI 各写一份消耗算法）。
        """
        left = self.consume_doses(iid, amount)
        return bool(left)

    @property
    def locations(self) -> list[str]:
        """允许的位置清单（用户定的固定格位 + 「学校」「家」）；键缺失就补一份（老文件没有）。"""
        locs = self._data.get("locations")
        if not locs:
            locs = list(DEFAULT_INVENTORY["locations"])
            self._data["locations"] = locs
        return locs

    @staticmethod
    def normalize_locations(values: list[str]) -> list[str]:
        """去空白 + 去重，保持传入顺序（命令层与界面共用同一套规则）。"""
        seen: list[str] = []
        for v in values:
            name = v.strip()
            if name and name not in seen:
                seen.append(name)
        return seen

    @property
    def all_tags(self) -> list[str]:
        tags = set()
        for it in self.items:
            for t in it.get("tags", []):
                tags.add(t)
        return sorted(tags)

    @property
    def stock_count(self) -> int:
        return len([it for it in self.items if it.get("status") == "充足"])
