# -*- coding: utf-8 -*-
"""
统一日志系统。所有模块通过 `from .logger import logger` 获取根 logger。
主程序可调用 setup_log_file() 追加写入文件 handler。
"""
import logging
import logging.handlers
import sys
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """
    获取配置好的 Logger 实例。
    同一 name 仅在首次调用时注册 handler，避免重复输出。
    """
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    lg.addHandler(ch)
    return lg


def setup_log_file(log_path: Path) -> None:
    """可选：将 DEBUG 及以上日志追加写入文件（供 GUI 捕获完整记录）。"""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger("t2a")
    # 避免重复添加同路径的 FileHandler
    for h in root_logger.handlers:
        if isinstance(h, logging.FileHandler) and h.baseFilename == str(log_path.resolve()):
            return
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s (%(funcName)s:%(lineno)d): %(message)s"
        )
    )
    root_logger.addHandler(fh)


def add_ui_handler(callback: "Callable[[str, str], None]") -> None:
    """
    将 GUI 回调注册为日志 handler。
    callback 签名: ``callback(level: str, message: str)``
    level 为 "DEBUG" / "INFO" / "WARNING" / "ERROR" / "CRITICAL"。

    示例（Streamlit）::

        add_ui_handler(lambda level, msg: st.session_state.logs.append(f"[{level}] {msg}"))
    """
    from typing import Callable  # local import, avoid circular

    class _CallbackHandler(logging.Handler):
        def __init__(self, cb: Callable[[str, str], None]) -> None:
            super().__init__()
            self._cb = cb

        def emit(self, record: logging.LogRecord) -> None:
            try:
                self._cb(record.levelname, self.format(record))
            except Exception:
                self.handleError(record)

    h = _CallbackHandler(callback)
    h.setLevel(logging.DEBUG)
    h.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("t2a").addHandler(h)


def remove_ui_handlers() -> None:
    """移除所有通过 add_ui_handler 添加的回调 handler（页面刷新时调用）。"""
    root_logger = logging.getLogger("t2a")
    # 保留 StreamHandler 和 FileHandler，移除其他自定义 handler
    keep = [h for h in root_logger.handlers
            if isinstance(h, (logging.StreamHandler, logging.FileHandler))
            and not isinstance(h, logging.handlers.MemoryHandler)]
    root_logger.handlers = keep


# 项目根 logger（供各模块 `from .logger import logger` 使用）
logger = get_logger("t2a")
