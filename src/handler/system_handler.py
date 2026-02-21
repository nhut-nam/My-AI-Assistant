from src.utils.logger import LoggerMixin
from typing import Dict, Any, Optional
from datetime import datetime
import traceback
import sys


class SystemHandler(LoggerMixin):
    """
    Base class for system-level handlers.
    Provides common functionality for health checks, monitoring, and system state.
    """
    
    def __init__(self, name: Optional[str] = None):
        super().__init__(name or self.__class__.__name__)
        self._initialized_at = datetime.utcnow()
        self._health_status = "healthy"
        self._metrics: Dict[str, Any] = {}
        self.info("system_handler_initialized", handler_name=self.__class__.__name__)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of the handler."""
        return {
            "status": self._health_status,
            "initialized_at": self._initialized_at.isoformat(),
            "uptime_seconds": (datetime.utcnow() - self._initialized_at).total_seconds(),
            "metrics": self._metrics.copy()
        }
    
    def update_metric(self, key: str, value: Any):
        """Update a metric value."""
        self._metrics[key] = value
    
    def increment_metric(self, key: str, amount: int = 1):
        """Increment a metric counter."""
        self._metrics[key] = self._metrics.get(key, 0) + amount
    
    def set_health_status(self, status: str):
        """Set health status (healthy, degraded, unhealthy)."""
        if status != self._health_status:
            self.warning("health_status_changed", old_status=self._health_status, new_status=status)
            self._health_status = status
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        import platform
        return {
            "platform": platform.platform(),
            "python_version": sys.version,
            "handler_name": self.__class__.__name__,
            "health": self.get_health_status()
        }