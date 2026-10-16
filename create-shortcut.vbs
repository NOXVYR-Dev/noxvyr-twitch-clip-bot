Set shell = CreateObject("WScript.Shell")
Set shortcut = shell.CreateShortcut("__LINK__")
shortcut.TargetPath = "wscript.exe"
shortcut.Arguments = Chr(34) & "__TARGET__" & Chr(34)
shortcut.WorkingDirectory = "__WORKING__"
shortcut.Save
