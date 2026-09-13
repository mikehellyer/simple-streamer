; Inno Setup script for Simple-Streamer.
; Built with: iscc packaging\windows\installer.iss
; Expects dist\Simple-Streamer\ (PyInstaller onedir output) to already
; exist, and the version passed in via /DAppVersion=x.y.z (the release
; workflow does this so the .iss file never has to be hand-edited per
; release).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Simple-Streamer"
#define RepoRoot AddBackslash(SourcePath) + "..\.."

[Setup]
AppId={{6C1B6E2E-6B3B-4C1C-9B9E-3F9E7F5E6C10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Mike Hellyer
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\Simple-Streamer.exe
OutputDir={#RepoRoot}\dist
OutputBaseFilename=Simple-Streamer-{#AppVersion}-Windows-Setup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#RepoRoot}\packaging\icons\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#RepoRoot}\dist\Simple-Streamer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Simple-Streamer.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Simple-Streamer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Simple-Streamer.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
