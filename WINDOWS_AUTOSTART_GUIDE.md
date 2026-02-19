# Windows 10 開機自動執行設定指南

本文檔說明如何讓 Flask 多專案備份工具在 Windows 10 開機時自動於背景執行。

## 📋 目錄

- [快速開始](#快速開始)
- [方法一：工作排程器（推薦）](#方法一工作排程器推薦)
- [方法二：啟動資料夾](#方法二啟動資料夾)
- [方法三：註冊表 Run 鍵](#方法三註冊表-run-鍵)
- [方法四：Windows 服務](#方法四windows-服務)
- [自動設定腳本](#自動設定腳本)
- [疑難排解](#疑難排解)

## 快速開始

最簡單的方式是執行自動設定腳本：

1. **以系統管理員身分**開啟命令提示字元（CMD）
2. 切換到專案目錄：
   ```cmd
   cd D:\ai_develop\backapp
   ```
3. 執行設定腳本：
   ```cmd
   setup_autostart.bat
   ```
4. 選擇「[1] 工作排程器」選項

## 方法一：工作排程器（推薦）

**優點**：
- 可設定延遲啟動（避免開機時系統負載過重）
- 可設定執行條件（如網路連線後才執行）
- 可設定重試機制
- 支援最高權限執行

### 手動設定步驟

1. 建立啟動腳本 `start_silent.bat`：
   ```batch
   @echo off
   cd /d "D:\ai_develop\backapp"
   start /min "" pythonw flask_multi_backup.py --silent
   ```

2. 開啟「工作排程器」（Task Scheduler）
   - 按 `Win + R`，輸入 `taskschd.msc`，按 Enter

3. 建立新工作：
   - 點擊右側「建立工作...」

4. 一般設定：
   - **名稱**：`FlaskMultiBackup`
   - **描述**：`Flask 專案自動備份`
   - 勾選「使用最高權限執行」
   - 選擇「無論使用者是否登入都要執行」

5. 觸發程序設定：
   - 點擊「新增...」
   - **開始工作**：`登入時`
   - **延遲工作時間**：`30 秒`（建議）
   - 勾選「已啟用」

6. 動作設定：
   - 點擊「新增...」
   - **動作**：`啟動程式`
   - **程式/指令碼**：瀏覽選擇 `start_silent.bat`
   - **開始位置**：`D:\ai_develop\backapp`

7. 條件設定（選用）：
   - 勾選「只有在下列網路連線可用時才啟動」
   - 選擇「任何連線」

8. 點擊「確定」儲存

## 方法二：啟動資料夾

**優點**：設定最簡單  
**缺點**：無法設定延遲、條件等進階選項

### 手動設定步驟

1. 建立啟動腳本 `start_silent.bat`：
   ```batch
   @echo off
   cd /d "D:\ai_develop\backapp"
   start /min "" pythonw flask_multi_backup.py --silent
   ```

2. 建立捷徑：
   - 右鍵點擊 `start_silent.bat`
   - 選擇「建立捷徑」
   - 右鍵捷徑 → 內容
   - 「執行」選項設為「最小化」

3. 移動捷徑到啟動資料夾：
   - 按 `Win + R`，輸入 `shell:startup`，按 Enter
   - 將捷徑複製到開啟的資料夾中

## 方法三：註冊表 Run 鍵

**優點**：系統級自動啟動  
**缺點**：需要修改註冊表

### 手動設定步驟

1. 建立啟動腳本 `start_silent.bat`

2. 開啟登錄編輯程式：
   - 按 `Win + R`，輸入 `regedit`，按 Enter

3. 導航至：
   ```
   HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
   ```

4. 新增字串值：
   - 右鍵 → 新增 → 字串值
   - **名稱**：`FlaskMultiBackup`
   - **值**：`"D:\ai_develop\backapp\start_silent.bat"`

## 方法四：Windows 服務

**優點**：
- 無需使用者登入即可執行
- 系統級背景服務
- 可透過服務管理員控制

**缺點**：設定較複雜，需要安裝 pywin32

### 安裝步驟

1. 安裝 pywin32：
   ```cmd
   pip install pywin32
   ```

2. 建立服務安裝腳本 `install_service.py`（內容見 setup_autostart.bat 自動生成部分）

3. 以系統管理員身分安裝服務：
   ```cmd
   python install_service.py install
   python install_service.py start
   ```

4. 管理服務：
   ```cmd
   python install_service.py start    # 啟動
   python install_service.py stop     # 停止
   python install_service.py remove   # 移除
   ```

## 自動設定腳本

專案包含 `setup_autostart.bat` 腳本，可自動完成上述設定：

```cmd
# 以系統管理員身分執行
setup_autostart.bat
```

**選項說明**：
- `[1]` 工作排程器 - 最推薦，功能最完整
- `[2]` 啟動資料夾 - 最簡單，適合一般使用者
- `[3]` 註冊表 Run 鍵 - 系統級啟動
- `[4]` Windows 服務 - 無需登入，適合伺服器
- `[5]` 移除所有設定 - 清除所有自動啟動

## 設定自動備份

無論使用哪種自動啟動方式，請先在 GUI 中設定：

1. **開啟 GUI**：
   ```cmd
   python flask_multi_backup.py
   ```

2. **新增專案**：
   - 切換到「專案管理」分頁
   - 點擊「新增專案」選擇要備份的 Flask 專案

3. **設定備份目的地**：
   - 切換到「備份設定」分頁
   - 設定備份儲存路徑

4. **啟用自動備份**：
   - 勾選「啟用自動備份」
   - 設定備份間隔（小時）

5. **儲存設定**：
   - 點擊「儲存設定」

## 無聲模式參數

程式支援 `--silent` 參數在背景執行：

```cmd
# 背景執行（無 GUI）
pythonw flask_multi_backup.py --silent
```

**注意**：使用 `pythonw.exe` 而非 `python.exe` 以避免彈出命令視窗。

## 檢視日誌

自動執行時，所有輸出都會記錄到日誌檔案：

- **一般日誌**：`%APPDATA%\FlaskMultiBackup\logs\backup.log`
- **錯誤日誌**：`%APPDATA%\FlaskMultiBackup\logs\error.log`

快速開啟日誌資料夾：
```cmd
explorer %APPDATA%\FlaskMultiBackup\logs
```

## 疑難排解

### 問題：程式沒有自動啟動

**檢查項目**：
1. 確認 Python 已加入環境變數 PATH
2. 確認使用 `pythonw.exe` 而非 `python.exe`
3. 檢查日誌檔案是否有錯誤訊息
4. 確認設定檔已正確儲存

### 問題：開機後馬上執行導致系統緩慢

**解決方案**：
- 使用工作排程器並設定延遲（建議 30-60 秒）
- 或在腳本中加入延遲：
  ```batch
  @echo off
  timeout /t 30 /nobreak >nul
  cd /d "D:\ai_develop\backapp"
  start /min "" pythonw flask_multi_backup.py --silent
  ```

### 問題：備份失敗但沒有錯誤訊息

**檢查步驟**：
1. 查看錯誤日誌：`error.log`
2. 確認備份目的地有寫入權限
3. 確認專案路徑仍然有效
4. 手動執行測試：
   ```cmd
   python flask_multi_backup.py --silent
   ```

### 問題：如何停止自動備份

**方法**：
1. 執行 `setup_autostart.bat` 選擇 `[5] 移除所有自動啟動設定`
2. 或手動移除對應的設定：
   - 工作排程器：刪除 `FlaskMultiBackup` 工作
   - 啟動資料夾：刪除 `FlaskBackup.lnk`
   - 註冊表：刪除 `FlaskMultiBackup` 鍵值
   - 服務：`python install_service.py stop && python install_service.py remove`

### 問題：程式在背景執行但不知道狀態

**解決方案**：
1. 查看日誌檔案確認執行狀態
2. 定期手動開啟 GUI 檢查
3. 修改設定，將備份目的地設為網路磁碟機，透過檔案時間戳確認

## 📝 注意事項

1. **第一次設定後請重新開機測試**，確認能正常自動啟動
2. **定期檢查備份結果**，建議每月至少一次
3. **備份磁碟空間**，確保備份目的地有足夠空間
4. **權限問題**，若備份到系統目錄需要系統管理員權限
5. **防毒軟體**，部分防毒軟體可能阻擋自動啟動，需加入白名單

## 🔧 進階設定

### 修改備份時間

編輯 `config.json`：
```json
{
  "backup_interval_hours": 12,
  "auto_backup": true
}
```

### 設定多個備份目的地

目前支援單一備份目的地，如需多地備份，可建立多個排程工作，分別使用不同的設定檔。

### 備份完成後通知

可在啟動腳本中加入通知：
```batch
@echo off
cd /d "D:\ai_develop\backapp"
pythonw flask_multi_backup.py --silent
if %errorlevel% == 0 (
    msg * "備份完成！"
)
```

---

如有問題，請檢查日誌檔案或手動執行測試。
