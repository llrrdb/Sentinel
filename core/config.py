import os
import logging

# ==========================================
# Logging (改动: 文件日志改为可开关, 默认关闭)
# 原因: 打包成无控制台 exe 后 print 全部丢失, 无法诊断问题; 但常态下写日志
#       并非必要. 现在做成设置项 "enable_logging"(默认 False), 用户需要排查
#       问题时再在设置页开启. 控制台输出始终保留(有控制台时才可见).
# ==========================================
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stt_app.log")

def _setup_logging():
    logger = logging.getLogger("stt")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    return logger

log = _setup_logging()

def apply_logging_setting():
    """根据设置项开关文件日志处理器. 可在设置保存后热更新."""
    try:
        from PyQt6.QtCore import QSettings as _QS
        enabled = _QS("MySTT", "STTApp").value("enable_logging", False, type=bool)
    except Exception:
        enabled = False

    # 找到现有的 FileHandler(如果有)
    existing_fh = next((h for h in log.handlers if isinstance(h, logging.FileHandler)), None)

    if enabled and existing_fh is None:
        try:
            fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
            fh.setFormatter(fmt)
            log.addHandler(fh)
            log.info("文件日志已启用")
        except Exception:
            pass  # 文件不可写时也不能让程序崩溃
    elif not enabled and existing_fh is not None:
        log.info("文件日志已关闭")
        log.removeHandler(existing_fh)
        try:
            existing_fh.close()
        except Exception:
            pass

# --- Constants ---
BYTES_PER_CHUNK = 32000          # 8000 frames * 4 bytes
FPS_INTERVAL = 16                # ~60 FPS

# 改动: 让打字机淡入的分层速度真正生效
# 原因: 原代码 FAST/NORMAL/SLOW 全部等于 10, 分层调度形同虚设.
#       现在按积压量拉开梯度: 越积压越快追赶, 越空闲越柔和渐显.
TYPE_SPEED_FASTEST = 6           # 极速追赶 (ms)
TYPE_SPEED_FAST = 10             # 快速 (ms)
TYPE_SPEED_NORMAL = 16           # 正常 (ms)
TYPE_SPEED_SLOW = 24             # 柔和起步 (ms)

# 改动: 断线重连的退避参数 (新增)
RECONNECT_DELAY_MIN = 0.5        # 初始重连间隔 (s)
RECONNECT_DELAY_MAX = 10.0       # 最大重连间隔 (s)

# 改动: 停止录音后"等识别完成"的收尾策略 (语义升级)
# 原因: 用户按停止时, 后端可能才识别到句子中段(如说到 9, 字幕才到 6). 直接定格
#       会丢结尾. 现在停麦克风后进入 finalizing 状态, 持续接收后端剩余结果,
#       直到文本"稳定"(一段时间没有新结果)或触及硬上限, 再真正结束会话.
RESULT_SETTLE_SECONDS = 0.6      # 连续这么久没有新结果, 视为识别完成
RESULT_MAX_WAIT = 8.0            # 收尾最长等待, 防止后端异常时无限等

# 改动: 客户端 VAD(语音活动检测) 门控参数 (新增)
# 原因: 麦克风把静音/环境底噪也持续送后端, 流式 ASR 会在纯静音上"幻听"出文字.
#       现在低于门限的帧不送后端; 用 hangover 保留一小段尾音防吞字,
#       用 preroll 缓存起音前的几帧防吃头. 门限灵敏度可在设置页调节.
VAD_DEFAULT_SENSITIVITY = 3      # 1(最不灵敏,更安静才触发) ~ 5(最灵敏); 存 QSettings
VAD_RMS_THRESHOLDS = {           # 灵敏度 -> RMS 触发阈值
    1: 0.030,
    2: 0.018,
    3: 0.010,
    4: 0.006,
    5: 0.0035,
}
VAD_HANGOVER_SECONDS = 0.6       # 停止说话后继续发送的尾音时长, 防止句尾被切
VAD_PREROLL_FRAMES = 3           # 起音被检测到前, 回补的历史帧数, 防止句首被切

# UI 状态枚举
STATE_CIRCLE = 0  # 初始圆形待机
STATE_PILL = 1    # 胶囊形语音识别中
STATE_PANEL = 2   # 矩形结果展示面板
