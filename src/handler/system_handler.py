from src.utils.logger import LoggerMixin

class SystemHandler(LoggerMixin):
    def __init__(self):
        super().__init__()
        self.info("SystemHandler initialized")