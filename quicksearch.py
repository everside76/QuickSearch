from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QAction, QFont, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

BASE_DIR = Path(__file__).resolve().parent
# When frozen by PyInstaller --onefile, bundled data lives in sys._MEIPASS.
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core import autostart
from core.indexer import FileIndexer
from core.searcher import Searcher
from core.version import __version__
from ui.app_icon import app_icon
from ui.search_window import SearchWindow
from ui.update_manager import UpdateManager


def load_stylesheet() -> str:
    qss_path = RESOURCE_DIR / "ui" / "styles.qss"
    try:
        return qss_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_tray(
    app: QApplication,
    window: SearchWindow,
    icon: QIcon,
    updates: UpdateManager,
) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip(f"QuickSearch v{__version__} — 클릭하여 검색창 열기")

    menu = QMenu()
    menu.setStyleSheet(
        "QMenu { font-family: '맑은 고딕'; font-size: 10pt; padding: 6px; }"
        "QMenu::item { padding: 6px 18px; border-radius: 6px; }"
        "QMenu::item:selected { background-color: #3478F6; color: white; }"
    )

    act_open = QAction("검색창 열기", menu)
    act_open.triggered.connect(window.show_and_focus)
    menu.addAction(act_open)

    menu.addSeparator()

    if autostart.is_supported():
        act_autostart = QAction("Windows 시작 시 자동 실행", menu)
        act_autostart.setCheckable(True)
        act_autostart.setChecked(autostart.is_enabled())

        def _toggle_autostart(checked: bool) -> None:
            ok = autostart.set_enabled(checked)
            # 레지스트리 갱신 실패 시 실제 상태로 되돌리기
            act_autostart.setChecked(autostart.is_enabled() if not ok else checked)

        act_autostart.toggled.connect(_toggle_autostart)
        menu.addAction(act_autostart)
        menu.addSeparator()

    act_update = QAction("업데이트 확인", menu)
    act_update.triggered.connect(updates.check_now)
    menu.addAction(act_update)

    act_version = QAction(f"버전 v{__version__}", menu)
    act_version.setEnabled(False)
    menu.addAction(act_version)

    menu.addSeparator()

    act_quit = QAction("종료", menu)
    act_quit.triggered.connect(window.request_quit)
    menu.addAction(act_quit)

    tray.setContextMenu(menu)

    def on_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if window.isVisible():
                window.hide_to_tray()
            else:
                window.show_and_focus()

    tray.activated.connect(on_activated)

    settings = QSettings("QuickSearch", "QuickSearch")

    def on_hidden_to_tray() -> None:
        # × 로 창을 접었을 때 앱이 종료된 줄 오해하지 않도록 최초 1회만 안내한다
        if settings.value("tray/hint_shown", False, type=bool):
            return
        settings.setValue("tray/hint_shown", True)
        tray.showMessage(
            "QuickSearch 는 트레이에서 계속 실행 중입니다",
            "아이콘을 클릭하면 다시 열리고, 우클릭 메뉴에서 종료할 수 있습니다.",
            icon,
            6000,
        )

    window.hiddenToTray.connect(on_hidden_to_tray)

    tray.show()
    return tray


def _set_app_user_model_id() -> None:
    """Windows 작업표시줄이 호스트(python.exe)가 아닌 QuickSearch 아이콘을 쓰게 한다."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("QuickSearch.App")
    except (AttributeError, OSError):
        pass


def main() -> int:
    _set_app_user_model_id()

    app = QApplication(sys.argv)
    app.setApplicationName("QuickSearch")
    # 창을 닫아도 앱 유지 (트레이 상주)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("맑은 고딕", 10))

    icon = app_icon()
    app.setWindowIcon(icon)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        # 트레이를 못 쓰는 환경에서는 창을 닫으면 종료되도록 폴백
        app.setQuitOnLastWindowClosed(True)

    start_minimized = "--minimized" in sys.argv[1:]

    searcher = Searcher()
    window = SearchWindow(searcher, load_stylesheet())
    window.setWindowIcon(icon)
    if start_minimized and QSystemTrayIcon.isSystemTrayAvailable():
        # 트레이에서만 기동 — 자동 시작 상황에 적합
        pass
    else:
        window.show()
        window.input.setFocus()

    # 종료 요청 배선
    window.quitRequested.connect(app.quit)

    updates = UpdateManager(window)
    updates.quitRequested.connect(app.quit)

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = build_tray(app, window, icon, updates)
        updates.set_tray(tray)
    window.set_tray_available(tray is not None)

    updates.schedule_auto_check()

    indexer = FileIndexer()

    def on_ready(entries):
        searcher.set_index(entries)
        window.set_index_ready(True)

    def on_progress(msg: str):
        window.set_status(msg)

    indexer.indexReady.connect(on_ready)
    indexer.progress.connect(on_progress)
    indexer.start()

    exit_code = app.exec()
    if tray is not None:
        tray.hide()
    return exit_code


def _install_crash_logger() -> None:
    """Log uncaught exceptions to %LOCALAPPDATA%\\QuickSearch\\quicksearch\\crash.log."""
    import traceback
    from PyQt6.QtCore import QStandardPaths

    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    root = Path(base) if base else Path.home() / ".quicksearch"
    root = root / "quicksearch"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    log_path = root / "crash.log"

    def _hook(exc_type, exc, tb):
        try:
            with log_path.open("a", encoding="utf-8") as f:
                traceback.print_exception(exc_type, exc, tb, file=f)
                f.write("\n" + "-" * 60 + "\n")
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


if __name__ == "__main__":
    _install_crash_logger()
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        import traceback
        from PyQt6.QtCore import QStandardPaths

        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        root = Path(base) if base else Path.home() / ".quicksearch"
        root = root / "quicksearch"
        try:
            root.mkdir(parents=True, exist_ok=True)
            with (root / "crash.log").open("a", encoding="utf-8") as f:
                traceback.print_exc(file=f)
                f.write("\n" + "-" * 60 + "\n")
        except OSError:
            pass
        raise
