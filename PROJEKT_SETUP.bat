@echo off
rem Doppelklick oeffnet das Fenster. Oder den Projektordner auf diese Datei ziehen.
where pythonw >nul 2>nul
if errorlevel 1 (
    echo Python wurde nicht gefunden. Bitte von python.org installieren
    echo und beim Setup "Add python.exe to PATH" anhaken.
    pause
    exit /b 1
)
start "" pythonw "%~dp0PROJEKT_SETUP_GUI.pyw" %*
