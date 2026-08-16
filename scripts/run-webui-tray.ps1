[CmdletBinding()]
param(
    [string]$AppDir,
    [string]$HostAddress,
    [Nullable[int]]$Port,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type -MemberDefinition @'
[DllImport("user32.dll")]
public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("kernel32.dll")]
public static extern IntPtr GetConsoleWindow();
'@ -Name "Win32ConsoleHelper" -Namespace "Win32" -PassThru -ErrorAction SilentlyContinue | Out-Null

try {
    $consoleHandle = [Win32.Win32ConsoleHelper]::GetConsoleWindow()
    if ($consoleHandle -ne [IntPtr]::Zero) {
        [Win32.Win32ConsoleHelper]::ShowWindow($consoleHandle, 0) | Out-Null
    }
}
catch {
}

$resolvedAppDir = if (-not [string]::IsNullOrWhiteSpace($AppDir)) {
    [System.IO.Path]::GetFullPath($AppDir)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
}

$venvPython = Join-Path $resolvedAppDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    $fallbackPython = Join-Path $resolvedAppDir "python\python.exe"
    if (Test-Path -LiteralPath $fallbackPython) {
        $venvPython = $fallbackPython
    } else {
        [System.Windows.Forms.MessageBox]::Show(
            "Virtual environment Python not found at:`n$venvPython`n`nPlease install or reinstall Upload Assistant.",
            "Upload Assistant WebUI",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        exit 1
    }
}

$uploadPy = Join-Path $resolvedAppDir "upload.py"
$iconPath = Join-Path $resolvedAppDir "logo.ico"

# State & settings directory
$appDataDir = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)) "Upload-Assistant"
if (-not (Test-Path -LiteralPath $appDataDir)) {
    New-Item -ItemType Directory -Path $appDataDir -Force | Out-Null
}
$settingsFile = Join-Path $appDataDir "webui-settings.json"

function Get-DefaultBrowseRoots {
    $roots = [System.Collections.Generic.List[string]]::new()
    $downloads = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)) "Downloads"
    $videos = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)) "Videos"

    if (Test-Path -LiteralPath $downloads) { $roots.Add($downloads) }
    if (Test-Path -LiteralPath $videos) { $roots.Add($videos) }

    # Fallback to available ready drives if empty
    if ($roots.Count -eq 0) {
        foreach ($drive in [System.IO.DriveInfo]::GetDrives()) {
            if ($drive.IsReady -and $drive.DriveType -eq [System.IO.DriveType]::Fixed) {
                $roots.Add($drive.RootDirectory.FullName)
            }
        }
    }
    return @($roots)
}

function Load-Settings {
    if (Test-Path -LiteralPath $settingsFile) {
        try {
            $raw = Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8
            $data = $raw | ConvertFrom-Json
            return $data
        }
        catch {
            # Fall back to defaults on corrupt JSON
        }
    }

    $defaultSettings = [PSCustomObject]@{
        host = "127.0.0.1"
        port = 5000
        browse_roots = (Get-DefaultBrowseRoots)
        open_browser_on_start = $true
    }
    Save-Settings -Settings $defaultSettings
    return $defaultSettings
}

function Save-Settings {
    param([Parameter(Mandatory)][psobject]$Settings)
    $json = $Settings | ConvertTo-Json -Depth 4
    Set-Content -LiteralPath $settingsFile -Value $json -Encoding UTF8
}

$global:Settings = Load-Settings

if (-not [string]::IsNullOrWhiteSpace($HostAddress)) {
    $global:Settings.host = $HostAddress
}
if ($null -ne $Port -and $Port.HasValue) {
    $global:Settings.port = $Port.Value
}

# Single-Instance Enforcement via Named Mutex
$mutexCreated = $false
$mutexName = "Local\UploadAssistantWebUiTrayMutex"
$global:AppMutex = [System.Threading.Mutex]::new($true, $mutexName, [ref]$mutexCreated)

if (-not $mutexCreated) {
    # WebUI Tray is already running - just open the browser and exit silently
    $url = Get-WebUiUrl
    try {
        $psi = [System.Diagnostics.ProcessStartInfo]::new()
        $psi.FileName = $url
        $psi.UseShellExecute = $true
        [System.Diagnostics.Process]::Start($psi) | Out-Null
    }
    catch {
        Start-Process $url -ErrorAction SilentlyContinue
    }
    exit 0
}

function Cleanup-AppMutex {
    if ($global:AppMutex) {
        try {
            $global:AppMutex.ReleaseMutex()
            $global:AppMutex.Dispose()
        }
        catch {
        }
        finally {
            $global:AppMutex = $null
        }
    }
}

$global:WebUiProcess = $null
$global:NotifyIcon = $null
$global:StatusMenuItem = $null
$global:StartMenuItem = $null
$global:StopMenuItem = $null
$global:RestartMenuItem = $null
$global:OpenMenuItem = $null

function Get-WebUiUrl {
    $h = if ($global:Settings.host -eq "0.0.0.0") { "localhost" } else { $global:Settings.host }
    return "http://$h`:$($global:Settings.port)"
}

function Update-TrayState {
    param([bool]$IsRunning)

    $url = Get-WebUiUrl
    if ($IsRunning) {
        $global:NotifyIcon.Text = "Upload Assistant WebUI (Running - port $($global:Settings.port))"
        $global:StatusMenuItem.Text = "Status: Running ($url)"
        $global:StartMenuItem.Enabled = $false
        $global:StopMenuItem.Enabled = $true
        $global:RestartMenuItem.Enabled = $true
        $global:OpenMenuItem.Enabled = $true
    } else {
        $global:NotifyIcon.Text = "Upload Assistant WebUI (Stopped)"
        $global:StatusMenuItem.Text = "Status: Stopped"
        $global:StartMenuItem.Enabled = $true
        $global:StopMenuItem.Enabled = $false
        $global:RestartMenuItem.Enabled = $false
        $global:OpenMenuItem.Enabled = $false
    }
}

function Start-WebUi {
    param([bool]$OpenBrowser = $false)

    if ($global:WebUiProcess -and -not $global:WebUiProcess.HasExited) {
        if ($OpenBrowser) {
            Open-WebUiBrowser
        }
        return
    }

    $browseRootsList = @($global:Settings.browse_roots)
    if ($browseRootsList.Count -eq 0) {
        $browseRootsList = Get-DefaultBrowseRoots
        $global:Settings.browse_roots = $browseRootsList
        Save-Settings -Settings $global:Settings
    }
    $browseRootsStr = ($browseRootsList -join ",")

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $venvPython
    $psi.Arguments = "`"$uploadPy`" --webui $($global:Settings.host):$($global:Settings.port)"
    $psi.WorkingDirectory = $resolvedAppDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables["UA_BROWSE_ROOTS"] = $browseRootsStr

    try {
        $global:WebUiProcess = [System.Diagnostics.Process]::Start($psi)
        Update-TrayState -IsRunning $true

        if ($OpenBrowser) {
            # Give the server a brief moment to bind port
            Start-Sleep -Milliseconds 800
            Open-WebUiBrowser
        }
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "Failed to start WebUI:`n$_",
            "Upload Assistant WebUI Error",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        Update-TrayState -IsRunning $false
    }
}

function Stop-WebUi {
    if ($global:WebUiProcess) {
        try {
            if (-not $global:WebUiProcess.HasExited) {
                $global:WebUiProcess.Kill()
                $global:WebUiProcess.WaitForExit(3000)
            }
        }
        catch {
        }
        finally {
            $global:WebUiProcess.Dispose()
            $global:WebUiProcess = $null
        }
    }
    Update-TrayState -IsRunning $false
}

function Restart-WebUi {
    Stop-WebUi
    Start-Sleep -Milliseconds 500
    Start-WebUi -OpenBrowser $false
}

function Open-WebUiBrowser {
    $url = Get-WebUiUrl
    try {
        $psi = [System.Diagnostics.ProcessStartInfo]::new()
        $psi.FileName = $url
        $psi.UseShellExecute = $true
        [System.Diagnostics.Process]::Start($psi) | Out-Null
    }
    catch {
        Start-Process $url -ErrorAction SilentlyContinue
    }
}

function Add-AllowedFolder {
    $dialog = [System.Windows.Forms.FolderBrowserDialog]::new()
    $dialog.Description = "Select a folder to allow Upload Assistant WebUI to browse"
    $dialog.ShowNewFolderButton = $false

    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $selectedPath = $dialog.SelectedPath
        $currentRoots = [System.Collections.Generic.List[string]]::new()
        foreach ($r in @($global:Settings.browse_roots)) {
            if (-not [string]::IsNullOrWhiteSpace($r)) {
                $currentRoots.Add($r.ToString())
            }
        }

        $alreadyExists = $false
        foreach ($r in $currentRoots) {
            if ([System.StringComparer]::OrdinalIgnoreCase.Equals($r, $selectedPath)) {
                $alreadyExists = $true
                break
            }
        }

        if (-not $alreadyExists) {
            $currentRoots.Add($selectedPath)
            $global:Settings.browse_roots = @($currentRoots.ToArray())
            Save-Settings -Settings $global:Settings

            $msg = "Added allowed folder:`n$selectedPath`n`nDo you want to restart the WebUI now to apply changes?"
            $res = [System.Windows.Forms.MessageBox]::Show($msg, "Folder Added", [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Question)
            if ($res -eq [System.Windows.Forms.DialogResult]::Yes) {
                Restart-WebUi
            }
        } else {
            [System.Windows.Forms.MessageBox]::Show("This folder is already in the allowed list.", "Information", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
        }
    }
    $dialog.Dispose()
}

function Open-SettingsFile {
    if (Test-Path -LiteralPath $settingsFile) {
        Start-Process "notepad.exe" -ArgumentList "`"$settingsFile`""
    }
}

function Launch-UaConfig {
    $configScript = Join-Path $resolvedAppDir "config-generator.py"
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $venvPython
    $psi.Arguments = "`"$configScript`""
    $psi.WorkingDirectory = $resolvedAppDir
    $psi.UseShellExecute = $true
    [System.Diagnostics.Process]::Start($psi) | Out-Null
}

# Create System Tray Context Menu
$contextMenu = [System.Windows.Forms.ContextMenuStrip]::new()

$global:StatusMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Status: Starting...")
$global:StatusMenuItem.Enabled = $false
[void]$contextMenu.Items.Add($global:StatusMenuItem)

[void]$contextMenu.Items.Add([System.Windows.Forms.ToolStripSeparator]::new())

$global:OpenMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Open WebUI in Browser")
$global:OpenMenuItem.Font = [System.Drawing.Font]::new($global:OpenMenuItem.Font, [System.Drawing.FontStyle]::Bold)
$global:OpenMenuItem.Add_Click({ Open-WebUiBrowser })
[void]$contextMenu.Items.Add($global:OpenMenuItem)

$global:StartMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Start Server")
$global:StartMenuItem.Add_Click({ Start-WebUi -OpenBrowser $false })
[void]$contextMenu.Items.Add($global:StartMenuItem)

$global:StopMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Stop Server")
$global:StopMenuItem.Add_Click({ Stop-WebUi })
[void]$contextMenu.Items.Add($global:StopMenuItem)

$global:RestartMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Restart Server")
$global:RestartMenuItem.Add_Click({ Restart-WebUi })
[void]$contextMenu.Items.Add($global:RestartMenuItem)

[void]$contextMenu.Items.Add([System.Windows.Forms.ToolStripSeparator]::new())

$folderMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Add Allowed Folder (Browse Roots)...")
$folderMenuItem.Add_Click({ Add-AllowedFolder })
[void]$contextMenu.Items.Add($folderMenuItem)

$settingsMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Edit WebUI Settings (JSON)...")
$settingsMenuItem.Add_Click({ Open-SettingsFile })
[void]$contextMenu.Items.Add($settingsMenuItem)

$uaConfigMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Upload Assistant Config (ua-config)...")
$uaConfigMenuItem.Add_Click({ Launch-UaConfig })
[void]$contextMenu.Items.Add($uaConfigMenuItem)

[void]$contextMenu.Items.Add([System.Windows.Forms.ToolStripSeparator]::new())

$exitMenuItem = [System.Windows.Forms.ToolStripMenuItem]::new("Exit WebUI Tray")
$exitMenuItem.Add_Click({
    Stop-WebUi
    Cleanup-AppMutex
    $global:NotifyIcon.Visible = $false
    $global:NotifyIcon.Dispose()
    [System.Windows.Forms.Application]::Exit()
})
[void]$contextMenu.Items.Add($exitMenuItem)

# Initialize NotifyIcon
$global:NotifyIcon = [System.Windows.Forms.NotifyIcon]::new()
$global:NotifyIcon.ContextMenuStrip = $contextMenu

if (Test-Path -LiteralPath $iconPath) {
    $global:NotifyIcon.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($iconPath)
} else {
    $global:NotifyIcon.Icon = [System.Drawing.SystemIcons]::Application
}

$global:NotifyIcon.Text = "Upload Assistant WebUI"
$global:NotifyIcon.Visible = $true
$global:NotifyIcon.Add_DoubleClick({ Open-WebUiBrowser })

# Start server on launch
$shouldOpenBrowser = (-not $NoBrowser) -and [bool]($global:Settings.open_browser_on_start)
Start-WebUi -OpenBrowser $shouldOpenBrowser

# Clean up on PowerShell exit
Register-EngineEvent -SourceIdentifier ([guid]::NewGuid().ToString()) -Action {
    Stop-WebUi
    Cleanup-AppMutex
    if ($global:NotifyIcon) {
        $global:NotifyIcon.Visible = $false
        $global:NotifyIcon.Dispose()
    }
} | Out-Null

[System.Windows.Forms.Application]::Run()
