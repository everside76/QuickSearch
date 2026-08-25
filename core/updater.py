"""GitHub 릴리스 기반 자동 업데이트.

- 최신 릴리스를 GitHub API 로 조회해 현재 버전과 비교한다.
- 새 버전이 있으면 exe 를 내려받고 SHA-256 을 검증한 뒤,
  앱이 종료된 다음 파일을 교체·재실행하는 배치 스크립트를 남긴다.
- 소스(python quicksearch.py)로 실행 중일 때는 파일 교체가 무의미하므로
  릴리스 페이지를 열어주는 것으로 대체한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.version import (
    ASSET_NAME,
    LATEST_RELEASE_API,
    RELEASES_PAGE,
    SETUP_ASSET_PREFIX,
    UNINSTALL_KEY,
    __version__,
    is_newer,
)

try:
    import winreg  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Windows 전용
    winreg = None  # type: ignore[assignment]

_TIMEOUT = 15
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"QuickSearch/{__version__}",
    "X-GitHub-Api-Version": "2022-11-28",
}


@dataclass(frozen=True)
class UpdateInfo:
    """새 릴리스 한 건의 요약."""

    version: str          # 태그에서 v 를 뗀 버전 문자열
    tag: str
    notes: str
    download_url: str
    size: int
    sha256_url: str | None
    is_setup: bool = False   # 설치 프로그램이면 True, 포터블 exe 면 False
    page_url: str = RELEASES_PAGE

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)


class UpdateError(Exception):
    """업데이트 과정에서 사용자에게 보여줄 수 있는 오류."""


def parse_release(payload: dict, prefer_setup: bool | None = None) -> UpdateInfo | None:
    """GitHub 릴리스 JSON → UpdateInfo. 현재 버전 이하이거나 받을 게 없으면 None.

    prefer_setup 을 주지 않으면 지금 실행 중인 형태에 맞춰 고른다.
    설치형이면 설치 프로그램을, 포터블이면 단일 exe 를 우선한다.
    """
    tag = str(payload.get("tag_name") or "").strip()
    if not tag or payload.get("draft"):
        return None
    if not is_newer(tag):
        return None

    if prefer_setup is None:
        prefer_setup = is_installed()

    assets = payload.get("assets") or []
    exe = _pick_asset(assets, prefer_setup)
    if exe is None:
        return None

    exe_name = str(exe.get("name", "")).lower()
    checksum_url = None
    for asset in assets:
        if str(asset.get("name", "")).lower() == exe_name + ".sha256":
            checksum_url = asset.get("browser_download_url")
            break

    return UpdateInfo(
        version=tag.lstrip("vV"),
        tag=tag,
        notes=str(payload.get("body") or "").strip(),
        download_url=str(exe["browser_download_url"]),
        size=int(exe.get("size") or 0),
        sha256_url=checksum_url,
        is_setup=exe_name.startswith(SETUP_ASSET_PREFIX),
        page_url=str(payload.get("html_url") or RELEASES_PAGE),
    )


def _pick_asset(assets: list, prefer_setup: bool) -> dict | None:
    """릴리스 자산 중 내려받을 것 하나를 고른다."""
    setup = None
    portable = None
    other = None
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if not asset.get("browser_download_url") or not name.endswith(".exe"):
            continue
        if name.startswith(SETUP_ASSET_PREFIX):
            setup = setup or asset
        elif name == ASSET_NAME.lower():
            portable = portable or asset
        else:
            other = other or asset

    if prefer_setup:
        return setup or portable or other
    return portable or setup or other


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return response.read()


def is_frozen() -> bool:
    """PyInstaller 로 패키징된 exe 로 실행 중인지."""
    return bool(getattr(sys, "frozen", False))


def current_exe() -> Path:
    return Path(sys.executable).resolve()


def install_location() -> Path | None:
    """설치 프로그램이 기록한 설치 폴더. 설치된 적이 없으면 None."""
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallLocation")
    except OSError:
        return None
    text = str(value or "").strip().strip('"')
    return Path(text) if text else None


def is_installed() -> bool:
    """지금 도는 실행 파일이 '설치된 것'인지.

    설치 폴더가 아닌 곳에서 포터블 exe 를 돌리는 경우와 구분해야 한다.
    같은 PC 에 설치본과 포터블이 함께 있어도 각자 맞는 방식으로 갱신된다.
    """
    if not is_frozen():
        return False
    location = install_location()
    if location is None:
        return False
    try:
        return current_exe().parent == location.resolve()
    except OSError:
        return False


class UpdateCheckWorker(QThread):
    """최신 릴리스 조회. 결과는 시그널로만 전달한다."""

    updateFound = pyqtSignal(object)   # UpdateInfo
    upToDate = pyqtSignal()
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            payload = json.loads(_get(LATEST_RELEASE_API).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # 아직 릴리스가 하나도 없는 저장소
                self.upToDate.emit()
                return
            self.failed.emit(f"업데이트 서버 응답 오류 ({exc.code})")
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            self.failed.emit("네트워크에 연결할 수 없습니다.")
            return
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.failed.emit("업데이트 정보를 해석할 수 없습니다.")
            return

        info = parse_release(payload)
        if info is None:
            self.upToDate.emit()
        else:
            self.updateFound.emit(info)


class DownloadWorker(QThread):
    """새 exe 다운로드 + 체크섬 검증."""

    progress = pyqtSignal(int, int)    # 받은 바이트, 전체 바이트
    done = pyqtSignal(str)             # 내려받은 파일 경로
    failed = pyqtSignal(str)

    _CHUNK = 256 * 1024

    def __init__(self, info: UpdateInfo, parent=None) -> None:
        super().__init__(parent)
        self._info = info
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            target = _staging_path(self._info.is_setup)
        except OSError:
            self.failed.emit("임시 파일을 만들 수 없습니다.")
            return

        digest = hashlib.sha256()
        received = 0
        try:
            request = urllib.request.Request(self._info.download_url, headers=_HEADERS)
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                total = int(response.headers.get("Content-Length") or self._info.size or 0)
                with target.open("wb") as fh:
                    while True:
                        if self._cancelled:
                            raise UpdateError("사용자가 취소했습니다.")
                        chunk = response.read(self._CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        self.progress.emit(received, total)
        except UpdateError as exc:
            target.unlink(missing_ok=True)
            self.failed.emit(str(exc))
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            target.unlink(missing_ok=True)
            self.failed.emit("다운로드에 실패했습니다.")
            return

        if received == 0:
            target.unlink(missing_ok=True)
            self.failed.emit("받은 파일이 비어 있습니다.")
            return

        if not self._verify(digest.hexdigest()):
            target.unlink(missing_ok=True)
            self.failed.emit("파일 검증에 실패했습니다. 업데이트를 중단합니다.")
            return

        self.done.emit(str(target))

    def _verify(self, actual: str) -> bool:
        """릴리스에 .sha256 자산이 있으면 대조한다. 없으면 검증을 건너뛴다."""
        if not self._info.sha256_url:
            return True
        try:
            raw = _get(self._info.sha256_url).decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError, OSError):
            return True  # 체크섬을 못 받은 것으로 업데이트를 막지는 않는다
        return checksum_matches(raw, actual)


def checksum_matches(raw: str, actual: str) -> bool:
    """'<hash>' 또는 '<hash>  QuickSearch.exe' 형식의 체크섬 파일과 대조."""
    tokens = raw.strip().split()
    if not tokens:
        return False
    return tokens[0].strip().lower() == actual.strip().lower()


def _staging_path(is_setup: bool = False) -> Path:
    """받아둘 파일 경로. 교체 대상과 같은 드라이브를 우선한다.

    설치 프로그램은 어차피 실행만 하고 지울 것이므로 임시 폴더에 받는다.
    """
    if is_setup:
        fd, name = tempfile.mkstemp(prefix="QuickSearch-Setup-", suffix=".exe")
        os.close(fd)
        return Path(name)
    if is_frozen():
        beside = current_exe().parent / (ASSET_NAME + ".new")
        try:
            beside.parent.mkdir(parents=True, exist_ok=True)
            with beside.open("wb"):
                pass
            return beside
        except OSError:
            pass  # Program Files 등 쓰기 권한이 없으면 임시 폴더로
    fd, name = tempfile.mkstemp(prefix="QuickSearch-", suffix=".exe.new")
    os.close(fd)
    return Path(name)


# 이 배치는 반드시 순수 ASCII 로 유지한다.
#   - 비ASCII 문자를 넣으려면 chcp 로 코드페이지를 바꿔야 하는데, cmd 는 배치를
#     바이트 오프셋으로 읽기 때문에 실행 중 코드페이지가 바뀌면 파싱 위치를 잃는다.
#   - 그래서 경로·PID 는 파일에 박지 않고 명령행 인자로 넘긴다. 인자는 코드페이지를
#     타지 않으므로 한글이 섞인 경로도 안전하다.
#   - 외부 명령은 절대 경로로 부른다. Git/MSYS 가 PATH 앞에 있으면 find.exe 와
#     ping.exe 가 동명의 GNU 도구로 가려져 대기 루프가 무력화된다.
_SWAP_SCRIPT = """@echo off
setlocal
set "PID=%~1"
set "TARGET=%~2"
set "SOURCE=%~3"
set "SYS=%SystemRoot%\\System32"

rem 1) Wait for the running QuickSearch process to exit (about 30s max).
set /a TRIES=0
:wait
"%SYS%\\tasklist.exe" /fi "PID eq %PID%" /nh 2>nul | "%SYS%\\find.exe" "%PID%" >nul
if errorlevel 1 goto swap
set /a TRIES+=1
if %TRIES% GEQ 30 goto swap
"%SYS%\\ping.exe" -n 2 127.0.0.1 >nul
goto wait

rem 2) Replace the exe. A still-running exe stays locked, so retry a while.
:swap
set /a ATTEMPT=0
:trymove
move /y "%SOURCE%" "%TARGET%" >nul 2>&1
if not errorlevel 1 goto launch
set /a ATTEMPT+=1
if %ATTEMPT% GEQ 15 goto failed
"%SYS%\\ping.exe" -n 2 127.0.0.1 >nul
goto trymove

:failed
echo QuickSearch update failed: could not replace "%TARGET%".> "%TEMP%\\quicksearch-update-error.log"
exit /b 1

:launch
start "" "%TARGET%"
del "%~f0"
"""

# 설치형용. 앱이 종료되길 기다렸다가 설치 프로그램을 무음으로 돌린다.
# 앱 재실행은 설치 프로그램의 [Run] 항목(Check: WizardSilent)이 맡는다.
_INSTALL_SCRIPT = """@echo off
setlocal
set "PID=%~1"
set "SETUP=%~2"
set "SYS=%SystemRoot%\\System32"

rem 1) Wait for the running QuickSearch process to exit (about 30s max).
set /a TRIES=0
:wait
"%SYS%\\tasklist.exe" /fi "PID eq %PID%" /nh 2>nul | "%SYS%\\find.exe" "%PID%" >nul
if errorlevel 1 goto install
set /a TRIES+=1
if %TRIES% GEQ 30 goto install
"%SYS%\\ping.exe" -n 2 127.0.0.1 >nul
goto wait

:install
"%SETUP%" /SILENT /NORESTART /SUPPRESSMSGBOXES /LOG="%TEMP%\\quicksearch-setup.log"
if errorlevel 1 goto failed
del "%SETUP%" >nul 2>&1
del "%~f0"
exit /b 0

:failed
echo QuickSearch update failed: installer exited with an error. See "%TEMP%\\quicksearch-setup.log".> "%TEMP%\\quicksearch-update-error.log"
del "%SETUP%" >nul 2>&1
exit /b 1
"""


def apply_update(downloaded: str | Path, is_setup: bool = False) -> None:
    """받아둔 파일을 적용하는 스크립트를 띄운다. 호출 직후 앱을 종료해야 한다.

    설치형이면 설치 프로그램을 무음으로 돌리고, 포터블이면 exe 를 교체한다.
    어느 쪽이든 앱이 종료되기를 기다린 뒤에 진행한다.

    Raises:
        UpdateError: 소스 실행 중이거나 스크립트를 만들지 못한 경우.
    """
    if not is_frozen():
        raise UpdateError("소스로 실행 중에는 자동 교체를 할 수 없습니다.")

    source = Path(downloaded)
    if not source.is_file():
        raise UpdateError("내려받은 파일을 찾을 수 없습니다.")

    script = Path(tempfile.gettempdir()) / f"quicksearch-update-{os.getpid()}.bat"
    try:
        # ascii 로 쓰는 것이 계약이다 — 위 주석 참고
        script.write_text(_INSTALL_SCRIPT if is_setup else _SWAP_SCRIPT, encoding="ascii")
    except OSError as exc:
        raise UpdateError("업데이트 스크립트를 만들지 못했습니다.") from exc

    # CREATE_NO_WINDOW 만 준다. DETACHED_PROCESS 를 함께(또는 단독으로) 주면
    # 콘솔 없이 뜬 cmd 가 배치 파일을 찾지 못해 교체가 조용히 실패한다.
    # 부모(QuickSearch)가 종료돼도 이 자식 프로세스는 살아남는다.
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    if is_setup:
        args = [str(os.getpid()), str(source.resolve())]
    else:
        args = [str(os.getpid()), str(current_exe()), str(source.resolve())]

    try:
        subprocess.Popen(
            ["cmd", "/c", str(script), *args],
            creationflags=creation_flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError("업데이트 스크립트를 실행하지 못했습니다.") from exc
