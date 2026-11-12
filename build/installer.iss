; Nook installer. Build: build\build.ps1 (or ISCC build\installer.iss after PyInstaller).
; Per-user install: no admin prompt, lives in %LOCALAPPDATA%\Programs\Nook, data in %LOCALAPPDATA%\FocusOS.
; The app was called FocusOS before 1.1.1. AppId, AppMutex and the data folder keep the old name on purpose,
; so an old install upgrades in place (same folder, same data) instead of becoming a second app.

#define AppName "Nook"
#ifndef AppVersion
  #define AppVersion "0.0.0"   ; build.ps1 passes /DAppVersion from version.py
#endif

[Setup]
AppId={{6F1C2B7E-3D4A-4E59-9C1B-0F0C05000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Liyan Shanvel
AppPublisherURL=https://github.com/Liyan-Shanvel/Nook
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Nook-Setup-{#AppVersion}
SetupIconFile=focusos.ico
UninstallDisplayIcon={app}\Nook.exe
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
AppMutex=FocusOS_App_Mutex
CloseApplications=force
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Put Nook on the desktop"; Flags: unchecked
Name: "autostart"; Description: "Start Nook when Windows starts"

[InstallDelete]
; leftovers from when the app was called FocusOS
Type: files; Name: "{app}\FocusOS.exe"
Type: files; Name: "{userprograms}\FocusOS.lnk"
Type: files; Name: "{userdesktop}\FocusOS.lnk"
Type: files; Name: "{userstartup}\FocusOS.lnk"

[Files]
Source: "..\dist\Nook\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\Nook.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\Nook.exe"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\Nook.exe"; Parameters: "--hidden"; Tasks: autostart

[Run]
Filename: "{app}\Nook.exe"; Description: "Open Nook now"; Flags: nowait postinstall skipifsilent
; a self-update runs silent with /RELAUNCH: open the app again when done
Filename: "{app}\Nook.exe"; Flags: nowait; Check: Relaunch

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im Nook.exe /f"; Flags: runhidden; RunOnceId: "StopNook"

[UninstallDelete]
Type: files; Name: "{userstartup}\{#AppName}.lnk"

[Code]
function Relaunch: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/RELAUNCH') = 0 then Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im FocusOS.exe /f', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im Nook.exe /f', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;
