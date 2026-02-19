# Flask 專案備份工具

這是一個使用 Python tkinter 開發的 GUI 應用程式，用於備份 Flask Web 專案。

## 專案結構

```
backapp/
├── flask_multi_backup.py        # 主程式：支援多專案、排程備份、還原功能
├── setup_autostart.bat          # Windows 自動啟動設定腳本
├── silent_launcher.vbs          # 無聲啟動器（不顯示視窗）
├── WINDOWS_AUTOSTART_GUIDE.md   # Windows 自動啟動詳細指南
├── SCHEDULED_BACKUP_GUIDE.md    # 排程備份指南
└── README.md                    # 本文件
```

## 功能特點

- ✅ **多專案管理** - 同時備份多個 Flask 專案
- ✅ **自動備份排程** - 設定間隔自動執行或特定時間執行
- ✅ **台灣時區固定時間備份** - 可設定如凌晨 2:00 自動備份
- ✅ **還原功能** - 從備份還原專案
- ✅ **進度追蹤** - 備份與還原進度條
- ✅ **標準日誌** - 完整記錄執行狀況
- ✅ **Flask 偵測** - 自動識別 Flask 專案
- ✅ **效能優化** - 快速掃描與串流壓縮
- ✅ **無聲模式** - 支援 Windows 背景執行

## 快速開始

### 1. 執行程式（GUI 模式）

```bash
python flask_multi_backup.py
```

### 2. 無聲模式（背景執行）

```bash
# 不顯示 GUI，根據設定自動執行備份
pythonw flask_multi_backup.py --silent
```

或使用 VBS 啟動器（完全無聲）：
```bash
wscript silent_launcher.vbs
```

### 3. 設定自動啟動（Windows）

```bash
# 以系統管理員身分執行
setup_autostart.bat
```

詳細說明請參考：[WINDOWS_AUTOSTART_GUIDE.md](WINDOWS_AUTOSTART_GUIDE.md)

## 操作步驟（優化版）

### 專案管理
1. 切換到「專案管理」分頁
2. 點擊「新增專案」選擇 Flask 專案資料夾
3. 可新增多個專案到列表

### 備份設定
1. 切換到「備份設定」分頁
2. 設定備份目的地路徑
3. 調整排除模式（可選）
4. 啟用自動備份（可選）
   - **間隔模式**：每隔 N 小時自動備份
   - **固定時間模式**：在指定時間（如凌晨 2:00）自動備份（台灣時區）
5. 選擇是否壓縮為 ZIP
6. 點擊「儲存設定」

詳細說明請參考：[SCHEDULED_BACKUP_GUIDE.md](SCHEDULED_BACKUP_GUIDE.md)

### 執行備份
1. 切換到「執行備份」分頁
2. 點擊「開始備份所有專案」
3. 監看進度條和日誌
4. 可隨時點擊「停止備份」中斷

### 還原專案
1. 切換到「還原」分頁
2. 選擇備份資料夾
3. 選擇還原模式：
   - 僅還原已存在的專案
   - 還原所有備份中的專案
4. 點擊「開始還原」

## 系統需求

- Python 3.6+
- tkinter（Python 標準庫）
- Windows 10/11（自動啟動功能）

## 日誌檔案

所有操作都會記錄到標準日誌檔案：

- **一般日誌**：`%APPDATA%\FlaskMultiBackup\logs\backup.log`
- **錯誤日誌**：`%APPDATA%\FlaskMultiBackup\logs\error.log`

日誌特性：
- 自動輪轉（最大 5MB，保留 5 個備份）
- UTF-8 編碼支援中文
- 包含時間戳記和詳細錯誤資訊

快速開啟日誌資料夾：
```cmd
explorer %APPDATA%\FlaskMultiBackup\logs
```

## 設定檔

設定檔儲存位置：
```
%APPDATA%\FlaskMultiBackup\config.json
```

主要設定項目：
```json
{
  "projects": ["專案路徑列表"],
  "backup_path": "備份目的地",
  "exclude_patterns": ["排除模式列表"],
  "create_timestamp_folder": true,
  "compress_backup": false,
  "auto_backup": true,
  "backup_schedule_mode": "fixed_time",
  "backup_times": ["02:00", "14:00"],
  "timezone": "Asia/Taipei",
  "backup_interval_hours": 24
}
```

## 預設排除項目

- `__pycache__` - Python 快取資料夾
- `*.pyc` - Python 位元組碼檔案
- `.git` - Git 版本控制資料夾
- `venv`, `.venv` - Python 虛擬環境
- `node_modules` - Node.js 套件資料夾
- `.env` - 環境變數檔案
- `*.log` - 日誌檔案
- `.idea`, `.vscode` - IDE 設定資料夾
- `.pytest_cache` - Pytest 快取

## 備份檔案命名

### 一般備份
```
FlaskBackup_YYYYMMDD_HHMMSS/
├── project1/
├── project2/
└── project3/
```

### 壓縮備份
```
FlaskBackup_YYYYMMDD_HHMMSS/
└── all_projects.zip
```

時間戳記格式：`YYYYMMDD_HHMMSS`

## 優化項目說明

### 1. Flask 專案偵測改進
使用正規表達式精準識別：
- `from flask import ...`
- `import flask`
- `Flask(__name__)`
- `@app.route(...)`

### 2. 效能優化
- **單次檔案掃描**：避免重複遍歷目錄
- **串流 ZIP 壓縮**：直接寫入 ZIP，無需臨時資料夾
- **批次進度更新**：每 10 個檔案更新一次 UI

### 3. 執行緒安全
- 使用 `threading.Event()` 替代布林值
- 避免競態條件
- 支援隨時中斷操作

### 4. 輸入驗證
- 備份間隔限制在 1-720 小時
- 即時驗證防止無效輸入

### 5. 錯誤處理
- 完整的 try-except 區塊
- 詳細的錯誤日誌
- 友善的錯誤訊息

## 注意事項

1. **第一次使用**：請先設定專案和備份目的地
2. **權限問題**：備份到系統目錄需要系統管理員權限
3. **磁碟空間**：壓縮備份時確保有足夠空間
4. **定期檢查**：建議每月檢查一次備份結果
5. **網路磁碟**：備份到網路磁碟機需確保連線正常

## Windows 開機自動執行

支援四種自動啟動方式：

1. **工作排程器**（推薦）- 可設定延遲和條件
2. **啟動資料夾** - 最簡單
3. **註冊表 Run 鍵** - 系統級
4. **Windows 服務** - 無需登入

詳細設定請參考：[WINDOWS_AUTOSTART_GUIDE.md](WINDOWS_AUTOSTART_GUIDE.md)

## 常見問題

### Q: 如何確認備份成功？
A: 檢查 `%APPDATA%\FlaskMultiBackup\logs\backup.log` 查看執行記錄。

### Q: 備份時程式卡住？
A: 大型專案首次備份可能需要較長時間，請耐心等待。可點擊「停止備份」中斷。

### Q: 如何還原備份？
A: 切換到「還原」分頁，選擇備份資料夾後點擊「開始還原」。

### Q: 自動備份沒有執行？
A: 
1. 確認已啟用「自動備份」選項
2. 確認備份間隔時間設定正確
3. 檢查錯誤日誌 `error.log`
4. 確認程式有寫入備份目的地的權限

### Q: 如何關閉自動啟動？
A: 執行 `setup_autostart.bat` 選擇「[5] 移除所有自動啟動設定」。

## 授權

本專案為開源專案，可自由使用與修改。

## 更新日誌

### v2.1 (台灣時區固定時間備份)
- 🆕 **台灣時區固定時間備份** - 可設定特定時間（如凌晨 2:00）自動備份
- 🆕 **多時間點支援** - 可設定多個備份時間
- 🆕 **防重複機制** - 自動記錄備份日期，避免同一天重複執行
- 🆕 **時區支援** - 支援 Asia/Taipei 等多個時區
- 🆕 **靈活排程模式** - 間隔模式和固定時間模式可切換

### v2.0 (優化版)
- 新增多專案管理
- 新增還原功能
- 新增標準日誌框架
- 新增自動備份排程
- 效能優化（單次掃描、串流 ZIP）
- 執行緒安全改進
- Flask 偵測精準度提升
- Windows 自動啟動支援

### v1.0 (基礎版)
- 基礎單專案備份功能
- GUI 介面
- 排除模式設定
- ZIP 壓縮支援
