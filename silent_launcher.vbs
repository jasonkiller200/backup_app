' Flask Multi Backup - 無聲啟動器
' 此腳本可在背景完全無聲地執行備份工具
' 不會顯示任何命令視窗

Dim WShell
Set WShell = CreateObject("WScript.Shell")

' 設定工作目錄
Dim FSO, workDir
Set FSO = CreateObject("Scripting.FileSystemObject")
workDir = FSO.GetParentFolderName(WScript.ScriptFullName)

' 執行備份（無聲模式）
WShell.Run "pythonw """ & workDir & "\flask_multi_backup.py"" --silent", 0, False

Set WShell = Nothing
