' Console-free Windows launcher and Python runtime guard for PayPamin Flow.
' Copyright © 2026 Rickard Längkvist.
'
' An existing Python is never replaced with another runtime. The selected
' Python Install Manager runtime is updated by its exact install ID, which
' keeps the update in the existing installation directory. A default Python
' is installed only after the existing-runtime checks have found nothing.
Option Explicit
Dim fso, sh, appDir, scriptPath, env, runtimeLogPath
Dim pythonwPath, pythonPath, knownPythonPath, managerPath, wingetPath
Dim anyPythonPath, managedPythonPath, managedLauncherPath, managedId, refreshedPath
Dim anyCode, managedCode, updateCode, installCode, captured
Dim hasPython, managerInventoryOK, canUpdateManaged
Dim cmd, arguments, argument

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fso.BuildPath(appDir, "paypamin_flow_launcher.py")
runtimeLogPath = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\.paminnelseapp\logs\python-runtime.log"
If Not fso.FileExists(scriptPath) Then
  MsgBox "Hittar inte paypamin_flow_launcher.py i appmappen.", vbCritical, "PayPamin Flow"
  WScript.Quit 1
End If
sh.CurrentDirectory = appDir
Set env = sh.Environment("PROCESS")

' 1. Inventory first. WindowsApps Python aliases are deliberately excluded:
'    without a real runtime they can open a store/install flow by themselves.
pythonwPath = FindOnPath("pythonw.exe")
pythonPath = FindOnPath("python.exe")
If pythonwPath = "" And pythonPath <> "" Then pythonwPath = ConsoleFreePythonFor(pythonPath)
hasPython = (pythonwPath <> "" Or pythonPath <> "")
managerPath = FindOnPath("pymanager.exe")
managerInventoryOK = True
anyPythonPath = ""
managedPythonPath = ""
managedId = ""

If managerPath <> "" Then
  anyPythonPath = ManagerValue(managerPath, "exe", False, anyCode)
  If anyCode <> 0 Then
    managerInventoryOK = False
  ElseIf anyPythonPath <> "" Then
    If fso.FileExists(anyPythonPath) Then
      hasPython = True
      If pythonwPath = "" Then pythonwPath = ConsoleFreePythonFor(anyPythonPath)
    Else
      managerInventoryOK = False
      WriteRuntimeLog "Python inventory returned a missing executable: " & anyPythonPath
    End If
  End If

  managedId = ManagerValue(managerPath, "id", True, managedCode)
  If managedCode <> 0 Then
    managerInventoryOK = False
    managedId = ""
  ElseIf Not IsSafeInstallId(managedId) Then
    If managedId <> "" Then managerInventoryOK = False
    managedId = ""
  Else
    managedPythonPath = ManagerValue(managerPath, "exe", True, managedCode)
    If managedCode <> 0 Or Not fso.FileExists(managedPythonPath) Then
      managerInventoryOK = False
      managedPythonPath = ""
      managedId = ""
    End If
  End If
End If

' Also check the standard python.org and Python Install Manager locations
' before deciding that Python is absent. These installations are only reused,
' never removed or replaced by this launcher.
If Not hasPython Then
  knownPythonPath = FindKnownPython()
  If knownPythonPath <> "" Then
    hasPython = True
    pythonPath = knownPythonPath
    pythonwPath = ConsoleFreePythonFor(knownPythonPath)
    WriteRuntimeLog "Found existing Python outside PATH: " & knownPythonPath
  End If
End If

' A failed inventory is not proof that Python is absent. Stop rather than
' risking a parallel installation.
If Not hasPython And managerPath <> "" And Not managerInventoryOK Then
  FailRuntime "Det gick inte att kontrollera Python-installationen. Ingen ny Python har installerats."
End If

' 2. Update only the existing runtime that this launcher will actually use.
'    --by-id is essential: a newer major/minor runtime has another ID and must
'    not be installed beside the current one. Other managed runtimes are not
'    touched, and unmanaged/system/venv Python installations are left alone.
canUpdateManaged = False
If hasPython And managerPath <> "" And managedId <> "" And managedPythonPath <> "" Then
  managedLauncherPath = ConsoleFreePythonFor(managedPythonPath)
  If pythonwPath = "" Then
    pythonwPath = managedLauncherPath
    canUpdateManaged = True
  ElseIf SamePath(pythonwPath, managedLauncherPath) Then
    canUpdateManaged = True
  ElseIf pythonPath <> "" And SamePath(pythonPath, managedPythonPath) Then
    canUpdateManaged = True
  ElseIf anyPythonPath <> "" And SamePath(anyPythonPath, managedPythonPath) And SamePath(pythonwPath, ConsoleFreePythonFor(anyPythonPath)) Then
    canUpdateManaged = True
  ElseIf IsManagerAliasPath(pythonwPath) Then
    pythonwPath = managedLauncherPath
    canUpdateManaged = True
  End If
End If

If canUpdateManaged Then
  pythonwPath = managedLauncherPath
  WriteRuntimeLog "Checking existing Python runtime for an in-place update: " & managedId
  updateCode = RunCaptured(Quote(managerPath) & " install --update --by-id " & Quote(managedId), "Update existing Python runtime " & managedId, captured)
  If updateCode <> 0 Then
    WriteRuntimeLog "ERROR: Python update failed with exit code " & updateCode & ". The existing runtime will be reused; no new runtime was requested."
    MsgBox "Python kunde inte uppdateras. PayPamin Flow startar med befintlig Python. Ingen ny Python installerades." & vbCrLf & vbCrLf & "Logg: " & runtimeLogPath, vbExclamation, "PayPamin Flow"
  Else
    refreshedPath = ManagerValue(managerPath, "exe", True, managedCode)
    If managedCode = 0 And refreshedPath <> "" And fso.FileExists(refreshedPath) Then
      pythonwPath = ConsoleFreePythonFor(refreshedPath)
    End If
  End If
ElseIf hasPython Then
  WriteRuntimeLog "Existing Python is not confirmed as the selected manager-managed runtime. Leaving it unchanged; no update or new installation was requested."
End If

' 3. Install only when all existing-runtime checks found no Python. The
'    manager's default tag selects its current recommended stable release.
If Not hasPython Then
  WriteRuntimeLog "No existing Python runtime found. A new default stable runtime may now be installed."
  If managerPath = "" Then
    wingetPath = FindOnPath("winget.exe")
    If wingetPath = "" Then
      FailRuntime "Python saknas. WinGet och Python Install Manager hittades inte, sa Python kunde inte installeras automatiskt. Installera Python Install Manager fran python.org och starta igen."
    End If
    installCode = RunCaptured(Quote(wingetPath) & " install 9NQ7512CXL7T -e --accept-package-agreements --disable-interactivity", "Install Python Install Manager because Python is missing", captured)
    If installCode <> 0 Then
      FailRuntime "Python saknas, men Python Install Manager kunde inte installeras. Ingen annan Python-installation har startats."
    End If
    managerPath = FindOnPath("pymanager.exe")
    If managerPath = "" Then
      managerPath = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Microsoft\WindowsApps\pymanager.exe"
      If Not fso.FileExists(managerPath) Then managerPath = ""
    End If
    If managerPath = "" Then
      FailRuntime "Python Install Manager installerades men hittades inte. Starta PayPamin Flow igen eller logga ut och in."
    End If
  End If

  installCode = RunCaptured(Quote(managerPath) & " install default", "Install latest recommended stable Python because no runtime exists", captured)
  If installCode <> 0 Then
    FailRuntime "Python saknas, men den senaste stabila Python kunde inte installeras. Se loggen for information."
  End If
  pythonPath = ManagerValue(managerPath, "exe", False, anyCode)
  If anyCode <> 0 Or pythonPath = "" Or Not fso.FileExists(pythonPath) Then
    FailRuntime "Python-installationen avslutades men ingen fungerande Python hittades. Starta PayPamin Flow igen."
  End If
  pythonwPath = ConsoleFreePythonFor(pythonPath)
  hasPython = True
End If

If pythonwPath = "" Then
  FailRuntime "Python finns men ingen startbar Python-tolk hittades. Ingen ny Python har installerats."
End If

' Preserve --minimized and any future launcher arguments for OS autostart.
arguments = ""
For Each argument In WScript.Arguments
  arguments = arguments & " " & Quote(CStr(argument))
Next
WriteRuntimeLog "Starting PayPamin Flow with existing Python: " & pythonwPath
cmd = Quote(pythonwPath) & " " & Quote(scriptPath) & arguments
sh.Run cmd, 0, False

Function Quote(value)
  Quote = Chr(34) & CStr(value) & Chr(34)
End Function

Function SingleLine(value)
  Dim lines, index, candidate
  lines = Split(Replace(CStr(value), vbCrLf, vbLf), vbLf)
  For index = UBound(lines) To 0 Step -1
    candidate = Trim(lines(index))
    If candidate <> "" Then
      SingleLine = candidate
      Exit Function
    End If
  Next
  SingleLine = ""
End Function

Function FindOnPath(fileName)
  Dim parts, part, candidate, pythonAlias
  FindOnPath = ""
  parts = Split(env("PATH"), ";")
  For Each part In parts
    part = Replace(Trim(part), Chr(34), "")
    If Len(part) > 0 Then
      candidate = fso.BuildPath(part, fileName)
      pythonAlias = (LCase(fileName) = "python.exe" Or LCase(fileName) = "pythonw.exe") And IsWindowsAppsPath(candidate)
      If Not pythonAlias Then
        If fso.FileExists(candidate) Then
          FindOnPath = candidate
          Exit Function
        End If
      End If
    End If
  Next
End Function

Function IsWindowsAppsPath(path)
  IsWindowsAppsPath = (InStr(1, LCase(CStr(path)), "\microsoft\windowsapps\", vbTextCompare) > 0)
End Function

Function IsManagerAliasPath(path)
  Dim managerBin
  managerBin = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Python\bin\"
  IsManagerAliasPath = (InStr(1, LCase(CStr(path)), LCase(managerBin), vbTextCompare) = 1) Or IsWindowsAppsPath(path)
End Function

Function ConsoleFreePythonFor(pythonExecutable)
  Dim candidate
  ConsoleFreePythonFor = ""
  If pythonExecutable = "" Then Exit Function
  If LCase(fso.GetFileName(pythonExecutable)) = "pythonw.exe" Then
    ConsoleFreePythonFor = pythonExecutable
    Exit Function
  End If
  candidate = fso.BuildPath(fso.GetParentFolderName(pythonExecutable), "pythonw.exe")
  If fso.FileExists(candidate) Then
    ConsoleFreePythonFor = candidate
  Else
    ' WScript.Shell.Run below still hides this interpreter's console.
    ConsoleFreePythonFor = pythonExecutable
  End If
End Function

Function SamePath(firstPath, secondPath)
  On Error Resume Next
  SamePath = False
  If firstPath = "" Or secondPath = "" Then Exit Function
  SamePath = (StrComp(fso.GetAbsolutePathName(firstPath), fso.GetAbsolutePathName(secondPath), vbTextCompare) = 0)
End Function

Function IsSafeInstallId(value)
  Dim expression
  IsSafeInstallId = False
  If value = "" Then Exit Function
  Set expression = CreateObject("VBScript.RegExp")
  expression.Pattern = "^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
  IsSafeInstallId = expression.Test(value)
End Function

Function ManagerValue(managerExecutable, formatName, onlyManaged, ByRef resultCode)
  Dim commandLine, value
  commandLine = Quote(managerExecutable) & " list "
  If onlyManaged Then commandLine = commandLine & "--only-managed "
  commandLine = commandLine & "--one --format=" & formatName
  resultCode = RunCaptured(commandLine, "Inspect installed Python runtime; format=" & formatName & "; onlyManaged=" & CStr(onlyManaged), value)
  If resultCode = 0 Then
    ManagerValue = SingleLine(value)
  Else
    ManagerValue = ""
  End If
End Function

Function RunCaptured(commandLine, action, ByRef output)
  Dim temporaryPath, commandLineWithRedirect, exitCode, stream, errorText
  output = ""
  temporaryPath = fso.BuildPath(fso.GetSpecialFolder(2), fso.GetTempName())
  commandLineWithRedirect = commandLine & " > " & Quote(temporaryPath) & " 2>&1"
  exitCode = -1
  errorText = ""
  On Error Resume Next
  exitCode = sh.Run(Quote(sh.ExpandEnvironmentStrings("%ComSpec%")) & " /d /s /c " & Quote(commandLineWithRedirect), 0, True)
  If Err.Number <> 0 Then
    errorText = Err.Description
    Err.Clear
  End If
  If fso.FileExists(temporaryPath) Then
    Set stream = fso.OpenTextFile(temporaryPath, 1, False, 0)
    If Not stream.AtEndOfStream Then output = stream.ReadAll
    stream.Close
    fso.DeleteFile temporaryPath, True
  End If
  On Error GoTo 0
  If errorText <> "" Then output = output & vbCrLf & errorText
  WriteRuntimeLog action & "; exit=" & CStr(exitCode) & "; output=" & Replace(Replace(output, vbCrLf, " | "), vbLf, " | ")
  RunCaptured = exitCode
End Function

Function FindKnownPython()
  Dim localRoot, roots, root
  FindKnownPython = ""
  localRoot = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%")
  roots = Array( _
    Array(localRoot & "\Programs\Python", False), _
    Array(localRoot & "\Python", False), _
    Array(sh.ExpandEnvironmentStrings("%ProgramFiles%"), True), _
    Array(sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%"), True), _
    Array(sh.ExpandEnvironmentStrings("%SystemDrive%") & "\", True) _
  )
  For Each root In roots
    FindKnownPython = FindPythonBelow(CStr(root(0)), CBool(root(1)))
    If FindKnownPython <> "" Then Exit Function
  Next
End Function

Function FindPythonBelow(rootPath, pythonFoldersOnly)
  Dim candidate, folder, subfolder
  FindPythonBelow = ""
  If rootPath = "" Or Not fso.FolderExists(rootPath) Then Exit Function
  candidate = fso.BuildPath(rootPath, "python.exe")
  If fso.FileExists(candidate) Then
    FindPythonBelow = candidate
    Exit Function
  End If
  On Error Resume Next
  Set folder = fso.GetFolder(rootPath)
  If Err.Number <> 0 Then
    Err.Clear
    Exit Function
  End If
  For Each subfolder In folder.SubFolders
    If (Not pythonFoldersOnly) Or Left(LCase(subfolder.Name), 6) = "python" Then
      candidate = fso.BuildPath(subfolder.Path, "python.exe")
      If fso.FileExists(candidate) Then
        FindPythonBelow = candidate
        Exit Function
      End If
    End If
  Next
End Function

Sub EnsureFolder(folderPath)
  If folderPath = "" Or fso.FolderExists(folderPath) Then Exit Sub
  EnsureFolder fso.GetParentFolderName(folderPath)
  fso.CreateFolder folderPath
End Sub

Sub WriteRuntimeLog(message)
  On Error Resume Next
  Dim stream
  EnsureFolder fso.GetParentFolderName(runtimeLogPath)
  Set stream = fso.OpenTextFile(runtimeLogPath, 8, True, 0)
  stream.WriteLine "[" & CStr(Now) & "] " & CStr(message)
  stream.Close
End Sub

Sub FailRuntime(message)
  WriteRuntimeLog "ERROR: " & message
  MsgBox message & vbCrLf & vbCrLf & "Logg: " & runtimeLogPath, vbCritical, "PayPamin Flow"
  WScript.Quit 1
End Sub
