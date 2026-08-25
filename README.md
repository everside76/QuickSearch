# QuickSearch

삼성 갤럭시의 "퀵서치(파인더)" 스타일로 동작하는 Windows 데스크톱 파일 런처.

실행하면 화면 중앙에 둥근 검색창이 떠오르고, 입력과 동시에 파일/폴더 결과가 실시간으로 표시됩니다.

## 특징
- 프레임리스 + 반투명 다크 UI
- 사용자 홈의 주요 폴더(바탕화면, 문서, 다운로드, 사진, 동영상, 음악) 자동 인덱싱
- 150ms 디바운스 실시간 검색
- 재실행 시 캐시 인덱스 즉시 로드 후 백그라운드 재인덱싱
- Windows Shell 아이콘으로 파일 타입 식별
- 시스템 트레이 상주 — 창을 닫아도 트레이에 남고, 아이콘 클릭으로 다시 호출
- GitHub 릴리스 기반 자동 업데이트

## 설치

### 설치 프로그램 (권장)
[릴리스 페이지](https://github.com/everside76/QuickSearch/releases/latest)에서
`QuickSearch-Setup-x.y.z.exe` 를 받아 실행하세요.

- **관리자 권한이 필요 없습니다.** `%LOCALAPPDATA%\Programs\QuickSearch` 에 현재 사용자로만 설치됩니다.
- 시작 메뉴 바로가기가 만들어지고, 설치 중 바탕화면 아이콘과 자동 실행을 선택할 수 있습니다.
- 제거는 Windows 설정 → 앱 → QuickSearch 에서 합니다. 인덱스 캐시까지 함께 정리됩니다.
- 설치형은 앱이 스스로 업데이트합니다(아래 참고).

### 포터블
설치 없이 쓰려면 같은 릴리스의 `QuickSearch.exe` 를 받아 아무 폴더에나 두고 실행하세요.
USB 등에서 바로 쓸 수 있고, 역시 자동 업데이트가 동작합니다.

### 소스에서 실행
```powershell
pip install -r requirements.txt
python quicksearch.py
```

`--minimized` 옵션으로 실행하면 창 없이 트레이에만 상주합니다(자동 시작용).

## 키보드
| 키 | 동작 |
|----|------|
| 입력 | 실시간 검색 |
| ↑ / ↓ | 결과 이동 |
| Enter | 기본 앱으로 열고 트레이로 숨기기 |
| Ctrl+Enter | 탐색기에서 파일 위치 열고 트레이로 숨기기 |
| Esc | 트레이로 숨기기 |
| Ctrl+Q | 종료 |

## 창 닫기와 종료
창 오른쪽 위 **×** 버튼과 **Esc** 는 창을 트레이로 접기만 합니다. 검색 결과를 연
뒤에도 앱은 트레이에 남습니다. 완전히 끄려면 **트레이 메뉴의 종료** 또는 **Ctrl+Q**
를 사용하세요. 시스템 트레이를 쓸 수 없는 환경에서는 창을 되살릴 수단이 없으므로
× 가 종료로 동작합니다.

## 트레이 메뉴
- **검색창 열기** — 창을 다시 띄웁니다(트레이 아이콘 클릭도 동일)
- **Windows 시작 시 자동 실행** — 레지스트리 Run 키 등록/해제
- **업데이트 확인** — GitHub 릴리스에서 새 버전을 조회
- **종료**

## 아이콘
트레이·작업표시줄·exe 아이콘은 `assets/quicksearch.ico` 하나를 공유합니다.
디자인을 바꾸려면 `tools/make_icon.py` 를 수정하고 다시 생성하세요.

```powershell
pip install pillow
python tools/make_icon.py
```

16~256px 아홉 가지 해상도가 하나의 .ico 로 만들어집니다. 리소스가 없는 상태로
실행되더라도 [ui/app_icon.py](ui/app_icon.py) 가 같은 디자인을 코드로 그려 폴백합니다.

## 자동 업데이트
앱은 시작 후 잠시 뒤(하루 1회) GitHub 릴리스를 조회하고, 새 버전이 있으면 알립니다.
트레이 메뉴의 **업데이트 확인** 으로 즉시 조회할 수도 있습니다.

받는 파일은 지금 실행 중인 형태에 맞춰 자동으로 갈립니다.

| 실행 형태 | 받는 것 | 적용 방식 |
|----------|--------|----------|
| 설치형 | `QuickSearch-Setup-x.y.z.exe` | 앱 종료 후 설치 프로그램을 무음으로 실행해 덮어쓰고 재실행 |
| 포터블 | `QuickSearch.exe` | 앱 종료 후 실행 파일을 교체하고 재실행 |
| 소스 실행 | — | 릴리스 페이지를 열어줍니다 |

어느 쪽이든 함께 올라온 `.sha256` 으로 무결성을 검증한 뒤에 적용합니다. 설치형 판정은
설치 프로그램이 남긴 제거 레지스트리 키의 설치 경로와 현재 실행 파일 위치를 대조해서
하므로, 같은 PC 에 설치본과 포터블이 함께 있어도 각자 맞는 방식으로 갱신됩니다.

교체가 실패하면 `%TEMP%\quicksearch-update-error.log` 에 기록되고, 다음 실행 때
트레이 알림으로 알려줍니다.

## 릴리스 방법
버전은 `core/version.py` 의 `__version__` 하나가 기준입니다. 태그와 다르면
워크플로가 빌드를 실패시킵니다.

```powershell
# 1) core/version.py 의 __version__ 을 올린다 (예: 1.0.1)
# 2) 커밋 후 태그를 푸시하면 GitHub Actions 가 빌드·릴리스까지 처리한다
git commit -am "release: v1.0.1"
git tag v1.0.1
git push origin main --tags
```

[.github/workflows/release.yml](.github/workflows/release.yml) 이 windows 러너에서
PyInstaller 빌드 → Inno Setup 으로 설치 프로그램 생성 → 체크섬 → 릴리스 게시를 수행합니다.
릴리스에는 설치 프로그램과 포터블 exe 가 함께 올라갑니다.

## 로컬 빌드 (선택)
```powershell
pip install pyinstaller pillow
python tools/make_icon.py
pyinstaller --noconfirm QuickSearch.spec
```
빌드 후 `dist/QuickSearch.exe` 더블클릭으로 실행 가능.

설치 프로그램까지 만들려면 [Inno Setup 6](https://jrsoftware.org/isdl.php) 이 필요합니다.
```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.0.3 installer\QuickSearch.iss
```
결과물은 `dist/QuickSearch-Setup-1.0.3.exe` 입니다.

## 캐시 위치
`%LOCALAPPDATA%\QuickSearch\quicksearch\index.pkl`

삭제하면 다음 실행 시 전체 재인덱싱됩니다. 크래시 로그는 같은 폴더의 `crash.log` 에 쌓입니다.
