[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InstallDir,

    [Parameter(Mandatory)]
    [string]$PythonInstaller,

    [Parameter(Mandatory)]
    [string]$FfmpegArchive,

    [Parameter(Mandatory)]
    [string]$Wheelhouse,

)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function ConvertTo-ProcessArgumentString {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $escapedArguments = foreach ($argument in $Arguments) {
        if ($argument -notmatch '[\s"]') {
            $argument
        }
        else {
            '"' + (($argument -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
        }
    }
    return [string]::Join(' ', $escapedArguments)
}

function Add-DirectoryToUserPath {
    param([Parameter(Mandatory)][string]$DirectoryPath)

    $resolvedDirectory = [System.IO.Path]::GetFullPath($DirectoryPath)
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathEntries = if ([string]::IsNullOrWhiteSpace($currentPath)) {
        @()
    }
    else {
        $currentPath.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries)
    }

    $alreadyPresent = $pathEntries | Where-Object {
        [System.StringComparer]::OrdinalIgnoreCase.Equals($_.TrimEnd('\\'), $resolvedDirectory.TrimEnd('\\'))
    } | Select-Object -First 1

    if (-not $alreadyPresent) {
        [Environment]::SetEnvironmentVariable("Path", ($pathEntries + $resolvedDirectory) -join ';', "User")
    }

    if (-not (($env:Path -split ';') | Where-Object {
        [System.StringComparer]::OrdinalIgnoreCase.Equals($_.TrimEnd('\\'), $resolvedDirectory.TrimEnd('\\'))
    } | Select-Object -First 1)) {
        $env:Path = "$env:Path;$resolvedDirectory"
    }
}

function Invoke-Process {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [Parameter(Mandatory)][string]$Description
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    if ($startInfo.PSObject.Properties.Name -contains 'ArgumentList') {
        foreach ($argument in $ArgumentList) {
            [void]$startInfo.ArgumentList.Add($argument)
        }
    }
    else {
        $startInfo.Arguments = ConvertTo-ProcessArgumentString -Arguments $ArgumentList
    }

    $process = [System.Diagnostics.Process]::Start($startInfo)
    try {
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "$Description failed with exit code $($process.ExitCode)."
        }
    }
    finally {
        $process.Dispose()
    }
}

function Test-PythonVersionMatch {
    param(
        [Parameter(Mandatory)][string]$PythonPath,
        [Parameter(Mandatory)][string]$ExpectedMinorVersion
    )

    if (-not (Test-Path -LiteralPath $PythonPath)) {
        return $false
    }

    try {
        $version = (& $PythonPath -c "import platform; print(platform.python_version())").Trim()
        return $version.StartsWith("$ExpectedMinorVersion.", [System.StringComparison]::Ordinal)
    }
    catch {
        return $false
    }
}

function Find-ExistingPython {
    param([Parameter(Mandatory)][string]$ExpectedMinorVersion)

    $versionDirectory = "Python" + ($ExpectedMinorVersion -replace '\.', '')
    $candidates = @(
        if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "Programs\Python\$versionDirectory\python.exe" }
        if ($env:ProgramFiles) { Join-Path $env:ProgramFiles "$versionDirectory\python.exe" }
        if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} "$versionDirectory\python.exe" }
    )

    foreach ($candidate in $candidates) {
        if (Test-PythonVersionMatch -PythonPath $candidate -ExpectedMinorVersion $ExpectedMinorVersion) {
            return $candidate
        }
    }

    return $null
}

function Write-Runner {
    param([Parameter(Mandatory)][string]$AppDirectory)

    $runnerPath = Join-Path $AppDirectory "run-ua.ps1"
    $runnerContents = @'
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$UploadArgs
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment not found at $venvPython. Re-run the Upload Assistant installer."
}

Set-Location $scriptDir
& $venvPython (Join-Path $scriptDir "upload.py") @UploadArgs
exit $LASTEXITCODE
'@

    Set-Content -LiteralPath $runnerPath -Value $runnerContents -Encoding ASCII
}

function Write-Launchers {
    param(
        [Parameter(Mandatory)][string]$AppDirectory,
        [Parameter(Mandatory)][string]$LauncherDirectory
    )

    New-Item -ItemType Directory -Path $LauncherDirectory -Force | Out-Null
    $escapedAppDirectory = $AppDirectory.Replace('"', '""')
    $launchers = @{
        "ua.cmd" = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$escapedAppDirectory\run-ua.ps1`" %*`r`nexit /b %errorlevel%`r`n"
        "ua-update.cmd" = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$escapedAppDirectory\scripts\update-windows.ps1`" -UaDir `"$escapedAppDirectory`" -PythonInstallDir `"$escapedAppDirectory\python`" -LauncherDir `"$escapedAppDirectory\bin`" -FfmpegInstallDir `"$escapedAppDirectory\ffmpeg`" %*`r`nexit /b %errorlevel%`r`n"
    }

    foreach ($launcher in $launchers.GetEnumerator()) {
        Set-Content -LiteralPath (Join-Path $LauncherDirectory $launcher.Key) -Value $launcher.Value -Encoding ASCII
    }
}

$resolvedInstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$pythonDir = Join-Path $resolvedInstallDir "python"
$pythonExe = Join-Path $pythonDir "python.exe"
$ffmpegDir = Join-Path $resolvedInstallDir "ffmpeg"
$venvDir = Join-Path $resolvedInstallDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$launcherDir = Join-Path $resolvedInstallDir "bin"
$resolvedWheelhouse = [System.IO.Path]::GetFullPath($Wheelhouse)

if (-not (Test-Path -LiteralPath (Join-Path $resolvedInstallDir "upload.py"))) {
    throw "Upload Assistant files are missing from $resolvedInstallDir."
}

if (-not (Test-Path -LiteralPath $resolvedWheelhouse)) {
    throw "Bundled Python dependency wheelhouse is missing from $resolvedWheelhouse."
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    if (Test-Path -LiteralPath $pythonDir) {
        Remove-Item -LiteralPath $pythonDir -Recurse -Force
    }

    Write-Step "Installing bundled Python"
    Invoke-Process -FilePath $PythonInstaller -Description "Bundled Python installation" -ArgumentList @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=0",
        "AssociateFiles=0",
        "Shortcuts=0",
        "Include_launcher=0",
        "Include_test=0",
        "SimpleInstall=1",
        "TargetDir=$pythonDir"
    )
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    $existingPython = Find-ExistingPython -ExpectedMinorVersion "3.14"
    if (-not $existingPython) {
        throw "Bundled Python did not create $pythonExe, and no compatible existing Python was found."
    }

    Write-Step "Using existing compatible Python at $existingPython"
    $pythonExe = $existingPython
}

if (-not (Test-Path -LiteralPath (Join-Path $ffmpegDir "bin\ffmpeg.exe"))) {
    if (Test-Path -LiteralPath $ffmpegDir) {
        Remove-Item -LiteralPath $ffmpegDir -Recurse -Force
    }

    $extractDir = Join-Path ([System.IO.Path]::GetTempPath()) ("UploadAssistantFfmpeg-" + [guid]::NewGuid().ToString("N"))
    try {
        Write-Step "Extracting bundled FFmpeg"
        Expand-Archive -LiteralPath $FfmpegArchive -DestinationPath $extractDir -Force
        $extractedRoot = Get-ChildItem -LiteralPath $extractDir -Directory | Select-Object -First 1 -ExpandProperty FullName
        if (-not $extractedRoot -or -not (Test-Path -LiteralPath (Join-Path $extractedRoot "bin\ffmpeg.exe"))) {
            throw "The bundled FFmpeg archive has an unexpected layout."
        }
        Move-Item -LiteralPath $extractedRoot -Destination $ffmpegDir
    }
    finally {
        Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Step "Creating virtual environment"
    Invoke-Process -FilePath $pythonExe -Description "Virtual environment creation" -ArgumentList @("-m", "venv", $venvDir)
}

Write-Runner -AppDirectory $resolvedInstallDir
Write-Launchers -AppDirectory $resolvedInstallDir -LauncherDirectory $launcherDir
Add-DirectoryToUserPath -DirectoryPath $launcherDir
Add-DirectoryToUserPath -DirectoryPath (Join-Path $ffmpegDir "bin")

Write-Step "Installing Upload Assistant dependencies"
Invoke-Process -FilePath $venvPython -Description "Bundled pip upgrade" -ArgumentList @("-m", "pip", "install", "--no-index", "--find-links", $resolvedWheelhouse, "--upgrade", "pip")
Invoke-Process -FilePath $venvPython -Description "Bundled base dependency installation" -ArgumentList @("-m", "pip", "install", "--no-index", "--find-links", $resolvedWheelhouse, "-r", (Join-Path $resolvedInstallDir "requirements.txt"))
Write-Step "Installation complete. Use the Web UI configuration editor before the first upload."
