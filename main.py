import sys
import os
import keyboard
import atexit

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QSettings, QSharedMemory
from PyQt6.QtGui import QIcon, QFont
from qfluentwidgets import SystemTrayMenu, Action, FluentIcon as FIF, setTheme, Theme

from core.config import apply_logging_setting, log
from core.workers import STTWorker, DictationTypingWorker
from ui.subtitle import SubtitleWindow
from ui.settings import SettingsWindow, parse_shortcut

atexit.register(keyboard.unhook_all)

class HotkeySignals(QObject):
    pressed = pyqtSignal()
    released = pyqtSignal()

# ==========================================
# Main Application Manager
# ==========================================
class STTAppManager(QObject):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MySTT", "STTApp")

        self.subtitle_win = SubtitleWindow()
        self.subtitle_win.hide()

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic.svg")
        app_icon = QIcon(icon_path) if os.path.exists(icon_path) else FIF.MICROPHONE.icon()
        self.tray_icon = QSystemTrayIcon(app_icon, QApplication.instance())
        self.tray_icon.setToolTip("Qwen3-ASR 智能终端")

        self.tray_menu = SystemTrayMenu()

        self.settings_action = Action(FIF.SETTING, "设置")
        self.settings_action.triggered.connect(self.show_settings)
        self.tray_menu.addAction(self.settings_action)

        self.tray_menu.addSeparator()

        self.exit_action = Action(FIF.POWER_BUTTON, "退出")
        self.exit_action.triggered.connect(self.quit_app)
        self.tray_menu.addAction(self.exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        ws_url = self.settings.value("ws_url", "ws://127.0.0.1:8000/v1/audio/stream")
        self.worker = STTWorker(ws_url)
        self.worker.text_received.connect(self.on_text_received)
        self.worker.volume_changed.connect(self.subtitle_win.set_volume)
        self.worker.error_occurred.connect(self.on_worker_error)
        self.worker.finalized.connect(self.on_recognition_finalized)
        self.worker.start()

        self._pending_finalize_mode = None

        self.hotkey_signals = HotkeySignals()
        self.hotkey_signals.pressed.connect(self.handle_hotkey_press)
        self.hotkey_signals.released.connect(self.handle_hotkey_release)

        self.RELEASE_DEBOUNCE_MS = 200
        self.release_debounce_timer = QTimer()
        self.release_debounce_timer.setSingleShot(True)
        self.release_debounce_timer.timeout.connect(self.actual_hotkey_release)

        self.last_input_text = ""
        self.is_hotkey_physically_down = False

        self.typing_worker = DictationTypingWorker()
        self.typing_worker.clipboard_signal.connect(self.set_clipboard_text, Qt.ConnectionType.QueuedConnection)
        self.typing_worker.start()

        self.setup_hotkey()

    def set_clipboard_text(self, text):
        QApplication.clipboard().setText(text)

    def setup_hotkey(self):
        shortcut_str = self.settings.value("shortcut", "f10")
        keyboard.unhook_all()

        try:
            target_name, target_scan = parse_shortcut(shortcut_str)

            if target_name.startswith('key '):
                bind_key = target_scan
                is_modifier = False
            else:
                bind_key = target_name
                is_modifier = target_name in ['ctrl', 'right ctrl', 'left ctrl', 'alt', 'right alt', 'left alt', 'shift', 'right shift', 'left shift', 'windows', 'right windows', 'left windows']

            should_suppress = not is_modifier

            def on_press_cb(e):
                if target_name.startswith('key '):
                    if e.scan_code != target_scan: return
                else:
                    if str(e.name).lower() != target_name: return

                if getattr(self, 'is_hotkey_physically_down', False):
                    return
                self.is_hotkey_physically_down = True

                self.hotkey_signals.pressed.emit()

            def on_release_cb(e):
                if target_name.startswith('key '):
                    if e.scan_code != target_scan: return
                else:
                    if str(e.name).lower() != target_name: return

                self.is_hotkey_physically_down = False

                self.hotkey_signals.released.emit()

            keyboard.on_press_key(bind_key, on_press_cb, suppress=should_suppress)
            keyboard.on_release_key(bind_key, on_release_cb, suppress=should_suppress)
            log.info(f"快捷键就绪: {shortcut_str} (suppress={should_suppress})")
        except Exception as e:
            log.error(f"快捷键绑定失败 {shortcut_str}: {e}")
            self.tray_icon.showMessage("错误", f"无法绑定快捷键 {shortcut_str}", QSystemTrayIcon.MessageIcon.Warning)

    def handle_hotkey_press(self):
        if self.release_debounce_timer.isActive():
            self.release_debounce_timer.stop()
            return

        shortcut_mode = self.settings.value("shortcut_mode", "hold")

        if shortcut_mode == "toggle":
            if self.worker.is_recording:
                self.actual_hotkey_release()
                return
        else:
            if self.worker.is_recording:
                return

        self.worker.start_recording()
        self.last_input_text = ""
        self.worker.cancel_finalizing()
        self._pending_finalize_mode = None

        self.subtitle_win.clear_text_data()
        self.subtitle_win.morph_to_pill()

        self.subtitle_win.label.setText("")

        self.subtitle_win.setWindowOpacity(1.0)
        self.subtitle_win.adjustSize()
        self.subtitle_win.show()

    def on_text_received(self, text):
        mode = self.settings.value("output_mode", "subtitle")

        if mode == "subtitle" or mode == "input_clipboard":
            self.subtitle_win.update_text(text)
        elif mode == "input_sendinput":
            if not text:
                return

            self.subtitle_win.full_text = text
            self.subtitle_win.update_text("")

            common_len = len(os.path.commonprefix([self.last_input_text, text]))

            backspaces = len(self.last_input_text) - common_len
            if backspaces > 0:
                self.typing_worker.action_queue.put({'type': 'backspace', 'count': backspaces})

            new_part = text[common_len:]
            if new_part:
                self.typing_worker.action_queue.put({'type': 'text', 'text': new_part})

            self.last_input_text = text

    def handle_hotkey_release(self):
        shortcut_mode = self.settings.value("shortcut_mode", "hold")
        if shortcut_mode == "toggle":
            return

        self.release_debounce_timer.start(self.RELEASE_DEBOUNCE_MS)

    def actual_hotkey_release(self):
        if self.worker.is_recording:
            mode = self.settings.value("output_mode", "subtitle")
            self._pending_finalize_mode = mode
            self.worker.stop_recording()

    def on_recognition_finalized(self):
        mode = self._pending_finalize_mode or self.settings.value("output_mode", "subtitle")
        self._pending_finalize_mode = None
        auto_send = self.settings.value("auto_send_enabled", False, type=bool)
        auto_send_key = self.settings.value("auto_send_key", "enter")

        if not self.subtitle_win.full_text.strip():
            self.subtitle_win.start_fade_out()
            return

        if mode == "input_sendinput":
            self.subtitle_win.start_fade_out()
            if auto_send:
                self.typing_worker.action_queue.put({'type': 'auto_send', 'key_mode': auto_send_key})
        elif mode == "input_clipboard":
            self.subtitle_win.start_fade_out()
            self.typing_worker.action_queue.put({'type': 'paste', 'text': self.subtitle_win.full_text})
            if auto_send:
                self.typing_worker.action_queue.put({'type': 'auto_send', 'key_mode': auto_send_key})
        else:
            self.subtitle_win.morph_to_panel()

    def on_worker_error(self, err_msg):
        log.error(f"Worker Error: {err_msg}")
        self.subtitle_win.update_text(f"错误: {err_msg}")

    def show_settings(self):
        if hasattr(self, 'settings_dlg') and self.settings_dlg.isVisible():
            self.settings_dlg.activateWindow()
            return

        self.settings_dlg = SettingsWindow()
        self.settings_dlg.settings_changed.connect(self.on_settings_changed)
        self.settings_dlg.reset_pos_signal.connect(self.subtitle_win.reset_session_pos)
        self.settings_dlg.show()

    def on_settings_changed(self):
        self.subtitle_win.apply_styles()
        self.setup_hotkey()

        self.worker.reload_vad_settings()
        apply_logging_setting()

        new_ws_url = self.settings.value("ws_url", "ws://127.0.0.1:8000/v1/audio/stream")
        if new_ws_url != self.worker.ws_url:
            self.worker.update_url(new_ws_url)

    def quit_app(self):
        if self.worker:
            self.worker.shutdown()
        if hasattr(self, 'typing_worker') and self.typing_worker.isRunning():
            self.typing_worker.stop()
        QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)

    _single_instance = QSharedMemory("MySTT_STTApp_SingleInstance")
    if not _single_instance.create(1):
        log.warning("检测到程序已在运行, 本次启动退出.")
        try:
            QSystemTrayIcon(FIF.MICROPHONE.icon(), app).showMessage(
                "Qwen3-ASR 智能终端", "程序已在运行 (托盘区)。",
                QSystemTrayIcon.MessageIcon.Information, 3000
            )
        except Exception:
            pass
        sys.exit(0)

    app.setFont(QFont("Segoe UI", 10))
    setTheme(Theme.DARK)
    app.setQuitOnLastWindowClosed(False)
    apply_logging_setting()
    manager = STTAppManager()
    sys.exit(app.exec())
