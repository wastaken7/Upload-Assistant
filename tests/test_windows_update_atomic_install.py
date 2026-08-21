import pathlib

SCRIPT = (pathlib.Path(__file__).parents[1] / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
INSTALLER = (pathlib.Path(__file__).parents[1] / "scripts" / "windows-installer.iss").read_text(encoding="utf-8")
BUNDLED_INSTALLER = (pathlib.Path(__file__).parents[1] / "scripts" / "install-bundled-windows.ps1").read_text(encoding="utf-8")
WORKFLOW = (pathlib.Path(__file__).parents[1] / ".github" / "workflows" / "windows-installer.yml").read_text(encoding="utf-8")


def test_update_stages_dependencies_before_replacing_installation():
    """A failed pip install must leave the currently installed command usable."""
    stage = SCRIPT.index("Install-RepositoryFromZip -DestinationDir $stagingDir")
    dependencies = SCRIPT.index("Install-Dependencies -PythonExe $stagedPythonExe -AppDir $stagingDir")
    activate = SCRIPT.index("Complete-StagedInstallation -StagingDir $stagingDir")

    if not stage < dependencies < activate:
        raise AssertionError("Dependencies must complete before installation activation")
    if "Move-Item -LiteralPath $resolvedDestinationDir -Destination $backupDir" not in SCRIPT:
        raise AssertionError("The previous installation must be backed up before activation")
    if "Move-Item -LiteralPath $backupDir -Destination $resolvedDestinationDir" not in SCRIPT:
        raise AssertionError("A failed activation must restore the previous installation")
    for preserved_path in (
        '(Join-Path $resolvedUaDir "data")',
        '(Join-Path $resolvedUaDir "tmp")',
        "$PythonInstallDir",
        '(Join-Path $resolvedUaDir "ffmpeg")',
    ):
        if preserved_path not in SCRIPT:
            raise AssertionError(f"The updater must preserve {preserved_path} during activation")


def test_windows_updater_stages_embedded_python_runtime_before_dependencies():
    if "$stagedPythonExe = $PythonExe" not in SCRIPT:
        raise AssertionError("The updater must initialize staged Python executable")
    if "Copy-Item -LiteralPath $resolvedPythonInstallDir -Destination $stagedPythonDir" not in SCRIPT:
        raise AssertionError("The updater must stage embedded Python into the staging directory")
    if "$stagedPythonExe = Join-Path $stagedPythonDir $relativePythonExe" not in SCRIPT:
        raise AssertionError("The updater must use staged Python executable for dependencies")
    if "if (Test-Path -LiteralPath $stagedPath) {" not in SCRIPT:
        raise AssertionError("Activation must not overwrite staged directories")



def test_installer_aborts_when_post_installation_fails():
    if "procedure CurStepChanged(CurStep: TSetupStep);" not in INSTALLER:
        raise AssertionError("The installer must run post-installation setup from [Code]")
    if "ewWaitUntilTerminated, ResultCode" not in INSTALLER:
        raise AssertionError("The installer must wait for the post-installation exit code")
    if "if ResultCode <> 0 then" not in INSTALLER:
        raise AssertionError("The installer must fail when post-installation fails")
    if "see install.log in the selected folder for details" not in INSTALLER:
        raise AssertionError("The installer must direct users to the post-installation log")


def test_bundled_installer_records_post_installation_output():
    if '$installLog = Join-Path $resolvedInstallDir "install.log"' not in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must define a persistent installation log")
    if "Start-Transcript -LiteralPath $installLog -Append" not in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must record post-installation output")
    if "$startInfo.RedirectStandardOutput = $true" not in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must redirect child process standard output")
    if "$startInfo.RedirectStandardError = $true" not in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must redirect child process standard error")


def test_windows_installers_do_not_fall_back_to_existing_python():
    for installer in (SCRIPT, BUNDLED_INSTALLER):
        if "Find-InstalledPython" in installer or "Find-ExistingPython" in installer:
            raise AssertionError("Windows installers must not reuse a system Python runtime")
        if "Using existing compatible Python" in installer or "using it for the Upload Assistant virtual environment" in installer:
            raise AssertionError("Windows installers must require their isolated Python runtime")


def test_bundled_installer_uses_embeddable_python_without_registry_installation():
    if "python-$fullVersion-embed-$archName.zip" not in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must use Python's embeddable distribution")
    if "bundled pip bootstrap" not in BUNDLED_INSTALLER:
        raise AssertionError("The embedded runtime must bootstrap its bundled pip")
    if "[System.IO.Compression.ZipFile]::ExtractToDirectory" not in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must extract the runtime without PowerShell archive modules")
    if "$pathEntries += '..'" not in BUNDLED_INSTALLER:
        raise AssertionError("The embedded runtime must include the application directory on sys.path")
    if "Expand-Archive" in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must not depend on Microsoft.PowerShell.Archive")
    if '"TargetDir=$pythonDir"' in BUNDLED_INSTALLER or '"SimpleInstall=1"' in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must not invoke the registry-backed Python installer")
    if 'Join-Path $scriptDir "python\\python.exe"' not in BUNDLED_INSTALLER:
        raise AssertionError("The application launcher must use its embedded Python runtime")


def test_bundled_installer_is_offline_after_setup_starts():
    for parameter in ("PythonRuntimeArchive", "PipBootstrap", "Wheelhouse", "FfmpegArchive"):
        if f"[string]${parameter}" not in BUNDLED_INSTALLER:
            raise AssertionError(f"The bundled installer must receive {parameter} from the setup payload")
    if '"--no-index", "--find-links", $resolvedWheelhouse' not in BUNDLED_INSTALLER:
        raise AssertionError("Dependency installation must use the bundled wheelhouse")
    if "Ensure-DestinationFfmpeg" not in BUNDLED_INSTALLER:
        raise AssertionError("The bundled installer must install its bundled FFmpeg archive")
    for artifact in ("python-runtime.zip", "get-pip.py", "ffmpeg.zip", "wheels"):
        if artifact not in INSTALLER:
            raise AssertionError(f"The Inno Setup payload must include {artifact}")
    for artifact in ("python-$pythonVersion-embed-amd64.zip", "get-pip.py", "ffmpeg.zip", "pip -r requirements.txt"):
        if artifact not in WORKFLOW:
            raise AssertionError(f"The build workflow must create bundled {artifact}")


def test_windows_updater_can_reuse_the_embedded_runtime():
    if '& $PythonExe -c "import venv"' not in SCRIPT:
        raise AssertionError("The updater must detect whether its isolated runtime supports virtual environments")
    if "Installing dependencies in the embedded Python runtime" not in SCRIPT:
        raise AssertionError("The updater must install dependencies directly for embedded Python")
    if 'Join-Path $scriptDir "python\\python.exe"' not in SCRIPT:
        raise AssertionError("The updater-generated runner must support the embedded Python runtime")
