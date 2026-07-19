Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName) & "\"
pyexe = base & "_py\pythonw.exe"
If Not fso.FileExists(pyexe) Then pyexe = "pythonw"
Set sh = CreateObject("WScript.Shell")
sh.Run """" & pyexe & """ """ & base & "agent_server.py""", 0, False
