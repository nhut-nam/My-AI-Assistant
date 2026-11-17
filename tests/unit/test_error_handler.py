"""
Unit tests for src.handler.error_handler module.
"""
import pytest
from src.handler.error_handler import (
    ErrorHandler,
    ErrorType,
    ErrorSeverity,
    AgentError
)


class TestErrorHandler:
    """Tests for ErrorHandler class."""
    
    def test_error_handler_init(self):
        """Test ErrorHandler initialization."""
        handler = ErrorHandler()
        
        assert handler is not None
    
    def test_handle_file_not_found_error(self):
        """Test handling FileNotFoundError."""
        handler = ErrorHandler()
        error = FileNotFoundError("File not found")
        
        agent_error = handler.handle_exception(error, "test_source")
        
        assert agent_error.error_type == ErrorType.IO_ERROR
        assert agent_error.severity == ErrorSeverity.RECOVERABLE
        assert agent_error.source == "test_source"
        assert agent_error.raw_exception == error
    
    def test_handle_permission_error(self):
        """Test handling PermissionError."""
        handler = ErrorHandler()
        error = PermissionError("Permission denied")
        
        agent_error = handler.handle_exception(error, "test_source")
        
        assert agent_error.error_type == ErrorType.PERMISSION_ERROR
        assert agent_error.severity == ErrorSeverity.ESCALATE
    
    def test_handle_value_error(self):
        """Test handling ValueError."""
        handler = ErrorHandler()
        error = ValueError("Invalid value")
        
        agent_error = handler.handle_exception(error, "test_source")
        
        assert agent_error.error_type == ErrorType.RUNTIME_ERROR
        assert agent_error.severity == ErrorSeverity.RECOVERABLE
    
    def test_handle_unknown_exception(self):
        """Test handling unknown exception type."""
        handler = ErrorHandler()
        error = KeyError("Key not found")
        
        agent_error = handler.handle_exception(error, "test_source")
        
        assert agent_error.error_type == ErrorType.SYSTEM_ERROR
        assert agent_error.severity == ErrorSeverity.FATAL
    
    def test_handle_validation_failure(self):
        """Test handling validation failure."""
        handler = ErrorHandler()
        
        agent_error = handler.handle_validation_failure(
            "Validation failed: missing field",
            "test_source"
        )
        
        assert agent_error.error_type == ErrorType.VALIDATION_ERROR
        assert agent_error.severity == ErrorSeverity.RECOVERABLE
        assert "missing field" in agent_error.message
    
    def test_is_fatal(self):
        """Test is_fatal helper method."""
        handler = ErrorHandler()
        
        fatal_error = AgentError(
            error_type=ErrorType.SYSTEM_ERROR,
            severity=ErrorSeverity.FATAL,
            message="Fatal error",
            source="test"
        )
        
        recoverable_error = AgentError(
            error_type=ErrorType.VALIDATION_ERROR,
            severity=ErrorSeverity.RECOVERABLE,
            message="Recoverable error",
            source="test"
        )
        
        assert handler.is_fatal(fatal_error) is True
        assert handler.is_fatal(recoverable_error) is False


