"""
Unit tests for src.models.models module.
"""
import pytest
from src.models.models import (
    Plan,
    SOPStep,
    SOP,
    Condition,
    ToolResponse,
    ExecutionState,
    ExecutionStatus
)


class TestPlan:
    """Tests for Plan model."""
    
    def test_plan_creation(self):
        """Test creating a valid Plan."""
        plan = Plan(steps=["Step 1", "Step 2", "Step 3"])
        
        assert len(plan.steps) == 3
        assert plan.steps[0] == "Step 1"
    
    def test_plan_empty_steps(self):
        """Test Plan with empty steps is valid."""
        plan = Plan(steps=[])
        
        assert len(plan.steps) == 0


class TestSOPStep:
    """Tests for SOPStep model."""
    
    def test_sop_step_creation(self):
        """Test creating a valid SOPStep."""
        step = SOPStep(
            step_number=1,
            description="Test step",
            agent_type="CRUDAgent",
            execution_mode="static",
            action_type={"agent": "CRUDAgent", "tool": "read_file"},
            params={"filename": "test.txt"},
            conditions=[],
            retry=0,
            store_result_as="result"
        )
        
        assert step.step_number == 1
        assert step.agent_type == "CRUDAgent"
        assert step.execution_mode == "static"
    
    def test_sop_step_dynamic_mode(self):
        """Test SOPStep with dynamic execution mode."""
        step = SOPStep(
            step_number=1,
            description="Dynamic step",
            agent_type="CRUDAgent",
            execution_mode="dynamic",
            action_type=None,  # Must be None for dynamic
            params={},
            conditions=[],
            retry=0
        )
        
        assert step.execution_mode == "dynamic"
        assert step.action_type is None
    
    def test_sop_step_with_conditions(self):
        """Test SOPStep with conditions."""
        condition = Condition(
            step=1,
            field="success",
            operator="==",
            value=True
        )
        
        step = SOPStep(
            step_number=2,
            description="Conditional step",
            agent_type="CRUDAgent",
            execution_mode="static",
            action_type={"agent": "CRUDAgent", "tool": "read_file"},
            params={},
            conditions=[condition],
            retry=0
        )
        
        assert len(step.conditions) == 1
        assert step.conditions[0].step == 1


class TestCondition:
    """Tests for Condition model."""
    
    def test_condition_creation(self):
        """Test creating a valid Condition."""
        condition = Condition(
            step=1,
            field="success",
            operator="==",
            value=True
        )
        
        assert condition.step == 1
        assert condition.operator == "=="
        assert condition.value is True
    
    def test_condition_field_validation(self):
        """Test Condition field format validation."""
        # Valid fields
        valid_fields = ["success", "output", "error", "meta", "output.field", "meta.key"]
        for field in valid_fields:
            condition = Condition(step=1, field=field, operator="==", value=True)
            assert condition.field == field
        
        # Invalid fields should raise ValueError
        invalid_fields = ["invalid", "output..field", "unknown"]
        for field in invalid_fields:
            with pytest.raises(ValueError):
                Condition(step=1, field=field, operator="==", value=True)


class TestToolResponse:
    """Tests for ToolResponse model."""
    
    def test_tool_response_success(self):
        """Test ToolResponse for successful execution."""
        response = ToolResponse(
            success=True,
            output="Result data",
            error=None
        )
        
        assert response.success is True
        assert response.output == "Result data"
        assert response.error is None
    
    def test_tool_response_failure(self):
        """Test ToolResponse for failed execution."""
        response = ToolResponse(
            success=False,
            output=None,
            error="Error message"
        )
        
        assert response.success is False
        assert response.error == "Error message"
    
    def test_tool_response_with_meta(self):
        """Test ToolResponse with metadata."""
        response = ToolResponse(
            success=True,
            output="Result",
            meta={"duration": 1.5, "timestamp": "2024-01-01"}
        )
        
        assert "duration" in response.meta
        assert response.meta["duration"] == 1.5


class TestExecutionStatus:
    """Tests for ExecutionStatus dataclass."""
    
    def test_execution_status_done(self):
        """Test ExecutionStatus with DONE state."""
        status = ExecutionStatus(
            state=ExecutionState.DONE,
            result="Success",
            steps=[],
            context={}
        )
        
        assert status.state == ExecutionState.DONE
        assert status.result == "Success"
    
    def test_execution_status_failed(self):
        """Test ExecutionStatus with FAILED state."""
        status = ExecutionStatus(
            state=ExecutionState.FAILED,
            error="Error message",
            steps=[],
            context={}
        )
        
        assert status.state == ExecutionState.FAILED
        assert status.error == "Error message"


