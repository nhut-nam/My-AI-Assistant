import logging
import os
import json
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional


class LoggerMixin:
    def __init__(
        self,
        name: Optional[str] = None,
        log_dir: str = "logs",
        *,
        execution_id: Optional[str] = None,
        component: Optional[str] = None,
    ):
        self.name = name or self.__class__.__name__
        self.log_dir = log_dir
        self.execution_id = execution_id
        self.component = component or self.name
        self.logger = self._get_logger(self.name)

    # -------------------------
    # PUBLIC LOG METHODS
    # -------------------------

    def info(self, event: str, **meta):
        self._log(logging.INFO, event, meta)

    def warning(self, event: str, **meta):
        self._log(logging.WARNING, event, meta)

    def error(self, event: str, **meta):
        self._log(logging.ERROR, event, meta)

    def debug(self, event: str, **meta):
        self._log(logging.DEBUG, event, meta)

    # -------------------------
    # CORE LOGGING
    # -------------------------

    def _log(self, level: int, event: str, meta: Dict[str, Any]):
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": logging.getLevelName(level),
            "event": event,
            "component": self.component,
        }

        # optional fields
        if self.execution_id:
            payload["execution_id"] = self.execution_id
            # Also add as segment_id for backward compatibility
            payload["segment_id"] = self.execution_id

        # merge custom metadata (step, tool, severity, error, ...)
        # segment_id từ metadata sẽ override execution_id nếu có
        for k, v in meta.items():
            if v is not None:
                payload[k] = v

        self.logger.log(level, json.dumps(payload, ensure_ascii=False))

    # -------------------------
    # LOGGER SETUP
    # -------------------------

    def _get_logger(self, name: str):
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        # tránh add handler nhiều lần
        if getattr(logger, "_configured", False):
            return logger

        os.makedirs(self.log_dir, exist_ok=True)

        formatter = logging.Formatter(
            "%(message)s"  # message lúc này đã là JSON
        )

        # Console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File (rotating)
        log_file = os.path.join(
            self.log_dir,
            f"{name.replace('.', '_')}.log"
        )

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger._configured = True
        return logger
