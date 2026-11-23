"""P1：轮询发现外部改动要**按域**通知，而不是一律 `external`（审计 2026-11-21）。

审计原文：*"轮询用存在状态和 `st_mtime_ns` 等元数据做探针，**提交回执按域直接发通知**，
遇到不确定状态再比对内容"*。

`external` 的语义是"不知道改了什么" → 消费方只能**全刷**（所有面板重建），
每 3 秒一次的话开销很大。既然探针已经知道是哪个文件变了，就该发对应域名：
`tasks.json` → `task`，`expenses.json` → `expense` …（映射在 `DataManager` 里唯一登记）。
"""

import os

import pytest

from src.services.data_manager import DataManager

# 文件名 → 域名的**唯一映射**（新增模型必须同时加进这里与 `_models()`）
EXPECTED = {
    "courses": "course",
    "tasks": "task",
    "habits": "habit",
    "routines": "routine",
    "expenses": "expense",
    "daily_logs": "plan",
    "exams": "exam",
    "inventory": "inventory",
    "study": "study",
    "semesters": "semester",
}


def _external_events(dm: DataManager) -> list[str]:
    """记录**全部** `data_changed` 事件名（含 `external`）。"""
    events: list[str] = []
    dm.data_changed.connect(events.append)
    return events


@pytest.fixture
def dm(qapp, tmp_path) -> DataManager:
    manager = DataManager(tmp_path)
    manager._capture_mtimes()
    return manager


def test_each_touched_file_reports_its_own_domain(dm) -> None:
    """⭐ 只改 `tasks.json` → 只发 `task`（不再发 `external` 触发全刷）。"""
    events = _external_events(dm)
    dm.tasks.file_path.write_text(
        '{"_version": 2, "tasks": [{"id": "t_001", "title": "外部"}], "archived": []}',
        encoding="utf-8")

    dm._auto_reload()

    assert "task" in events, events
    assert "external" not in events, "已知域名的改动不该退化成全刷"


def test_several_files_report_all_their_domains(dm) -> None:
    """一次轮询里改了两个文件 → 两个域名都发（每个面板各刷一次）。"""
    events = _external_events(dm)
    dm.tasks.file_path.write_text(
        '{"_version": 2, "tasks": [], "archived": []}', encoding="utf-8")
    dm.expenses.file_path.write_text(
        '{"_version": 1, "categories": [], "budget": {}, "records": [], "finance": {}}',
        encoding="utf-8")

    dm._auto_reload()

    assert {"task", "expense"} <= set(events), events


def test_unknown_file_falls_back_to_blanket_refresh(dm, monkeypatch) -> None:
    """**不确定**的状态仍要保守：发 `external`（宁可全刷，也不能漏刷）。

    模拟"探针知道变了、但 `DOMAIN_OF` 里没有它"—— 新增模型忘登记时就是这个形状。
    """
    events = _external_events(dm)
    stamp = dm.tasks.file_path.stat().st_mtime_ns + 50_000_000   # 明确 +50ms
    dm.tasks.file_path.write_text(
        '{"_version": 2, "tasks": [], "archived": []}', encoding="utf-8")
    os.utime(dm.tasks.file_path, ns=(stamp, stamp))
    # 把真实模型的域名摘掉 → 走保守分支
    patched = {k: v for k, v in dm.DOMAIN_OF.items() if k != "tasks"}
    monkeypatch.setattr(type(dm), "DOMAIN_OF", patched)

    dm._auto_reload()

    assert "external" in events, events
    assert "task" not in events


def test_unchanged_poll_is_silent(dm) -> None:
    """没有任何改动 → **不**发事件（否则界面每 3 秒重建一次）。"""
    events = _external_events(dm)

    dm._auto_reload()

    assert events == [], events


def test_domain_map_covers_every_ui_visible_model(dm) -> None:
    """映射必须覆盖 `_models()` 里**界面可见**的每一项。

    `membership_contacts` 是私有手机号，只在会员弹窗里读，不进刷新链路 → 显式豁免。
    新增模型忘了登记时只会静默退化成全刷，所以这里逐个点名。
    """
    not_in_refresh_chain = {"membership_contacts"}
    names = {name for _model, name in dm._models()} - not_in_refresh_chain

    assert names <= set(EXPECTED), sorted(names - set(EXPECTED))
    assert names == set(dm.DOMAIN_OF)


def test_domain_map_uses_registered_event_names() -> None:
    """域名字符串必须都在 `EVENT_PANELS` 里登记（否则面板不认识）。"""
    from src.ui.components.main_workspace import EVENT_PANELS

    unknown = {domain for domain in DataManager.DOMAIN_OF.values()
               if domain not in EVENT_PANELS}
    assert not unknown, f"这些域名没有面板登记：{sorted(unknown)}"
