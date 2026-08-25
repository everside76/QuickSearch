"""릴리스 태그와 core/version.py 의 __version__ 이 같은지 확인한다.

앱 내부 업데이트 확인이 __version__ 을 기준으로 비교하므로, 태그와 어긋난 채
릴리스되면 사용자가 영영 업데이트 알림을 못 받거나 매번 받게 된다.

    python tools/check_version.py v1.0.0
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.version import __version__  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("사용법: python tools/check_version.py <태그>")
        return 2

    tag = argv[1].strip()
    expected = f"v{__version__}"
    if tag != expected:
        print(f"::error::태그({tag})와 core/version.py({expected})가 일치하지 않습니다.")
        return 1

    print(f"버전 확인 OK: {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
