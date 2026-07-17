[CmdletBinding()]
param(
    [string]$UaDir = (Join-Path $HOME "tools\ua"),
    [string]$PythonVersion = "3.14",
    [string]$PythonPackageId = "Python.Python.3.14",
    [string]$PythonInstallDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\python\3.14"),
    [string]$LauncherDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\bin"),
    [string]$FfmpegPackageId = "Gyan.FFmpeg",
    [switch]$WithDiscord,
    [switch]$ForceUpdate,
    [switch]$SkipFfmpegInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function Fail {
    param([string]$Message)
    throw $Message
}

function Invoke-WingetInstall {
    param(
        [Parameter(Mandatory)]
        [string]$PackageId,

        [Parameter(Mandatory)]
        [string]$Label,

        [string[]]$ExtraArgs = @(),

        [int]$TimeoutSeconds = 1800
    )

    $arguments = @(
        "install",
        "--id", $PackageId,
        "--exact",
        "--silent",
        "--accept-source-agreements",
        "--accept-package-agreements"
    ) + $ExtraArgs

    Write-Step "Installing $Label with winget"
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = "winget.exe"
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    foreach ($argument in $arguments) {
        [void]$startInfo.ArgumentList.Add($argument)
    }

    $wingetProcess = $null
    $stdoutHandler = $null
    $stderrHandler = $null

    try {
        $stdoutBuilder = [System.Text.StringBuilder]::new()
        $stderrBuilder = [System.Text.StringBuilder]::new()
        $wingetProcess = [System.Diagnostics.Process]::new()
        $wingetProcess.StartInfo = $startInfo

        $stdoutHandler = [System.Diagnostics.DataReceivedEventHandler]{
            param($sender, $eventArgs)
            if ($null -ne $eventArgs.Data) {
                [void]$stdoutBuilder.AppendLine($eventArgs.Data)
            }
        }
        $stderrHandler = [System.Diagnostics.DataReceivedEventHandler]{
            param($sender, $eventArgs)
            if ($null -ne $eventArgs.Data) {
                [void]$stderrBuilder.AppendLine($eventArgs.Data)
            }
        }

        $wingetProcess.add_OutputDataReceived($stdoutHandler)
        $wingetProcess.add_ErrorDataReceived($stderrHandler)
        [void]$wingetProcess.Start()
        $wingetProcess.BeginOutputReadLine()
        $wingetProcess.BeginErrorReadLine()

        if (-not $wingetProcess.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                $wingetProcess.Kill()
                $wingetProcess.WaitForExit()
            }
            catch {
            }

            Fail "winget timed out while installing $Label after $TimeoutSeconds seconds (package: $PackageId)"
        }

        $wingetProcess.WaitForExit()

        if ($stdoutBuilder.Length -gt 0) {
            $stdoutBuilder.ToString().TrimEnd("`r", "`n") | Write-Host
        }

        if ($stderrBuilder.Length -gt 0) {
            $stderrBuilder.ToString().TrimEnd("`r", "`n") | Write-Host
        }

        if ($wingetProcess.ExitCode -ne 0) {
            Fail "winget failed while installing $Label (package: $PackageId)"
        }
    }
    finally {
        if ($null -ne $wingetProcess) {
            if ($null -ne $stdoutHandler) {
                $wingetProcess.remove_OutputDataReceived($stdoutHandler)
            }

            if ($null -ne $stderrHandler) {
                $wingetProcess.remove_ErrorDataReceived($stderrHandler)
            }

            $wingetProcess.Dispose()
        }
    }
}

function Resolve-CommandPath {
    param(
        [Parameter(Mandatory)]
        [string]$CommandName,

        [string[]]$CandidatePaths = @()
    )

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source)) {
        return $command.Source
    }

    foreach ($candidate in $CandidatePaths) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Ensure-Git {
    $gitCandidates = @(
        (Join-Path $env:ProgramFiles "Git\cmd\git.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Git\cmd\git.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Git\cmd\git.exe")
    )

    $gitExe = Resolve-CommandPath -CommandName "git.exe" -CandidatePaths $gitCandidates
    if ($gitExe) {
        return $gitExe
    }

    Invoke-WingetInstall -PackageId "Git.Git" -Label "Git"

    $gitExe = Resolve-CommandPath -CommandName "git.exe" -CandidatePaths $gitCandidates
    if (-not $gitExe) {
        Fail "Git was installed but git.exe could not be located. Reopen PowerShell or install Git manually."
    }

    return $gitExe
}

function Ensure-IsolatedPython {
    $pythonExe = Join-Path $PythonInstallDir "python.exe"
    if (Test-Path -LiteralPath $pythonExe) {
        $installedVersion = (& $pythonExe -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')").Trim()
        if ($installedVersion -eq $PythonVersion) {
            return $pythonExe
        }

        if (-not $ForceUpdate) {
            Fail "Existing isolated Python at $PythonInstallDir uses version $installedVersion; rerun with -ForceUpdate to replace it with Python $PythonVersion."
        }

        Write-Step "Removing isolated Python $installedVersion from $PythonInstallDir"
        Remove-Item -LiteralPath $PythonInstallDir -Recurse -Force
    }

    $pythonParent = Split-Path -Parent $PythonInstallDir
    New-Item -ItemType Directory -Path $pythonParent -Force | Out-Null

    $overrideArgs = @(
        "InstallAllUsers=0",
        "PrependPath=0",
        "AssociateFiles=0",
        "Shortcuts=0",
        "Include_launcher=0",
        "Include_test=0",
        "SimpleInstall=1",
        "TargetDir=`"$PythonInstallDir`""
    )

    Invoke-WingetInstall `
        -PackageId $PythonPackageId `
        -Label "Python $PythonVersion" `
        -ExtraArgs @(
            "--scope", "user",
            "--location", $PythonInstallDir,
            "--override", ($overrideArgs -join " ")
        )

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        Fail "winget completed, but the isolated Python install was not created at $PythonInstallDir. This usually means an existing managed Python install intercepted the package request."
    }

    return $pythonExe
}

function Ensure-Ffmpeg {
    if ($SkipFfmpegInstall) {
        return
    }

    $ffmpegCommand = Resolve-CommandPath -CommandName "ffmpeg.exe"
    if ($ffmpegCommand) {
        return
    }

    Invoke-WingetInstall -PackageId $FfmpegPackageId -Label "FFmpeg"
}

function Clone-OrUpdateRepo {
    param([Parameter(Mandatory)][string]$GitExe)

    $parentDir = Split-Path -Parent $UaDir
    if (-not [string]::IsNullOrWhiteSpace($parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }

    $gitDir = Join-Path $UaDir ".git"
    if (Test-Path -LiteralPath $gitDir) {
        Write-Step "Updating existing Upload Assistant checkout"
        & $GitExe -C $UaDir pull --ff-only
        if ($LASTEXITCODE -ne 0) {
            Fail "git pull failed"
        }
        return
    }

    $looksLikeCheckout = (Test-Path -LiteralPath (Join-Path $UaDir "upload.py")) -and
        (Test-Path -LiteralPath (Join-Path $UaDir "requirements.txt")) -and
        (Test-Path -LiteralPath (Join-Path $UaDir "scripts\install-windows.ps1"))

    if ($looksLikeCheckout) {
        Write-Step "Using existing Upload Assistant files in $UaDir"
        return
    }

    if (-not (Test-Path -LiteralPath $UaDir)) {
        Write-Step "Cloning Upload Assistant into $UaDir"
        & $GitExe clone https://github.com/wastaken7/Upload-Assistant.git $UaDir
        if ($LASTEXITCODE -ne 0) {
            Fail "git clone failed"
        }
        return
    }

    Fail "$UaDir already exists but is neither a git checkout nor a recognizable Upload Assistant checkout. Choose a different -UaDir or use an extracted Upload Assistant ZIP."
}

function Install-Dependencies {
    param([Parameter(Mandatory)][string]$PythonExe)

    $venvDir = Join-Path $UaDir ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    if ($ForceUpdate -and (Test-Path -LiteralPath $venvDir)) {
        Write-Step "Removing existing virtual environment"
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step "Creating virtual environment"
        & $PythonExe -m venv $venvDir
        if ($LASTEXITCODE -ne 0) {
            Fail "Failed to create virtual environment"
        }
    }
    else {
        $venvVersion = (& $venvPython -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')").Trim()
        if ($venvVersion -ne $PythonVersion) {
            if (-not $ForceUpdate) {
                Fail "Existing .venv uses Python $venvVersion; rerun with -ForceUpdate to recreate it for Python $PythonVersion."
            }

            Write-Step "Recreating virtual environment for Python $PythonVersion"
            Remove-Item -LiteralPath $venvDir -Recurse -Force
            & $PythonExe -m venv $venvDir
            if ($LASTEXITCODE -ne 0) {
                Fail "Failed to recreate virtual environment"
            }
        }
    }

    Write-Step "Upgrading pip"
    & $venvPython -m pip install -U pip
    if ($LASTEXITCODE -ne 0) {
        Fail "pip upgrade failed"
    }

    Write-Step "Installing Upload Assistant dependencies"
    & $venvPython -m pip install -r (Join-Path $UaDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Fail "Base dependency installation failed"
    }

    if ($WithDiscord) {
        Write-Step "Installing optional Discord dependencies"
        & $venvPython -m pip install -r (Join-Path $UaDir "requirements-discord.txt")
        if ($LASTEXITCODE -ne 0) {
            Fail "Discord dependency installation failed"
        }
    }
}

function Add-DirectoryToUserPath {
    param([Parameter(Mandatory)][string]$DirectoryPath)

    $resolvedDirectory = [System.IO.Path]::GetFullPath($DirectoryPath)
    New-Item -ItemType Directory -Path $resolvedDirectory -Force | Out-Null

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathEntries = @()
    if (-not [string]::IsNullOrWhiteSpace($currentPath)) {
        $pathEntries = $currentPath.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries)
    }

    $alreadyPresent = $pathEntries | Where-Object {
        try {
            [System.StringComparer]::OrdinalIgnoreCase.Equals(
                [System.IO.Path]::GetFullPath($_),
                $resolvedDirectory
            )
        }
        catch {
            $false
        }
    } | Select-Object -First 1

    if (-not $alreadyPresent) {
        $newPath = if ($pathEntries.Count -gt 0) {
            ($pathEntries + $resolvedDirectory) -join ';'
        }
        else {
            $resolvedDirectory
        }

        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    }

    if (-not (($env:Path -split ';') | Where-Object {
        try {
            [System.StringComparer]::OrdinalIgnoreCase.Equals(
                [System.IO.Path]::GetFullPath($_),
                $resolvedDirectory
            )
        }
        catch {
            $false
        }
    } | Select-Object -First 1)) {
        $env:Path = if ([string]::IsNullOrWhiteSpace($env:Path)) {
            $resolvedDirectory
        }
        else {
            "$env:Path;$resolvedDirectory"
        }
    }
}

function Write-Runner {
    $runnerPath = Join-Path $UaDir "run-ua.ps1"
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
    throw "Virtual environment not found at $venvPython. Re-run scripts/install-windows.ps1 first."
}

Set-Location $scriptDir
& $venvPython (Join-Path $scriptDir "upload.py") @UploadArgs
exit $LASTEXITCODE
'@

    Set-Content -LiteralPath $runnerPath -Value $runnerContents -Encoding ASCII
}

function Write-GlobalLauncher {
    New-Item -ItemType Directory -Path $LauncherDir -Force | Out-Null

    $launcherPs1Path = Join-Path $LauncherDir "ua.ps1"
    $launcherCmdPath = Join-Path $LauncherDir "ua.cmd"
    $updatePs1Path = Join-Path $LauncherDir "ua-update.ps1"
    $updateCmdPath = Join-Path $LauncherDir "ua-update.cmd"
    $launcherPs1Contents = @"
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = `$true)]
    [string[]]`$UploadArgs
)

& (Join-Path "$UaDir" "run-ua.ps1") @UploadArgs
exit `$LASTEXITCODE
"@
    $launcherCmdContents = @"
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0ua.ps1" %*
exit /b %errorlevel%
"@
    $updatePs1Contents = @"
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = `$true)]
    [string[]]`$UpdateArgs
)

& (Join-Path "$UaDir" "scripts\update-windows.ps1") @UpdateArgs
exit `$LASTEXITCODE
"@
    $updateCmdContents = @"
@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0ua-update.ps1" %*
exit /b %errorlevel%
"@

    Set-Content -LiteralPath $launcherPs1Path -Value $launcherPs1Contents -Encoding UTF8
    Set-Content -LiteralPath $launcherCmdPath -Value $launcherCmdContents -Encoding ASCII
    Set-Content -LiteralPath $updatePs1Path -Value $updatePs1Contents -Encoding UTF8
    Set-Content -LiteralPath $updateCmdPath -Value $updateCmdContents -Encoding ASCII
    Add-DirectoryToUserPath -DirectoryPath $LauncherDir
}

if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
    Fail "winget is required for this installer. Install Windows Package Manager first."
}

$GitExe = Ensure-Git
$PythonExe = Ensure-IsolatedPython
Ensure-Ffmpeg
Clone-OrUpdateRepo -GitExe $GitExe
Install-Dependencies -PythonExe $PythonExe
Write-Runner
Write-GlobalLauncher

$venvPythonPath = Join-Path $UaDir ".venv\Scripts\python.exe"
$launcherPs1Path = Join-Path $LauncherDir "ua.ps1"
$launcherCmdPath = Join-Path $LauncherDir "ua.cmd"
$updatePs1Path = Join-Path $LauncherDir "ua-update.ps1"
$updateCmdPath = Join-Path $LauncherDir "ua-update.cmd"

Write-Host ""
Write-Host "Installation complete."
Write-Host ""
Write-Host "Location:"
Write-Host "  $UaDir"
Write-Host ""
Write-Host "Isolated Python:"
Write-Host "  $PythonExe"
Write-Host ""
Write-Host "Run:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$UaDir\run-ua.ps1`" `"/path/to/content`" --trackers yourtracker"
Write-Host "  ua `"/path/to/content`" --trackers yourtracker"
Write-Host "  ua-update"
Write-Host ""
Write-Host "Global launcher:"
Write-Host "  $launcherPs1Path"
Write-Host "  $launcherCmdPath"
Write-Host "  $updatePs1Path"
Write-Host "  $updateCmdPath"
Write-Host ""
Write-Host "PATH note:"
Write-Host "  A new PowerShell or Command Prompt window may be required before 'ua' and 'ua-update' are available everywhere."
Write-Host ""
Write-Host "Optional next steps:"
Write-Host "  - Configure UA with: & `"$venvPythonPath`" `"$UaDir\config-generator.py`""
if (-not $WithDiscord) {
    Write-Host "  - Enable Discord later with: & `"$venvPythonPath`" -m pip install -r `"$UaDir\requirements-discord.txt`""
}
