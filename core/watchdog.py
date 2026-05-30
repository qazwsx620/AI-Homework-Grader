"""
core/watchdog.py — 看门狗与系统维护
负责：检测网页关闭后自动退出程序、心跳保活、清理缓存图片
"""
import os
import time
import glob
import threading
from flask import jsonify

_LAST_HEARTBEAT = time.time()
_HAS_CONNECTED = False


def start_watchdog():
    """启动看门狗线程：若网页断开超过6秒则自动退出"""
    def _watchdog_loop():
        global _LAST_HEARTBEAT, _HAS_CONNECTED
        while True:
            time.sleep(2)
            if (time.time() - _LAST_HEARTBEAT > 6) and _HAS_CONNECTED:
                print("\n [Watchdog] 检测到网页已关闭，后台服务正在安全退出...")
                os._exit(0)

    thread = threading.Thread(target=_watchdog_loop, daemon=True)
    thread.start()


def heartbeat():
    """心跳接口：前端每2秒调用一次，重置看门狗计时"""
    global _LAST_HEARTBEAT, _HAS_CONNECTED
    _LAST_HEARTBEAT = time.time()
    _HAS_CONNECTED = True
    return jsonify({'status': 'success'})


def clean_old_static_files():
    """清理 static/ 目录下超过5分钟的缓存结果图片"""
    try:
        static_dir = "static"
        if not os.path.exists(static_dir):
            return
        now = time.time()
        for file_path in glob.glob(os.path.join(static_dir, "result_*.jpg")):
            if os.path.getmtime(file_path) < now - 300:
                os.remove(file_path)
                print(f"清理历史缓存图片: {os.path.basename(file_path)}")
    except Exception as e:
        print(f"清理历史文件时出错: {e}")
