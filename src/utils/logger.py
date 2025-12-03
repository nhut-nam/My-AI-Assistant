import logging
import os
from logging.handlers import RotatingFileHandler

class LoggerMixin:
    def __init__(self, name: str = None, log_dir='logs'):
        self.name = name or self.__class__.__name__
        self.log_dir = log_dir
        self.logger = self.get_logger(self.name)

    def info(self, msg: str):
        self.logger.info(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(msg)

    def debug(self, msg: str):
        self.logger.debug(msg)

    def get_logger(self, name: str):
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        if logger.handlers:
            return logger

        os.makedirs(self.log_dir, exist_ok=True)

        formatter = logging.Formatter(
            "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
            "%Y-%m-%d %H:%M:%S"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        log_file = os.path.join(self.log_dir, f"{name.replace('.', '_')}.log")
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  
            backupCount=3,       
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger
