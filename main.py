import sys
import os
import re
import json
import time
import threading
import subprocess
import websocket
import winsound
import ctypes
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox
from PyQt5.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PIL import Image
import pystray
from pystray import MenuItem as item
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox


def resource_path(relative_path):
    """获取资源文件路径，支持打包后的exe"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)


def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    config_file = "config.json"
    default_config = {
        "target_group_id": 955256911,
        "ws_host": "127.0.0.1",
        "ws_port": 3001,
        "ws_path": "/onebot/v11/ws",
        "auto_reply_text": "好",
        "max_message_length": 24,
        "enable_auto_reply": True,
        "enable_top_popup": True,
        "enable_right_popup": True,
        "enable_toast": True,
        "enable_center_popup": False,
        "enable_center_win32": True,
        "enable_center_tk": True,
        "enable_center_pyqt": True,
        "enable_center_fluent": True,
        "enable_sound": True,
        "popup_start_hour": 12,
        "popup_start_minute": 0,
        "popup_end_hour": 12,
        "popup_end_minute": 43,
        "audio_file": "audio.WAV"
    }

    if not os.path.exists(config_file):
        print(f"[调试] 配置文件不存在，创建默认配置: {config_file}", flush=True)
        save_config(default_config)
        return default_config

    config = None
    content = ""
    content_fixed = ""
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            content = f.read()
        content_fixed = content
        content_fixed = re.sub(r'\bNone\b', 'null', content_fixed)
        content_fixed = re.sub(r'\bTrue\b', 'true', content_fixed)
        content_fixed = re.sub(r'\bFalse\b', 'false', content_fixed)
        config = json.loads(content_fixed)
    except Exception as e:
        print(f"[错误] 配置文件读取失败: {e}", flush=True)
        return default_config

    if content != content_fixed:
        print(f"[调试] 配置文件已自动修正", flush=True)
        save_config(config)

    for key, value in default_config.items():
        if key == "target_group_id":
            if key not in config:
                config[key] = value
        else:
            if key not in config:
                config[key] = value

    if "ws_url" in config and "ws_port" not in config:
        old_url = config.pop("ws_url")
        try:
            parts = old_url.replace("ws://", "").split("/")
            host_port = parts[0].split(":")
            config["ws_host"] = host_port[0]
            config["ws_port"] = int(host_port[1]) if len(host_port) > 1 else 3001
            config["ws_path"] = "/" + "/".join(parts[1:])
        except:
            config["ws_host"] = "127.0.0.1"
            config["ws_port"] = 3001
            config["ws_path"] = "/onebot/v11/ws"

    return config


def save_config(config):
    """保存配置文件"""
    config_file = "config.json"
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        print(f"[调试] 配置已保存", flush=True)
    except Exception as e:
        print(f"[调试] 配置保存失败: {e}", flush=True)


def get_ws_url(config):
    """根据配置构建WebSocket URL"""
    return f"ws://{config.get('ws_host', '127.0.0.1')}:{config.get('ws_port', 3001)}{config.get('ws_path', '/onebot/v11/ws')}"


class Communicate(QObject):
    show_top_notification = pyqtSignal(str, str, str)
    show_right_notification = pyqtSignal(str, str, str)
    show_center_popup = pyqtSignal(str, str, str)
    show_toast = pyqtSignal(str, str)


class TopNotificationWindow(QWidget):
    """上方弹出通知 - 胶囊形状，停留5秒"""

    def __init__(self, group_name, nickname, message_text, delay_ms=5000):
        super().__init__()
        self.group_name = group_name
        self.nickname = nickname
        self.message_text = message_text
        self.delay_ms = delay_ms

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        self.window_width = 300
        self.window_height = 60
        self.setFixedSize(self.window_width, self.window_height)

        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.window_width) // 2
        self.target_y = 10
        self.start_y = -self.window_height
        self.move(x, self.start_y)

        display_msg = self.truncate_message(self.message_text)

        title_label = QLabel(f"{group_name}  ·  {nickname}", self)
        title_label.setFont(QFont("微软雅黑", 9, QFont.Bold))
        title_label.setStyleSheet("color: #3498db; background: transparent;")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setGeometry(0, 10, self.window_width, 20)

        msg_label = QLabel(display_msg, self)
        msg_label.setFont(QFont("微软雅黑", 9))
        msg_label.setStyleSheet("color: white; background: transparent;")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setGeometry(0, 32, self.window_width, 20)

        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(300)
        self.animation.setStartValue(QPoint(x, self.start_y))
        self.animation.setEndValue(QPoint(x, self.target_y))
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.start_slide_out)
        self.hide_timer.start(self.delay_ms)

    def truncate_message(self, message_text):
        max_length = 24
        if len(message_text) > max_length:
            return message_text[:max_length] + "..."
        return message_text

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bg_color = QColor(44, 62, 80, 240)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        radius = self.window_height // 2
        painter.drawRoundedRect(0, 0, self.window_width, self.window_height, radius, radius)

    def start_slide_out(self):
        current_pos = self.pos()
        self.slide_out = QPropertyAnimation(self, b"pos")
        self.slide_out.setDuration(300)
        self.slide_out.setStartValue(current_pos)
        self.slide_out.setEndValue(QPoint(current_pos.x(), -self.window_height))
        self.slide_out.setEasingCurve(QEasingCurve.InCubic)
        self.slide_out.finished.connect(self.close)
        self.slide_out.start()

    def update_content(self, group_name, nickname, message_text):
        self.group_name = group_name
        self.nickname = nickname
        self.message_text = message_text
        display_msg = self.truncate_message(message_text)
        for child in self.findChildren(QLabel):
            text = child.text()
            if "·" in text:
                child.setText(f"{group_name}  ·  {nickname}")
            else:
                child.setText(display_msg)
        self.update()
        self.hide_timer.stop()
        self.hide_timer.start(self.delay_ms)


class RightNotificationWindow(QWidget):
    """右侧弹出通知 - 长方形，停留4秒"""

    def __init__(self, group_name, nickname, message_text, delay_ms=4000):
        super().__init__()
        self.group_name = group_name
        self.nickname = nickname
        self.message_text = message_text
        self.delay_ms = delay_ms

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        self.window_width = 280
        self.window_height = 80
        self.setFixedSize(self.window_width, self.window_height)

        screen = QApplication.primaryScreen().geometry()
        self.target_x = screen.width() - self.window_width - 10
        self.start_x = screen.width() + self.window_width
        self.move(self.start_x, screen.height() // 2 - self.window_height // 2)

        display_msg = self.truncate_message(self.message_text)

        title_label = QLabel(f"{group_name}  ·  {nickname}", self)
        title_label.setFont(QFont("微软雅黑", 10, QFont.Bold))
        title_label.setStyleSheet("color: #3498db; background: transparent;")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setGeometry(0, 15, self.window_width, 25)

        msg_label = QLabel(display_msg, self)
        msg_label.setFont(QFont("微软雅黑", 9))
        msg_label.setStyleSheet("color: white; background: transparent;")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setGeometry(0, 45, self.window_width, 25)

        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(300)
        y = screen.height() // 2 - self.window_height // 2
        self.animation.setStartValue(QPoint(self.start_x, y))
        self.animation.setEndValue(QPoint(self.target_x, y))
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.start_slide_out)
        self.hide_timer.start(self.delay_ms)

    def truncate_message(self, message_text):
        max_length = 30
        if len(message_text) > max_length:
            return message_text[:max_length] + "..."
        return message_text

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bg_color = QColor(44, 62, 80, 240)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.window_width, self.window_height, 10, 10)

    def start_slide_out(self):
        current_pos = self.pos()
        screen = QApplication.primaryScreen().geometry()
        self.slide_out = QPropertyAnimation(self, b"pos")
        self.slide_out.setDuration(300)
        self.slide_out.setStartValue(current_pos)
        self.slide_out.setEndValue(QPoint(screen.width() + self.window_width, current_pos.y()))
        self.slide_out.setEasingCurve(QEasingCurve.InCubic)
        self.slide_out.finished.connect(self.close)
        self.slide_out.start()

    def update_content(self, group_name, nickname, message_text):
        self.group_name = group_name
        self.nickname = nickname
        self.message_text = message_text
        display_msg = self.truncate_message(message_text)
        for child in self.findChildren(QLabel):
            text = child.text()
            if "·" in text:
                child.setText(f"{group_name}  ·  {nickname}")
            else:
                child.setText(display_msg)
        self.update()
        self.hide_timer.stop()
        self.hide_timer.start(self.delay_ms)


class ToastNotification:
    """Windows Toast通知"""

    def __init__(self, title, content):
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, content, duration=5, threaded=True)
        except ImportError:
            print(f"[Toast] {title}: {content}", flush=True)


class ConfigWindow:
    """配置窗口 - 使用 tkinter"""

    def __init__(self, monitor=None):
        self.monitor = monitor
        self.config = load_config()

        self.root = tk.Tk()
        self.root.title("设置")
        self.root.geometry("450x650")
        self.root.attributes('-topmost', True)

        canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        frame = ttk.Frame(scrollable_frame, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0

        ttk.Label(frame, text="【基础设置】", font=("微软雅黑", 11, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=10)
        row += 1

        ttk.Label(frame, text="目标群号:", font=("微软雅黑", 10)).grid(row=row, column=0, sticky=tk.W, pady=5)
        self.group_id_var = tk.StringVar(value=str(self.config.get("target_group_id", "")))
        ttk.Entry(frame, textvariable=self.group_id_var, width=30).grid(row=row, column=1, pady=5)
        row += 1

        ttk.Label(frame, text="WebSocket主机:", font=("微软雅黑", 10)).grid(row=row, column=0, sticky=tk.W, pady=5)
        self.host_var = tk.StringVar(value=self.config.get("ws_host", "127.0.0.1"))
        ttk.Entry(frame, textvariable=self.host_var, width=30).grid(row=row, column=1, pady=5)
        row += 1

        ttk.Label(frame, text="WebSocket端口:", font=("微软雅黑", 10)).grid(row=row, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.StringVar(value=str(self.config.get("ws_port", 3001)))
        ttk.Entry(frame, textvariable=self.port_var, width=30).grid(row=row, column=1, pady=5)
        row += 1

        ttk.Label(frame, text="回复文本:", font=("微软雅黑", 10)).grid(row=row, column=0, sticky=tk.W, pady=5)
        self.reply_var = tk.StringVar(value=self.config.get("auto_reply_text", "好"))
        ttk.Entry(frame, textvariable=self.reply_var, width=30).grid(row=row, column=1, pady=5)
        row += 1

        ttk.Label(frame, text="【功能开关】", font=("微软雅黑", 11, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=10)
        row += 1

        self.auto_reply_var = tk.BooleanVar(value=self.config.get("enable_auto_reply", True))
        ttk.Checkbutton(frame, text="启用自动回复", variable=self.auto_reply_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        self.top_popup_var = tk.BooleanVar(value=self.config.get("enable_top_popup", True))
        ttk.Checkbutton(frame, text="启用上方弹出通知", variable=self.top_popup_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        self.right_popup_var = tk.BooleanVar(value=self.config.get("enable_right_popup", True))
        ttk.Checkbutton(frame, text="启用右侧弹出通知", variable=self.right_popup_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        self.toast_var = tk.BooleanVar(value=self.config.get("enable_toast", True))
        ttk.Checkbutton(frame, text="启用Toast通知", variable=self.toast_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        self.center_popup_var = tk.BooleanVar(value=self.config.get("enable_center_popup", False))
        ttk.Checkbutton(frame, text="启用中间弹窗", variable=self.center_popup_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        self.sound_var = tk.BooleanVar(value=self.config.get("enable_sound", True))
        ttk.Checkbutton(frame, text="启用声音提示", variable=self.sound_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        ttk.Label(frame, text="【中间弹窗类型】", font=("微软雅黑", 11, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=10)
        row += 1

        ttk.Label(frame, text="（需先启用中间弹窗）", font=("微软雅黑", 9, "italic")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=2)
        row += 1

        self.center_win32_var = tk.BooleanVar(value=self.config.get("enable_center_win32", True))
        ttk.Checkbutton(frame, text="系统级(Win32) MessageBox", variable=self.center_win32_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        self.center_fluent_var = tk.BooleanVar(value=self.config.get("enable_center_fluent", True))
        ttk.Checkbutton(frame, text="Fluent MessageBox", variable=self.center_fluent_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        ttk.Label(frame, text="【中间弹窗时间段】", font=("微软雅黑", 11, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=10)
        row += 1

        ttk.Label(frame, text="开始时间 (小时:分钟):", font=("微软雅黑", 10)).grid(row=row, column=0, sticky=tk.W, pady=5)
        self.start_hour_var = tk.StringVar(value=str(self.config.get("popup_start_hour", 12)))
        self.start_min_var = tk.StringVar(value=str(self.config.get("popup_start_minute", 0)))
        time_frame1 = ttk.Frame(frame)
        ttk.Entry(time_frame1, textvariable=self.start_hour_var, width=5).pack(side=tk.LEFT)
        ttk.Label(time_frame1, text=":").pack(side=tk.LEFT)
        ttk.Entry(time_frame1, textvariable=self.start_min_var, width=5).pack(side=tk.LEFT)
        time_frame1.grid(row=row, column=1, pady=5)
        row += 1

        ttk.Label(frame, text="结束时间 (小时:分钟):", font=("微软雅黑", 10)).grid(row=row, column=0, sticky=tk.W, pady=5)
        self.end_hour_var = tk.StringVar(value=str(self.config.get("popup_end_hour", 12)))
        self.end_min_var = tk.StringVar(value=str(self.config.get("popup_end_minute", 43)))
        time_frame2 = ttk.Frame(frame)
        ttk.Entry(time_frame2, textvariable=self.end_hour_var, width=5).pack(side=tk.LEFT)
        ttk.Label(time_frame2, text=":").pack(side=tk.LEFT)
        ttk.Entry(time_frame2, textvariable=self.end_min_var, width=5).pack(side=tk.LEFT)
        time_frame2.grid(row=row, column=1, pady=5)
        row += 1

        ttk.Label(frame, text="【音频设置】", font=("微软雅黑", 11, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=10)
        row += 1

        ttk.Label(frame, text="音频文件:", font=("微软雅黑", 10)).grid(row=row, column=0, sticky=tk.W, pady=5)
        self.audio_var = tk.StringVar(value=self.config.get("audio_file", "audio.WAV"))
        ttk.Entry(frame, textvariable=self.audio_var, width=30).grid(row=row, column=1, pady=5)
        row += 1

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)
        ttk.Button(button_frame, text="保存", command=self.save).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="取消", command=self.root.destroy).pack(side=tk.LEFT, padx=10)

        self.root.mainloop()

    def save(self):
        try:
            port = int(self.port_var.get())
            if port <= 0 or port > 65535:
                raise ValueError("端口号无效")
        except ValueError:
            messagebox.showerror("错误", "端口必须是1-65535的数字")
            return

        try:
            group_id = int(self.group_id_var.get())
            if group_id <= 0:
                raise ValueError("群号无效")
        except ValueError:
            group_id_str = self.group_id_var.get().strip()
            if group_id_str.lower() in ["none", "null", "0", ""]:
                group_id = None
            else:
                messagebox.showerror("错误", "群号必须是正整数或None")
                return

        try:
            start_hour = int(self.start_hour_var.get())
            start_min = int(self.start_min_var.get())
            end_hour = int(self.end_hour_var.get())
            end_min = int(self.end_min_var.get())
            if not (0 <= start_hour <= 23 and 0 <= start_min <= 59 and 0 <= end_hour <= 23 and 0 <= end_min <= 59):
                raise ValueError("时间无效")
        except ValueError:
            messagebox.showerror("错误", "时间格式错误，小时0-23，分钟0-59")
            return

        new_config = {
            "target_group_id": group_id,
            "ws_host": self.host_var.get().strip(),
            "ws_port": port,
            "auto_reply_text": self.reply_var.get(),
            "enable_auto_reply": self.auto_reply_var.get(),
            "enable_top_popup": self.top_popup_var.get(),
            "enable_right_popup": self.right_popup_var.get(),
            "enable_toast": self.toast_var.get(),
            "enable_center_popup": self.center_popup_var.get(),
            "enable_center_win32": self.center_win32_var.get(),
            "enable_center_fluent": self.center_fluent_var.get(),
            "enable_sound": self.sound_var.get(),
            "popup_start_hour": start_hour,
            "popup_start_minute": start_min,
            "popup_end_hour": end_hour,
            "popup_end_minute": end_min,
            "audio_file": self.audio_var.get().strip(),
            "max_message_length": self.config.get("max_message_length", 24)
        }

        save_config(new_config)

        if self.monitor:
            self.monitor.update_config(new_config)

        messagebox.showinfo("成功", "配置已保存，立即生效")
        self.root.destroy()


class QQMonitor:
    """QQ消息监控主类"""

    def __init__(self, qt_app):
        self.qt_app = qt_app
        self.config = load_config()
        self.target_group_id = self.config.get("target_group_id", 0)
        self.ws_url = get_ws_url(self.config)

        if not self.target_group_id or self.target_group_id == 0:
            print("[错误] 目标群号未配置，请先运行设置", flush=True)
            return

        self.ws = None
        self.monitoring = True
        self.current_top_notification = None
        self.current_right_notification = None

        self.comm = Communicate()
        self.comm.show_top_notification.connect(self.on_show_top_notification)
        self.comm.show_right_notification.connect(self.on_show_right_notification)
        self.comm.show_center_popup.connect(self.on_show_center_popup)
        self.comm.show_toast.connect(self.on_show_toast)

        self.monitor_thread = threading.Thread(target=self.start_monitoring)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        self.create_tray_icon()

    def update_config(self, new_config):
        """更新配置，立即生效"""
        self.config = new_config
        self.target_group_id = self.config.get("target_group_id", 0)
        self.ws_url = get_ws_url(self.config)
        print("[调试] 配置已更新，立即生效", flush=True)

    def is_in_popup_time(self):
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute

        start_hour = self.config.get("popup_start_hour", 12)
        start_min = self.config.get("popup_start_minute", 0)
        end_hour = self.config.get("popup_end_hour", 12)
        end_min = self.config.get("popup_end_minute", 43)

        start_time = start_hour * 60 + start_min
        end_time = end_hour * 60 + end_min
        current_time = current_hour * 60 + current_minute

        return start_time <= current_time <= end_time

    def play_sound(self):
        if not self.config.get("enable_sound", True):
            return

        audio_file = self.config.get("audio_file", "audio.WAV")
        audio_path = resource_path(audio_file)

        if os.path.exists(audio_path):
            try:
                if audio_file.endswith(".WAV") or audio_file.endswith(".wav"):
                    winsound.PlaySound(audio_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    print(f"[调试] 播放音频: {audio_path}", flush=True)
                    try:
                        import pygame
                        pygame.mixer.init()
                        pygame.mixer.music.load(audio_path)
                        pygame.mixer.music.play()
                    except ImportError:
                        print("[调试] pygame未安装，无法播放MP3", flush=True)
            except Exception as e:
                print(f"[调试] 播放音频失败: {e}", flush=True)
        else:
            print(f"[调试] 音频文件不存在: {audio_path}", flush=True)

    def show_center_win32(self, group_name, nickname, message_text):
        """显示系统级(Win32) MessageBox"""
        def run_win32():
            ctypes.windll.user32.MessageBoxW(
                None,
                f"【{nickname}】：{message_text}",
                group_name,
                0x00000040 | 0x00000000
            )
        threading.Thread(target=run_win32, daemon=True).start()

    def show_center_fluent(self, group_name, nickname, message_text):
        """显示Fluent MessageBox"""
        msg_box_path = resource_path("mg/MessageBox.exe")
        if os.path.exists(msg_box_path):
            try:
                subprocess.Popen([
                    msg_box_path,
                    f"【{nickname}】：{message_text}",
                    group_name,
                    "0",
                    "64",
                    "0"
                ], cwd=resource_path("mg"))
            except Exception as e:
                print(f"[调试] Fluent MessageBox调用失败: {e}", flush=True)
        else:
            print(f"[调试] Fluent MessageBox不存在: {msg_box_path}", flush=True)

    def start_monitoring(self):
        max_attempts = 3
        attempt = 0

        while attempt < max_attempts and self.monitoring:
            attempt += 1
            print(f"[调试] 连接NapCat... (尝试 {attempt}/{max_attempts})", flush=True)
            try:
                self.connect_websocket()
            except Exception as e:
                print(f"[调试] 连接失败: {e}", flush=True)
            if attempt < max_attempts and self.monitoring:
                time.sleep(5)

    def connect_websocket(self):
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if data.get("post_type") == "meta_event":
                    return

                if data.get("post_type") == "message":
                    msg_type = data.get("message_type")
                    if msg_type != "group":
                        return

                    group_id = data.get("group_id")
                    if group_id != self.target_group_id:
                        return

                    raw_message = data.get("message", "")
                    group_name = data.get("group_name", "未知群")

                    sender = data.get("sender", {})
                    nickname = sender.get("card", "").strip()
                    if not nickname:
                        nickname = sender.get("nickname", "未知用户")

                    if isinstance(raw_message, list):
                        skip_types = ["file", "image", "share", "json", "record", "video"]
                        for seg in raw_message:
                            if seg.get("type") in skip_types:
                                print(f"[调试] 跳过 {seg.get('type')} 类型消息", flush=True)
                                return

                        message_text = ""
                        for seg in raw_message:
                            if seg.get("type") == "text":
                                message_text += seg.get("data", {}).get("text", "")

                        if not message_text.strip():
                            return
                    else:
                        message_text = str(raw_message)
                        if not message_text.strip():
                            return

                    print(f"[调试] 收到消息: [{group_name}] [{nickname}]: {message_text}", flush=True)

                    if self.config.get("enable_top_popup", True):
                        self.comm.show_top_notification.emit(group_name, nickname, message_text)

                    if self.config.get("enable_right_popup", True):
                        self.comm.show_right_notification.emit(group_name, nickname, message_text)

                    if self.config.get("enable_toast", True):
                        toast_content = f"【{nickname}】：{message_text}"
                        self.comm.show_toast.emit(nickname, toast_content)

                    center_popup_enabled = self.config.get("enable_center_popup", False)
                    if center_popup_enabled or self.is_in_popup_time():
                        self.comm.show_center_popup.emit(group_name, nickname, message_text)

                    if self.config.get("enable_auto_reply", True):
                        self.send_group_message(self.target_group_id, self.config.get("auto_reply_text", "好"))
                        print(f"[调试] 已发送回复: {self.config.get('auto_reply_text', '好')}", flush=True)

                    self.play_sound()

            except Exception as e:
                print(f"[调试] 处理消息错误: {e}", flush=True)

        def on_error(ws, error):
            print(f"[调试] WebSocket错误: {error}", flush=True)

        def on_close(ws, *args):
            print("[调试] WebSocket连接关闭", flush=True)

        def on_open(ws):
            print("[调试] WebSocket连接成功", flush=True)
            ws.send(json.dumps({
                "action": "get_status",
                "params": {},
                "echo": "auth"
            }))

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        self.ws.run_forever()

    def on_show_top_notification(self, group_name, nickname, message_text):
        if self.current_top_notification is not None:
            try:
                if self.current_top_notification.isVisible():
                    self.current_top_notification.update_content(group_name, nickname, message_text)
                    return
            except RuntimeError:
                pass
        self.current_top_notification = TopNotificationWindow(group_name, nickname, message_text)
        self.current_top_notification.show()

    def on_show_right_notification(self, group_name, nickname, message_text):
        if self.current_right_notification is not None:
            try:
                if self.current_right_notification.isVisible():
                    self.current_right_notification.update_content(group_name, nickname, message_text)
                    return
            except RuntimeError:
                pass
        self.current_right_notification = RightNotificationWindow(group_name, nickname, message_text)
        self.current_right_notification.show()

    def on_show_center_popup(self, group_name, nickname, message_text):
        if self.config.get("enable_center_win32", True):
            self.show_center_win32(group_name, nickname, message_text)
        if self.config.get("enable_center_fluent", True):
            self.show_center_fluent(group_name, nickname, message_text)

    def on_show_toast(self, title, content):
        ToastNotification(title, content)

    def send_group_message(self, group_id, message):
        if not self.ws:
            return
        try:
            send_data = {
                "action": "send_group_msg",
                "params": {
                    "group_id": group_id,
                    "message": message
                },
                "echo": f"send_{time.time()}"
            }
            self.ws.send(json.dumps(send_data))
        except Exception as e:
            print(f"[调试] 发送消息失败: {e}", flush=True)

    def create_tray_icon(self):
        image = Image.new('RGB', (64, 64), color='#3498db')
        menu = (
            item('设置', lambda: self.open_config()),
            item('退出', lambda: self.exit_app()),
        )
        self.tray = pystray.Icon("QQMonitor", image, "QQ消息监控", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def open_config(self):
        def run_tk():
            ConfigWindow(self)
        threading.Thread(target=run_tk, daemon=True).start()

    def exit_app(self):
        self.monitoring = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        if hasattr(self, 'tray'):
            self.tray.stop()
        QApplication.quit()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        ConfigWindow()
        return

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)

    monitor = QQMonitor(qt_app)
    sys.exit(qt_app.exec_())


if __name__ == '__main__':
    main()
