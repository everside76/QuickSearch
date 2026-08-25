from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import QFileInfo, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QFontMetrics, QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.searcher import SearchResult, Searcher


UI_FONT_FAMILY = "맑은 고딕"


class ElidedLabel(QLabel):
    """가용 폭에 맞춰 가운데(…)로 자동 생략되는 단일행 라벨."""

    def __init__(self, text: str = "", parent: QWidget | None = None,
                 mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle):
        super().__init__(parent)
        self._full_text = text
        self._mode = mode
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self._update_text()

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text
        self._update_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_text()

    def _update_text(self) -> None:
        fm = QFontMetrics(self.font())
        avail = max(0, self.width() - 4)
        elided = fm.elidedText(self._full_text, self._mode, avail)
        super().setText(elided)


class ResultItemWidget(QWidget):
    def __init__(self, icon: QIcon, name: str, path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 10, 4)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(30, 30))
        icon_label.setFixedSize(32, 32)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        text_wrap = QVBoxLayout()
        text_wrap.setContentsMargins(0, 0, 0, 0)
        text_wrap.setSpacing(1)

        name_label = ElidedLabel(name, mode=Qt.TextElideMode.ElideRight)
        name_label.setFont(QFont(UI_FONT_FAMILY, 11, QFont.Weight.DemiBold))
        name_label.setStyleSheet("color: #ffffff;")
        text_wrap.addWidget(name_label)

        path_label = ElidedLabel(path, mode=Qt.TextElideMode.ElideMiddle)
        path_label.setFont(QFont(UI_FONT_FAMILY, 9))
        path_label.setStyleSheet("color: rgba(235,235,245,160);")
        text_wrap.addWidget(path_label)

        layout.addLayout(text_wrap, 1)


class SearchWindow(QMainWindow):
    querySubmitted = pyqtSignal(str)
    quitRequested = pyqtSignal()

    def __init__(self, searcher: Searcher, stylesheet: str):
        super().__init__()
        self._searcher = searcher
        self._icon_provider = QFileIconProvider()
        self._index_ready = False
        self._force_quit = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(760, 520)

        root = QFrame(self)
        root.setObjectName("rootFrame")
        self.setCentralWidget(root)

        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 10)
        vbox.setSpacing(0)

        # 상단 타이틀바: 창을 끌어 이동, 우측에 최소화/종료 버튼
        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(36)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(16, 4, 8, 4)
        tb_layout.setSpacing(6)

        self._title_label = QLabel("QuickSearch")
        self._title_label.setObjectName("titleLabel")
        self._title_label.setFont(QFont(UI_FONT_FAMILY, 9))
        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch(1)

        self._btn_tray = QPushButton("−")
        self._btn_tray.setObjectName("trayButton")
        self._btn_tray.setFixedSize(28, 24)
        self._btn_tray.setToolTip("트레이로 숨기기 (Esc)")
        self._btn_tray.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_tray.clicked.connect(self.hide_to_tray)
        tb_layout.addWidget(self._btn_tray)

        self._btn_close = QPushButton("×")
        self._btn_close.setObjectName("closeButton")
        self._btn_close.setFixedSize(28, 24)
        self._btn_close.setToolTip("종료 (Ctrl+Q)")
        self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_close.clicked.connect(self.request_quit)
        tb_layout.addWidget(self._btn_close)

        self._title_bar = title_bar
        self._drag_pos = None
        vbox.addWidget(title_bar)
        # NOTE: installEventFilter는 self.input 등 다른 속성이 모두 생성된 뒤 호출한다.

        self.input = QLineEdit()
        self.input.setObjectName("searchInput")
        self.input.setPlaceholderText("검색어를 입력하세요")
        self.input.setFont(QFont(UI_FONT_FAMILY, 18))
        self.input.setMinimumHeight(64)
        self.input.installEventFilter(self)
        vbox.addWidget(self.input)

        self.status = QLabel("준비 중...")
        self.status.setObjectName("statusLabel")
        self.status.setFont(QFont(UI_FONT_FAMILY, 9))
        vbox.addWidget(self.status)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        vbox.addWidget(divider)

        self.results = QListWidget()
        self.results.setObjectName("resultList")
        self.results.setIconSize(QSize(30, 30))
        self.results.setFont(QFont(UI_FONT_FAMILY, 10))
        self.results.itemActivated.connect(self._on_activate)
        self.results.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.results.setUniformItemSizes(True)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        vbox.addWidget(self.results, 1)

        self.setStyleSheet(stylesheet)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._run_search)
        self.input.textChanged.connect(lambda _: self._debounce.start())

        # 모든 속성이 준비된 뒤에 이벤트 필터를 설치한다.
        self._title_bar.installEventFilter(self)

        self._center_on_screen()

    # ---- 트레이 / 종료 ----
    def hide_to_tray(self) -> None:
        self.hide()

    def show_and_focus(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.input.selectAll()

    def request_quit(self) -> None:
        self._force_quit = True
        self.quitRequested.emit()

    def closeEvent(self, event) -> None:
        # X 버튼이나 창 닫기 이벤트는 기본적으로 트레이로 숨김
        if self._force_quit:
            event.accept()
        else:
            event.ignore()
            self.hide_to_tray()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + int(geo.height() * 0.22)
        self.move(x, y)

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_index_ready(self, ready: bool) -> None:
        self._index_ready = ready
        if ready and self.input.text().strip():
            self._run_search()

    def _run_search(self) -> None:
        query = self.input.text()
        results = self._searcher.search(query)
        self._render_results(results)

    def _render_results(self, results: list[SearchResult]) -> None:
        self.results.clear()
        for res in results:
            info = QFileInfo(res.path)
            icon = self._icon_provider.icon(info)
            if icon.isNull():
                icon = self._icon_provider.icon(
                    QFileIconProvider.IconType.Folder if res.is_dir else QFileIconProvider.IconType.File
                )
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, res.path)
            item.setData(Qt.ItemDataRole.UserRole + 1, res.is_dir)
            widget = ResultItemWidget(icon, res.name, res.path)
            item.setSizeHint(QSize(0, 56))
            self.results.addItem(item)
            self.results.setItemWidget(item, widget)
        if self.results.count() > 0:
            self.results.setCurrentRow(0)

    def _selected(self) -> QListWidgetItem | None:
        items = self.results.selectedItems()
        if items:
            return items[0]
        if self.results.count() > 0:
            return self.results.item(0)
        return None

    def _on_activate(self, item: QListWidgetItem) -> None:
        self._open_item(item, reveal=False)

    def _open_item(self, item: QListWidgetItem, reveal: bool) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        is_dir = item.data(Qt.ItemDataRole.UserRole + 1)
        if not path:
            return
        if reveal:
            self._reveal_in_explorer(path, is_dir)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        QApplication.quit()

    def _reveal_in_explorer(self, path: str, is_dir: bool) -> None:
        try:
            if is_dir:
                os.startfile(path)
            else:
                subprocess.Popen(["explorer", f"/select,{path}"])
        except OSError:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def eventFilter(self, obj, event):
        # 초기화 중 이벤트가 들어올 수 있으므로 방어
        if not hasattr(self, "input"):
            return super().eventFilter(obj, event)
        # 타이틀바 드래그로 창 이동
        if obj is self._title_bar:
            et = event.type()
            if et == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if et == event.Type.MouseMove and self._drag_pos is not None \
                    and event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
            if et == event.Type.MouseButtonRelease:
                self._drag_pos = None
                return False

        if obj is self.input and event.type() == event.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_Escape:
                self.hide_to_tray()
                return True
            if key == Qt.Key.Key_Q and mods & Qt.KeyboardModifier.ControlModifier:
                self.request_quit()
                return True
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                count = self.results.count()
                if count == 0:
                    return True
                row = self.results.currentRow()
                if key == Qt.Key.Key_Down:
                    row = min(count - 1, row + 1) if row >= 0 else 0
                else:
                    row = max(0, row - 1) if row >= 0 else 0
                self.results.setCurrentRow(row)
                self.results.scrollToItem(self.results.currentItem())
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._selected()
                if item is not None:
                    reveal = bool(mods & Qt.KeyboardModifier.ControlModifier)
                    self._open_item(item, reveal=reveal)
                return True
        return super().eventFilter(obj, event)
