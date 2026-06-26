"""
Flask 多專案備份與還原工具 - 優化版
整合版：支援多專案、還原功能、進度顯示、排程備份、標準日誌框架
"""

import os
import sys
import shutil
import json
import threading
import queue
import zipfile
import tkinter as tk
import logging
import logging.handlers
import re
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime, timedelta, time
from fnmatch import fnmatch
from typing import List, Tuple, Optional, Dict, Any

# 時區支援 (Python 3.9+)
try:
    from zoneinfo import ZoneInfo

    TIMEZONE_SUPPORT = True
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo

        TIMEZONE_SUPPORT = True
    except ImportError:
        ZoneInfo = None
        TIMEZONE_SUPPORT = False


# =============================================================================
# 設定檔儲存位置
# =============================================================================
CONFIG_DIR = Path(os.getenv("APPDATA", Path.home() / ".config")) / "FlaskMultiBackup"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_DIR = CONFIG_DIR / "logs"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# 日誌配置
# =============================================================================
def setup_logging() -> logging.Logger:
    """設定標準日誌框架"""
    logger = logging.getLogger("FlaskMultiBackup")
    logger.setLevel(logging.DEBUG)

    # 避免重複添加 handler
    if logger.handlers:
        return logger

    # 日誌格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 檔案 handler (按大小輪轉，最大 5MB，保留 5 個備份)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "backup.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # 錯誤專用日誌
    error_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "error.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(error_handler)

    return logger


# 初始化日誌
logger = setup_logging()


# =============================================================================
# 主要應用類別
# =============================================================================
class FlaskMultiBackupApp:
    def __init__(self, root=None):
        self.root = root
        self.config = self.load_config()
        self.backup_thread: Optional[threading.Thread] = None
        self.restore_thread: Optional[threading.Thread] = None

        # 使用 threading.Event 替代布林值（解決競態條件問題）
        self.stop_backup_event = threading.Event()
        self.stop_restore_event = threading.Event()

        self.msg_queue = queue.Queue(maxsize=1000)  # 限制佇列大小避免記憶體耗盡

        logger.info("應用程式初始化完成")

        if root:
            self.setup_gui()
            self.check_queue()
            self.check_auto_backup()

    def load_config(self) -> Dict[str, Any]:
        """載入設定檔"""
        default_config = {
            "projects": [],
            "backup_path": "",
            "exclude_patterns": [
                "__pycache__",
                "*.pyc",
                ".git",
                "venv",
                ".venv",
                "node_modules",
                ".env",
                "*.log",
                "*.tmp",
                ".pytest_cache",
                ".idea",
                ".vscode",
            ],
            "create_timestamp_folder": True,
            "compress_backup": False,
            "auto_backup": False,
            "backup_schedule_mode": "interval",  # 'interval' 或 'fixed_time'
            "backup_interval_hours": 24,
            "backup_times": ["02:00"],  # 固定時間備份（台灣時區），格式 HH:MM
            "timezone": "Asia/Taipei",  # 時區設定
            "last_backup_time": None,
            "last_backup_dates": {},  # 記錄每個時間點的最後備份日期 {time: date}
            "max_log_lines": 1000,  # 日誌區域最大行數
            "max_backup_count": 2,  # 備份目的地保留的最大備份數量（0=不限制）
        }

        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    default_config.update(loaded)
                logger.info(f"設定檔已載入: {CONFIG_FILE}")
            except Exception as e:
                logger.error(f"載入設定檔失敗: {e}")

        return default_config

    def save_config(self) -> bool:
        """儲存設定檔"""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info("設定檔已儲存")
            return True
        except Exception as e:
            logger.error(f"儲存設定檔失敗: {e}")
            return False

    def setup_gui(self):
        """設定 GUI 介面"""
        if self.root is None:
            return

        self.root.title("Flask 多專案備份與還原工具")
        self.root.geometry("900x750")
        self.root.minsize(800, 600)

        # 建立分頁
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # === 專案管理分頁 ===
        self.projects_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.projects_tab, text="專案管理")
        self.setup_projects_tab()

        # === 備份設定分頁 ===
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text="備份設定")
        self.setup_settings_tab()

        # === 備份執行分頁 ===
        self.backup_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.backup_tab, text="執行備份")
        self.setup_backup_tab()

        # === 還原分頁 ===
        self.restore_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.restore_tab, text="還原")
        self.setup_restore_tab()

        # 設定關閉事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """關閉視窗前的處理"""
        if self.root is None:
            return

        if self.backup_thread and self.backup_thread.is_alive():
            if messagebox.askyesno("確認", "備份正在進行中，確定要關閉嗎？"):
                self.stop_backup_event.set()
                self.root.after(1000, self.root.destroy)
            return
        self.root.destroy()

    def setup_projects_tab(self):
        """專案管理介面"""
        # 說明標籤
        ttk.Label(
            self.projects_tab,
            text="管理要備份的 Flask 專案列表",
            font=("Microsoft JhengHei", 12, "bold"),
        ).pack(pady=10)

        # 專案列表
        list_frame = ttk.Frame(self.projects_tab)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 建立 Treeview 顯示專案資訊
        columns = ("path", "name", "status")
        self.project_tree = ttk.Treeview(
            list_frame, columns=columns, show="headings", height=10
        )
        self.project_tree.heading("path", text="專案路徑")
        self.project_tree.heading("name", text="專案名稱")
        self.project_tree.heading("status", text="狀態")
        self.project_tree.column("path", width=450)
        self.project_tree.column("name", width=150)
        self.project_tree.column("status", width=150)

        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.project_tree.yview
        )
        self.project_tree.configure(yscrollcommand=scrollbar.set)

        self.project_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 按鈕框架
        btn_frame = ttk.Frame(self.projects_tab)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="➕ 新增專案", command=self.add_project).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(btn_frame, text="➖ 移除選取", command=self.remove_project).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            btn_frame, text="🔄 重新整理", command=self.refresh_project_list
        ).pack(side=tk.LEFT, padx=5)

        # 載入現有專案
        self.refresh_project_list()

    def setup_settings_tab(self):
        """備份設定介面"""
        # 備份目的地
        dest_frame = ttk.LabelFrame(self.settings_tab, text="備份目的地", padding=10)
        dest_frame.pack(fill=tk.X, padx=20, pady=10)

        self.backup_path_var = tk.StringVar(value=self.config.get("backup_path", ""))
        ttk.Entry(
            dest_frame, textvariable=self.backup_path_var, font=("Consolas", 10)
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(dest_frame, text="瀏覽...", command=self.select_backup_dir).pack(
            side=tk.RIGHT
        )

        # 排除設定
        exclude_frame = ttk.LabelFrame(self.settings_tab, text="排除模式", padding=10)
        exclude_frame.pack(fill=tk.X, padx=20, pady=10)

        self.exclude_var = tk.StringVar(
            value=",".join(self.config.get("exclude_patterns", []))
        )
        ttk.Label(
            exclude_frame, text="排除的檔案/資料夾 (逗號分隔，支援萬用字元 * ?):"
        ).pack(anchor=tk.W)
        ttk.Entry(
            exclude_frame, textvariable=self.exclude_var, font=("Consolas", 10)
        ).pack(fill=tk.X, pady=(5, 0))

        # 備份選項
        options_frame = ttk.LabelFrame(self.settings_tab, text="備份選項", padding=10)
        options_frame.pack(fill=tk.X, padx=20, pady=10)

        self.timestamp_var = tk.BooleanVar(
            value=self.config.get("create_timestamp_folder", True)
        )
        ttk.Checkbutton(
            options_frame, text="建立時間戳記資料夾", variable=self.timestamp_var
        ).pack(anchor=tk.W)

        self.compress_var = tk.BooleanVar(
            value=self.config.get("compress_backup", False)
        )
        ttk.Checkbutton(
            options_frame, text="壓縮為 ZIP 檔案", variable=self.compress_var
        ).pack(anchor=tk.W)

        # 備份保留數量設定
        retention_frame = ttk.Frame(options_frame)
        retention_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(retention_frame, text="保留最新備份數量 (0=不限制):").pack(side=tk.LEFT)
        self.max_backup_count_var = tk.StringVar(
            value=str(self.config.get("max_backup_count", 2))
        )
        if self.root is not None:
            vcmd_retention = (self.root.register(self.validate_retention_count), "%P")
        else:
            vcmd_retention = None
        self.retention_spinbox = ttk.Spinbox(
            retention_frame,
            from_=0,
            to=100,
            textvariable=self.max_backup_count_var,
            width=10,
            validate="key" if vcmd_retention else "none",
            validatecommand=vcmd_retention if vcmd_retention else "",
        )
        self.retention_spinbox.pack(side=tk.LEFT, padx=5)
        ttk.Label(retention_frame, text="個").pack(side=tk.LEFT)

        # 自動備份設定
        auto_frame = ttk.LabelFrame(self.settings_tab, text="自動備份", padding=10)
        auto_frame.pack(fill=tk.X, padx=20, pady=10)

        self.auto_backup_var = tk.BooleanVar(
            value=self.config.get("auto_backup", False)
        )
        ttk.Checkbutton(
            auto_frame, text="啟用自動備份", variable=self.auto_backup_var
        ).pack(anchor=tk.W)

        # 備份模式選擇
        mode_frame = ttk.Frame(auto_frame)
        mode_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Label(mode_frame, text="備份模式:").pack(side=tk.LEFT)
        self.schedule_mode_var = tk.StringVar(
            value=self.config.get("backup_schedule_mode", "interval")
        )
        mode_combo = ttk.Combobox(
            mode_frame,
            textvariable=self.schedule_mode_var,
            values=["interval", "fixed_time"],
            width=15,
            state="readonly",
        )
        mode_combo.pack(side=tk.LEFT, padx=5)
        mode_combo.bind("<<ComboboxSelected>>", self.on_schedule_mode_changed)

        ttk.Label(mode_frame, text="(interval=間隔, fixed_time=固定時間)").pack(
            side=tk.LEFT
        )

        # 間隔模式設定
        self.interval_frame = ttk.Frame(auto_frame)
        self.interval_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(self.interval_frame, text="備份間隔 (小時，1-720):").pack(
            side=tk.LEFT
        )

        # 驗證函數
        if self.root is not None:
            vcmd = (self.root.register(self.validate_interval), "%P")
        else:
            vcmd = None
        self.interval_var = tk.StringVar(
            value=str(self.config.get("backup_interval_hours", 24))
        )
        self.interval_spinbox = ttk.Spinbox(
            self.interval_frame,
            from_=1,
            to=720,
            textvariable=self.interval_var,
            width=10,
            validate="key" if vcmd else "none",
            validatecommand=vcmd if vcmd else "",
        )
        self.interval_spinbox.pack(side=tk.LEFT, padx=5)

        # 固定時間模式設定
        self.fixed_time_frame = ttk.LabelFrame(
            auto_frame, text="固定備份時間 (台灣時區)", padding=5
        )
        self.fixed_time_frame.pack(fill=tk.X, pady=(5, 0))

        # 時間選擇器
        time_select_frame = ttk.Frame(self.fixed_time_frame)
        time_select_frame.pack(fill=tk.X, pady=2)

        ttk.Label(time_select_frame, text="新增時間:").pack(side=tk.LEFT)

        # 小時選擇 (00-23)
        self.hour_var = tk.StringVar(value="02")
        hour_combo = ttk.Combobox(
            time_select_frame,
            textvariable=self.hour_var,
            values=[f"{h:02d}" for h in range(24)],
            width=5,
            state="readonly",
        )
        hour_combo.pack(side=tk.LEFT, padx=2)
        ttk.Label(time_select_frame, text=":").pack(side=tk.LEFT)

        # 分鐘選擇 (00, 15, 30, 45)
        self.minute_var = tk.StringVar(value="00")
        minute_combo = ttk.Combobox(
            time_select_frame,
            textvariable=self.minute_var,
            values=["00", "15", "30", "45"],
            width=5,
            state="readonly",
        )
        minute_combo.pack(side=tk.LEFT, padx=2)

        ttk.Button(
            time_select_frame, text="➕ 新增", command=self.add_backup_time
        ).pack(side=tk.LEFT, padx=5)

        # 已設定時間列表
        self.backup_times_listbox = tk.Listbox(self.fixed_time_frame, height=4)
        self.backup_times_listbox.pack(fill=tk.X, pady=2)

        # 載入已儲存的時間
        for time_str in self.config.get("backup_times", ["02:00"]):
            self.backup_times_listbox.insert(tk.END, time_str)

        ttk.Button(
            self.fixed_time_frame, text="🗑️ 移除選取", command=self.remove_backup_time
        ).pack(anchor=tk.W)

        # 時區顯示
        tz_frame = ttk.Frame(self.fixed_time_frame)
        tz_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(tz_frame, text="時區:").pack(side=tk.LEFT)
        self.timezone_var = tk.StringVar(
            value=self.config.get("timezone", "Asia/Taipei")
        )
        tz_combo = ttk.Combobox(
            tz_frame,
            textvariable=self.timezone_var,
            values=["Asia/Taipei", "Asia/Tokyo", "Asia/Seoul", "Asia/Shanghai", "UTC"],
            width=15,
            state="readonly",
        )
        tz_combo.pack(side=tk.LEFT, padx=5)

        # 根據目前模式顯示/隱藏對應框架
        self.on_schedule_mode_changed(None)

        # 儲存按鈕
        ttk.Button(
            self.settings_tab, text="💾 儲存設定", command=self.save_settings
        ).pack(pady=20)

    def setup_backup_tab(self):
        """備份執行介面"""
        # 操作按鈕
        btn_frame = ttk.Frame(self.backup_tab)
        btn_frame.pack(pady=20)

        self.backup_btn = ttk.Button(
            btn_frame,
            text="🚀 開始備份所有專案",
            command=self.start_backup_thread,
            style="Accent.TButton",
        )
        self.backup_btn.pack(side=tk.LEFT, padx=10)

        self.stop_btn = ttk.Button(
            btn_frame,
            text="⏹️ 停止備份",
            command=self.stop_backup_process,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        # 進度顯示
        progress_frame = ttk.LabelFrame(self.backup_tab, text="備份進度", padding=10)
        progress_frame.pack(fill=tk.X, padx=20, pady=10)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            length=400,
        )
        self.progress_bar.pack(fill=tk.X)

        self.status_label = ttk.Label(progress_frame, text="就緒")
        self.status_label.pack(pady=(5, 0))

        # 日誌區域
        log_frame = ttk.LabelFrame(self.backup_tab, text="備份日誌", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 9), height=15
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 清空日誌按鈕
        ttk.Button(log_frame, text="清空日誌", command=self.clear_log).pack(
            anchor=tk.E, pady=(5, 0)
        )

    def setup_restore_tab(self):
        """還原介面"""
        ttk.Label(
            self.restore_tab,
            text="從備份還原專案",
            font=("Microsoft JhengHei", 12, "bold"),
        ).pack(pady=10)

        # 選擇備份資料夾
        backup_select_frame = ttk.Frame(self.restore_tab)
        backup_select_frame.pack(fill=tk.X, padx=20, pady=10)

        self.restore_backup_path = tk.StringVar()
        ttk.Entry(
            backup_select_frame,
            textvariable=self.restore_backup_path,
            font=("Consolas", 10),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(
            backup_select_frame,
            text="選擇備份資料夾...",
            command=self.select_restore_backup,
        ).pack(side=tk.RIGHT)

        # 還原選項
        options_frame = ttk.LabelFrame(self.restore_tab, text="還原選項", padding=10)
        options_frame.pack(fill=tk.X, padx=20, pady=10)

        self.restore_mode_var = tk.StringVar(value="matched")
        ttk.Radiobutton(
            options_frame,
            text="僅還原已存在的專案（依資料夾名稱比對）",
            variable=self.restore_mode_var,
            value="matched",
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            options_frame,
            text="還原所有備份中的專案（自動建立資料夾）",
            variable=self.restore_mode_var,
            value="all",
        ).pack(anchor=tk.W)

        # 還原按鈕
        btn_frame = ttk.Frame(self.restore_tab)
        btn_frame.pack(pady=10)

        self.restore_btn = ttk.Button(
            btn_frame,
            text="⏪ 開始還原",
            command=self.start_restore_thread,
            style="Accent.TButton",
        )
        self.restore_btn.pack(side=tk.LEFT, padx=5)

        self.stop_restore_btn = ttk.Button(
            btn_frame,
            text="⏹️ 停止還原",
            command=self.stop_restore_process,
            state=tk.DISABLED,
        )
        self.stop_restore_btn.pack(side=tk.LEFT, padx=5)

        # 進度顯示
        progress_frame = ttk.LabelFrame(self.restore_tab, text="還原進度", padding=10)
        progress_frame.pack(fill=tk.X, padx=20, pady=10)

        self.restore_progress_var = tk.DoubleVar()
        self.restore_progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.restore_progress_var,
            maximum=100,
            mode="determinate",
        )
        self.restore_progress_bar.pack(fill=tk.X)

        self.restore_status_label = ttk.Label(progress_frame, text="就緒")
        self.restore_status_label.pack(pady=(5, 0))

        # 還原日誌
        restore_log_frame = ttk.LabelFrame(self.restore_tab, text="還原日誌", padding=5)
        restore_log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.restore_log = scrolledtext.ScrolledText(
            restore_log_frame, wrap=tk.WORD, font=("Consolas", 9), height=10
        )
        self.restore_log.pack(fill=tk.BOTH, expand=True)

        # 清空日誌按鈕
        ttk.Button(
            restore_log_frame, text="清空日誌", command=self.clear_restore_log
        ).pack(anchor=tk.E, pady=(5, 0))

    def validate_interval(self, value: str) -> bool:
        """驗證備份間隔輸入"""
        if value == "":
            return True
        try:
            num = int(value)
            return 1 <= num <= 720
        except ValueError:
            return False

    def validate_retention_count(self, value: str) -> bool:
        """驗證保留備份數量輸入"""
        if value == "":
            return True
        try:
            num = int(value)
            return 0 <= num <= 100
        except ValueError:
            return False

    def on_schedule_mode_changed(self, event):
        """當備份模式改變時"""
        mode = self.schedule_mode_var.get()
        if mode == "interval":
            self.interval_frame.pack(fill=tk.X, pady=(5, 0))
            self.fixed_time_frame.pack_forget()
        else:
            self.interval_frame.pack_forget()
            self.fixed_time_frame.pack(fill=tk.X, pady=(5, 0))

    def add_backup_time(self):
        """新增備份時間"""
        hour = self.hour_var.get()
        minute = self.minute_var.get()
        time_str = f"{hour}:{minute}"

        # 檢查是否已存在
        existing = list(self.backup_times_listbox.get(0, tk.END))
        if time_str in existing:
            messagebox.showwarning("提示", f"時間 {time_str} 已存在")
            return

        self.backup_times_listbox.insert(tk.END, time_str)
        logger.info(f"新增備份時間: {time_str}")

    def remove_backup_time(self):
        """移除選取的備份時間"""
        selection = self.backup_times_listbox.curselection()
        if selection:
            time_str = self.backup_times_listbox.get(selection[0])
            self.backup_times_listbox.delete(selection[0])
            logger.info(f"移除備份時間: {time_str}")

    def refresh_project_list(self):
        """重新整理專案列表"""
        for item in self.project_tree.get_children():
            self.project_tree.delete(item)

        for project_path in self.config.get("projects", []):
            p = Path(project_path)
            status = "✅ 存在" if p.exists() else "❌ 不存在"
            flask_indicator = ""
            if p.exists():
                is_flask = self.check_is_flask_project(project_path)
                if is_flask:
                    flask_indicator = " 🌶️ Flask"
                else:
                    flask_indicator = " 📁 一般"

            self.project_tree.insert(
                "", tk.END, values=(project_path, p.name, status + flask_indicator)
            )

    def check_is_flask_project(self, path: str) -> bool:
        """檢查是否為 Flask 專案（使用正規表達式改進準確性）"""
        try:
            # Flask 專案特徵的正規表達式模式
            patterns = [
                r"^\s*from\s+flask\s+import\s+",  # from flask import
                r"^\s*import\s+flask\s*$",  # import flask
                r"^\s*from\s+flask\.\w+\s+import\s+",  # from flask.xxx import
                r"Flask\s*\(\s*__name__\s*\)",  # Flask(__name__)
                r"app\s*=\s*Flask\s*\(",  # app = Flask(
                r"@app\.route\s*\(",  # @app.route(
            ]

            compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

            for item in os.listdir(path):
                if item.endswith(".py"):
                    file_path = os.path.join(path, item)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            for pattern in compiled_patterns:
                                if pattern.search(content):
                                    logger.debug(f"在 {file_path} 偵測到 Flask 模式")
                                    return True
                    except Exception as e:
                        logger.warning(f"無法讀取檔案 {file_path}: {e}")
                        continue
        except Exception as e:
            logger.error(f"檢查 Flask 專案時發生錯誤: {e}")
        return False

    def add_project(self):
        """新增專案"""
        path = filedialog.askdirectory(title="選擇 Flask 專案資料夾")
        if path:
            if path not in self.config["projects"]:
                self.config["projects"].append(path)
                self.save_config()
                self.refresh_project_list()
                self.log(f"已新增專案: {path}")
                logger.info(f"新增專案: {path}")
            else:
                messagebox.showwarning("提示", "此專案已在列表中")

    def remove_project(self):
        """移除選取專案"""
        selection = self.project_tree.selection()
        if selection:
            item = self.project_tree.item(selection[0])
            path = item["values"][0]
            if path in self.config["projects"]:
                self.config["projects"].remove(path)
                self.save_config()
                self.refresh_project_list()
                self.log(f"已移除專案: {path}")
                logger.info(f"移除專案: {path}")

    def select_backup_dir(self):
        """選擇備份目錄"""
        path = filedialog.askdirectory(title="選擇備份儲存位置")
        if path:
            self.backup_path_var.set(path)

    def save_settings(self):
        """儲存設定（加入輸入驗證）"""
        self.config["backup_path"] = self.backup_path_var.get()
        self.config["exclude_patterns"] = [
            p.strip() for p in self.exclude_var.get().split(",") if p.strip()
        ]
        self.config["create_timestamp_folder"] = self.timestamp_var.get()
        self.config["compress_backup"] = self.compress_var.get()
        self.config["auto_backup"] = self.auto_backup_var.get()

        # 儲存備份排程模式
        self.config["backup_schedule_mode"] = self.schedule_mode_var.get()

        # 儲存時區
        self.config["timezone"] = self.timezone_var.get()

        # 驗證並儲存備份間隔
        try:
            interval = int(self.interval_var.get())
            if 1 <= interval <= 720:
                self.config["backup_interval_hours"] = interval
            else:
                raise ValueError("間隔必須在 1-720 小時之間")
        except ValueError as e:
            messagebox.showerror("錯誤", f"備份間隔設定無效: {e}")
            logger.error(f"備份間隔設定無效: {e}")
            return

        # 驗證並儲存保留備份數量
        try:
            max_count = int(self.max_backup_count_var.get())
            if 0 <= max_count <= 100:
                self.config["max_backup_count"] = max_count
            else:
                raise ValueError("保留數量必須在 0-100 之間")
        except ValueError as e:
            messagebox.showerror("錯誤", f"保留備份數量設定無效: {e}")
            logger.error(f"保留備份數量設定無效: {e}")
            return

        # 儲存固定時間列表
        backup_times = list(self.backup_times_listbox.get(0, tk.END))
        if not backup_times:
            backup_times = ["02:00"]  # 預設值
        self.config["backup_times"] = backup_times

        if self.save_config():
            messagebox.showinfo("成功", "設定已儲存！")
            logger.info("設定已儲存")
        else:
            messagebox.showerror("錯誤", "儲存設定失敗，請檢查權限")

    def check_queue(self):
        """檢查並處理佇列中的訊息（優化效能）"""
        processed = 0
        max_per_cycle = 50  # 每個週期最多處理 50 條訊息

        while not self.msg_queue.empty() and processed < max_per_cycle:
            try:
                msg = self.msg_queue.get_nowait()
                action = msg[0]

                if action == "log":
                    self._log_to_widget(msg[1])
                elif action == "restore_log":
                    self._log_to_restore_widget(msg[1])
                elif action == "progress":
                    self.progress_var.set(msg[1])
                elif action == "restore_progress":
                    self.restore_progress_var.set(msg[1])
                elif action == "status":
                    self.status_label.config(text=msg[1])
                elif action == "restore_status":
                    self.restore_status_label.config(text=msg[1])
                elif action == "messagebox_info":
                    messagebox.showinfo(msg[1], msg[2])
                elif action == "messagebox_warn":
                    messagebox.showwarning(msg[1], msg[2])
                elif action == "messagebox_error":
                    messagebox.showerror(msg[1], msg[2])
                elif action == "backup_done":
                    self.backup_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                elif action == "backup_start":
                    self.backup_btn.config(state=tk.DISABLED)
                    self.stop_btn.config(state=tk.NORMAL)
                elif action == "restore_done":
                    self.restore_btn.config(state=tk.NORMAL)
                    self.stop_restore_btn.config(state=tk.DISABLED)
                elif action == "restore_start":
                    self.restore_btn.config(state=tk.DISABLED)
                    self.stop_restore_btn.config(state=tk.NORMAL)

                processed += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"處理佇列訊息時發生錯誤: {e}")

        if self.root:
            self.root.after(100, self.check_queue)

    def log(self, message: str):
        """記錄日誌 (Thread-safe public interface)"""
        try:
            self.msg_queue.put(("log", message), block=False)
        except queue.Full:
            logger.warning(f"訊息佇列已滿，丟棄訊息: {message}")

    def _log_to_widget(self, message: str):
        """實際寫入 Widget (僅限主執行緒呼叫)"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}\n"

        self.log_text.insert(tk.END, log_msg)

        # 限制日誌行數
        max_lines = self.config.get("max_log_lines", 1000)
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > max_lines:
            self.log_text.delete("1.0", f"{line_count - max_lines}.0")

        self.log_text.see(tk.END)

    def clear_log(self):
        """清空備份日誌"""
        self.log_text.delete(1.0, tk.END)

    def should_exclude(self, item_name: str, exclude_list: List[str]) -> bool:
        """檢查是否應排除"""
        for pattern in exclude_list:
            pattern = pattern.strip()
            if pattern:
                if fnmatch(item_name, pattern):
                    return True
                if item_name == pattern:
                    return True
        return False

    def start_backup_thread(self):
        """在背景執行緒開始備份"""
        self.stop_backup_event.clear()
        self.backup_thread = threading.Thread(
            target=self.backup_all_projects, daemon=True
        )
        self.backup_thread.start()

    def stop_backup_process(self):
        """停止備份（使用 threading.Event）"""
        self.stop_backup_event.set()
        self.log("正在停止備份...")
        logger.info("使用者要求停止備份")

    def collect_files_to_backup(
        self, projects: List[str], exclude_list: List[str]
    ) -> List[Tuple[str, Path]]:
        """
        收集所有需要備份的檔案（單次遍歷優化）
        回傳: [(原始路徑, 相對路徑), ...]
        """
        files_to_backup = []

        for project_path in projects:
            p_path = Path(project_path)
            if not p_path.exists():
                logger.warning(f"專案不存在: {project_path}")
                continue

            for root, dirs, files in os.walk(project_path):
                # 排除資料夾（原地修改 dirs 會影響 os.walk 的後續遍歷）
                dirs[:] = [d for d in dirs if not self.should_exclude(d, exclude_list)]

                for file in files:
                    if self.should_exclude(file, exclude_list):
                        continue

                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(p_path)
                    files_to_backup.append((str(file_path), rel_path))

                    # 檢查停止信號
                    if self.stop_backup_event.is_set():
                        logger.info("檔案收集被中斷")
                        return files_to_backup

        return files_to_backup

    def backup_all_projects(self):
        """備份所有專案（優化版）"""
        self.msg_queue.put(("backup_start", None))
        self.msg_queue.put(("progress", 0))
        logger.info("開始備份所有專案")

        try:
            projects = self.config.get("projects", [])
            dst_base = self.config.get("backup_path")
            exclude_list = self.config.get("exclude_patterns", [])

            if not projects:
                self.msg_queue.put(
                    ("messagebox_warn", "警告", "請先新增要備份的專案！")
                )
                self.msg_queue.put(("backup_done", None))
                logger.warning("無專案可備份")
                return

            if not dst_base:
                self.msg_queue.put(("messagebox_warn", "警告", "請設定備份目的地！"))
                self.msg_queue.put(("backup_done", None))
                logger.warning("未設定備份目的地")
                return

            # 建立備份根目錄
            if self.config.get("create_timestamp_folder", True):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                root_backup_dir = Path(dst_base) / f"FlaskBackup_{timestamp}"
            else:
                root_backup_dir = Path(dst_base) / "FlaskBackup"

            root_backup_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"開始備份到: {root_backup_dir}")
            logger.info(f"備份目標: {root_backup_dir}")

            # 使用優化的單次遍歷收集檔案
            self.log("正在掃描檔案...")
            files_to_backup = self.collect_files_to_backup(projects, exclude_list)
            total_files = len(files_to_backup)

            if self.stop_backup_event.is_set():
                self.log("備份已取消")
                logger.info("備份在檔案掃描後被取消")
                self.msg_queue.put(("backup_done", None))
                return

            self.log(f"預計備份 {total_files} 個檔案")
            logger.info(f"預計備份 {total_files} 個檔案")

            if total_files == 0:
                self.msg_queue.put(
                    ("messagebox_warn", "警告", "沒有找到可備份的檔案！")
                )
                self.msg_queue.put(("backup_done", None))
                return

            # 執行備份
            copied_files = 0
            compress_backup = self.config.get("compress_backup", False)

            if compress_backup:
                # ZIP 壓縮備份（串流寫入，無需臨時資料夾）
                zip_path = root_backup_dir / "all_projects.zip"
                copied_files = self.backup_to_zip(
                    files_to_backup, projects, zip_path, total_files
                )
            else:
                # 一般複製備份
                copied_files = self.backup_to_folders(
                    files_to_backup, projects, root_backup_dir, total_files
                )

            if self.stop_backup_event.is_set():
                self.log("備份已取消")
                logger.info("備份被取消")
            else:
                # 更新最後備份時間
                self.config["last_backup_time"] = datetime.now().isoformat()
                self.save_config()

                self.msg_queue.put(("progress", 100))
                self.msg_queue.put(("status", "備份完成！"))
                self.log(f"\n✅ 所有專案備份完成！共 {copied_files} 個檔案")
                logger.info(f"備份完成，共 {copied_files} 個檔案")

                # 自動清理舊備份
                cleanup_msg = self.cleanup_old_backups(dst_base)
                if cleanup_msg:
                    self.log(cleanup_msg)

                if not self.config.get("silent_mode", False):
                    self.msg_queue.put(
                        (
                            "messagebox_info",
                            "完成",
                            f"備份成功完成！\n位置: {root_backup_dir}",
                        )
                    )

        except Exception as e:
            error_msg = f"備份過程中發生錯誤: {str(e)}"
            self.log(f"❌ {error_msg}")
            logger.exception("備份過程中發生錯誤")
            self.msg_queue.put(("messagebox_error", "錯誤", error_msg))
        finally:
            self.msg_queue.put(("backup_done", None))

    def backup_to_folders(
        self,
        files_to_backup: List[Tuple[str, Path]],
        projects: List[str],
        root_backup_dir: Path,
        total_files: int,
    ) -> int:
        """備份到資料夾（優化版）"""
        copied = 0
        project_paths = {Path(p).name: Path(p) for p in projects}

        for idx, (src_file, rel_path) in enumerate(files_to_backup):
            if self.stop_backup_event.is_set():
                return copied

            src_path = Path(src_file)

            # 找出對應的專案
            project_name = None
            for pname, ppath in project_paths.items():
                try:
                    src_path.relative_to(ppath)
                    project_name = pname
                    break
                except ValueError:
                    continue

            if project_name is None:
                logger.warning(f"無法確定檔案所屬專案: {src_file}")
                continue

            # 建立目標路徑
            dst_file = root_backup_dir / project_name / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                shutil.copy2(src_file, dst_file)
                copied += 1

                # 每 10 個檔案更新一次進度（減少 UI 更新頻率）
                if idx % 10 == 0 or idx == total_files - 1:
                    progress = ((idx + 1) / total_files) * 100
                    self.msg_queue.put(("progress", progress))
                    self.msg_queue.put(
                        (
                            "status",
                            f"複製中... {idx + 1}/{total_files} 檔案 ({progress:.1f}%)",
                        )
                    )

            except Exception as e:
                error_msg = f"無法複製 {src_file}: {str(e)}"
                self.log(f"  ⚠️ {error_msg}")
                logger.warning(error_msg)

        return copied

    def backup_to_zip(
        self,
        files_to_backup: List[Tuple[str, Path]],
        projects: List[str],
        zip_path: Path,
        total_files: int,
    ) -> int:
        """備份到 ZIP（串流寫入，無需臨時資料夾）"""
        copied = 0
        project_paths = {Path(p).name: Path(p) for p in projects}

        try:
            with zipfile.ZipFile(
                zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6
            ) as zipf:
                for idx, (src_file, rel_path) in enumerate(files_to_backup):
                    if self.stop_backup_event.is_set():
                        logger.info("ZIP 壓縮被中斷")
                        return copied

                    src_path = Path(src_file)

                    # 找出對應的專案
                    project_name = None
                    for pname, ppath in project_paths.items():
                        try:
                            src_path.relative_to(ppath)
                            project_name = pname
                            break
                        except ValueError:
                            continue

                    if project_name is None:
                        logger.warning(f"無法確定檔案所屬專案: {src_file}")
                        continue

                    # 在 ZIP 中的路徑
                    arcname = f"{project_name}/{rel_path}"

                    try:
                        zipf.write(src_file, arcname)
                        copied += 1

                        # 每 10 個檔案更新一次進度
                        if idx % 10 == 0 or idx == total_files - 1:
                            progress = ((idx + 1) / total_files) * 100
                            self.msg_queue.put(("progress", progress))
                            self.msg_queue.put(
                                (
                                    "status",
                                    f"壓縮中... {idx + 1}/{total_files} 檔案 ({progress:.1f}%)",
                                )
                            )

                    except Exception as e:
                        error_msg = f"無法壓縮 {src_file}: {str(e)}"
                        self.log(f"  ⚠️ {error_msg}")
                        logger.warning(error_msg)

        except Exception as e:
            logger.error(f"建立 ZIP 檔案時發生錯誤: {e}")
            raise

        return copied

    def select_restore_backup(self):
        """選擇要還原的備份"""
        path = filedialog.askdirectory(
            title="選擇備份資料夾 (例如 FlaskBackup_20230101_120000)"
        )
        if path:
            self.restore_backup_path.set(path)

    def start_restore_thread(self):
        """在背景執行緒開始還原"""
        self.stop_restore_event.clear()
        self.restore_thread = threading.Thread(target=self.start_restore, daemon=True)
        self.restore_thread.start()

    def stop_restore_process(self):
        """停止還原（使用 threading.Event）"""
        self.stop_restore_event.set()
        self.restore_log_insert("正在停止還原...\n")
        logger.info("使用者要求停止還原")

    def restore_log_insert(self, message: str):
        """還原日誌寫入（Thread-safe）"""
        try:
            self.msg_queue.put(("restore_log", message), block=False)
        except queue.Full:
            logger.warning(f"還原訊息佇列已滿")

    def _log_to_restore_widget(self, message: str):
        """實際寫入還原日誌 Widget"""
        self.restore_log.insert(tk.END, message)
        self.restore_log.see(tk.END)

    def clear_restore_log(self):
        """清空還原日誌"""
        self.restore_log.delete(1.0, tk.END)

    def start_restore(self):
        """開始還原（加入進度追蹤）"""
        self.msg_queue.put(("restore_start", None))
        self.msg_queue.put(("restore_progress", 0))
        logger.info("開始還原程序")

        backup_path = self.restore_backup_path.get()
        if not backup_path:
            self.msg_queue.put(("messagebox_warn", "警告", "請選擇備份資料夾！"))
            self.msg_queue.put(("restore_done", None))
            return

        backup_dir = Path(backup_path)
        if not backup_dir.exists():
            self.msg_queue.put(("messagebox_error", "錯誤", "備份資料夾不存在！"))
            self.msg_queue.put(("restore_done", None))
            return

        if not messagebox.askyesno("確認", "還原將會覆蓋現有檔案，確定要繼續嗎？"):
            self.msg_queue.put(("restore_done", None))
            return

        restore_mode = self.restore_mode_var.get()
        restore_count = 0

        try:
            # 收集還原項目
            restore_items = []

            if restore_mode == "matched":
                current_projects = {
                    Path(p).name: Path(p) for p in self.config.get("projects", [])
                }

                for project_item in backup_dir.iterdir():
                    if project_item.is_dir() and project_item.name in current_projects:
                        restore_items.append(
                            (project_item, current_projects[project_item.name])
                        )
                    elif project_item.is_file() and project_item.suffix == ".zip":
                        project_name = project_item.stem
                        if project_name in current_projects:
                            restore_items.append(
                                (project_item, current_projects[project_name])
                            )
            else:
                base_path = (
                    Path(self.config.get("projects", ["."])[0]).parent
                    if self.config.get("projects")
                    else Path(".")
                )

                for project_item in backup_dir.iterdir():
                    if project_item.is_dir():
                        target_path = base_path / project_item.name
                        target_path.mkdir(parents=True, exist_ok=True)
                        restore_items.append((project_item, target_path))
                    elif project_item.is_file() and project_item.suffix == ".zip":
                        target_path = base_path / project_item.stem
                        target_path.mkdir(parents=True, exist_ok=True)
                        restore_items.append((project_item, target_path))

            if not restore_items:
                self.msg_queue.put(
                    ("messagebox_warn", "警告", "沒有找到可還原的項目！")
                )
                self.msg_queue.put(("restore_done", None))
                return

            # 計算總檔案數（用於進度追蹤）
            total_files = 0
            for src, dst in restore_items:
                if src.is_dir():
                    total_files += len(list(src.rglob("*")))
                elif src.suffix == ".zip":
                    with zipfile.ZipFile(src, "r") as zf:
                        total_files += len(zf.namelist())

            self.restore_log_insert(f"開始還原: {backup_path}\n{'=' * 50}\n")
            logger.info(f"還原目標: {backup_path}, 預計 {total_files} 個檔案")

            processed_files = 0

            # 執行還原
            for idx, (src_item, target_path) in enumerate(restore_items):
                if self.stop_restore_event.is_set():
                    self.restore_log_insert("\n還原已取消\n")
                    logger.info("還原被取消")
                    self.msg_queue.put(("restore_done", None))
                    return

                if src_item.is_dir():
                    count = self.restore_project_with_progress(
                        src_item, target_path, total_files, processed_files
                    )
                    processed_files += count
                    restore_count += count
                    self.restore_log_insert(
                        f"✅ 已還原 {src_item.name}: {count} 個檔案\n"
                    )
                elif src_item.suffix == ".zip":
                    count = self.restore_project_zip_with_progress(
                        src_item, target_path, total_files, processed_files
                    )
                    processed_files += count
                    restore_count += count
                    self.restore_log_insert(
                        f"✅ 已還原 {src_item.stem} (ZIP): {count} 個檔案\n"
                    )

                # 更新進度
                progress = ((idx + 1) / len(restore_items)) * 100
                self.msg_queue.put(("restore_progress", progress))
                self.msg_queue.put(
                    ("restore_status", f"已還原 {idx + 1}/{len(restore_items)} 個專案")
                )

            self.restore_log_insert(
                f"\n{'=' * 50}\n還原完成！共 {restore_count} 個檔案"
            )
            logger.info(f"還原完成，共 {restore_count} 個檔案")
            self.msg_queue.put(
                ("messagebox_info", "完成", f"還原成功！共還原 {restore_count} 個檔案")
            )

        except Exception as e:
            error_msg = f"還原過程中發生錯誤: {str(e)}"
            self.restore_log_insert(f"\n❌ {error_msg}\n")
            logger.exception("還原過程中發生錯誤")
            self.msg_queue.put(("messagebox_error", "錯誤", error_msg))
        finally:
            self.msg_queue.put(("restore_done", None))

    def restore_project_with_progress(
        self, src_dir: Path, dst_dir: Path, total_files: int, current_files: int
    ) -> int:
        """還原單一專案（含進度追蹤）"""
        count = 0
        all_files = list(src_dir.rglob("*"))

        for idx, file_path in enumerate(all_files):
            if self.stop_restore_event.is_set():
                return count

            if file_path.is_file():
                rel_path = file_path.relative_to(src_dir)
                target_file = dst_dir / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, target_file)
                count += 1

                # 每 10 個檔案更新進度
                if (current_files + idx) % 10 == 0:
                    progress = ((current_files + idx) / total_files) * 100
                    self.msg_queue.put(("restore_progress", progress))
                    self.msg_queue.put(
                        (
                            "restore_status",
                            f"還原中... {current_files + idx}/{total_files} 檔案",
                        )
                    )

        return count

    def restore_project_zip_with_progress(
        self, zip_file: Path, dst_dir: Path, total_files: int, current_files: int
    ) -> int:
        """還原單一專案 ZIP（含進度追蹤）"""
        with zipfile.ZipFile(zip_file, "r") as zipf:
            file_list = zipf.namelist()
            count = len(file_list)

            # 逐個解壓以顯示進度
            for idx, member in enumerate(file_list):
                if self.stop_restore_event.is_set():
                    return idx

                zipf.extract(member, dst_dir)

                # 每 10 個檔案更新進度
                if (current_files + idx) % 10 == 0:
                    progress = ((current_files + idx) / total_files) * 100
                    self.msg_queue.put(("restore_progress", progress))
                    self.msg_queue.put(
                        (
                            "restore_status",
                            f"解壓中... {current_files + idx}/{total_files} 檔案",
                        )
                    )

        return count

    def get_current_time_in_timezone(self) -> datetime:
        """取得設定時區的目前時間"""
        tz_name = self.config.get("timezone", "Asia/Taipei")

        if TIMEZONE_SUPPORT and ZoneInfo:
            try:
                tz = ZoneInfo(tz_name)
                return datetime.now(tz)
            except Exception as e:
                logger.warning(f"無法載入時區 {tz_name}: {e}，使用系統時間")

        # 降級處理：使用系統本地時間
        return datetime.now()

    def check_auto_backup(self):
        """檢查是否需要自動備份（支援間隔和固定時間模式）"""
        if not self.config.get("auto_backup", False):
            return

        schedule_mode = self.config.get("backup_schedule_mode", "interval")

        try:
            if schedule_mode == "fixed_time":
                self._check_fixed_time_backup()
            else:
                self._check_interval_backup()
        except Exception as e:
            logger.error(f"檢查自動備份時發生錯誤: {e}")

        # 每分鐘檢查一次（固定時間模式需要更頻繁檢查）
        check_interval = 60000 if schedule_mode == "fixed_time" else 3600000
        if self.root:
            self.root.after(check_interval, self.check_auto_backup)

    def _check_interval_backup(self):
        """檢查間隔備份模式"""
        last_backup = self.config.get("last_backup_time")
        interval = self.config.get("backup_interval_hours", 24)

        if last_backup:
            last_time = datetime.fromisoformat(last_backup)
            next_backup = last_time + timedelta(hours=interval)

            if datetime.now() >= next_backup:
                self._trigger_auto_backup("間隔備份")

    def _check_fixed_time_backup(self):
        """檢查固定時間備份模式（台灣時區）"""
        backup_times = self.config.get("backup_times", ["02:00"])
        last_backup_dates = self.config.get("last_backup_dates", {})

        # 取得設定時區的目前時間
        current_time = self.get_current_time_in_timezone()
        current_date = current_time.date()
        current_hour = current_time.hour
        current_minute = current_time.minute

        logger.debug(
            f"檢查固定時間備份 - 目前時間: {current_time.strftime('%Y-%m-%d %H:%M')}"
        )

        for time_str in backup_times:
            try:
                hour, minute = map(int, time_str.split(":"))

                # 檢查是否已到達備份時間（允許 5 分鐘內的誤差）
                if current_hour == hour and abs(current_minute - minute) <= 5:
                    # 檢查今天是否已備份
                    last_date_str = last_backup_dates.get(time_str)
                    today_str = current_date.isoformat()

                    if last_date_str != today_str:
                        # 今天還沒備份，執行備份
                        self._trigger_auto_backup(f"固定時間備份 {time_str}")

                        # 更新最後備份日期
                        last_backup_dates[time_str] = today_str
                        self.config["last_backup_dates"] = last_backup_dates
                        self.save_config()
                        break  # 一次只執行一個時間點的備份

            except ValueError:
                logger.error(f"無效的時間格式: {time_str}")
                continue

    def _trigger_auto_backup(self, trigger_type: str):
        """觸發自動備份"""
        self.log(f"執行自動備份 ({trigger_type})...")
        logger.info(f"觸發自動備份 ({trigger_type})")
        self.start_backup_thread()

    def cleanup_old_backups(self, backup_base_path: str) -> Optional[str]:
        """
        清理舊備份，只保留最新的 N 個備份。
        透過備份資料夾/ZIP 的名稱時間戳記排序，刪除最舊的。
        回傳清理結果的日誌訊息，若無需清理則回傳 None。
        """
        max_count = self.config.get("max_backup_count", 2)
        if max_count <= 0:
            logger.debug("備份保留數量設為 0（不限制），跳過清理")
            return None

        backup_base = Path(backup_base_path)
        if not backup_base.exists():
            logger.warning(f"備份目的地不存在，跳過清理: {backup_base}")
            return None

        # 收集所有 FlaskBackup_ 開頭的資料夾和 ZIP 檔
        backup_items = []
        backup_pattern = re.compile(r"^FlaskBackup_(\d{8}_\d{6})$")
        zip_pattern = re.compile(r"^FlaskBackup_(\d{8}_\d{6})\.zip$")

        for item in backup_base.iterdir():
            if item.is_dir():
                match = backup_pattern.match(item.name)
                if match:
                    try:
                        timestamp = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
                        backup_items.append((timestamp, item))
                    except ValueError:
                        continue
            elif item.is_file() and item.suffix == ".zip":
                # 嘗試匹配 ZIP 檔案名稱
                zip_name_match = zip_pattern.match(item.name)
                if zip_name_match:
                    try:
                        timestamp = datetime.strptime(zip_name_match.group(1), "%Y%m%d_%H%M%S")
                        backup_items.append((timestamp, item))
                    except ValueError:
                        continue

        if len(backup_items) <= max_count:
            logger.debug(f"備份數量 ({len(backup_items)}) 未超過上限 ({max_count})，無需清理")
            return None

        # 依時間戳記排序（最新的在前）
        backup_items.sort(key=lambda x: x[0], reverse=True)

        # 要刪除的項目（保留前 N 個，刪除其餘的）
        items_to_delete = backup_items[max_count:]
        deleted_count = 0
        freed_size = 0

        for timestamp, item in items_to_delete:
            try:
                if item.is_dir():
                    # 計算資料夾大小
                    dir_size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    freed_size += dir_size
                    shutil.rmtree(item)
                    deleted_count += 1
                    logger.info(f"已刪除舊備份資料夾: {item.name}")
                elif item.is_file():
                    freed_size += item.stat().st_size
                    item.unlink()
                    deleted_count += 1
                    logger.info(f"已刪除舊備份檔案: {item.name}")
            except Exception as e:
                logger.error(f"刪除舊備份失敗 {item}: {e}")
                self.log(f"  ⚠️ 刪除舊備份失敗: {item.name} - {e}")

        if deleted_count > 0:
            # 格式化釋放的空間大小
            if freed_size >= 1024 * 1024 * 1024:
                size_str = f"{freed_size / (1024 * 1024 * 1024):.2f} GB"
            elif freed_size >= 1024 * 1024:
                size_str = f"{freed_size / (1024 * 1024):.2f} MB"
            elif freed_size >= 1024:
                size_str = f"{freed_size / 1024:.2f} KB"
            else:
                size_str = f"{freed_size} Bytes"

            msg = f"🗑️ 已清理 {deleted_count} 個舊備份，釋放 {size_str} 空間（保留最新 {max_count} 個）"
            logger.info(msg)
            return msg

        return None


def main():
    if "--silent" in sys.argv:
        # 命令列模式（無 GUI）
        logger.info("以無聲模式啟動")
        app = FlaskMultiBackupApp()
        app.config["silent_mode"] = True
        app.backup_all_projects()
    else:
        # GUI 模式
        root = tk.Tk()
        app = FlaskMultiBackupApp(root)

        # 設定視窗置中
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")

        root.mainloop()


if __name__ == "__main__":
    main()
