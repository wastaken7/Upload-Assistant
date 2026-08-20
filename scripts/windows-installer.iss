; Build input supplied by .github/workflows/windows-installer.yml:
; ..\build\payload\source plus the offline Python runtime, wheelhouse, and FFmpeg archive.
#define AppName "Upload-Assistant"
#define AppVersion GetEnv("UA_VERSION")
#define AppPublisher "Upload-Assistant"
#define AppURL "https://github.com/wastaken7/Upload-Assistant"

[Setup]
AppId={{1E1D3D95-529C-4D84-BDF3-8FE8F1C9A4E1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
UninstallDisplayName={#AppName} {#AppVersion}
DefaultDirName={localappdata}\Programs\Upload-Assistant
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
OutputDir=..\build\output
OutputBaseFilename=Upload-Assistant-Setup-{#AppVersion}-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\logo.ico

[Files]
Source: "..\build\payload\source\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\build\payload\python-runtime.zip"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "..\build\payload\get-pip.py"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "..\build\payload\ffmpeg.zip"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "..\build\payload\wheels\*"; DestDir: "{tmp}\wheels"; Flags: recursesubdirs deleteafterinstall
Source: "install-bundled-windows.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Icons]
Name: "{group}\Upload Assistant WebUI"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\scripts\run-webui-tray.ps1"" -AppDir ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\logo.ico"
Name: "{group}\Upload Assistant Configuration"; Filename: "{app}\bin\ua-config.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\logo.ico"
Name: "{group}\Upload Assistant Command Prompt"; Filename: "{cmd}"; Parameters: "/k set PATH={app}\bin;%PATH% & title Upload Assistant"; WorkingDir: "{app}"; IconFilename: "{app}\logo.ico"
Name: "{autodesktop}\Upload Assistant WebUI"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\scripts\run-webui-tray.ps1"" -AppDir ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Messages]
FinishedHeadingLabel=Completing the [name] Setup Wizard
FinishedLabelNoIcons=Setup has finished installing [name] on your computer.%n%nAvailable commands (open a new terminal window):%n  ua%n  ua-config%n  ua-update%n  ua-webui
FinishedLabel=Setup has finished installing [name] on your computer.%n%nAvailable commands (open a new terminal window):%n  ua%n  ua-config%n  ua-update%n  ua-webui

[Code]
function NextButtonClick(CurPageID: Integer): Boolean;
var
  TestDir, TestFile: String;
begin
  Result := True;

  if CurPageID = wpSelectDir then
  begin
    TestDir := WizardDirValue;

    if not ForceDirectories(TestDir) then
    begin
      MsgBox('The selected directory could not be created.' + #13#10 + #13#10 +
             'Please choose a folder where you have write permissions (for example, in your user profile or another drive).', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    TestFile := AddBackslash(TestDir) + 'ua_perm_test.tmp';
    if not SaveStringToFile(TestFile, 'test', False) then
    begin
      MsgBox('The selected installation directory requires administrator privileges or is read-only.' + #13#10 + #13#10 +
             'Because this installer runs without elevated privileges, please choose a folder where you have write permissions (for example: ' + ExpandConstant('{localappdata}\Programs\Upload-Assistant') + ' or another drive).', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    DeleteFile(TestFile);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;

  if not Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\install-bundled-windows.ps1') + '" -InstallDir "' + ExpandConstant('{app}') + '" -PythonRuntimeArchive "' + ExpandConstant('{tmp}\python-runtime.zip') + '" -PipBootstrap "' + ExpandConstant('{tmp}\get-pip.py') + '" -Wheelhouse "' + ExpandConstant('{tmp}\wheels') + '" -FfmpegArchive "' + ExpandConstant('{tmp}\ffmpeg.zip') + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('Upload Assistant could not start its post-installation setup.', mbError, MB_OK);
    RaiseException('Post-installation setup could not be started.');
  end;

  if ResultCode <> 0 then
  begin
    MsgBox('Upload Assistant post-installation setup failed (exit code ' + IntToStr(ResultCode) + '). The installation may be incomplete; see install.log in the selected folder for details.', mbError, MB_OK);
    RaiseException('Post-installation setup failed with exit code ' + IntToStr(ResultCode) + '.');
  end;
end;
