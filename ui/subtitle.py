import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QVariantAnimation, QRectF, QEasingCurve, QSettings
from PyQt6.QtGui import QColor, QPainter, QFontMetrics, QPen, QLinearGradient
from qfluentwidgets import InfoBar, InfoBarPosition

from core.config import (
    FPS_INTERVAL, STATE_CIRCLE, STATE_PILL, STATE_PANEL,
    TYPE_SPEED_FASTEST, TYPE_SPEED_FAST, TYPE_SPEED_NORMAL, TYPE_SPEED_SLOW
)

# ==========================================
# Audio Visualizer Widget
# ==========================================
class AudioVisualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 50)  # 略加宽以容纳 7 根柱
        self.bar_count = 7          # 奇数, 保证有明确中心柱
        self.min_h = 3.0
        self.max_h = 26.0
        self.current_heights = [self.min_h] * self.bar_count
        self.target_heights = [self.min_h] * self.bar_count
        self.phase = 0.0

        # 中心对称的权重: 中间高、两侧低 (钟形包络), 让音量以中心为核心向外扩散
        center = (self.bar_count - 1) / 2.0
        self.env = []
        for i in range(self.bar_count):
            d = abs(i - center) / center if center > 0 else 0.0
            # 余弦包络: 中心 1.0 -> 边缘 ~0.35
            self.env.append(0.35 + 0.65 * (math.cos(d * math.pi) * 0.5 + 0.5))

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animation)
        self.anim_timer.start(FPS_INTERVAL)

        self.color = QColor("#FFFFFF")
        self.is_speaking = False
        self.target_vol = 0.0
        self.current_vol = 0.0

    def set_color(self, color_hex):
        self.color = QColor(color_hex)
        self.update()

    def set_volume(self, rms):
        vol = min(rms * 1200, 1.0)
        self.target_vol = vol
        self.is_speaking = vol > 0.02

    def update_animation(self):
        # 音量一阶低通, 避免柱子抖动
        self.current_vol += (self.target_vol - self.current_vol) * 0.18
        idle = (not self.is_speaking and self.current_vol < 0.05)

        if idle:
            # 待机: 一条柔和的行波从中心向两侧扩散的呼吸感
            self.phase += 0.045
            for i in range(self.bar_count):
                wave = 0.5 + 0.5 * math.sin(self.phase - abs(i - (self.bar_count - 1) / 2.0) * 0.5)
                self.target_heights[i] = self.min_h + 3.5 * wave * self.env[i]
        else:
            # 说话: 以 current_vol 为总能量, 按中心包络分配, 叠加轻微相位错动
            self.phase += 0.13
            for i in range(self.bar_count):
                jitter = 0.5 + 0.5 * math.sin(self.phase * 1.3 + i * 0.9)
                amp = self.current_vol * self.env[i]
                h = self.min_h + amp * (self.max_h - self.min_h) * (0.55 + 0.45 * jitter)
                self.target_heights[i] = max(self.min_h, min(self.max_h, h))

        needs_update = False
        # 上升快、回落慢 —— 均衡器的经典手感 (attack/decay 不对称)
        for i in range(self.bar_count):
            diff = self.target_heights[i] - self.current_heights[i]
            factor = 0.45 if diff > 0 else (0.10 if idle else 0.22)
            if abs(diff) > 0.01:
                self.current_heights[i] += diff * factor
                needs_update = True

        if needs_update or not self.is_speaking:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_width = 4.0
        spacing = 3.0
        total_width = self.bar_count * bar_width + (self.bar_count - 1) * spacing
        start_x = (self.width() - total_width) / 2.0
        cy = self.height() / 2.0

        base = QColor(self.color)
        painter.setPen(Qt.PenStyle.NoPen)

        for i in range(self.bar_count):
            h = self.current_heights[i]
            x = start_x + i * (bar_width + spacing)
            y = cy - h / 2.0

            # 竖直渐变: 顶部亮、底部稍暗, 强度随柱高提升, 制造发光质感
            grad = QLinearGradient(0, y, 0, y + h)
            top = QColor(base)
            bottom = QColor(base)
            intensity = 0.5 + 0.5 * min(h / self.max_h, 1.0)
            top.setAlphaF(min(1.0, 0.85 * intensity + 0.15))
            bottom.setAlphaF(0.35 * intensity + 0.10)
            grad.setColorAt(0.0, top)
            grad.setColorAt(1.0, bottom)
            painter.setBrush(grad)

            painter.drawRoundedRect(QRectF(x, y, bar_width, h), bar_width / 2.0, bar_width / 2.0)

class AnimatedBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.radius = 25.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.bg_opacity = 180
        self.refresh_opacity()

    def refresh_opacity(self):
        settings = QSettings("MySTT", "STTApp")
        self.bg_opacity = settings.value("bg_opacity", 180, type=int)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor(30, 30, 30, self.bg_opacity)
        border_color = QColor(255, 255, 255, 30)

        pen = QPen(border_color, 1.0)
        painter.setPen(pen)
        painter.setBrush(bg_color)

        inner_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(inner_rect, self.radius, self.radius)

# ==========================================
# Floating Subtitle Window
# ==========================================
class SubtitleWindow(QWidget):
    def __init__(self):
        super().__init__()
        # 无边框、透明背景、置顶
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setFixedSize(160, 110)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.container = AnimatedBox(self)
        self.container.setObjectName("container")
        self.container.setFixedSize(100, 50)

        # 添加高级阴影
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QSizePolicy
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 8)
        self.container.setGraphicsEffect(shadow)

        self.main_layout.addWidget(self.container)

        self.box_layout = QVBoxLayout(self.container)
        self.box_layout.setContentsMargins(0, 0, 0, 0)
        self.box_layout.setSpacing(0)

        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(50)
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(20, 0, 20, 0)
        self.header_layout.setSpacing(10)

        self.header_layout.addStretch()
        self.visualizer = AudioVisualizer(self.header_widget)
        self.visualizer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.header_layout.addWidget(self.visualizer)

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label.setWordWrap(False)
        self.label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.label.setStyleSheet('background: transparent;')
        self.label.hide()
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.header_layout.addWidget(self.label)

        self.header_layout.addStretch()

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setStyleSheet('QPushButton { background-color: rgba(255, 255, 255, 20); color: white; border-radius: 14px; font-weight: bold; } QPushButton:hover { background-color: rgba(255, 70, 70, 200); }')
        self.btn_close.hide()
        self.btn_close.clicked.connect(self.start_fade_out)
        self.header_layout.addWidget(self.btn_close)

        self.box_layout.addWidget(self.header_widget)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent; border: none;
                color: #E0E0E0; font-size: 15px; font-family: "Microsoft YaHei"; line-height: 1.8;
            }
            QScrollBar:vertical { width: 6px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(255, 255, 255, 50); border-radius: 3px; }
        """)
        self.text_edit.hide()

        self.body_widget = QWidget()
        self.body_layout = QVBoxLayout(self.body_widget)
        self.body_layout.setContentsMargins(20, 0, 20, 0)
        self.body_layout.addWidget(self.text_edit)
        self.box_layout.addWidget(self.body_widget)

        self.footer_widget = QWidget()
        self.footer_layout = QHBoxLayout(self.footer_widget)
        self.footer_layout.setContentsMargins(20, 0, 20, 15)
        self.footer_layout.addStretch()

        btn_qss = """
            QPushButton {
                background-color: rgba(255, 255, 255, 15); color: white;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px; padding: 6px 16px; font-size: 13px; font-family: "Microsoft YaHei";
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 30); }
        """
        self.btn_copy = QPushButton("复制内容")
        self.btn_copy.setStyleSheet(btn_qss)
        self.btn_copy.clicked.connect(self.copy_text_and_toast)
        self.footer_layout.addWidget(self.btn_copy)
        self.footer_widget.hide()

        self.box_layout.addWidget(self.footer_widget)

        # --- Engine variables ---
        self.ui_state = STATE_CIRCLE
        self.full_text = ""
        self.stable_text = ""
        self.fading_text = ""
        self.pending_text = ""
        self.fade_alpha = 0
        self.max_session_width = 0

        self.target_width = 100.0
        self.current_width = 100.0

        self.smooth_timer = QTimer(self)
        self.smooth_timer.timeout.connect(self.update_smooth_layout)
        self.smooth_timer.start(FPS_INTERVAL)

        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self.type_next_char)

        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.fade_anim.finished.connect(self.hide_completely)

        self.clear_timer = QTimer(self)
        self.clear_timer.setInterval(2500)
        self.clear_timer.setSingleShot(True)
        self.clear_timer.timeout.connect(self.start_fade_out)

        self.apply_styles()
        self._is_custom_pos = False

    def copy_text_and_toast(self):
        QApplication.clipboard().setText(self.full_text)
        InfoBar.success(
            title='复制成功',
            content='文本已复制到剪贴板',
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._is_dragging = True
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            self._is_custom_pos = True
            self._custom_center_x = new_pos.x() + self.width() // 2
            self._custom_y = new_pos.y()
            event.accept()

    def mouseReleaseEvent(self, event):
        if hasattr(self, '_drag_pos'):
            del self._drag_pos
            QTimer.singleShot(50, lambda: setattr(self, '_is_dragging', False))
            event.accept()

    def _start_morph_animation(self, target_w, target_h, target_r, duration, easing):
        self.morph_anim = QVariantAnimation(self)
        self.morph_anim.setDuration(duration)
        self.morph_anim.setStartValue(0.0)
        self.morph_anim.setEndValue(1.0)
        self.morph_anim.setEasingCurve(easing)

        self.start_w = self.current_width
        self.start_h = self.container.height()
        self.start_r = getattr(self.container, 'radius', 25.0)

        self.target_panel_w = float(target_w)
        self.target_panel_h = float(target_h)
        self.target_panel_r = float(target_r)
        self.target_width = float(target_w)

        self.morph_anim.valueChanged.connect(self._on_morph_step)
        self.morph_anim.start()

    def morph_to_pill(self):
        self.ui_state = STATE_PILL
        self.label.hide()
        self.btn_close.hide()
        self.footer_widget.hide()
        self.text_edit.hide()
        self._start_morph_animation(100.0, 50.0, 25.0, 500, QEasingCurve.Type.OutCubic)

    def morph_to_panel(self):
        self.ui_state = STATE_PANEL
        self.visualizer.set_volume(0)

        self.label.hide()
        self.btn_close.show()

        self.text_edit.setPlainText(self.full_text)
        self.text_edit.show()

        self.footer_widget.show()

        fm = QFontMetrics(self.text_edit.font())
        text_w = 480 - 40
        rect = fm.boundingRect(0, 0, text_w, 10000, Qt.TextFlag.TextWordWrap, self.full_text)
        required_text_h = rect.height()

        target_h = required_text_h + 50 + 50 + 40
        screen_h = self.screen().geometry().height()
        max_h = screen_h * 0.6
        target_h = min(max(target_h, 150), max_h)

        self._start_morph_animation(480.0, target_h, 15.0, 600, QEasingCurve.Type.OutExpo)

    def morph_to_circle(self):
        self.ui_state = STATE_CIRCLE
        self.visualizer.set_volume(0)

        self.label.hide()
        self.text_edit.hide()
        self.btn_close.hide()
        self.footer_widget.hide()
        self._start_morph_animation(100.0, 50.0, 25.0, 500, QEasingCurve.Type.OutCubic)

    def reset_to_circle(self):
        self.ui_state = STATE_CIRCLE
        self.visualizer.set_volume(0)
        self.label.hide()
        self.text_edit.hide()
        self.btn_close.hide()
        self.footer_widget.hide()

        self.current_width = 100.0
        self.target_width = 100.0
        self.container.radius = 25.0
        self.container.setFixedSize(100, 50)
        self.setFixedSize(160, 110)
        self.setWindowOpacity(1.0)

    def _on_morph_step(self, progress):
        w = self.start_w + (self.target_panel_w - self.start_w) * progress
        h = self.start_h + (self.target_panel_h - self.start_h) * progress
        r = self.start_r + (self.target_panel_r - self.start_r) * progress

        self.current_width = w
        self.container.radius = r
        self.container.setFixedSize(int(w), int(h))
        self.setFixedSize(int(w) + 60, int(h) + 60)

    def update_smooth_layout(self):
        if hasattr(self, 'morph_anim') and self.morph_anim.state() == QVariantAnimation.State.Running:
            return

        if self.ui_state == STATE_PILL:
            diff = self.target_width - self.current_width
            if abs(diff) > 0.5:
                self.current_width += diff * 0.25
                self.container.setFixedSize(int(round(self.current_width)), self.container.height())
                self.setFixedSize(int(round(self.current_width)) + 60, self.container.height() + 60)
            elif abs(diff) > 0:
                self.current_width = self.target_width
                self.container.setFixedSize(int(round(self.current_width)), self.container.height())
                self.setFixedSize(int(round(self.current_width)) + 60, self.container.height() + 60)

            if hasattr(self, 'current_margin'):
                if self.current_margin > 0.5:
                    self.current_margin -= self.current_margin * 0.15
                    self.label.setContentsMargins(int(round(self.current_margin)), 0, 0, 0)
                elif self.current_margin > 0:
                    self.current_margin = 0
                    self.label.setContentsMargins(0, 0, 0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if getattr(self, '_is_dragging', False):
            return

        current_screen = self.screen()
        is_first_show = getattr(self, '_last_screen', None) is None

        if getattr(self, '_last_screen', None) != current_screen:
            self._last_screen = current_screen
            if getattr(self, '_is_custom_pos', False):
                self._custom_center_x = self.x() + self.width() // 2

            if not is_first_show:
                return

        if not getattr(self, '_is_custom_pos', False):
            screen = current_screen.geometry()
            x = (screen.width() - self.width()) // 2 + screen.x()
            y = screen.height() - 120 - (self.height() // 2) + screen.y()
            self.move(x, int(y))
        else:
            if hasattr(self, '_custom_center_x'):
                x = self._custom_center_x - self.width() // 2
                y = getattr(self, '_custom_y', self.y())
                screen_geom = current_screen.geometry()
                max_y = screen_geom.bottom() - self.height() - 20
                if y > max_y:
                    y = max_y
                self.move(x, int(y))

    def reset_session(self):
        self.clear_text_data()
        self.target_width = 100.0
        self.current_width = 100.0
        if hasattr(self, 'current_margin'):
            self.current_margin = 0
        self.container.radius = 25.0
        self.container.setFixedSize(100, 50)
        self.setFixedSize(160, 110)
        self.ui_state = STATE_CIRCLE

    def reset_session_pos(self):
        current_screen = self.screen()
        screen = current_screen.geometry()
        x = (screen.width() - self.width()) // 2 + screen.x()
        y = screen.height() - 120 - (self.height() // 2) + screen.y()
        self.move(x, int(y))
        self._is_custom_pos = False
        if hasattr(self, '_custom_center_x'):
            del self._custom_center_x

    def clear_text_data(self):
        self.typing_timer.stop()
        self.fade_anim.stop()
        self.clear_timer.stop()

        self.label.setContentsMargins(0, 0, 0, 0)
        self.full_text = ""
        self.stable_text = ""
        self.fading_text = ""
        self.pending_text = ""
        self.fade_alpha = 0
        self.last_chopped_width = 0
        self.label.setText("")

    def apply_styles(self):
        settings = QSettings("MySTT", "STTApp")
        font_size = settings.value("font_size", 24, type=int)
        self.current_font_color = settings.value("font_color", "#FFFFFF")

        self.visualizer.set_color(self.current_font_color)
        self.container.refresh_opacity()

        style_sheet = f"""
            #container {{
                background-color: transparent;
                border: none;
            }}
            QLabel {{
                color: {self.current_font_color};
                font-size: {font_size}px;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                font-weight: 500;
                background: transparent;
            }}
        """
        self.setStyleSheet(style_sheet)

    def update_label_content(self, stable_text, fading_text, fade_alpha, pending_text=""):
        fm = QFontMetrics(self.label.font())
        screen_w = self.screen().geometry().width()
        max_width = max(int(screen_w * 0.3), 400)

        chopped_width = 0
        full_display = stable_text + fading_text

        if len(stable_text) > 150:
            pre_chop_text = stable_text[:-150]
            pre_chop_w = fm.horizontalAdvance(pre_chop_text)
            chopped_width += pre_chop_w
            stable_text = stable_text[-150:]
            full_display = stable_text + fading_text

        current_w = fm.horizontalAdvance(full_display)

        if current_w > max_width:
            left, right = 0, len(full_display)
            best_start = 0
            while left <= right:
                mid = (left + right) // 2
                if fm.horizontalAdvance(full_display[mid:]) <= max_width:
                    best_start = mid
                    right = mid - 1
                else:
                    left = mid + 1

            dropped_text = full_display[:best_start]
            chopped_width += fm.horizontalAdvance(dropped_text)

            orig_stable_len = len(stable_text)
            if best_start <= orig_stable_len:
                stable_text = stable_text[best_start:]
            else:
                stable_text = ""
                fading_text = fading_text[best_start - orig_stable_len:]

            current_w = fm.horizontalAdvance(stable_text + fading_text)

        delta_chop = chopped_width - getattr(self, 'last_chopped_width', 0)
        if delta_chop != 0:
            self.current_margin = getattr(self, 'current_margin', 0) + delta_chop
            if self.current_margin < 0:
                self.current_margin = 0
            self.label.setContentsMargins(int(round(self.current_margin)), 0, 0, 0)

        self.last_chopped_width = chopped_width

        display_w = current_w if current_w < max_width else max_width
        self.label.setFixedWidth(int(display_w))

        c = QColor(self.current_font_color)
        r, g, b = c.red(), c.green(), c.blue()
        color_stable = f"rgba({r}, {g}, {b}, 1.0)"
        color_fading = f"rgba({r}, {g}, {b}, {fade_alpha/255.0:.2f})"

        html = f'<span style="color: {color_stable};">{stable_text}</span>'
        if fading_text and fade_alpha > 0:
            html += f'<span style="color: {color_fading};">{fading_text}</span>'

        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setText(html)
        needed_width = 110 + current_w
        if self.ui_state == STATE_PILL and needed_width > self.target_width:
            self.target_width = needed_width

    def update_text(self, text):
        if text is None:
            return

        if len(text) > 2000:
            text = text[-2000:]

        self.full_text = text

        if self.isHidden() or self.windowOpacity() < 1.0:
            self.fade_anim.stop()
            self.setWindowOpacity(1.0)
            self.show()

        if text and self.label.isHidden() and self.ui_state == STATE_PILL:
            self.label.show()

        self.clear_timer.stop()

        speed = FPS_INTERVAL

        visible_len = len(self.stable_text) + len(self.fading_text)

        if len(self.full_text) <= visible_len:
            self.stable_text = self.full_text
            self.fading_text = ""
            self.fade_alpha = 0
            self.pending_text = ""
        else:
            self.stable_text = self.full_text[:visible_len]
            self.fading_text = ""
            self.fade_alpha = 0
            self.pending_text = self.full_text[visible_len:]

        self.update_label_content(self.stable_text, self.fading_text, self.fade_alpha, self.pending_text)
        if not self.typing_timer.isActive() and self.pending_text:
            self.typing_timer.start(speed)

    def type_next_char(self):
        if not self.fading_text and self.pending_text:
            self.fading_text = self.pending_text[0]
            self.pending_text = self.pending_text[1:]
            self.fade_alpha = 0

        if self.fading_text:
            self.update_label_content(self.stable_text, self.fading_text, self.fade_alpha, self.pending_text)

            if self.fade_alpha >= 255:
                self.stable_text += self.fading_text
                self.fading_text = ""
            else:
                backlog = len(self.pending_text)
                if backlog > 15:
                    speed_factor = 1.0
                elif backlog > 8:
                    speed_factor = 0.8
                elif backlog > 3:
                    speed_factor = 0.6
                else:
                    speed_factor = 0.4

                self.fade_alpha += max(15, int((255 - self.fade_alpha) * speed_factor))
                if self.fade_alpha > 255:
                    self.fade_alpha = 255

            backlog = len(self.pending_text)
            if backlog > 0:
                if backlog > 10:
                    self.typing_timer.start(TYPE_SPEED_FASTEST)
                elif backlog > 5:
                    self.typing_timer.start(TYPE_SPEED_FAST)
                elif backlog > 2:
                    self.typing_timer.start(TYPE_SPEED_NORMAL)
                else:
                    self.typing_timer.start(TYPE_SPEED_SLOW)
        else:
            self.typing_timer.stop()

    def set_volume(self, rms):
        self.visualizer.set_volume(rms)

    def schedule_clear(self):
        self.clear_timer.start()

    def start_fade_out(self):
        self.fade_anim.start()

    def hide_completely(self):
        self.reset_session()
        self.visualizer.set_volume(0)
        self.repaint()
        self.hide()
