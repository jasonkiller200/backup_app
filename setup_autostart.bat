@echo off
title Flask 備份工具 - Windows 開機自動執行設定
cls

echo ==========================================
echo  Flask 多專案備份工具 - 自動啟動設定
echo ==========================================
echo.

REM 獲取當前目錄
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%flask_multi_backup.py"
set "PYTHON_CMD=pythonw"

REM 檢查 Python 是否安裝
%PYTHON_CMD% --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 未找到 pythonw.exe，請確認 Python 已安裝並加入環境變數
    pause
    exit /b 1
)

echo 偵測到 Python 安裝
echo.
echo 請選擇設定方式：
echo.
echo  [1] 工作排程器 (推薦) - 可設定觸發條件、延遲啟動
echo  [2] 啟動資料夾 - 最簡單，登入時自動執行
echo  [3] 註冊表 Run 鍵 - 系統級自動啟動
echo  [4] 建立 Windows 服務 - 背景執行，無需登入
echo  [5] 移除所有自動啟動設定
echo  [0] 取消
echo.

set /p choice="請輸入選項 (0-5): "

if "%choice%"=="1" goto :task_scheduler
if "%choice%"=="2" goto :startup_folder
if "%choice%"=="3" goto :registry
if "%choice%"=="4" goto :windows_service
if "%choice%"=="5" goto :remove_all
if "%choice%"=="0" goto :cancel
goto :invalid

:task_scheduler
echo.
echo [工作排程器設定]
echo 正在建立排程工作...

REM 建立啟動腳本
set "STARTUP_SCRIPT=%SCRIPT_DIR%start_backup_silent.bat"
echo @echo off > "%STARTUP_SCRIPT%"
echo cd /d "%SCRIPT_DIR%" >> "%STARTUP_SCRIPT%"
echo start /min "" pythonw flask_multi_backup.py --silent >> "%STARTUP_SCRIPT%"

REM 刪除舊的排程工作（如果存在）
schtasks /delete /tn "FlaskMultiBackup" /f >nul 2>&1

REM 建立新的排程工作（登入時啟動，延遲 30 秒）
schtasks /create /tn "FlaskMultiBackup" /tr "\"%STARTUP_SCRIPT%\"" /sc onlogon /delay 0000:30 /rl highest /f >nul 2>&1

if errorlevel 1 (
    echo [錯誤] 建立排程工作失敗，請以系統管理員身分執行
    pause
    exit /b 1
)

echo [成功] 排程工作已建立！
echo.
echo 設定內容：
echo   - 工作名稱: FlaskMultiBackup
echo   - 觸發條件: 使用者登入時
echo   - 延遲啟動: 30 秒
echo   - 執行權限: 最高權限
echo   - 執行模式: 無聲模式（背景執行）
echo.
echo 您可以在「工作排程器」中修改進階設定
echo.
pause
goto :end

:startup_folder
echo.
echo [啟動資料夾設定]

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_DIR%\FlaskBackup.lnk"

REM 建立啟動腳本
set "STARTUP_SCRIPT=%SCRIPT_DIR%start_backup_silent.bat"
echo @echo off > "%STARTUP_SCRIPT%"
echo cd /d "%SCRIPT_DIR%" >> "%STARTUP_SCRIPT%"
echo start /min "" pythonw flask_multi_backup.py --silent >> "%STARTUP_SCRIPT%"

REM 建立捷徑（使用 PowerShell）
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT_PATH%'); $Shortcut.TargetPath = '%STARTUP_SCRIPT%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.WindowStyle = 7; $Shortcut.Save()" >nul 2>&1

if errorlevel 1 (
    echo [錯誤] 建立捷徑失敗
    pause
    exit /b 1
)

echo [成功] 啟動項目已建立！
echo   位置: %SHORTCUT_PATH%
echo.
echo 下次登入時將自動啟動備份工具
echo.
pause
goto :end

:registry
echo.
echo [註冊表設定]
echo 正在寫入註冊表...

set "STARTUP_SCRIPT=%SCRIPT_DIR%start_backup_silent.bat"
echo @echo off > "%STARTUP_SCRIPT%"
echo cd /d "%SCRIPT_DIR%" >> "%STARTUP_SCRIPT%"
echo start /min "" pythonw flask_multi_backup.py --silent >> "%STARTUP_SCRIPT%"

REM 寫入 Run 鍵
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "FlaskMultiBackup" /t REG_SZ /d "\"%STARTUP_SCRIPT%\"" /f >nul 2>&1

if errorlevel 1 (
    echo [錯誤] 寫入註冊表失敗，請以系統管理員身分執行
    pause
    exit /b 1
)

echo [成功] 註冊表項目已建立！
echo   鍵值: HKCU\Software\Microsoft\Windows\CurrentVersion\Run\FlaskMultiBackup
echo.
pause
goto :end

:windows_service
echo.
echo [Windows 服務設定]
echo 注意：此選項需要額外安裝 pywin32 套件
echo.

REM 檢查 pywin32
%PYTHON_CMD% -c "import win32service" >nul 2>&1
if errorlevel 1 (
    echo [提示] 需要安裝 pywin32 套件
    echo 正在安裝...
    pip install pywin32
    if errorlevel 1 (
        echo [錯誤] 安裝失敗，請手動執行: pip install pywin32
        pause
        exit /b 1
    )
)

REM 建立服務安裝腳本
set "SERVICE_SCRIPT=%SCRIPT_DIR%install_service.py"
echo import sys > "%SERVICE_SCRIPT%"
echo import os >> "%SERVICE_SCRIPT%"
echo sys.path.insert(0, r'%SCRIPT_DIR%.'[:-1]) >> "%SERVICE_SCRIPT%"
echo. >> "%SERVICE_SCRIPT%"
echo from flask_multi_backup import FlaskMultiBackupApp >> "%SERVICE_SCRIPT%"
echo import win32serviceutil >> "%SERVICE_SCRIPT%"
echo import win32service >> "%SERVICE_SCRIPT%"
echo import win32event >> "%SERVICE_SCRIPT%"
echo import servicemanager >> "%SERVICE_SCRIPT%"
echo import socket >> "%SERVICE_SCRIPT%"
echo. >> "%SERVICE_SCRIPT%"
echo class FlaskBackupService(win32serviceutil.ServiceFramework): >> "%SERVICE_SCRIPT%"
echo     _svc_name_ = 'FlaskMultiBackupService' >> "%SERVICE_SCRIPT%"
echo     _svc_display_name_ = 'Flask Multi Backup Service' >> "%SERVICE_SCRIPT%"
echo     _svc_description_ = '自動備份 Flask 專案的背景服務' >> "%SERVICE_SCRIPT%"
echo. >> "%SERVICE_SCRIPT%"
echo     def __init__(self, args): >> "%SERVICE_SCRIPT%"
echo         win32serviceutil.ServiceFramework.__init__(self, args) >> "%SERVICE_SCRIPT%"
echo         self.stop_event = win32event.CreateEvent(None, 0, 0, None) >> "%SERVICE_SCRIPT%"
echo         socket.setdefaulttimeout(60) >> "%SERVICE_SCRIPT%"
echo. >> "%SERVICE_SCRIPT%"
echo     def SvcStop(self): >> "%SERVICE_SCRIPT%"
echo         self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING) >> "%SERVICE_SCRIPT%"
echo         win32event.SetEvent(self.stop_event) >> "%SERVICE_SCRIPT%"
echo. >> "%SERVICE_SCRIPT%"
echo     def SvcDoRun(self): >> "%SERVICE_SCRIPT%"
echo         servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE, >> "%SERVICE_SCRIPT%"
echo                               servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, '')) >> "%SERVICE_SCRIPT%"
echo         app = FlaskMultiBackupApp() >> "%SERVICE_SCRIPT%"
echo         app.config['silent_mode'] = True >> "%SERVICE_SCRIPT%"
echo         app.config['auto_backup'] = True >> "%SERVICE_SCRIPT%"
echo         app.backup_all_projects() >> "%SERVICE_SCRIPT%"
echo         win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE) >> "%SERVICE_SCRIPT%"
echo         servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE, >> "%SERVICE_SCRIPT%"
echo                               servicemanager.PYS_SERVICE_STOPPED, (self._svc_name_, '')) >> "%SERVICE_SCRIPT%"
echo. >> "%SERVICE_SCRIPT%"
echo if __name__ == '__main__': >> "%SERVICE_SCRIPT%"
echo     if len(sys.argv) == 1: >> "%SERVICE_SCRIPT%"
echo         servicemanager.Initialize() >> "%SERVICE_SCRIPT%"
echo         servicemanager.PrepareToHostSingle(FlaskBackupService) >> "%SERVICE_SCRIPT%"
echo         servicemanager.StartServiceCtrlDispatcher() >> "%SERVICE_SCRIPT%"
echo     else: >> "%SERVICE_SCRIPT%"
echo         win32serviceutil.HandleCommandLine(FlaskBackupService) >> "%SERVICE_SCRIPT%"

echo 正在安裝服務...
python "%SERVICE_SCRIPT%" install >nul 2>&1
python "%SERVICE_SCRIPT%" start >nul 2>&1

if errorlevel 1 (
    echo [錯誤] 服務安裝失敗，請以系統管理員身分執行
    pause
    exit /b 1
)

echo [成功] 服務已安裝並啟動！
echo   服務名稱: FlaskMultiBackupService
echo.
echo 管理命令：
echo   啟動: python install_service.py start
echo   停止: python install_service.py stop
echo   移除: python install_service.py remove
echo.
pause
goto :end

:remove_all
echo.
echo [移除所有自動啟動設定]
echo.

REM 移除工作排程器
echo 移除工作排程器項目...
schtasks /delete /tn "FlaskMultiBackup" /f >nul 2>&1

REM 移除啟動資料夾捷徑
echo 移除啟動資料夾項目...
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FlaskBackup.lnk" >nul 2>&1

REM 移除註冊表
echo 移除註冊表項目...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "FlaskMultiBackup" /f >nul 2>&1

REM 停止並移除服務
echo 移除 Windows 服務...
python "%SCRIPT_DIR%install_service.py" stop >nul 2>&1
python "%SCRIPT_DIR%install_service.py" remove >nul 2>&1

echo [完成] 所有自動啟動設定已移除
echo.
pause
goto :end

:cancel
echo 操作已取消
timeout /t 2 >nul
goto :end

:invalid
echo 無效的選項
timeout /t 2 >nul
goto :end

:end
exit /b 0
