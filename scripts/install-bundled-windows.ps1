[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InstallDir,

    [string]$PythonVersion = "3.14",
    [string]$PythonDownloadBaseUrl = "https://www.python.org/ftp/python"
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

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $downloadForm = New-Object System.Windows.Forms.Form
    $downloadForm.Text = "Upload Assistant Setup"
    $downloadForm.ClientSize = New-Object System.Drawing.Size(440, 105)
    $downloadForm.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
    $downloadForm.ControlBox = $false
    $downloadForm.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
    $downloadForm.TopMost = $true

    $statusLabel = New-Object System.Windows.Forms.Label
    $statusLabel.AutoSize = $false
    $statusLabel.Location = New-Object System.Drawing.Point(18, 16)
    $statusLabel.Size = New-Object System.Drawing.Size(404, 24)
    $statusLabel.Text = "Downloading $Label..."
    $downloadForm.Controls.Add($statusLabel)

    $progressBar = New-Object System.Windows.Forms.ProgressBar
    $progressBar.Location = New-Object System.Drawing.Point(18, 48)
    $progressBar.Size = New-Object System.Drawing.Size(404, 24)
    $progressBar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
    $downloadForm.Controls.Add($progressBar)

    $downloadState = [pscustomobject]@{
        Complete = $false
        Error = $null
    }
    $webClient = New-Object System.Net.WebClient
    $webClient.add_DownloadProgressChanged({
        param($sender, $eventArgs)

        if ($eventArgs.TotalBytesToReceive -gt 0) {
            $progressBar.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
            $progressBar.Value = [Math]::Min(100, $eventArgs.ProgressPercentage)
            $downloadedMegabytes = $eventArgs.BytesReceived / 1MB
            $totalMegabytes = $eventArgs.TotalBytesToReceive / 1MB
            $statusLabel.Text = "Downloading $Label... {0:N1} / {1:N1} MB ({2}%)" -f $downloadedMegabytes, $totalMegabytes, $eventArgs.ProgressPercentage
        }
    })
    $webClient.add_DownloadFileCompleted({
        param($sender, $eventArgs)

        $downloadState.Error = $eventArgs.Error
        $downloadState.Complete = $true
    })

    try {
        $downloadForm.Show()
        $webClient.DownloadFileAsync([Uri]$Url, $DestinationPath)
        while (-not $downloadState.Complete) {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 50
        }

        if ($downloadState.Error) {
            throw $downloadState.Error
        }
    }
    finally {
        $downloadForm.Close()
        $downloadForm.Dispose()
        $webClient.Dispose()
    }
}

function Get-OsArchitectureName {
    $osArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    switch ($osArchitecture) {
        ([System.Runtime.InteropServices.Architecture]::X64) { return "amd64" }
        ([System.Runtime.InteropServices.Architecture]::Arm64) { return "arm64" }
        default { return "amd64" }
    }
}

function Resolve-LatestPythonPatchVersion {
    param(
        [Parameter(Mandatory)][string]$MinorVersion,
        [Parameter(Mandatory)][string]$DownloadBaseUrl
    )

    if ($MinorVersion -match '^\d+\.\d+\.\d+$') {
        return $MinorVersion
    }

    if ($MinorVersion -notmatch '^\d+\.\d+$') {
        throw "PythonVersion must use major.minor or major.minor.patch format."
    }

    $indexUrl = "$DownloadBaseUrl/"
    $response = Invoke-CompatibleWebRequest -Url $indexUrl
    $versionPattern = [regex]::Escape($MinorVersion) + '\.\d+/'
    $matches = [regex]::Matches($response.Content, $versionPattern)

    if ($matches.Count -eq 0) {
        throw "Could not find a Python $MinorVersion release in $indexUrl"
    }

    $versions = @(
        foreach ($match in $matches) {
            $match.Value.TrimEnd('/')
        }
    ) | Select-Object -Unique

    return ($versions | Sort-Object { [version]$_ } -Descending | Select-Object -First 1)
}

function Get-PythonInstallerUrl {
    param(
        [Parameter(Mandatory)][string]$MinorVersion,
        [Parameter(Mandatory)][string]$DownloadBaseUrl
    )
    $fullVersion = Resolve-LatestPythonPatchVersion -MinorVersion $MinorVersion -DownloadBaseUrl $DownloadBaseUrl
    $archName = Get-OsArchitectureName
    return "$DownloadBaseUrl/$fullVersion/python-$fullVersion-$archName.exe"
}

function Assert-TrustedPythonInstaller {
    param([Parameter(Mandatory)][string]$InstallerPath)

    $signature = Get-AuthenticodeSignature -FilePath $InstallerPath
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
        $signature.SignerCertificate.Subject -notmatch '(^|,\s*)CN=Python Software Foundation(,|$)') {
        throw "Downloaded Python installer failed signature validation: $($signature.Status)."
    }
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
        [Parameter(Mandatory)][string]$Description,
        [string]$ProgressMessage
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

    $process = $null
    $progressForm = $null
    try {
        if (-not [string]::IsNullOrWhiteSpace($ProgressMessage)) {
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing

            $progressForm = New-Object System.Windows.Forms.Form
            $progressForm.Text = "Upload Assistant Setup"
            $progressForm.ClientSize = New-Object System.Drawing.Size(440, 105)
            $progressForm.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
            $progressForm.ControlBox = $false
            $progressForm.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
            $progressForm.TopMost = $true

            $statusLabel = New-Object System.Windows.Forms.Label
            $statusLabel.AutoSize = $false
            $statusLabel.Location = New-Object System.Drawing.Point(18, 16)
            $statusLabel.Size = New-Object System.Drawing.Size(404, 32)
            $statusLabel.Text = $ProgressMessage
            $progressForm.Controls.Add($statusLabel)

            $progressBar = New-Object System.Windows.Forms.ProgressBar
            $progressBar.Location = New-Object System.Drawing.Point(18, 56)
            $progressBar.Size = New-Object System.Drawing.Size(404, 24)
            $progressBar.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
            $progressForm.Controls.Add($progressBar)
            $progressForm.Show()
        }

        $process = [System.Diagnostics.Process]::Start($startInfo)
        while (-not $process.HasExited) {
            if ($progressForm) {
                [System.Windows.Forms.Application]::DoEvents()
            }
            Start-Sleep -Milliseconds 100
        }
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw "$Description failed with exit code $($process.ExitCode)."
        }
    }
    finally {
        if ($null -ne $process) {
            $process.Dispose()
        }
        if ($null -ne $progressForm) {
            $progressForm.Close()
            $progressForm.Dispose()
        }
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

function Ensure-DestinationPython {
    param(
        [Parameter(Mandatory)][string]$DestinationDir,
        [Parameter(Mandatory)][string]$ExpectedMinorVersion,
        [Parameter(Mandatory)][string]$DownloadBaseUrl
    )

    $pythonDir = Join-Path $DestinationDir "python"
    $pythonExe = Join-Path $pythonDir "python.exe"

    if (Test-Path -LiteralPath $pythonExe) {
        if (Test-PythonVersionMatch -PythonPath $pythonExe -ExpectedMinorVersion $ExpectedMinorVersion) {
            Write-Step "Using existing Python in destination folder at $pythonExe"
            return $pythonExe
        }
        Write-Step "Existing Python at $pythonExe does not match version $ExpectedMinorVersion. Reinstalling..."
        Remove-Item -LiteralPath $pythonDir -Recurse -Force
    }

    Write-Step "Downloading Python $ExpectedMinorVersion installer"
    $pythonInstallerUrl = Get-PythonInstallerUrl -MinorVersion $ExpectedMinorVersion -DownloadBaseUrl $DownloadBaseUrl
    $installerFileName = [System.IO.Path]::GetFileName(([System.Uri]$pythonInstallerUrl).AbsolutePath)
    $tempInstallerPath = Join-Path ([System.IO.Path]::GetTempPath()) ("UploadAssistantPython-" + [guid]::NewGuid().ToString("N") + "-$installerFileName")

    try {
        Invoke-DownloadFile -Url $pythonInstallerUrl -DestinationPath $tempInstallerPath -Label "Python $ExpectedMinorVersion installer"
        Assert-TrustedPythonInstaller -InstallerPath $tempInstallerPath
        Write-Step "Installing Python $ExpectedMinorVersion to $pythonDir"
        Invoke-Process -FilePath $tempInstallerPath -Description "Python installation" -ArgumentList @(
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
    finally {
        Remove-Item -LiteralPath $tempInstallerPath -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        $existingPython = Find-ExistingPython -ExpectedMinorVersion $ExpectedMinorVersion
        if (-not $existingPython) {
            throw "Python installation did not create $pythonExe, and no compatible Python $ExpectedMinorVersion was found."
        }
        Write-Step "Using existing compatible Python at $existingPython"
        return $existingPython
    }

    return $pythonExe
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
        "ua-update.cmd" = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$escapedAppDirectory\scripts\update-windows.ps1`" -UaDir `"$escapedAppDirectory`" -PythonInstallDir `"$escapedAppDirectory\python`" -LauncherDir `"$escapedAppDirectory\bin`" %*`r`nexit /b %errorlevel%`r`n"
        "ua-config.cmd" = "@echo off`r`npushd `"$escapedAppDirectory`"`r`n`"$escapedAppDirectory\.venv\Scripts\python.exe`" `"$escapedAppDirectory\config-generator.py`" %*`r`nset `"exit_code=%errorlevel%`"`r`npopd`r`nexit /b %exit_code%`r`n"
        "ua-webui.cmd" = "@echo off`r`nstart `"`" `"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$escapedAppDirectory\scripts\run-webui-tray.ps1`" -AppDir `"$escapedAppDirectory`" %*`r`nexit /b 0`r`n"
    }

    foreach ($launcher in $launchers.GetEnumerator()) {
        Set-Content -LiteralPath (Join-Path $LauncherDirectory $launcher.Key) -Value $launcher.Value -Encoding ASCII
    }
}

$resolvedInstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$venvDir = Join-Path $resolvedInstallDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$launcherDir = Join-Path $resolvedInstallDir "bin"

if (-not (Test-Path -LiteralPath (Join-Path $resolvedInstallDir "upload.py"))) {
    throw "Upload Assistant files are missing from $resolvedInstallDir."
}

$pythonExe = Ensure-DestinationPython -DestinationDir $resolvedInstallDir -ExpectedMinorVersion $PythonVersion -DownloadBaseUrl $PythonDownloadBaseUrl

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Step "Creating virtual environment"
    Invoke-Process -FilePath $pythonExe -Description "Virtual environment creation" -ArgumentList @("-m", "venv", $venvDir)
}

Write-Runner -AppDirectory $resolvedInstallDir
Write-Launchers -AppDirectory $resolvedInstallDir -LauncherDirectory $launcherDir
Add-DirectoryToUserPath -DirectoryPath $launcherDir

Write-Step "Installing Upload Assistant dependencies"
Invoke-Process -FilePath $venvPython -Description "Pip upgrade" -ProgressMessage "Updating pip..." -ArgumentList @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Process -FilePath $venvPython -Description "Base dependency installation" -ProgressMessage "Downloading and installing Upload Assistant dependencies. This may take several minutes..." -ArgumentList @("-m", "pip", "install", "-r", (Join-Path $resolvedInstallDir "requirements.txt"))

Write-Step "Installation complete."
Write-Host ""
Write-Host "Available commands (open a new terminal window):"
Write-Host "  ua"
Write-Host "  ua-config"
Write-Host "  ua-update"
Write-Host "  ua-webui"
Write-Host ""
