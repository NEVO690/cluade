; Inno Setup script for AVEN AI Desktop.
; Built by scripts/build_windows.ps1:  iscc /DAppVersion=1.0.0 installer\aven_ai.iss
;
; Installs per user (no administrator rights needed) into %LOCALAPPDATA%\Programs\AVEN AI,
; adds Start menu (and optional desktop) shortcuts and a normal Windows uninstaller.
; Conversations and downloaded models live in %APPDATA%\AVEN AI and are kept on uninstall.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
; Never change AppId: Windows uses it to recognise updates of the same app.
AppId={{D9A0DFCA-54E6-4292-BCF0-35ECB6C4BDC4}
AppName=AVEN AI
AppVersion={#AppVersion}
AppVerName=AVEN AI {#AppVersion}
AppPublisher=AVEN AI
VersionInfoVersion={#AppVersion}
VersionInfoProductName=AVEN AI Desktop
VersionInfoDescription=AVEN AI Desktop Setup
DefaultDirName={autopf}\AVEN AI
DefaultGroupName=AVEN AI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=AVEN-AI-Setup-{#AppVersion}
SetupIconFile=..\assets\aven.ico
UninstallDisplayIcon={app}\AVEN AI.exe
UninstallDisplayName=AVEN AI
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\AVEN AI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AVEN AI"; Filename: "{app}\AVEN AI.exe"
Name: "{autodesktop}\AVEN AI"; Filename: "{app}\AVEN AI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AVEN AI.exe"; Description: "{cm:LaunchProgram,AVEN AI}"; Flags: nowait postinstall skipifsilent
