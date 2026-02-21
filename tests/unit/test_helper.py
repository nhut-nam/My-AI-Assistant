"""
Unit tests for src.utils.helper module.
"""
import pytest
import yaml
from pathlib import Path
import tempfile
import os
from src.utils.helper import load_yaml, validate_sop, get_env


class TestLoadYaml:
    """Tests for load_yaml function."""
    
    def test_load_yaml_valid(self, tmp_path):
        """Test loading a valid YAML file."""
        yaml_content = """
        test_key: test_value
        nested:
          key: value
        """
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)
        
        result = load_yaml(str(yaml_file))
        
        assert result == {"test_key": "test_value", "nested": {"key": "value"}}
    
    def test_load_yaml_invalid_format(self, tmp_path):
        """Test loading an invalid YAML file."""
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text("invalid: yaml: content: [")
        
        with pytest.raises(ValueError, match="Invalid YAML format"):
            load_yaml(str(yaml_file))
    
    def test_load_yaml_not_found(self):
        """Test loading a non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_yaml("nonexistent.yaml")


class TestValidateSOP:
    """Tests for validate_sop function."""
    
    def test_validate_sop_valid(self, sample_sop_dict, sample_agent_dict):
        """Test validation of a valid SOP."""
        is_valid, message = validate_sop(sample_sop_dict, sample_agent_dict)
        
        assert is_valid is True
        assert message == "ok"
    
    def test_validate_sop_missing_steps(self, sample_agent_dict):
        """Test validation fails when steps are missing."""
        invalid_sop = {}
        
        is_valid, message = validate_sop(invalid_sop, sample_agent_dict)
        
        assert is_valid is False
        assert "steps" in message.lower()
    
    def test_validate_sop_invalid_agent(self, sample_sop_dict, sample_agent_dict):
        """Test validation fails with unknown agent."""
        sample_sop_dict["steps"][0]["agent_type"] = "UnknownAgent"
        
        is_valid, message = validate_sop(sample_sop_dict, sample_agent_dict)
        
        assert is_valid is False
        assert "unknown agent" in message.lower()
    
    def test_validate_sop_invalid_tool(self, sample_sop_dict, sample_agent_dict):
        """Test validation fails with unknown tool."""
        sample_sop_dict["steps"][0]["action_type"]["tool"] = "unknown_tool"
        
        is_valid, message = validate_sop(sample_sop_dict, sample_agent_dict)
        
        assert is_valid is False
        assert "unknown tool" in message.lower()
    
    def test_validate_sop_duplicate_store_result_as(self, sample_agent_dict):
        """Test validation fails with duplicate store_result_as."""
        sop = {
            "steps": [
                {
                    "step_number": 1,
                    "description": "Step 1",
                    "agent_type": "CRUDAgent",
                    "execution_mode": "static",
                    "action_type": {"agent": "CRUDAgent", "tool": "read_file"},
                    "params": {},
                    "conditions": [],
                    "retry": 0,
                    "store_result_as": "result",
                    "condition_to_jump_step": None
                },
                {
                    "step_number": 2,
                    "description": "Step 2",
                    "agent_type": "CRUDAgent",
                    "execution_mode": "static",
                    "action_type": {"agent": "CRUDAgent", "tool": "read_file"},
                    "params": {},
                    "conditions": [],
                    "retry": 0,
                    "store_result_as": "result",  # Duplicate!
                    "condition_to_jump_step": None
                }
            ]
        }
        
        is_valid, message = validate_sop(sop, sample_agent_dict)
        
        assert is_valid is False
        assert "duplicate" in message.lower()
        assert "store_result_as" in message.lower()


class TestGetEnv:
    """Tests for get_env function."""
    
    def test_get_env_exists(self, monkeypatch):
        """Test getting an existing environment variable."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        
        result = get_env("TEST_VAR")
        
        assert result == "test_value"
    
    def test_get_env_missing(self, monkeypatch):
        """Test getting a missing environment variable raises error."""
        monkeypatch.delenv("TEST_VAR", raising=False)
        
        with pytest.raises(ValueError, match="is missing"):
            get_env("TEST_VAR")
    
    def test_get_env_with_default(self, monkeypatch):
        """Test get_env with default value."""
        monkeypatch.delenv("TEST_VAR", raising=False)
        
        # get_env doesn't support default, but we can test the behavior
        with pytest.raises(ValueError):
            get_env("TEST_VAR", default="default")


