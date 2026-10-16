Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run Chr(34) & base & "\.venv\Scripts\pythonw.exe" & Chr(34) & " " & Chr(34) & base & "\manager.pyw" & Chr(34) & " --autostart --minimized", 7, False
