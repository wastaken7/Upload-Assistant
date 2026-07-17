[CmdletBinding()]
param(
    [string]$UaDir = (Join-Path $HOME "tools\ua"),
    [string]$PythonVersion = "3.14",
    [string]$PythonInstallDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\python\3.14"),
    [string]$LauncherDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\bin"),
    [string]$FfmpegInstallDir = (Join-Path $env:LOCALAPPDATA "UploadAssistant\ffmpeg"),
    [string]$PythonDownloadBaseUrl = "https://www.python.org/ftp/python",
    [string]$GitReleaseApiUrl = "https://api.github.com/repos/git-for-windows/git/releases/latest",
    [string]$FfmpegDownloadUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
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

function Find-InstalledPython {
    $pythonDirectoryName = "Python" + ($PythonVersion -replace '\.', '')
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\$pythonDirectoryName\python.exe"),
        (Join-Path $env:ProgramFiles "Python$($PythonVersion -replace '\.', '')\python.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Python$($PythonVersion -replace '\.', '')\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }

        $installedVersion = (& $candidate -c "import platform; print(platform.python_version())").Trim()
        if (Test-PythonVersionMatch -InstalledVersion $installedVersion -RequestedVersion $PythonVersion) {
            return $candidate
        }
    }

    return $null
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

function Get-GitInstallerUrl {
    $response = Invoke-RestMethod -Uri $GitReleaseApiUrl -Headers @{ "User-Agent" = "Upload-Assistant" }
    $assetPattern = switch ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture) {
        ([System.Runtime.InteropServices.Architecture]::Arm64) { '^Git-.*-arm64\.exe$' }
        default { '^Git-.*-64-bit\.exe$' }
    }

    $asset = $response.assets | Where-Object { $_.name -match $assetPattern } | Select-Object -First 1
    if (-not $asset) {
        Fail "Could not find a matching Git for Windows installer in the latest release."
    }

    return $asset.browser_download_url
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

    $gitInstallerUrl = Get-GitInstallerUrl
    $gitInstallerPath = New-TemporaryDownloadPath -FileName ([System.IO.Path]::GetFileName(([System.Uri]$gitInstallerUrl).AbsolutePath))
    Invoke-DownloadFile -Url $gitInstallerUrl -DestinationPath $gitInstallerPath -Label "Git for Windows"
    Write-Step "Installing Git for Windows"
    Invoke-ExternalProcess `
        -FilePath $gitInstallerPath `
        -Label "Git for Windows installer" `
        -Arguments @(
            "/VERYSILENT",
            "/NORESTART",
            "/NOCANCEL",
            "/SP-",
            "/CURRENTUSER",
            "/SUPPRESSMSGBOXES",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
            "/o:PathOption=Cmd"
        )

    $gitExe = Resolve-CommandPath -CommandName "git.exe" -CandidatePaths $gitCandidates
    if (-not $gitExe) {
        Fail "Git was installed but git.exe could not be located. Reopen PowerShell or install Git manually."
    }

    return $gitExe
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
        $existingPython = Find-InstalledPython
        if ($existingPython) {
            Write-Host "Python $PythonVersion is already installed at $existingPython; using it for the Upload Assistant virtual environment."
            return $existingPython
        }

        Fail "Python installation completed, but python.exe was not created at $PythonInstallDir. The installer may have reused an existing Python installation; install Python $PythonVersion manually or remove that installation and rerun this script."
    }

    return $pythonExe
}

function Ensure-Ffmpeg {
    if ($SkipFfmpegInstall) {
        return
    }

    $managedFfmpegExe = Join-Path $FfmpegInstallDir "bin\ffmpeg.exe"
    if (Test-Path -LiteralPath $managedFfmpegExe) {
        Add-DirectoryToUserPath -DirectoryPath (Split-Path -Parent $managedFfmpegExe)
        return
    }

    $ffmpegCommand = Resolve-CommandPath -CommandName "ffmpeg.exe"
    if ($ffmpegCommand) {
        return
    }

    $ffmpegArchivePath = New-TemporaryDownloadPath -FileName ([System.IO.Path]::GetFileName(([System.Uri]$FfmpegDownloadUrl).AbsolutePath))
    $extractRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("UploadAssistantFfmpeg-" + [guid]::NewGuid().ToString("N"))

    Invoke-DownloadFile -Url $FfmpegDownloadUrl -DestinationPath $ffmpegArchivePath -Label "FFmpeg"
    Write-Step "Installing FFmpeg"
    Expand-Archive -LiteralPath $ffmpegArchivePath -DestinationPath $extractRoot -Force

    $ffmpegExe = Get-ChildItem -Path $extractRoot -Filter ffmpeg.exe -Recurse | Select-Object -First 1 -ExpandProperty FullName
    if (-not $ffmpegExe) {
        Fail "Downloaded FFmpeg archive did not contain ffmpeg.exe."
    }

    $ffmpegRoot = Split-Path -Parent (Split-Path -Parent $ffmpegExe)
    if (Test-Path -LiteralPath $FfmpegInstallDir) {
        Remove-Item -LiteralPath $FfmpegInstallDir -Recurse -Force
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $FfmpegInstallDir) -Force | Out-Null
    Move-Item -LiteralPath $ffmpegRoot -Destination $FfmpegInstallDir
    Add-DirectoryToUserPath -DirectoryPath (Join-Path $FfmpegInstallDir "bin")
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
