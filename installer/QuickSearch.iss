; QuickSearch 설치 프로그램 (Inno Setup 6)
;
; 빌드:
;   ISCC.exe /DMyAppVersion=1.0.3 installer\QuickSearch.iss
;
; 관리자 권한 없이 현재 사용자에게만 설치한다. 그래야 설치 폴더에 쓰기 권한이
; 있어서 앱이 스스로 업데이트할 수 있고, 설치·업데이트마다 UAC 창이 뜨지 않는다.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "QuickSearch"
#define MyAppExeName "QuickSearch.exe"
#define MyAppPublisher "everside76"
#define MyAppURL "https://github.com/everside76/QuickSearch"

[Setup]
; 이 GUID 는 절대 바꾸지 말 것 — 업그레이드 시 기존 설치를 찾는 기준이고,
; core/version.py 의 APP_ID 와 짝을 이뤄 '설치형인지' 판정에 쓰인다.
AppId={{8F3A7C21-5B4E-4C9A-9E2D-7A1B6C4D8E90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 설치 프로그램

PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

OutputDir=..\dist
OutputBaseFilename=QuickSearch-Setup-{#MyAppVersion}
SetupIconFile=..\assets\quicksearch.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; 업데이트 설치 시 실행 중인 QuickSearch 를 닫는다
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

[Languages]
; Korean.isl 은 Inno Setup 기본 배포에 없을 수 있어 있을 때만 등록한다
; (릴리스 워크플로가 공식 저장소에서 받아 넣는다)
#if FileExists(CompilerPath + "Languages\Korean.isl")
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Windows 시작 시 자동 실행"; GroupDescription: "추가 옵션"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 앱의 트레이 메뉴에 있는 자동 실행 토글과 같은 값을 쓴다(core/autostart.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "QuickSearch"; \
    ValueData: """{app}\{#MyAppExeName}"" --minimized"; \
    Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; 사람이 직접 설치할 때: 마지막 화면의 체크박스로 실행
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent
; 앱이 자동 업데이트로 조용히 재설치한 경우: 트레이 상주로 바로 되살린다
Filename: "{app}\{#MyAppExeName}"; Parameters: "--minimized"; \
    Flags: nowait; Check: WizardSilent

[UninstallDelete]
; 인덱스 캐시와 크래시 로그까지 정리한다
Type: filesandordirs; Name: "{localappdata}\QuickSearch"
