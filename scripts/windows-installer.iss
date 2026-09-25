; Inno Setup script. Build on Windows after PyInstaller:
;   ISCC.exe scripts\windows-installer.iss

#define AppVersion "1.0.3"

[Setup]
AppId={{A7B3E1C4-6D28-4F0A-9C55-1E2D8B7A4F10}
AppName=That's Not My Name
AppVersion={#AppVersion}
AppPublisher=That's Not My Name
DefaultDirName={autopf}\ThatsNotMyName
DefaultGroupName=That's Not My Name
OutputDir=..\dist
OutputBaseFilename=ThatsNotMyName-Setup
UninstallDisplayIcon={app}\ThatsNotMyName.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
WizardStyle=modern
SetupIconFile=..\build\app-icon.ico

[Files]
Source: "..\dist\ThatsNotMyName\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\That's Not My Name"; Filename: "{app}\ThatsNotMyName.exe"
Name: "{autodesktop}\That's Not My Name"; Filename: "{app}\ThatsNotMyName.exe"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2..."; Flags: waituntilterminated
Filename: "{app}\ThatsNotMyName.exe"; Description: "Launch That's Not My Name"; Flags: postinstall nowait skipifsilent
