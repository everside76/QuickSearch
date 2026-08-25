"""QuickSearch 앱/트레이 아이콘 로더.

assets/quicksearch.ico 를 우선 사용하고, 파일이 없거나 읽지 못하면 동일한
디자인을 QPainter 로 직접 그려 폴백한다. 덕분에 리소스가 누락된 상태로 배포돼도
Qt 기본 아이콘으로 떨어지지 않는다.

아이콘 원본을 다시 만들려면: python tools/make_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

ICON_RELPATH = Path("assets") / "quicksearch.ico"

# tools/make_icon.py 와 동일한 팔레트
_GRADIENT_TOP = QColor(91, 155, 255)
_GRADIENT_BOTTOM = QColor(30, 92, 214)
_GLASS = QColor(255, 255, 255, 48)

_FALLBACK_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

_cached: QIcon | None = None


def resource_root() -> Path:
    """PyInstaller onefile 이면 sys._MEIPASS, 아니면 프로젝트 루트."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else Path(__file__).resolve().parent.parent


def icon_path() -> Path:
    return resource_root() / ICON_RELPATH


def app_icon() -> QIcon:
    """트레이/창/작업표시줄에서 공통으로 쓰는 앱 아이콘."""
    global _cached
    if _cached is not None:
        return _cached

    path = icon_path()
    if path.is_file():
        icon = QIcon(str(path))
        if not icon.isNull() and icon.availableSizes():
            _cached = icon
            return _cached

    _cached = _drawn_icon()
    return _cached


def _drawn_icon() -> QIcon:
    icon = QIcon()
    for size in _FALLBACK_SIZES:
        icon.addPixmap(_render_pixmap(size))
    return icon


def _render_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        # 라운드 사각형 배경 + 세로 그라데이션
        gradient = QLinearGradient(0.0, 0.0, 0.0, float(size))
        gradient.setColorAt(0.0, _GRADIENT_TOP)
        gradient.setColorAt(1.0, _GRADIENT_BOTTOM)
        background = QPainterPath()
        background.addRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        painter.fillPath(background, QBrush(gradient))

        # 작은 크기에서는 선을 굵게, 렌즈를 크게 잡아 형태가 뭉개지지 않게 한다
        small = size <= 20
        stroke = max(1.0, size * (0.115 if small else 0.095))
        radius = size * (0.245 if small else 0.220)
        center = size * (0.405 if small else 0.420)

        pen = QPen(QColor(255, 255, 255), stroke)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush) if small else QBrush(_GLASS))
        painter.drawEllipse(QPointF(center, center), radius, radius)

        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        offset = (radius + stroke * 0.25) * 0.70710678
        painter.drawLine(
            QPointF(center + offset, center + offset),
            QPointF(size * 0.79, size * 0.79),
        )
    finally:
        painter.end()

    return pixmap
