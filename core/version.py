"""앱 버전과 배포 채널 정보.

여기의 __version__ 은 GitHub 릴리스 태그(v1.0.0)와 반드시 일치해야 한다.
릴리스 워크플로가 태그와 이 값을 비교해 다르면 빌드를 실패시킨다.
"""
from __future__ import annotations

__version__ = "1.0.1"

GITHUB_OWNER = "everside76"
GITHUB_REPO = "QuickSearch"

LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# 릴리스에 올라가는 실행 파일 이름
ASSET_NAME = "QuickSearch.exe"


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3', '1.2.3-beta' 등을 숫자 튜플로. 해석 못 한 자리는 0으로 둔다."""
    cleaned = text.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    """remote 버전이 local 보다 높으면 True."""
    a, b = parse_version(remote), parse_version(local)
    width = max(len(a), len(b))
    a += (0,) * (width - len(a))
    b += (0,) * (width - len(b))
    return a > b
