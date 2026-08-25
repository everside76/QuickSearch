from __future__ import annotations

import os
import pickle
import time
import unicodedata
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, QThread, pyqtSignal


IndexEntry = tuple[str, str, bool, float]


def _cache_path() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    root = Path(base) if base else Path.home() / ".quicksearch"
    root = root / "quicksearch"
    root.mkdir(parents=True, exist_ok=True)
    # v2: 파일명을 NFC로 정규화하여 저장 (자모분리 파일 대응)
    return root / "index.v2.pkl"


def _default_roots() -> list[Path]:
    locations = [
        QStandardPaths.StandardLocation.DesktopLocation,
        QStandardPaths.StandardLocation.DocumentsLocation,
        QStandardPaths.StandardLocation.DownloadLocation,
        QStandardPaths.StandardLocation.PicturesLocation,
        QStandardPaths.StandardLocation.MoviesLocation,
        QStandardPaths.StandardLocation.MusicLocation,
    ]
    roots: list[Path] = []
    for loc in locations:
        path = QStandardPaths.writableLocation(loc)
        if path:
            p = Path(path)
            if p.exists() and p not in roots:
                roots.append(p)
    return roots


def _is_hidden(entry: os.DirEntry) -> bool:
    if entry.name.startswith("."):
        return True
    try:
        attrs = entry.stat(follow_symlinks=False).st_file_attributes
        return bool(attrs & 0x2 or attrs & 0x4)
    except (AttributeError, OSError):
        return False


def _walk(root: Path) -> list[IndexEntry]:
    out: list[IndexEntry] = []
    stack: list[str] = [str(root)]
    while stack:
        current = stack.pop()
        try:
            it = os.scandir(current)
        except (PermissionError, FileNotFoundError, OSError):
            continue
        with it:
            for entry in it:
                try:
                    if _is_hidden(entry):
                        continue
                    is_dir = entry.is_dir(follow_symlinks=False)
                    try:
                        mtime = entry.stat(follow_symlinks=False).st_mtime
                    except OSError:
                        mtime = 0.0
                    # NFC normalize so macOS/iCloud 자모분리(NFD) 파일명도 정상 표시/검색
                    name_nfc = unicodedata.normalize("NFC", entry.name)
                    path_nfc = unicodedata.normalize("NFC", entry.path)
                    out.append((name_nfc.lower(), path_nfc, is_dir, mtime))
                    if is_dir:
                        stack.append(entry.path)
                except OSError:
                    continue
    return out


class FileIndexer(QThread):
    indexReady = pyqtSignal(list)
    progress = pyqtSignal(str)

    def __init__(self, roots: list[Path] | None = None, parent=None):
        super().__init__(parent)
        self.roots = roots if roots is not None else _default_roots()
        self._cache_file = _cache_path()

    def _load_cache(self) -> list[IndexEntry] | None:
        try:
            if self._cache_file.exists():
                with self._cache_file.open("rb") as f:
                    data = pickle.load(f)
                if isinstance(data, list) and data and len(data[0]) == 4:
                    return data
        except (pickle.PickleError, OSError, EOFError):
            return None
        return None

    def _save_cache(self, entries: list[IndexEntry]) -> None:
        try:
            with self._cache_file.open("wb") as f:
                pickle.dump(entries, f, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError:
            pass

    def run(self) -> None:
        cached = self._load_cache()
        if cached is not None:
            self.progress.emit(f"캐시 로드: {len(cached):,}개 항목")
            self.indexReady.emit(cached)

        self.progress.emit("인덱싱 중...")
        started = time.perf_counter()
        entries: list[IndexEntry] = []
        for root in self.roots:
            entries.extend(_walk(root))
        elapsed = time.perf_counter() - started
        self.progress.emit(f"인덱싱 완료: {len(entries):,}개 · {elapsed:.1f}s")
        self.indexReady.emit(entries)
        self._save_cache(entries)
