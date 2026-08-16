[CmdletBinding()]
param(
    [string]$UaDir,
    [string]$PythonVersion = "3.14",
    [string]$PythonInstallDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\python\3.14"),
    [string]$LauncherDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\bin"),
    [string]$PythonDownloadBaseUrl = "https://www.python.org/ftp/python",
    [string]$RepositoryZipUrl = "https://github.com/wastaken7/Upload-Assistant/archive/refs/heads/development.zip",
    [string]$InstallerUrl = "https://raw.githubusercontent.com/wastaken7/Upload-Assistant/development/scripts/install-windows.ps1",
    [switch]$ForceUpdate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($UaDir)) {
    $UaDir = Split-Path -Parent $PSScriptRoot
}

function Fail {
    param([string]$Message)
    throw $Message
}

$resolvedUaDir = [System.IO.Path]::GetFullPath($UaDir)
$venvPython = Join-Path $resolvedUaDir ".venv\Scripts\python.exe"

$installArguments = @{
    UaDir = $resolvedUaDir
    PythonVersion = $PythonVersion
    PythonInstallDir = $PythonInstallDir
    LauncherDir = $LauncherDir
    PythonDownloadBaseUrl = $PythonDownloadBaseUrl
    RepositoryZipUrl = $RepositoryZipUrl
}

if ($ForceUpdate) {
    $installArguments.ForceUpdate = $true
}

$installerPath = Join-Path ([System.IO.Path]::GetTempPath()) ("UploadAssistantInstaller-" + [guid]::NewGuid().ToString("N") + ".ps1")
try {
    Invoke-WebRequest -UseBasicParsing -Uri $InstallerUrl -OutFile $installerPath
    & $installerPath @installArguments
    exit $LASTEXITCODE
}
finally {
    Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
}
