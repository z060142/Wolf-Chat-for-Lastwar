' ============================================================
' Request Administrator Privileges VBScript
' ============================================================
' This script requests administrator privileges and relaunches
' the specified batch file with elevated permissions
' ============================================================

If WScript.Arguments.Count = 0 Then
    WScript.Echo "Error: No script specified to run with admin privileges"
    WScript.Quit 1
End If

' Get the script to run from command line arguments
Dim scriptPath
scriptPath = WScript.Arguments(0)

' Create Shell object
Dim objShell
Set objShell = CreateObject("Shell.Application")

' Get additional arguments if any
Dim args
args = ""
If WScript.Arguments.Count > 1 Then
    For i = 1 To WScript.Arguments.Count - 1
        args = args & " " & WScript.Arguments(i)
    Next
End If

' Request admin privileges and run the script
objShell.ShellExecute "cmd.exe", "/c """ & scriptPath & """" & args, "", "runas", 1

' Exit this instance
WScript.Quit 0
