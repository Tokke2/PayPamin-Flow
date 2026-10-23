' Windows launcher for PayPåminn Flow: starts pythonw.exe with no console window.
Option Explicit
Dim fso, sh, appDir, scriptPath, env, paths, p, pythonwPath, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fso.BuildPath(appDir, "paypaminn_flow.pyw")
If Not fso.FileExists(scriptPath) Then
  MsgBox "Hittar inte paypaminn_flow.pyw i appmappen.", vbCritical, "PayPåminn Flow"
  WScript.Quit 1
End If
sh.CurrentDirectory = appDir
Set env = sh.Environment("PROCESS")
paths = Split(env("PATH"), ";")
pythonwPath = ""
For Each p In paths
  p = Replace(Trim(p), Chr(34), "")
  If Len(p) > 0 Then
    If fso.FileExists(fso.BuildPath(p, "pythonw.exe")) Then
      pythonwPath = fso.BuildPath(p, "pythonw.exe")
      Exit For
    End If
  End If
Next
If pythonwPath = "" Then
  MsgBox "Hittar inte pythonw.exe. Installera Python för Windows och kontrollera att Python finns i PATH.", vbExclamation, "PayPåminn Flow"
  WScript.Quit 1
End If
cmd = Chr(34) & pythonwPath & Chr(34) & " " & Chr(34) & scriptPath & Chr(34)
sh.Run cmd, 0, False
