from __future__ import annotations

from pathlib import Path

from gow_monitor.ui.main_window import MainWindow


def test_async_connection_does_not_use_synchronous_loader(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    results_root = tmp_path / "results"
    results_root.mkdir()

    window = MainWindow()
    qtbot.addWidget(window)

    calls: list[tuple[str, Path | None]] = []

    def fail_sync_loader(*args, **kwargs):
        del args, kwargs
        raise AssertionError(
            "The async CLI connection must not call _load_monitor_data"
        )

    def record_connect(path):
        calls.append(("connect", Path(path).resolve()))

    def record_refresh():
        calls.append(("refresh", None))
        return True

    monkeypatch.setattr(
        window,
        "_load_monitor_data",
        fail_sync_loader,
    )
    monkeypatch.setattr(
        window.live_refresh,
        "connect_path",
        record_connect,
    )
    monkeypatch.setattr(
        window.live_refresh,
        "refresh_now",
        record_refresh,
    )

    window.connect_results_root_async(results_root)

    assert window._connected_path == results_root.resolve()
    assert window.run_selector.count() == 0
    assert window.run_selector.isEnabled() is False
    assert calls == [
        ("connect", results_root.resolve()),
        ("refresh", None),
    ]
    assert "Loading GOW artifacts" in (
        window.overview_page.chart_footer.text()
    )

    window.resource_monitor.stop()


def test_synchronous_connection_contract_remains_available(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    results_root = tmp_path / "results"
    results_root.mkdir()

    window = MainWindow()
    qtbot.addWidget(window)

    called = {"sync": False}

    original = window._load_monitor_data

    def record_sync_loader(path):
        called["sync"] = True
        return original(path)

    monkeypatch.setattr(
        window,
        "_load_monitor_data",
        record_sync_loader,
    )

    window.connect_results_root(results_root)

    assert called["sync"] is True

    window.live_refresh.stop()
    window.resource_monitor.stop()
