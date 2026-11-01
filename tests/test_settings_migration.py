"""旧「场景存档」位置 → 天气设置 的一次性迁移。

场景功能已弃用（2026-10-16）：位置改由 `settings.ini [Weather] lat/lon` 提供，
旧数据在 `data/scenes_meta.json` 的当前场景 `location{lat,lon}`。
"""

import json

from src.services.settings_manager import SettingsManager, migrate_legacy_scene_location


def _legacy(tmp_path, lat=30.25, lon=120.15, current="s1") -> None:
    (tmp_path / "scenes_meta.json").write_text(json.dumps({
        "current_scene": current,
        "scenes": {"s1": {"id": "s1", "name": "在校", "location": {"lat": lat, "lon": lon}}},
    }, ensure_ascii=False), encoding="utf-8")


def _settings(tmp_path) -> SettingsManager:
    s = SettingsManager(tmp_path / "settings.ini")
    s.load()
    return s


def test_migrates_location_from_legacy_scene(tmp_path) -> None:
    _legacy(tmp_path)
    s = _settings(tmp_path)

    assert migrate_legacy_scene_location(tmp_path, s) is True

    assert s.weather_lat == "30.25"
    assert s.weather_lon == "120.15"


def test_migration_is_idempotent(tmp_path) -> None:
    _legacy(tmp_path)
    s = _settings(tmp_path)
    migrate_legacy_scene_location(tmp_path, s)

    # 第二次不再改写，也不会用旧值覆盖用户后来改过的值
    s.weather_lat = "40.0"
    assert migrate_legacy_scene_location(tmp_path, s) is False
    assert s.weather_lat == "40.0"


def test_noop_without_legacy_file(tmp_path) -> None:
    s = _settings(tmp_path)
    assert migrate_legacy_scene_location(tmp_path, s) is False
    assert s.weather_lat == "31.23"        # 默认值


def test_noop_when_scene_has_no_location(tmp_path) -> None:
    (tmp_path / "scenes_meta.json").write_text(
        json.dumps({"current_scene": "s1", "scenes": {"s1": {"id": "s1"}}}), encoding="utf-8")
    s = _settings(tmp_path)
    assert migrate_legacy_scene_location(tmp_path, s) is False


def test_noop_on_broken_json(tmp_path) -> None:
    (tmp_path / "scenes_meta.json").write_text("{ not json", encoding="utf-8")
    s = _settings(tmp_path)
    assert migrate_legacy_scene_location(tmp_path, s) is False


def test_weather_service_location_follows_settings(tmp_path, qapp) -> None:
    """天气位置改由设置提供（原场景存档已删）。"""
    from src.services.weather_service import WeatherService

    s = _settings(tmp_path)
    s.weather_lat, s.weather_lon = "30.25", "120.15"

    assert WeatherService(s, data_dir=tmp_path).get_location() == "120.15,30.25"
    assert WeatherService(data_dir=tmp_path).get_location() == "121.47,31.23"
