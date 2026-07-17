; Build input supplied by .github/workflows/windows-installer.yml:
; ..\build\payload\source, ..\build\payload\python-installer.exe, ..\build\payload\ffmpeg.zip, and ..\build\payload\wheels.
#define AppName "Upload Assistant"
#define AppVersion GetEnv("UA_VERSION")
#define AppPublisher "Upload Assistant"
#define AppURL "https://github.com/wastaken7/Upload-Assistant"

[Setup]
AppId={{1E1D3D95-529C-4D84-BDF3-8FE8F1C9A4E1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={localappdata}\Programs\Upload Assistant
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\output
OutputBaseFilename=Upload-Assistant-Setup-{#AppVersion}-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\upload.py

[Tasks]
Name: "discord"; Description: "Install optional Discord notification support"; Flags: unchecked
Name: "configure"; Description: "Open the configuration wizard after installation"; Flags: checkedonce

[Files]
Source: "..\build\payload\source\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\build\payload\python-installer.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "..\build\payload\ffmpeg.zip"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "..\build\payload\wheels\*"; DestDir: "{tmp}\wheels"; Flags: recursesubdirs deleteafterinstall
Source: "install-bundled-windows.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\Upload Assistant Configuration"; Filename: "{app}\bin\ua-config.cmd"
Name: "{autoprograms}\Upload Assistant Command Prompt"; Filename: "{cmd}"; Parameters: "/k set PATH={app}\bin;%PATH% & title Upload Assistant"

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{tmp}\install-bundled-windows.ps1"" -InstallDir ""{app}"" -PythonInstaller ""{tmp}\python-installer.exe"" -FfmpegArchive ""{tmp}\ffmpeg.zip"" -Wheelhouse ""{tmp}\wheels"" {code:DiscordParameter}"; StatusMsg: "Installing Upload Assistant and its bundled tools (this may take a while)..."; Flags: waituntilterminated runhidden
Filename: "{app}\bin\ua-config.cmd"; Description: "Configure Upload Assistant now"; Flags: postinstall nowait skipifsilent unchecked; Tasks: configure

[Code]
function DiscordParameter(Param: String): String;
begin
  if WizardIsTaskSelected('discord') then
    Result := '-WithDiscord'
  else
    Result := '';
end;
