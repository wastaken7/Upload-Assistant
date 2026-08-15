Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
appDir = fso.GetParentFolderName(scriptDir)

If WScript.Arguments.Count > 0 Then
    appDir = WScript.Arguments(0)
End If

cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & appDir & "\scripts\run-webui-tray.ps1"" -AppDir """ & appDir & """"
WshShell.Run cmd, 0, False
