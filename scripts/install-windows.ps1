[CmdletBinding()]
param(
    [string]$UaDir = (Join-Path $HOME "tools\ua"),
    [string]$PythonVersion = "3.14",
    [string]$PythonInstallDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\python\3.14"),
    [string]$LauncherDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\bin"),
    [string]$PythonDownloadBaseUrl = "https://www.python.org/ftp/python",
    [string]$RepositoryZipUrl = "https://github.com/wastaken7/Upload-Assistant/archive/refs/heads/development.zip",
    [switch]$ForceUpdate
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

function ConvertTo-ProcessArgumentString {
    param([string[]]$Arguments)

    [string[]]$escapedArguments = @(
        foreach ($argument in $Arguments) {
            if ($null -eq $argument) {
                '""'
                continue
            }

            if ($argument -notmatch '[\s"]') {
                $argument
                continue
            }

            '"' + (($argument -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
        }
    )

    return [string]::Join(' ', $escapedArguments)
}

function Invoke-ExternalProcess {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [Parameter(Mandatory)]
        [string]$Label,

        [string[]]$Arguments = @(),

        [int]$TimeoutSeconds = 1800
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    if ($startInfo.PSObject.Properties.Name -contains "ArgumentList") {
        foreach ($argument in $arguments) {
            [void]$startInfo.ArgumentList.Add($argument)
        }
    }
    else {
        $startInfo.Arguments = ConvertTo-ProcessArgumentString -Arguments $arguments
    }

    $process = $null
    $stdoutTask = $null
    $stderrTask = $null

    try {
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo

        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()

        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                $process.Kill()
                $process.WaitForExit()
            }
            catch {
            }

            Fail "$Label timed out after $TimeoutSeconds seconds"
        }

        $process.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()

        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            $stdout.TrimEnd("`r", "`n") | Write-Host
        }

        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            $stderr.TrimEnd("`r", "`n") | Write-Host
        }

        if ($process.ExitCode -ne 0) {
            Fail "$Label failed with exit code $($process.ExitCode)"
        }
    }
    finally {
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
}

function New-TemporaryDownloadPath {
    param(
        [Parameter(Mandatory)]
        [string]$FileName
    )

    $downloadDir = Join-Path ([System.IO.Path]::GetTempPath()) "UploadAssistantDownloads"
    New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
    return Join-Path $downloadDir $FileName
}

function Invoke-CompatibleWebRequest {
    param(
        [Parameter(Mandatory)]
        [string]$Url,

        [string]$DestinationPath
    )

    $requestParams = @{
        Uri = $Url
    }

    if ($PSVersionTable.PSVersion.Major -lt 6) {
        $requestParams.UseBasicParsing = $true
    }

    if ($DestinationPath) {
        $requestParams.OutFile = $DestinationPath
    }

    return Invoke-WebRequest @requestParams
}

function Invoke-DownloadFile {
    param(
        [Parameter(Mandatory)]
        [string]$Url,

        [Parameter(Mandatory)]
        [string]$DestinationPath,

        [Parameter(Mandatory)]
        [string]$Label
    )

    Write-Step "Downloading $Label"
    Invoke-CompatibleWebRequest -Url $Url -DestinationPath $DestinationPath | Out-Null
}

function Get-OsArchitectureName {
    $osArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    switch ($osArchitecture) {
        ([System.Runtime.InteropServices.Architecture]::X64) { return "amd64" }
        ([System.Runtime.InteropServices.Architecture]::Arm64) { return "arm64" }
        default { Fail "Unsupported Windows architecture: $osArchitecture" }
    }
}

function Resolve-LatestPythonPatchVersion {
    param([Parameter(Mandatory)][string]$MinorVersion)

    if ($MinorVersion -match '^\d+\.\d+\.\d+$') {
        return $MinorVersion
    }

    if ($MinorVersion -notmatch '^\d+\.\d+$') {
        Fail "PythonVersion must use major.minor or major.minor.patch format."
    }

    $indexUrl = "$PythonDownloadBaseUrl/"
    $response = Invoke-CompatibleWebRequest -Url $indexUrl
    $versionPattern = [regex]::Escape($MinorVersion) + '\.\d+/'
    $matches = [regex]::Matches($response.Content, $versionPattern)

    if ($matches.Count -eq 0) {
        Fail "Could not find a Python $MinorVersion release in $indexUrl"
    }

    $versions = @(
        foreach ($match in $matches) {
            $match.Value.TrimEnd('/')
        }
    ) | Select-Object -Unique

    return ($versions | Sort-Object { [version]$_ } -Descending | Select-Object -First 1)
}

function Get-PythonInstallerUrl {
    $fullVersion = Resolve-LatestPythonPatchVersion -MinorVersion $PythonVersion
    $archName = Get-OsArchitectureName
    return "$PythonDownloadBaseUrl/$fullVersion/python-$fullVersion-$archName.exe"
}

function Test-PythonVersionMatch {
    param(
        [Parameter(Mandatory)]
        [string]$InstalledVersion,

        [Parameter(Mandatory)]
        [string]$RequestedVersion
    )

    if ($RequestedVersion -match '^\d+\.\d+$') {
        return $InstalledVersion.StartsWith("$RequestedVersion.", [System.StringComparison]::Ordinal)
    }

    return [System.StringComparer]::Ordinal.Equals($InstalledVersion, $RequestedVersion)
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

function Ensure-IsolatedPython {
    $pythonExe = Join-Path $PythonInstallDir "python.exe"
    if (Test-Path -LiteralPath $pythonExe) {
        $installedVersion = (& $pythonExe -c "import platform; print(platform.python_version())").Trim()
        if (Test-PythonVersionMatch -InstalledVersion $installedVersion -RequestedVersion $PythonVersion) {
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

    $pythonInstallerUrl = Get-PythonInstallerUrl
    $pythonInstallerPath = New-TemporaryDownloadPath -FileName ([System.IO.Path]::GetFileName(([System.Uri]$pythonInstallerUrl).AbsolutePath))
    Invoke-DownloadFile -Url $pythonInstallerUrl -DestinationPath $pythonInstallerPath -Label "Python $PythonVersion"
    Write-Step "Installing Python $PythonVersion"
    Invoke-ExternalProcess `
        -FilePath $pythonInstallerPath `
        -Label "Python installer" `
        -Arguments @(
            "/quiet",
            "InstallAllUsers=0",
            "PrependPath=0",
            "AssociateFiles=0",
            "Shortcuts=0",
            "Include_launcher=0",
            "Include_test=0",
            "SimpleInstall=1",
            "TargetDir=$PythonInstallDir"
        )

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        Fail "Python installation completed, but python.exe was not created at $PythonInstallDir. Re-run the Upload Assistant installer; it must create and use its isolated Python runtime."
    }

    return $pythonExe
}

function Install-RepositoryFromZip {
    param([Parameter(Mandatory)][string]$DestinationDir)

    $parentDir = Split-Path -Parent $DestinationDir
    if (-not [string]::IsNullOrWhiteSpace($parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }

    $resolvedDestinationDir = [System.IO.Path]::GetFullPath($DestinationDir)
    $rootDir = [System.IO.Path]::GetPathRoot($resolvedDestinationDir)
    if ([System.StringComparer]::OrdinalIgnoreCase.Equals($resolvedDestinationDir, $rootDir)) {
        Fail "DestinationDir cannot be a drive root. Choose a dedicated Upload Assistant directory."
    }

    $zipPath = New-TemporaryDownloadPath -FileName ("UploadAssistant-" + [guid]::NewGuid().ToString("N") + ".zip")
    $parentDir = Split-Path -Parent $resolvedDestinationDir
    New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    $extractRoot = Join-Path $parentDir (".UploadAssistant-extract-" + [guid]::NewGuid().ToString("N"))

    try {
        Invoke-DownloadFile -Url $RepositoryZipUrl -DestinationPath $zipPath -Label "Upload Assistant"
        Write-Step "Extracting Upload Assistant"
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force

        $sourceDir = Get-ChildItem -Path $extractRoot -Directory | Select-Object -First 1 -ExpandProperty FullName
        if (-not $sourceDir -or -not (Test-Path -LiteralPath (Join-Path $sourceDir "upload.py"))) {
            Fail "Downloaded Upload Assistant ZIP has an unexpected layout."
        }

        if (Test-Path -LiteralPath $resolvedDestinationDir) {
            Fail "Destination directory already exists and must be preserved. This appears to be a staging directory collision."
        }

        Move-Item -LiteralPath $sourceDir -Destination $resolvedDestinationDir
    }
    finally {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    }
}

function Install-Dependencies {
    param(
        [Parameter(Mandatory)][string]$PythonExe,
        [Parameter(Mandatory)][string]$AppDir
    )

    & $PythonExe -c "import venv"
    $supportsVirtualEnvironments = $LASTEXITCODE -eq 0

    if (-not $supportsVirtualEnvironments) {
        Write-Step "Installing dependencies in the embedded Python runtime"
        & $PythonExe -m pip install -U pip --no-warn-script-location
        if ($LASTEXITCODE -ne 0) {
            Fail "pip upgrade failed"
        }

        & $PythonExe -m pip install --no-warn-script-location -r (Join-Path $AppDir "requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            Fail "Base dependency installation failed"
        }

        return $PythonExe
    }

    $venvDir = Join-Path $AppDir ".venv"
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
        $venvVersion = (& $venvPython -c "import platform; print(platform.python_version())").Trim()
        if (-not (Test-PythonVersionMatch -InstalledVersion $venvVersion -RequestedVersion $PythonVersion)) {
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
    & $venvPython -m pip install -U pip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) {
        Fail "pip upgrade failed"
    }

    Write-Step "Installing Upload Assistant dependencies"
    & $venvPython -m pip install --no-warn-script-location -r (Join-Path $AppDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Fail "Base dependency installation failed"
    }

    return $venvPython
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
    param([Parameter(Mandatory)][string]$AppDir)

    $runnerPath = Join-Path $AppDir "run-ua.ps1"
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
    $venvPython = Join-Path $scriptDir "python\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Python runtime not found. Re-run scripts/install-windows.ps1 first."
    }
}

Set-Location $scriptDir
& $venvPython (Join-Path $scriptDir "upload.py") @UploadArgs
exit $LASTEXITCODE
'@

    Set-Content -LiteralPath $runnerPath -Value $runnerContents -Encoding ASCII
}

function Write-GlobalLauncher {
    param([Parameter(Mandatory)][string]$AppDir)

    New-Item -ItemType Directory -Path $LauncherDir -Force | Out-Null

    $launcherCmdPath = Join-Path $LauncherDir "ua.cmd"
    $updateCmdPath = Join-Path $LauncherDir "ua-update.cmd"
    $configCmdPath = Join-Path $LauncherDir "ua-config.cmd"
    $webuiCmdPath = Join-Path $LauncherDir "ua-webui.cmd"
    $launcherCmdContents = @"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$AppDir\run-ua.ps1" %*
exit /b %errorlevel%
"@
$updateCmdContents = @"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$AppDir\scripts\update-windows.ps1" -UaDir "$AppDir" -PythonInstallDir "$PythonInstallDir" -LauncherDir "$LauncherDir" %*
exit /b %errorlevel%
"@
    $configCmdContents = @"
@echo off
pushd "$AppDir"
if exist "$AppDir\python\python.exe" (
    "$AppDir\python\python.exe" "$AppDir\config-generator.py" %*
) else (
    "$AppDir\.venv\Scripts\python.exe" "$AppDir\config-generator.py" %*
)
set "exit_code=%errorlevel%"
popd
exit /b %exit_code%
"@
    $webuiCmdContents = @"
@echo off
start "" "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "$AppDir\scripts\run-webui-tray.ps1" -AppDir "$AppDir" %*
exit /b 0
"@

    Remove-Item -LiteralPath (Join-Path $LauncherDir "ua.ps1") -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $LauncherDir "ua-update.ps1") -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $LauncherDir "ua-config.ps1") -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $LauncherDir "ua-webui.ps1") -Force -ErrorAction SilentlyContinue
    Set-Content -LiteralPath $launcherCmdPath -Value $launcherCmdContents -Encoding ASCII
    Set-Content -LiteralPath $updateCmdPath -Value $updateCmdContents -Encoding ASCII
    Set-Content -LiteralPath $configCmdPath -Value $configCmdContents -Encoding ASCII
    Set-Content -LiteralPath $webuiCmdPath -Value $webuiCmdContents -Encoding ASCII
    Add-DirectoryToUserPath -DirectoryPath $LauncherDir
}

function Complete-StagedInstallation {
    param(
        [Parameter(Mandatory)][string]$StagingDir,
        [Parameter(Mandatory)][string]$DestinationDir,
        [string[]]$PreserveDirectories = @()
    )

    $resolvedStagingDir = [System.IO.Path]::GetFullPath($StagingDir)
    $resolvedDestinationDir = [System.IO.Path]::GetFullPath($DestinationDir)
    $backupDir = Join-Path (Split-Path -Parent $resolvedDestinationDir) (".UploadAssistant-backup-" + [guid]::NewGuid().ToString("N"))
    $movedDirectories = @()
    $activated = $false

    try {
        if (Test-Path -LiteralPath $resolvedDestinationDir) {
            Write-Step "Activating updated Upload Assistant"
            Move-Item -LiteralPath $resolvedDestinationDir -Destination $backupDir

            foreach ($directory in $PreserveDirectories) {
                if ([string]::IsNullOrWhiteSpace($directory)) {
                    continue
                }

                $resolvedDirectory = [System.IO.Path]::GetFullPath($directory)
                $destinationPrefix = $resolvedDestinationDir.TrimEnd('\') + '\'
                if (-not $resolvedDirectory.StartsWith($destinationPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    continue
                }

                $relativeDirectory = $resolvedDirectory.Substring($destinationPrefix.Length)
                $backupPath = Join-Path $backupDir $relativeDirectory
                if (-not (Test-Path -LiteralPath $backupPath)) {
                    continue
                }

                $stagedPath = Join-Path $resolvedStagingDir $relativeDirectory
                if (Test-Path -LiteralPath $stagedPath) {
                    continue
                }
                New-Item -ItemType Directory -Path (Split-Path -Parent $stagedPath) -Force | Out-Null
                Move-Item -LiteralPath $backupPath -Destination $stagedPath
                $movedDirectories += [pscustomobject]@{
                    StagedPath = $stagedPath
                    BackupPath = $backupPath
                }
            }
        }

        Move-Item -LiteralPath $resolvedStagingDir -Destination $resolvedDestinationDir
        $activated = $true
    }
    catch {
        foreach ($movedDirectory in $movedDirectories) {
            if (Test-Path -LiteralPath $movedDirectory.StagedPath) {
                New-Item -ItemType Directory -Path (Split-Path -Parent $movedDirectory.BackupPath) -Force | Out-Null
                Move-Item -LiteralPath $movedDirectory.StagedPath -Destination $movedDirectory.BackupPath -Force
            }
        }

        if (Test-Path -LiteralPath $backupDir) {
            if (Test-Path -LiteralPath $resolvedDestinationDir) {
                Remove-Item -LiteralPath $resolvedDestinationDir -Recurse -Force
            }
            Move-Item -LiteralPath $backupDir -Destination $resolvedDestinationDir
        }

        throw
    }
    finally {
        if ($activated) {
            Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $resolvedStagingDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$PythonExe = Ensure-IsolatedPython
$resolvedUaDir = [System.IO.Path]::GetFullPath($UaDir)
$stagingDir = Join-Path (Split-Path -Parent $resolvedUaDir) (".UploadAssistant-staging-" + [guid]::NewGuid().ToString("N"))
$actualPythonPath = $null
try {
    Install-RepositoryFromZip -DestinationDir $stagingDir

    $stagedPythonExe = $PythonExe
    $resolvedPythonInstallDir = [System.IO.Path]::GetFullPath($PythonInstallDir)
    $destinationPrefix = $resolvedUaDir.TrimEnd('\') + '\'
    if ($resolvedPythonInstallDir.StartsWith($destinationPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedPythonInstallDir)) {
        $relativePythonDir = $resolvedPythonInstallDir.Substring($destinationPrefix.Length)
        $stagedPythonDir = Join-Path $stagingDir $relativePythonDir
        Copy-Item -LiteralPath $resolvedPythonInstallDir -Destination $stagedPythonDir -Recurse -Force
        $relativePythonExe = $PythonExe.Substring($resolvedPythonInstallDir.Length).TrimStart('\')
        $stagedPythonExe = Join-Path $stagedPythonDir $relativePythonExe
    }

    $actualPythonPath = Install-Dependencies -PythonExe $stagedPythonExe -AppDir $stagingDir
    Write-Runner -AppDir $stagingDir
    $preservePaths = @(
        (Join-Path $resolvedUaDir "data")
        (Join-Path $resolvedUaDir "tmp")
        $PythonInstallDir
        (Join-Path $resolvedUaDir "ffmpeg")
    )
    Complete-StagedInstallation -StagingDir $stagingDir -DestinationDir $resolvedUaDir -PreserveDirectories $preservePaths
    Write-GlobalLauncher -AppDir $resolvedUaDir
}
finally {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force -ErrorAction SilentlyContinue
}

if ($actualPythonPath -and $actualPythonPath.StartsWith($stagingDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    $relativePath = $actualPythonPath.Substring($stagingDir.Length).TrimStart('\')
    $actualPythonPath = Join-Path $resolvedUaDir $relativePath
}

if (-not $actualPythonPath) {
    $actualPythonPath = Join-Path $resolvedUaDir ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $actualPythonPath)) {
        $actualPythonPath = $PythonExe
    }
}

$launcherCmdPath = Join-Path $LauncherDir "ua.cmd"
$updateCmdPath = Join-Path $LauncherDir "ua-update.cmd"
$configCmdPath = Join-Path $LauncherDir "ua-config.cmd"
$webuiCmdPath = Join-Path $LauncherDir "ua-webui.cmd"

Write-Host ""
Write-Host "Installation complete."
Write-Host ""
Write-Host "Location:"
Write-Host "  $UaDir"
Write-Host ""
Write-Host "Python interpreter:"
Write-Host "  $actualPythonPath"
Write-Host ""
Write-Host "First step:"
Write-Host "  Configure UA with: ua-config"
Write-Host "  (Run this before the first upload.)"
Write-Host ""
Write-Host "Run:"
Write-Host "  ua `"/path/to/content`" --trackers yourtracker"
Write-Host "  ua-update"
Write-Host "  ua-webui"
Write-Host ""
Write-Host "Global launcher:"
Write-Host "  $launcherCmdPath"
Write-Host "  $updateCmdPath"
Write-Host "  $configCmdPath"
Write-Host "  $webuiCmdPath"
Write-Host ""
Write-Host "PATH note:"
Write-Host "  A new PowerShell or Command Prompt window may be required before 'ua', 'ua-update', 'ua-config', and 'ua-webui' are available everywhere."
Write-Host ""
Write-Host "Configuration command (equivalent):"
Write-Host "  & `"$actualPythonPath`" `"$UaDir\config-generator.py`""
