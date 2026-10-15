"""Simple plugin manager: scan ./plugins, load plugin.py, expose panels and enable/disable.

Plugin folder layout (per-plugin):
  plugins/<name>/
    IsOpen.able            # present -> enabled
    # or IsOpen.able.disable -> disabled
    plugin.py              # optional - defines `register(api)` to register panels
    manifest.json          # optional metadata

API available to plugins:
  api.register_panel(display_name: str, factory: Callable)

Factories should be callables accepting (settings, ai_service, data_manager, parent=None)
and returning a QWidget instance.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PluginInfo:
    name: str
    path: Path
    enabled: bool
    manifest: dict | None = None


class PluginManager:
    def __init__(self, plugins_dir: Path, settings, data_manager, app=None):
        self.plugins_dir = Path(plugins_dir)
        self.settings = settings
        self.data_manager = data_manager
        self.app = app

        self.plugins: dict[str, PluginInfo] = {}
        # panels cache: plugin_name -> list of (display_name, factory)
        # factories are not loaded until requested (lazy load)
        self.panels: dict[str, list] = {}
        # module cache to avoid re-importing repeatedly
        self._module_cache: dict[str, object] = {}

        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def scan_plugins(self) -> None:
        self.plugins.clear()
        for p in sorted(self.plugins_dir.iterdir()):
            if not p.is_dir():
                continue
            # detect IsOpen.able or IsOpen.able.disable
            isopen = None
            for candidate in (p / "IsOpen.able", p / "IsOpen.able.disable"):
                if candidate.exists():
                    isopen = candidate
                    break
            enabled = isopen is not None and isopen.name == "IsOpen.able"
            self.plugins[p.name] = PluginInfo(name=p.name, path=p, enabled=enabled)

    def load_plugins(self) -> None:
        """Scan plugins and clear cached panels. Do NOT import plugin code here.
        Importing plugin code is deferred until a panel is requested to reduce startup
        memory/time cost.
        """
        self.scan_plugins()
        self.panels.clear()
        self._module_cache.clear()

    def list_plugins(self) -> list[PluginInfo]:
        if not self.plugins:
            self.scan_plugins()
        return list(self.plugins.values())

    def _load_plugin_definitions(self, plugin_name: str) -> list:
        """Import plugin.py and return list of (display_name, factory).
        Caches the module to avoid repeated imports.
        """
        if plugin_name in self.panels:
            return self.panels[plugin_name]
        info = self.plugins.get(plugin_name)
        if not info:
            return []
        mod_path = info.path / "plugin.py"
        if not mod_path.exists():
            return []
        try:
            # import module under a stable name per plugin
            if plugin_name in self._module_cache:
                mod = self._module_cache[plugin_name]
            else:
                spec = importlib.util.spec_from_file_location(f"plugins.{plugin_name}.plugin", str(mod_path))
                mod = importlib.util.module_from_spec(spec)
                loader = spec.loader
                assert loader is not None
                loader.exec_module(mod)  # type: ignore
                self._module_cache[plugin_name] = mod

            regs: list = []

            class _API:
                def register_panel(self, display_name: str, factory: Callable):
                    regs.append((display_name, factory))

            if hasattr(mod, "register") and callable(mod.register):
                try:
                    mod.register(_API())
                # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
                except Exception:  # noqa: BLE001
                    regs.append(("<load error>", lambda *a, **k: None))
            if regs:
                self.panels[plugin_name] = regs
            return regs
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception:  # noqa: BLE001
            return []

    def is_enabled(self, plugin_name: str) -> bool:
        p = self.plugins.get(plugin_name)
        return bool(p and p.enabled)

    def enable(self, plugin_name: str) -> bool:
        p = self.plugins.get(plugin_name)
        if not p:
            return False
        isopen = p.path / "IsOpen.able.disable"
        good = p.path / "IsOpen.able"
        try:
            if isopen.exists():
                isopen.rename(good)
            elif not good.exists():
                # create the enable file
                good.write_text("")
            p.enabled = True
            self.load_plugins()
            return True
        # 边界捕获：本层已处理/记录，不允许异常向上逃逸（CODE_STANDARDS Q-I1）
        except Exception:  # noqa: BLE001
            return False

    def disable(self, plugin_name: str) -> bool:
        p = self.plugins.get(plugin_name)
        if not p:
            return False
        good = p.path / "IsOpen.able"
        dis = p.path / "IsOpen.able.disable"
        try:
            if good.exists():
                good.rename(dis)
            elif not dis.exists():
                dis.write_text("")
            p.enabled = False
            self.load_plugins()
            return True
        # 边界捕获：第三方/外部（插件代码、SMTP）异常不外逃（CODE_STANDARDS Q-I1）
        except Exception:  # noqa: BLE001
            return False

    def get_panels(self, plugin_name: str):
        if plugin_name in self.panels:
            return self.panels[plugin_name]
        # lazy load definitions
        return self._load_plugin_definitions(plugin_name)

    def create_panel(self, plugin_name: str, display_name: str, settings, ai_service, data_manager, parent=None):
        regs = self.get_panels(plugin_name)
        for disp, factory in regs:
            if disp == display_name:
                try:
                    return factory(settings, ai_service, data_manager, parent)
                # 边界捕获：第三方/外部（插件代码、SMTP）异常不外逃（CODE_STANDARDS Q-I1）
                except Exception:  # noqa: BLE001
                    return None
        return None
