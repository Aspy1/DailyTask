"""会员**手机号**（私有）：不进仓库、也不进 AI 提示词。

为什么要单独一个文件（用户口径 2026-10-18）：手机号是 PII，而 `inventory.json` 是
**会同步到 GitHub 的**（`git_sync.DATA_FILES`）—— 放在一起就会被推上去。所以拆出来：

- 本文件被 `.gitignore` 挡住（`data/private/`），并且登记在 `git_sync.PRIVATE_FILES`
  （"故意不同步"的清单）—— `tests/test_git_sync_scope.py` 要求每个数据模型要么在同步清单里、
  要么在私有清单里，且私有清单里的每一项都必须被 `.gitignore` 挡住；
- 它**不参与 AI 提示词**（`AIService._inventory_prompt` 只读 `inventory.json`），
  所以手机号也不会随对话发给模型服务商；
- 写入仍走模型 `save()`（原子写 + 冲突检测），与其它数据文件同一套。

⚠ 代价：换机器时这份**不会自动带过去**，需要重新录（这是"不进仓库"的必然结果）。
"""

from pathlib import Path

from src.models.base import BaseJsonModel

DEFAULT_CONTACTS = {"_version": 1, "contacts": {}}


class MembershipContactsModel(BaseJsonModel):
    """按物品 id 存手机号：`{"i_003": {"phone": "138..."}}`。

    存成"id → 小对象"而不是裸字符串，是为了以后还能挂别的私有字段（不改结构）。
    """

    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, DEFAULT_CONTACTS)

    def phone_of(self, iid: str) -> str:
        entry = self._data.get("contacts", {}).get(iid) or {}
        return str(entry.get("phone") or "")

    def set_phone(self, iid: str, phone: str) -> None:
        """记手机号；传空串 = **删掉这一条**（不留空壳）。"""
        contacts = self._data.setdefault("contacts", {})
        value = (phone or "").strip()
        if value:
            contacts[iid] = {"phone": value}
        else:
            contacts.pop(iid, None)
