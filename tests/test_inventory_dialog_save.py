"""保存被拒时**不许报成功** —— 2026-10-19 审查 R8 的回归。

病根：`edit_membership_dialog` / `edit_tags_dialog` 调 `dm.*.save()` 却**不看返回值** ✗ ——
磁盘被别人改过时保存会被拒（冲突检测），弹窗照常关闭、调用方照常发数据变化信号，
**用户看到内存里的新值，磁盘上没有** ✗。

本文件里 `email_reminder_dialog` 早就是正确写法（检查返回值 + 告警）✓ —— 这里把它推广到
另外两个弹窗，并用**桩**把保存打回 False 来测（审查要求"补库存冲突 / 私有文件冲突路径"）。
"""

from PySide6.QtWidgets import QDialog, QMessageBox

from src.services.data_manager import DataManager
from src.ui.panels.inventory_dialogs import edit_membership_dialog, edit_tags_dialog


def _accept_any_dialog(monkeypatch) -> None:
    """把模态 `exec()` 换成"直接确认"（测试里不跑模态循环）。"""
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)


def _capture_warnings(monkeypatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda _p, _t, text, *a, **k: seen.append(str(text)))
    return seen


def _member(dm: DataManager) -> dict:
    dm.inventory.add_item({"name": "网盘会员", "category": "虚拟品类", "quantity": 1})
    return dm.inventory.items[0]


def test_membership_dialog_stops_when_inventory_save_is_rejected(qapp, tmp_path,
                                                                 monkeypatch) -> None:
    """库存保存被拒 → 返回 False、有告警，而且**不再**去写私有文件。"""
    dm = DataManager(tmp_path)
    item = _member(dm)
    _accept_any_dialog(monkeypatch)
    monkeypatch.setattr(dm.inventory, "save", lambda: False)
    wrote_private = []
    monkeypatch.setattr(dm.membership_contacts, "save", lambda: wrote_private.append(1) or True)
    warned = _capture_warnings(monkeypatch)

    assert edit_membership_dialog(None, dm, item) is False
    assert warned, "保存失败必须告警"
    assert not wrote_private, "库存都没存上，不该接着写私有文件"


def test_membership_dialog_reports_half_success(qapp, tmp_path, monkeypatch) -> None:
    """私有文件保存被拒 = **部分成功** → 如实说，不当全成功。"""
    dm = DataManager(tmp_path)
    item = _member(dm)
    _accept_any_dialog(monkeypatch)
    monkeypatch.setattr(dm.membership_contacts, "save", lambda: False)
    warned = _capture_warnings(monkeypatch)

    assert edit_membership_dialog(None, dm, item) is False
    assert warned and "手机号" in warned[-1], warned


def test_membership_dialog_reports_success_when_both_saves_work(qapp, tmp_path,
                                                               monkeypatch) -> None:
    """两条保存都成功 → 正常返回 True（别把成功也当成失败）。"""
    dm = DataManager(tmp_path)
    item = _member(dm)
    _accept_any_dialog(monkeypatch)
    warned = _capture_warnings(monkeypatch)

    assert edit_membership_dialog(None, dm, item) is True
    assert not warned


def test_tags_dialog_stops_when_save_is_rejected(qapp, tmp_path, monkeypatch) -> None:
    dm = DataManager(tmp_path)
    dm.inventory.add_item({"name": "抽纸", "quantity": 2, "tags": ["常用"]})
    item = dm.inventory.items[0]
    _accept_any_dialog(monkeypatch)
    monkeypatch.setattr(dm.inventory, "save", lambda: False)
    warned = _capture_warnings(monkeypatch)

    assert edit_tags_dialog(None, dm, item) is False
    assert warned, "标签保存失败必须告警"
