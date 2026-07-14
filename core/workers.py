import asyncio
import json
import time
import queue
import ctypes
from ctypes import wintypes

import numpy as np
import websockets
import sounddevice as sd
from PyQt6.QtCore import QThread, pyqtSignal, QSettings

from core.config import (
    log, BYTES_PER_CHUNK, RECONNECT_DELAY_MIN, RECONNECT_DELAY_MAX,
    RESULT_SETTLE_SECONDS, RESULT_MAX_WAIT, VAD_DEFAULT_SENSITIVITY,
    VAD_RMS_THRESHOLDS, VAD_HANGOVER_SECONDS, VAD_PREROLL_FRAMES
)

# --- Win32 SendInput Helpers ---
user32 = ctypes.WinDLL('user32', use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_BACK = 0x08
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_V = 0x56

NULL_EXTRA = ctypes.POINTER(ctypes.c_ulong)()

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)))

class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT),
                    ("mi", ctypes.c_byte * 28),
                    ("hi", ctypes.c_byte * 8))
    _anonymous_ = ("_union",)
    _fields_ = (("type", wintypes.DWORD),
                ("_union", _INPUT_UNION))

def send_unicode_string(text: str):
    for char in text:
        code_point = ord(char)
        if code_point > 0xFFFF:
            high = 0xD800 + ((code_point - 0x10000) >> 10)
            low = 0xDC00 + ((code_point - 0x10000) & 0x3FF)
            inputs = (INPUT * 4)()
            inputs[0].type = INPUT_KEYBOARD
            inputs[0].ki = KEYBDINPUT(wVk=0, wScan=high, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=NULL_EXTRA)
            inputs[1].type = INPUT_KEYBOARD
            inputs[1].ki = KEYBDINPUT(wVk=0, wScan=high, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
            inputs[2].type = INPUT_KEYBOARD
            inputs[2].ki = KEYBDINPUT(wVk=0, wScan=low, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=NULL_EXTRA)
            inputs[3].type = INPUT_KEYBOARD
            inputs[3].ki = KEYBDINPUT(wVk=0, wScan=low, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
            user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        else:
            inputs = (INPUT * 2)()
            inputs[0].type = INPUT_KEYBOARD
            inputs[0].ki = KEYBDINPUT(wVk=0, wScan=code_point, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=NULL_EXTRA)
            inputs[1].type = INPUT_KEYBOARD
            inputs[1].ki = KEYBDINPUT(wVk=0, wScan=code_point, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
            user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))

        time.sleep(0.005)

def send_backspaces(count: int):
    for _ in range(count):
        inputs = (INPUT * 2)()
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].ki = KEYBDINPUT(wVk=VK_BACK, wScan=0, dwFlags=0, time=0, dwExtraInfo=NULL_EXTRA)
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].ki = KEYBDINPUT(wVk=VK_BACK, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        time.sleep(0.01)

def send_ctrl_v():
    inputs = (INPUT * 4)()
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].ki = KEYBDINPUT(wVk=VK_CONTROL, wScan=0, dwFlags=0, time=0, dwExtraInfo=NULL_EXTRA)
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].ki = KEYBDINPUT(wVk=VK_V, wScan=0, dwFlags=0, time=0, dwExtraInfo=NULL_EXTRA)
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].ki = KEYBDINPUT(wVk=VK_V, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].ki = KEYBDINPUT(wVk=VK_CONTROL, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
    user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))

def send_auto_key(key_mode: str):
    if key_mode == "enter":
        inputs = (INPUT * 2)()
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=0, time=0, dwExtraInfo=NULL_EXTRA)
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    elif key_mode == "ctrl_enter":
        inputs = (INPUT * 4)()
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].ki = KEYBDINPUT(wVk=VK_CONTROL, wScan=0, dwFlags=0, time=0, dwExtraInfo=NULL_EXTRA)
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=0, time=0, dwExtraInfo=NULL_EXTRA)
        inputs[2].type = INPUT_KEYBOARD
        inputs[2].ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
        inputs[3].type = INPUT_KEYBOARD
        inputs[3].ki = KEYBDINPUT(wVk=VK_CONTROL, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
        user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    elif key_mode == "shift_enter":
        inputs = (INPUT * 4)()
        inputs[0].type = INPUT_KEYBOARD
        inputs[0].ki = KEYBDINPUT(wVk=VK_SHIFT, wScan=0, dwFlags=0, time=0, dwExtraInfo=NULL_EXTRA)
        inputs[1].type = INPUT_KEYBOARD
        inputs[1].ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=0, time=0, dwExtraInfo=NULL_EXTRA)
        inputs[2].type = INPUT_KEYBOARD
        inputs[2].ki = KEYBDINPUT(wVk=VK_RETURN, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
        inputs[3].type = INPUT_KEYBOARD
        inputs[3].ki = KEYBDINPUT(wVk=VK_SHIFT, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=NULL_EXTRA)
        user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))

# ==========================================
# Audio & WebSocket Worker
# ==========================================
class STTWorker(QThread):
    text_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    volume_changed = pyqtSignal(float)
    finalized = pyqtSignal()   # 改动(新增): 收尾识别完成, 通知主线程可以定格/输出了

    def __init__(self, ws_url):
        super().__init__()
        self.ws_url = ws_url
        self._is_running = True
        self.is_recording = False
        self.loop = None
        self.ws = None
        self.stream = None
        self.audio_queue = None

        # 改动(新增): 收尾等待状态机
        self.is_finalizing = False          # 停麦后、等后端识别完的过渡态
        self._last_result_time = 0.0        # 最近一次收到后端结果的时刻
        self._finalize_deadline = 0.0       # 收尾硬超时时刻

        # 改动(新增): 客户端 VAD 门控运行时状态
        self._vad_threshold = VAD_RMS_THRESHOLDS[VAD_DEFAULT_SENSITIVITY]
        self._vad_hangover_until = 0.0      # 尾音保护截止时刻
        self._vad_preroll = []              # 起音前的历史帧缓存
        self.reload_vad_settings()

    def reload_vad_settings(self):
        # 从 QSettings 读取灵敏度并映射为 RMS 阈值; 灵敏度存的是 1~5 的整数
        s = QSettings("MySTT", "STTApp")
        sens = s.value("vad_sensitivity", VAD_DEFAULT_SENSITIVITY, type=int)
        sens = max(1, min(5, sens))
        self._vad_enabled = s.value("vad_enabled", True, type=bool)
        self._vad_threshold = VAD_RMS_THRESHOLDS.get(sens, VAD_RMS_THRESHOLDS[VAD_DEFAULT_SENSITIVITY])

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.audio_queue = asyncio.Queue()
        try:
            self.loop.run_until_complete(self.ws_main_loop())
        finally:
            self.loop.close()

    async def ws_main_loop(self):
        # 改动: 指数退避重连
        # 原因: 原代码断线后固定 sleep(0.05) 无限重试, 后端宕机时会高频空转+刷屏.
        #       现在从 0.5s 起, 每次失败翻倍, 上限 10s; 连接成功后立即复位.
        reconnect_delay = RECONNECT_DELAY_MIN
        while self._is_running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self.ws = ws
                    log.info(f"STTWorker connected to {self.ws_url}")
                    reconnect_delay = RECONNECT_DELAY_MIN  # 连接成功, 复位退避

                    self.receive_task = asyncio.create_task(self.receiver_loop(ws))
                    self.send_task = asyncio.create_task(self.sender_loop(ws))

                    done, pending = await asyncio.wait(
                        [self.receive_task, self.send_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for task in pending:
                        task.cancel()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(f"STTWorker WS Connection dropped: {e}")

            self.ws = None
            if self._is_running:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, RECONNECT_DELAY_MAX)

    async def sender_loop(self, ws):
        audio_buffer = bytearray()
        try:
            while self._is_running:
                # 录音中 或 收尾中 都要继续把缓冲里剩余音频发完
                if not self.is_recording and not self.is_finalizing:
                    audio_buffer.clear()
                    await asyncio.sleep(0.05)
                    continue

                try:
                    chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                audio_buffer.extend(chunk)
                if len(audio_buffer) >= BYTES_PER_CHUNK:
                    chunk_to_send = bytes(audio_buffer[:BYTES_PER_CHUNK])
                    del audio_buffer[:BYTES_PER_CHUNK]
                    try:
                        await ws.send(chunk_to_send)
                    except Exception as e:
                        log.error(f"Send error: {e}")
                        break
        except asyncio.CancelledError:
            pass

    async def receiver_loop(self, ws):
        try:
            async for message in ws:
                # 改动: 录音中 或 收尾等待中 的结果都接收
                # 原因: 收尾阶段(is_finalizing)正是我们等后端把最后几个字识别完的关键窗口.
                if not self.is_recording and not self.is_finalizing:
                    continue

                data = json.loads(message)
                if 'text' in data:
                    self._last_result_time = time.monotonic()  # 刷新"最近有结果"的时间戳
                    self.text_received.emit(data['text'])
        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            log.error(f"Receiver loop error: {e}")

    async def finalize_watcher(self):
        # 改动(新增): 收尾看门狗. 停麦后启动, 轮询判断识别是否已"稳定".
        # 稳定条件: 距最近一次结果超过 RESULT_SETTLE_SECONDS, 或已达硬上限 RESULT_MAX_WAIT.
        try:
            while self.is_finalizing and self._is_running:
                now = time.monotonic()
                settled = (now - self._last_result_time) >= RESULT_SETTLE_SECONDS
                timed_out = now >= self._finalize_deadline
                if settled or timed_out:
                    self.is_finalizing = False
                    self.finalized.emit()
                    return
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    async def send_safe(self, data):
        if self.ws is not None:
            try:
                await self.ws.send(data)
            except Exception as e:
                log.error(f"Error sending safe data: {e}")

    def update_url(self, new_url):
        self.ws_url = new_url
        if self.ws is not None and self.loop:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)

    def start_recording(self):
        if self.ws is None:
            self.error_occurred.emit("WebSocket 未连接，请等待或检查后端")
            return

        # 每次开录都重读一次 VAD 设置, 保证设置页刚改完即刻生效
        self.reload_vad_settings()

        self.is_recording = True
        self.is_finalizing = False
        self._vad_hangover_until = 0.0
        self._vad_preroll = []

        if self.loop:
            def reset_queue():
                self.audio_queue = asyncio.Queue()
            self.loop.call_soon_threadsafe(reset_queue)

        context_prompt = QSettings("MySTT", "STTApp").value("context_prompt", "")
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self.send_safe(json.dumps({"context": context_prompt})),
                self.loop
            )

        def audio_callback(indata, frames, time_info, status):
            if not (self.is_recording and self.audio_queue and self.loop):
                return

            # numpy 向量化算 RMS (用于音量条 + VAD 判决)
            try:
                samples = np.asarray(indata, dtype=np.float32).reshape(-1)
                rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size > 0 else 0.0
            except Exception:
                rms = 0.0
            self.volume_changed.emit(rms)

            raw_bytes = bytes(indata)

            # 改动(新增): 客户端 VAD 门控
            # 目的: 静音/环境底噪不送后端, 避免 ASR 在无人说话时"幻听"出文字.
            if not self._vad_enabled:
                self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, raw_bytes)
                return

            now = time.monotonic()
            is_voice = rms >= self._vad_threshold

            if is_voice:
                # 检测到语音: 先把 preroll 里缓存的起音前几帧补发, 再发当前帧, 防吃字头
                if self._vad_preroll:
                    for pre in self._vad_preroll:
                        self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, pre)
                    self._vad_preroll = []
                self._vad_hangover_until = now + VAD_HANGOVER_SECONDS
                self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, raw_bytes)
            elif now < self._vad_hangover_until:
                # 尾音保护期内: 继续发送, 防止把句尾的弱音/气声切掉
                self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, raw_bytes)
            else:
                # 判定为静音: 不发送, 只把当前帧滚动缓存进 preroll
                self._vad_preroll.append(raw_bytes)
                if len(self._vad_preroll) > VAD_PREROLL_FRAMES:
                    self._vad_preroll.pop(0)

        try:
            if hasattr(self, 'stream') and self.stream:
                self.stream.stop()
                self.stream.close()
            self.stream = sd.InputStream(samplerate=16000, channels=1, dtype='float32', blocksize=800, callback=audio_callback)
            self.stream.start()
        except Exception as e:
            self.error_occurred.emit(f"录音设备错误: {e}")

    def stop_recording(self):
        # 改动(语义升级): 停止 = 停麦克风, 但不立即结束会话, 而是进入收尾等待,
        #                 让后端把最后识别的内容返回完整, 再由 finalize_watcher 通知定格.
        was_recording = self.is_recording
        self.is_recording = False
        if hasattr(self, 'stream') and self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.volume_changed.emit(0.0)

        if self.loop:
            asyncio.run_coroutine_threadsafe(self.send_safe("DONE"), self.loop)

        if was_recording:
            # 进入收尾态并启动看门狗
            self.is_finalizing = True
            self._last_result_time = time.monotonic()
            self._finalize_deadline = time.monotonic() + RESULT_MAX_WAIT
            if self.loop:
                asyncio.run_coroutine_threadsafe(self._spawn_finalize_watcher(), self.loop)

    async def _spawn_finalize_watcher(self):
        # 在事件循环线程内创建看门狗任务
        asyncio.create_task(self.finalize_watcher())

    def cancel_finalizing(self):
        # 主线程可主动取消收尾(例如用户在收尾中又开始了新录音)
        self.is_finalizing = False

    def shutdown(self):
        self._is_running = False
        self.stop_recording()
        if self.ws is not None and self.loop:
            asyncio.run_coroutine_threadsafe(self.ws.close(), self.loop)
        self.wait()

# ==========================================
# Dictation Typing Worker (Queue-based)
# ==========================================
class DictationTypingWorker(QThread):
    clipboard_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.action_queue = queue.Queue()
        self.is_running = True

    def run(self):
        while self.is_running:
            try:
                action = self.action_queue.get(timeout=0.1)

                if action['type'] == 'backspace':
                    count = action['count']
                    if count > 0:
                        send_backspaces(count)
                elif action['type'] == 'text':
                    text = action['text']
                    if text and self.is_running:
                        # 改动: 用自定义 SendInput(send_unicode_string) 替代 keyboard.write
                        # 原因: 原来精心写的 send_unicode_string(含 UTF-16 代理对处理) 从未被调用,
                        #       穿透模式实际用的是 keyboard.write, 对部分 Unicode/emoji/IME 场景
                        #       不如底层 SendInput 可靠. 现在统一走 SendInput, 死代码得以启用.
                        send_unicode_string(text)
                elif action['type'] == 'paste':
                    text = action['text']
                    if text:
                        self.clipboard_signal.emit(text)
                        time.sleep(0.05)
                        send_ctrl_v()
                elif action['type'] == 'auto_send':
                    key_mode = action['key_mode']
                    time.sleep(0.05)
                    send_auto_key(key_mode)

                self.action_queue.task_done()
            except queue.Empty:
                continue

    def stop(self):
        self.is_running = False
        self.wait()
