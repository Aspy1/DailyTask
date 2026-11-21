"""Desktop gateway controls invoke the installed Hermes launcher."""

import json
import os
import sys
from pathlib import Path

from src.services.hermes_gateway import gateway_online, launch_gateway


def test_gateway_status_requires_matching_live_process(sandbox) -> None:
    from src.services.hermes_gateway import _running_process_birth

    state = sandbox / "gateway_state.json"
    birth = _running_process_birth(os.getpid())
    assert birth is not None
    record = {"pid": os.getpid(), "start_time": birth, "gateway_state": "running"}
    assert not gateway_online(sandbox)
    state.write_text(json.dumps(record), encoding="utf-8")
    assert gateway_online(sandbox)
    for change in ({"start_time": birth - 100}, {"pid": 0}, {"gateway_state": "starting"}):
        state.write_text(json.dumps(record | change), encoding="utf-8")
        assert not gateway_online(sandbox)
    state.write_text("{", encoding="utf-8")
    assert not gateway_online(sandbox)


def test_detached_qprocess_runs_child_with_hermes_home(qapp, tmp_path) -> None:
    from PySide6.QtTest import QTest

    from src.services.hermes_gateway import _start_detached

    output = tmp_path / "launched.txt"
    program = "import os; from pathlib import Path; Path('launched.txt').write_text(os.environ['HERMES_HOME'])"
    assert _start_detached(Path(sys.executable), ["-c", program], tmp_path)
    for _attempt in range(100):
        if output.exists() and output.stat().st_size:
            break
        QTest.qWait(25)
    assert Path(output.read_text()) == tmp_path


def test_gateway_start_and_restart_use_the_selected_home(tmp_path, monkeypatch) -> None:
    from src.services import hermes_gateway

    executable = tmp_path / "bin" / "hermes.exe"
    executable.parent.mkdir()
    executable.touch()
    calls = []
    monkeypatch.setattr(hermes_gateway, "_start_detached",
                        lambda *args: calls.append(args) or True)

    assert launch_gateway(tmp_path) == "launched"
    assert launch_gateway(tmp_path, restart=True) == "launched"
    assert calls == [
        (executable, ["gateway", "run"], tmp_path),
        (executable, ["gateway", "run", "--replace"], tmp_path),
    ]


def test_gateway_reports_a_missing_installation(tmp_path) -> None:
    assert launch_gateway(tmp_path) == "missing"


def test_settings_buttons_dispatch_without_creating_the_old_assistant(qapp, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QPushButton

    from src.services.data_manager import DataManager
    from src.services.settings_manager import SettingsManager
    from src.ui.main_window import MainWindow
    from src.ui.panels import settings_panel

    requests = []
    monkeypatch.setattr(settings_panel, "launch_gateway",
                        lambda *, restart: requests.append(restart) or "launched")
    window = MainWindow(SettingsManager(tmp_path / "settings.ini"), DataManager(tmp_path))
    try:
        assert not hasattr(window, "_ai_panel")
        assert not hasattr(window._sidebar, "_ai_btn")
        assert not hasattr(window._workspace.schedule_view, "_arrange_btn")
        window.findChild(QPushButton, "hermes_start").click()
        window.findChild(QPushButton, "hermes_restart").click()
        assert requests == [False, True]
    finally:
        window.shutdown()


def test_settings_gateway_status_refreshes_text_and_color(qapp, sandbox, monkeypatch) -> None:
    from PySide6.QtWidgets import QLabel

    from src.i18n.loader import tr
    from src.services.settings_manager import SettingsManager
    from src.ui.panels import settings_panel
    from src.ui.styles.theme import get_colors

    online = False
    monkeypatch.setattr(settings_panel, "gateway_online", lambda: online)
    panel = settings_panel.SettingsPanel(SettingsManager(sandbox / "settings.ini"))
    label = panel.findChild(QLabel, "hermes_connection")
    assert label.text() == tr("hermes.offline")
    assert get_colors()["fg_hint"] in label.styleSheet()

    online = True
    panel._hermes_status_timer.timeout.emit()
    assert label.text() == tr("hermes.online")
    assert get_colors()["green"] in label.styleSheet()

    online = False
    panel._hermes_status_timer.timeout.emit()
    assert label.text() == tr("hermes.offline")
