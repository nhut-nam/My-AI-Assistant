from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.handler.system_handler import SystemHandler

class ErrorType(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    IO_ERROR = "IO_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class ErrorSeverity(str, Enum):
    RECOVERABLE = "RECOVERABLE"   
    ESCALATE = "ESCALATE"         
    FATAL = "FATAL"               


@dataclass
class AgentError:
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    source: str
    raw_exception: Optional[Exception] = None


class ErrorHandler(SystemHandler):
    """
    System-level Error Handler.

    Responsibilities:
    - Normalize all system / runtime / validation errors
    - Attach semantic meaning (type + severity)
    - Emit deterministic signals for Executor / Controller
    """

    def __init__(self):
        super().__init__()
        self.info("ErrorHandler initialized")

    # ---------- Exception normalization ----------

    def handle_exception(self, exc: Exception, source: str) -> AgentError:
        """
        Normalize a raised Exception into AgentError.
        """
        self.error(f"[{source}] Exception: {exc}")

        # ---- IO errors ----
        if isinstance(exc, FileNotFoundError):
            return AgentError(
                error_type=ErrorType.IO_ERROR,
                severity=ErrorSeverity.RECOVERABLE,
                message="File not found",
                source=source,
                raw_exception=exc
            )

        if isinstance(exc, PermissionError):
            return AgentError(
                error_type=ErrorType.PERMISSION_ERROR,
                severity=ErrorSeverity.ESCALATE,
                message="Permission denied",
                source=source,
                raw_exception=exc
            )

        # ---- Known runtime / tool errors ----
        if isinstance(exc, ValueError):
            return AgentError(
                error_type=ErrorType.RUNTIME_ERROR,
                severity=ErrorSeverity.RECOVERABLE,
                message=str(exc),
                source=source,
                raw_exception=exc
            )

        # ---- Fallback (unknown) ----
        return AgentError(
            error_type=ErrorType.SYSTEM_ERROR,
            severity=ErrorSeverity.FATAL,
            message=str(exc),
            source=source,
            raw_exception=exc
        )

    # ---------- Validation failure normalization ----------

    def handle_validation_failure(self, reason: str, source: str) -> AgentError:
        """
        Normalize a validation failure (no exception raised).
        """
        self.warning(f"[{source}] Validation failed: {reason}")

        return AgentError(
            error_type=ErrorType.VALIDATION_ERROR,
            severity=ErrorSeverity.RECOVERABLE,
            message=reason,
            source=source
        )

    # ---------- Optional helper ----------

    def is_fatal(self, error: AgentError) -> bool:
        return error.severity == ErrorSeverity.FATAL
