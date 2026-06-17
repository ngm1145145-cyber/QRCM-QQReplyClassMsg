import sys
import os
import json
import time
import threading
import websocket
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PIL import Image
import pystray
from pystray import MenuItem as item
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox


# NapCat WebSocket默认配置
DEFAULT_WS_URL = "ws://127.0.0.1:3001/onebot/v11/ws"


def load_config():
    """加载配置文件"""
    config_file = "config.json"
    default_config = {
        "target_group_id": None,
        "ws_url": DEFAULT_WS_URL,
        "auto_reply_text": "好"
    }
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default_config
    return default_config


def save_config(config):
    """保存配置文件"""
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class Communicate(QObject):
    """用于线程间通信的信号"""
    show_notification = pyqtSignal(str, str, str)  # 群名, 昵称, 消息


class NotificationWindow(QWidget):
    """通知窗口 - 胶囊形状（左右半圆）"""

    def __init__(self, group_name, nickname, message_text, delay_ms=2000):
        super().__init__()
        self.group_name = group_name
        self.nickname = nickname
        self.message_text = message_text
        self.delay_ms = delay_ms  # 停留时间

        # 窗口设置
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
        self.setAttribute(Qt.WA_NoSystemBackground)

        # 窗口大小
        self.window_width = 300
        self.window_height = 60
        self.setFixedSize(self.window_width, self.window_height)

        # 屏幕居中顶部
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.window_width) // 2
        self.target_y = 10
        self.start_y = -self.window_height
        self.move(x, self.start_y)

        # 截断长消息
        display_msg = self.message_text
        if len(display_msg) > 24:
            display_msg = display_msg[:24] + "..."

        # 创建标题和消息标签
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

        # 滑入动画
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(300)  # 0.3秒
        self.animation.setStartValue(QPoint(x, self.start_y))
        self.animation.setEndValue(QPoint(x, self.target_y))
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()

        # delay_ms毫秒后开始滑出
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.start_slide_out)
        self.hide_timer.start(self.delay_ms)

    def paintEvent(self, event):
        """绘制胶囊形状（左右半圆）"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景色
        bg_color = QColor(44, 62, 80, 240)  # #2c3e50 带透明度
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)

        # 绘制胶囊形状
        radius = self.window_height // 2
        painter.drawRoundedRect(0, 0, self.window_width, self.window_height,
                                radius, radius)

    def start_slide_out(self):
        """开始滑出动画"""
        current_pos = self.pos()
        self.slide_out = QPropertyAnimation(self, b"pos")
        self.slide_out.setDuration(300)  # 0.3秒
        self.slide_out.setStartValue(current_pos)
        self.slide_out.setEndValue(QPoint(current_pos.x(), -self.window_height))
        self.slide_out.setEasingCurve(QEasingCurve.InCubic)
        self.slide_out.finished.connect(self.close)
        self.slide_out.start()

    def update_content(self, group_name, nickname, message_text):
        """更新通知内容并重置停留定时器"""
        self.group_name = group_name
        self.nickname = nickname
        self.message_text = message_text

        # 截断长消息
        display_msg = message_text
        if len(display_msg) > 24:
            display_msg = display_msg[:24] + "..."

        # 更新标签
        for child in self.findChildren(QLabel):
            text = child.text()
            if "·" in text:
                # 标题标签
                child.setText(f"{group_name}  ·  {nickname}")
            else:
                # 消息标签
                child.setText(display_msg)

        # 重新触发重绘
        self.update()

        # 重置停留定时器
        self.hide_timer.stop()
        self.hide_timer.start(self.delay_ms)


class ConfigWindow:
    """配置窗口 - 使用 tkinter"""

    def __init__(self):
        self.config = load_config()

        self.root = tk.Tk()
        self.root.title("设置")
        self.root.geometry("350x180")
        self.root.attributes('-topmost', True)

        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # 群号
        ttk.Label(frame, text="目标群号:", font=("微软雅黑", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.group_id_var = tk.StringVar(value=str(self.config.get("target_group_id", "")))
        ttk.Entry(frame, textvariable=self.group_id_var, width=30).grid(row=0, column=1, pady=5)

        # WebSocket端口
        ttk.Label(frame, text="WebSocket端口:", font=("微软雅黑", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.port_var = tk.StringVar(value=str(self.config.get("ws_port", 3001)))
        ttk.Entry(frame, textvariable=self.port_var, width=30).grid(row=1, column=1, pady=5)

        # 自动回复文本
        ttk.Label(frame, text="回复文本:", font=("微软雅黑", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        self.reply_var = tk.StringVar(value=self.config.get("auto_reply_text", "好"))
        ttk.Entry(frame, textvariable=self.reply_var, width=30).grid(row=2, column=1, pady=5)

        # 按钮
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=15)

        ttk.Button(button_frame, text="保存", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.root.destroy).pack(side=tk.LEFT, padx=5)

        self.root.mainloop()

    def save(self):
        """保存配置"""
        try:
            port = int(self.port_var.get())
            self.config["ws_port"] = port
            self.config["ws_url"] = f"ws://127.0.0.1:{port}/onebot/v11/ws"
        except ValueError:
            messagebox.showerror("错误", "端口必须是数字")
            return

        try:
            group_id = int(self.group_id_var.get())
            self.config["target_group_id"] = group_id
        except ValueError:
            messagebox.showerror("错误", "群号必须是数字")
            return

        self.config["auto_reply_text"] = self.reply_var.get()
        save_config(self.config)
        messagebox.showinfo("成功", "配置已保存，请重启程序生效")
        self.root.destroy()


class QQMonitor:
    """QQ消息监控主类"""

    def __init__(self, qt_app):
        self.qt_app = qt_app
        self.config = load_config()
        self.target_group_id = self.config.get("target_group_id", 0)
        self.ws_url = self.config.get("ws_url", DEFAULT_WS_URL)
        self.auto_reply_text = self.config.get("auto_reply_text", "好")
        self.reply_delay = self.config.get("reply_delay", 2)

        # 检查群号
        if not self.target_group_id or self.target_group_id == 0:
            print("[错误] 目标群号未配置，请先运行设置", flush=True)
            return

        self.ws = None
        self.monitoring = True
        self.current_notification = None

        # 通信信号
        self.comm = Communicate()
        self.comm.show_notification.connect(self.on_show_notification)

        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.start_monitoring)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        # 创建托盘
        self.create_tray_icon()

    def start_monitoring(self):
        """启动WebSocket监控"""
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
        """连接WebSocket"""

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

                    # 发送者信息（优先群昵称）
                    sender = data.get("sender", {})
                    nickname = sender.get("card", "").strip()
                    if not nickname:
                        nickname = sender.get("nickname", "未知用户")

                    # 过滤消息类型
                    if isinstance(raw_message, list):
                        skip_types = ["file", "image", "share", "json", "record", "video"]
                        for seg in raw_message:
                            if seg.get("type") in skip_types:
                                print(f"[调试] 跳过 {seg.get('type')} 类型消息", flush=True)
                                return

                        # 提取文本
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

                    # 弹出通知
                    self.comm.show_notification.emit(group_name, nickname, message_text)

                    # 立即发送回复
                    self.send_group_message(self.target_group_id, self.auto_reply_text)
                    print(f"[调试] 已发送回复: {self.auto_reply_text}", flush=True)

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

    def on_show_notification(self, group_name, nickname, message_text):
        """在主线程显示通知"""
        # 如果已有通知窗口，更新内容并重置定时器
        if self.current_notification is not None:
            try:
                if self.current_notification.isVisible():
                    self.current_notification.update_content(group_name, nickname, message_text)
                    return
            except RuntimeError:
                # 窗口已被删除
                pass

        # 创建新通知
        self.current_notification = NotificationWindow(group_name, nickname, message_text)
        self.current_notification.show()

    def send_group_message(self, group_id, message):
        """通过WebSocket发送群消息"""
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
        """创建系统托盘"""
        image = Image.new('RGB', (64, 64), color='#3498db')
        menu = (
            item('设置', lambda: self.open_config()),
            item('退出', lambda: self.exit_app()),
        )
        self.tray = pystray.Icon("ToastMonitor", image, "QQ消息通知", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def open_config(self):
        """打开设置窗口"""
        # 在新线程中运行tk窗口
        def run_tk():
            ConfigWindow()
        threading.Thread(target=run_tk, daemon=True).start()

    def exit_app(self):
        """退出"""
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
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        # 仅打开设置窗口
        ConfigWindow()
        return

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)  # 关闭窗口时不退出

    monitor = QQMonitor(qt_app)
    sys.exit(qt_app.exec_())


if __name__ == '__main__':
    main()
