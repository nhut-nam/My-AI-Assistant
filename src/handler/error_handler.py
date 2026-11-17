from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
import traceback
import sys
import json
from datetime import datetime

from src.handler.system_handler import SystemHandler


class ErrorType(str, Enum):
    """Types of errors that can occur in the system."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    IO_ERROR = "IO_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    LLM_ERROR = "LLM_ERROR"
    SERIALIZATION_ERROR = "SERIALIZATION_ERROR"


class ErrorSeverity(str, Enum):
    """Severity levels for errors."""
    RECOVERABLE = "RECOVERABLE"   # Can retry or continue
    ESCALATE = "ESCALATE"         # Needs attention but not fatal
    FATAL = "FATAL"               # Cannot continue


@dataclass
class ErrorContext:
    """Additional context about an error."""
    traceback: Optional[str] = None
    line_number: Optional[int] = None
    file_name: Optional[str] = None
    function_name: Optional[str] = None
    local_vars: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AgentError:
    """Structured error representation."""
    error_type: ErrorType
    severity: ErrorSeverity
    message: str
    source: str
    raw_exception: Optional[Exception] = None
    context: Optional[ErrorContext] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        result = {
            "error_type": self.error_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "source": self.source,
            "metadata": self.metadata
        }
        if self.context:
            result["context"] = {
                "traceback": self.context.traceback,
                "line_number": self.context.line_number,
                "file_name": self.context.file_name,
                "function_name": self.context.function_name,
                "timestamp": self.context.timestamp
            }
        if self.raw_exception:
            result["exception_type"] = type(self.raw_exception).__name__
        return result


class ErrorHandler(SystemHandler):
    """
    Professional Error Handler for the AI Assistant system.

    Responsibilities:
    - Normalize all system / runtime / validation errors
    - Attach semantic meaning (type + severity)
    - Capture error context (traceback, line numbers, etc.)
    - Track error metrics and statistics
    - Provide error recovery strategies
    - Emit deterministic signals for Executor / Controller
    """

    def __init__(self):
        super().__init__("ErrorHandler")
        self._error_counts: Dict[ErrorType, int] = {}
        self._error_history: List[AgentError] = []
        self._max_history_size = 100
        
    # ---------- Exception normalization ----------

    def handle_exception(
        self, 
        exc: Exception, 
        source: str,
        include_traceback: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentError:
        """
        Normalize a raised Exception into AgentError with full context.
        
        Args:
            exc: The exception that was raised
            source: Source component/function name
            include_traceback: Whether to include full traceback
            metadata: Additional metadata to attach
            
        Returns:
            AgentError with normalized error information
        """
        # Extract error context
        context = self._extract_context(exc, include_traceback)
        
        # Determine error type and severity
        error_type, severity = self._classify_exception(exc)
        
        # Build error message
        message = self._build_error_message(exc, error_type)
        
        # Create AgentError
        agent_error = AgentError(
            error_type=error_type,
            severity=severity,
            message=message,
            source=source,
            raw_exception=exc,
            context=context,
            metadata=metadata or {}
        )
        
        # Log and track
        self._log_error(agent_error)
        self._track_error(agent_error)
        
        return agent_error
    
    def _extract_context(self, exc: Exception, include_traceback: bool) -> ErrorContext:
        """Extract context information from exception."""
        context = ErrorContext()
        
        if include_traceback:
            try:
                tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
                context.traceback = "".join(tb_lines)
                
                # Extract frame info from traceback
                if exc.__traceback__:
                    tb = exc.__traceback__
                    while tb.tb_next:
                        tb = tb.tb_next
                    frame = tb.tb_frame
                    context.line_number = tb.tb_lineno
                    context.file_name = frame.f_code.co_filename
                    context.function_name = frame.f_code.co_name
            except Exception:
                pass
        
        return context
    
    def _classify_exception(self, exc: Exception) -> tuple[ErrorType, ErrorSeverity]:
        """Classify exception type and determine severity."""
        exc_type = type(exc)
        
        # IO Errors
        if isinstance(exc, FileNotFoundError):
            return ErrorType.IO_ERROR, ErrorSeverity.RECOVERABLE
        if isinstance(exc, PermissionError):
            return ErrorType.PERMISSION_ERROR, ErrorSeverity.ESCALATE
        if isinstance(exc, (OSError, IOError)):
            return ErrorType.IO_ERROR, ErrorSeverity.RECOVERABLE
        
        # Network/Timeout Errors
        if isinstance(exc, TimeoutError):
            return ErrorType.TIMEOUT_ERROR, ErrorSeverity.RECOVERABLE
        if "timeout" in str(exc).lower() or "connection" in str(exc).lower():
            return ErrorType.NETWORK_ERROR, ErrorSeverity.RECOVERABLE
        
        # Runtime Errors
        if isinstance(exc, ValueError):
            return ErrorType.RUNTIME_ERROR, ErrorSeverity.RECOVERABLE
        if isinstance(exc, TypeError):
            return ErrorType.RUNTIME_ERROR, ErrorSeverity.RECOVERABLE
        if isinstance(exc, KeyError):
            return ErrorType.RUNTIME_ERROR, ErrorSeverity.RECOVERABLE
        if isinstance(exc, AttributeError):
            return ErrorType.RUNTIME_ERROR, ErrorSeverity.RECOVERABLE
        
        # Serialization Errors
        if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)):
            return ErrorType.SERIALIZATION_ERROR, ErrorSeverity.RECOVERABLE
        
        # LLM-specific errors (check by message content)
        error_msg = str(exc).lower()
        if any(keyword in error_msg for keyword in ["api", "llm", "model", "token", "rate limit"]):
            return ErrorType.LLM_ERROR, ErrorSeverity.ESCALATE
        
        # Fallback
        return ErrorType.SYSTEM_ERROR, ErrorSeverity.FATAL
    
    def _build_error_message(self, exc: Exception, error_type: ErrorType) -> str:
        """Build user-friendly error message."""
        base_message = str(exc) or f"{type(exc).__name__} occurred"
        
        # Enhance message based on error type
        if error_type == ErrorType.IO_ERROR:
            if "No such file" in base_message or "not found" in base_message.lower():
                return f"File not found: {base_message}"
            return f"I/O error: {base_message}"
        
        if error_type == ErrorType.NETWORK_ERROR:
            return f"Network error: {base_message}"
        
        if error_type == ErrorType.TIMEOUT_ERROR:
            return f"Operation timed out: {base_message}"
        
        if error_type == ErrorType.LLM_ERROR:
            return f"LLM service error: {base_message}"
        
        return base_message
    
    def _log_error(self, error: AgentError):
        """Log error with structured format."""
        log_data = error.to_dict()

        if error.severity == ErrorSeverity.FATAL:
            self.error("error_occurred", **log_data)
        elif error.severity == ErrorSeverity.ESCALATE:
            self.warning("error_occurred", **log_data)
        else:
            self.warning("error_occurred", **log_data)

    
    def _track_error(self, error: AgentError):
        """Track error for metrics and history."""
        # Update counts
        self._error_counts[error.error_type] = self._error_counts.get(error.error_type, 0) + 1
        self.increment_metric(f"errors_{error.error_type.value.lower()}", 1)
        self.increment_metric(f"errors_{error.severity.value.lower()}", 1)
        
        # Add to history
        self._error_history.append(error)
        if len(self._error_history) > self._max_history_size:
            self._error_history.pop(0)
        
        # Update health status based on error patterns
        if error.severity == ErrorSeverity.FATAL:
            self.set_health_status("unhealthy")
        elif self._get_recent_fatal_count() > 5:
            self.set_health_status("degraded")

    # ---------- Validation failure normalization ----------

    def handle_validation_failure(
        self, 
        reason: str, 
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentError:
        """
        Normalize a validation failure (no exception raised).
        
        Args:
            reason: Reason for validation failure
            source: Source component/function name
            metadata: Additional metadata
            
        Returns:
            AgentError representing the validation failure
        """
        agent_error = AgentError(
            error_type=ErrorType.VALIDATION_ERROR,
            severity=ErrorSeverity.RECOVERABLE,
            message=reason,
            source=source,
            metadata=metadata or {}
        )
        
        self._log_error(agent_error)
        self._track_error(agent_error)
        
        return agent_error

    # ---------- Helper methods ----------

    def is_fatal(self, error: AgentError) -> bool:
        """Check if error is fatal."""
        return error.severity == ErrorSeverity.FATAL
    
    def is_recoverable(self, error: AgentError) -> bool:
        """Check if error is recoverable."""
        return error.severity == ErrorSeverity.RECOVERABLE
    
    def should_retry(self, error: AgentError, max_retries: int = 3) -> bool:
        """Determine if operation should be retried."""
        if error.severity == ErrorSeverity.FATAL:
            return False
        if error.error_type == ErrorType.PERMISSION_ERROR:
            return False
        return True
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics."""
        return {
            "total_errors": sum(self._error_counts.values()),
            "error_counts_by_type": {k.value: v for k, v in self._error_counts.items()},
            "recent_errors": len(self._error_history),
            "health_status": self._health_status
        }
    
    def _get_recent_fatal_count(self, window: int = 10) -> int:
        """Count fatal errors in recent history."""
        recent = self._error_history[-window:]
        return sum(1 for e in recent if e.severity == ErrorSeverity.FATAL)
    
    def get_recovery_suggestion(self, error: AgentError) -> Optional[str]:
        """Get recovery suggestion for an error."""
        suggestions = {
            ErrorType.IO_ERROR: "Check file path and permissions. Ensure file exists.",
            ErrorType.PERMISSION_ERROR: "Check file/directory permissions. Run with appropriate privileges.",
            ErrorType.NETWORK_ERROR: "Check network connection. Retry after a delay.",
            ErrorType.TIMEOUT_ERROR: "Operation timed out. Consider increasing timeout or retrying.",
            ErrorType.LLM_ERROR: "LLM service may be unavailable. Check API key and rate limits.",
            ErrorType.VALIDATION_ERROR: "Review input data and validation rules.",
            ErrorType.SERIALIZATION_ERROR: "Check data format. Ensure valid JSON/serializable data.",
        }
        return suggestions.get(error.error_type)
