; Inno Setup Script for CAPEView
; Build: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" CAPEView_setup.iss
; Pass version on command line: ISCC.exe /dMyAppVersion=0.0.2 CAPEView_setup.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.0.1"
#endif
#define MyAppName "CAPEView"
#define MyAppPublisher "Process Logic Labs, LLC"
#define MyAppExeName "CAPEView.exe"
#define SourceDir "dist\CAPEView"

[Setup]
AppId={{C9E3D2A1-4F1B-4E7A-9C2D-7B8E5F1A0C2D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=CAPEView_Setup_{#MyAppVersion}
SetupIconFile=CAPEView\Resources\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\_internal\Resources\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\Resources\icon.ico"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\Resources\icon.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent runasoriginaluser shellexec

[Code]
var
  DbDirPage: TInputDirWizardPage;

procedure InitializeWizard;
begin
  DbDirPage := CreateInputDirPage(wpSelectDir,
    'CAPEView Database Location',
    'Where should CAPEView store its database file?',
    'Select the folder where the populated cape.db will be installed. The default is your local AppData folder. ' +
    'If you''re on the office LAN and want to share the database with other users, pick the shared CAPEView folder instead. ' +
    'You can change this later via File > Settings.',
    False, '');
  DbDirPage.Add('');
  DbDirPage.Values[0] := ExpandConstant('{localappdata}\CAPEView');
end;

function GetDbDir(Param: string): string;
begin
  Result := DbDirPage.Values[0];
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  SettingsPath: string;
  DbPath: string;
  Json: string;
  ExistingJson: AnsiString;
begin
  if CurStep = ssPostInstall then begin
    SettingsPath := ExpandConstant('{localappdata}\CAPEView\settings.json');
    // Idempotency guard: if a prior install already configured a DB path,
    // leave it alone (handles silent updates from auto_update.py correctly).
    if FileExists(SettingsPath) then begin
      if LoadStringFromFile(SettingsPath, ExistingJson) and
         (Pos('"database.path"', ExistingJson) > 0) then begin
        Exit;
      end;
    end;
    DbPath := AddBackslash(DbDirPage.Values[0]) + 'cape.db';
    // Escape backslashes for JSON
    StringChangeEx(DbPath, '\', '\\', True);
    Json := '{' + #13#10 + '  "database.path": "' + DbPath + '"' + #13#10 + '}';
    ForceDirectories(ExpandConstant('{localappdata}\CAPEView'));
    SaveStringToFile(SettingsPath, Json, False);
  end;
end;
