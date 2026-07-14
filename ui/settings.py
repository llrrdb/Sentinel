import os
import keyboard

from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QFormLayout, QHBoxLayout, QColorDialog, QFrame, QTextBrowser, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QColor, QIcon
from qfluentwidgets import (
    ScrollArea, Slider, ComboBox, PushButton, LineEdit, SwitchButton, ColorPickerButton,
    MSFluentWindow, NavigationItemPosition, InfoBar, InfoBarPosition, Action, FluentIcon as FIF
)

from core.config import log, VAD_DEFAULT_SENSITIVITY

def parse_shortcut(raw: str) -> tuple:
    if '|' in raw:
        parts = raw.split('|')
        return parts[0].lower(), int(parts[1])
    return raw.lower(), -1

class AppearanceInterface(ScrollArea):
    reset_pos_signal = pyqtSignal()

    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.setObjectName("appearanceInterface")
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea{background: transparent; border: none}")

        self.view = QWidget(self)
        self.view.setStyleSheet("QWidget{background: transparent;}")
        self.setWidget(self.view)

        self.settings = QSettings("MySTT", "STTApp")

        main_layout = QVBoxLayout(self.view)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)

        # --- Preview Card ---
        self.preview_card = QFrame()
        self.preview_card.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.05); border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.1); }")
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(20, 20, 20, 20)

        preview_title = QLabel("效果预览")
        preview_title.setStyleSheet("color: #CCCCCC; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        preview_layout.addWidget(preview_title)

        preview_box_container = QWidget()
        preview_box_container.setStyleSheet("border: none; background: transparent;")
        box_layout = QHBoxLayout(preview_box_container)
        box_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_box = QFrame()
        self.preview_box.setFixedSize(320, 60)
        self.preview_label = QLabel("文本预览 Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_layout = QVBoxLayout(self.preview_box)
        lbl_layout.setContentsMargins(0, 0, 0, 0)
        lbl_layout.addWidget(self.preview_label)
        box_layout.addWidget(self.preview_box)

        preview_layout.addWidget(preview_box_container)
        main_layout.addWidget(self.preview_card)

        # --- Settings Card ---
        self.settings_card = QFrame()
        self.settings_card.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.03); border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08); }")
        form_layout = QFormLayout(self.settings_card)
        form_layout.setVerticalSpacing(25)
        form_layout.setContentsMargins(25, 25, 25, 25)

        # Font Size
        font_size_container = QHBoxLayout()
        self.font_size_input = Slider(Qt.Orientation.Horizontal)
        self.font_size_input.setRange(12, 72)
        self.font_size_input.setValue(self.settings.value("font_size", 24, type=int))
        self.font_size_label = QLabel(f"{self.font_size_input.value()} px")
        self.font_size_label.setStyleSheet("color: white; font-size: 14px; border: none; background: transparent;")
        self.font_size_input.valueChanged.connect(self.update_preview)
        font_size_container.addWidget(self.font_size_input)
        font_size_container.addSpacing(15)
        font_size_container.addWidget(self.font_size_label)
        form_layout.addRow(QLabel("字幕字号"), font_size_container)

        # Opacity
        opacity_container = QHBoxLayout()
        self.opacity_input = Slider(Qt.Orientation.Horizontal)
        self.opacity_input.setRange(0, 255)
        self.opacity_input.setValue(self.settings.value("bg_opacity", 180, type=int))
        self.opacity_label = QLabel(f"{self.opacity_input.value()}")
        self.opacity_label.setStyleSheet("color: white; font-size: 14px; border: none; background: transparent;")
        self.opacity_input.valueChanged.connect(self.update_preview)
        opacity_container.addWidget(self.opacity_input)
        opacity_container.addSpacing(15)
        opacity_container.addWidget(self.opacity_label)
        form_layout.addRow(QLabel("字幕透明度"), opacity_container)

        # Colors
        color_container = QHBoxLayout()
        color_container.setSpacing(12)
        presets = [
            ("#FFFFFF", "纯白"),
            ("#00E5FF", "青色"),
            ("#FFD700", "亮黄"),
            ("#FF4B91", "玫瑰粉"),
            ("#00A3FF", "海蓝色")
        ]
        self.current_color = self.settings.value("font_color", "#FFFFFF")

        for c_hex, c_name in presets:
            btn = ColorPickerButton(QColor(c_hex), c_name, self)
            btn.setFixedSize(36, 36)
            btn.setToolTip(c_name)
            btn.clicked.connect(lambda checked, col=c_hex: self.set_preset_color(col))
            color_container.addWidget(btn)

        color_container.addSpacing(10)
        self.color_btn = PushButton("自定义")
        self.color_btn.clicked.connect(self.choose_color)
        color_container.addWidget(self.color_btn)
        color_container.addStretch()
        form_layout.addRow(QLabel("字体颜色"), color_container)

        # Position Reset
        self.reset_pos_btn = PushButton("还原字幕位置")
        self.reset_pos_btn.clicked.connect(self.reset_pos_signal.emit)
        form_layout.addRow(QLabel("字幕位置"), self.reset_pos_btn)

        main_layout.addWidget(self.settings_card)
        main_layout.addStretch()

        self.settings_card.setStyleSheet(self.settings_card.styleSheet() + " QLabel { color: #EEEEEE; font-size: 14px; font-weight: bold; border: none; background: transparent; }")

        self.update_preview()

    def set_preset_color(self, col):
        self.current_color = col
        self.update_preview()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.current_color), self, "选择自定义颜色")
        if color.isValid():
            self.current_color = color.name()
            self.update_preview()

    def update_preview(self):
        self.font_size_label.setText(f"{self.font_size_input.value()} px")
        self.opacity_label.setText(f"{self.opacity_input.value()}")

        font_size = self.font_size_input.value()
        opacity = self.opacity_input.value()
        color = self.current_color

        self.preview_box.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 30, 30, {opacity});
                border-radius: 30px;
                border: 1px solid rgba(255, 255, 255, 30);
            }}
            QLabel {{
                color: {color};
                font-size: {font_size}px;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                font-weight: 500;
                background: transparent;
                border: none;
            }}
        """)

    def save(self):
        self.settings.setValue("font_size", self.font_size_input.value())
        self.settings.setValue("font_color", self.current_color)
        self.settings.setValue("bg_opacity", self.opacity_input.value())

class BackendInterface(ScrollArea):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.setObjectName("backendInterface")
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea{background: transparent; border: none}")

        self.view = QWidget(self)
        self.view.setStyleSheet("QWidget{background: transparent;}")
        self.setWidget(self.view)

        self.settings = QSettings("MySTT", "STTApp")

        main_layout = QVBoxLayout(self.view)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)

        # --- Connection Card ---
        conn_card = QFrame()
        conn_card.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.03); border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08); }")
        conn_layout = QFormLayout(conn_card)
        conn_layout.setVerticalSpacing(25)
        conn_layout.setContentsMargins(25, 25, 25, 25)

        self.mode_combo = ComboBox()
        self.mode_combo.addItems([
            "字幕模式 (悬浮面板)",
            "输入法模式 - 剪贴板 (松开瞬间粘贴)",
            "输入法模式 - 穿透 (实时打字效果)"
        ])

        current_mode = self.settings.value("output_mode", "subtitle")
        if current_mode == "subtitle":
            self.mode_combo.setCurrentIndex(0)
        elif current_mode == "input_clipboard":
            self.mode_combo.setCurrentIndex(1)
        else:
            self.mode_combo.setCurrentIndex(2)

        conn_layout.addRow(QLabel("工作模式"), self.mode_combo)

        # --- Auto Send Settings ---
        self.auto_send_switch = SwitchButton("启用自动发送")
        self.auto_send_switch.setChecked(self.settings.value("auto_send_enabled", False, type=bool))

        self.auto_send_key_combo = ComboBox()
        self.auto_send_key_combo.addItems(["enter", "ctrl_enter", "shift_enter"])
        current_send_key = self.settings.value("auto_send_key", "enter")
        if current_send_key in ["enter", "ctrl_enter", "shift_enter"]:
            self.auto_send_key_combo.setCurrentIndex(["enter", "ctrl_enter", "shift_enter"].index(current_send_key))

        auto_send_layout = QHBoxLayout()
        auto_send_layout.addWidget(self.auto_send_switch)
        auto_send_layout.addSpacing(20)
        auto_send_layout.addWidget(QLabel("发送键:"))
        auto_send_layout.addWidget(self.auto_send_key_combo)
        auto_send_layout.addStretch()

        conn_layout.addRow(QLabel("自动发送"), auto_send_layout)

        self.mode_combo.currentIndexChanged.connect(self._update_auto_send_state)
        self._update_auto_send_state()

        self.current_shortcut = self.settings.value("shortcut", "f10")
        display_name, _ = parse_shortcut(self.current_shortcut)
        self.shortcut_btn = PushButton(display_name)
        self.shortcut_btn.clicked.connect(self.start_shortcut_recording)

        self.shortcut_mode_combo = ComboBox()
        self.shortcut_mode_combo.addItems(["长按 (按住说话，松开结束)", "单击 (点击开始，再次点击结束)"])
        current_shortcut_mode = self.settings.value("shortcut_mode", "hold")
        self.shortcut_mode_combo.setCurrentIndex(0 if current_shortcut_mode == "hold" else 1)

        shortcut_layout = QHBoxLayout()
        shortcut_layout.addWidget(self.shortcut_btn)
        shortcut_layout.addSpacing(15)
        shortcut_layout.addWidget(self.shortcut_mode_combo)
        shortcut_layout.addStretch()

        conn_layout.addRow(QLabel("全局唤醒键"), shortcut_layout)

        main_layout.addWidget(conn_card)

        # --- Interaction Card ---
        interaction_card = QFrame()
        interaction_card.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.03); border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08); }")
        inter_layout = QFormLayout(interaction_card)
        inter_layout.setVerticalSpacing(25)
        inter_layout.setContentsMargins(25, 25, 25, 25)

        self.url_input = LineEdit()
        self.url_input.setText(self.settings.value("ws_url", "ws://127.0.0.1:8000/v1/audio/stream"))
        inter_layout.addRow(QLabel("后端地址"), self.url_input)

        self.context_input = QTextEdit()
        self.context_input.setStyleSheet("QTextEdit { background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 5px; color: white; padding: 10px; font-size: 13px; }")
        self.context_input.setPlaceholderText("在这里输入背景信息或专有名词...")
        self.context_input.setFixedHeight(120)
        self.context_input.setPlainText(self.settings.value("context_prompt", ""))

        lbl_context = QLabel("场景/背景提示词")
        lbl_context.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        inter_layout.addRow(lbl_context, self.context_input)

        help_text = (
            "💡 最佳实践示例：\n"
            "· “我正在解说电影《流浪地球》，主要人物有图恒宇、马兆...”\n"
            "· “这是一场关于 Kubernetes 容器化部署的 IT 技术会议...”\n"
            "说明： 提前告诉 AI 你的谈话背景或专有名词，可大幅减少同音字和生僻字的识别错误。"
        )
        self.context_help = QLabel(help_text)
        self.context_help.setStyleSheet("color: #999999; font-size: 12px; border: none; background: transparent;")
        self.context_help.setWordWrap(True)
        inter_layout.addRow(QLabel(""), self.context_help)

        main_layout.addWidget(interaction_card)

        # --- Recognition / Noise-gate Card ---
        vad_card = QFrame()
        vad_card.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.03); border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08); }")
        vad_layout = QFormLayout(vad_card)
        vad_layout.setVerticalSpacing(25)
        vad_layout.setContentsMargins(25, 25, 25, 25)

        self.vad_switch = SwitchButton("启用噪音门控")
        self.vad_switch.setChecked(self.settings.value("vad_enabled", True, type=bool))
        vad_layout.addRow(QLabel("静音过滤"), self.vad_switch)

        vad_sens_container = QHBoxLayout()
        self.vad_sens_slider = Slider(Qt.Orientation.Horizontal)
        self.vad_sens_slider.setRange(1, 5)
        self.vad_sens_slider.setValue(self.settings.value("vad_sensitivity", VAD_DEFAULT_SENSITIVITY, type=int))
        self.vad_sens_label = QLabel(self._sens_text(self.vad_sens_slider.value()))
        self.vad_sens_label.setStyleSheet("color: white; font-size: 14px; border: none; background: transparent;")
        self.vad_sens_slider.valueChanged.connect(
            lambda v: self.vad_sens_label.setText(self._sens_text(v))
        )
        vad_sens_container.addWidget(self.vad_sens_slider)
        vad_sens_container.addSpacing(15)
        vad_sens_container.addWidget(self.vad_sens_label)
        vad_layout.addRow(QLabel("识别灵敏度"), vad_sens_container)

        vad_help = QLabel(
            "说明： 门控会在你不说话时停止上传音频，避免后端在静音时“凭空”识别出文字。\n"
            "灵敏度越低越安静时才触发（更抗噪），越高越容易触发（怕漏掉小声说话）。"
        )
        vad_help.setStyleSheet("color: #999999; font-size: 12px; border: none; background: transparent;")
        vad_help.setWordWrap(True)
        vad_layout.addRow(QLabel(""), vad_help)

        self.logging_switch = SwitchButton("启用文件日志")
        self.logging_switch.setChecked(self.settings.value("enable_logging", False, type=bool))
        log_help = QLabel(
            "关闭状态下不写日志文件。仅在排查问题时开启，日志会写入程序目录 stt_app.log。"
        )
        log_help.setStyleSheet("color: #999999; font-size: 12px; border: none; background: transparent;")
        log_help.setWordWrap(True)
        vad_layout.addRow(QLabel("诊断日志"), self.logging_switch)
        vad_layout.addRow(QLabel(""), log_help)

        main_layout.addWidget(vad_card)
        main_layout.addStretch()

        for card in [conn_card, interaction_card, vad_card]:
            card.setStyleSheet(card.styleSheet() + " QLabel { color: #EEEEEE; font-size: 14px; font-weight: bold; border: none; background: transparent; }")

        self._hook_conn = None

    @staticmethod
    def _sens_text(v):
        names = {1: "1 · 最抗噪", 2: "2 · 抗噪", 3: "3 · 均衡", 4: "4 · 灵敏", 5: "5 · 最灵敏"}
        return names.get(int(v), str(v))

    def start_shortcut_recording(self):
        if hasattr(self, '_hook_conn') and self._hook_conn:
            return

        self.shortcut_btn.setText("请按下新按键...")
        self.shortcut_btn.setEnabled(False)

        def on_key(event):
            if event.event_type == keyboard.KEY_DOWN:
                try:
                    keyboard.unhook(self._hook_conn)
                except Exception as e:
                    log.warning(f"Failed to unhook shortcut: {e}")
                self._hook_conn = None
                name = str(event.name).lower() if event.name and str(event.name).lower() != 'unknown' else f"Key {event.scan_code}"
                self.parent_window.shortcut_recorded.emit(f"{name}|{event.scan_code}")

        self._hook_conn = keyboard.hook(on_key)

    def _update_auto_send_state(self):
        is_subtitle = (self.mode_combo.currentIndex() == 0)
        self.auto_send_switch.setDisabled(is_subtitle)
        self.auto_send_key_combo.setDisabled(is_subtitle)

    def on_shortcut_read(self, hk):
        if hk:
            self.current_shortcut = hk
            display_name, _ = parse_shortcut(hk)
            self.shortcut_btn.setText(display_name)
        else:
            display_name, _ = parse_shortcut(self.current_shortcut)
            self.shortcut_btn.setText(display_name)
        self.shortcut_btn.setEnabled(True)

    def save(self):
        idx = self.mode_combo.currentIndex()
        if idx == 0:
            mode = "subtitle"
        elif idx == 1:
            mode = "input_clipboard"
        else:
            mode = "input_sendinput"

        self.settings.setValue("output_mode", mode)
        self.settings.setValue("auto_send_enabled", self.auto_send_switch.isChecked())
        self.settings.setValue("auto_send_key", self.auto_send_key_combo.currentText())
        self.settings.setValue("shortcut_mode", "hold" if self.shortcut_mode_combo.currentIndex() == 0 else "toggle")
        self.settings.setValue("ws_url", self.url_input.text())
        self.settings.setValue("shortcut", self.current_shortcut.lower())
        self.settings.setValue("context_prompt", self.context_input.toPlainText())
        self.settings.setValue("vad_enabled", self.vad_switch.isChecked())
        self.settings.setValue("vad_sensitivity", self.vad_sens_slider.value())
        self.settings.setValue("enable_logging", self.logging_switch.isChecked())

class AboutInterface(ScrollArea):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.setObjectName("aboutInterface")
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea{background: transparent; border: none}")

        self.view = QWidget(self)
        self.view.setStyleSheet("QWidget{background: transparent;}")
        self.setWidget(self.view)

        main_layout = QVBoxLayout(self.view)
        main_layout.setContentsMargins(30, 30, 30, 30)

        self.browser = QTextBrowser()
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
                border: none;
                color: #E0E0E0;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.setOpenExternalLinks(True)

        about_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "about.md")
        if os.path.exists(about_file):
            with open(about_file, "r", encoding="utf-8") as f:
                content = f.read()
                try:
                    import markdown
                    html = markdown.markdown(content, extensions=['extra', 'sane_lists'])
                    full_html = f"""
                    <html><head><style>
                    body {{
                        font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                        font-size: 14px;
                        color: #E0E0E0;
                        line-height: 1.6;
                    }}
                    h1, h2, h3 {{ color: #FFFFFF; font-weight: normal; margin-top: 10px; margin-bottom: 10px; }}
                    h1 {{ font-size: 24px; border-bottom: 1px solid #333333; padding-bottom: 5px; }}
                    h2 {{ font-size: 20px; border-bottom: 1px solid #333333; padding-bottom: 5px; }}
                    h3 {{ font-size: 16px; }}
                    p {{ margin-bottom: 10px; }}
                    ul, ol {{ margin-bottom: 10px; padding-left: 20px; }}
                    li {{ margin-bottom: 5px; }}
                    blockquote {{
                        border-left: 4px solid #555555;
                        padding-left: 10px;
                        color: #AAAAAA;
                        margin-left: 0;
                    }}
                    hr {{ border: 0; height: 1px; background: #333333; margin: 15px 0; }}
                    </style></head><body>{html}</body></html>
                    """
                    self.browser.setHtml(full_html)
                except ImportError:
                    self.browser.setMarkdown(content)

        main_layout.addWidget(self.browser)

class SettingsWindow(MSFluentWindow):
    settings_changed = pyqtSignal()
    shortcut_recorded = pyqtSignal(str)
    reset_pos_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("系统设置")
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mic.svg")
        self.setWindowIcon(QIcon(icon_path) if os.path.exists(icon_path) else FIF.MICROPHONE.icon())
        self.resize(950, 700)

        self.shortcut_recorded.connect(self.on_shortcut_read)

        self.appearance_interface = AppearanceInterface(self)
        self.appearance_interface.reset_pos_signal.connect(self.reset_pos_signal.emit)
        self.backend_interface = BackendInterface(self)
        self.about_interface = AboutInterface(self)

        self.addSubInterface(self.appearance_interface, FIF.BRUSH, '外观设置')
        self.addSubInterface(self.backend_interface, FIF.SETTING, '常规设置')
        self.addSubInterface(self.about_interface, FIF.INFO, '关于软件')

        self.navigationInterface.addItem(
            routeKey='Save',
            icon=FIF.SAVE,
            text='保存应用',
            onClick=self.save_all,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )

    def on_shortcut_read(self, hk):
        self.backend_interface.on_shortcut_read(hk)

    def save_all(self):
        self.appearance_interface.save()
        self.backend_interface.save()
        self.settings_changed.emit()
        InfoBar.success(
            title='保存成功',
            content='设置已保存并生效。',
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self
        )

    def closeEvent(self, event):
        if hasattr(self.backend_interface, '_hook_conn') and self.backend_interface._hook_conn:
            try:
                keyboard.unhook(self.backend_interface._hook_conn)
            except Exception as e:
                log.warning(f"Failed to unhook shortcut on close: {e}")
            self.backend_interface._hook_conn = None
        super().closeEvent(event)
