"""업데이트 확인 → 다운로드 → 교체까지의 사용자 흐름.

네트워크와 파일 교체 로직은 core.updater 에 있고, 여기서는 대화상자·진행률·
트레이 알림 같은 UI 만 담당한다.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QSystemTrayIcon, QWidget

from core.updater import (
    DownloadWorker,
    UpdateCheckWorker,
    UpdateError,
    UpdateInfo,
    apply_update,
    is_frozen,
)
from core.version import RELEASES_PAGE, __version__

# 자동 확인 간격 — 앱을 자주 켜도 하루 한 번만 조회한다
AUTO_CHECK_INTERVAL = timedelta(hours=24)
# 시작 직후에는 인덱싱이 바쁘므로 잠시 뒤에 확인한다
AUTO_CHECK_DELAY_MS = 5000

_NOTES_LIMIT = 1200


class UpdateManager(QObject):
    """트레이 메뉴의 '업데이트 확인'과 시작 시 자동 확인을 함께 처리한다."""

    quitRequested = pyqtSignal()

    def __init__(self, parent: QWidget, tray: QSystemTrayIcon | None = None) -> None:
        super().__init__(parent)
        self._parent = parent
        self._tray = tray
        self._settings = QSettings("QuickSearch", "QuickSearch")
        self._checker: UpdateCheckWorker | None = None
        self._downloader: DownloadWorker | None = None
        self._progress: QProgressDialog | None = None
        self._silent = False

    # ---- 진입점 ----
    def set_tray(self, tray: QSystemTrayIcon | None) -> None:
        self._tray = tray

    def check_now(self) -> None:
        """트레이 메뉴에서 호출. 결과를 항상 사용자에게 알린다."""
        self._start_check(silent=False)

    def schedule_auto_check(self) -> None:
        """앱 시작 시 1회 호출. 마지막 확인이 24시간 이내면 건너뛴다."""
        QTimer.singleShot(AUTO_CHECK_DELAY_MS, self._report_previous_failure)
        if not self._auto_check_due():
            return
        QTimer.singleShot(AUTO_CHECK_DELAY_MS, lambda: self._start_check(silent=True))

    def _report_previous_failure(self) -> None:
        """지난 실행에서 exe 교체가 실패했다면 알려준다.

        교체 스크립트는 앱이 죽은 뒤에 돌기 때문에 실패를 그 자리에서 알릴 수 없다.
        대신 로그를 남겨두고, 다음 실행 때 이 자리에서 확인한다.
        """
        log = Path(tempfile.gettempdir()) / "quicksearch-update-error.log"
        if not log.is_file():
            return
        try:
            log.unlink()
        except OSError:
            pass
        self._notify(
            "지난 업데이트가 적용되지 않았습니다",
            "새 버전으로 교체하지 못했습니다. 트레이 메뉴에서 다시 시도해 주세요.",
        )

    # ---- 확인 ----
    def _auto_check_due(self) -> bool:
        raw = self._settings.value("updates/last_check", "", type=str)
        if not raw:
            return True
        try:
            last = datetime.fromisoformat(raw)
        except ValueError:
            return True
        return datetime.now() - last >= AUTO_CHECK_INTERVAL

    def _start_check(self, silent: bool) -> None:
        if self._checker is not None and self._checker.isRunning():
            return
        if self._downloader is not None and self._downloader.isRunning():
            return

        self._silent = silent
        worker = UpdateCheckWorker(self)
        worker.updateFound.connect(self._on_update_found)
        worker.upToDate.connect(self._on_up_to_date)
        worker.failed.connect(self._on_check_failed)
        worker.finished.connect(self._clear_checker)
        self._checker = worker
        worker.start()

    def _clear_checker(self) -> None:
        self._settings.setValue("updates/last_check", datetime.now().isoformat(timespec="seconds"))
        self._checker = None

    def _on_up_to_date(self) -> None:
        if self._silent:
            return
        QMessageBox.information(
            self._parent,
            "업데이트 확인",
            f"이미 최신 버전입니다. (v{__version__})",
        )

    def _on_check_failed(self, message: str) -> None:
        if self._silent:
            return
        QMessageBox.warning(self._parent, "업데이트 확인 실패", message)

    def _on_update_found(self, info: UpdateInfo) -> None:
        if self._silent and self._settings.value("updates/skipped_version", "", type=str) == info.tag:
            return

        if not is_frozen():
            self._offer_manual_download(info)
            return

        box = QMessageBox(self._parent)
        box.setWindowTitle("새 버전 사용 가능")
        box.setIcon(QMessageBox.Icon.Information)
        size_note = f" ({info.size_mb:.1f} MB)" if info.size else ""
        box.setText(f"QuickSearch v{info.version} 이(가) 나왔습니다.{size_note}")
        box.setInformativeText(f"현재 버전: v{__version__}\n지금 내려받아 업데이트할까요?")
        if info.notes:
            box.setDetailedText(info.notes[:_NOTES_LIMIT])

        update_btn = box.addButton("지금 업데이트", QMessageBox.ButtonRole.AcceptRole)
        later_btn = box.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
        skip_btn = box.addButton("이 버전 건너뛰기", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(update_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked is update_btn:
            self._start_download(info)
        elif clicked is skip_btn:
            self._settings.setValue("updates/skipped_version", info.tag)
        elif clicked is later_btn:
            pass

    def _offer_manual_download(self, info: UpdateInfo) -> None:
        """소스 실행 중에는 자동 교체 대신 릴리스 페이지를 안내한다."""
        if self._silent:
            self._notify(f"QuickSearch v{info.version} 사용 가능", "트레이 메뉴에서 업데이트를 확인하세요.")
            return
        answer = QMessageBox.question(
            self._parent,
            "새 버전 사용 가능",
            f"QuickSearch v{info.version} 이(가) 나왔습니다. (현재 v{__version__})\n\n"
            "소스로 실행 중이라 자동 교체는 할 수 없습니다.\n릴리스 페이지를 열까요?",
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Open,
        )
        if answer == QMessageBox.StandardButton.Open:
            QDesktopServices.openUrl(QUrl(info.page_url or RELEASES_PAGE))

    # ---- 다운로드 ----
    def _start_download(self, info: UpdateInfo) -> None:
        progress = QProgressDialog(
            f"v{info.version} 내려받는 중...", "취소", 0, 100, self._parent
        )
        progress.setWindowTitle("업데이트")
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        worker = DownloadWorker(info, self)
        progress.canceled.connect(worker.cancel)
        worker.progress.connect(self._on_progress)
        worker.done.connect(self._on_downloaded)
        worker.failed.connect(self._on_download_failed)
        worker.finished.connect(self._close_progress)

        self._progress = progress
        self._downloader = worker
        worker.start()
        progress.show()

    def _on_progress(self, received: int, total: int) -> None:
        if self._progress is None:
            return
        if total > 0:
            self._progress.setMaximum(100)
            self._progress.setValue(int(received * 100 / total))
            self._progress.setLabelText(
                f"내려받는 중... {received / 1048576:.1f} / {total / 1048576:.1f} MB"
            )
        else:
            # 전체 크기를 모르면 무한 진행 표시
            self._progress.setMaximum(0)

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        self._downloader = None

    def _on_download_failed(self, message: str) -> None:
        self._close_progress()
        QMessageBox.warning(self._parent, "업데이트 실패", message)

    def _on_downloaded(self, path: str) -> None:
        self._close_progress()
        try:
            apply_update(path)
        except UpdateError as exc:
            QMessageBox.warning(self._parent, "업데이트 실패", str(exc))
            return

        QMessageBox.information(
            self._parent,
            "업데이트 준비 완료",
            "QuickSearch 를 종료하고 새 버전으로 교체합니다.\n잠시 후 자동으로 다시 실행됩니다.",
        )
        self._settings.remove("updates/skipped_version")
        self.quitRequested.emit()
        QApplication.quit()

    # ---- 보조 ----
    def _notify(self, title: str, body: str) -> None:
        if self._tray is not None and self._tray.isVisible():
            self._tray.showMessage(title, body, self._tray.icon(), 6000)
