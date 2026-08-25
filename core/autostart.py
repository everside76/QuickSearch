"""Windows 로그인 시 자동 시작 토글 (HKCU\\...\\Run).

관리자 권한 없이 현재 사용자 계정에서만 적용된다.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import winreg  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

APP_NAME = "QuickSearch"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _target_command() -> str:
    """부팅 시 실행할 명령 문자열. 경로에 공백이 있어도 동작하도록 따옴표 처리.

    --minimized 플래그를 붙여, 부팅 시에는 창을 띄우지 않고 트레이에만 상주한다.
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return f'"{exe}" --minimized'
    script = Path(sys.argv[0]).resolve()
    py = Path(sys.executable).resolve()
    pyw = py.with_name("pythonw.exe")
    runner = pyw if pyw.exists() else py
    return f'"{runner}" "{script}" --minimized'


def is_supported() -> bool:
    return winreg is not None and sys.platform.startswith("win")


def is_enabled() -> bool:
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _target_command())
        return True
    except OSError:
        return False


def disable() -> bool:
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def set_enabled(flag: bool) -> bool:
    return enable() if flag else disable()
