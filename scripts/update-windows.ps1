[CmdletBinding()]
param(
    [string]$UaDir = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonVersion = "3.14",
    [string]$PythonPackageId = "Python.Python.3.14",
    [string]$PythonInstallDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\python\3.14"),
    [string]$LauncherDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\bin"),
    [string]$FfmpegPackageId = "Gyan.FFmpeg",
    [switch]$ForceUpdate,
    [switch]$SkipFfmpegInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail {
    param([string]$Message)
    throw $Message
}

$resolvedUaDir = [System.IO.Path]::GetFullPath($UaDir)
$gitDir = Join-Path $resolvedUaDir ".git"
$installScript = Join-Path $resolvedUaDir "scripts\install-windows.ps1"
$venvPython = Join-Path $resolvedUaDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $installScript)) {
    Fail "install-windows.ps1 was not found in $resolvedUaDir. Point -UaDir to a valid Upload Assistant checkout."
}

if (-not (Test-Path -LiteralPath $gitDir)) {
    Fail "This Upload Assistant directory is not a git checkout. ZIP-based installs cannot use 'ua-update'; download a fresh ZIP and rerun the installer instead."
}

$installArguments = @{
    UaDir = $resolvedUaDir
    PythonVersion = $PythonVersion
    PythonPackageId = $PythonPackageId
    PythonInstallDir = $PythonInstallDir
    LauncherDir = $LauncherDir
    FfmpegPackageId = $FfmpegPackageId
}

if ($ForceUpdate) {
    $installArguments.ForceUpdate = $true
}

if ($SkipFfmpegInstall) {
    $installArguments.SkipFfmpegInstall = $true
}

if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -m pip show discord.py *> $null
    if ($LASTEXITCODE -eq 0) {
        $installArguments.WithDiscord = $true
    }
}

& $installScript @installArguments
exit $LASTEXITCODE
