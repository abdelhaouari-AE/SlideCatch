; Inno Setup script for the SlideCatch installer.
; Built by the CI after the portable folder (dist\SlideCatch):
;   iscc /DAppVersion=0.3.1 installer\SlideCatch.iss
; Installs for the current user only (no administrator rights), in
; %LOCALAPPDATA%\Programs\SlideCatch. That folder can be written by the user,
; so the built-in "Update now" keeps working after installation.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E1C7B0A-3D52-4C7B-9F0E-5A1C2B7D9E41}
AppName=SlideCatch
AppVersion={#AppVersion}
AppPublisher=Abdelhalim EL HAOUARI
AppPublisherURL=https://github.com/abdelhaouari-AE/SlideCatch
DefaultDirName={localappdata}\Programs\SlideCatch
DefaultGroupName=SlideCatch
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SlideCatch-{#AppVersion}-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\SlideCatch.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\SlideCatch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SlideCatch"; Filename: "{app}\SlideCatch.exe"
Name: "{autodesktop}\SlideCatch"; Filename: "{app}\SlideCatch.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SlideCatch.exe"; Description: "{cm:LaunchProgram,SlideCatch}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; files left by the self-update (sessions and settings are kept)
Type: filesandordirs; Name: "{app}\updates"
Type: filesandordirs; Name: "{app}\_internal.old"
Type: files; Name: "{app}\SlideCatch.exe.old"
