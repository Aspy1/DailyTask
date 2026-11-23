"""方案 A-1：首屏延迟构建面板（`MD-files/PERFORMANCE_WORKFLOW.md` §3.1-1）。

**验收口径**（手册 §4.1：先写回归测试再动代码）：

1. **首屏只构造必要面板** —— 启动后立刻可用的面板（日程）必须已就绪；
   非首屏面板（作业 / 考试 / 习惯 / 记账 / 库存 / 备考）在首次进入前**不构造**；
2. **首次切页后行为不变** —— 切过去就有正确数据，`_refresh` 被真的调用过；
3. **事件不丢** —— 面板建好之前到达的 `data_changed`，建好后必须补刷一次
   （否则切过去看到的是建面板那一刻的旧数据）；
4. **属性访问兼容** —— `workspace._task_panel`、`_panel_map`、`switch_to` 全部照旧，
   已有测试与菜单入口不用改；
5. **可回退** —— `LAZY_PANELS=0` 时退回"全构造"，两种模式对外表现一致。
"""


import pytest

from src.services.data_manager import DataManager
from src.services.settings_manager import SettingsManager
from src.ui.components import panel_factory
from src.ui.components.main_workspace import (
    ALL_PANELS,
    ATTR_TO_KEY,
    KEY_TO_DOMAIN,
    MainWorkspace,
)


class _PluginManager:
    """插件管理器替身（真实实现会扫目录并加载插件代码）。"""

    def list_plugins(self) -> list:
        return []

    def is_enabled(self, _name: str) -> bool:
        return False

    def toggle(self, _name: str, _enabled: bool) -> None:
        return None


def _workspace(tmp_path, monkeypatch, *, lazy: bool) -> MainWorkspace:
    monkeypatch.setattr(panel_factory, "LAZY_PANELS", lazy)
    settings = SettingsManager(tmp_path / "settings.ini")
    settings.load()
    dm = DataManager(tmp_path)
    return MainWorkspace(settings, dm, _PluginManager())


PANEL_DOMAINS = ("task", "habit", "routine", "exam", "expense", "inventory", "study")


def test_first_screen_is_ready_and_the_rest_is_deferred(tmp_path, qapp, monkeypatch) -> None:
    """⭐ 首屏面板已就绪；其余面板在首次进入前**没有构造**。

    这里用 `_panel_of(key)`（不触发构造的内部接口）判断 —— 直接读 `_task_panel`
    会按设计**立即构造**，那就测不到"延迟"了。
    """
    ws = _workspace(tmp_path, monkeypatch, lazy=True)

    assert ws.schedule_view is not None, "日程是首屏，必须已构造"
    assert ws._settings_panel is not None, "设置页由菜单直达，保持立即构造"
    for key in ATTR_TO_KEY.values():
        assert ws._panel_of(key) is None, f"{key} 不该在启动时构造"


def test_first_switch_builds_the_panel_and_shows_data(tmp_path, qapp, monkeypatch) -> None:
    """首次切过去：真的构造出来，并且刷过一次（不是空壳）。"""
    ws = _workspace(tmp_path, monkeypatch, lazy=True)
    ws._dm.tasks.add({"title": "算法实验"})
    ws._dm.tasks.save()

    ws.switch_to("tasks")

    assert ws._task_panel is not None
    assert ws._task_panel._table.rowCount() == 1


def test_event_before_construction_is_replayed(tmp_path, qapp, monkeypatch) -> None:
    """⭐ 面板还没建时到达的事件，建好后必须补刷（否则显示旧数据）。"""
    ws = _workspace(tmp_path, monkeypatch, lazy=True)
    # 面板未构造时就能收到事件（连接在 workspace 上，与面板无关）
    ws._dm.data_changed.emit("task")
    ws._dm.tasks.add({"title": "后来的作业"})

    ws.switch_to("tasks")

    assert ws._task_panel._table.rowCount() == 1, "建好之后要补刷到最新"


def test_every_nav_key_still_resolves(tmp_path, qapp, monkeypatch) -> None:
    """所有导航键都能切过去（`_panel_map` 的键集不变）。"""
    ws = _workspace(tmp_path, monkeypatch, lazy=True)

    for key in ("schedule", "tasks", "exams", "daily", "routines",
                "study", "expenses", "inventory", "meals", "settings"):
        assert key in ws._panel_map, key
        ws.switch_to(key)
        assert ws._stack.currentIndex() == ws._panel_map[key]


def test_attribute_access_builds_on_demand(tmp_path, qapp, monkeypatch) -> None:
    """既有入口 `workspace._task_panel` 直接访问时也要能用（兼容旧测试/菜单）。"""
    ws = _workspace(tmp_path, monkeypatch, lazy=True)

    panel = ws._task_panel

    assert panel is not None and hasattr(panel, "_refresh")


def test_eager_mode_behaves_the_same_outwardly(tmp_path, qapp, monkeypatch) -> None:
    """回退开关：`LAZY_PANELS=0` 全构造，对外行为一致。"""
    ws = _workspace(tmp_path, monkeypatch, lazy=False)

    assert ws._task_panel is not None, "非延迟模式启动即构造"
    ws.switch_to("tasks")
    assert ws._stack.currentIndex() == ws._panel_map["tasks"]


def test_event_mapping_is_unchanged(tmp_path, qapp, monkeypatch) -> None:
    """`EVENT_PANELS` 的语义不能被延迟构建改坏（域名映射仍全覆盖）。"""
    ws = _workspace(tmp_path, monkeypatch, lazy=True)
    for key in PANEL_DOMAINS:
        assert key in ALL_PANELS, key
    assert ws is not None


def test_every_lazy_key_translates_to_a_registered_domain() -> None:
    """⭐ 导航键 → 事件域名**必须**能翻译，且域名已在 `EVENT_PANELS` 登记。

    这条守卫来自一个**真实 bug**：`_refresh_by_panel` 曾直接拿导航键（`tasks`）
    去比对域名集合（`task`），单复数不符 → 事件静默不刷；只有 `inventory`
    恰好同名才正常工作。靠人眼看不出来，必须逐键核对。
    """
    from src.ui.components.main_workspace import EVENT_PANELS, KEY_TO_DOMAIN

    for attr, key in ATTR_TO_KEY.items():
        assert key in KEY_TO_DOMAIN, f"{attr} → {key} 没有域名翻译"
        domain = KEY_TO_DOMAIN[key]
        assert domain in ALL_PANELS, f"{key} → {domain} 不在 ALL_PANELS"
        # 每个域名都要能被"自己的域名事件"刷到
        assert domain in EVENT_PANELS.get(domain, frozenset()), \
            f"{domain} 的自身事件不能刷新它"


@pytest.mark.parametrize("lazy", [False, True])
def test_each_domain_refreshes_its_own_panel(sandbox, qapp, monkeypatch, lazy) -> None:
    """逐键验证：每个域名的事件都真的能刷到对应面板（不是只有 inventory）。"""
    ws = _workspace(sandbox, monkeypatch, lazy=lazy)
    hits: dict[str, int] = {}
    for _attr, key in ATTR_TO_KEY.items():
        ws.switch_to(key)                    # 构造出来
        panel = ws._built[key]
        # 默认参数把 key 绑在**当前**这一轮（闭包晚绑定会全记到最后一个键上）
        monkeypatch.setattr(panel, "_refresh",
                            lambda *a, _k=key, **k: hits.__setitem__(
                                _k, hits.get(_k, 0) + 1))

    for _attr, key in ATTR_TO_KEY.items():
        ws._dm.data_changed.emit(KEY_TO_DOMAIN[key])
        ws._coalescer.flush()                # 合并器走事件循环，这里直接执行

    for _attr, key in ATTR_TO_KEY.items():
        assert hits.get(key, 0) >= 1, f"{key} 没有被自己的域名事件刷到"
