"""settings.ini 的写入语义（ERRORS #044 的根治）。

旧实现每次 `save()` 都**整份写回内存副本** —— 运行中的应用每 60s 写一次
`last_reminder_check`，外部脚本改的 `AI.model` 几分钟后就被静默回滚。
现在只回写**改动过的键**，其余键以磁盘为准。
"""

import configparser
import time
from pathlib import Path

from src.services.settings_manager import SettingsManager


def _read(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    return parser


def test_first_run_writes_defaults(tmp_path) -> None:
    path = tmp_path / "settings.ini"
    SettingsManager(path)
    assert path.exists()
    parser = _read(path)
    assert parser.get("General", "language") == "zh-CN"


def test_save_preserves_external_changes(tmp_path) -> None:
    """⭐ 只回写脏键：外部改的 AI.model 不能被运行中的应用回滚。"""
    path = tmp_path / "settings.ini"
    settings = SettingsManager(path)

    # 外部脚本改了模型（模拟另一个进程）
    parser = _read(path)
    parser.set("AI", "model", "deepseek-v4.1-flash")
    with open(path, "w", encoding="utf-8") as f:
        parser.write(f)

    # 应用只改了 last_reminder_check 并保存
    settings.set("Email", "last_reminder_check", "2026-10-31T12:00:00")
    assert settings.save() is True

    parser = _read(path)
    assert parser.get("AI", "model") == "deepseek-v4.1-flash", "外部改动被回滚了"
    assert parser.get("Email", "last_reminder_check") == "2026-10-31T12:00:00"


def test_no_dirty_keys_means_no_write(tmp_path) -> None:
    path = tmp_path / "settings.ini"
    settings = SettingsManager(path)
    before = path.stat().st_mtime_ns
    time.sleep(0.01)
    assert settings.save() is False
    assert path.stat().st_mtime_ns == before


def test_setting_same_value_does_not_dirty(tmp_path) -> None:
    path = tmp_path / "settings.ini"
    settings = SettingsManager(path)
    before = path.stat().st_mtime_ns
    settings.set("General", "language", settings.get("General", "language"))
    assert settings.save() is False
    assert path.stat().st_mtime_ns == before


def test_percent_in_password_roundtrip(tmp_path) -> None:
    """授权码里带 `%`，默认的 BasicInterpolation 会抛异常（旧实现会保存失败）。"""
    path = tmp_path / "settings.ini"
    settings = SettingsManager(path)
    settings.set("Email", "smtp_pass", "ab%cd%ef")
    assert settings.save() is True
    assert SettingsManager(path).get("Email", "smtp_pass") == "ab%cd%ef"


def test_atomic_write_leaves_no_tmp(tmp_path) -> None:
    path = tmp_path / "settings.ini"
    settings = SettingsManager(path)
    settings.set("AI", "model", "x")
    settings.save()
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_file_is_quarantined_on_save(tmp_path) -> None:
    path = tmp_path / "settings.ini"
    path.write_text("[AI\nnot a config", encoding="utf-8")
    settings = SettingsManager(path)          # 读不出来 → 内存用默认值
    settings.set("AI", "model", "new-model")
    assert settings.save() is True

    backups = list(tmp_path.glob("settings.corrupt-*.ini"))
    assert backups, "坏文件必须留档，不能直接覆盖（密钥现场）"
    assert _read(path).get("AI", "model") == "new-model"


def test_load_discards_unsaved_changes(tmp_path) -> None:
    path = tmp_path / "settings.ini"
    settings = SettingsManager(path)
    settings.set("AI", "model", "unsaved")
    settings.load()
    assert settings.get("AI", "model") == "deepseek-chat"
