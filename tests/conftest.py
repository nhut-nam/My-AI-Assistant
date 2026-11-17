"""
Pytest configuration and shared fixtures.
This file is automatically loaded by pytest.
"""
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import Generator
import os
import sys

# Add src to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.models import Plan
from src.agent.base_agent import BaseAgent
from src.llm.base import BaseClient


# ============================================================================
# FIXTURES - Mock LLM Clients
# ============================================================================

@pytest.fixture
def mock_llm_client():
    """Mock LLM client that can be used in tests."""
    mock_client = Mock(spec=BaseClient)
    mock_client._create_client = Mock()
    mock_client.invoke = AsyncMock(return_value="Mocked LLM response")
    mock_client.model_name = "test-model"
    mock_client.api_key = "test-api-key"
    mock_client.config = {"temperature": 0.5, "max_tokens": 2048}
    return mock_client


@pytest.fixture
def mock_langchain_client():
    """Mock LangChain client for agent tests."""
    mock_llm = Mock()
    
    # Mock invoke method
    async def mock_invoke(message):
        mock_response = Mock()
        mock_response.content = "Mocked response"
        return mock_response
    
    mock_llm.invoke = AsyncMock(side_effect=mock_invoke)
    mock_llm.ainvoke = AsyncMock(side_effect=mock_invoke)
    
    # Mock with_structured_output for structured outputs
    def mock_with_structured_output(model):
        async def structured_invoke(message):
            # Return a mock Plan object
            if model == Plan:
                return Plan(steps=["Step 1", "Step 2"])
            return {}
        mock_llm.invoke = AsyncMock(side_effect=structured_invoke)
        return mock_llm
    
    mock_llm.with_structured_output = Mock(side_effect=mock_with_structured_output)
    
    return mock_llm


# ============================================================================
# FIXTURES - Test Data
# ============================================================================

@pytest.fixture
def sample_plan():
    """Sample Plan object for testing."""
    return Plan(steps=[
        "Read file content",
        "Process data",
        "Write result to file"
    ])


@pytest.fixture
def sample_sop_dict():
    """Sample SOP dictionary for testing."""
    return {
        "steps": [
            {
                "step_number": 1,
                "description": "Read file",
                "agent_type": "CRUDAgent",
                "execution_mode": "static",
                "action_type": {"agent": "CRUDAgent", "tool": "read_file"},
                "params": {"filename": "test.txt"},
                "conditions": [],
                "retry": 0,
                "store_result_as": "file_content",
                "condition_to_jump_step": None
            }
        ],
        "final_target": None
    }


@pytest.fixture
def sample_agent_dict():
    """Sample agent dictionary for validation tests."""
    return {
        "CRUDAgent": {
            "tools": {
                "read_file": lambda x: x,
                "create_file": lambda x, y: None,
                "delete_file": lambda x: None
            }
        }
    }


# ============================================================================
# FIXTURES - Environment Setup
# ============================================================================

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Automatically setup test environment variables."""
    # Mock environment variables to avoid needing real API keys
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    
    # Create test logs directory
    test_log_dir = "tests/test_logs"
    os.makedirs(test_log_dir, exist_ok=True)
    
    yield
    
    # Cleanup (optional - uncomment if needed)
    # import shutil
    # if os.path.exists(test_log_dir):
    #     shutil.rmtree(test_log_dir)


# ============================================================================
# FIXTURES - Temporary Files
# ============================================================================

@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary file for testing."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Test content")
    return str(test_file)


# ============================================================================
# MARKERS - Custom markers
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests (fast)"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (slower)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (skip by default in CI)"
    )
    config.addinivalue_line(
        "markers", "llm: marks tests that require LLM API (skip if no API key)"
    )


# ============================================================================
# HELPERS
# ============================================================================

def skip_if_no_api_key(request):
    """Skip test if API key is not set."""
    marker = request.node.get_closest_marker("llm")
    if marker:
        if not os.getenv("GROQ_API_KEY") and not os.getenv("OLLAMA_API_KEY"):
            pytest.skip("LLM API key not set. Set GROQ_API_KEY or OLLAMA_API_KEY to run this test.")


